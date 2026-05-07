"""TrOCR 기반 OCR 엔진 -- fine-tuned 및 HuggingFace 모델 모두 지원."""
import os
import torch
from PIL import Image
from transformers import VisionEncoderDecoderModel, TrOCRProcessor

from .base_engine import BaseOCREngine, OCRResult


class TrOCREngine(BaseOCREngine):
    """TrOCR 모델 구현.

    사용 예:
        engine = TrOCREngine(model_path="./checkpoints/best/")
        engine = TrOCREngine(model_name="ddobokki/ko-trocr")
    """

    def __init__(self, *,
                 model_name: str | None = None,
                 model_path: str | None = None,
                 device: str = "cuda:0",
                 max_new_tokens: int = 32,
                 num_beams: int = 4,
                 batch_size: int = 32):
        if not model_name and not model_path:
            raise ValueError("model_name 또는 model_path 중 하나는 필수입니다")
        self._model_name = model_name
        self._model_path = model_path
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.num_beams = num_beams
        self.batch_size = batch_size
        self.model = None
        self.processor = None

    @property
    def source(self) -> str:
        return self._model_path or self._model_name or "unknown"

    def load_model(self) -> None:
        if self.model is not None:
            return
        src = self._model_path if self._model_path and os.path.isdir(self._model_path) else self._model_name
        print(f"  모델 로드 중: {src} → {self.device}")
        self.processor = TrOCRProcessor.from_pretrained(src)
        self.model = VisionEncoderDecoderModel.from_pretrained(src)
        try:
            self.model.to(self.device)
        except (RuntimeError, torch.cuda.OutOfMemoryError):
            print("  GPU OOM -- CPU 폴백")
            self.device = "cpu"
            self.model.to("cpu")
        self.model.eval()
        print("  모델 로드 완료")

    @torch.no_grad()
    def predict_text(self, images: list[Image.Image]) -> list[OCRResult]:
        self.load_model()
        all_results: list[OCRResult] = []

        for i in range(0, len(images), self.batch_size):
            batch = images[i:i + self.batch_size]
            try:
                results = self._infer_batch(batch)
                all_results.extend(results)
            except torch.cuda.OutOfMemoryError:
                # OOM: 배치 절반으로 재시도
                torch.cuda.empty_cache()
                half = max(1, len(batch) // 2)
                for sub_start in range(0, len(batch), half):
                    sub = batch[sub_start:sub_start + half]
                    try:
                        all_results.extend(self._infer_batch(sub))
                    except Exception as e:
                        all_results.extend([
                            OCRResult(text="", confidence=0.0, error=f"oom_retry_failed: {e}")
                            for _ in sub
                        ])
            except Exception as e:
                all_results.extend([
                    OCRResult(text="", confidence=0.0, error=f"inference_error: {e}")
                    for _ in batch
                ])

        return all_results

    def _infer_batch(self, images: list[Image.Image]) -> list[OCRResult]:
        pixel_values = self.processor(
            images=images, return_tensors="pt"
        ).pixel_values.to(self.device)

        outputs = self.model.generate(
            pixel_values,
            max_new_tokens=self.max_new_tokens,
            num_beams=self.num_beams,
            return_dict_in_generate=True,
            output_scores=True,
        )

        texts = self.processor.batch_decode(outputs.sequences, skip_special_tokens=True)

        confidences = []
        if hasattr(outputs, "sequences_scores") and outputs.sequences_scores is not None:
            for score in outputs.sequences_scores:
                prob = min(1.0, max(0.0, float(torch.exp(score))))
                confidences.append(round(prob, 4))
        else:
            confidences = [0.5] * len(texts)

        results = []
        for text, conf in zip(texts, confidences):
            clean = text.strip()
            results.append(OCRResult(
                text=clean,
                confidence=conf,
                candidates=[{"text": clean, "confidence": conf}],
            ))
        return results

    def get_model_info(self) -> dict:
        info = {
            "engine": "trocr",
            "source": self.source,
            "device": self.device,
            "max_new_tokens": self.max_new_tokens,
            "num_beams": self.num_beams,
            "batch_size": self.batch_size,
        }
        if self.model is not None:
            info["params"] = sum(p.numel() for p in self.model.parameters())
        return info

    def unload_model(self) -> None:
        if self.model is not None:
            del self.model
            del self.processor
            self.model = None
            self.processor = None
            if "cuda" in self.device:
                torch.cuda.empty_cache()
