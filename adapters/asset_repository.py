from __future__ import annotations

import re
from pathlib import Path


class LocalAssetRepository:
    """Simple local image search for migrated presentation image planning."""

    def __init__(self, base_dir: Path | None = None):
        root = Path(__file__).resolve().parent.parent
        self.base_dir = base_dir or (root / "vendor_presentation_core" / "assets")

    def list_images(self) -> list[Path]:
        if not self.base_dir.exists():
            return []
        patterns = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.svg")
        files: list[Path] = []
        for pattern in patterns:
            files.extend(self.base_dir.rglob(pattern))
        return sorted(files)

    def search_images(self, query: str, count: int = 3) -> list[dict]:
        tokens = [token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", query.lower()) if token]
        matches = []
        for image in self.list_images():
            score = sum(token in image.stem.lower() for token in tokens)
            if score:
                matches.append({"path": str(image), "name": image.name, "score": score})
        matches.sort(key=lambda item: (-item["score"], item["name"]))
        return matches[:count]
