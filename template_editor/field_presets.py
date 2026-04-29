"""계약서 3.1~3.7절 기반 필드 프리셋 정의"""

FIELD_TYPES = [
    "korean_name", "resident_number", "phone", "account", "address",
    "number_text", "date", "date_or_birth", "relation", "text",
    "checkbox", "signature",
]

GROUPS = ["header", "applicant", "manager", "other_farmer", "family", "confirm"]

GROUP_COLORS = {
    "header": "#888888",
    "applicant": "#e74c3c",
    "manager": "#2980b9",
    "other_farmer": "#8e44ad",
    "family": "#27ae60",
    "confirm": "#f39c12",
}

EXCEL_SHEET_MAP = {
    "header": "applicants",
    "applicant": "applicants",
    "manager": "applicants",
    "other_farmer": "applicants",
    "family": "family_members",
    "confirm": "applicants",
}

# 3.1 일반현황 상단
FIELD_PRESETS = {
    "receipt_no": {"label": "접수번호", "field_type": "text", "group": "header", "required": False},
    "receipt_date": {"label": "접수일자", "field_type": "date", "group": "header", "required": False},
    "farm_business_no": {"label": "농업경영체_등록번호", "field_type": "number_text", "group": "header", "required": False},
    "farmer_no_top": {"label": "농업인_번호", "field_type": "number_text", "group": "header", "required": False},
    "business_info_change_date": {"label": "경영정보변경일", "field_type": "date", "group": "header", "required": False},
    # 3.2 등록신청인
    "applicant_name": {"label": "등록신청인_성명", "field_type": "korean_name", "group": "applicant", "required": True},
    "applicant_rrn": {"label": "등록신청인_주민등록번호", "field_type": "resident_number", "group": "applicant", "required": True},
    "applicant_account": {"label": "등록신청인_계좌번호_은행명", "field_type": "account", "group": "applicant", "required": False},
    "applicant_address": {"label": "등록신청인_주소", "field_type": "address", "group": "applicant", "required": True},
    "applicant_phone": {"label": "등록신청인_전화번호", "field_type": "phone", "group": "applicant", "required": False},
    # 3.3 경영주인 농업인
    "manager_name": {"label": "경영주_성명", "field_type": "korean_name", "group": "manager", "required": False},
    "manager_farmer_no": {"label": "경영주_농업인번호", "field_type": "number_text", "group": "manager", "required": False},
    "manager_application_type": {"label": "경영주_신청유형", "field_type": "text", "group": "manager", "required": False},
    "manager_address": {"label": "경영주_주민등록표상주소지", "field_type": "address", "group": "manager", "required": False},
    "manager_village": {"label": "경영주_마을명", "field_type": "text", "group": "manager", "required": False},
    "manager_phone": {"label": "경영주_전화번호", "field_type": "phone", "group": "manager", "required": False},
    "livestock_farm_checked": {"label": "축산농가_체크", "field_type": "checkbox", "group": "manager", "required": False},
    "facility_farm_checked": {"label": "시설농가_체크", "field_type": "checkbox", "group": "manager", "required": False},
    # 3.4 경영주 외의 농업인
    "other_farmer_name": {"label": "경영주외_성명", "field_type": "korean_name", "group": "other_farmer", "required": False},
    "other_farmer_birth": {"label": "경영주외_생년월일", "field_type": "date_or_birth", "group": "other_farmer", "required": False},
    "other_farmer_no": {"label": "경영주외_농업인번호", "field_type": "number_text", "group": "other_farmer", "required": False},
    "other_farmer_relation": {"label": "경영주와의_관계", "field_type": "relation", "group": "other_farmer", "required": False},
    # 3.7 확인 체크
    "family_info_confirm_checked": {"label": "가족관계_인적정보_확인_체크", "field_type": "checkbox", "group": "confirm", "required": False},
}

# 3.5 가족관계 인적정보 작성표 ④-1 (1~4행, 좌/우)
for row in range(1, 5):
    for side, side_label in [("left", "좌"), ("right", "우")]:
        for suffix, label_suffix, ftype in [
            ("relation", "관계", "relation"),
            ("name", "성명", "korean_name"),
            ("rrn", "주민등록번호", "resident_number"),
        ]:
            key = f"family_{row}_{side}_{suffix}"
            FIELD_PRESETS[key] = {
                "label": f"가족관계_④-1_{row}행_{side_label}_{label_suffix}",
                "field_type": ftype,
                "group": "family",
                "required": False,
            }

# 3.6 가족관계 인적정보 작성표 ④-2 (선택)
for row in range(1, 3):
    for suffix, label_suffix, ftype in [
        ("relation", "관계", "relation"),
        ("name", "성명", "korean_name"),
        ("rrn", "주민등록번호", "resident_number"),
    ]:
        key = f"family_separated_{row}_{suffix}"
        FIELD_PRESETS[key] = {
            "label": f"가족관계_④-2_{row}행_{label_suffix}",
            "field_type": ftype,
            "group": "family",
            "required": False,
        }

PRESET_KEYS = list(FIELD_PRESETS.keys())
