"""모델 레지스트리 -- 설정 파일 기반 OCR 엔진 로딩/교체."""
import os
import yaml
from pathlib import Path
from PIL import Image

from .models import (
    BaseOCREngine, OCRResult, CheckboxDetector, SignatureDetector,
)
from .models.trocr_engine import TrOCREngine

# 엔진 타입 → 클래스 매핑
ENGINE_MAP = {
    "trocr": TrOCREngine,
}

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "model_config.yaml")


def load_config(config_path: str | None = None) -> dict:
    path = config_path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        return {"models": {}, "default_model": None}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def create_engine(model_id: str, config: dict | None = None) -> BaseOCREngine:
    """설정에서 모델 ID로 OCR 엔진을 생성한다."""
    if config is None:
        config = load_config()

    models = config.get("models", {})
    if model_id not in models:
        raise ValueError(f"모델 '{model_id}'을 설정에서 찾을 수 없습니다. 가능한 모델: {list(models.keys())}")

    model_conf = models[model_id]
    engine_type = model_conf.get("engine", "trocr")

    if engine_type not in ENGINE_MAP:
        raise ValueError(f"지원하지 않는 엔진 타입: {engine_type}. 가능: {list(ENGINE_MAP.keys())}")

    engine_cls = ENGINE_MAP[engine_type]

    kwargs = {}
    if "model_path" in model_conf:
        # 상대경로 → 절대경로 (config 파일 기준)
        mp = model_conf["model_path"]
        if not os.path.isabs(mp):
            mp = os.path.normpath(os.path.join(os.path.dirname(DEFAULT_CONFIG_PATH), mp))
        kwargs["model_path"] = mp
    if "model_name" in model_conf:
        kwargs["model_name"] = model_conf["model_name"]
    if "device" in model_conf:
        kwargs["device"] = model_conf["device"]
    if "max_new_tokens" in model_conf:
        kwargs["max_new_tokens"] = model_conf["max_new_tokens"]
    if "num_beams" in model_conf:
        kwargs["num_beams"] = model_conf["num_beams"]
    if "batch_size" in model_conf:
        kwargs["batch_size"] = model_conf["batch_size"]

    return engine_cls(**kwargs)


class ModelRegistry:
    """OCR 엔진 + 체크박스/서명 감지기를 통합 관리하는 레지스트리.

    사용법:
        registry = ModelRegistry("model_config.yaml")
        results = registry.process_requests(requests)
    """

    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)
        self.default_model = self.config.get("default_model")
        self._engines: dict[str, BaseOCREngine] = {}
        self.checkbox_detector = CheckboxDetector()
        self.signature_detector = SignatureDetector()

    def get_engine(self, model_id: str | None = None) -> BaseOCREngine:
        mid = model_id or self.default_model
        if not mid:
            raise ValueError("default_model이 설정되지 않았고 model_id도 제공되지 않았습니다")
        if mid not in self._engines:
            self._engines[mid] = create_engine(mid, self.config)
        return self._engines[mid]

    def process_requests(self, requests: list[dict], model_id: str | None = None) -> list[dict]:
        """요청 리스트를 타입별로 분류하여 처리한다."""
        from .models.base_engine import OCRResult as _  # type check

        ocr_reqs = []
        checkbox_reqs = []
        signature_reqs = []

        OCR_TYPES = {
            "korean_name", "resident_number", "phone", "account", "address",
            "number_text", "date", "date_or_birth", "relation", "text",
        }

        for req in requests:
            ft = req.get("field_type", "text")
            if ft == "checkbox":
                checkbox_reqs.append(req)
            elif ft == "signature":
                signature_reqs.append(req)
            else:
                ocr_reqs.append(req)

        results = []

        # OCR 배치 처리
        if ocr_reqs:
            engine = self.get_engine(model_id)
            images = []
            valid_indices = []
            for j, req in enumerate(ocr_reqs):
                try:
                    img = Image.open(req["crop_path"]).convert("RGB")
                    images.append(img)
                    valid_indices.append(j)
                except Exception as e:
                    results.append(_make_error(req, f"image_open_failed: {e}", engine.source))

            if images:
                ocr_results = engine.predict_text(images)
                for k, idx in enumerate(valid_indices):
                    req = ocr_reqs[idx]
                    r = ocr_results[k]
                    if r.error:
                        results.append(_make_error(req, r.error, engine.source))
                    else:
                        results.append(_make_success(req, r, engine.source))

        # 체크박스
        for req in checkbox_reqs:
            try:
                img = Image.open(req["crop_path"]).convert("L")
                det = self.checkbox_detector.detect(img)
                results.append({
                    "request_id": req["request_id"],
                    "document_id": req["document_id"],
                    "template_id": req["template_id"],
                    "page": req["page"],
                    "field_key": req["field_key"],
                    "field_type": "checkbox",
                    "text": "",
                    "normalized_text": "",
                    "value": det.value,
                    "confidence": det.confidence,
                    "candidates": det.candidates,
                    "status": "ok" if det.value != "unknown" else "unknown",
                    "error": None,
                    "ocr_engine_version": "checkbox_cv_v1",
                })
            except Exception as e:
                results.append(_make_error(req, f"checkbox_failed: {e}", "checkbox_cv_v1"))

        # 서명
        for req in signature_reqs:
            try:
                img = Image.open(req["crop_path"]).convert("L")
                det = self.signature_detector.detect(img)
                results.append({
                    "request_id": req["request_id"],
                    "document_id": req["document_id"],
                    "template_id": req["template_id"],
                    "page": req["page"],
                    "field_key": req["field_key"],
                    "field_type": "signature",
                    "text": "",
                    "normalized_text": "",
                    "value": det.value,
                    "confidence": det.confidence,
                    "candidates": [],
                    "status": "ok",
                    "error": None,
                    "ocr_engine_version": "signature_cv_v1",
                })
            except Exception as e:
                results.append(_make_error(req, f"signature_failed: {e}", "signature_cv_v1"))

        return results

    def list_models(self) -> list[dict]:
        models = self.config.get("models", {})
        return [
            {"id": mid, "default": mid == self.default_model, **conf}
            for mid, conf in models.items()
        ]


def _make_success(req: dict, r, engine_version: str) -> dict:
    from .validator import strip_label_prefix
    raw_text = r.text.strip()
    clean_text = strip_label_prefix(raw_text)
    return {
        "request_id": req["request_id"],
        "document_id": req["document_id"],
        "template_id": req["template_id"],
        "page": req["page"],
        "field_key": req["field_key"],
        "field_type": req["field_type"],
        "text": raw_text,
        "normalized_text": clean_text,
        "value": clean_text,
        "confidence": r.confidence,
        "candidates": r.candidates,
        "status": "ok",
        "error": None,
        "ocr_engine_version": engine_version,
    }


def _make_error(req: dict, error: str, engine_version: str) -> dict:
    return {
        "request_id": req["request_id"],
        "document_id": req["document_id"],
        "template_id": req["template_id"],
        "page": req["page"],
        "field_key": req["field_key"],
        "field_type": req["field_type"],
        "text": "",
        "normalized_text": "",
        "value": None,
        "confidence": 0.0,
        "candidates": [],
        "status": "ocr_failed",
        "error": error,
        "ocr_engine_version": engine_version,
    }
