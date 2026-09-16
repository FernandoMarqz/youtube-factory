"""Deterministic caption grouping and ASS serialization."""

import re

from youtube_factory.application.config import (
    CaptionEmphasisConfig,
    CaptionGroupingConfig,
    CaptionStyleConfig,
)
from youtube_factory.application.exceptions import CaptionPlanningError
from youtube_factory.domain.models import AlignedWord, CaptionCue, CaptionPlan, WordAlignment


class CaptionPlanner:
    identifier = "deterministic-caption-planner-v1"

    def plan(
        self, alignment: WordAlignment, language: str, config: CaptionGroupingConfig
    ) -> CaptionPlan:
        words = alignment.words
        groups: list[list[int]] = []
        current: list[int] = []
        for index, word in enumerate(words):
            candidate = [*current, index]
            candidate_text = " ".join(words[i].text for i in candidate)
            candidate_duration = word.end_seconds - words[candidate[0]].start_seconds
            if current and (
                len(candidate) > config.max_words_per_cue
                or len(candidate_text) > 2 * config.max_characters_per_line + 1
                or not _can_wrap(candidate_text, config.max_characters_per_line)
                or candidate_duration > config.max_cue_duration_seconds
            ):
                groups.append(current)
                current = [index]
            else:
                current = candidate
            if current and re.search(r"[.!?;:]$", word.text):
                groups.append(current)
                current = []
        if current:
            groups.append(current)
        for index in range(1, len(groups)):
            previous, group = groups[index - 1], groups[index]
            if len(group) != 1 or len(previous) < 3:
                continue
            shifted = [previous[-1], *group]
            shifted_text = " ".join(words[i].text for i in shifted)
            shifted_duration = words[shifted[-1]].end_seconds - words[shifted[0]].start_seconds
            if (
                not re.search(r"[.!?;:]$", words[previous[-1]].text)
                and _can_wrap(shifted_text, config.max_characters_per_line)
                and shifted_duration <= config.max_cue_duration_seconds
            ):
                groups[index - 1] = previous[:-1]
                groups[index] = shifted
        index = 0
        while index < len(groups):
            group = groups[index]
            duration = words[group[-1]].end_seconds - words[group[0]].start_seconds
            if (duration < config.min_cue_duration_seconds or len(group) == 1) and len(groups) > 1:
                neighbor = index - 1 if index else 1
                merged = groups[neighbor] + group if neighbor < index else group + groups[neighbor]
                merged_text = " ".join(words[i].text for i in merged)
                merged_duration = words[merged[-1]].end_seconds - words[merged[0]].start_seconds
                if (
                    len(merged) <= config.max_words_per_cue
                    and _can_wrap(merged_text, config.max_characters_per_line)
                    and merged_duration <= config.max_cue_duration_seconds
                ):
                    groups[neighbor] = merged
                    groups.pop(index)
                    index = max(0, neighbor - 1)
                    continue
            index += 1
        cues = []
        for sequence, group in enumerate(groups, start=1):
            text = " ".join(words[index].text for index in group)
            if not _can_wrap(text, config.max_characters_per_line):
                raise CaptionPlanningError(f"caption cue {sequence} cannot fit on two lines")
            cues.append(
                CaptionCue(
                    sequence=sequence,
                    text=text,
                    start_seconds=words[group[0]].start_seconds,
                    end_seconds=words[group[-1]].end_seconds,
                    word_start_index=group[0],
                    word_end_index=group[-1] + 1,
                )
            )
        return CaptionPlan(topic_id=alignment.topic_id, language=language, cues=cues)


def _wrap(text: str, width: int) -> str:
    words = text.split()
    if len(text) <= width:
        return text
    options = [
        (abs(len(" ".join(words[:split])) - len(" ".join(words[split:]))), split)
        for split in range(1, len(words))
        if len(" ".join(words[:split])) <= width and len(" ".join(words[split:])) <= width
    ]
    if not options:
        raise CaptionPlanningError("caption text exceeds the configured two-line width")
    split = min(options)[1]
    return " ".join(words[:split]) + "\\N" + " ".join(words[split:])


def _can_wrap(text: str, width: int) -> bool:
    try:
        _wrap(text, width)
    except CaptionPlanningError:
        return False
    return True


def _ass_centiseconds(seconds: float) -> int:
    return round(seconds * 100)


def _ass_time(centiseconds: int) -> str:
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def _ass_color(rgb: str, alpha: bool = False) -> str:
    red, green, blue = rgb[1:3], rgb[3:5], rgb[5:7]
    return f"&H{'00' if alpha else ''}{blue}{green}{red}&"


def _cue_word_ranges(plan: CaptionPlan, alignment: WordAlignment) -> list[tuple[int, int]]:
    """Validate explicit indexes or deterministically resolve legacy Phase 6 cues."""
    if plan.topic_id != alignment.topic_id:
        raise CaptionPlanningError("caption plan and word alignment belong to different topics")
    ranges: list[tuple[int, int]] = []
    next_index = 0
    for cue in plan.cues:
        tokens = cue.text.split()
        start = cue.word_start_index if cue.word_start_index is not None else next_index
        end = cue.word_end_index if cue.word_end_index is not None else start + len(tokens)
        if start != next_index or end != start + len(tokens) or end > len(alignment.words):
            raise CaptionPlanningError(f"caption cue {cue.sequence} has invalid word indexes")
        words = alignment.words[start:end]
        if [word.text for word in words] != tokens:
            raise CaptionPlanningError(
                f"caption cue {cue.sequence} does not match canonical aligned words; "
                "regenerate captions with caption-project"
            )
        if any(
            word.start_seconds < cue.start_seconds - 0.001
            or word.end_seconds > cue.end_seconds + 0.001
            for word in words
        ):
            raise CaptionPlanningError(f"caption cue {cue.sequence} has words outside its interval")
        ranges.append((start, end))
        next_index = end
    if next_index != len(alignment.words):
        raise CaptionPlanningError("caption cues do not cover all aligned words")
    return ranges


def _escape_ass_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _cue_text(cue: CaptionCue, line_width: int, active_index: int | None, active_color: str) -> str:
    wrapped = _wrap(cue.text, line_width)
    line_break_at = len(wrapped.split("\\N", 1)[0].split()) if "\\N" in wrapped else None
    pieces: list[str] = []
    for index, token in enumerate(cue.text.split()):
        if index:
            pieces.append("\\N" if index == line_break_at else " ")
        escaped = _escape_ass_text(token)
        if index == active_index:
            pieces.append("{\\1c" + active_color + "}" + escaped + "{\\r}")
        else:
            pieces.append(escaped)
    return "".join(pieces)


def _dynamic_events(
    cue: CaptionCue, words: list[AlignedWord], line_width: int, active_color: str
) -> list[tuple[int, int, str]]:
    """Build states from independently rounded absolute word boundaries."""
    start = _ass_centiseconds(cue.start_seconds)
    end = _ass_centiseconds(cue.end_seconds)
    if end <= start:
        raise CaptionPlanningError(f"caption cue {cue.sequence} is shorter than ASS precision")
    intervals = [
        (
            max(start, _ass_centiseconds(word.start_seconds)),
            min(end, _ass_centiseconds(word.end_seconds)),
        )
        for word in words
    ]
    boundaries = sorted({start, end, *(edge for interval in intervals for edge in interval)})
    states: list[tuple[int, int, int | None]] = []
    for left, right in zip(boundaries, boundaries[1:], strict=False):
        active = next(
            (
                index
                for index in reversed(range(len(words)))
                if intervals[index][0] <= left < intervals[index][1]
            ),
            None,
        )
        if states and states[-1][2] == active:
            states[-1] = (states[-1][0], right, active)
        else:
            states.append((left, right, active))
    return [
        (left, right, _cue_text(cue, line_width, active, active_color))
        for left, right, active in states
    ]


def build_ass(
    plan: CaptionPlan,
    style: CaptionStyleConfig,
    width: int,
    height: int,
    line_width: int,
    *,
    alignment: WordAlignment | None = None,
    emphasis: CaptionEmphasisConfig | None = None,
) -> str:
    """Render stable-layout static or word-emphasized UTF-8 ASS cues."""
    font = style.font_family.replace(",", " ").replace("\n", " ")
    inactive_color = _ass_color(emphasis.inactive_color if emphasis else "#FFFFFF", alpha=True)
    dynamic = emphasis is not None and emphasis.enabled and emphasis.mode == "word"
    if dynamic and alignment is None:
        raise CaptionPlanningError("word emphasis requires persisted word-alignment.json")
    ranges = _cue_word_ranges(plan, alignment) if dynamic and alignment is not None else []
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{font},{style.font_size},{inactive_color},{inactive_color},&H00000000,"
        f"&H80000000,{-1 if style.bold else 0},0,0,0,100,100,0,0,1,"
        f"{style.outline_width},{2 if style.shadow else 0},2,80,80,"
        f"{style.margin_vertical},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = []
    for cue_index, cue in enumerate(plan.cues):
        if style.max_lines == 1 and len(cue.text) > line_width:
            raise CaptionPlanningError(f"caption cue {cue.sequence} exceeds one line")
        if dynamic and alignment is not None and emphasis is not None:
            start, end = ranges[cue_index]
            events = _dynamic_events(
                cue, alignment.words[start:end], line_width, _ass_color(emphasis.active_color)
            )
        else:
            wrapped = _wrap(cue.text, line_width) if style.max_lines == 2 else cue.text
            escaped = "\\N".join(_escape_ass_text(part) for part in wrapped.split("\\N"))
            events = [
                (_ass_centiseconds(cue.start_seconds), _ass_centiseconds(cue.end_seconds), escaped)
            ]
        for start_cs, end_cs, rendered_text in events:
            lines.append(
                f"Dialogue: 0,{_ass_time(start_cs)},{_ass_time(end_cs)},"
                f"Caption,,0,0,0,,{rendered_text}"
            )
    return header + "\n".join(lines) + "\n"
