"""템플릿 기반 crop 이미지 + OCR 요청 JSONL 생성"""
import json
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


def generate_crops(template_path: str, pdf_path: str, work_dir: str, dpi: int = 150) -> dict:
    """
    하나의 PDF에서 템플릿 기반으로 crop 이미지를 생성하고 OCR 요청 JSONL을 만든다.

    Returns:
        {"batch_id": str, "requests": list[dict], "doc_id": str}
    """
    template = json.loads(Path(template_path).read_text("utf-8"))
    template_id = template["template_id"]
    pdf_path = Path(pdf_path)
    work = Path(work_dir)

    doc_id = pdf_path.stem
    # 문서 ID에서 특수문자 제거
    safe_doc_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in doc_id)[:60]

    doc = fitz.open(str(pdf_path))
    requests = []

    for field in template["fields"]:
        # 빈 key는 건너뛰기
        if not field.get("key", "").strip():
            continue
        page_num = field.get("page", 1)
        if page_num > len(doc):
            continue

        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        bbox = field["bbox_norm"]
        x = int(bbox[0] * pix.width)
        y = int(bbox[1] * pix.height)
        w = int(bbox[2] * pix.width)
        h = int(bbox[3] * pix.height)

        # 경계 보정
        x = max(0, x)
        y = max(0, y)
        w = min(w, pix.width - x)
        h = min(h, pix.height - y)

        if w < 2 or h < 2:
            continue

        crop_img = img.crop((x, y, x + w, y + h))

        # crop 저장
        crop_dir = work / "crops" / safe_doc_id / f"page_{page_num:03d}"
        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crop_dir / f"{field['key']}.png"
        crop_img.save(str(crop_path))

        # 페이지 이미지 저장 (한번만)
        page_img_dir = work / "page_images" / safe_doc_id
        page_img_dir.mkdir(parents=True, exist_ok=True)
        page_img_path = page_img_dir / f"page_{page_num:03d}.png"
        if not page_img_path.exists():
            img.save(str(page_img_path))

        request_id = f"{safe_doc_id}__page_{page_num:03d}__{field['key']}"
        requests.append({
            "request_id": request_id,
            "document_id": safe_doc_id,
            "template_id": template_id,
            "page": page_num,
            "field_key": field["key"],
            "field_label": field.get("label", field["key"]),
            "field_type": field.get("field_type", "text"),
            "crop_path": str(crop_path),
            "bbox_norm": bbox,
            "bbox_px": [x, y, w, h],
            "required": field.get("required", False),
            "metadata": {
                "row_index": None,
                "group": field.get("group", ""),
                "source_pdf": str(pdf_path),
            },
        })

    doc.close()

    # JSONL 저장
    req_dir = work / "ocr_requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    batch_id = f"batch_{safe_doc_id}"
    jsonl_path = req_dir / f"{batch_id}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for req in requests:
            f.write(json.dumps(req, ensure_ascii=False) + "\n")

    return {"batch_id": batch_id, "requests": requests, "doc_id": safe_doc_id}


def generate_all_crops(template_path: str, input_dir: str, work_dir: str, dpi: int = 150) -> list[dict]:
    """input_dir 내 모든 PDF에 대해 crop 생성. 반환: [{"batch_id", "requests", "doc_id"}, ...]"""
    input_path = Path(input_dir)
    pdfs = sorted(input_path.glob("*.pdf"))
    if not pdfs:
        print(f"[WARN] {input_dir}에 PDF 파일이 없습니다.")
        return []

    results = []
    for pdf in pdfs:
        print(f"  crop 생성: {pdf.name}")
        result = generate_crops(template_path, str(pdf), work_dir, dpi)
        results.append(result)
        print(f"    → {len(result['requests'])}개 필드")

    return results
