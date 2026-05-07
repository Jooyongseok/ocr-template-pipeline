"""실시간 데이터 저장소 -- 원자적 저장, 수정 이력, 문서 상태 관리.

검수 중 수정된 값은 즉시 저장되며, 수정 이력이 추적된다.
동시 접근 시 데이터 손실을 방지하기 위해 write-then-rename 패턴을 사용한다.
"""
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone

from . import field_dependency


# 보안: document_id 화이트리스트 패턴
SAFE_DOC_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_doc_id(doc_id: str) -> str:
    """경로 순회 공격을 방지한다."""
    if not SAFE_DOC_ID.match(doc_id):
        raise ValueError(f"잘못된 document_id: {doc_id!r}")
    return doc_id


def _mask_rrn(text: str) -> str:
    """주민등록번호 뒷자리 마스킹."""
    if not text:
        return text
    return re.sub(r"(\d{6})-?(\d)(\d{6})", r"\1-\2******", text)


def _mask_account(text: str) -> str:
    """계좌번호 부분 마스킹."""
    if not text:
        return text
    parts = re.findall(r"\d+", text)
    if len(parts) >= 2:
        last = parts[-1]
        masked = last[:len(last)//2] + "*" * (len(last) - len(last)//2)
        text = text.replace(last, masked, 1)
    return text


PII_MASKERS = {
    "resident_number": _mask_rrn,
    "account": _mask_account,
}


class DataStore:
    """JSON 기반 실시간 데이터 저장소.

    각 문서는 {store_dir}/{doc_id}.json 파일로 저장된다.
    수정 이력은 {store_dir}/{doc_id}_history.jsonl에 기록된다.
    """

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.store_dir = os.path.join(work_dir, "data_store")
        os.makedirs(self.store_dir, exist_ok=True)

    def _doc_path(self, doc_id: str) -> str:
        _validate_doc_id(doc_id)
        return os.path.join(self.store_dir, f"{doc_id}.json")

    def _history_path(self, doc_id: str) -> str:
        _validate_doc_id(doc_id)
        return os.path.join(self.store_dir, f"{doc_id}_history.jsonl")

    def _atomic_write(self, path: str, data: dict) -> None:
        """원자적 파일 쓰기 -- 중간에 죽어도 데이터 손상 없음."""
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)  # 원자적 교체
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def save_document(self, doc_data: dict) -> None:
        """문서 전체를 저장한다 (OCR 결과 병합 후 최초 저장용)."""
        doc_id = doc_data["document_id"]
        # PII 마스킹 적용 (저장본)
        masked = self._apply_pii_masking(doc_data)
        self._atomic_write(self._doc_path(doc_id), masked)

    def _apply_pii_masking(self, doc_data: dict) -> dict:
        """PII 필드를 마스킹한 복사본을 반환한다 (원본은 변경하지 않음)."""
        import copy
        masked = copy.deepcopy(doc_data)
        for fk, field in masked.get("fields", {}).items():
            ft = field.get("field_type", "")
            if ft in PII_MASKERS and "value" in field:
                field["value"] = PII_MASKERS[ft](field.get("value", ""))
                # raw_text는 보존하되 별도 마스킹 (검수 시 필요할 수 있음)
        return masked

    def get_document(self, doc_id: str) -> dict | None:
        """문서 데이터를 읽는다."""
        path = self._doc_path(doc_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_documents(self) -> list[str]:
        """저장된 모든 문서 ID를 반환한다."""
        docs = []
        for fname in os.listdir(self.store_dir):
            if fname.endswith(".json") and not fname.endswith("_history.jsonl"):
                docs.append(fname.replace(".json", ""))
        return sorted(docs)

    def save_field(self, doc_id: str, field_key: str, new_value: str,
                   edit_source: str = "manual_review") -> dict:
        """필드 값을 수정하고 즉시 저장한다. 수정 이력도 기록한다.

        Returns:
            업데이트된 문서 데이터
        """
        doc = self.get_document(doc_id)
        if doc is None:
            raise ValueError(f"문서를 찾을 수 없습니다: {doc_id}")

        fields = doc.get("fields", {})
        if field_key not in fields:
            raise ValueError(f"필드를 찾을 수 없습니다: {field_key}")

        field = fields[field_key]
        original_value = field.get("value", "")
        original_confidence = field.get("confidence", 0.0)

        # 수정 이력 기록
        history_entry = {
            "field_key": field_key,
            "original_value": original_value,
            "original_confidence": original_confidence,
            "edited_value": new_value,
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "edit_source": edit_source,
        }
        self._append_history(doc_id, history_entry)

        # 필드 값 업데이트
        field["value"] = new_value
        field["raw_text"] = field.get("raw_text", original_value)  # 원본 보존
        field["confidence"] = 1.0  # 사람이 수정했으므로 신뢰도 = 1.0
        field["status"] = "ok"
        field["warning"] = None
        field["edited"] = True

        # PII 마스킹 적용
        ft = field.get("field_type", "")
        if ft in PII_MASKERS:
            field["value"] = PII_MASKERS[ft](new_value)

        # 문서 상태 재계산
        doc["review_count"] = sum(
            1 for f in fields.values()
            if f.get("status") not in ("ok", "unchecked")
        )
        doc["document_status"] = "ok" if doc["review_count"] == 0 else "needs_review"

        # 연관성 검증
        dep_warnings = field_dependency.check_dependencies(fields)
        doc["dependency_warnings"] = [
            {"group": w.group_name, "field": w.field_key, "message": w.message}
            for w in dep_warnings
        ]

        self._atomic_write(self._doc_path(doc_id), doc)
        return doc

    def _append_history(self, doc_id: str, entry: dict) -> None:
        """수정 이력을 JSONL 파일에 추가한다."""
        path = self._history_path(doc_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_edit_history(self, doc_id: str, field_key: str | None = None) -> list[dict]:
        """수정 이력을 조회한다."""
        path = self._history_path(doc_id)
        if not os.path.exists(path):
            return []
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if field_key is None or entry.get("field_key") == field_key:
                    entries.append(entry)
        return entries

    def get_document_status(self, doc_id: str) -> str:
        """문서 완료 상태를 반환한다."""
        doc = self.get_document(doc_id)
        if doc is None:
            return "not_found"
        return doc.get("document_status", "unknown")

    def get_review_items(self, doc_id: str | None = None) -> list[dict]:
        """검수가 필요한 필드 목록을 반환한다.

        doc_id가 None이면 모든 문서에서 검수 대상을 가져온다.
        """
        items = []
        doc_ids = [doc_id] if doc_id else self.list_documents()

        for did in doc_ids:
            doc = self.get_document(did)
            if doc is None:
                continue
            for fk, field in doc.get("fields", {}).items():
                status = field.get("status", "ok")
                if status not in ("ok", "unchecked"):
                    items.append({
                        "document_id": did,
                        "source_pdf": doc.get("source_pdf", ""),
                        "field_key": fk,
                        "field_label": field.get("label", fk),
                        "field_type": field.get("field_type", "text"),
                        "value": field.get("value", ""),
                        "raw_text": field.get("raw_text", ""),
                        "confidence": field.get("confidence", 0.0),
                        "status": status,
                        "warning": field.get("warning"),
                        "crop_path": field.get("crop_path", ""),
                        "group": field_dependency.get_field_group(fk),
                        "group_fields": field_dependency.get_group_fields(fk),
                    })

        # 신뢰도 오름차순 정렬 (worst-first)
        items.sort(key=lambda x: x["confidence"])
        return items

    def get_batch_stats(self) -> dict:
        """전체 배치 통계를 반환한다."""
        doc_ids = self.list_documents()
        total_docs = len(doc_ids)
        completed_docs = 0
        total_fields = 0
        review_fields = 0
        ok_fields = 0

        for did in doc_ids:
            doc = self.get_document(did)
            if doc is None:
                continue
            if doc.get("document_status") == "ok":
                completed_docs += 1
            for field in doc.get("fields", {}).values():
                total_fields += 1
                status = field.get("status", "ok")
                if status == "ok":
                    ok_fields += 1
                elif status not in ("unchecked",):
                    review_fields += 1

        return {
            "total_docs": total_docs,
            "completed_docs": completed_docs,
            "total_fields": total_fields,
            "ok_fields": ok_fields,
            "review_fields": review_fields,
            "completion_pct": round(completed_docs / total_docs * 100, 1) if total_docs > 0 else 0,
        }

    def get_correction_data(self) -> list[dict]:
        """Active Learning용 -- 사람이 수정한 (crop_path, corrected_text) 쌍을 반환한다."""
        corrections = []
        for did in self.list_documents():
            history = self.get_edit_history(did)
            doc = self.get_document(did)
            if doc is None:
                continue
            for entry in history:
                fk = entry["field_key"]
                field = doc.get("fields", {}).get(fk, {})
                crop_path = field.get("crop_path", "")
                if crop_path and entry.get("edited_value"):
                    corrections.append({
                        "document_id": did,
                        "field_key": fk,
                        "field_type": field.get("field_type", "text"),
                        "crop_path": crop_path,
                        "original_text": entry.get("original_value", ""),
                        "corrected_text": entry["edited_value"],
                        "original_confidence": entry.get("original_confidence", 0.0),
                        "edited_at": entry.get("edited_at", ""),
                    })
        return corrections
