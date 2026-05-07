"""Active Learning 수집기 -- 사용자 수정 데이터를 재학습용으로 관리.

검수 과정에서 사용자가 수정한 (crop_image, corrected_text) 쌍을 수집하여
모델 재학습에 활용할 수 있는 형태로 저장한다.
"""
import csv
import json
import os
import shutil
from datetime import datetime, timezone


class ActiveLearningCollector:
    """수정 데이터 수집기.

    수정된 crop 이미지와 정답 텍스트를 별도 디렉토리에 모아
    fine-tuning 데이터셋으로 바로 사용할 수 있게 관리한다.

    디렉토리 구조:
        learning_data/
        ├── images/           # crop 이미지 복사본
        ├── corrections.csv   # image_path, text 쌍
        ├── stats.json        # 수집 통계
        └── export/           # 재학습용 내보내기
    """

    def __init__(self, work_dir: str, trigger_count: int = 500):
        self.work_dir = work_dir
        self.base_dir = os.path.join(work_dir, "learning_data")
        self.images_dir = os.path.join(self.base_dir, "images")
        self.trigger_count = trigger_count

        os.makedirs(self.images_dir, exist_ok=True)

    @property
    def csv_path(self) -> str:
        return os.path.join(self.base_dir, "corrections.csv")

    @property
    def stats_path(self) -> str:
        return os.path.join(self.base_dir, "stats.json")

    def collect_correction(self, crop_path: str, corrected_text: str,
                           field_type: str, original_text: str = "",
                           original_confidence: float = 0.0,
                           document_id: str = "", field_key: str = "") -> dict:
        """수정 데이터를 수집한다.

        Args:
            crop_path: 원본 crop 이미지 경로
            corrected_text: 사용자가 수정한 정답 텍스트
            field_type: 필드 타입
            original_text: OCR이 인식한 원본 텍스트
            original_confidence: 원본 신뢰도

        Returns:
            수집 결과 (새 이미지 경로, 전체 수집 건수 등)
        """
        if not os.path.exists(crop_path):
            return {"error": f"crop 이미지 없음: {crop_path}", "collected": False}

        if not corrected_text.strip():
            return {"error": "빈 텍스트는 수집하지 않음", "collected": False}

        # crop 이미지를 learning_data/images/에 복사
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        ext = os.path.splitext(crop_path)[1] or ".png"
        dest_name = f"{document_id}__{field_key}__{timestamp}{ext}"
        dest_path = os.path.join(self.images_dir, dest_name)
        shutil.copy2(crop_path, dest_path)

        # CSV에 기록
        is_new = not os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow([
                    "image_path", "text", "field_type",
                    "original_text", "original_confidence",
                    "document_id", "field_key", "collected_at",
                ])
            writer.writerow([
                dest_path, corrected_text, field_type,
                original_text, original_confidence,
                document_id, field_key,
                datetime.now(timezone.utc).isoformat(),
            ])

        # 통계 업데이트
        stats = self.get_stats()
        stats["total_corrections"] = stats.get("total_corrections", 0) + 1
        stats["last_collected"] = datetime.now(timezone.utc).isoformat()
        by_type = stats.get("by_field_type", {})
        by_type[field_type] = by_type.get(field_type, 0) + 1
        stats["by_field_type"] = by_type
        self._save_stats(stats)

        total = stats["total_corrections"]
        should_trigger = total >= self.trigger_count and total % self.trigger_count == 0

        return {
            "collected": True,
            "image_path": dest_path,
            "total_corrections": total,
            "trigger_retrain": should_trigger,
            "trigger_message": f"수집 데이터 {total}건 도달! 재학습을 권장합니다." if should_trigger else None,
        }

    def get_stats(self) -> dict:
        """수집 통계를 반환한다."""
        if not os.path.exists(self.stats_path):
            return {"total_corrections": 0, "by_field_type": {}}
        with open(self.stats_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_stats(self, stats: dict) -> None:
        with open(self.stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    def export_for_training(self, output_dir: str | None = None) -> str:
        """재학습용 데이터셋을 내보낸다.

        TrOCR fine-tuning에 바로 사용할 수 있는 CSV 형식:
            image_path, text

        Returns:
            내보낸 CSV 파일 경로
        """
        export_dir = output_dir or os.path.join(self.base_dir, "export")
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_path = os.path.join(export_dir, f"training_data_{timestamp}.csv")

        if not os.path.exists(self.csv_path):
            return ""

        # corrections.csv에서 (image_path, text) 쌍만 추출
        with open(self.csv_path, "r", encoding="utf-8") as fin, \
             open(export_path, "w", newline="", encoding="utf-8") as fout:
            reader = csv.DictReader(fin)
            writer = csv.writer(fout)
            writer.writerow(["image_path", "text"])
            count = 0
            for row in reader:
                img_path = row.get("image_path", "")
                text = row.get("text", "")
                if img_path and text and os.path.exists(img_path):
                    writer.writerow([img_path, text])
                    count += 1

        print(f"  재학습 데이터 내보내기 완료: {count}건 → {export_path}")
        return export_path

    def get_confidence_distribution(self) -> dict:
        """수정된 데이터의 원본 신뢰도 분포를 반환한다.

        어떤 신뢰도 구간에서 수정이 많이 발생하는지 분석용.
        """
        if not os.path.exists(self.csv_path):
            return {}

        bins = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                conf = float(row.get("original_confidence", 0))
                if conf < 0.2:
                    bins["0.0-0.2"] += 1
                elif conf < 0.4:
                    bins["0.2-0.4"] += 1
                elif conf < 0.6:
                    bins["0.4-0.6"] += 1
                elif conf < 0.8:
                    bins["0.6-0.8"] += 1
                else:
                    bins["0.8-1.0"] += 1
        return bins
