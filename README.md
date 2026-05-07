# OCR Template Pipeline v2

한국어 서류 OCR 템플릿 기반 자동 추출 시스템

**대상 문서**: 기본직접지불금 지급대상자 등록신청서 (농업인용)

> PDF 문서에서 템플릿 기반으로 필드를 추출하고, Fine-tuned TrOCR로 한글 손글씨를 인식한 뒤, 웹 기반 검수 UI에서 교정하여 엑셀로 출력하는 End-to-End 파이프라인

---

## 목차

- [프로젝트 구조](#프로젝트-구조)
- [주요 기능](#주요-기능)
- [시스템 아키텍처](#시스템-아키텍처)
- [데이터 흐름](#데이터-흐름)
- [모델 성능](#모델-성능)
- [설치 및 실행](#설치-및-실행)
- [API 명세](#api-명세)
- [기술 스택](#기술-스택)
- [프로젝트 통계](#프로젝트-통계)
- [버전 히스토리](#버전-히스토리)

---

## 프로젝트 구조

```
capstone/
├── ocr_pipeline/                  # OCR 파이프라인 (핵심 모듈)
│   ├── models/                    # 모델 추상화 레이어
│   │   ├── base_engine.py         #   추상 OCR 인터페이스 (BaseOCREngine)
│   │   └── trocr_engine.py        #   TrOCR 엔진 구현 (fine-tuned + 범용)
│   ├── model_registry.py          # 모델 등록/로딩/교체 (YAML 설정 기반)
│   ├── model_config.yaml          # 모델 설정 파일 (한 줄로 모델 교체)
│   ├── crop_generator.py          # PDF → 필드별 crop 이미지 생성
│   ├── ocr_engine.py              # OCR 추론 엔진 (배치 처리)
│   ├── validator.py               # 필드별 검증 규칙 + 신뢰도 분류
│   ├── field_dependency.py        # 필드 연관성 규칙 (세트/필수/조건부)
│   ├── data_store.py              # 실시간 JSON 저장소 + 수정 이력 + PII 마스킹
│   ├── active_learning.py         # 수정 데이터 수집 → 재학습용 내보내기
│   ├── review_app.py              # 통합 검수 웹 앱 (Flask, 13개 REST API)
│   ├── excel_writer.py            # 엑셀 4시트 출력
│   ├── run_pipeline.py            # 메인 CLI (배치 OCR 실행)
│   ├── static/
│   │   ├── review.js              #   검수 UI 로직 (인라인 수정, 키보드 네비게이션)
│   │   └── review.css             #   검수 UI 스타일 (Catppuccin Mocha 테마)
│   └── templates/
│       └── review.html            #   검수 UI 페이지
│
├── handwriting_ocr/               # TrOCR 한글 손글씨 Fine-tuning
│   ├── train.py                   #   학습 루프 (mixed precision, cosine LR)
│   ├── evaluate.py                #   평가 + 에러 분석
│   ├── dataset.py                 #   PyTorch Dataset + 데이터 증강
│   ├── metrics.py                 #   8가지 평가지표 (CER, WER, F1 등)
│   ├── prepare_data.py            #   AI Hub 데이터 전처리
│   ├── checkpoints/best/          #   학습 완료 모델 (CER 2.6%, 54.5M params)
│   ├── eval_results/              #   평가 결과
│   └── vlm_benchmark/             #   VLM 모델 벤치마크 (Qwen-VL, Varco)
│       ├── benchmark_zeroshot.py  #     Zero-shot VLM 평가
│       ├── finetune_qwen.py       #     Qwen-VL Fine-tuning
│       ├── finetune_varco.py      #     Varco Fine-tuning
│       └── final_comparison.py    #     TrOCR vs VLM 비교
│
├── template_editor/               # 템플릿 편집기 (브라우저 기반)
│   ├── app.py                     #   Flask 서버 (업로드, 저장)
│   ├── field_presets.py           #   70+ 필드 프리셋 정의 (12 타입, 6 그룹)
│   ├── ocr_template_editor.html   #   Canvas 기반 바운딩 박스 편집기
│   └── templates/index.html       #   편집기 UI
│
├── template/                      # 템플릿 JSON 파일
├── input/                         # 입력 PDF 파일
├── output/                        # 출력 엑셀 파일
├── work/                          # 작업 디렉토리 (crop, OCR 결과, JSON 저장소)
├── docs/                          # 프로젝트 문서 (project_documentation.pdf)
├── PLAN.md                        # v2 아키텍처 설계 문서 (396줄)
└── requirements.txt               # Python 의존성
```

---

## 주요 기능

### 1. 모델 추상화 레이어

OCR 모델을 **설정 파일 한 줄**로 교체할 수 있다. 코드 수정 없이 YAML만 변경하면 된다.

```yaml
# ocr_pipeline/model_config.yaml
models:
  fine_tuned_trocr:
    engine: trocr
    model_path: ../handwriting_ocr/checkpoints/best/
    max_new_tokens: 32
    num_beams: 4
    batch_size: 32
    description: "Fine-tuned TrOCR-small (CER 2.6%, 54M params)"

  ko_trocr:
    engine: trocr
    model_name: ddobokki/ko-trocr
    max_new_tokens: 64
    num_beams: 4
    batch_size: 32
    description: "General Korean TrOCR (213M params)"

# 이 한 줄만 바꾸면 모델 교체
default_model: fine_tuned_trocr
```

**새 모델 추가 방법**:
1. `models/` 폴더에 `BaseOCREngine`을 상속한 클래스 작성
2. `model_registry.py`의 `ENGINE_MAP`에 등록
3. `model_config.yaml`에 설정 추가

체크박스/서명 감지는 OCR 모델과 독립적인 `CheckboxDetector`, `SignatureDetector`로 분리되어 있다.

### 2. 통합 검수 UI

문제 필드를 **프로그램 내에서 즉각 수정**할 수 있다. 엑셀을 열 필요 없음.

**레이아웃**: 문서 이미지(40%) + 검수 패널(60%)
- 문서 이미지 위에 필드 위치가 색상 오버레이로 표시 (초록: 정상 / 주황: 주의 / 빨강: 오류)
- 문제 필드 클릭 → crop 이미지 2-3배 확대 + 수정 입력 칸이 바로 옆에 표시
- 수정 즉시 저장 (별도 저장 버튼 없음)
- Catppuccin Mocha 다크 테마

**키보드 단축키**:

| 키 | 동작 |
|----|------|
| `Tab` | 다음 문제 필드 (신뢰도 낮은 순) |
| `Shift+Tab` | 이전 문제 필드 |
| `Enter` | 확인 + 다음 이동 |
| `Esc` | 건너뛰기 |
| `Ctrl+Z` | 원본 값 복원 |

**2단계 진행률 표시**: 전체 문서 진행률 (8/50) + 현재 문서 필드 진행률 (12/15)

### 3. 필드 연관성 관리

필드 간 의존관계를 시스템이 인식하여 자동으로 경고한다.

| 타입 | 설명 | 예시 |
|------|------|------|
| `linked_set` | 하나라도 값이 있으면 나머지도 필요 | 가족관계 (관계 + 성명 + 주민번호) |
| `mixed` | 일부 필수 + 일부 선택 | 등록신청인 (이름/주소 필수, 전화 선택) |
| `all_optional` | 전부 비어있어도 OK | 경영주 정보 |
| `conditional` | 특정 필드에 값이 있으면 다른 필드도 필요 | 경영주 외 (이름 있으면 생년월일도 필요) |

검수 UI에서 연관 필드는 **그룹으로 묶어** 함께 표시된다.

### 4. 안전한 데이터 저장

- **원자적 저장**: write-then-rename 패턴으로 중간에 프로세스가 죽어도 데이터 손상 없음
- **수정 이력**: 모든 수정이 JSONL로 기록 (원본 값, 수정 값, 시각, 원본 신뢰도)
- **PII 마스킹**: 주민등록번호 뒷자리, 계좌번호는 저장 시 자동 마스킹
- **보안**: document_id 화이트리스트 검증으로 경로 순회 공격 차단

### 5. Active Learning

사용자가 검수 중 수정한 데이터를 자동으로 수집하여 모델 재학습에 활용한다.

- 수정 시 (crop 이미지, 정답 텍스트) 쌍 자동 저장
- **500건 누적 시 재학습 권장 알림**
- 신뢰도 분포 분석 (어떤 구간에서 오류가 많은지)
- TrOCR fine-tuning용 CSV 내보내기 (`image_path, text` 형식)

### 6. Fine-tuned TrOCR 한글 손글씨 모델

AI Hub 한국어 글자체 데이터셋(23GB)으로 학습한 모델이 기본 탑재되어 있다.

| 지표 | 값 |
|------|------|
| CER (Character Error Rate) | **2.648%** |
| Exact Match Accuracy | **97.35%** |
| 파라미터 수 | 54.5M (범용 모델 213M 대비 **3.9배 작음**) |
| 모델 크기 | 218 MB |
| 처리 속도 | 678.9 samples/sec |
| 학습 시간 | 6-7시간 (A100 80GB) |
| 테스트 샘플 | 50,000개 |

### 7. VLM 벤치마크

TrOCR 외에 Vision-Language Model(VLM) 기반 OCR도 실험하였다.

- **Qwen-VL**: Zero-shot + SFT Fine-tuning (step 1500~5500)
- **Varco**: Fine-tuning
- **비교 분석**: TrOCR vs VLM 성능/속도/크기 비교 (`final_comparison.py`)

### 8. 템플릿 편집기

브라우저에서 PDF 위에 바운딩 박스를 그려 필드 템플릿을 생성한다.

- Canvas 기반 드래그 & 드롭 편집
- **70+ 필드 프리셋** 제공 (12 타입 x 6 그룹)
- 필드 타입: `korean_name`, `resident_number`, `phone`, `account`, `address`, `number_text`, `date`, `date_or_birth`, `relation`, `text`, `checkbox`, `signature`
- JSON 형식으로 저장/로드

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Template Editor                              │
│                   (브라우저 기반 바운딩 박스 편집)                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ template.json
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       OCR Pipeline (Core)                            │
│                                                                      │
│  ┌──────────────┐    ┌─────────────────────────────────────────┐     │
│  │ PDF Input     │───▶│ crop_generator.py                       │     │
│  └──────────────┘    │ (PDF → 필드별 crop 이미지)               │     │
│                      └──────────────┬──────────────────────────┘     │
│                                     │                                │
│                                     ▼                                │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ model_registry.py (모델 추상화)                                │    │
│  │  ┌────────────────────┐  ┌────────────────────────────┐     │    │
│  │  │ fine_tuned_trocr   │  │ ko_trocr (범용)             │     │    │
│  │  │ CER 2.6% / 54M    │  │ 213M params                │     │    │
│  │  └────────────────────┘  └────────────────────────────┘     │    │
│  │  ┌────────────────────┐  ┌────────────────────────────┐     │    │
│  │  │ CheckboxDetector   │  │ SignatureDetector           │     │    │
│  │  └────────────────────┘  └────────────────────────────┘     │    │
│  └──────────────────────────┬───────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────┐    ┌─────────────────┐    ┌──────────────────┐   │
│  │ validator.py   │───▶│ field_dependency │───▶│ data_store.py    │   │
│  │ (검증+신뢰도)   │    │ (연관성 규칙)     │    │ (원자적 JSON 저장) │   │
│  └───────────────┘    └─────────────────┘    └────────┬─────────┘   │
│                                                        │             │
└────────────────────────────────────────────────────────┼─────────────┘
                                                         │
                              ┌───────────────────────────┼──────────┐
                              │                           ▼          │
                              │  ┌─────────────────────────────────┐ │
                              │  │ review_app.py (통합 검수 UI)      │ │
                              │  │ Flask + 13 REST API              │ │
                              │  └──────────┬──────────────────────┘ │
                              │             │                        │
                              │    ┌────────┴─────────┐              │
                              │    ▼                   ▼              │
                              │ ┌──────────────┐ ┌───────────────┐   │
                              │ │ excel_writer  │ │ active_learning│   │
                              │ │ (4시트 엑셀)   │ │ (재학습 데이터) │   │
                              │ └──────────────┘ └───────────────┘   │
                              └──────────────────────────────────────┘
```

---

## 데이터 흐름

```
PDF 입력
  │
  ▼
crop_generator.py ── 템플릿 바운딩 박스 기반 필드 crop 이미지 추출
  │
  ▼
ocr_requests/batch_*.jsonl ── OCR 요청 큐 (JSONL)
  │
  ▼
model_registry.process_requests() ── TrOCR 배치 추론 (GPU)
  │
  ▼
ocr_results/all_results.jsonl ── OCR 결과 (텍스트 + 신뢰도)
  │
  ▼
run_pipeline.merge_results() + check_dependencies() ── 결과 병합 + 연관성 검증
  │
  ▼
data_store.save_document() ── 원자적 JSON 저장 + PII 마스킹
  │
  ▼
review_app (웹 검수 UI) ── 문제 필드 수정 + 즉시 저장
  │
  ├──▶ active_learning.collect_correction() ── 수정 데이터 자동 수집
  │
  ▼
excel_writer.write_excel() ── 최종 엑셀 출력 (4시트)
```

---

## 모델 성능

### Fine-tuned TrOCR-small (기본 모델)

| 지표 | 값 |
|------|------|
| CER | 2.648% |
| Exact Match | 97.35% |
| 파라미터 | 54.5M |
| 모델 크기 | 218 MB |
| 추론 속도 | 678.9 samples/sec |

### 모델 비교

| 모델 | 파라미터 | CER | 비고 |
|------|----------|-----|------|
| **Fine-tuned TrOCR-small** | 54.5M | 2.648% | AI Hub 한글 손글씨 학습, 기본 탑재 |
| ddobokki/ko-trocr | 213M | - | 범용 한국어 TrOCR |
| Qwen-VL (실험) | - | - | VLM 벤치마크 진행 중 |
| Varco (실험) | - | - | VLM 벤치마크 진행 중 |

### 학습 환경

- **GPU**: NVIDIA A100 80GB
- **학습 시간**: 6-7시간
- **데이터셋**: AI Hub 한국어 글자체 (23GB raw → 42MB processed)
- **테스트**: 50,000 샘플
- **기법**: Mixed precision (bf16), Cosine LR scheduler, Warmup

---

## 설치 및 실행

### 1. 환경 설정

```bash
# 의존성 설치
pip install -r requirements.txt
```

**requirements.txt**:
```
torch>=2.0.0
transformers>=4.30.0
Pillow>=9.0.0
PyMuPDF>=1.23.0
openpyxl>=3.1.0
opencv-python-headless>=4.8.0
flask>=3.0.0
tqdm>=4.65.0
pyyaml>=6.0.0
numpy>=1.24.0
```

### 2. 템플릿 생성

```bash
cd template_editor
python app.py
# 브라우저에서 http://localhost:5000 접속
# PDF 업로드 → 바운딩 박스 지정 → JSON으로 저장
```

### 3. OCR 실행

```bash
cd ocr_pipeline
python run_pipeline.py \
  --template ../template/page1_template.json \
  --input ../input/ \
  --output ../output/result.xlsx
```

모델 변경:
```bash
# CLI 옵션으로 변경
python run_pipeline.py --model-id ko_trocr ...

# 또는 model_config.yaml에서 default_model 변경
```

### 4. 검수

```bash
python -m ocr_pipeline.review_app --work-dir work
# 브라우저에서 http://localhost:5001 접속
```

### 5. Active Learning 데이터 내보내기

```python
from ocr_pipeline.active_learning import ActiveLearningCollector

collector = ActiveLearningCollector("work")
export_path = collector.export_for_training()
# → work/learning_data/export/training_data_YYYYMMDD.csv
```

### 6. 모델 학습 (Fine-tuning)

```bash
cd handwriting_ocr
python train.py  # AI Hub 데이터 기반 TrOCR fine-tuning
python evaluate.py  # 평가 + 에러 분석
```

---

## API 명세

검수 앱(`review_app.py`)이 제공하는 REST API:

| Method | Endpoint | 설명 | 비고 |
|--------|----------|------|------|
| `GET` | `/api/documents` | 문서 목록 (상태 포함) | |
| `GET` | `/api/document/<id>/fields` | 문서 전체 필드 (오버레이용) | 신뢰도순 정렬 |
| `GET` | `/api/review-items` | 검수 대상 필드 | 페이지네이션 지원 |
| `GET` | `/api/crop/<id>/<key>` | crop 이미지 | lazy-loading, 보안 검증 |
| `GET` | `/api/page-image/<id>/<page>` | 페이지 전체 이미지 | |
| `POST` | `/api/update` | 필드 값 수정 | 즉시 저장, 이력 기록 |
| `POST` | `/api/skip-document` | 문서 건너뛰기 | |
| `GET` | `/api/stats` | 배치 통계 | 완료/검수/오류 수 |
| `POST` | `/api/export-excel` | 엑셀 내보내기 | 4시트 출력 |
| `GET` | `/api/learning-stats` | Active Learning 통계 | 수집 현황 |
| `POST` | `/api/export-training-data` | 재학습 데이터 내보내기 | CSV 형식 |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **딥러닝** | PyTorch 2.0+, HuggingFace Transformers 4.30+ |
| **OCR 모델** | TrOCR-small (fine-tuned), ddobokki/ko-trocr |
| **VLM (실험)** | Qwen-VL, Varco |
| **PDF 처리** | PyMuPDF (fitz) |
| **이미지 처리** | Pillow, OpenCV (headless) |
| **웹 프레임워크** | Flask 3.0+ |
| **프론트엔드** | Vanilla JS + Catppuccin Mocha CSS |
| **엑셀 출력** | openpyxl |
| **설정 관리** | PyYAML |
| **학습 데이터** | AI Hub 한국어 글자체 데이터셋 |

---

## 프로젝트 통계

| 항목 | 값 |
|------|------|
| 전체 Python 코드 | ~6,000+ lines |
| ocr_pipeline/ | 2,611 lines (13개 모듈) |
| handwriting_ocr/ | 1,238 lines (5개 스크립트) |
| vlm_benchmark/ | 2,057 lines (6개 스크립트) |
| template_editor/ | 215 lines (2개 스크립트) |
| 프론트엔드 (JS/CSS/HTML) | 990 lines |
| REST API 엔드포인트 | 13개 |
| 지원 필드 타입 | 12개 |
| 프리셋 필드 수 | 70+ |
| 필드 그룹 | 6개 |
| 모델 체크포인트 | 4개 (best + 3 epochs) |

---

## 보안

- **PII 마스킹**: 주민등록번호 뒷자리, 계좌번호 자동 마스킹
- **경로 보안**: document_id 정규식 화이트리스트 (`^[a-zA-Z0-9_\-]+$`)로 경로 순회 공격 차단
- **원자적 저장**: write-then-rename 패턴으로 데이터 무결성 보장
- **crop 경로 검증**: work_dir 외부 접근 차단

---

## 버전 히스토리

| 버전 | 날짜 | 내용 |
|------|------|------|
| **v2** | 2026-05-06 | 모델 추상화 레이어, 통합 검수 UI, 필드 연관성 시스템, Active Learning, 안전한 데이터 저장, VLM 벤치마크 |
| **v1** | 2026-04-29 | 초기 파이프라인 (템플릿 편집기 + 배치 OCR + 검수 UI + 엑셀 출력) |

---

## 라이선스

본 프로젝트는 캡스톤 디자인 과제로 개발되었습니다.
