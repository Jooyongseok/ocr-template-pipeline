"""OCR 엔진: ko-trocr 배치 추론 + checkbox/signature 판정"""
import numpy as np
import torch
from PIL import Image
from transformers import VisionEncoderDecoderModel, TrOCRProcessor


# checkbox/signature에 사용
try:
    import cv2
except ImportError:
    cv2 = None

OCR_FIELD_TYPES = {
    "korean_name", "resident_number", "phone", "account", "address",
    "number_text", "date", "date_or_birth", "relation", "text",
}
CHECKBOX_TYPES = {"checkbox"}
SIGNATURE_TYPES = {"signature"}


class OCREngine:
    def __init__(self, model_name: str = "ddobokki/ko-trocr", device: str = "cuda:0", batch_size: int = 32):
        self.device = device
        self.batch_size = batch_size
        self.model_name = model_name
        self.model = None
        self.processor = None

    def load_model(self):
        """모델 로드 (lazy loading)"""
        if self.model is not None:
            return
        print(f"  모델 로드 중: {self.model_name} → {self.device}")
        self.processor = TrOCRProcessor.from_pretrained(self.model_name)
        self.model = VisionEncoderDecoderModel.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()
        print("  모델 로드 완료")

    def process_batch(self, requests: list[dict]) -> list[dict]:
        """
        OCR 요청 리스트를 받아 결과 리스트를 반환한다.
        각 결과는 계약서 6절 스키마를 따른다.
        """
        results = []
        # 타입별 분류
        ocr_reqs = []
        checkbox_reqs = []
        signature_reqs = []
        other_reqs = []

        for req in requests:
            ft = req.get("field_type", "text")
            if ft in OCR_FIELD_TYPES:
                ocr_reqs.append(req)
            elif ft in CHECKBOX_TYPES:
                checkbox_reqs.append(req)
            elif ft in SIGNATURE_TYPES:
                signature_reqs.append(req)
            else:
                ocr_reqs.append(req)

        # OCR 배치 처리
        if ocr_reqs:
            self.load_model()
            results.extend(self._process_ocr_batch(ocr_reqs))

        # 체크박스 처리
        for req in checkbox_reqs:
            results.append(self._process_checkbox(req))

        # 서명 처리
        for req in signature_reqs:
            results.append(self._process_signature(req))

        return results

    def _process_ocr_batch(self, requests: list[dict]) -> list[dict]:
        """OCR 타입 필드를 GPU 배치로 처리"""
        results = []
        for i in range(0, len(requests), self.batch_size):
            batch_reqs = requests[i:i + self.batch_size]
            images = []
            valid_indices = []

            for j, req in enumerate(batch_reqs):
                try:
                    img = Image.open(req["crop_path"]).convert("RGB")
                    images.append(img)
                    valid_indices.append(j)
                except Exception as e:
                    results.append(self._make_error_result(req, f"image_open_failed: {e}"))

            if not images:
                continue

            # 배치 추론
            try:
                texts, confidences = self._infer_batch(images)
                for k, idx in enumerate(valid_indices):
                    req = batch_reqs[idx]
                    text = texts[k]
                    conf = confidences[k]
                    results.append(self._make_result(req, text, conf))
            except Exception as e:
                for idx in valid_indices:
                    results.append(self._make_error_result(batch_reqs[idx], f"inference_error: {e}"))

        return results

    @torch.no_grad()
    def _infer_batch(self, images: list[Image.Image]) -> tuple[list[str], list[float]]:
        """이미지 배치를 모델에 넣어 텍스트와 신뢰도를 반환"""
        pixel_values = self.processor(images=images, return_tensors="pt").pixel_values.to(self.device)

        outputs = self.model.generate(
            pixel_values,
            max_new_tokens=64,
            num_beams=4,
            return_dict_in_generate=True,
            output_scores=True,
        )

        # 텍스트 디코딩
        texts = self.processor.batch_decode(outputs.sequences, skip_special_tokens=True)

        # 신뢰도 계산: beam search score를 길이로 정규화
        confidences = []
        if hasattr(outputs, "sequences_scores") and outputs.sequences_scores is not None:
            for score in outputs.sequences_scores:
                # log probability → probability, clamp to [0, 1]
                prob = min(1.0, max(0.0, float(torch.exp(score))))
                confidences.append(round(prob, 4))
        else:
            confidences = [0.5] * len(texts)

        return texts, confidences

    def _process_checkbox(self, req: dict) -> dict:
        """체크박스 판정: 이미지 내 마킹 비율로 판단"""
        try:
            img = Image.open(req["crop_path"]).convert("L")
            arr = np.array(img)

            # 이진화
            threshold = 128
            dark_pixels = np.sum(arr < threshold)
            total_pixels = arr.size
            dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0

            # 빈 칸: dark_ratio < 0.05, 체크됨: > 0.10
            if dark_ratio > 0.10:
                value = True
                conf = min(1.0, 0.5 + dark_ratio * 2)
            elif dark_ratio < 0.05:
                value = False
                conf = min(1.0, 1.0 - dark_ratio * 10)
            else:
                value = "unknown"
                conf = 0.3

            return {
                "request_id": req["request_id"],
                "document_id": req["document_id"],
                "template_id": req["template_id"],
                "page": req["page"],
                "field_key": req["field_key"],
                "field_type": "checkbox",
                "text": "",
                "normalized_text": "",
                "value": value,
                "confidence": round(conf, 4),
                "candidates": [
                    {"value": True, "confidence": round(dark_ratio, 4)},
                    {"value": False, "confidence": round(1.0 - dark_ratio, 4)},
                ],
                "status": "ok" if value != "unknown" else "unknown",
                "error": None,
                "ocr_engine_version": "checkbox_cv_v1",
            }
        except Exception as e:
            return self._make_error_result(req, f"checkbox_failed: {e}")

    def _process_signature(self, req: dict) -> dict:
        """서명/날인 존재 여부 판정"""
        try:
            img = Image.open(req["crop_path"]).convert("L")
            arr = np.array(img)
            dark_ratio = np.sum(arr < 128) / arr.size if arr.size > 0 else 0

            if dark_ratio > 0.03:
                value = "present"
                conf = min(1.0, 0.5 + dark_ratio * 5)
            else:
                value = "absent"
                conf = min(1.0, 1.0 - dark_ratio * 20)

            return {
                "request_id": req["request_id"],
                "document_id": req["document_id"],
                "template_id": req["template_id"],
                "page": req["page"],
                "field_key": req["field_key"],
                "field_type": "signature",
                "text": "",
                "normalized_text": "",
                "value": value,
                "confidence": round(conf, 4),
                "candidates": [],
                "status": "ok",
                "error": None,
                "ocr_engine_version": "signature_cv_v1",
            }
        except Exception as e:
            return self._make_error_result(req, f"signature_failed: {e}")

    def _make_result(self, req: dict, text: str, confidence: float) -> dict:
        return {
            "request_id": req["request_id"],
            "document_id": req["document_id"],
            "template_id": req["template_id"],
            "page": req["page"],
            "field_key": req["field_key"],
            "field_type": req["field_type"],
            "text": text,
            "normalized_text": text.strip(),
            "value": text.strip(),
            "confidence": confidence,
            "candidates": [{"text": text.strip(), "confidence": confidence}],
            "status": "ok",
            "error": None,
            "ocr_engine_version": self.model_name,
        }

    def _make_error_result(self, req: dict, error: str) -> dict:
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
            "ocr_engine_version": self.model_name,
        }
