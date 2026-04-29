"""OCR 템플릿 편집기 - Flask 서버"""
import os
import io
import json
import base64
from pathlib import Path

import fitz  # PyMuPDF
from flask import Flask, render_template, request, jsonify

from field_presets import FIELD_PRESETS, FIELD_TYPES, GROUPS, GROUP_COLORS, EXCEL_SHEET_MAP

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "template"
TEMPLATE_DIR.mkdir(exist_ok=True)

# 업로드된 이미지 캐시 (세션 단순화를 위해 메모리 저장)
_page_cache = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify(error="파일이 없습니다"), 400

    page_num = int(request.form.get("page", 1)) - 1
    data = f.read()
    filename = f.filename or "unknown"

    if filename.lower().endswith(".pdf"):
        doc = fitz.open(stream=data, filetype="pdf")
        if page_num >= len(doc):
            return jsonify(error=f"페이지 {page_num+1}이 없습니다 (총 {len(doc)}페이지)"), 400
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        total_pages = len(doc)
        doc.close()
    else:
        img_bytes = data
        total_pages = 1

    b64 = base64.b64encode(img_bytes).decode()
    _page_cache["current"] = img_bytes

    return jsonify(
        image=f"data:image/png;base64,{b64}",
        total_pages=total_pages,
        filename=filename,
    )


@app.route("/presets")
def presets():
    return jsonify(
        presets=FIELD_PRESETS,
        field_types=FIELD_TYPES,
        groups=GROUPS,
        group_colors=GROUP_COLORS,
        excel_sheet_map=EXCEL_SHEET_MAP,
    )


@app.route("/save-template", methods=["POST"])
def save_template():
    data = request.get_json()
    if not data:
        return jsonify(error="데이터가 없습니다"), 400

    template_id = data.get("template_id", "template_v1")
    filename = f"{template_id}.json"
    out_path = TEMPLATE_DIR / filename

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    return jsonify(saved=str(out_path))


@app.route("/templates")
def list_templates():
    files = sorted(TEMPLATE_DIR.glob("*.json"))
    result = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            meta = json.load(fp)
        result.append({
            "filename": f.name,
            "template_id": meta.get("template_id", f.stem),
            "document_name": meta.get("document_name", ""),
            "field_count": len(meta.get("fields", [])),
        })
    return jsonify(templates=result)


@app.route("/load-template", methods=["POST"])
def load_template():
    data = request.get_json()
    filename = data.get("filename")
    if not filename:
        return jsonify(error="파일명이 없습니다"), 400

    path = TEMPLATE_DIR / filename
    if not path.exists():
        return jsonify(error="파일을 찾을 수 없습니다"), 404

    with open(path, encoding="utf-8") as fp:
        template = json.load(fp)
    return jsonify(template=template)


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"OCR 템플릿 편집기: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
