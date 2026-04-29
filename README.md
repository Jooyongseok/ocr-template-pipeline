# OCR Template Pipeline

한국어 서류 OCR 템플릿 기반 자동 추출 시스템

대상 문서: **기본직접지불금 지급대상자 등록신청서 (농업인용)**

## 구조

```
template_editor/
  ocr_template_editor.html    # 템플릿 편집기 (브라우저에서 직접 실행)
ocr_pipeline/
  run_pipeline.py              # 메인 CLI (배치 OCR)
  ocr_engine.py                # ko-trocr GPU 추론 + checkbox
  crop_generator.py            # PDF -> crop 이미지
  validator.py                 # 검증 규칙 + 마스킹
  excel_writer.py              # 엑셀 4시트 출력
  review_server.py             # 검수 UI 서버
docs/
  project_documentation.pdf    # 전체 구조 문서 (7페이지)
```

## 사용법

### 1. 설치

```bash
pip install torch transformers pymupdf pillow openpyxl opencv-python-headless flask tqdm
```

### 2. 템플릿 생성

`template_editor/ocr_template_editor.html`을 브라우저에서 열어 PDF 위에 바운딩 박스를 지정하고 JSON으로 저장합니다.

### 3. OCR 실행

```bash
cd ocr_pipeline
python run_pipeline.py \
  --template ../template/page1_template.json \
  --input ../input/ \
  --output ../output/result.xlsx \
  --device cuda:0 \
  --batch-size 32
```

### 4. 검수

```bash
python review_server.py --work-dir ../work
# 브라우저에서 localhost:5001 접속
```

## OCR 모델

- **ddobokki/ko-trocr** (Apache-2.0)
- 파라미터: 213.7M
- VRAM: ~1.2 GB (batch=32, FP32)

## 주요 기능

- 53개 프리셋 필드, 줌/그리드/다중선택/Undo
- GPU 배치 추론, 중단 후 이어서 처리 (--resume)
- 신뢰도 기반 자동/검수 분류
- 웹 검수 UI (키보드 단축키)
- 개인정보 마스킹 (주민등록번호, 계좌번호)
