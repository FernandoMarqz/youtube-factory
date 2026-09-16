"""Caption a persisted project without regenerating upstream assets."""

import re

from youtube_factory.application.config import ChannelConfig
from youtube_factory.application.exceptions import CaptionAlignmentError
from youtube_factory.application.services.captions import CaptionPlanner, build_ass
from youtube_factory.domain.models import CaptionPlan
from youtube_factory.ports import CaptionAlignmentProvider, ProjectArtifactStore


class CaptionProjectUseCase:
    def __init__(
        self,
        store: ProjectArtifactStore,
        alignment: CaptionAlignmentProvider,
        channel: ChannelConfig,
    ) -> None:
        self._store = store
        self._alignment = alignment
        self._channel = channel
        self._planner = CaptionPlanner()

    def execute(self, project_id: str) -> CaptionPlan:
        narration, audio = self._store.load_caption_audio(project_id)
        alignment = self._alignment.align(narration, audio, self._channel.language)
        if alignment.topic_id != narration.topic_id or [
            word.text for word in alignment.words
        ] != re.findall(r"\S+", narration.narration_text):
            raise CaptionAlignmentError("alignment does not match persisted narration")
        plan = self._planner.plan(
            alignment, self._channel.language, self._channel.captions.grouping
        )
        ass = build_ass(
            plan,
            self._channel.captions.style,
            self._channel.render.width,
            self._channel.render.height,
            self._channel.captions.grouping.max_characters_per_line,
            alignment=alignment,
            emphasis=self._channel.captions.emphasis,
        )
        self._store.save_captions(
            project_id, alignment, plan, ass, self._alignment.identifier, self._planner.identifier
        )
        return plan
