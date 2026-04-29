"""프로젝트 구조 PDF 문서 생성"""
from fpdf import FPDF

FONT_PATH = "/tmp/NanumGothic.ttf"


class PDF(FPDF):
    def header(self):
        self.set_font("nanumgothic", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "OCR Template Pipeline - Project Documentation", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, 14, 200, 14)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("nanumgothic", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"- {self.page_no()} -", align="C")

    def section(self, title):
        self.set_font("nanumgothic", "B", 14)
        self.set_text_color(44, 62, 80)
        self.ln(4)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(52, 152, 219)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def subsection(self, title):
        self.set_font("nanumgothic", "B", 11)
        self.set_text_color(52, 73, 94)
        self.ln(2)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body(self, text):
        self.set_font("nanumgothic", size=9)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bullet(self, text):
        self.set_font("nanumgothic", size=9)
        self.set_text_color(50, 50, 50)
        x = self.get_x()
        self.cell(8, 5, "  -  ", new_x="END")
        self.multi_cell(0, 5, text)
        self.set_x(x)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [190 / len(headers)] * len(headers)
        # header
        self.set_font("nanumgothic", "B", 8)
        self.set_fill_color(44, 62, 80)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 6, h, border=1, fill=True, align="C")
        self.ln()
        # rows
        self.set_font("nanumgothic", size=8)
        self.set_text_color(50, 50, 50)
        for ri, row in enumerate(rows):
            fill = ri % 2 == 1
            if fill:
                self.set_fill_color(240, 244, 248)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 5.5, str(cell), border=1, fill=fill, align="C" if i > 0 else "L")
            self.ln()
        self.ln(2)


def generate():
    pdf = PDF()
    pdf.add_font("nanumgothic", "", FONT_PATH)
    pdf.add_font("nanumgothic", "B", FONT_PATH)
    pdf.set_auto_page_break(auto=True, margin=20)

    # ===== 표지 =====
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("nanumgothic", "B", 28)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 15, "OCR Template Pipeline", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("nanumgothic", size=14)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "한국어 서류 OCR 템플릿 기반 자동 추출 시스템", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("nanumgothic", size=11)
    pdf.cell(0, 8, "대상 문서: 기본직접지불금 지급대상자 등록신청서 (농업인용)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(30)
    pdf.set_font("nanumgothic", size=10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 7, "Capstone Project", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "2026.04", align="C", new_x="LMARGIN", new_y="NEXT")

    # ===== 1. 프로젝트 개요 =====
    pdf.add_page()
    pdf.section("1. 프로젝트 개요")
    pdf.body(
        "본 시스템은 한국 농업 보조금 신청서(기본직접지불금 지급대상자 등록신청서)의 "
        "필기/인쇄 내용을 자동으로 추출하는 OCR 파이프라인이다.\n\n"
        "수기 작성된 대량의 신청서를 일괄 처리하여 엑셀로 출력하되, "
        "악필 등으로 인식이 불확실한 항목은 관리자가 웹 UI에서 직접 검수할 수 있다."
    )

    pdf.subsection("핵심 기능")
    pdf.bullet("웹 기반 템플릿 편집기: PDF 위에 바운딩 박스를 그려 OCR 영역 지정")
    pdf.bullet("배치 OCR 파이프라인: 수백 건의 PDF를 GPU 배치로 일괄 처리")
    pdf.bullet("신뢰도 기반 자동/검수 분류: 임계점 미달 항목만 관리자 검수")
    pdf.bullet("웹 검수 UI: crop 이미지와 OCR 결과를 보면서 승인/수정")
    pdf.bullet("엑셀 출력: 4개 시트 (인적사항/가족관계/검수항목/원본결과)")
    pdf.bullet("개인정보 마스킹: 주민등록번호, 계좌번호 자동 마스킹")

    # ===== 2. 시스템 아키텍처 =====
    pdf.add_page()
    pdf.section("2. 시스템 아키텍처")
    pdf.body("전체 흐름은 4단계로 구성된다:")
    pdf.ln(2)
    pdf.body(
        "[1단계] 템플릿 편집기 (ocr_template_editor.html)\n"
        "  PDF를 열고 각 필드의 바운딩 박스를 마우스로 지정한다.\n"
        "  53개 프리셋 필드를 제공하며, JSON 템플릿으로 저장한다.\n\n"
        "[2단계] Crop + OCR 파이프라인 (run_pipeline.py)\n"
        "  템플릿 좌표로 PDF에서 필드를 crop하고,\n"
        "  ko-trocr 모델로 GPU 배치 추론을 실행한다.\n\n"
        "[3단계] 검증 + 분류 (validator.py)\n"
        "  필드타입별 정규식 검증과 신뢰도 기반 상태 분류를 수행한다.\n"
        "  결과를 엑셀 4시트로 출력한다.\n\n"
        "[4단계] 관리자 검수 (review_server.py)\n"
        "  검수 필요 항목을 웹 UI에서 확인/수정 후 엑셀을 재생성한다."
    )

    # ===== 3. 디렉토리 구조 =====
    pdf.section("3. 디렉토리 구조")
    pdf.table(
        ["경로", "역할", "라인수"],
        [
            ["template_editor/ocr_template_editor.html", "템플릿 편집기 (독립 HTML, 서버 불필요)", "970"],
            ["template_editor/app.py", "Flask 서버 (선택적, PDF 렌더링용)", "124"],
            ["template_editor/field_presets.py", "53개 프리셋 필드 정의", "91"],
            ["ocr_pipeline/run_pipeline.py", "메인 CLI, 배치 오케스트레이션", "208"],
            ["ocr_pipeline/crop_generator.py", "템플릿 기반 crop 이미지 생성", "116"],
            ["ocr_pipeline/ocr_engine.py", "ko-trocr 배치 OCR + checkbox 판정", "252"],
            ["ocr_pipeline/validator.py", "필드타입 검증 + 마스킹", "168"],
            ["ocr_pipeline/excel_writer.py", "엑셀 4시트 출력", "219"],
            ["ocr_pipeline/review_server.py", "Flask 검수 UI 서버", "138"],
            ["ocr_pipeline/templates/review.html", "관리자 검수 웹 UI", "283"],
            ["template/", "저장된 템플릿 JSON", "-"],
            ["input/", "입력 PDF 파일", "-"],
            ["output/", "출력 엑셀 파일", "-"],
            ["work/", "작업 디렉토리 (crop, JSONL 등)", "-"],
        ],
        [80, 80, 30],
    )

    # ===== 4. 하드웨어 요구사항 =====
    pdf.add_page()
    pdf.section("4. 하드웨어 요구사항 및 GPU 메모리")

    pdf.subsection("OCR 모델: ddobokki/ko-trocr")
    pdf.table(
        ["항목", "값"],
        [
            ["모델 아키텍처", "TrOCR (ViT encoder + KR-BERT decoder)"],
            ["파라미터 수", "213.7M"],
            ["라이선스", "Apache-2.0"],
            ["입력", "crop 이미지 (RGB)"],
            ["출력", "텍스트 + 신뢰도"],
        ],
        [60, 130],
    )

    pdf.subsection("GPU 메모리 사용량 (VRAM)")
    pdf.table(
        ["구성", "VRAM 사용량", "비고"],
        [
            ["모델 로드 (FP32)", "0.80 GB", "모델 가중치만"],
            ["모델 로드 (FP16)", "0.40 GB", "half precision"],
            ["추론 batch=32 (FP32)", "~1.2 GB", "가중치 + 활성화"],
            ["추론 batch=64 (FP32)", "~1.5 GB", "가중치 + 활성화"],
            ["추론 batch=128 (FP32)", "~2.0 GB", "대량 배치 처리"],
        ],
        [60, 40, 90],
    )
    pdf.body(
        "본 시스템은 NVIDIA A100 80GB 환경에서 개발/테스트되었다.\n"
        "모델 크기가 작아 (213.7M) 일반적인 GPU (4GB+ VRAM)에서도 충분히 동작한다.\n"
        "CUDA 미지원 환경에서는 CPU 모드로 자동 전환되나, 처리 속도가 크게 저하된다."
    )

    pdf.subsection("최소/권장 사양")
    pdf.table(
        ["항목", "최소 사양", "권장 사양"],
        [
            ["GPU", "GTX 1060 6GB", "RTX 3060 이상 / A100"],
            ["VRAM", "2 GB", "8 GB+"],
            ["RAM", "8 GB", "16 GB+"],
            ["Python", "3.10+", "3.10"],
            ["PyTorch", "2.0+", "2.10+ (CUDA 12)"],
            ["디스크", "2 GB (모델)", "5 GB+ (모델 + 작업)"],
        ],
        [40, 75, 75],
    )

    # ===== 5. 소프트웨어 의존성 =====
    pdf.section("5. 소프트웨어 의존성")
    pdf.table(
        ["패키지", "버전", "용도", "라이선스"],
        [
            ["torch", "2.10+", "딥러닝 프레임워크", "BSD-3"],
            ["transformers", "5.7+", "HuggingFace 모델 로딩", "Apache-2.0"],
            ["PyMuPDF (fitz)", "1.27+", "PDF 렌더링/이미지 변환", "AGPL-3.0"],
            ["Pillow", "12.1+", "이미지 처리", "HPND"],
            ["openpyxl", "3.1+", "엑셀 생성", "MIT"],
            ["opencv-python", "4.13+", "체크박스/서명 판정", "Apache-2.0"],
            ["Flask", "3.1+", "검수 UI 서버", "BSD-3"],
            ["tqdm", "4.0+", "진행률 표시", "MIT/MPL"],
            ["fpdf2", "2.8+", "PDF 문서 생성", "LGPL-3.0"],
        ],
        [40, 25, 70, 55],
    )

    # ===== 6. 필드 타입 =====
    pdf.add_page()
    pdf.section("6. 필드 타입 및 처리 방식")
    pdf.table(
        ["field_type", "처리 방식", "검증 규칙", "예시"],
        [
            ["korean_name", "ko-trocr OCR", "한글 2~5자, 숫자 포함시 오류", "홍길동"],
            ["resident_number", "ko-trocr OCR", "6-7자리 형식, 마스킹 저장", "800101-1******"],
            ["phone", "ko-trocr OCR", "전화번호 패턴 검사", "010-1234-5678"],
            ["account", "ko-trocr OCR", "숫자/은행명 혼합 허용", "농협 123-456"],
            ["address", "ko-trocr OCR", "5자 미만시 검수", "경기도 파주시..."],
            ["number_text", "ko-trocr OCR", "숫자/하이픈 허용", "123456789"],
            ["date", "ko-trocr OCR", "날짜 형식 정규화", "2026-04-29"],
            ["date_or_birth", "ko-trocr OCR", "6/8자리 허용", "1980-01-01"],
            ["relation", "ko-trocr OCR", "관계 사전 검증", "배우자"],
            ["text", "ko-trocr OCR", "최소 검증", "임의 문자열"],
            ["checkbox", "OpenCV 흑색비율", "true/false/unknown", "true"],
            ["signature", "픽셀 밀도 분석", "present/absent", "present"],
        ],
        [30, 35, 65, 60],
    )

    # ===== 7. 신뢰도 체계 =====
    pdf.section("7. 신뢰도 및 검수 체계")
    pdf.table(
        ["신뢰도 범위", "상태", "처리"],
        [
            [">= 0.80", "ok", "자동 승인"],
            ["0.50 ~ 0.80", "needs_review", "관리자 검수 필요"],
            ["< 0.50", "low_confidence", "관리자 검수 필수"],
        ],
        [50, 50, 90],
    )
    pdf.ln(2)
    pdf.body(
        "주민등록번호, 계좌번호는 신뢰도와 무관하게 항상 needs_review로 분류된다.\n"
        "체크박스는 이미지 내 흑색 픽셀 비율로 판정하며, 애매한 경우 unknown 처리된다."
    )

    pdf.subsection("상태 코드")
    pdf.table(
        ["status", "의미"],
        [
            ["ok", "정상 추출, 검증 통과"],
            ["needs_review", "관리자 검수 필요"],
            ["missing", "필수 필드인데 값 없음"],
            ["low_confidence", "신뢰도 50% 미만"],
            ["invalid_format", "형식 오류 (정규식 불일치)"],
            ["ocr_failed", "OCR 실패 (이미지 열기 실패 등)"],
            ["multiple_candidates", "후보 2개 이상, 점수 차이 작음"],
            ["unknown", "판정 불가"],
        ],
        [50, 140],
    )

    # ===== 8. 사용법 =====
    pdf.add_page()
    pdf.section("8. 사용법")

    pdf.subsection("Step 1: 템플릿 생성")
    pdf.body(
        "ocr_template_editor.html을 브라우저에서 열어 PDF를 로드한다.\n"
        "마우스 드래그로 각 필드의 바운딩 박스를 그리고,\n"
        "프리셋에서 field_key/type/group을 선택한다.\n"
        "완성된 템플릿을 JSON으로 저장한다."
    )

    pdf.subsection("Step 2: OCR 파이프라인 실행")
    pdf.body(
        "python run_pipeline.py \\\n"
        "  --template template/page1_template.json \\\n"
        "  --input input/ \\\n"
        "  --output output/result.xlsx \\\n"
        "  --device cuda:0 \\\n"
        "  --batch-size 32"
    )

    pdf.subsection("Step 3: 검수 UI")
    pdf.body(
        "python review_server.py --work-dir work\n\n"
        "브라우저에서 localhost:5001 접속.\n"
        "crop 이미지와 OCR 결과를 확인하고 승인/수정한다.\n"
        "키보드 단축키: Enter(승인+다음), Tab(다음), Esc(판독불가)"
    )

    pdf.subsection("Step 4: 엑셀 재생성")
    pdf.body(
        "검수 완료 후 웹 UI에서 '엑셀 재생성' 버튼을 클릭하면\n"
        "검수 결과가 반영된 최종 엑셀이 output/ 폴더에 생성된다."
    )

    pdf.subsection("CLI 옵션")
    pdf.table(
        ["옵션", "기본값", "설명"],
        [
            ["--template", "(필수)", "템플릿 JSON 경로"],
            ["--input", "(필수)", "입력 PDF 디렉토리"],
            ["--output", "output/result.xlsx", "출력 엑셀 경로"],
            ["--device", "cuda:0", "GPU 디바이스"],
            ["--batch-size", "32", "GPU 배치 크기"],
            ["--model", "ddobokki/ko-trocr", "OCR 모델"],
            ["--resume", "False", "이전 결과 이어서 처리"],
            ["--no-mask", "False", "개인정보 마스킹 비활성화"],
            ["--cleanup", "False", "처리 후 crop 이미지 삭제"],
        ],
        [35, 45, 110],
    )

    # ===== 9. 배치 처리 =====
    pdf.add_page()
    pdf.section("9. 배치 처리 전략")
    pdf.body(
        "대량 처리 시 다음과 같은 최적화가 적용된다:\n\n"
        "1. 모든 PDF의 모든 crop을 하나의 큐에 모아 GPU 배치 추론\n"
        "   (PDF별로 따로 처리하지 않음 -> GPU 활용도 극대화)\n\n"
        "2. batch_size 조절 가능 (기본 32, A100에서 128까지 가능)\n\n"
        "3. 중간 결과를 JSONL로 스트리밍 저장\n"
        "   (중단 후 --resume 옵션으로 이어서 처리)\n\n"
        "4. tqdm 진행률 표시\n\n"
        "5. 이미 처리된 request_id는 자동 스킵"
    )

    pdf.subsection("예상 처리 속도")
    pdf.table(
        ["GPU", "batch_size", "초당 crop 수", "100건 PDF (40필드/건) 예상"],
        [
            ["A100 80GB", "64", "~120", "~33초"],
            ["RTX 3060", "16", "~40", "~100초"],
            ["CPU only", "1", "~2", "~33분"],
        ],
        [40, 35, 45, 70],
    )

    # ===== 10. 개인정보 처리 =====
    pdf.section("10. 개인정보 처리")
    pdf.body(
        "본 시스템은 주민등록번호, 계좌번호, 주소, 전화번호 등 민감 정보를 처리한다.\n"
        "다음과 같은 보호 조치가 적용된다:\n\n"
        "1. 엑셀 저장 시 주민등록번호 뒷자리 마스킹 (800101-1******)\n"
        "2. 계좌번호 일부 마스킹\n"
        "3. raw_ocr_results 시트에만 원본 저장 (접근 제한 필요)\n"
        "4. --cleanup 옵션으로 처리 후 crop 이미지 자동 삭제\n"
        "5. --no-mask 옵션은 관리자 전용 (마스킹 해제)"
    )

    # 저장
    out = "/project/ahnailab/jys0207/capstone/docs/project_documentation.pdf"
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pdf.output(out)
    print(f"PDF 생성 완료: {out}")
    print(f"페이지 수: {pdf.page}")


if __name__ == "__main__":
    generate()
