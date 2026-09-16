"""Deterministic caption grouping and ASS serialization."""

import re

from youtube_factory.application.config import CaptionGroupingConfig, CaptionStyleConfig
from youtube_factory.application.exceptions import CaptionPlanningError
from youtube_factory.domain.models import CaptionCue, CaptionPlan, WordAlignment


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


def _ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def build_ass(
    plan: CaptionPlan, style: CaptionStyleConfig, width: int, height: int, line_width: int
) -> str:
    """Render a stable, UTF-8 ASS document with explicit two-line wrapping."""
    font = style.font_family.replace(",", " ").replace("\n", " ")
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{font},{style.font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        f"&H80000000,{-1 if style.bold else 0},0,0,0,100,100,0,0,1,"
        f"{style.outline_width},{2 if style.shadow else 0},2,80,80,"
        f"{style.margin_vertical},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = []
    for cue in plan.cues:
        wrapped = _wrap(cue.text, line_width) if style.max_lines == 2 else cue.text
        if style.max_lines == 1 and len(wrapped) > line_width:
            raise CaptionPlanningError(f"caption cue {cue.sequence} exceeds one line")
        wrapped = "\\N".join(
            part.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            for part in wrapped.split("\\N")
        )
        lines.append(
            f"Dialogue: 0,{_ass_time(cue.start_seconds)},{_ass_time(cue.end_seconds)},"
            f"Caption,,0,0,0,,{wrapped}"
        )
    return header + "\n".join(lines) + "\n"
