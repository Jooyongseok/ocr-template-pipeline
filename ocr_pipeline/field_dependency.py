"""필드 연관성 시스템 -- 필드 간 의존관계 정의 및 일관성 검증.

연관 타입:
  - linked_set: 그룹 내 하나라도 값이 있으면 나머지도 있어야 함 (가족관계)
  - mixed: 일부 필수 + 일부 선택 (등록신청인)
  - all_optional: 전부 비어있어도 OK (경영주 정보)
  - conditional: 특정 필드에 값이 있으면 다른 필드도 필요 (경영주 외 농업인)
"""
from dataclasses import dataclass


@dataclass
class DependencyWarning:
    group_name: str
    warning_type: str  # "incomplete_set" | "missing_required" | "missing_conditional"
    field_key: str
    message: str
    related_fields: list[str]


# 1페이지 필드 연관성 규칙
FIELD_DEPENDENCIES = {
    "family_1_left": {
        "type": "linked_set",
        "fields": ["family_1_left_relation", "family_1_left_name", "family_1_left_rrn"],
        "label": "가족관계 ④-1 1행 좌",
    },
    "family_1_right": {
        "type": "linked_set",
        "fields": ["family_1_right_relation", "family_1_right_name", "family_1_right_rrn"],
        "label": "가족관계 ④-1 1행 우",
    },
    "family_2_left": {
        "type": "linked_set",
        "fields": ["family_2_left_relation", "family_2_left_name", "family_2_left_rrn"],
        "label": "가족관계 ④-1 2행 좌",
    },
    "family_2_right": {
        "type": "linked_set",
        "fields": ["family_2_right_relation", "family_2_right_name", "family_2_right_rrn"],
        "label": "가족관계 ④-1 2행 우",
    },
    "family_3_left": {
        "type": "linked_set",
        "fields": ["family_3_left_relation", "family_3_left_name", "family_3_left_rrn"],
        "label": "가족관계 ④-1 3행 좌",
    },
    "family_3_right": {
        "type": "linked_set",
        "fields": ["family_3_right_relation", "family_3_right_name", "family_3_right_rrn"],
        "label": "가족관계 ④-1 3행 우",
    },
    "family_4_left": {
        "type": "linked_set",
        "fields": ["family_4_left_relation", "family_4_left_name", "family_4_left_rrn"],
        "label": "가족관계 ④-1 4행 좌",
    },
    "family_4_right": {
        "type": "linked_set",
        "fields": ["family_4_right_relation", "family_4_right_name", "family_4_right_rrn"],
        "label": "가족관계 ④-1 4행 우",
    },
    "applicant": {
        "type": "mixed",
        "required": ["applicant_name", "applicant_rrn", "applicant_address"],
        "optional": ["applicant_account", "applicant_phone"],
        "label": "등록신청인",
    },
    "manager": {
        "type": "all_optional",
        "fields": [
            "manager_name", "manager_farmer_no", "manager_address",
            "manager_village", "manager_phone", "manager_application_type",
            "livestock_farm_checked", "facility_farm_checked",
        ],
        "label": "경영주인 농업인",
    },
    "other_farmer": {
        "type": "conditional",
        "trigger": "other_farmer_name",
        "then_required": ["other_farmer_birth"],
        "always_optional": ["other_farmer_no", "other_farmer_relation"],
        "label": "경영주 외의 농업인",
    },
}


def _has_value(fields_data: dict, field_key: str) -> bool:
    """필드에 유효한 값이 있는지 확인한다."""
    if field_key not in fields_data:
        return False
    field = fields_data[field_key]
    val = field.get("value") if isinstance(field, dict) else field
    if val is None or val == "" or val == "unknown":
        return False
    return True


def check_dependencies(fields_data: dict) -> list[DependencyWarning]:
    """필드 데이터의 연관성을 검증하고 경고 목록을 반환한다.

    Args:
        fields_data: {field_key: {"value": ..., "status": ...}} 형태의 딕셔너리

    Returns:
        DependencyWarning 목록 (문제 없으면 빈 리스트)
    """
    warnings = []

    for group_name, dep in FIELD_DEPENDENCIES.items():
        dep_type = dep["type"]

        if dep_type == "linked_set":
            fields = dep["fields"]
            filled = [fk for fk in fields if _has_value(fields_data, fk)]
            empty = [fk for fk in fields if not _has_value(fields_data, fk)]

            # 하나라도 있으면 나머지도 있어야 함 (전부 비어있으면 OK)
            if filled and empty:
                for fk in empty:
                    warnings.append(DependencyWarning(
                        group_name=group_name,
                        warning_type="incomplete_set",
                        field_key=fk,
                        message=f"[{dep['label']}] {fk} 값이 비어있습니다. "
                                f"같은 그룹의 {', '.join(filled)}에 값이 있으므로 이 필드도 필요합니다.",
                        related_fields=fields,
                    ))

        elif dep_type == "mixed":
            for fk in dep["required"]:
                if not _has_value(fields_data, fk):
                    warnings.append(DependencyWarning(
                        group_name=group_name,
                        warning_type="missing_required",
                        field_key=fk,
                        message=f"[{dep['label']}] 필수 필드 {fk}이(가) 비어있습니다.",
                        related_fields=dep["required"] + dep["optional"],
                    ))

        elif dep_type == "all_optional":
            # 전부 선택이므로 경고 없음
            pass

        elif dep_type == "conditional":
            trigger = dep["trigger"]
            if _has_value(fields_data, trigger):
                for fk in dep["then_required"]:
                    if not _has_value(fields_data, fk):
                        warnings.append(DependencyWarning(
                            group_name=group_name,
                            warning_type="missing_conditional",
                            field_key=fk,
                            message=f"[{dep['label']}] {trigger}에 값이 있으므로 "
                                    f"{fk}도 필요합니다.",
                            related_fields=[trigger] + dep["then_required"] + dep.get("always_optional", []),
                        ))

    return warnings


def get_field_group(field_key: str) -> dict | None:
    """특정 필드가 속한 연관성 그룹을 반환한다."""
    for group_name, dep in FIELD_DEPENDENCIES.items():
        all_fields = []
        if dep["type"] == "linked_set":
            all_fields = dep["fields"]
        elif dep["type"] == "mixed":
            all_fields = dep["required"] + dep["optional"]
        elif dep["type"] == "all_optional":
            all_fields = dep["fields"]
        elif dep["type"] == "conditional":
            all_fields = [dep["trigger"]] + dep["then_required"] + dep.get("always_optional", [])

        if field_key in all_fields:
            return {"group_name": group_name, **dep}
    return None


def get_group_fields(field_key: str) -> list[str]:
    """특정 필드와 같은 그룹의 모든 필드 키를 반환한다."""
    group = get_field_group(field_key)
    if group is None:
        return [field_key]

    dep_type = group["type"]
    if dep_type == "linked_set":
        return group["fields"]
    elif dep_type == "mixed":
        return group["required"] + group["optional"]
    elif dep_type == "all_optional":
        return group["fields"]
    elif dep_type == "conditional":
        return [group["trigger"]] + group["then_required"] + group.get("always_optional", [])
    return [field_key]


def is_field_optional(field_key: str) -> bool:
    """필드가 비어있어도 되는지 판단한다."""
    group = get_field_group(field_key)
    if group is None:
        return True  # 그룹에 속하지 않으면 선택으로 취급

    dep_type = group["type"]
    if dep_type == "linked_set":
        return True  # 그룹 전체가 비어있으면 OK (개별 필드는 optional)
    elif dep_type == "mixed":
        return field_key in group.get("optional", [])
    elif dep_type == "all_optional":
        return True
    elif dep_type == "conditional":
        return field_key != group["trigger"] and field_key not in group.get("then_required", [])
    return True
