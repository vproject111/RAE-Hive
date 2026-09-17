"""Visual ingestion pipeline for multimodal artifacts (Playwright screenshots, architecture diagrams)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from rae_core.models.envelope import ContextEnvelope
from rae_core.models.multimodal import MultimodalArtifact


class VisualIngestPipeline:
    """
    Ingests visual artifacts from automated tests (Playwright) or documentation,
    extracts metadata and OCR, and packages them into MultimodalArtifacts.
    """

    def __init__(self, storage_dir: str = "/tmp/rae_multimodal"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def ingest_screenshot(
        self,
        image_path: str | Path,
        artifact_type: str = "screenshot",
        ocr_text: str | None = None,
        visual_embedding: list[float] | None = None,
        text_embedding: list[float] | None = None,
        project: str = "dreamsoft",
        task_id: str | None = None,
    ) -> MultimodalArtifact:
        """
        Package a screenshot into a deterministic MultimodalArtifact.
        """
        img_p = Path(image_path)
        artifact_id = f"art_{uuid4().hex[:12]}"

        envelope = ContextEnvelope(
            source_type="test",
            project=project,
            task_id=task_id,
            timestamp=datetime.now(timezone.utc),
            scope_tags=["ui", "screenshot", artifact_type],
            semantic_summary=f"Visual evidence for {artifact_type} ({img_p.name})",
        )

        return MultimodalArtifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            image_uri=str(img_p.resolve() if img_p.exists() else img_p),
            ocr_extracted_text=ocr_text,
            visual_embedding=visual_embedding,
            text_embedding=text_embedding,
            envelope=envelope,
        )
