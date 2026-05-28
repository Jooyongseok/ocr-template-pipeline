"""필드타입별 검증 규칙 (계약서 8절)"""
import re


# 신뢰도 임계점
CONF_OK = 0.80
CONF_REVIEW = 0.50

# OCR 결과에서 제거할 인쇄 라벨 패턴 (셀에 라벨+데이터가 함께 crop된 경우)
LABEL_PREFIXES = [
    "성명", "주민등록번호", "주민번호", "계좌번호(은행명)", "계좌번호",
    "주소", "전화번호", "농업인번호", "농업인 번호", "농업경영체등록번호",
    "경영정보변경일", "접수번호", "접수일자", "생년월일", "신청유형",
    "주민등록표상", "주소지", "(마을명)", "마을명", "경영주와의 관계",
    "관계", "성 명",
]


def strip_label_prefix(text: str) -> str:
    """OCR 텍스트에서 인쇄 라벨 접두사를 제거한다.

    공백 유무와 무관하게 매칭한다: "성명이경준" → "이경준"
    """
    stripped = text.strip()
    # 공백 제거 버전으로도 매칭
    no_space = stripped.replace(" ", "")
    for label in sorted(LABEL_PREFIXES, key=len, reverse=True):
        label_ns = label.replace(" ", "")
        # 공백 포함 원본에서 매칭
        if stripped.startswith(label):
            stripped = stripped[len(label):].strip()
            return stripped
        # 공백 제거 버전에서 매칭
        if no_space.startswith(label_ns) and len(no_space) > len(label_ns):
            # 원본에서 라벨에 해당하는 문자 수 계산
            consumed = 0
            matched = 0
            for ch in stripped:
                if matched >= len(label_ns):
                    break
                if ch == ' ':
                    consumed += 1
                    continue
                if ch == label_ns[matched]:
                    matched += 1
                    consumed += 1
                else:
                    break
            if matched >= len(label_ns):
                stripped = stripped[consumed:].strip()
                return stripped
    return stripped

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
