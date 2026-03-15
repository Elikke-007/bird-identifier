from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib import error, request

from PIL import Image

from .schemas import DetectionBox, IdentifyRequest, IdentifyResponse
from .species_glossary import glossary_lookup_species, normalize_species_name

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
DETECTION_MODEL_ID = "ollama-vision"
CLASSIFICATION_MODEL_ID = "llava:7b"
TRANSLATION_MODEL_ID = "deepseek-r1:14b"


class BirdRecognitionService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._translation_cache: dict[str, str] = {}

    def warmup(self) -> None:
        self._ensure_ollama_models()

    def identify(self, request: IdentifyRequest) -> IdentifyResponse:
        image_path = Path(request.image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"image not found: {image_path}")

        with Image.open(image_path) as source_image:
            source_image.verify()

        image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        vision_result = self._recognize_species(image_base64, request.top_k)

        top_species_original = self._normalize_candidate_list(
            vision_result.get("top_species_english"),
            request.top_k,
        )
        best_original = self._normalize_candidate(vision_result.get("species_english", ""))

        if best_original:
            top_species_original = [
                best_original,
                *[item for item in top_species_original if item != best_original],
            ]

        if not top_species_original:
            raise RuntimeError(f"{CLASSIFICATION_MODEL_ID} 未返回可用的鸟种结果。")

        top_species_original = top_species_original[: request.top_k]
        best_original = top_species_original[0]
        top_species_map = self._translate_species_batch(top_species_original)
        top_species = [top_species_map.get(item, item) for item in top_species_original]
        best_species = top_species[0]
        confidence = self._coerce_confidence(vision_result.get("confidence"), default=0.6)
        reason = str(vision_result.get("reason") or "").strip()
        reason_prefix = f"视觉模型 {CLASSIFICATION_MODEL_ID} 基于整张图片完成识别"
        reason_suffix = f"翻译模型 {TRANSLATION_MODEL_ID} 输出中文结果“{best_species}”"
        full_reason = "；".join(part for part in [reason_prefix, reason, reason_suffix] if part)

        return IdentifyResponse(
            species=best_species,
            speciesOriginal=best_original,
            sex="未知",
            confidence=confidence,
            speciesConfidence=confidence,
            sexConfidence=0.0,
            reason=full_reason,
            sexReason="当前后端未接入鸟类性别模型，默认返回“未知”，可在前端人工修正。",
            topSpecies=top_species,
            topSpeciesOriginal=top_species_original,
            detectionCount=0,
            detectionBox=None,
        )

    def _recognize_species(self, image_base64: str, top_k: int) -> dict[str, Any]:
        prompt = f"""
你是鸟类识别助手。请根据图片内容识别最可能的鸟种，并只输出一个 JSON 对象。

输出格式：
{{
  "species_english": "Top-1 bird species common name in English",
  "top_species_english": ["Top-1", "Top-2", "Top-3"],
  "confidence": 0.0,
  "reason": "brief reason in Chinese"
}}

要求：
1. `species_english` 和 `top_species_english` 只能填写英文鸟类常见名，不要写中文，不要写学名。
2. `top_species_english` 最多返回 {top_k} 个候选，按可能性从高到低排序。
3. `confidence` 使用 0 到 1 之间的小数。
4. 如果无法完全确认，也要给出最可能的候选。
5. 只能返回 JSON，不要输出额外说明，不要使用 markdown。
""".strip()

        raw = self._ollama_generate(
            model=CLASSIFICATION_MODEL_ID,
            prompt=prompt,
            images=[image_base64],
            format_json=True,
        )
        parsed = self._parse_json_payload(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError(f"{CLASSIFICATION_MODEL_ID} 返回了不可解析的识别结果：{raw}")
        return parsed

    def _translate_species_batch(self, species_names: list[str]) -> dict[str, str]:
        normalized = [self._normalize_candidate(item) for item in species_names if self._normalize_candidate(item)]
        missing = [item for item in normalized if item not in self._translation_cache]

        if missing:
            prompt = f"""
你是鸟类名称翻译助手。请把下面这些英文鸟类常见名翻译成简体中文，并只输出一个 JSON 对象。

输出格式：
{{
  "items": [
    {{"original": "Gray Kingbird", "translation": "灰王鹟"}}
  ]
}}

待翻译列表：
{json.dumps(missing, ensure_ascii=False)}

要求：
1. `original` 必须与输入中的英文名称完全一致。
2. `translation` 必须是简体中文常见名。
3. 如果不确定，translation 可以保留英文原名。
4. 只能返回 JSON，不要输出额外说明，不要使用 markdown。
""".strip()

            raw = self._ollama_generate(
                model=TRANSLATION_MODEL_ID,
                prompt=prompt,
                images=None,
                format_json=True,
            )
            parsed = self._parse_json_payload(raw)
            items = parsed.get("items", []) if isinstance(parsed, dict) else []

            with self._lock:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    original = self._normalize_candidate(item.get("original", ""))
                    if not original:
                        continue
                    translation = str(item.get("translation") or "").strip()
                    if not translation:
                        translation = glossary_lookup_species(original)[0]
                    self._translation_cache[original] = translation

                for original in missing:
                    if original not in self._translation_cache:
                        self._translation_cache[original] = glossary_lookup_species(original)[0]

        return {
            original: self._translation_cache.get(original, glossary_lookup_species(original)[0])
            for original in normalized
        }

    def _ensure_ollama_models(self) -> None:
        payload = self._http_get_json(f"{OLLAMA_BASE_URL}/api/tags")
        models = payload.get("models", []) if isinstance(payload, dict) else []
        available = {item.get("name") for item in models if isinstance(item, dict)}
        required = {CLASSIFICATION_MODEL_ID, TRANSLATION_MODEL_ID}
        missing = [model for model in required if model not in available]
        if missing:
            raise RuntimeError(
                f"Ollama 缺少模型：{', '.join(missing)}。当前可用模型：{', '.join(sorted(filter(None, available)))}"
            )

    def _ollama_generate(
        self,
        *,
        model: str,
        prompt: str,
        images: list[str] | None,
        format_json: bool,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }
        if images:
            payload["images"] = images
        if format_json:
            payload["format"] = "json"

        response = self._http_post_json(f"{OLLAMA_BASE_URL}/api/generate", payload)
        text = str(response.get("response") or "").strip()
        if not text:
            raise RuntimeError(f"{model} 没有返回内容。")
        return text

    def _http_get_json(self, url: str) -> dict[str, Any]:
        try:
            with request.urlopen(url, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"无法连接 Ollama 服务：{OLLAMA_BASE_URL}。{exc}") from exc

    def _http_post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with request.urlopen(req, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"调用 Ollama 失败：HTTP {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"无法连接 Ollama 服务：{OLLAMA_BASE_URL}。{exc}") from exc

    def _parse_json_payload(self, raw: str) -> dict[str, Any] | list[Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start : end + 1])
            raise

    def _normalize_candidate(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        normalized = normalize_species_name(value)
        return normalized if normalized else ""

    def _normalize_candidate_list(self, value: Any, top_k: int) -> list[str]:
        if not isinstance(value, list):
            return []

        items: list[str] = []
        for candidate in value:
            normalized = self._normalize_candidate(candidate)
            if normalized and normalized not in items:
                items.append(normalized)
            if len(items) >= top_k:
                break
        return items

    def _coerce_confidence(self, value: Any, default: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = default
        confidence = max(0.0, min(confidence, 1.0))
        return round(confidence, 4)
