"""추상 OCR 엔진 인터페이스 -- 모델 교체를 위한 공통 계약"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from PIL import Image


@dataclass
class OCRResult:
    text: str
    confidence: float
    candidates: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.text != ""


@dataclass
class CheckboxResult:
    value: bool | str  # True / False / "unknown"
    confidence: float
    candidates: list[dict] = field(default_factory=list)


@dataclass
class SignatureResult:
    value: str  # "present" / "absent"
    confidence: float


class BaseOCREngine(ABC):
    """모든 OCR 엔진이 구현해야 하는 인터페이스.

    모델을 교체하려면 이 클래스를 상속하고
    model_config.yaml에 등록하면 된다.
    """

    @abstractmethod
    def load_model(self) -> None:
        """모델을 메모리에 로드한다 (lazy loading 지원)."""
        ...

    @abstractmethod
    def predict_text(self, images: list[Image.Image]) -> list[OCRResult]:
        """이미지 배치에서 텍스트를 추출한다."""
        ...

    @abstractmethod
    def get_model_info(self) -> dict:
        """모델 이름, 버전, 파라미터 수 등 메타데이터를 반환한다."""
        ...

    def unload_model(self) -> None:
        """GPU 메모리를 해제한다. 기본 구현은 아무것도 하지 않는다."""
        pass


class CheckboxDetector:
    """이미지 기반 체크박스 판정 -- OCR 모델과 독립적."""

    def __init__(self, dark_threshold: int = 128,
                 checked_ratio: float = 0.10,
                 unchecked_ratio: float = 0.05):
        self.dark_threshold = dark_threshold
        self.checked_ratio = checked_ratio
        self.unchecked_ratio = unchecked_ratio

    def detect(self, image: Image.Image) -> CheckboxResult:
        import numpy as np
        arr = np.array(image.convert("L"))
        dark_pixels = int(np.sum(arr < self.dark_threshold))
        total = arr.size
        dark_ratio = dark_pixels / total if total > 0 else 0

        if dark_ratio > self.checked_ratio:
            value = True
            conf = min(1.0, 0.5 + dark_ratio * 2)
        elif dark_ratio < self.unchecked_ratio:
            value = False
            conf = min(1.0, 1.0 - dark_ratio * 10)
        else:
            value = "unknown"
            conf = 0.3

        return CheckboxResult(
            value=value,
            confidence=round(conf, 4),
            candidates=[
                {"value": True, "confidence": round(dark_ratio, 4)},
                {"value": False, "confidence": round(1.0 - dark_ratio, 4)},
            ],
        )


class SignatureDetector:
    """이미지 기반 서명/날인 존재 여부 판정 -- OCR 모델과 독립적."""

    def __init__(self, dark_threshold: int = 128,
                 present_ratio: float = 0.03):
        self.dark_threshold = dark_threshold
        self.present_ratio = present_ratio

    def detect(self, image: Image.Image) -> SignatureResult:
        import numpy as np
        arr = np.array(image.convert("L"))
        dark_ratio = float(np.sum(arr < self.dark_threshold)) / arr.size if arr.size > 0 else 0

        if dark_ratio > self.present_ratio:
            value = "present"
            conf = min(1.0, 0.5 + dark_ratio * 5)
        else:
            value = "absent"
            conf = min(1.0, 1.0 - dark_ratio * 20)

        return SignatureResult(value=value, confidence=round(conf, 4))
