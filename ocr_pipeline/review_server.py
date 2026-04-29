"""검수 UI Flask 서버"""
import argparse
import json
import base64
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

WORK_DIR = None


def load_documents():
    """final_json에서 검수 필요 문서 로드"""
    final_dir = Path(WORK_DIR) / "final_json"
    if not final_dir.exists():
        return []
    docs = []
    for f in sorted(final_dir.glob("*_extracted.json")):
        with open(f, encoding="utf-8") as fp:
            doc = json.load(fp)
        docs.append(doc)
    return docs


def get_review_items():
    """검수 필요 항목만 추출"""
    docs = load_documents()
    items = []
    for doc in docs:
        for key, field in doc.get("fields", {}).items():
            if field.get("status") not in ("ok", "unchecked"):
                # crop 이미지를 base64로 인코딩
                crop_b64 = ""
                crop_path = field.get("crop_path", "")
                if crop_path and Path(crop_path).exists():
                    with open(crop_path, "rb") as img_f:
                        crop_b64 = base64.b64encode(img_f.read()).decode()

                items.append({
                    "document_id": doc["document_id"],
                    "source_pdf": doc.get("source_pdf", ""),
                    "field_key": key,
                    "field_label": field.get("label", key),
                    "field_type": field.get("field_type", "text"),
                    "value": field.get("value"),
                    "raw_text": field.get("raw_text", ""),
                    "confidence": field.get("confidence", 0),
                    "status": field.get("status", ""),
                    "warning": field.get("warning", ""),
                    "candidates": field.get("candidates", []),
                    "crop_image": crop_b64,
                    "request_id": field.get("request_id", ""),
                })
    return items


@app.route("/")
def index():
    return render_template("review.html")


@app.route("/api/items")
def api_items():
    return jsonify(items=get_review_items())


@app.route("/api/update", methods=["POST"])
def api_update():
    """검수 결과 업데이트"""
    data = request.get_json()
    doc_id = data.get("document_id")
    field_key = data.get("field_key")
    new_value = data.get("value")
    new_status = data.get("status", "ok")

    # final_json 업데이트
    json_path = Path(WORK_DIR) / "final_json" / f"{doc_id}_extracted.json"
    if not json_path.exists():
        return jsonify(error="문서를 찾을 수 없습니다"), 404

    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)

    if field_key in doc["fields"]:
        doc["fields"][field_key]["value"] = new_value
        doc["fields"][field_key]["status"] = new_status
        doc["fields"][field_key]["warning"] = None if new_status == "ok" else "manually_reviewed"

        # review_count 재계산
        doc["review_count"] = sum(
            1 for f in doc["fields"].values()
            if f.get("status") not in ("ok", "unchecked")
        )
        doc["document_status"] = "ok" if doc["review_count"] == 0 else "needs_review"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    return jsonify(ok=True, review_count=doc["review_count"])


@app.route("/api/regenerate-excel", methods=["POST"])
def api_regenerate():
    """검수 완료 후 엑셀 재생성"""
    from excel_writer import write_excel

    docs = load_documents()
    output_path = Path(WORK_DIR).parent / "output" / "result_reviewed.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_excel(docs, str(output_path))
    return jsonify(ok=True, path=str(output_path))


@app.route("/api/stats")
def api_stats():
    docs = load_documents()
    total_fields = sum(len(d["fields"]) for d in docs)
    review_fields = sum(d["review_count"] for d in docs)
    return jsonify(
        total_docs=len(docs),
        total_fields=total_fields,
        review_fields=review_fields,
        done_fields=total_fields - review_fields,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default="work", help="작업 디렉토리")
    parser.add_argument("--port", type=int, default=5001, help="포트")
    args = parser.parse_args()

    WORK_DIR = args.work_dir
    print(f"검수 UI: http://localhost:{args.port}")
    print(f"작업 디렉토리: {WORK_DIR}")
    app.run(host="0.0.0.0", port=args.port, debug=True)
