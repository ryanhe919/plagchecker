import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from checker.history import HistoryRepository
from checker.schemas import AnalysisResult, HistoryPage, JobFile, JobManifest, JobStatus, Settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.history = HistoryRepository(root / "history.sqlite3")
        self._import_legacy()

    def _import_legacy(self) -> None:
        for folder in self.root.iterdir():
            manifest_file = folder / "manifest.json"
            if not folder.is_dir() or not manifest_file.is_file():
                continue
            try:
                manifest = JobManifest.model_validate_json(manifest_file.read_bytes())
                self.history.upsert_manifest(manifest)
                result_file = folder / "result.json"
                if result_file.is_file() and not self.history.has_result(manifest.id):
                    self.history.put_result(
                        manifest.id, AnalysisResult.model_validate_json(result_file.read_bytes())
                    )
            except (ValueError, OSError):
                continue

    def _folder(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise FileNotFoundError(job_id)
        return self.root / job_id

    def _write_json(self, path: Path, value: object) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def create(
        self,
        files: list[tuple[str, str, BinaryIO]],
        settings: Settings,
        reference: tuple[str, str, BinaryIO] | None = None,
    ) -> JobStatus:
        job_id = uuid4().hex
        folder = self._folder(job_id)
        folder.mkdir(mode=0o700)
        uploads: list[JobFile] = []
        reference_upload: JobFile | None = None
        try:
            for index, (name, suffix, source) in enumerate(files):
                stored_name = f"source-{index}.{suffix}"
                source.seek(0)
                with (folder / stored_name).open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                uploads.append(JobFile(name=name, stored_name=stored_name, format=suffix))
            if reference is not None:
                name, suffix, source = reference
                stored_name = f"reference.{suffix}"
                source.seek(0)
                with (folder / stored_name).open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                reference_upload = JobFile(name=name, stored_name=stored_name, format=suffix)
            count = len(uploads)
            timestamp = _now()
            manifest = JobManifest(
                id=job_id,
                state="queued",
                phase="queued",
                total=count + int(reference_upload is not None) + count * (count - 1) // 2,
                message="文件已接收，等待后台分析",
                created_at=timestamp,
                updated_at=timestamp,
                files=[item.name for item in uploads],
                reference_name=reference_upload.name if reference_upload else None,
                settings=settings,
                uploads=uploads,
                reference_upload=reference_upload,
            )
            self.save(manifest)
            return JobStatus.model_validate(manifest.model_dump())
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def save(self, manifest: JobManifest) -> None:
        self._write_json(self._folder(manifest.id) / "manifest.json", manifest.model_dump(mode="json"))
        self.history.upsert_manifest(manifest)

    def read(self, job_id: str) -> JobManifest:
        try:
            return JobManifest.model_validate_json((self._folder(job_id) / "manifest.json").read_bytes())
        except FileNotFoundError as exc:
            raise FileNotFoundError(job_id) from exc

    def update(self, job_id: str, **changes: object) -> JobManifest:
        manifest = self.read(job_id)
        updated = JobManifest.model_validate({**manifest.model_dump(), **changes, "updated_at": _now()})
        self.save(updated)
        return updated

    def pending(self) -> list[str]:
        jobs: list[tuple[str, str]] = []
        for folder in self.root.iterdir():
            if not folder.is_dir():
                continue
            try:
                manifest = self.read(folder.name)
            except (FileNotFoundError, ValueError):
                continue
            if manifest.state in {"queued", "running"}:
                jobs.append((manifest.created_at, manifest.id))
        return [job_id for _, job_id in sorted(jobs)]

    def put_result(self, job_id: str, result: AnalysisResult) -> None:
        self.history.put_result(job_id, result)

    def get_result(self, job_id: str) -> AnalysisResult:
        try:
            return self.history.get_result(job_id)
        except FileNotFoundError:
            return AnalysisResult.model_validate_json((self._folder(job_id) / "result.json").read_bytes())

    def result_exists(self, job_id: str) -> bool:
        return self.history.has_result(job_id) or (self._folder(job_id) / "result.json").is_file()

    def clear_uploads(self, manifest: JobManifest) -> None:
        for upload in manifest.uploads:
            (self._folder(manifest.id) / upload.stored_name).unlink(missing_ok=True)
        if manifest.reference_upload:
            (self._folder(manifest.id) / manifest.reference_upload.stored_name).unlink(missing_ok=True)

    def list_history(self, limit: int = 20, cursor: str | None = None) -> HistoryPage:
        return self.history.list(limit, cursor)

    def cleanup(self) -> None:
        for folder in self.root.iterdir():
            if not folder.is_dir():
                continue
            try:
                manifest = self.read(folder.name)
            except (FileNotFoundError, ValueError):
                if time.time() - folder.stat().st_mtime > 3600:
                    shutil.rmtree(folder, ignore_errors=True)
                continue
