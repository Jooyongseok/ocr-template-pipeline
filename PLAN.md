<!-- /autoplan restore point: /home/jys0207/.gstack/projects/Jooyongseok-ocr-template-pipeline/master-autoplan-restore-20260506-183916.md -->
# OCR Template Pipeline v2 -- Application Improvement Plan

## Problem Statement

현재 OCR 파이프라인은 기본 기능(템플릿 편집, 배치 OCR, 엑셀 출력, 검수 UI)이 구현되어 있지만,
실사용자 관점에서 불편한 점이 많다:

1. **모델 고정**: ddobokki/ko-trocr(213M, 범용)를 사용 중이나, 직접 fine-tuned TrOCR(54M, CER 2.6%)이 완성됨
2. **검수 UX 부족**: 임계점 미달 필드를 수정하려면 어디가 문제인지 직관적으로 보이지 않고, 수정 입력 칸이 멀리 떨어져 있음
3. **엑셀 의존**: 결과 확인/수정이 외부 엑셀 파일에서만 가능, 프로그램 내 즉각 수정 불가
4. **데이터 저장 미세 처리 부족**: 비어있어도 무방한 필드와 연관성 있는 필드 구분이 없음 (예: 가족 관계-성명-주민번호는 세트, 경영주 정보는 전부 선택)
5. **모델 교체 불가**: 나중에 VLM이나 다른 모델로 바꿀 때 코드 전체를 수정해야 함

## Premises

1. Fine-tuned TrOCR 모델이 handwriting_ocr/checkpoints/best/에 학습 완료 (CER 2.648%, Exact Match 97.35%)
2. VLM 모델은 별도 학습 중이므로 이번 개발 범위에서 제외하되, 나중에 교체 가능한 구조 필요
3. 대상 문서는 "기본직접지불금 지급대상자 등록신청서" 1페이지 (53+ 필드)
4. 사용자는 OCR 전문가가 아닌 행정 담당자 -- 모든 UI를 직관적으로 설계해야 함
5. 현재 Flask 기반 review_server.py가 존재하며, 이를 확장하는 방향으로 개발
6. 필드 간 연관성(가족 관계-성명-주민번호 세트, 경영주 정보 세트 등)을 시스템이 인식해야 함

## Scope

### In Scope

#### 1. 모델 추상화 레이어 (Model Abstraction)
- OCR 엔진을 추상 인터페이스로 분리
- Fine-tuned TrOCR, ddobokki/ko-trocr, 향후 VLM 등을 설정만으로 교체 가능
- 모델별 설정 파일 (config YAML/JSON)
- 체크박스/서명 판정은 모델과 독립적으로 유지

#### 2. 통합 검수 UI (Integrated Review & Correction)
- 문서 이미지 위에 필드 위치를 오버레이로 표시
- 임계점 미달 필드는 빨간색/주황색으로 하이라이트
- 문제 필드 클릭 시 해당 위치의 crop 이미지 + 수정 입력 칸을 바로 옆에 표시
- OCR 후보 목록(candidates) 클릭 선택 가능
- 수정 즉시 저장, 엑셀 재생성 불필요
- 키보드 네비게이션: Tab으로 다음 문제 필드, Enter로 확인
- 문서 간 이동 (이전/다음 문서)
- 필터링: 상태별(전체/문제만/완료), 필드 타입별

#### 3. 필드 연관성 관리 (Field Dependency System)
- 필드 그룹 정의: 독립 필드 vs 연관 필드 세트
  - 가족 관계 세트: relation + name + rrn (3개가 한 세트, 하나라도 있으면 나머지도 있어야)
  - 경영주 정보: 전부 선택이므로 비어있어도 무방
  - 등록신청인: name, rrn, address 필수 / account, phone 선택
- 연관 필드 중 일부만 비어있으면 경고 표시
- 검수 UI에서 연관 필드를 그룹으로 묶어서 표시
- 필드 메타데이터에 dependency_group, allow_empty, linked_fields 추가

#### 4. 데이터 저장 고도화 (Enhanced Data Persistence)
- JSON 기반 실시간 저장 (검수 수정 시 즉시 반영)
- 수정 이력 추적 (original_value, edited_value, edited_at, edited_by)
- 문서별 완료 상태 관리 (전체 필드 OK 시 자동 완료 표시)
- 엑셀 내보내기는 최종 확정 후 한 번만 (실시간이 아닌 export 개념)
- 비어있어도 되는 필드 vs 필수 필드 구분 저장
- 연관 필드 세트의 일관성 검증 결과 저장

#### 5. OCR 엔진 개선 (Engine Improvements)
- Fine-tuned 모델 통합 (handwriting_ocr/checkpoints/best/)
- 신뢰도 점수 보정 (temperature scaling으로 calibration)
- 체크박스 판정 개선 (적응형 이진화 threshold)
- 배치 추론 최적화 (동일 페이지 필드 한번에 처리)

#### 6. Active Learning 피드백 루프
- 사용자가 검수 중 수정한 데이터를 fine-tuning 학습 데이터로 자동 수집
- 수정 데이터 포맷: (crop_image, corrected_text) 쌍으로 저장
- 일정량(예: 500건) 누적 시 재학습 트리거 알림
- 학습 데이터 품질 관리: 수정 횟수, 신뢰도 분포 통계
- 모델 버전 관리: 재학습 전/후 성능 비교 리포트

### Out of Scope
- VLM 모델 통합 (학습 중, 나중에 모델 추상화 레이어로 추가)
- 자동 재학습 실행 (알림만, 수동 트리거)
- 다중 페이지 확장 (1페이지 완성 후)
- 모바일/태블릿 대응
- 다국어 지원
- 사용자 인증/권한 관리

## Architecture

### 현재 구조 (AS-IS)
```
template_editor/  →  template.json
                         ↓
input/*.pdf  →  crop_generator.py  →  ocr_engine.py  →  validator.py  →  excel_writer.py
                                                                              ↓
                                                            review_server.py (별도 웹 UI)
```

### 개선 구조 (TO-BE)
```
template_editor/  →  template.json (+ field_dependency 메타데이터)
                         ↓
input/*.pdf  →  crop_generator.py  →  model_registry.py  →  validator.py
                                      (모델 추상화 레이어)       ↓
                                           ↓               field_dependency.py
                                      ocr_engine.py            ↓
                                      (or vlm_engine.py)   data_store.py
                                      (or custom_engine)   (실시간 JSON 저장 + 수정 이력)
                                                               ↓
                                                    integrated_review_app.py
                                                    (통합 웹 앱: 검수 + 수정 + 내보내기)
                                                               ↓
                                                    excel_writer.py (export only)
```

### 새로운 파일 구조
```
ocr_pipeline/
├── models/
│   ├── base_engine.py        # 추상 OCR 엔진 인터페이스
│   ├── trocr_engine.py       # TrOCR 구현 (기존 + fine-tuned)
│   ├── vlm_engine.py         # VLM 구현 (placeholder)
│   └── model_config.yaml     # 모델 설정 파일
├── model_registry.py         # 모델 등록/로딩/교체
├── field_dependency.py       # 필드 연관성 규칙
├── data_store.py             # 실시간 데이터 저장/수정 이력
├── crop_generator.py         # (기존 유지)
├── validator.py              # (확장: 연관성 검증 추가)
├── excel_writer.py           # (export 전용으로 변경)
├── review_app.py             # 통합 검수 웹 앱
├── static/
│   ├── review.js             # 검수 UI 프론트엔드
│   └── review.css            # 스타일
├── templates/
│   └── review.html           # 통합 검수 페이지
├── active_learning.py        # 수정 데이터 수집 + 학습 데이터 관리
└── run_pipeline.py           # (기존 유지, model_registry 연동)
```

## Detailed Design

### 1. Model Abstraction Layer

```python
# base_engine.py
class BaseOCREngine(ABC):
    @abstractmethod
    def load_model(self, config: dict) -> None: ...
    
    @abstractmethod
    def predict_text(self, images: list[PIL.Image], field_types: list[str]) -> list[OCRResult]: ...
    
    @abstractmethod
    def get_model_info(self) -> dict: ...  # name, version, params, etc.

# 체크박스/서명은 OCR과 독립적인 감지기로 분리
class CheckboxDetector:
    def detect(self, image: PIL.Image, threshold: float = 0.10) -> CheckboxResult: ...

class SignatureDetector:
    def detect(self, image: PIL.Image, threshold: float = 0.03) -> SignatureResult: ...
```

```yaml
# model_config.yaml
models:
  fine_tuned_trocr:
    engine: trocr
    model_path: ../handwriting_ocr/checkpoints/best/
    max_new_tokens: 32
    num_beams: 4
    device: cuda:0
    description: "Fine-tuned TrOCR (CER 2.6%, 54M params)"
    
  ko_trocr:
    engine: trocr
    model_name: ddobokki/ko-trocr
    max_new_tokens: 64
    num_beams: 4
    device: cuda:0
    description: "General Korean TrOCR (213M params)"

default_model: fine_tuned_trocr
```

### 2. Field Dependency System

```python
# field_dependency.py
FIELD_DEPENDENCIES = {
    # 가족관계 세트: 하나라도 값이 있으면 나머지도 있어야 함
    "family_set": {
        "type": "linked_set",  # 하나라도 있으면 전부 있어야
        "groups": [
            ["family_1_left_relation", "family_1_left_name", "family_1_left_rrn"],
            ["family_1_right_relation", "family_1_right_name", "family_1_right_rrn"],
            # ... family_2 ~ family_4
        ]
    },
    
    # 등록신청인: 필수/선택 구분
    "applicant": {
        "type": "mixed",
        "required": ["applicant_name", "applicant_rrn", "applicant_address"],
        "optional": ["applicant_account", "applicant_phone"]
    },
    
    # 경영주 정보: 전부 선택 (비어있어도 OK)
    "manager": {
        "type": "all_optional",
        "fields": ["manager_name", "manager_farmer_no", "manager_address", 
                   "manager_village", "manager_phone", "manager_application_type",
                   "livestock_farm_checked", "facility_farm_checked"]
    },
    
    # 경영주 외 농업인: 전부 선택이지만, 이름이 있으면 생년월일도 있어야
    "other_farmer": {
        "type": "conditional",
        "trigger": "other_farmer_name",  # 이 필드에 값이 있으면
        "then_required": ["other_farmer_birth"],  # 이것도 필요
        "always_optional": ["other_farmer_no", "other_farmer_relation"]
    }
}
```

### 3. Integrated Review UI

검수 화면 레이아웃 (수정 패널 우선 60:40):
```
┌───────────────────────────────────────────────────────────────────┐
│  문서 8/50 완료  ████████░░ 80%    [< 이전]  문서 3  [다음 >]     │
│  필터: [전체|문제만|완료]  [문서 건너뛰기 / 재스캔 요청]           │
├──────────────────────┬────────────────────────────────────────────┤
│                      │  ┌──────────────────────────────────────┐  │
│  문서 이미지 (40%)   │  │  검수 패널 (60%)                      │  │
│                      │  │                                      │  │
│  ┌────────────────┐  │  │  [crop 이미지 2-3x 확대]              │  │
│  │ 축소 전체 이미지 │  │  │                                      │  │
│  │                │  │  │  OCR 결과: "홍길동"  신뢰도: 0.94 ✓    │  │
│  │ 선택된 필드     │  │  │  [수정 입력: ___________ ]            │  │
│  │ 자동 스크롤    │  │  │                                      │  │
│  │ + 하이라이트   │  │  │  후보 (최대 5개):                     │  │
│  │                │  │  │   홍길동 (0.94) [클릭선택]            │  │
│  │ ■ 초록 = OK    │  │  │   홍길둥 (0.41) [클릭선택]            │  │
│  │ ■ 주황 = review│  │  │                                      │  │
│  │ ■ 빨강 = error │  │  │  [확인 Enter] [건너뛰기 Esc]          │  │
│  │                │  │  │  [실행취소 Ctrl+Z]                    │  │
│  └────────────────┘  │  │                                      │  │
│                      │  │  ── 연관 필드 그룹 ──                  │  │
│  필드 목록 (사이드바) │  │  관계: 배우자 (0.87) ⚠️                │  │
│  > applicant_name ✓  │  │  성명: 김영희 (0.91) ✓                 │  │
│  > applicant_rrn  ⚠️  │  │  주민번호: 800101-2... (0.45) ❌       │  │
│  > applicant_addr ✓  │  │  [그룹 전체 확인]                     │  │
│  > family_1 그룹  ❌  │  └──────────────────────────────────────┘  │
│  (대체 네비게이션)    │                                            │
├──────────────────────┴────────────────────────────────────────────┤
│  이 문서: 12/15 필드 완료  ██████░░░░ │ [엑셀 내보내기] [CSV 저장] │
└───────────────────────────────────────────────────────────────────┘
```

### UI 상세 명세

**레이아웃 기술**: CSS positioned divs over scaled `<img>` (Canvas 아닌 DOM 기반)
- 좌표 매핑: bbox_norm 비율 좌표 → CSS percentage로 변환 (반응형)
- 클릭 타겟 최소 크기: 24x24px + 4px 패딩 (작은 필드도 클릭 가능)
- 브라우저 리사이즈 시 비율 유지

**Tab 순서**: 신뢰도 오름차순 (worst-first), 연관 그룹 내에서는 그룹 순서 유지
- Tab: 다음 문제 필드 / Shift+Tab: 이전 문제 필드
- Enter: 확인 + 다음 이동 / Esc: 건너뛰기
- Ctrl+Z: 마지막 수정 실행취소

**연관 필드 그룹 규칙**:
- 그룹 내 하나라도 flagged이면 그룹 전체를 리뷰 큐에 표시
- 그룹 구성원 중 OK인 것도 함께 보여줌 (컨텍스트)

**진행률**: 2단계 표시
- 상단: 전체 문서 진행률 (8/50 문서 완료)
- 하단: 현재 문서 필드 진행률 (12/15 필드 완료)
- 문서 100% 완료 시: 완료 애니메이션 + 자동으로 다음 문서 이동

**누락 상태 처리**:
- Loading: OCR 처리 중 스켈레톤 UI + 프로그레스 바
- Empty batch: "검수할 문서가 없습니다" + 다음 단계 안내
- Partial failure: 문서별 오류 뱃지, 오류 문서 별도 탭
- Save failure: 토스트 알림 + 자동 재시도 (3회)
- 동시 편집: 파일 write-then-rename 원자적 저장 + version 필드로 stale 감지

**"Wall of red" 대응**:
- 40개 이상 필드 flagged 시: "이 문서는 스캔 품질이 낮습니다. 재스캔을 권장합니다" 알림
- [문서 건너뛰기] 또는 [재스캔 요청] 버튼 제공
- 심각도순 정렬: 빨강(error) → 주황(review) → 초록(ok)

핵심 UX 원칙:
- 문제 필드 클릭 → crop 이미지와 수정 칸이 바로 옆에 (시선 이동 최소화)
- 연관 필드는 그룹으로 묶어 표시 (가족 관계-성명-주민번호가 한번에 보임)
- 수정 즉시 저장 (write-then-rename 원자적 저장)
- Tab/Shift+Tab으로 문제 필드만 순차 이동 (신뢰도 오름차순)
- 전체 진행률 실시간 표시 (문서 + 필드 2단계)
- 필드 목록 사이드바: 이미지 클릭이 어려울 때 대체 네비게이션

### 4. Data Store

```python
# data_store.py
class DataStore:
    """실시간 JSON 기반 데이터 저장소"""
    
    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.store_path = os.path.join(work_dir, "data_store")
        
    def save_field(self, doc_id: str, field_key: str, value: str, 
                   edited: bool = False) -> None:
        """필드 값 즉시 저장 + 수정 이력"""
        
    def get_document(self, doc_id: str) -> dict:
        """문서 전체 데이터 조회"""
        
    def get_edit_history(self, doc_id: str, field_key: str) -> list:
        """필드 수정 이력 조회"""
        
    def get_document_status(self, doc_id: str) -> str:
        """문서 완료 상태 (all_ok / needs_review / incomplete)"""
        
    def check_dependencies(self, doc_id: str) -> list[dict]:
        """연관 필드 일관성 검증"""
        
    def export_to_excel(self, output_path: str) -> None:
        """확정된 데이터만 엑셀로 내보내기"""
```

수정 이력 스키마:
```json
{
  "field_key": "applicant_name",
  "original_value": "홍길둥",
  "original_confidence": 0.41,
  "edited_value": "홍길동",
  "edited_at": "2026-05-06T19:30:00",
  "edit_source": "manual_review"
}
```

## Implementation Order

1. **models/ + model_registry.py** (모델 추상화) -- 기존 ocr_engine.py 리팩터링
2. **field_dependency.py** (필드 연관성 규칙 정의)
3. **data_store.py** (실시간 저장소)
4. **validator.py 확장** (연관성 검증 추가)
5. **review_app.py + 프론트엔드** (통합 검수 UI)
6. **active_learning.py** (수정 데이터 수집 + 학습 데이터 관리)
7. **run_pipeline.py 수정** (model_registry 연동)
8. **통합 테스트 + 실문서 검증**

## Risks

1. **Fine-tuned 모델 호환성**: checkpoints/best/의 토크나이저가 기존 파이프라인과 호환되는지 확인 필요
2. **프론트엔드 복잡도**: Canvas 기반 이미지 오버레이 + 실시간 수정 UI가 브라우저 성능에 영향
3. **데이터 무결성**: 실시간 저장 시 동시 접근으로 인한 데이터 손상 가능
4. **모델 전환 시 결과 차이**: 같은 이미지에 다른 모델을 적용하면 기존 검수 결과가 무효화될 수 있음

## Success Criteria

1. 모델 교체가 config 파일 수정만으로 가능 (코드 변경 0)
2. 검수 시 문제 필드의 crop 이미지와 수정 입력이 같은 화면에 표시
3. 연관 필드 그룹에서 일부만 비어있으면 경고 표시
4. 수정 즉시 저장, 엑셀 재생성 없이 결과 반영
5. Fine-tuned 모델 사용 시 CER < 3% 유지
6. 실문서 검증: 실제 스캔 문서 10건 이상에서 Exact Match > 85%
7. 검수 시간: 수동 입력 대비 50% 이상 단축
8. Active Learning: 수정 데이터 수집 및 재학습 트리거 동작 확인

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|---------------|-----------|-----------|----------|
| 1 | CEO | Modular rewrite over extend existing | Mechanical | P1+P5 | Clean abstractions for VLM swap | Extend existing |
| 2 | CEO | Add CSV export alongside Excel | Mechanical | P2 | Low effort, blast radius | - |
| 3 | CEO | Add outcome metrics to success criteria | Mechanical | P1 | Subagent flagged missing outcomes | Feature-only criteria |
| 4 | CEO | Premise gate: user chose C (active learning) | User Gate | - | User decision | A, B |
| 5 | Design | Correction panel 60%, doc image 40% | Mechanical | P5 | Users correct, not browse | Equal panels |
| 6 | Design | Add 5 missing UI states | Mechanical | P1 | Completeness | - |
| 7 | Design | CSS divs over img (not Canvas) | Mechanical | P5 | Simpler, accessible | Canvas |
| 8 | Design | Percentage-based coords, responsive | Mechanical | P5 | Explicit | - |
| 9 | Design | Tab order: confidence ascending | Mechanical | P3 | Worst-first saves time | Spatial order |
| 10 | Design | Min click target 24x24px | Mechanical | P1 | Usability | - |
| 11 | Design | Max 5 candidates shown | Mechanical | P3 | Pragmatic | Unlimited |
| 12 | Design | Crop 2-3x magnification | Mechanical | P5 | Readable | 1x |
| 13 | Design | Two-tier progress (doc + field) | Mechanical | P1 | Completeness | Field only |
| 14 | Design | Skip/rescan document button | Mechanical | P1 | Edge case | - |
| 15 | Design | Show full group when any member flagged | Mechanical | P1 | Context needed | Flagged only |
| 16 | Design | Write-then-rename atomic save | Mechanical | P5 | Simple, safe | Direct write |
| 17 | Eng | Separate checkbox/signature from OCR interface | Mechanical | P5 | Independent concerns | Bundled interface |
| 18 | Eng | Add doc_id whitelist validation (security) | Mechanical | P1 | Path traversal vulnerability | No validation |
| 19 | Eng | Lazy-load crops via /api/crop endpoint | Mechanical | P5 | Memory bomb fix | Base64 all-at-once |
| 20 | Eng | Catch OOM, halve batch, retry | Mechanical | P1 | GPU edge case | Batch fails entirely |
| 21 | Eng | Confidence calibration as prerequisite | Mechanical | P1 | Thresholds depend on it | Optional sub-bullet |
| 22 | Eng | Mask PII on storage, raw in memory only | Mechanical | P1 | Security | Plaintext JSON |
| 23 | Eng | Add test plan (6 unit + 3 integration suites) | Mechanical | P1 | Zero tests existed | No tests |
