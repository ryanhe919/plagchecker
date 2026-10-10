import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from checker.compare import analyze
from checker.extract import parse_docx
from checker.extract_pdf import parse_pdf
from checker.jobs import JobStore
from checker.schemas import AnalysisResult, HistoryPage, JobStatus, Settings


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.job_store = JobStore(Path(os.getenv("CHECKER_JOBS_DIR", "/tmp/plagiarism-checker-jobs")))
    yield


app = FastAPI(title="标书查重 API", version="0.2.0", lifespan=lifespan)


def _settings(value: str) -> Settings:
    try:
        return Settings.model_validate(json.loads(value))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(422, f"参数无效：{exc}") from exc


def _uploads(files: list[UploadFile]) -> list[tuple[str, str, UploadFile]]:
    if not 2 <= len(files) <= 12:
        raise HTTPException(422, "请上传 2–12 个 DOCX 或 PDF 文件")
    result: list[tuple[str, str, UploadFile]] = []
    for index, upload in enumerate(files):
        name = upload.filename or f"标书 {index + 1}.docx"
        suffix = name.lower().rsplit(".", 1)[-1]
        if suffix not in {"docx", "pdf"}:
            raise HTTPException(422, f"{name} 不是 .docx 或 .pdf 文件")
        result.append((name, suffix, upload))
    return result


def _job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def _reference(upload: UploadFile | None) -> tuple[str, str, UploadFile] | None:
    if upload is None:
        return None
    name = upload.filename or "招标文件"
    suffix = name.lower().rsplit(".", 1)[-1]
    if suffix not in {"docx", "pdf"}:
        raise HTTPException(422, "招标文件必须是 .docx 或 .pdf")
    return name, suffix, upload


@app.get("/api/v1/checker/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/checker/analyses", response_model=AnalysisResult)
async def create_analysis(
    files: Annotated[list[UploadFile], File(description="2–12 个 DOCX/PDF 标书")],
    settings: Annotated[str, Form()] = "{}",
    reference: UploadFile | None = File(default=None),
) -> AnalysisResult:
    options = _settings(settings)
    parsed_reference = None
    reference_upload = _reference(reference)
    if reference_upload:
        name, suffix, upload = reference_upload
        try:
            if suffix == "pdf":
                parsed_reference = await run_in_threadpool(parse_pdf, upload.file, name, "reference", options.pdf_ocr_mode)
            else:
                parsed_reference = await run_in_threadpool(parse_docx, upload.file, name, "reference")
        except ValueError as exc:
            raise HTTPException(422, f"招标文件 {name}：{exc}") from exc
    parsed = []
    for index, (name, suffix, upload) in enumerate(_uploads(files)):
        try:
            if suffix == "pdf":
                parsed.append(await run_in_threadpool(parse_pdf, upload.file, name, str(index + 1), options.pdf_ocr_mode))
            else:
                parsed.append(await run_in_threadpool(parse_docx, upload.file, name, str(index + 1)))
        except ValueError as exc:
            raise HTTPException(422, f"{name}：{exc}") from exc
    try:
        return await run_in_threadpool(analyze, parsed, options, None, parsed_reference)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/checker/jobs", response_model=JobStatus, status_code=202)
async def create_job(
    request: Request,
    files: Annotated[list[UploadFile], File(description="2–12 个 DOCX/PDF 标书")],
    settings: Annotated[str, Form()] = "{}",
    reference: UploadFile | None = File(default=None),
) -> JobStatus:
    options = _settings(settings)
    uploads = [(name, suffix, upload.file) for name, suffix, upload in _uploads(files)]
    reference_upload = _reference(reference)
    reference_file = None
    if reference_upload:
        name, suffix, upload = reference_upload
        reference_file = (name, suffix, upload.file)
    return await run_in_threadpool(_job_store(request).create, uploads, options, reference_file)


@app.get("/api/v1/checker/history", response_model=HistoryPage)
def list_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> HistoryPage:
    try:
        return _job_store(request).list_history(limit, cursor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/checker/jobs/{job_id}", response_model=JobStatus)
def read_job(request: Request, job_id: str) -> JobStatus:
    try:
        return JobStatus.model_validate(_job_store(request).read(job_id).model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(404, "任务不存在或已过期") from exc


@app.get("/api/v1/checker/jobs/{job_id}/result", response_model=AnalysisResult)
def read_job_result(request: Request, job_id: str) -> AnalysisResult:
    store = _job_store(request)
    try:
        manifest = store.read(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "任务不存在或已过期") from exc
    if manifest.state != "completed":
        raise HTTPException(409, "任务尚未完成")
    try:
        return store.get_result(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(500, "任务结果文件缺失") from exc
