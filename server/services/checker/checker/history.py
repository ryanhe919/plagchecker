import gzip
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from checker.schemas import AnalysisResult, HistoryItem, HistoryPage, JobManifest


class HistoryRepository:
    def __init__(self, database: Path):
        self.database = database
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    files_json TEXT NOT NULL,
                    reference_name TEXT,
                    pair_count INTEGER,
                    max_similarity REAL,
                    exact_image_count INTEGER,
                    result_gzip BLOB
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS analysis_history_recent ON analysis_history(created_at DESC, id DESC)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_manifest(self, manifest: JobManifest) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_history
                    (id, state, created_at, updated_at, files_json, reference_name)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state=excluded.state,
                    updated_at=excluded.updated_at,
                    files_json=excluded.files_json,
                    reference_name=excluded.reference_name
                """,
                (
                    manifest.id,
                    manifest.state,
                    manifest.created_at,
                    manifest.updated_at,
                    json.dumps(manifest.files, ensure_ascii=False),
                    manifest.reference_name,
                ),
            )

    def put_result(self, job_id: str, result: AnalysisResult) -> None:
        payload = gzip.compress(result.model_dump_json().encode("utf-8"), compresslevel=6)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_history SET
                    result_gzip=?, pair_count=?, max_similarity=?, exact_image_count=?
                WHERE id=?
                """,
                (
                    payload,
                    len(result.pairs),
                    max((pair.similarity for pair in result.pairs), default=0),
                    sum(pair.exact_image_count for pair in result.pairs),
                    job_id,
                ),
            )

    def has_result(self, job_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_gzip IS NOT NULL AS present FROM analysis_history WHERE id=?", (job_id,)
            ).fetchone()
        return bool(row and row["present"])

    def get_result(self, job_id: str) -> AnalysisResult:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_gzip FROM analysis_history WHERE id=?", (job_id,)
            ).fetchone()
        if row is None or row["result_gzip"] is None:
            raise FileNotFoundError(job_id)
        return AnalysisResult.model_validate_json(gzip.decompress(row["result_gzip"]))

    def list(self, limit: int = 20, cursor: str | None = None) -> HistoryPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须为 1–100")
        parameters: list[str | int] = []
        condition = ""
        if cursor:
            timestamp, separator, job_id = cursor.rpartition("|")
            if separator != "|" or not timestamp or not re.fullmatch(r"[0-9a-f]{32}", job_id):
                raise ValueError("历史记录游标无效")
            condition = "WHERE (created_at, id) < (?, ?)"
            parameters.extend((timestamp, job_id))
        parameters.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, state, created_at, updated_at, files_json, reference_name,
                       pair_count, max_similarity, exact_image_count
                FROM analysis_history {condition}
                ORDER BY created_at DESC, id DESC LIMIT ?
                """,
                parameters,
            ).fetchall()
        items = [
            HistoryItem(
                id=row["id"],
                state=row["state"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                files=json.loads(row["files_json"]),
                reference_name=row["reference_name"],
                pair_count=row["pair_count"],
                max_similarity=row["max_similarity"],
                exact_image_count=row["exact_image_count"],
            )
            for row in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = f"{last.created_at}|{last.id}"
        return HistoryPage(items=items, next_cursor=next_cursor)
