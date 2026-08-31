from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dashboard_api.repository import (
    CURRENT_DATASET_ID,
    DEFAULT_DATASET_ID,
    PROJECT_ROOT,
    available_datasets,
    dataset_metadata,
    evidence,
    export_csv,
    indicator_index,
    page_blocks,
    pdf_path,
    quality_metrics,
    query_results,
    report_index,
    result_detail,
    summary,
)
from dashboard_api.reviews import ReviewStore
from dashboard_api.tasks import MAX_UPLOAD_BYTES, TaskManager
from dashboard_api.audit import audit_queue, audit_summary
from dashboard_api.preaudit import claim_graph, export_workpaper_csv, preaudit_issues, preaudit_summary
from dashboard_api.system import system_health


WEB_DIST = PROJECT_ROOT / "dashboard_web/dist"
MAX_BODY_BYTES = MAX_UPLOAD_BYTES


class DashboardHandler(BaseHTTPRequestHandler):
    review_store = ReviewStore()
    task_manager = TaskManager()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            if path == "/api/health":
                return self._json(system_health())
            if path == "/api/datasets":
                return self._json(available_datasets())
            if path == "/api/summary":
                return self._json(summary(self._dataset_id(params)))
            if path == "/api/quality":
                return self._json(quality_metrics(self._dataset_id(params)))
            if path == "/api/reports":
                dataset_id = self._dataset_id(params)
                query = params.get("search", "").lower()
                items = [item for item in report_index(dataset_id) if query in item["report_id"].lower()]
                return self._json({"items": items, "total": len(items), **dataset_metadata(dataset_id)})
            if path == "/api/indicators":
                dataset_id = self._dataset_id(params)
                items = indicator_index(dataset_id)
                return self._json({"items": items, "total": len(items), **dataset_metadata(dataset_id)})
            if path == "/api/results":
                if params.get("report_id") and not self._formal_report_exists(params["report_id"]):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(query_results(params))
            if path == "/api/export/results.csv":
                if params.get("report_id") and not self._formal_report_exists(params["report_id"]):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._bytes(export_csv(params), "text/csv; charset=utf-8", "esg_extraction_results.csv")
            if path == "/api/export/results.json":
                if params.get("report_id") and not self._formal_report_exists(params["report_id"]):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                body = json.dumps(query_results({**params, "offset": "0", "limit": "1000"})["items"], ensure_ascii=False, indent=2).encode("utf-8")
                return self._bytes(body, "application/json; charset=utf-8", "esg_extraction_results.json")
            if path == "/api/reviews":
                dataset_id = self._dataset_id(params)
                rows = self._review_rows(dataset_id, params.get("report_id", ""), params.get("indicator_id", ""))
                return self._json(
                    {
                        "items": rows,
                        "metrics": self._review_metrics(dataset_id),
                        **dataset_metadata(dataset_id),
                    }
                )
            if path == "/api/review-metrics":
                return self._json(self._review_metrics(self._dataset_id(params)))
            if path == "/api/audit/summary":
                dataset_id = self._dataset_id(params)
                if params.get("report_id") and not self._formal_report_exists(params["report_id"], dataset_id):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(
                    audit_summary(self._review_rows(dataset_id), params.get("report_id", ""), dataset_id)
                )
            if path == "/api/audit/queue":
                dataset_id = self._dataset_id(params)
                if params.get("report_id") and not self._formal_report_exists(params["report_id"], dataset_id):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(
                    audit_queue(
                        self._review_rows(dataset_id),
                        params.get("report_id", ""),
                        int(params.get("limit", "65")),
                        params.get("include_reviewed", "false").lower() == "true",
                        dataset_id,
                    )
                )
            if path == "/api/preaudit/summary":
                dataset_id = self._dataset_id(params)
                report_id = params.get("report_id", "")
                if report_id and not self._formal_report_exists(report_id, dataset_id):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(
                    preaudit_summary(self._issue_actions(dataset_id, report_id), report_id, dataset_id)
                )
            if path == "/api/preaudit/issues":
                dataset_id = self._dataset_id(params)
                report_id = params.get("report_id", "")
                if report_id and not self._formal_report_exists(report_id, dataset_id):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(
                    preaudit_issues(
                        self._issue_actions(dataset_id, report_id),
                        report_id,
                        params.get("include_closed", "false").lower() == "true",
                        dataset_id,
                    )
                )
            if path == "/api/preaudit/graph":
                if params.get("report_id") and not self._formal_report_exists(params["report_id"], self._dataset_id(params)):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(claim_graph(params.get("report_id", ""), self._dataset_id(params)))
            if path == "/api/preaudit/workpaper.csv":
                dataset_id = self._dataset_id(params)
                report_id = params.get("report_id", "")
                if not report_id:
                    return self._error(HTTPStatus.BAD_REQUEST, "report_id is required")
                if not self._formal_report_exists(report_id, dataset_id):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                body = export_workpaper_csv(self._issue_actions(dataset_id, report_id), report_id, dataset_id)
                return self._bytes(body, "text/csv; charset=utf-8", "esg_claimguard_workpaper.csv")
            if path == "/api/tasks":
                items = self.task_manager.list()
                return self._json({"items": items, "total": len(items)})
            if path.startswith("/api/tasks/"):
                parts = path.removeprefix("/api/tasks/").split("/")
                task_id = parts[0]
                if len(parts) == 2 and parts[1] == "summary":
                    payload = self.task_manager.summary(task_id)
                    return self._json(payload) if payload else self._error(HTTPStatus.NOT_FOUND, "completed task summary not found")
                if len(parts) == 2 and parts[1] == "results":
                    rows = self.task_manager.results(task_id)
                    return self._json({"items": rows, "total": len(rows), "task_id": task_id, "dataset_id": f"task:{task_id}", "scope": "single_upload"}) if rows is not None else self._error(HTTPStatus.NOT_FOUND, "completed task results not found")
                if len(parts) == 2 and parts[1] == "preaudit":
                    payload = self.task_manager.preaudit(task_id)
                    return self._json(payload) if payload else self._error(HTTPStatus.NOT_FOUND, "completed task preaudit not found")
                if len(parts) == 2 and parts[1] == "evidence":
                    payload = self.task_manager.evidence(task_id, params.get("block_id", ""))
                    return self._json(payload) if payload else self._error(HTTPStatus.NOT_FOUND, "task evidence block not found")
                if len(parts) == 2 and parts[1] == "pdf":
                    target = self.task_manager.pdf_path(task_id)
                    return self._file(target, "application/pdf") if target else self._error(HTTPStatus.NOT_FOUND, "task PDF not found")
                if len(parts) != 1:
                    return self._error(HTTPStatus.NOT_FOUND, "task endpoint not found")
                task = self.task_manager.get(task_id)
                return self._json(task) if task else self._error(HTTPStatus.NOT_FOUND, "task not found")
            if path.startswith("/api/result/"):
                parts = path.removeprefix("/api/result/").split("/", 1)
                if len(parts) != 2:
                    return self._error(HTTPStatus.BAD_REQUEST, "report_id and indicator_id are required")
                item = result_detail(*parts, self._dataset_id(params))
                return self._json(item) if item else self._error(HTTPStatus.NOT_FOUND, "result not found")
            if path.startswith("/api/pdf/"):
                report_id = path.removeprefix("/api/pdf/")
                target = pdf_path(report_id)
                return self._file(target, "application/pdf") if target else self._error(HTTPStatus.NOT_FOUND, "PDF not found")
            if path.startswith("/api/evidence/"):
                report_id = path.removeprefix("/api/evidence/")
                item = evidence(report_id, params.get("block_id", ""), self._dataset_id(params))
                return self._json(item) if item else self._error(HTTPStatus.NOT_FOUND, "evidence block not found")
            if path.startswith("/api/page-blocks/"):
                report_id = path.removeprefix("/api/page-blocks/")
                dataset_id = self._dataset_id(params)
                if not self._formal_report_exists(report_id, dataset_id):
                    return self._error(HTTPStatus.NOT_FOUND, "formal report not found")
                return self._json(
                    {
                        "items": page_blocks(report_id, int(params.get("page_no", "1")), dataset_id),
                        **dataset_metadata(dataset_id),
                    }
                )
            return self._serve_web(path)
        except (ValueError, TypeError) as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - last-resort API guard
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/reviews":
                payload = self._read_json()
                dataset_id = self._payload_dataset_id(payload)
                saved = self.review_store.upsert(payload)
                return self._json({**saved, **dataset_metadata(dataset_id)}, HTTPStatus.CREATED)
            if parsed.path == "/api/preaudit/actions":
                payload = self._read_json()
                dataset_id = self._payload_dataset_id(payload)
                saved = self.review_store.upsert_issue_action(payload)
                return self._json({**saved, **dataset_metadata(dataset_id)}, HTTPStatus.CREATED)
            if parsed.path == "/api/uploads":
                return self._upload()
            return self._error(HTTPStatus.NOT_FOUND, "endpoint not found")
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {exc}")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("invalid request body size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    @staticmethod
    def _dataset_id(params: dict[str, str]) -> str:
        return params.get("dataset_id", DEFAULT_DATASET_ID) or DEFAULT_DATASET_ID

    @staticmethod
    def _payload_dataset_id(payload: dict) -> str:
        dataset_id = str(payload.get("dataset_id", DEFAULT_DATASET_ID) or DEFAULT_DATASET_ID)
        dataset_metadata(dataset_id)
        if dataset_id != CURRENT_DATASET_ID:
            raise ValueError("optional datasets are read-only until review records have snapshot lineage")
        return dataset_id

    def _review_rows(self, dataset_id: str, report_id: str = "", indicator_id: str = "") -> list[dict]:
        dataset_metadata(dataset_id)
        if dataset_id != CURRENT_DATASET_ID:
            return []
        return self.review_store.list(report_id, indicator_id)

    def _review_metrics(self, dataset_id: str) -> dict:
        metadata = dataset_metadata(dataset_id)
        if dataset_id == CURRENT_DATASET_ID:
            return {**self.review_store.metrics(), **metadata}
        return {
            "reviewed_count": 0,
            "label_counts": {},
            "precision": None,
            "recall": None,
            "f1": None,
            "metrics_status": "snapshot_reviews_unavailable",
            "note": "该可选快照尚无带数据血缘的人工工作流记录，不复用 baseline 复核结果。",
            **metadata,
        }

    def _issue_actions(self, dataset_id: str, report_id: str = "") -> list[dict]:
        dataset_metadata(dataset_id)
        if dataset_id != CURRENT_DATASET_ID:
            return []
        return self.review_store.issue_actions(report_id)

    @staticmethod
    def _formal_report_exists(report_id: str, dataset_id: str = DEFAULT_DATASET_ID) -> bool:
        return any(item["report_id"] == report_id for item in report_index(dataset_id))

    def _upload(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        filename = Path(unquote(self.headers.get("X-Filename", "upload.pdf"))).name
        if length <= 0 or length > MAX_BODY_BYTES:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "PDF 文件大小必须在 1 字节到 200 MB 之间")
        task = self.task_manager.create_upload(filename, length, self.rfile)
        return self._json(task, HTTPStatus.CREATED)

    def _serve_web(self, path: str) -> None:
        if not WEB_DIST.is_dir():
            return self._error(HTTPStatus.NOT_FOUND, "frontend is not built; run npm run build in dashboard_web")
        relative = path.lstrip("/") or "index.html"
        target = (WEB_DIST / relative).resolve()
        if WEB_DIST.resolve() not in target.parents and target != WEB_DIST.resolve():
            return self._error(HTTPStatus.FORBIDDEN, "invalid path")
        if not target.is_file():
            target = WEB_DIST / "index.html"
        return self._file(target, mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    def _file(self, path: Path, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        no_store = content_type == "application/pdf" or content_type.startswith("text/html")
        self.send_header("Cache-Control", "no-store" if no_store else "public, max-age=3600")
        self.end_headers()
        with path.open("rb") as stream:
            shutil.copyfileobj(stream, self.wfile)

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, body: bytes, content_type: str, filename: str = "") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        return self._json({"error": message}, status)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dashboard] {self.address_string()} {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the ESG Evidence dashboard and API.")
    parser.add_argument("--host", default=os.environ.get("ESG_DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ESG_DASHBOARD_PORT", "8765")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"ESG Evidence dashboard: http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
