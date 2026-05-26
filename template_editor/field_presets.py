"""범용 필드 프리셋 정의 -- 사용자 정의 템플릿 지원.

사용자가 직접 바운딩 박스와 필드 타입을 정의하고,
재사용 가능한 템플릿으로 저장할 수 있다.
"""
import json
import os
from pathlib import Path

# ── 기본 필드 타입 (모든 문서에서 사용 가능) ──
FIELD_TYPES = [
    "text",            # 일반 텍스트
    "korean_name",     # 한국어 이름
    "number_text",     # 숫자+텍스트 혼합
    "date",            # 날짜 (YYYYMMDD)
    "date_or_birth",   # 생년월일 (6자리 또는 8자리)
    "phone",           # 전화번호
    "resident_number", # 주민등록번호
    "account",         # 계좌번호
    "address",         # 주소
    "relation",        # 가족 관계
    "checkbox",        # 체크박스
    "signature",       # 서명
]

# ── 기본 그룹 (사용자가 추가/수정 가능) ──
DEFAULT_GROUPS = ["일반", "신청인", "담당자", "기타"]

DEFAULT_GROUP_COLORS = {
    "일반": "#888888",
    "신청인": "#e74c3c",
    "담당자": "#2980b9",
    "기타": "#27ae60",
}

# ── 샘플 프리셋 (참고용, 사용자가 직접 만드는 것이 기본) ──
SAMPLE_PRESETS = {
    "name": {"label": "이름", "field_type": "korean_name", "group": "신청인", "required": True},
    "rrn": {"label": "주민등록번호", "field_type": "resident_number", "group": "신청인", "required": True},
    "phone": {"label": "전화번호", "field_type": "phone", "group": "신청인", "required": False},
    "address": {"label": "주소", "field_type": "address", "group": "신청인", "required": False},
    "date": {"label": "날짜", "field_type": "date", "group": "일반", "required": False},
    "checkbox": {"label": "체크박스", "field_type": "checkbox", "group": "일반", "required": False},
    "signature": {"label": "서명", "field_type": "signature", "group": "일반", "required": False},
    "text": {"label": "텍스트", "field_type": "text", "group": "일반", "required": False},
}


# ── 사용자 정의 프리셋 로드/저장 ──

USER_PRESETS_DIR = Path(__file__).resolve().parent.parent / "template" / "user_presets"


def load_user_presets() -> dict:
    """사용자가 저장한 커스텀 프리셋을 로드한다."""
    USER_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    presets = {}
    for f in USER_PRESETS_DIR.glob("*.json"):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
            presets[f.stem] = data
    return presets


def save_user_preset(name: str, preset: dict):
    """커스텀 프리셋을 저장한다."""
    USER_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_PRESETS_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(preset, fp, ensure_ascii=False, indent=2)
    return str(path)


def delete_user_preset(name: str) -> bool:
    """커스텀 프리셋을 삭제한다."""
    path = USER_PRESETS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def get_all_presets() -> dict:
    """기본 프리셋 + 사용자 정의 프리셋을 합쳐서 반환한다."""
    all_presets = dict(SAMPLE_PRESETS)
    user = load_user_presets()
    for name, data in user.items():
        if "fields" in data:
            for fk, fv in data["fields"].items():
                all_presets[fk] = fv
    return all_presets


def get_groups_and_colors(user_groups: list[str] | None = None) -> tuple[list[str], dict]:
    """사용 가능한 그룹 목록과 색상을 반환한다."""
    groups = list(DEFAULT_GROUPS)
    colors = dict(DEFAULT_GROUP_COLORS)
    if user_groups:
        for g in user_groups:
            if g not in groups:
                groups.append(g)
                # auto-assign color
                palette = ["#e67e22", "#9b59b6", "#1abc9c", "#34495e", "#f39c12", "#d35400"]
                colors[g] = palette[len(groups) % len(palette)]
    return groups, colors


# ── 하위 호환성 ──
FIELD_PRESETS = SAMPLE_PRESETS
GROUPS = DEFAULT_GROUPS
GROUP_COLORS = DEFAULT_GROUP_COLORS
EXCEL_SHEET_MAP = {}  # 사용자가 정의
PRESET_KEYS = list(SAMPLE_PRESETS.keys())
