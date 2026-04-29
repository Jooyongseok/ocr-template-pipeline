"""OCR 파이프라인 메인 CLI"""
import argparse
import json
import sys
import time
from pathlib import Path

from tqdm import tqdm

from crop_generator import generate_all_crops
from ocr_engine import OCREngine
from validator import validate_result
from excel_writer import write_excel


def merge_results(batch_results: list[dict], ocr_results: list[dict]) -> list[dict]:
    """배치 결과와 OCR 결과를 문서 단위로 병합한다."""
    # request_id → ocr_result 매핑
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

            # 검증
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
            }

            if validated.get("status") not in ("ok", "unchecked"):
                review_count += 1

        source_pdf = ""
        if batch["requests"]:
            source_pdf = batch["requests"][0].get("metadata", {}).get("source_pdf", "")

        doc_status = "ok" if review_count == 0 else "needs_review"
        documents.append({
            "document_id": doc_id,
            "template_id": batch["requests"][0]["template_id"] if batch["requests"] else "",
            "source_pdf": source_pdf,
            "page_scope": sorted(set(r["page"] for r in batch["requests"])),
            "fields": fields,
            "document_status": doc_status,
            "review_count": review_count,
        })

    return documents


def save_final_json(documents: list[dict], work_dir: str):
    """문서별 최종 JSON 저장"""
    out_dir = Path(work_dir) / "final_json"
    out_dir.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        path = out_dir / f"{doc['document_id']}_extracted.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)


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
    parser.add_argument("--model", default="ddobokki/ko-trocr", help="OCR 모델")
    parser.add_argument("--no-mask", action="store_true", help="개인정보 마스킹 비활성화")
    parser.add_argument("--cleanup", action="store_true", help="완료 후 crop 이미지 삭제")
    parser.add_argument("--resume", action="store_true", help="이전 결과 이어서 처리")
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

    # 3. OCR 실행
    print("\n[2/5] OCR 추론 실행 중...")
    engine = OCREngine(model_name=args.model, device=args.device, batch_size=args.batch_size)

    all_requests = []
    for batch in batch_results:
        for req in batch["requests"]:
            if req["request_id"] not in existing:
                all_requests.append(req)

    if all_requests:
        # tqdm 진행률
        ocr_results = []
        for i in tqdm(range(0, len(all_requests), args.batch_size), desc="  OCR 배치"):
            batch_req = all_requests[i:i + args.batch_size]
            batch_res = engine.process_batch(batch_req)
            ocr_results.extend(batch_res)

        # 기존 결과와 합치기
        for r in ocr_results:
            existing[r["request_id"]] = r
    else:
        print("  모든 필드가 이미 처리되었습니다.")

    all_ocr_results = list(existing.values())
    print(f"  총 {len(all_ocr_results)}개 OCR 결과")

    # 4. 결과 저장
    print("\n[3/5] 중간 결과 저장...")
    save_ocr_results_jsonl(all_ocr_results, args.work_dir)

    # 5. 병합 + 검증
    print("\n[4/5] 결과 병합 + 검증...")
    documents = merge_results(batch_results, all_ocr_results)
    save_final_json(documents, args.work_dir)

    total_review = sum(d["review_count"] for d in documents)
    total_fields = sum(len(d["fields"]) for d in documents)
    print(f"  {len(documents)}개 문서, {total_fields}개 필드, {total_review}개 검수 필요")

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
        print(f"    python review_server.py --work-dir {args.work_dir}")
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
