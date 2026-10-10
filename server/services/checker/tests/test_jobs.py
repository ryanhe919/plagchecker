import io
import sqlite3
import threading
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from checker.api import app
from checker.extract_pdf import parse_pdf
from checker.jobs import JobStore
from checker.schemas import AnalysisResult, JobManifest, Settings
from checker.worker import run_job


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def test_job_survives_client_recreation_and_result_is_restored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHECKER_JOBS_DIR", str(tmp_path))
    shared = "本项目建立分阶段质量验收机制，并对现场记录进行统一归档。"
    files = [("files", ("甲.docx", _docx(shared))), ("files", ("乙.docx", _docx(shared)))]
    with TestClient(app) as client:
        response = client.post("/api/v1/checker/jobs", files=files, data={"settings": "{}"})
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        assert client.get(f"/api/v1/checker/jobs/{job_id}").json()["state"] == "queued"
        assert client.get(f"/api/v1/checker/jobs/{job_id}/result").status_code == 409

    store = JobStore(tmp_path)
    store.update(job_id, state="running", phase="extracting")
    assert job_id in store.pending()
    run_job(store, job_id)

    with TestClient(app) as client:
        status = client.get(f"/api/v1/checker/jobs/{job_id}")
        result = client.get(f"/api/v1/checker/jobs/{job_id}/result")
    assert status.status_code == result.status_code == 200
    assert status.json()["state"] == "completed"
    assert status.json()["completed"] == status.json()["total"]
    assert result.json()["pairs"][0]["passages"]
    assert not (tmp_path / job_id / "source-0.docx").exists()


def test_pdf_beyond_500_pages_parses_without_page_cap() -> None:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    for page in range(501):
        document.drawString(48, 750, f"Page {page + 1} quality review record")
        document.showPage()
    document.save()
    parsed = parse_pdf(output.getvalue(), "long.pdf", "1", "off")
    assert parsed.pages == 501
    assert len(parsed.blocks) == 501


def test_interrupted_worker_requeues_job_without_losing_uploads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHECKER_JOBS_DIR", str(tmp_path))
    shared = "投标方案采用分阶段质量控制流程，并保留每个节点的复核记录。"
    files = [("files", ("甲.docx", _docx(shared))), ("files", ("乙.docx", _docx(shared)))]
    with TestClient(app) as client:
        job_id = client.post("/api/v1/checker/jobs", files=files, data={"settings": "{}"}).json()["id"]
    store = JobStore(tmp_path)
    stop = threading.Event()
    stop.set()
    run_job(store, job_id, stop)
    assert store.read(job_id).state == "queued"
    assert (tmp_path / job_id / "source-0.docx").exists()
    run_job(store, job_id)
    assert store.read(job_id).state == "completed"


def test_extraction_failure_during_shutdown_keeps_job_for_retry(tmp_path: Path, monkeypatch) -> None:
    store = JobStore(tmp_path)
    status = store.create(
        [("甲.docx", "docx", io.BytesIO(_docx("施工质量验收记录"))),
         ("乙.docx", "docx", io.BytesIO(_docx("施工质量验收记录")))],
        Settings(),
    )
    stop = threading.Event()

    def interrupted_extraction(*_args, **_kwargs):
        stop.set()
        raise ValueError("OCR child process was terminated during application shutdown")

    monkeypatch.setattr("checker.worker.parse_docx", interrupted_extraction)
    run_job(store, status.id, stop)
    assert store.read(status.id).state == "queued"
    assert (tmp_path / status.id / "source-0.docx").exists()
    assert (tmp_path / status.id / "source-1.docx").exists()


def test_tender_reference_and_history_are_persisted_in_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHECKER_JOBS_DIR", str(tmp_path))
    tender = "招标文件统一要求施工质量验收和记录归档"
    unique = "投标方另行采用自主研发的智能监测与风险预警方法"
    files = [("files", ("甲.docx", _docx(tender + unique))), ("files", ("乙.docx", _docx(tender + unique)))]
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/checker/jobs",
            files=[*files, ("reference", ("招标文件.docx", _docx(tender)))],
            data={"settings": "{}"},
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        assert response.json()["reference_name"] == "招标文件.docx"
    run_job(JobStore(tmp_path), job_id)
    with TestClient(app) as client:
        history = client.get("/api/v1/checker/history")
        result = client.get(f"/api/v1/checker/jobs/{job_id}/result")
    assert history.status_code == result.status_code == 200
    item = history.json()["items"][0]
    assert item["reference_name"] == "招标文件.docx"
    assert item["pair_count"] == 1
    body = result.json()
    assert body["reference"]["name"] == "招标文件.docx"
    assert body["pairs"][0]["passages"][0]["matched_chars"] == len(unique)
    assert body["documents"][0]["excluded_reference_chars"] >= len(tender)
    assert not (tmp_path / job_id / "reference.docx").exists()
    assert not (tmp_path / job_id / "result.json").exists()
    with sqlite3.connect(tmp_path / "history.sqlite3") as connection:
        row = connection.execute("SELECT length(result_gzip) FROM analysis_history WHERE id=?", (job_id,)).fetchone()
    assert row is not None and row[0] > 0


def test_history_pagination_and_legacy_result_import(tmp_path: Path) -> None:
    job_id = "a" * 32
    folder = tmp_path / job_id
    folder.mkdir()
    manifest = JobManifest(
        id=job_id,
        state="completed",
        phase="completed",
        total=3,
        completed=3,
        message="分析完成",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
        files=["旧甲.docx", "旧乙.docx"],
        settings=Settings(),
        uploads=[],
    )
    (folder / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (folder / "result.json").write_text(
        AnalysisResult(documents=[], pairs=[], settings=Settings()).model_dump_json(), encoding="utf-8"
    )
    store = JobStore(tmp_path)
    created = store.create(
        [("新甲.docx", "docx", io.BytesIO(_docx("新任务甲文件的质量验收内容。"))),
         ("新乙.docx", "docx", io.BytesIO(_docx("新任务乙文件的质量验收内容。")))],
        Settings(),
    )
    first = store.list_history(limit=1)
    second = store.list_history(limit=1, cursor=first.next_cursor)
    assert first.items[0].id == created.id
    assert second.items[0].id == job_id
    assert store.get_result(job_id).documents == []
    store.cleanup()
    assert store.read(job_id).state == "completed"
