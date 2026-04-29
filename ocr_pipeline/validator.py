"""필드타입별 검증 규칙 (계약서 8절)"""
import re


# 신뢰도 임계점
CONF_OK = 0.80
CONF_REVIEW = 0.50

# 항상 검수 대상
ALWAYS_REVIEW_TYPES = {"resident_number", "account"}

# 관계 사전
RELATION_WORDS = {"본인", "배우자", "부", "모", "자", "녀", "자녀", "형", "제", "누나", "언니", "동생", "조부", "조모", "기타"}


def validate_result(result: dict, required: bool = False) -> dict:
    """OCR 결과에 검증 규칙을 적용하여 status, warning을 업데이트한다."""
    ft = result.get("field_type", "text")
    conf = result.get("confidence", 0.0)
    value = result.get("value")
    text = result.get("normalized_text", "")
    status = result.get("status", "ok")
    warning = None

    # 이미 실패한 결과
    if status == "ocr_failed":
        if required:
            return {**result, "status": "needs_review", "warning": "ocr_failed_required"}
        return {**result, "status": "needs_review", "warning": "ocr_failed"}

    # 필수인데 빈 값
    if required and (not text or text.strip() == ""):
        return {**result, "status": "missing", "warning": "required_empty"}

    # 신뢰도 기반
    if conf < CONF_REVIEW:
        status = "low_confidence"
    elif conf < CONF_OK:
        status = "needs_review"
    else:
        status = "ok"

    # 항상 검수 대상
    if ft in ALWAYS_REVIEW_TYPES and status == "ok":
        status = "needs_review"
        warning = "sensitive_personal_id"

    # 필드타입별 검증
    validator = VALIDATORS.get(ft)
    if validator and text:
        type_status, type_warning = validator(text)
        if type_status:
            status = type_status
            warning = type_warning

    # 후보 다수 + 점수 차이 작음
    candidates = result.get("candidates", [])
    if len(candidates) >= 2:
        scores = sorted([c.get("confidence", 0) for c in candidates], reverse=True)
        if scores[0] - scores[1] < 0.15:
            status = "multiple_candidates"
            warning = warning or "ambiguous_candidates"

    return {**result, "status": status, "warning": warning}


def _validate_korean_name(text: str):
    clean = text.strip()
    if not clean:
        return None, None
    if re.search(r"[0-9]", clean):
        return "invalid_format", "name_contains_number"
    if not (2 <= len(clean) <= 5):
        return "needs_review", "name_length_unusual"
    return None, None


def _validate_resident_number(text: str):
    clean = re.sub(r"[\s\-]", "", text.strip())
    if not clean:
        return None, None
    if len(clean) == 13 and clean.isdigit():
        return None, None
    if re.match(r"^\d{6}-?\d{7}$", text.strip()):
        return None, None
    return "invalid_format", "rrn_format_error"


def _validate_phone(text: str):
    clean = re.sub(r"[\s\-()]", "", text.strip())
    if not clean:
        return None, None
    if re.match(r"^(010|02|0\d{2})\d{7,8}$", clean):
        return None, None
    if re.match(r"^[\d\-() ]+$", text.strip()):
        return "needs_review", "phone_format_unusual"
    return "invalid_format", "phone_format_error"


def _validate_address(text: str):
    if len(text.strip()) < 5:
        return "needs_review", "address_too_short"
    return None, None


def _validate_date(text: str):
    clean = re.sub(r"[\s.\-/]", "", text.strip())
    if not clean:
        return None, None
    if re.match(r"^\d{8}$", clean) or re.match(r"^\d{4}[\-./]\d{1,2}[\-./]\d{1,2}$", text.strip()):
        return None, None
    return "needs_review", "date_format_unusual"


def _validate_date_or_birth(text: str):
    clean = re.sub(r"[\s.\-/]", "", text.strip())
    if not clean:
        return None, None
    if len(clean) in (6, 8) and clean.isdigit():
        return None, None
    return "needs_review", "birth_format_unusual"


def _validate_relation(text: str):
    clean = text.strip()
    if not clean:
        return None, None
    if clean in RELATION_WORDS:
        return None, None
    return "needs_review", "unknown_relation"


def _validate_checkbox(text: str):
    return None, None  # checkbox는 value로 판정, text 검증 불필요


VALIDATORS = {
    "korean_name": _validate_korean_name,
    "resident_number": _validate_resident_number,
    "phone": _validate_phone,
    "address": _validate_address,
    "date": _validate_date,
    "date_or_birth": _validate_date_or_birth,
    "relation": _validate_relation,
    "checkbox": _validate_checkbox,
}


def mask_rrn(text: str) -> str:
    """주민등록번호 마스킹: 800101-1234567 → 800101-1******"""
    clean = text.strip()
    m = re.match(r"^(\d{6})-?(\d)(\d{6})$", clean)
    if m:
        return f"{m.group(1)}-{m.group(2)}******"
    return clean


def mask_account(text: str) -> str:
    """계좌번호 부분 마스킹"""
    parts = re.findall(r"\d+", text)
    if not parts:
        return text
    # 마지막 숫자 그룹 마스킹
    result = text
    last = parts[-1]
    masked = last[:2] + "*" * (len(last) - 2) if len(last) > 2 else last
    result = result[:result.rfind(last)] + masked + result[result.rfind(last) + len(last):]
    return result
