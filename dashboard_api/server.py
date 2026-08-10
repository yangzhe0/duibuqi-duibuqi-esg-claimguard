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
    PROJECT_ROOT,
    evidence,
    export_csv,
    indicator_index,
    page_blocks,
    pdf_path,
    query_results,
    report_index,
    result_detail,
    summary,
)
from dashboard_api.reviews import ReviewStore
from dashboard_api.tasks import MAX_UPLOAD_BYTES, TaskManager
from dashboard_api.audit import audit_queue, audit_summary
from dashboard_api.preaudit import claim_graph, export_workpaper_csv, preaudit_issues, preaudit_summary
from dashboard_api.natural_gold import (
    export_manifest_csv,
    load_manifest,
    natural_gold_evaluation,
    natural_gold_summary,
    natural_gold_tasks,
    validate_annotation,
)
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
            if path == "/api/summary":
                return self._json(summary())
            if path == "/api/reports":
                query = params.get("search", "").lower()
                items = [item for item in report_index() if query in item["report_id"].lower()]
                return self._json({"items": items, "total": len(items)})
            if path == "/api/indicators":
                return self._json({"items": indicator_index(), "total": len(indicator_index())})
            if path == "/api/results":
                return self._json(query_results(params))
            if path == "/api/export/results.csv":
                return self._bytes(export_csv(params), "text/csv; charset=utf-8", "esg_extraction_results.csv")
            if path == "/api/export/results.json":
                body = json.dumps(query_results({**params, "offset": "0", "limit": "1000"})["items"], ensure_ascii=False, indent=2).encode("utf-8")
                return self._bytes(body, "application/json; charset=utf-8", "esg_extraction_results.json")
            if path == "/api/reviews":
                return self._json(
                    {
                        "items": self.review_store.list(params.get("report_id", ""), params.get("indicator_id", "")),
                        "metrics": self.review_store.metrics(),
                    }
                )
            if path == "/api/review-metrics":
                return self._json(self.review_store.metrics())
            if path == "/api/audit/summary":
                return self._json(audit_summary(self.review_store.list(), params.get("report_id", "")))
            if path == "/api/audit/queue":
                return self._json(
                    audit_queue(
                        self.review_store.list(),
                        params.get("report_id", ""),
                        int(params.get("limit", "65")),
                        params.get("include_reviewed", "false").lower() == "true",
                    )
                )
            if path == "/api/preaudit/summary":
                report_id = params.get("report_id", "")
                return self._json(preaudit_summary(self.review_store.issue_actions(report_id), report_id))
            if path == "/api/preaudit/issues":
                report_id = params.get("report_id", "")
                return self._json(
                    preaudit_issues(
                        self.review_store.issue_actions(report_id),
                        report_id,
                        params.get("include_closed", "false").lower() == "true",
                    )
                )
            if path == "/api/preaudit/graph":
                return self._json(claim_graph(params.get("report_id", "")))
            if path == "/api/preaudit/workpaper.csv":
                report_id = params.get("report_id", "")
                if not report_id:
                    return self._error(HTTPStatus.BAD_REQUEST, "report_id is required")
                body = export_workpaper_csv(self.review_store.issue_actions(report_id), report_id)
                return self._bytes(body, "text/csv; charset=utf-8", "esg_claimguard_workpaper.csv")
            if path == "/api/natural-gold/summary":
                return self._json(natural_gold_summary(self.review_store.natural_gold_annotations()))
            if path == "/api/natural-gold/tasks":
                return self._json(
                    natural_gold_tasks(
                        self.review_store.natural_gold_annotations(),
                        params.get("role", "annotator_a"),
                        params.get("status", "all"),
                    )
                )
            if path == "/api/natural-gold/evaluation":
                return self._json(natural_gold_evaluation(self.review_store.natural_gold_annotations()))
            if path == "/api/natural-gold/manifest.csv":
                return self._bytes(export_manifest_csv(), "text/csv; charset=utf-8", "natural_gold_v1_manifest.csv")
            if path == "/api/tasks":
                items = self.task_manager.list()
                return self._json({"items": items, "total": len(items)})
            if path.startswith("/api/tasks/"):
                task = self.task_manager.get(path.removeprefix("/api/tasks/"))
                return self._json(task) if task else self._error(HTTPStatus.NOT_FOUND, "task not found")
            if path.startswith("/api/result/"):
                parts = path.removeprefix("/api/result/").split("/", 1)
                if len(parts) != 2:
                    return self._error(HTTPStatus.BAD_REQUEST, "report_id and indicator_id are required")
                item = result_detail(*parts)
                return self._json(item) if item else self._error(HTTPStatus.NOT_FOUND, "result not found")
            if path.startswith("/api/pdf/"):
                report_id = path.removeprefix("/api/pdf/")
                target = pdf_path(report_id)
                return self._file(target, "application/pdf") if target else self._error(HTTPStatus.NOT_FOUND, "PDF not found")
            if path.startswith("/api/evidence/"):
                report_id = path.removeprefix("/api/evidence/")
                item = evidence(report_id, params.get("block_id", ""))
                return self._json(item) if item else self._error(HTTPStatus.NOT_FOUND, "evidence block not found")
            if path.startswith("/api/page-blocks/"):
                report_id = path.removeprefix("/api/page-blocks/")
                return self._json({"items": page_blocks(report_id, int(params.get("page_no", "1")))})
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
                return self._json(self.review_store.upsert(payload), HTTPStatus.CREATED)
            if parsed.path == "/api/preaudit/actions":
                payload = self._read_json()
                return self._json(self.review_store.upsert_issue_action(payload), HTTPStatus.CREATED)
            if parsed.path == "/api/natural-gold/annotations":
                payload = self._read_json()
                task_id = str(payload.get("task_id", "")).strip()
                task = next((item for item in load_manifest() if item["task_id"] == task_id), None)
                if not task:
                    raise ValueError("Natural-Gold task not found")
                existing = self.review_store.natural_gold_annotations(task_id)
                values = validate_annotation(payload, task, existing)
                return self._json(self.review_store.upsert_natural_gold_annotation(values), HTTPStatus.CREATED)
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
