from __future__ import annotations

import base64
import json
import os
import re
import threading
from pathlib import Path
from typing import Any
from urllib import error, request

from PIL import Image

from .schemas import IdentifyResponse
from .species_glossary import glossary_lookup_species, normalize_species_name

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
DETECTION_MODEL_ID = "ollama-vision"
CLASSIFICATION_MODEL_ID = "llava:7b"
TRANSLATION_MODEL_ID = "deepseek-r1:14b"
INVALID_SPECIES_MARKERS = {
    "top-1",
    "top 1",
    "bird species",
    "common name in english",
    "unknown",
    "not sure",
    "n/a",
}


class BirdRecognitionService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._translation_cache: dict[str, str] = {}

    def warmup(self) -> None:
        self._ensure_ollama_models()

    def identify(self, request) -> IdentifyResponse:
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
            top_species_original = [best_original, *[item for item in top_species_original if item != best_original]]

        if not top_species_original:
            raise RuntimeError(
                f"{CLASSIFICATION_MODEL_ID} 没有返回可用鸟种结果。原始输出：{vision_result.get('raw_output', '')}"
            )

        top_species_original = top_species_original[: request.top_k]
        best_original = top_species_original[0]
        top_species_map = self._translate_species_batch(top_species_original)
        top_species = [top_species_map.get(item, item) for item in top_species_original]
        best_species = top_species[0]
        confidence = self._coerce_confidence(vision_result.get("confidence"), default=0.6)
        reason = str(vision_result.get("reason") or "").strip()
        full_reason = "；".join(
            part
            for part in [
                f"视觉模型 {CLASSIFICATION_MODEL_ID} 基于整张图片完成识别",
                reason,
                f"翻译模型 {TRANSLATION_MODEL_ID} 输出中文结果“{best_species}”",
            ]
            if part
        )

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
        json_prompt = f"""
你是一名鸟类识别助手。请观察图片中的鸟，只返回一个 JSON 对象，不要返回说明文字，不要返回 markdown。

JSON 格式必须严格如下：
{{
  "species_english": "Gray Kingbird",
  "top_species_english": ["Gray Kingbird", "Tropical Kingbird", "Eastern Kingbird"],
  "confidence": 0.72,
  "reason": "图中鸟停在树枝上，头部偏灰，嘴较粗直，体型与王鹟类相符。"
}}

要求：
1. `species_english` 和 `top_species_english` 必须填写真实的英文鸟类常见名。
2. 不允许返回示例词、占位词、模板词，例如 Top-1、bird species、common name in English。
3. `top_species_english` 最多返回 {top_k} 个候选，按可能性排序。
4. `confidence` 必须是 0 到 1 之间的小数。
5. 如果不确定，也要给出最可能的真实鸟名。
""".strip()

        raw = self._ollama_generate(
            model=CLASSIFICATION_MODEL_ID,
            prompt=json_prompt,
            images=[image_base64],
            format_json=True,
        )
        parsed = self._parse_json_payload(raw)
        candidate = self._normalize_candidate(parsed.get("species_english", "")) if isinstance(parsed, dict) else ""
        if isinstance(parsed, dict) and self._is_valid_species_name(candidate):
            parsed["raw_output"] = raw
            return parsed

        fallback_prompt = f"""
请识别图片中的鸟，并按下面纯文本格式输出，不要输出别的内容：

species_english: Gray Kingbird
top_species_english: Gray Kingbird | Tropical Kingbird | Eastern Kingbird
confidence: 0.72
reason: 图中鸟停在树枝上，头部偏灰，嘴较粗直，体型与王鹟类相符。

要求：
1. 必须填写真实英文鸟类常见名。
2. 不允许输出 Top-1、bird species、common name in English 这类模板词。
3. 最多返回 {top_k} 个候选。
""".strip()

        fallback_raw = self._ollama_generate(
            model=CLASSIFICATION_MODEL_ID,
            prompt=fallback_prompt,
            images=[image_base64],
            format_json=False,
        )
        fallback_parsed = self._parse_fallback_recognition(fallback_raw, top_k)
        fallback_parsed["raw_output"] = fallback_raw
        return fallback_parsed

    def _translate_species_batch(self, species_names: list[str]) -> dict[str, str]:
        normalized = [self._normalize_candidate(item) for item in species_names if self._normalize_candidate(item)]
        missing = [item for item in normalized if item not in self._translation_cache]

        if missing:
            items = self._request_translation_batch(missing)
            with self._lock:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    original = self._normalize_candidate(item.get("original", ""))
                    if not original:
                        continue
                    translation = self._sanitize_translation(original, item.get("translation", ""))
                    if translation:
                        self._translation_cache[original] = translation

                unresolved = [original for original in missing if original not in self._translation_cache]
                if unresolved:
                    retry_items = self._retry_translation_batch(unresolved)
                    for item in retry_items:
                        if not isinstance(item, dict):
                            continue
                        original = self._normalize_candidate(item.get("original", ""))
                        if not original:
                            continue
                        translation = self._sanitize_translation(original, item.get("translation", ""))
                        if translation:
                            self._translation_cache[original] = translation

                for original in missing:
                    if original not in self._translation_cache:
                        glossary_translation = glossary_lookup_species(original)[0]
                        self._translation_cache[original] = glossary_translation if glossary_translation != original else original

        return {original: self._translation_cache.get(original, glossary_lookup_species(original)[0]) for original in normalized}

    def _request_translation_batch(self, species_names: list[str]) -> list[dict[str, Any]]:
        prompt = f"""
你是鸟类名称翻译助手。请把下面这些英文鸟类常见名翻译成简体中文，并只输出一个 JSON 对象。

输出格式：
{{
  "items": [
    {{"original": "Gray Kingbird", "translation": "灰王霸鹟"}}
  ]
}}

待翻译列表：
{json.dumps(species_names, ensure_ascii=False)}

要求：
1. `original` 必须与输入中的英文名称完全一致。
2. `translation` 必须是简体中文常见名，不能直接照抄英文原名。
3. 如果不确定，请给出最常见、最接近的中文鸟名；不要返回解释。
4. 只能返回 JSON，不要输出额外说明，不要使用 markdown。
""".strip()

        raw = self._ollama_generate(
            model=TRANSLATION_MODEL_ID,
            prompt=prompt,
            images=None,
            format_json=True,
        )
        parsed = self._parse_json_payload(raw)
        return parsed.get("items", []) if isinstance(parsed, dict) else []

    def _retry_translation_batch(self, species_names: list[str]) -> list[dict[str, Any]]:
        prompt = f"""
请把下列英文鸟类常见名翻译成简体中文。只能返回 JSON，不要返回说明。

输出格式：
{{
  "items": [
    {{"original": "Gray Kingbird", "translation": "灰王霸鹟"}}
  ]
}}

待翻译列表：
{json.dumps(species_names, ensure_ascii=False)}

强制要求：
1. translation 必须包含中文字符。
2. 不允许直接返回英文原文。
3. 不确定时也要给出一个中文常见名近似译法。
""".strip()

        raw = self._ollama_generate(
            model=TRANSLATION_MODEL_ID,
            prompt=prompt,
            images=None,
            format_json=True,
        )
        parsed = self._parse_json_payload(raw)
        return parsed.get("items", []) if isinstance(parsed, dict) else []

    def _sanitize_translation(self, original: str, translation_value: Any) -> str:
        translation = str(translation_value or "").strip()
        if not translation:
            return ""
        if translation.lower() == original.lower():
            return ""
        if re.search(r"[A-Za-z]", translation) and not re.search(r"[\u4e00-\u9fff]", translation):
            return ""
        return translation

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

    def _ollama_generate(self, *, model: str, prompt: str, images: list[str] | None, format_json: bool) -> str:
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

    def _parse_fallback_recognition(self, raw: str, top_k: int) -> dict[str, Any]:
        def extract(pattern: str) -> str:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            return match.group(1).strip() if match else ""

        species = self._normalize_candidate(extract(r"species_english\s*:\s*(.+)"))
        raw_candidates = extract(r"top_species_english\s*:\s*(.+)")
        reason = extract(r"reason\s*:\s*(.+)")
        confidence_text = extract(r"confidence\s*:\s*([0-9.]+)")
        candidates = [self._normalize_candidate(item) for item in re.split(r"\||,", raw_candidates) if self._normalize_candidate(item)]

        if species and species not in candidates:
            candidates.insert(0, species)

        candidates = [item for item in candidates if self._is_valid_species_name(item)]
        if not candidates:
            raise RuntimeError(f"{CLASSIFICATION_MODEL_ID} 返回了不可用结果：{raw}")

        return {
            "species_english": candidates[0],
            "top_species_english": candidates[:top_k],
            "confidence": self._coerce_confidence(confidence_text, default=0.6),
            "reason": reason,
        }

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
            if self._is_valid_species_name(normalized) and normalized not in items:
                items.append(normalized)
            if len(items) >= top_k:
                break
        return items

    def _is_valid_species_name(self, value: str) -> bool:
        if not value:
            return False
        compact = value.strip().lower()
        if len(compact) < 3:
            return False
        return not any(marker in compact for marker in INVALID_SPECIES_MARKERS)

    def _coerce_confidence(self, value: Any, default: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = default
        confidence = max(0.0, min(confidence, 1.0))
        return round(confidence, 4)
