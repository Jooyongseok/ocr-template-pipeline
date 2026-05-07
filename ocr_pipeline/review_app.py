"""통합 검수 웹 앱 -- 인라인 수정, 연관 필드 그룹, Active Learning 수집.

기존 review_server.py를 대체한다.
"""
import base64
import os
import re

from flask import Flask, jsonify, render_template, request, send_file

from .data_store import DataStore
from .active_learning import ActiveLearningCollector
from .field_dependency import get_group_fields, get_field_group
from .excel_writer import write_excel

SAFE_DOC_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")


def create_app(work_dir: str = "work", output_dir: str = "output") -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    store = DataStore(work_dir)
    collector = ActiveLearningCollector(work_dir)

    # ── 페이지 ──

    @app.route("/")
    def index():
        return render_template("review.html")

    # ── API: 문서 목록 ──

    @app.route("/api/documents")
    def api_documents():
        doc_ids = store.list_documents()
        docs = []
        for did in doc_ids:
            doc = store.get_document(did)
            if doc:
                docs.append({
                    "document_id": did,
                    "source_pdf": doc.get("source_pdf", ""),
                    "status": doc.get("document_status", "unknown"),
                    "review_count": doc.get("review_count", 0),
                    "total_fields": len(doc.get("fields", {})),
                    "dependency_warnings": doc.get("dependency_warnings", []),
                })
        return jsonify(docs)

    # ── API: 검수 대상 필드 (페이지네이션) ──

    @app.route("/api/review-items")
    def api_review_items():
        doc_id = request.args.get("doc_id")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))

        items = store.get_review_items(doc_id)
        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page

        return jsonify({
            "items": items[start:end],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_next": end < total,
        })

    # ── API: 문서 전체 필드 (검수 화면용) ──

    @app.route("/api/document/<doc_id>/fields")
    def api_document_fields(doc_id):
        if not SAFE_DOC_ID.match(doc_id):
            return jsonify({"error": "잘못된 document_id"}), 400

        doc = store.get_document(doc_id)
        if doc is None:
            return jsonify({"error": "문서 없음"}), 404

        fields = []
        for fk, field in doc.get("fields", {}).items():
            group = get_field_group(fk)
            fields.append({
                "field_key": fk,
                "label": field.get("label", fk),
                "field_type": field.get("field_type", "text"),
                "value": field.get("value", ""),
                "raw_text": field.get("raw_text", ""),
                "confidence": field.get("confidence", 0.0),
                "status": field.get("status", "ok"),
                "warning": field.get("warning"),
                "candidates": field.get("candidates", []),
                "bbox_norm": field.get("bbox_norm"),
                "crop_path": field.get("crop_path", ""),
                "edited": field.get("edited", False),
                "group_name": group["group_name"] if group else None,
                "group_fields": get_group_fields(fk),
                "required": field.get("required", False),
            })

        # 신뢰도 오름차순 (worst-first), 문제 필드 먼저
        fields.sort(key=lambda x: (
            0 if x["status"] not in ("ok", "unchecked") else 1,
            x["confidence"],
        ))

        return jsonify({
            "document_id": doc_id,
            "source_pdf": doc.get("source_pdf", ""),
            "document_status": doc.get("document_status", "unknown"),
            "review_count": doc.get("review_count", 0),
            "dependency_warnings": doc.get("dependency_warnings", []),
            "fields": fields,
        })

    # ── API: crop 이미지 (lazy-loading) ──

    @app.route("/api/crop/<doc_id>/<field_key>")
    def api_crop(doc_id, field_key):
        if not SAFE_DOC_ID.match(doc_id):
            return jsonify({"error": "잘못된 document_id"}), 400

        doc = store.get_document(doc_id)
        if doc is None:
            return jsonify({"error": "문서 없음"}), 404

        field = doc.get("fields", {}).get(field_key)
        if field is None:
            return jsonify({"error": "필드 없음"}), 404

        crop_path = field.get("crop_path", "")
        if not crop_path or not os.path.exists(crop_path):
            return jsonify({"error": "crop 이미지 없음"}), 404

        # 보안: crop_path가 work_dir 내부인지 확인
        abs_crop = os.path.abspath(crop_path)
        abs_work = os.path.abspath(work_dir)
        if not abs_crop.startswith(abs_work):
            return jsonify({"error": "접근 거부"}), 403

        return send_file(abs_crop, mimetype="image/png")

    # ── API: 페이지 이미지 ──

    @app.route("/api/page-image/<doc_id>/<int:page_num>")
    def api_page_image(doc_id, page_num):
        if not SAFE_DOC_ID.match(doc_id):
            return jsonify({"error": "잘못된 document_id"}), 400

        page_path = os.path.join(work_dir, "page_images", doc_id, f"page_{page_num:03d}.png")
        if not os.path.exists(page_path):
            return jsonify({"error": "페이지 이미지 없음"}), 404

        abs_page = os.path.abspath(page_path)
        abs_work = os.path.abspath(work_dir)
        if not abs_page.startswith(abs_work):
            return jsonify({"error": "접근 거부"}), 403

        return send_file(abs_page, mimetype="image/png")

    # ── API: 필드 수정 ──

    @app.route("/api/update", methods=["POST"])
    def api_update():
        data = request.get_json()
        if not data:
            return jsonify({"error": "요청 데이터 없음"}), 400

        doc_id = data.get("document_id", "")
        field_key = data.get("field_key", "")
        new_value = data.get("value", "")

        if not SAFE_DOC_ID.match(doc_id):
            return jsonify({"error": "잘못된 document_id"}), 400

        try:
            # 수정 전 원본 정보 (Active Learning용)
            doc_before = store.get_document(doc_id)
            field_before = doc_before.get("fields", {}).get(field_key, {}) if doc_before else {}
            original_text = field_before.get("raw_text", field_before.get("value", ""))
            original_confidence = field_before.get("confidence", 0.0)
            crop_path = field_before.get("crop_path", "")
            field_type = field_before.get("field_type", "text")

            # 값 저장
            updated_doc = store.save_field(doc_id, field_key, new_value)

            # Active Learning: 수정 데이터 수집
            al_result = {}
            if original_text != new_value and crop_path:
                al_result = collector.collect_correction(
                    crop_path=crop_path,
                    corrected_text=new_value,
                    field_type=field_type,
                    original_text=original_text,
                    original_confidence=original_confidence,
                    document_id=doc_id,
                    field_key=field_key,
                )

            return jsonify({
                "ok": True,
                "document_status": updated_doc.get("document_status"),
                "review_count": updated_doc.get("review_count"),
                "dependency_warnings": updated_doc.get("dependency_warnings", []),
                "active_learning": al_result,
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # ── API: 문서 건너뛰기 ──

    @app.route("/api/skip-document", methods=["POST"])
    def api_skip_document():
        data = request.get_json()
        doc_id = data.get("document_id", "")
        reason = data.get("reason", "skipped")

        if not SAFE_DOC_ID.match(doc_id):
            return jsonify({"error": "잘못된 document_id"}), 400

        doc = store.get_document(doc_id)
        if doc is None:
            return jsonify({"error": "문서 없음"}), 404

        doc["document_status"] = "skipped"
        doc["skip_reason"] = reason
        store._atomic_write(store._doc_path(doc_id), doc)

        return jsonify({"ok": True, "document_status": "skipped"})

    # ── API: 통계 ──

    @app.route("/api/stats")
    def api_stats():
        batch_stats = store.get_batch_stats()
        al_stats = collector.get_stats()
        return jsonify({
            **batch_stats,
            "active_learning": al_stats,
        })

    # ── API: 엑셀 내보내기 ──

    @app.route("/api/export-excel", methods=["POST"])
    def api_export_excel():
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "result_reviewed.xlsx")

        docs = []
        for did in store.list_documents():
            doc = store.get_document(did)
            if doc:
                docs.append(doc)

        if not docs:
            return jsonify({"error": "내보낼 문서 없음"}), 400

        write_excel(docs, output_path, mask_pii=True)
        return jsonify({"ok": True, "path": output_path})

    # ── API: Active Learning 통계 ──

    @app.route("/api/learning-stats")
    def api_learning_stats():
        stats = collector.get_stats()
        dist = collector.get_confidence_distribution()
        return jsonify({
            **stats,
            "confidence_distribution": dist,
            "trigger_count": collector.trigger_count,
            "ready_for_retrain": stats.get("total_corrections", 0) >= collector.trigger_count,
        })

    # ── API: Active Learning 데이터 내보내기 ──

    @app.route("/api/export-training-data", methods=["POST"])
    def api_export_training():
        path = collector.export_for_training()
        if not path:
            return jsonify({"error": "수집된 데이터 없음"}), 400
        return jsonify({"ok": True, "path": path, "stats": collector.get_stats()})

    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OCR 검수 웹 앱")
    parser.add_argument("--work-dir", default="work")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app(args.work_dir, args.output_dir)
    print(f"\n  검수 앱 실행: http://{args.host}:{args.port}")
    print(f"  작업 디렉토리: {args.work_dir}")
    print(f"  출력 디렉토리: {args.output_dir}\n")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
