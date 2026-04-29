# 1페이지 신청서 OCR 병렬 작업 계약 설계서

대상 문서: **기본직접지불금 지급대상자 등록신청서(농업인용) 1페이지**

목표는 전체 8페이지가 아니라 **1페이지 인적사항 중심 영역만 먼저 안정적으로 추출**하는 것이다.  
A팀과 B팀은 서로의 결과물을 기다리지 않고 동시에 개발하되, 최종적으로 `request_id`, `field_key`, `field_type`, JSONL 입출력 계약만 맞춰서 결과물을 합친다.

---

## 1. 전체 목표

1페이지에서 다음 정보를 추출한다.

- 등록신청인 정보
- 경영주인 농업인 정보
- 경영주 외의 농업인 정보
- 가족관계 인적정보 작성표 일부
- 축산농가/시설농가 체크 여부
- 가족관계 확인 체크 여부

전체 흐름은 다음과 같다.

```text
B팀: 1페이지 PDF/이미지 → 지정 좌표 crop → OCR 요청 JSONL 생성
A팀: crop 이미지 + OCR 요청 JSONL → OCR/체크박스 분석 → OCR 결과 JSONL 생성
B팀: OCR 결과 JSONL 병합 → 검증 → 검수용 CSV/Excel 생성
```

---

## 2. 팀별 책임 범위

## 2.1 A팀 책임

A팀은 **crop 이미지 하나를 받아서 분석 결과 한 줄을 반환하는 모듈**을 만든다.

A팀은 다음을 담당한다.

```text
1. OCR 요청 JSONL 읽기
2. crop_path의 이미지 열기
3. field_type에 따라 분석 방식 선택
4. 텍스트/체크박스/서명 여부 등 결과 반환
5. confidence, candidates, error 포함
6. 실패해도 반드시 OCR 결과 JSONL 한 줄 반환
```

A팀은 다음을 담당하지 않는다.

```text
1. PDF 전체 페이지 렌더링
2. 신청서 좌표 지정
3. crop 이미지 생성
4. 필드별 의미 해석
5. 엑셀 저장
6. 최종 검증 규칙 적용
```

즉, A팀은 신청서 전체 구조를 몰라도 된다.  
A팀은 `field_type`, `crop_path`, `request_id`만 신뢰하고 처리한다.

---

## 2.2 B팀 책임

B팀은 **1페이지 신청서 처리 파이프라인 전체**를 만든다.

B팀은 다음을 담당한다.

```text
1. 빈 양식 1페이지 기준 템플릿 좌표 관리
2. 실제 PDF 1페이지 렌더링
3. 필드별 crop 이미지 생성
4. OCR 요청 JSONL 생성
5. A팀 OCR 결과 JSONL 수신
6. request_id 기준 결과 병합
7. field_type별 검증 규칙 적용
8. 검수 대상 분리
9. 최종 Excel/CSV/JSON 저장
```

B팀은 다음을 담당하지 않는다.

```text
1. crop 이미지 내부의 글자 인식 모델 구현
2. 체크박스 이미지 판정 모델 구현
3. OCR 후보군 생성
```

---

## 3. 1페이지 필드 범위

## 3.1 일반현황 상단 기본 정보

| field_key | 라벨 | field_type | 필수 여부 | 비고 |
|---|---|---:|---:|---|
| receipt_no | 접수번호 | text | false | 색상이 어두운 난이면 추출 제외 가능 |
| receipt_date | 접수일자 | date | false | 추출 제외 가능 |
| farm_business_no | 농업경영체 등록번호 | number_text | false | 선택 |
| farmer_no_top | 농업인 번호 | number_text | false | 선택 |
| business_info_change_date | 경영정보변경일 | date | false | 선택 |

초기 1페이지 MVP에서는 위 상단 행은 제외해도 된다.  
우선 실사용자가 직접 작성하는 주요 인적사항부터 처리한다.

---

## 3.2 등록신청인

| field_key | 라벨 | field_type | 필수 여부 | 비고 |
|---|---|---:|---:|---|
| applicant_name | 등록신청인_성명 | korean_name | true | |
| applicant_rrn | 등록신청인_주민등록번호 | resident_number | true | 마스킹 저장 옵션 필요 |
| applicant_account | 등록신청인_계좌번호_은행명 | account | false | 은행명 포함 가능 |
| applicant_address | 등록신청인_주소 | address | true | 긴 텍스트 가능 |
| applicant_phone | 등록신청인_전화번호 | phone | false | |

---

## 3.3 경영주인 농업인

| field_key | 라벨 | field_type | 필수 여부 | 비고 |
|---|---|---:|---:|---|
| manager_name | 경영주_성명 | korean_name | false | 자동표시 영역일 수 있음 |
| manager_farmer_no | 경영주_농업인번호 | number_text | false | |
| manager_application_type | 경영주_신청유형 | text | false | 안내문 참조 영역 |
| manager_address | 경영주_주민등록표상주소지 | address | false | |
| manager_village | 경영주_마을명 | text | false | 괄호 안 |
| manager_phone | 경영주_전화번호 | phone | false | |
| livestock_farm_checked | 축산농가_체크 | checkbox | false | true/false/unknown |
| facility_farm_checked | 시설농가_체크 | checkbox | false | true/false/unknown |

---

## 3.4 경영주 외의 농업인

| field_key | 라벨 | field_type | 필수 여부 | 비고 |
|---|---|---:|---:|---|
| other_farmer_name | 경영주외_성명 | korean_name | false | |
| other_farmer_birth | 경영주외_생년월일 | date_or_birth | false | |
| other_farmer_no | 경영주외_농업인번호 | number_text | false | |
| other_farmer_relation | 경영주와의_관계 | relation | false | 예: 배우자 |

---

## 3.5 가족관계 인적정보 작성표 ④-1

초기 범위는 ④-1 주민등록표상 세대원만 대상으로 한다.  
좌우 2세트 컬럼이 있으므로 `left/right`를 명시한다.

| field_key | 라벨 | field_type | 필수 여부 |
|---|---|---:|---:|
| family_1_left_relation | 가족관계_④-1_1행_좌_관계 | relation | false |
| family_1_left_name | 가족관계_④-1_1행_좌_성명 | korean_name | false |
| family_1_left_rrn | 가족관계_④-1_1행_좌_주민등록번호 | resident_number | false |
| family_1_right_relation | 가족관계_④-1_1행_우_관계 | relation | false |
| family_1_right_name | 가족관계_④-1_1행_우_성명 | korean_name | false |
| family_1_right_rrn | 가족관계_④-1_1행_우_주민등록번호 | resident_number | false |

2행부터 4행까지는 같은 규칙으로 반복한다.

```text
family_2_left_relation
family_2_left_name
family_2_left_rrn
...
family_4_right_relation
family_4_right_name
family_4_right_rrn
```

---

## 3.6 가족관계 인적정보 작성표 ④-2

초기 범위에서는 선택 사항으로 둔다.  
추출이 필요하면 ④-1과 같은 방식으로 별도 필드를 둔다.

```text
family_separated_1_relation
family_separated_1_name
family_separated_1_rrn
family_separated_2_relation
family_separated_2_name
family_separated_2_rrn
```

---

## 3.7 확인 체크

| field_key | 라벨 | field_type | 필수 여부 | 비고 |
|---|---|---:|---:|---|
| family_info_confirm_checked | 가족관계_인적정보_확인_체크 | checkbox | false | 하단 `[ ] 확인` |

---

## 4. 공통 field_type 정의

A팀과 B팀은 아래 `field_type`을 공유한다.

| field_type | 의미 | A팀 반환 예시 | B팀 검증 |
|---|---|---|---|
| korean_name | 한글 이름 | 홍길동 | 2~5자 한글 중심 |
| resident_number | 주민등록번호 | 800101-1234567 | 형식 검사, 마스킹 가능 |
| phone | 전화번호 | 010-1234-5678 | 전화번호 패턴 검사 |
| account | 계좌번호/은행명 | 농협 123-456-7890 | 숫자/은행명 혼합 허용 |
| address | 주소 | 경기도 파주시 ... | 빈값/길이 확인 |
| number_text | 숫자성 문자열 | 123456789 | 숫자/하이픈 허용 |
| date | 날짜 | 2026-04-29 | 날짜 형식 정규화 |
| date_or_birth | 생년월일 | 1980-01-01 | 6자리/8자리/날짜 허용 |
| relation | 관계 | 배우자 | 관계 단어 사전 검증 |
| text | 일반 텍스트 | 임의 문자열 | 최소 검증 |
| checkbox | 체크박스 | true / false / unknown | unknown이면 검수 |
| signature | 서명/날인 | present / absent / unknown | 1페이지에서는 선택 |

---

## 5. OCR 요청 JSONL 계약

B팀이 A팀에게 전달하는 파일이다.  
한 줄에 crop 하나를 의미한다.

## 5.1 파일명 규칙

```text
work/ocr_requests/{batch_id}.jsonl
```

예시:

```text
work/ocr_requests/batch_000001.jsonl
```

## 5.2 요청 JSON 스키마

```json
{
  "request_id": "doc_000001__page_001__applicant_name",
  "document_id": "doc_000001",
  "template_id": "basic_direct_payment_farmer_page1_v1",
  "page": 1,
  "field_key": "applicant_name",
  "field_label": "등록신청인_성명",
  "field_type": "korean_name",
  "crop_path": "work/crops/doc_000001/page_001/applicant_name.png",
  "bbox_norm": [0.1562, 0.1801, 0.1800, 0.0350],
  "bbox_px": [160, 185, 184, 36],
  "required": true,
  "metadata": {
    "row_index": null,
    "group": "applicant",
    "source_pdf": "input/doc_000001.pdf"
  }
}
```

## 5.3 필수 키

A팀은 다음 키가 반드시 있다고 가정한다.

```text
request_id
document_id
template_id
page
field_key
field_label
field_type
crop_path
bbox_norm
```

## 5.4 request_id 규칙

```text
{document_id}__page_{page_3digit}__{field_key}
```

예시:

```text
doc_000001__page_001__applicant_name
doc_000001__page_001__livestock_farm_checked
doc_000001__page_001__family_1_left_rrn
```

`request_id`는 전체 batch 안에서 절대 중복되면 안 된다.

---

## 6. OCR 결과 JSONL 계약

A팀이 B팀에게 반환하는 파일이다.

## 6.1 파일명 규칙

```text
work/ocr_results/{batch_id}.jsonl
```

예시:

```text
work/ocr_results/batch_000001.jsonl
```

## 6.2 결과 JSON 스키마

```json
{
  "request_id": "doc_000001__page_001__applicant_name",
  "document_id": "doc_000001",
  "template_id": "basic_direct_payment_farmer_page1_v1",
  "page": 1,
  "field_key": "applicant_name",
  "field_type": "korean_name",
  "text": "홍길동",
  "normalized_text": "홍길동",
  "value": "홍길동",
  "confidence": 0.94,
  "candidates": [
    {"text": "홍길동", "confidence": 0.94},
    {"text": "홍길둥", "confidence": 0.41}
  ],
  "status": "ok",
  "error": null,
  "ocr_engine_version": "mock_model_v0.1"
}
```

## 6.3 checkbox 결과 예시

```json
{
  "request_id": "doc_000001__page_001__livestock_farm_checked",
  "document_id": "doc_000001",
  "template_id": "basic_direct_payment_farmer_page1_v1",
  "page": 1,
  "field_key": "livestock_farm_checked",
  "field_type": "checkbox",
  "text": "",
  "normalized_text": "",
  "value": true,
  "confidence": 0.88,
  "candidates": [
    {"value": true, "confidence": 0.88},
    {"value": false, "confidence": 0.12}
  ],
  "status": "ok",
  "error": null,
  "ocr_engine_version": "mock_model_v0.1"
}
```

## 6.4 실패 결과 예시

실패해도 반드시 한 줄을 반환한다.

```json
{
  "request_id": "doc_000001__page_001__applicant_rrn",
  "document_id": "doc_000001",
  "template_id": "basic_direct_payment_farmer_page1_v1",
  "page": 1,
  "field_key": "applicant_rrn",
  "field_type": "resident_number",
  "text": "",
  "normalized_text": "",
  "value": null,
  "confidence": 0.0,
  "candidates": [],
  "status": "ocr_failed",
  "error": "image_open_failed",
  "ocr_engine_version": "mock_model_v0.1"
}
```

---

## 7. 상태 코드 계약

A팀과 B팀은 아래 상태 코드를 공유한다.

| status | 의미 | 주 사용 팀 |
|---|---|---|
| ok | 정상 추출 | A/B |
| needs_review | 사람이 검수해야 함 | B |
| missing | 값이 비어 있음 | B |
| low_confidence | 신뢰도 낮음 | A/B |
| invalid_format | 형식 오류 | B |
| ocr_failed | OCR 실패 | A |
| multiple_candidates | 후보가 여러 개라 애매함 | A/B |
| unchecked | 체크박스 미체크 | A/B |
| unknown | 판정 불가 | A/B |

기준 신뢰도는 초기값으로 다음을 사용한다.

```text
confidence >= 0.80 → ok 후보
0.50 <= confidence < 0.80 → needs_review
confidence < 0.50 → low_confidence
```

단, 주민등록번호, 계좌번호, 체크박스는 confidence가 높아도 검수 대상으로 둘 수 있다.

---

## 8. B팀 검증 규칙

B팀은 OCR 결과를 받은 뒤 아래 규칙을 적용한다.

## 8.1 공통 규칙

```text
required=true인데 값이 비어 있으면 missing
confidence < 0.80이면 needs_review
A팀 status가 ocr_failed이면 needs_review
candidates가 2개 이상이고 점수 차이가 작으면 multiple_candidates
```

## 8.2 필드별 규칙

| field_type | 검증 규칙 |
|---|---|
| korean_name | 한글 2~5자 권장, 숫자 포함 시 invalid_format |
| resident_number | 6자리-7자리 또는 13자리 숫자 허용, 저장 시 마스킹 옵션 |
| phone | 02/031/010 등 전화번호 패턴 허용 |
| account | 숫자, 하이픈, 은행명 허용 |
| address | 5자 미만이면 needs_review |
| date_or_birth | 6자리/8자리/날짜형 허용 |
| relation | 본인/배우자/부/모/자/녀/기타 허용 |
| checkbox | true/false/unknown 중 하나, unknown이면 needs_review |

---

## 9. B팀 최종 병합 형식

B팀은 A팀 결과를 문서 단위로 합쳐서 다음 JSON을 만든다.

```json
{
  "document_id": "doc_000001",
  "template_id": "basic_direct_payment_farmer_page1_v1",
  "source_pdf": "input/doc_000001.pdf",
  "page_scope": [1],
  "fields": {
    "applicant_name": {
      "label": "등록신청인_성명",
      "value": "홍길동",
      "raw_text": "홍길동",
      "confidence": 0.94,
      "status": "ok",
      "warning": null,
      "crop_path": "work/crops/doc_000001/page_001/applicant_name.png"
    },
    "applicant_rrn": {
      "label": "등록신청인_주민등록번호",
      "value": "800101-1******",
      "raw_text": "800101-1234567",
      "confidence": 0.91,
      "status": "needs_review",
      "warning": "sensitive_personal_id"
    }
  },
  "document_status": "needs_review",
  "review_count": 1
}
```

---

## 10. Excel 산출물 계약

1페이지 전용이므로 초기에는 단일 시트 중심으로 저장한다.  
단, 가족관계 정보는 반복 행이므로 별도 시트로 분리할 수 있게 설계한다.

## 10.1 추천 시트 구조

```text
applicants
family_members
review_items
raw_ocr_results
```

## 10.2 applicants 시트 컬럼

| 컬럼명 | 매핑 field_key |
|---|---|
| document_id | document_id |
| source_pdf | source_pdf |
| 등록신청인_성명 | applicant_name |
| 등록신청인_주민등록번호 | applicant_rrn |
| 등록신청인_계좌번호_은행명 | applicant_account |
| 등록신청인_주소 | applicant_address |
| 등록신청인_전화번호 | applicant_phone |
| 경영주_성명 | manager_name |
| 경영주_농업인번호 | manager_farmer_no |
| 경영주_신청유형 | manager_application_type |
| 경영주_주소 | manager_address |
| 경영주_마을명 | manager_village |
| 경영주_전화번호 | manager_phone |
| 축산농가_체크 | livestock_farm_checked |
| 시설농가_체크 | facility_farm_checked |
| 경영주외_성명 | other_farmer_name |
| 경영주외_생년월일 | other_farmer_birth |
| 경영주외_농업인번호 | other_farmer_no |
| 경영주와의_관계 | other_farmer_relation |
| 가족관계_확인_체크 | family_info_confirm_checked |
| 문서상태 | document_status |
| 검수필요건수 | review_count |

## 10.3 family_members 시트 컬럼

| 컬럼명 |
|---|
| document_id |
| source_pdf |
| family_group |
| row_index |
| side |
| 관계 |
| 성명 |
| 주민등록번호 |
| confidence_min |
| status |

예시:

```text
doc_000001 | 신청서1.pdf | ④-1 | 1 | left | 배우자 | 김영희 | 800101-2****** | 0.87 | needs_review
```

## 10.4 review_items 시트 컬럼

| 컬럼명 |
|---|
| document_id |
| source_pdf |
| page |
| field_key |
| field_label |
| field_type |
| raw_text |
| value |
| confidence |
| status |
| warning |
| crop_path |

---

## 11. 폴더 및 파일 산출물 구조

```text
project_root/
  template/
    page1_template.json
    page1_field_map.csv

  input/
    doc_000001.pdf
    doc_000002.pdf

  work/
    page_images/
      doc_000001/page_001.png

    crops/
      doc_000001/page_001/applicant_name.png
      doc_000001/page_001/applicant_rrn.png

    ocr_requests/
      batch_000001.jsonl

    ocr_results/
      batch_000001.jsonl

    final_json/
      doc_000001_page1_extracted.json

  output/
    page1_result.xlsx
    page1_result.csv
    review_items.csv
    raw_ocr_results.jsonl
```

---

## 12. 템플릿 JSON 구조

B팀이 관리하는 1페이지 전용 템플릿이다.

```json
{
  "template_id": "basic_direct_payment_farmer_page1_v1",
  "document_name": "기본직접지불금 지급대상자 등록신청서_농업인용_1페이지",
  "page_scope": [1],
  "coordinate_system": "normalized",
  "page_width": 1024,
  "page_height": 768,
  "fields": [
    {
      "key": "applicant_name",
      "label": "등록신청인_성명",
      "page": 1,
      "group": "applicant",
      "field_type": "korean_name",
      "required": true,
      "bbox_norm": [0.165, 0.170, 0.175, 0.040],
      "excel_sheet": "applicants",
      "excel_column": "등록신청인_성명"
    },
    {
      "key": "livestock_farm_checked",
      "label": "축산농가_체크",
      "page": 1,
      "group": "manager",
      "field_type": "checkbox",
      "required": false,
      "bbox_norm": [0.795, 0.288, 0.025, 0.025],
      "excel_sheet": "applicants",
      "excel_column": "축산농가_체크"
    }
  ]
}
```

좌표값은 예시이므로 실제 빈 양식 이미지 위에서 B팀이 보정한다.

---

## 13. 동시 개발 방식

## 13.1 A팀은 다음 샘플로 개발 시작

B팀 최종 crop이 없어도 A팀은 샘플 crop과 샘플 요청 JSONL로 개발한다.

```text
contract/page1_ocr_request_sample.jsonl
samples/page1_crops/
```

A팀의 1차 완료 기준:

```text
1. 요청 JSONL을 읽는다.
2. 각 crop_path에 대해 결과 JSONL을 만든다.
3. request_id가 원본과 1:1로 대응한다.
4. 실패해도 결과 한 줄을 반환한다.
5. field_type=checkbox일 때 value=true/false/unknown을 반환한다.
```

---

## 13.2 B팀은 mock OCR 결과로 개발 시작

A팀 결과가 없어도 B팀은 mock 결과 파일로 병합/검증/엑셀 저장을 개발한다.

```text
contract/page1_ocr_result_sample.jsonl
```

B팀의 1차 완료 기준:

```text
1. 빈 양식 1페이지에서 필드 좌표를 저장한다.
2. 실제 PDF 여러 개에서 같은 좌표로 crop을 생성한다.
3. OCR 요청 JSONL을 만든다.
4. 샘플 OCR 결과 JSONL을 읽어 병합한다.
5. 검증 규칙을 적용한다.
6. Excel, CSV, review_items를 만든다.
```

---

## 14. 통합 테스트 기준

A팀/B팀 결과물을 합칠 때 아래 순서로 테스트한다.

```text
1. B팀이 실제 PDF 3개를 넣고 ocr_request.jsonl과 crop 이미지를 생성한다.
2. A팀이 해당 요청을 받아 ocr_result.jsonl을 생성한다.
3. B팀이 ocr_result.jsonl을 병합한다.
4. Excel 결과의 document_id 개수가 입력 PDF 개수와 같은지 확인한다.
5. request_id 누락/중복이 없는지 확인한다.
6. review_items에 low_confidence, missing, invalid_format이 정상 분리되는지 확인한다.
```

필수 통과 조건:

```text
요청 개수 == 결과 개수
request_id 중복 없음
request_id 누락 없음
document_id별 applicant_name 컬럼 생성
Excel 파일 열림
review_items 시트 생성
A팀 실패 결과도 B팀에서 검수 항목으로 표시
```

---

## 15. 개인정보 처리 원칙

1페이지에는 주민등록번호, 계좌번호, 주소, 전화번호가 포함된다.  
따라서 B팀은 저장 시 다음 정책을 옵션으로 제공한다.

```text
1. raw_text 원본 저장 여부 선택
2. 주민등록번호 Excel 저장 시 뒷자리 마스킹
3. 계좌번호 일부 마스킹
4. crop 이미지 보관/삭제 선택
5. 작업 완료 후 work/crops 삭제 옵션
```

추천 기본값:

```text
Excel에는 마스킹 값 저장
raw_ocr_results.jsonl에는 원본 저장 가능하나 접근 제한
검수 후 crop 이미지는 필요 시 삭제
```

---

## 16. 버전 규칙

1페이지 전용 계약 버전은 다음으로 시작한다.

```text
template_id: basic_direct_payment_farmer_page1_v1
contract_version: page1_contract_v1
```

변경 규칙:

```text
필드 추가만 있는 경우: page1_contract_v1 유지 가능
field_key 이름 변경: page1_contract_v2
JSONL 필수 키 변경: page1_contract_v2
Excel 컬럼명만 추가: page1_contract_v1.1
field_type 의미 변경: page1_contract_v2
```

---

## 17. 최종 결론

1페이지 전용으로는 A팀/B팀 분리가 충분히 현실적이다.

A팀은 **crop 단위 분석기**만 만들고,  
B팀은 **템플릿 좌표, crop 생성, 검증, 엑셀 저장**을 맡는다.

두 팀이 동시에 작업해도 다음 4가지만 고정하면 나중에 쉽게 합칠 수 있다.

```text
1. request_id
2. field_key
3. field_type
4. OCR 요청/결과 JSONL 스키마
```

초기 개발은 1페이지에서 성공 흐름을 만든 뒤, 3페이지 확인/서명, 4~5페이지 동의/서명, 2페이지 농지 표 순서로 확장하는 것이 좋다.
