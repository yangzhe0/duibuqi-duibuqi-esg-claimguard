from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get("ESG_REVIEW_DB", PROJECT_ROOT / "outputs/dashboard/reviews.sqlite3"))
VALID_LABELS = {"correct", "partial", "incorrect", "missed", "confirmed_missing"}
VALID_ISSUE_ACTIONS = {"open", "confirmed", "resolved", "accepted", "pending_material", "not_issue"}


class ReviewStore:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    report_id TEXT NOT NULL,
                    indicator_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    corrected_value TEXT NOT NULL DEFAULT '',
                    corrected_unit TEXT NOT NULL DEFAULT '',
                    corrected_evidence TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (report_id, indicator_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS issue_actions (
                    issue_id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS natural_gold_annotations (
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    disclosure TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    period TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT '',
                    value TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL DEFAULT '',
                    evidence_pages TEXT NOT NULL DEFAULT '',
                    evidence_text TEXT NOT NULL DEFAULT '',
                    confidence TEXT NOT NULL DEFAULT 'medium',
                    note TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, role)
                )
                """
            )

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = str(payload.get("label", ""))
        if label not in VALID_LABELS:
            raise ValueError(f"invalid label: {label}")
        report_id = str(payload.get("report_id", "")).strip()
        indicator_id = str(payload.get("indicator_id", "")).strip()
        if not report_id or not indicator_id:
            raise ValueError("report_id and indicator_id are required")
        values = {
            "report_id": report_id,
            "indicator_id": indicator_id,
            "label": label,
            "corrected_value": str(payload.get("corrected_value", "")),
            "corrected_unit": str(payload.get("corrected_unit", "")),
            "corrected_evidence": str(payload.get("corrected_evidence", "")),
            "note": str(payload.get("note", "")),
            "reviewer": str(payload.get("reviewer", "")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reviews VALUES (
                    :report_id, :indicator_id, :label, :corrected_value, :corrected_unit,
                    :corrected_evidence, :note, :reviewer, :updated_at
                )
                ON CONFLICT(report_id, indicator_id) DO UPDATE SET
                    label=excluded.label,
                    corrected_value=excluded.corrected_value,
                    corrected_unit=excluded.corrected_unit,
                    corrected_evidence=excluded.corrected_evidence,
                    note=excluded.note,
                    reviewer=excluded.reviewer,
                    updated_at=excluded.updated_at
                """,
                values,
            )
        return values

    def list(self, report_id: str = "", indicator_id: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if report_id:
            clauses.append("report_id = ?")
            params.append(report_id)
        if indicator_id:
            clauses.append("indicator_id = ?")
            params.append(indicator_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM reviews{where} ORDER BY updated_at DESC", params).fetchall()
        return [dict(row) for row in rows]

    def metrics(self) -> dict[str, Any]:
        rows = self.list()
        counts = {label: 0 for label in sorted(VALID_LABELS)}
        for row in rows:
            counts[row["label"]] += 1
        return {
            "reviewed_count": len(rows),
            "label_counts": counts,
            "precision": None,
            "recall": None,
            "f1": None,
            "metrics_status": "workflow_labels_only",
            "note": "普通复核记录不是冻结金标准，因此不计算 Precision、Recall 或 F1。",
        }

    def upsert_issue_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "")).strip()
        if action not in VALID_ISSUE_ACTIONS:
            raise ValueError(f"invalid issue action: {action}")
        issue_id = str(payload.get("issue_id", "")).strip()
        report_id = str(payload.get("report_id", "")).strip()
        if not issue_id or not report_id:
            raise ValueError("issue_id and report_id are required")
        values = {
            "issue_id": issue_id,
            "report_id": report_id,
            "action": action,
            "note": str(payload.get("note", "")),
            "reviewer": str(payload.get("reviewer", "")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO issue_actions VALUES (
                    :issue_id, :report_id, :action, :note, :reviewer, :updated_at
                )
                ON CONFLICT(issue_id) DO UPDATE SET
                    report_id=excluded.report_id,
                    action=excluded.action,
                    note=excluded.note,
                    reviewer=excluded.reviewer,
                    updated_at=excluded.updated_at
                """,
                values,
            )
        return values

    def issue_actions(self, report_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM issue_actions"
        params: list[str] = []
        if report_id:
            query += " WHERE report_id = ?"
            params.append(report_id)
        query += " ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_natural_gold_annotation(self, values: dict[str, Any]) -> dict[str, Any]:
        saved = {
            **values,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO natural_gold_annotations VALUES (
                    :task_id, :role, :disclosure, :subject, :period, :scope,
                    :value, :unit, :evidence_pages, :evidence_text, :confidence,
                    :note, :reviewer, :updated_at
                )
                ON CONFLICT(task_id, role) DO UPDATE SET
                    disclosure=excluded.disclosure,
                    subject=excluded.subject,
                    period=excluded.period,
                    scope=excluded.scope,
                    value=excluded.value,
                    unit=excluded.unit,
                    evidence_pages=excluded.evidence_pages,
                    evidence_text=excluded.evidence_text,
                    confidence=excluded.confidence,
                    note=excluded.note,
                    reviewer=excluded.reviewer,
                    updated_at=excluded.updated_at
                """,
                saved,
            )
        return saved

    def natural_gold_annotations(self, task_id: str = "", role: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if role:
            clauses.append("role = ?")
            params.append(role)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM natural_gold_annotations{where} ORDER BY updated_at DESC",
                params,
            ).fetchall()
        return [dict(row) for row in rows]
