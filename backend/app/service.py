from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PIL import Image
from transformers import pipeline
from ultralytics import YOLO

from .schemas import DetectionBox, IdentifyRequest, IdentifyResponse
from .species_glossary import glossary_lookup_species

DETECTION_MODEL_ID = "yolo11x.pt"
CLASSIFICATION_MODEL_ID = "chriamue/bird-species-classifier"
TRANSLATION_MODEL_ID = "Helsinki-NLP/opus-mt-en-zh"
BIRD_CLASS_ID = 14


class BirdRecognitionService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detector: YOLO | None = None
        self._classifier: Any | None = None
        self._translator: Any | None = None
        self._translation_cache: dict[str, str] = {}

    def warmup(self) -> None:
        self._get_detector()
        self._get_classifier()
        self._get_translator()

    def identify(self, request: IdentifyRequest) -> IdentifyResponse:
        image_path = Path(request.image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"image not found: {image_path}")

        with Image.open(image_path) as source_image:
            source_image = source_image.convert("RGB")
            detection_box, detection_count = self._detect_primary_bird(image_path)
            crop_image = self._crop_for_classification(source_image, detection_box)
            top_items = self._classify_crop(crop_image, request.top_k)

        top_species_original = [item["label"] for item in top_items]
        top_species = [self._to_chinese_species(item["label"])[0] for item in top_items]
        best_item = top_items[0]
        best_species, best_original, translated = self._to_chinese_species(best_item["label"])
        reason_suffix = (
            f"已映射为中文名“{best_species}”"
            if translated
            else f"由翻译模型 {TRANSLATION_MODEL_ID} 生成中文结果“{best_species}”"
        )
        detect_reason = (
            f"先使用 {DETECTION_MODEL_ID} 检测到 {detection_count} 只鸟，再对主目标裁剪图进行分类"
            if detection_box is not None
            else "未检测到明确鸟目标，已回退为整张图片分类"
        )

        return IdentifyResponse(
            species=best_species,
            speciesOriginal=best_original,
            sex="未知",
            confidence=round(float(best_item["score"]), 4),
            speciesConfidence=round(float(best_item["score"]), 4),
            sexConfidence=0.0,
            reason=f"{detect_reason}；分类模型 {CLASSIFICATION_MODEL_ID} 输出 Top-1：{best_original}，{reason_suffix}",
            sexReason="当前后端未接入鸟类性别模型，默认返回“未知”，可在前端人工修正。",
            topSpecies=top_species,
            topSpeciesOriginal=top_species_original,
            detectionCount=detection_count,
            detectionBox=detection_box,
        )

    def _get_detector(self) -> YOLO:
        if self._detector is None:
            with self._lock:
                if self._detector is None:
                    self._detector = YOLO(DETECTION_MODEL_ID)
        return self._detector

    def _get_classifier(self) -> Any:
        if self._classifier is None:
            with self._lock:
                if self._classifier is None:
                    self._classifier = pipeline(
                        task="image-classification",
                        model=CLASSIFICATION_MODEL_ID,
                        top_k=5,
                    )
        return self._classifier

    def _get_translator(self) -> Any:
        if self._translator is None:
            with self._lock:
                if self._translator is None:
                    self._translator = pipeline(
                        task="translation",
                        model=TRANSLATION_MODEL_ID,
                    )
        return self._translator

    def _detect_primary_bird(self, image_path: Path) -> tuple[DetectionBox | None, int]:
        detector = self._get_detector()
        results = detector.predict(source=str(image_path), classes=[BIRD_CLASS_ID], verbose=False)
        boxes = results[0].boxes if results else None
        if boxes is None or boxes.xyxy is None or len(boxes.xyxy) == 0:
            return None, 0

        xyxy = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist() if boxes.conf is not None else [0.0] * len(xyxy)

        candidates = []
        for coords, confidence in zip(xyxy, confidences, strict=False):
            x1, y1, x2, y2 = coords
            area = max(x2 - x1, 0) * max(y2 - y1, 0)
            candidates.append((area, DetectionBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=float(confidence))))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1], len(candidates)

    def _crop_for_classification(self, image: Image.Image, detection_box: DetectionBox | None) -> Image.Image:
        if detection_box is None:
            return image.copy()

        width, height = image.size
        pad_x = int((detection_box.x2 - detection_box.x1) * 0.08)
        pad_y = int((detection_box.y2 - detection_box.y1) * 0.08)
        left = max(int(detection_box.x1) - pad_x, 0)
        top = max(int(detection_box.y1) - pad_y, 0)
        right = min(int(detection_box.x2) + pad_x, width)
        bottom = min(int(detection_box.y2) + pad_y, height)
        return image.crop((left, top, right, bottom))

    def _classify_crop(self, crop_image: Image.Image, top_k: int) -> list[dict[str, Any]]:
        classifier = self._get_classifier()
        result = classifier(crop_image, top_k=top_k)
        if isinstance(result, list):
            return result
        return [result]

    def _to_chinese_species(self, label: str) -> tuple[str, str, bool]:
        chinese, original, translated = glossary_lookup_species(label)
        if translated:
            return chinese, original, True

        cached = self._translation_cache.get(original)
        if cached:
            return cached, original, False

        translator = self._get_translator()
        result = translator(original)
        if isinstance(result, list):
            translation_text = result[0].get("translation_text", "").strip()
        else:
            translation_text = result.get("translation_text", "").strip()

        chinese = translation_text or original
        self._translation_cache[original] = chinese
        return chinese, original, False
