"""OCR 파이프라인 메인 CLI -- model_registry + data_store 통합"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from tqdm import tqdm

from .crop_generator import generate_all_crops
from .model_registry import ModelRegistry
from .validator import validate_result
from .excel_writer import write_excel
from .data_store import DataStore
from .field_dependency import check_dependencies


def merge_results(batch_results: list[dict], ocr_results: list[dict]) -> list[dict]:
    """배치 결과와 OCR 결과를 문서 단위로 병합한다."""
    result_map = {r["request_id"]: r for r in ocr_results}

    documents = []
    for batch in batch_results:
        doc_id = batch["doc_id"]
        fields = {}
        review_count = 0

        for req in batch["requests"]:
            rid = req["request_id"]
            ocr = result_map.get(rid)
            if not ocr:
                continue

            validated = validate_result(ocr, required=req.get("required", False))

            fields[req["field_key"]] = {
                "request_id": rid,
                "label": req["field_label"],
                "field_type": req["field_type"],
                "page": req["page"],
                "value": validated.get("value"),
                "raw_text": validated.get("text", ""),
                "confidence": validated.get("confidence", 0),
                "status": validated.get("status", ""),
                "warning": validated.get("warning"),
                "crop_path": req["crop_path"],
                "candidates": validated.get("candidates", []),
                "bbox_norm": req.get("bbox_norm"),
                "required": req.get("required", False),
            }

            if validated.get("status") not in ("ok", "unchecked"):
                review_count += 1

        source_pdf = ""
        if batch["requests"]:
            source_pdf = batch["requests"][0].get("metadata", {}).get("source_pdf", "")

        # 연관성 검증
        dep_warnings = check_dependencies(fields)
        dep_warning_list = [
            {"group": w.group_name, "field": w.field_key, "message": w.message}
            for w in dep_warnings
        ]

        doc_status = "ok" if review_count == 0 else "needs_review"
        documents.append({
            "document_id": doc_id,
            "template_id": batch["requests"][0]["template_id"] if batch["requests"] else "",
            "source_pdf": source_pdf,
            "page_scope": sorted(set(r["page"] for r in batch["requests"])),
            "fields": fields,
            "document_status": doc_status,
            "review_count": review_count,
            "dependency_warnings": dep_warning_list,
        })

    return documents


def save_ocr_results_jsonl(ocr_results: list[dict], work_dir: str):
    """OCR 결과 JSONL 저장 (중간 결과)"""
    out_dir = Path(work_dir) / "ocr_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "all_results.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in ocr_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(path)


def load_existing_results(work_dir: str) -> dict:
    """이미 처리된 결과가 있으면 로드 (이어서 처리용)"""
    path = Path(work_dir) / "ocr_results" / "all_results.jsonl"
    if not path.exists():
        return {}
    results = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                results[r["request_id"]] = r
    return results


def main():
    parser = argparse.ArgumentParser(description="OCR 파이프라인")
    parser.add_argument("--template", required=True, help="템플릿 JSON 경로")
    parser.add_argument("--input", required=True, help="입력 PDF 디렉토리")
    parser.add_argument("--output", default="output/result.xlsx", help="출력 엑셀 경로")
    parser.add_argument("--work-dir", default="work", help="작업 디렉토리")
    parser.add_argument("--device", default="cuda:0", help="GPU 디바이스")
    parser.add_argument("--batch-size", type=int, default=32, help="배치 크기")
    parser.add_argument("--model-config", default=None, help="모델 설정 YAML 경로")
    parser.add_argument("--model-id", default=None, help="사용할 모델 ID (config에서)")
    parser.add_argument("--no-mask", action="store_true", help="개인정보 마스킹 비활성화")
    parser.add_argument("--cleanup", action="store_true", help="완료 후 crop 이미지 삭제")
    parser.add_argument("--resume", action="store_true", help="이전 결과 이어서 처리")
    # 하위호환: --model 인자도 지원
    parser.add_argument("--model", default=None, help="(레거시) OCR 모델 이름/경로")
    args = parser.parse_args()

    print("=" * 60)
    print("  OCR 파이프라인 시작")
    print("=" * 60)
    start_time = time.time()

    # 1. Crop 생성
    print("\n[1/5] Crop 이미지 생성 중...")
    batch_results = generate_all_crops(args.template, args.input, args.work_dir)
    if not batch_results:
        print("처리할 PDF가 없습니다.")
        sys.exit(1)

    total_requests = sum(len(b["requests"]) for b in batch_results)
    print(f"  총 {len(batch_results)}개 문서, {total_requests}개 필드")

    # 2. 이전 결과 로드 (resume)
    existing = {}
    if args.resume:
        existing = load_existing_results(args.work_dir)
        if existing:
            print(f"\n[INFO] 이전 결과 {len(existing)}개 로드됨")

    # 3. OCR 실행 -- ModelRegistry 사용
    print("\n[2/5] OCR 추론 실행 중...")
    registry = ModelRegistry(args.model_config)

    # 모델 정보 표시
    model_id = args.model_id
    engine = registry.get_engine(model_id)
    info = engine.get_model_info()
    print(f"  모델: {info.get('source', 'unknown')}")
    print(f"  디바이스: {info.get('device', 'unknown')}")

    all_requests = []
    for batch in batch_results:
        for req in batch["requests"]:
            if req["request_id"] not in existing:
                all_requests.append(req)

    if all_requests:
        ocr_results = []
        batch_size = args.batch_size
        for i in tqdm(range(0, len(all_requests), batch_size), desc="  OCR 배치"):
            batch_req = all_requests[i:i + batch_size]
            batch_res = registry.process_requests(batch_req, model_id)
            ocr_results.extend(batch_res)

        for r in ocr_results:
            existing[r["request_id"]] = r
    else:
        print("  모든 필드가 이미 처리되었습니다.")

    all_ocr_results = list(existing.values())
    print(f"  총 {len(all_ocr_results)}개 OCR 결과")

    # 4. 결과 저장
    print("\n[3/5] 중간 결과 저장...")
    save_ocr_results_jsonl(all_ocr_results, args.work_dir)

    # 5. 병합 + 검증 + DataStore 저장
    print("\n[4/5] 결과 병합 + 검증 + 저장...")
    documents = merge_results(batch_results, all_ocr_results)

    store = DataStore(args.work_dir)
    for doc in documents:
        store.save_document(doc)

    total_review = sum(d["review_count"] for d in documents)
    total_fields = sum(len(d["fields"]) for d in documents)
    dep_total = sum(len(d.get("dependency_warnings", [])) for d in documents)
    print(f"  {len(documents)}개 문서, {total_fields}개 필드, {total_review}개 검수 필요")
    if dep_total > 0:
        print(f"  필드 연관성 경고: {dep_total}건")

    # 6. 엑셀 출력
    print("\n[5/5] 엑셀 출력...")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    write_excel(documents, args.output, mask_pii=not args.no_mask)

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"  완료! ({elapsed:.1f}초)")
    print(f"  엑셀: {args.output}")
    print(f"  검수 필요: {total_review}건")
    if total_review > 0:
        print(f"\n  검수 UI 실행:")
        print(f"    python -m ocr_pipeline.review_app --work-dir {args.work_dir}")
    print("=" * 60)

    # cleanup
    if args.cleanup:
        import shutil
        crop_dir = Path(args.work_dir) / "crops"
        if crop_dir.exists():
            shutil.rmtree(crop_dir)
            print("  crop 이미지 삭제 완료")


if __name__ == "__main__":
    main()
