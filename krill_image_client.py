from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from config import (
    KRILL_IMAGE_API_KEY,
    KRILL_IMAGE_API_URL,
    KRILL_IMAGE_MODEL,
    missing_krill_image_settings,
)

KRILL_IMAGE_TIMEOUT_SECONDS = 300
KRILL_IMAGE_DEFAULT_SIZE = "1280x720"
KRILL_IMAGE_DEFAULT_QUALITY = "high"


class KrillImageClient:
    def __init__(self) -> None:
        missing = missing_krill_image_settings()
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(f"Krill image API is not configured: missing {names}")
        self.api_url = KRILL_IMAGE_API_URL
        self.timeout_seconds = KRILL_IMAGE_TIMEOUT_SECONDS
        self.http_client = httpx.Client(timeout=httpx.Timeout(connect=30, read=self.timeout_seconds, write=30, pool=30))
        self.client = OpenAI(
            api_key=KRILL_IMAGE_API_KEY,
            base_url=self.api_url,
            http_client=self.http_client,
            timeout=self.timeout_seconds,
        )

    def _extract_asset(self, result) -> tuple[str, str]:
        payload = result.model_dump() if hasattr(result, "model_dump") else result
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list) and payload["data"]:
                candidate = payload["data"][0]
            elif isinstance(payload.get("result"), dict):
                candidate = payload["result"]
            else:
                candidate = payload
        else:
            candidate = None
            data_attr = getattr(result, "data", None)
            if isinstance(data_attr, list) and data_attr:
                candidate = data_attr[0]
            elif getattr(result, "result", None) is not None:
                candidate = getattr(result, "result")
            else:
                candidate = result

        def _read(key: str):
            if isinstance(candidate, dict):
                return candidate.get(key)
            return getattr(candidate, key, None)

        for key in ("b64_json", "image_base64", "base64", "b64"):
            value = _read(key)
            if isinstance(value, str) and value.strip():
                return "base64", value.strip()

        for key in ("url", "image_url"):
            value = _read(key)
            if isinstance(value, str) and value.strip():
                return "url", value.strip()

        raise RuntimeError("Image API response does not contain a supported image field")

    def _write_base64_image(self, encoded: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(encoded))
        return output_path

    def _download_image(self, url: str, output_path: Path) -> Path:
        response = self.http_client.get(url)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path

    def _save_result_image(self, result, output_path: Path) -> Path:
        asset_kind, asset_value = self._extract_asset(result)
        if asset_kind == "base64":
            return self._write_base64_image(asset_value, output_path)
        return self._download_image(asset_value, output_path)

    def generate_image(self, prompt: str, output_path: Path) -> Path:
        result = self.client.images.generate(
            model=KRILL_IMAGE_MODEL,
            prompt=prompt,
            size=KRILL_IMAGE_DEFAULT_SIZE,
            quality=KRILL_IMAGE_DEFAULT_QUALITY,
        )
        return self._save_result_image(result, output_path)

    def edit_image(self, prompt: str, image_path: Path, output_path: Path, *, mask_path: Path | None = None) -> Path:
        with image_path.open("rb") as image_file:
            kwargs = {
                "model": KRILL_IMAGE_MODEL,
                "image": image_file,
                "prompt": prompt,
                "size": KRILL_IMAGE_DEFAULT_SIZE,
                "quality": KRILL_IMAGE_DEFAULT_QUALITY,
            }
            if mask_path is not None:
                with mask_path.open("rb") as mask_file:
                    kwargs["mask"] = mask_file
                    result = self.client.images.edit(**kwargs)
            else:
                result = self.client.images.edit(**kwargs)
        return self._save_result_image(result, output_path)


def infer_extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return suffix
    return ".png"
