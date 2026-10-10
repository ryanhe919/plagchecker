import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from checker.desktop import configure_runtime, parent_running
from checker.desktop_app import DesktopFiles, create_desktop_app


def make_web_dir(root: Path) -> Path:
    web = root / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>Desktop application</html>", encoding="utf-8")
    (web / "assets").mkdir()
    (web / "assets/app.js").write_text("console.log('desktop');", encoding="utf-8")
    return web


def wait_for(predicate, timeout: float = 20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Desktop child process did not become ready before the timeout")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        if os.name == "nt":
            # Windows venv python.exe can redirect to a different interpreter
            # PID. Kill its entire tree, including OCR, instead of the launcher.
            subprocess.run(
                [str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/taskkill.exe"),
                 "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, check=False, timeout=10,
            )
            process.wait(timeout=10)
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    target = io.BytesIO()
    document.save(target)
    return target.getvalue()


def pdf_bytes() -> bytes:
    target = io.BytesIO()
    document = canvas.Canvas(target)
    document.drawString(48, 750, "Quality inspection and phased construction plan")
    document.save()
    return target.getvalue()


def test_desktop_app_routes_origin_guard_and_static_path_isolation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHECKER_JOBS_DIR", str(tmp_path / "jobs"))
    web = make_web_dir(tmp_path)
    application = create_desktop_app(web, 8123)
    with TestClient(application, base_url="http://127.0.0.1:8123") as client:
        for page in ("/", "/new", "/history", "/jobs/" + "a" * 32):
            response = client.get(page)
            assert response.status_code == 200
            assert "Desktop application" in response.text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/v1/checker/missing").status_code == 404
        assert client.get("/%2e%2e/secret.txt").status_code == 404
        health = "/api/v1/checker/health"
        assert client.get(health).json() == {"status": "ok"}
        assert client.get(health, headers={"Origin": "http://127.0.0.1:8123"}).status_code == 200
        assert client.get(health, headers={"Origin": "https://external.example"}).status_code == 403
        assert client.post("/api/v1/checker/jobs", headers={"Origin": "null"}).status_code == 403
        assert client.get(health, headers={"Host": "external.example:8123"}).status_code == 403
        assert client.get(health, headers={"Host": "127.0.0.1:9999"}).status_code == 403


def test_desktop_app_accepts_windows_filesystem_separators(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHECKER_JOBS_DIR", str(tmp_path / "jobs"))
    original_get_path = DesktopFiles.get_path

    def windows_get_path(self, scope):
        return original_get_path(self, scope).replace("/", "\\")

    monkeypatch.setattr(DesktopFiles, "get_path", windows_get_path)
    application = create_desktop_app(make_web_dir(tmp_path), 8123)
    with TestClient(application, base_url="http://127.0.0.1:8123") as client:
        response = client.get("/jobs/" + "a" * 32)
        assert response.status_code == 200
        assert "Desktop application" in response.text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/v1/checker/missing").status_code == 404
        assert client.get("/%2e%2e/secret.txt").status_code == 404


def test_desktop_runtime_uses_explicit_ocr_and_persistent_data_paths(tmp_path: Path, monkeypatch) -> None:
    from pytesseract import pytesseract

    executable = tmp_path / "OCR 目录" / "tesseract.exe"
    executable.parent.mkdir()
    executable.touch()
    languages = tmp_path / "语言包"
    languages.mkdir()
    (languages / "eng.traineddata").touch()
    (languages / "chi_sim.traineddata").touch()
    monkeypatch.setenv("TESSERACT_CMD", str(executable))
    monkeypatch.setenv("TESSDATA_PREFIX", str(languages))
    monkeypatch.setattr(pytesseract, "tesseract_cmd", "tesseract")
    monkeypatch.setenv("CHECKER_JOBS_DIR", "unused")
    jobs = tmp_path / "本地历史" / "jobs"
    configure_runtime(jobs)
    assert jobs.is_dir()
    assert os.environ["CHECKER_JOBS_DIR"] == str(jobs.resolve())
    assert pytesseract.tesseract_cmd == str(executable.resolve())
    assert os.environ["TESSDATA_PREFIX"] == str(languages.resolve())
    (languages / "chi_sim.traineddata").unlink()
    with pytest.raises(ValueError, match="chi_sim.traineddata"):
        configure_runtime(jobs)


def test_desktop_processes_complete_job_and_retain_history_after_restart(tmp_path: Path) -> None:
    web = make_web_dir(tmp_path)
    ready = tmp_path / "runtime" / "ready.json"
    data_dir = tmp_path / "用户数据" / "jobs"
    binary = os.environ.get("CHECKER_TEST_BACKEND")
    common = [binary] if binary else [sys.executable, "-m", "checker.desktop"]
    child_environment = os.environ.copy()
    launch_token = uuid4().hex
    child_environment["CHECKER_LAUNCH_TOKEN"] = launch_token
    if binary:
        # The frozen children must work without finding an installed interpreter.
        child_environment["PATH"] = ""
        child_environment.pop("PYTHONHOME", None)
        child_environment.pop("PYTHONPATH", None)
    serve = [*common, "serve", "--data-dir", str(data_dir), "--web-dir", str(web),
             "--ready-file", str(ready), "--port", "0", "--parent-pid", str(os.getpid())]
    worker = [*common, "worker", "--data-dir", str(data_dir), "--parent-pid", str(os.getpid())]
    processes: list[subprocess.Popen] = []
    with (tmp_path / "backend.log").open("wb") as log:
        try:
            processes.append(subprocess.Popen(serve, stdout=log, stderr=log, env=child_environment))
            wait_for(lambda: ready.exists())
            endpoint = json.loads(ready.read_text(encoding="utf-8"))
            assert endpoint["host"] == "127.0.0.1"
            assert endpoint["launch_token"] == launch_token
            if os.name == "nt" and not binary:
                assert parent_running(endpoint["pid"])
            else:
                assert endpoint["pid"] == processes[0].pid
            assert 0 < endpoint["port"] < 65536
            with httpx.Client(base_url=f"http://127.0.0.1:{endpoint['port']}") as client:
                assert client.get("/api/v1/checker/health").json() == {"status": "ok"}
                assert client.get("/new").status_code == 200
                shared = "本项目采用分阶段质量验收方法，所有施工记录统一归档并定期复核。"
                response = client.post(
                    "/api/v1/checker/jobs",
                    files=[("files", ("甲.docx", docx_bytes(shared))),
                           ("files", ("乙.docx", docx_bytes(shared))),
                           ("files", ("文字.pdf", pdf_bytes()))],
                    data={"settings": "{}"},
                )
                assert response.status_code == 202, response.text
                job_id = response.json()["id"]
                processes.append(subprocess.Popen(worker, stdout=log, stderr=log, env=child_environment))
                def completed() -> bool:
                    status = client.get(f"/api/v1/checker/jobs/{job_id}").json()
                    assert status["state"] != "failed", status.get("error")
                    return status["state"] == "completed"

                wait_for(completed)
                result = client.get(f"/api/v1/checker/jobs/{job_id}/result")
                assert result.json()["pairs"][0]["passages"]
                assert len(result.json()["pairs"]) == 3
                native_pdf = next(document for document in result.json()["documents"] if document["format"] == "pdf")
                assert native_pdf["pages"] == 1 and native_pdf["chars"] > 20
            for process in processes:
                stop_process(process)
            if os.name != "nt":
                assert not ready.exists()
            ready.unlink(missing_ok=True)
            processes.append(subprocess.Popen(serve, stdout=log, stderr=log, env=child_environment))
            wait_for(lambda: ready.exists())
            endpoint = json.loads(ready.read_text(encoding="utf-8"))
            with httpx.Client(base_url=f"http://127.0.0.1:{endpoint['port']}") as client:
                history = client.get("/api/v1/checker/history").json()
                assert history["items"][0]["id"] == job_id
                assert client.get(f"/api/v1/checker/jobs/{job_id}/result").json()["pairs"][0]["passages"]
        finally:
            for process in processes:
                stop_process(process)


def test_parent_watchdog_exits_after_parent_is_gone(tmp_path: Path) -> None:
    assert parent_running(os.getpid())
    parent = subprocess.Popen([sys.executable, "-c", "pass"])
    parent.wait(timeout=10)
    assert not parent_running(parent.pid)
    with (tmp_path / "worker.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "checker.desktop", "worker", "--data-dir", str(tmp_path / "jobs"),
             "--parent-pid", str(parent.pid)],
            stdout=log,
            stderr=log,
            start_new_session=os.name != "nt",
        )
        try:
            process.wait(timeout=10)
            if os.name != "nt":
                assert process.returncode in (0, -signal.SIGTERM)
        finally:
            stop_process(process)
