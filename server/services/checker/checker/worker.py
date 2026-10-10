import logging
import os
import signal
import threading
from pathlib import Path

from checker.compare import analyze
from checker.extract import parse_docx
from checker.extract_pdf import parse_pdf
from checker.jobs import JobStore

logger = logging.getLogger(__name__)


class JobInterrupted(Exception):
    pass


def run_job(store: JobStore, job_id: str, stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    manifest = store.read(job_id)
    if store.result_exists(job_id):
        store.update(job_id, state="completed", phase="completed", completed=manifest.total, message="分析完成")
        store.clear_uploads(manifest)
        return
    store.update(job_id, state="running", phase="extracting", error=None, message="开始提取文件内容")
    parsed = []
    try:
        reference = None
        offset = 0
        if manifest.reference_upload:
            upload = manifest.reference_upload
            store.update(job_id, completed=0, message=f"正在提取招标文件 {upload.name}")

            def reference_progress(stage: str, page: int, total: int) -> None:
                if stop.is_set():
                    raise JobInterrupted
                fraction = (0.8 if stage == "text" else 0.2) * page / max(total, 1)
                if stage == "images":
                    fraction += 0.8
                store.update(job_id, completed=fraction, message=f"招标文件 {upload.name}：第 {page}/{total} 页")

            with (store.root / job_id / upload.stored_name).open("rb") as source:
                if upload.format == "pdf":
                    reference = parse_pdf(source, upload.name, "reference", manifest.settings.pdf_ocr_mode, reference_progress)
                else:
                    reference = parse_docx(source, upload.name, "reference")
            offset = 1
            store.update(job_id, completed=1, message="招标文件已提取，开始处理投标文件")

        for index, upload in enumerate(manifest.uploads):
            if stop.is_set():
                raise JobInterrupted
            store.update(job_id, completed=offset + index, message=f"正在提取 {upload.name}")

            def page_progress(stage: str, page: int, total: int) -> None:
                if stop.is_set():
                    raise JobInterrupted
                fraction = (0.8 if stage == "text" else 0.2) * page / max(total, 1)
                if stage == "images":
                    fraction += 0.8
                label = "识别文字" if stage == "text" else "检查图片"
                store.update(
                    job_id,
                    completed=offset + index + fraction,
                    message=f"{upload.name}：{label} {page}/{total} 页",
                )

            with (store.root / job_id / upload.stored_name).open("rb") as source:
                if upload.format == "pdf":
                    parsed.append(parse_pdf(source, upload.name, str(index + 1), manifest.settings.pdf_ocr_mode, page_progress))
                else:
                    parsed.append(parse_docx(source, upload.name, str(index + 1)))
            store.update(job_id, completed=offset + index + 1, message=f"已提取 {index + 1}/{len(manifest.uploads)} 份投标文件")

        store.update(job_id, phase="comparing", message="正在逐对比对文件")

        def pair_progress(completed: int, total: int) -> None:
            if stop.is_set():
                raise JobInterrupted
            store.update(
                job_id,
                completed=offset + len(manifest.uploads) + completed,
                message=f"已完成 {completed}/{total} 组文件比对",
            )

        result = analyze(parsed, manifest.settings, pair_progress, reference)
        store.put_result(job_id, result)
        store.update(job_id, state="completed", phase="completed", completed=manifest.total, message="分析完成")
        store.clear_uploads(manifest)
    except JobInterrupted:
        store.update(job_id, state="queued", phase="queued", message="后台服务重启后继续分析")
    except Exception as exc:
        if stop.is_set():
            # A desktop shutdown can also terminate a currently running OCR
            # subprocess. Keep its sources so the next worker can retry it.
            store.update(job_id, state="queued", phase="queued", message="后台服务重启后继续分析")
            return
        logger.exception("analysis_job_failed job_id=%s", job_id)
        error = str(exc) if isinstance(exc, ValueError) else "分析失败，请检查文件是否完整并重试"
        store.update(job_id, state="failed", phase="failed", message="分析失败", error=error)
        store.clear_uploads(manifest)


def main(stop: threading.Event | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    store = JobStore(Path(os.getenv("CHECKER_JOBS_DIR", "/tmp/plagiarism-checker-jobs")))
    stop = stop or threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        pending = store.pending()
        if not pending:
            store.cleanup()
            stop.wait(1)
            continue
        for job_id in pending:
            if stop.is_set():
                break
            run_job(store, job_id, stop)


if __name__ == "__main__":
    main()
