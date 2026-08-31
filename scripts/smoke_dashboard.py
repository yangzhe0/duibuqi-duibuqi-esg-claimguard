#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = PROJECT_ROOT / "outputs/ai_contest/dashboard_smoke.json"
OUTPUT_MD = PROJECT_ROOT / "outputs/ai_contest/dashboard_smoke.md"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _request(base_url: str, path: str, expected_type: str = "") -> tuple[bytes, dict[str, Any]]:
    started = time.monotonic()
    with urlopen(base_url + path, timeout=30) as response:
        body = response.read()
        content_type = response.headers.get_content_type()
        record = {
            "path": path,
            "status": response.status,
            "content_type": content_type,
            "bytes": len(body),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }
    if record["status"] != 200:
        raise RuntimeError(f"{path} returned HTTP {record['status']}")
    if expected_type and content_type != expected_type:
        raise RuntimeError(f"{path} returned {content_type}, expected {expected_type}")
    if not body:
        raise RuntimeError(f"{path} returned an empty body")
    return body, record


def _json_request(base_url: str, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    body, record = _request(base_url, path, "application/json")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} did not return a JSON object")
    return payload, record


def _wait_until_ready(process: subprocess.Popen[str], base_url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"dashboard exited before becoming ready:\n{output[-2000:]}")
        try:
            _json_request(base_url, "/api/health")
            return
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            time.sleep(0.15)
    raise RuntimeError("dashboard did not become ready within 20 seconds")


def run_smoke(port: int = 0) -> dict[str, Any]:
    port = port or _free_port()
    base_url = f"http://127.0.0.1:{port}"
    command = ["bash", "scripts/run_dashboard.sh", "--host", "127.0.0.1", "--port", str(port)]
    isolated_state = tempfile.TemporaryDirectory(prefix="esg-dashboard-smoke-")
    state_root = Path(isolated_state.name)
    environment = {
        **os.environ,
        "ESG_TASK_ROOT": str(state_root / "tasks"),
        "ESG_REVIEW_DB": str(state_root / "reviews.sqlite3"),
    }
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
    )
    checks: list[dict[str, Any]] = []
    assertions: dict[str, Any] = {}
    try:
        _wait_until_ready(process, base_url)
        _, record = _request(base_url, "/", "text/html")
        checks.append(record)
        for path in (
            "/api/health",
            "/api/summary",
            "/api/reports",
            "/api/indicators",
            "/api/review-metrics",
            "/api/audit/summary",
            "/api/preaudit/summary",
            "/api/tasks",
        ):
            _, record = _json_request(base_url, path)
            checks.append(record)

        summary, _ = _json_request(base_url, "/api/summary")
        reports, _ = _json_request(base_url, "/api/reports")
        assertions = {
            "report_count_at_least_200": int(summary.get("report_count", 0)) >= 200,
            "indicator_count_is_65": int(summary.get("indicator_count", 0)) == 65,
            "result_count_matches_reports_times_indicators": int(summary.get("total_results", 0))
            == int(summary.get("report_count", 0)) * int(summary.get("indicator_count", 0)),
        }
        failed = [name for name, passed in assertions.items() if not passed]
        if failed:
            raise RuntimeError(f"dashboard contract assertions failed: {', '.join(failed)}")

        report_id = str(reports["items"][0]["report_id"])
        encoded_report = quote(report_id, safe="")
        results, record = _json_request(base_url, f"/api/results?report_id={encoded_report}&limit=65")
        checks.append(record)
        result = next((row for row in results["items"] if row.get("block_id")), results["items"][0])
        indicator_id = str(result["indicator_id"])
        block_id = str(result.get("block_id", ""))
        paths = (
            f"/api/result/{encoded_report}/{quote(indicator_id, safe='')}",
            f"/api/preaudit/issues?report_id={encoded_report}&include_closed=true",
            f"/api/preaudit/graph?report_id={encoded_report}",
        )
        for path in paths:
            _, record = _json_request(base_url, path)
            checks.append(record)
        if block_id:
            _, record = _json_request(
                base_url,
                f"/api/evidence/{encoded_report}?block_id={quote(block_id, safe='')}",
            )
            checks.append(record)
        pdf, record = _request(base_url, f"/api/pdf/{encoded_report}", "application/pdf")
        checks.append(record)
        if not pdf.startswith(b"%PDF-"):
            raise RuntimeError("PDF endpoint did not return a PDF signature")
        workpaper, record = _request(
            base_url,
            f"/api/preaudit/workpaper.csv?report_id={encoded_report}",
            "text/csv",
        )
        checks.append(record)
        if b"issue_id" not in workpaper[:300]:
            raise RuntimeError("workpaper export is missing its header")
    finally:
        process.terminate()
        try:
            server_output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            server_output, _ = process.communicate(timeout=5)
        isolated_state.cleanup()

    return {
        "status": "passed",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": f"conda:{Path(sys.prefix).name}",
        "server_command": command,
        "isolated_state": True,
        "base_url": base_url,
        "checks": checks,
        "assertions": assertions,
        "check_count": len(checks),
        "server_log_tail": server_output.splitlines()[-20:],
    }


def _write_report(payload: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    slowest = sorted(payload["checks"], key=lambda item: item["elapsed_ms"], reverse=True)[:5]
    rows = "\n".join(
        f"| `{item['path']}` | {item['status']} | {item['content_type']} | {item['bytes']} | {item['elapsed_ms']:.2f} |"
        for item in slowest
    )
    assertions = "\n".join(
        f"- {'通过' if passed else '失败'}：`{name}`" for name, passed in payload["assertions"].items()
    )
    markdown_path.write_text(
        f"""# ESG ClaimGuard 生产链路 Smoke Test

> 状态：**通过**。该检查启动真实生产后端，验证前端入口、核心 API、PDF 证据与工作底稿导出；不会写入业务处置数据。

## 验收摘要

- 检查时间：{payload['generated_at']}
- 检查端点：{payload['check_count']}
- Python：`{payload['python']}`
- 启动命令：`{' '.join(payload['server_command'])}`
- 状态隔离：临时任务目录与临时 SQLite（检查后已删除）
- 临时服务：`{payload['base_url']}`（检查后已关闭）

## 数据合同

{assertions}

## 响应最慢的 5 个端点

| 路径 | HTTP | 类型 | 字节 | 毫秒 |
|---|---:|---|---:|---:|
{rows}

这份结果只证明系统可启动、路由可访问和关键数据合同成立，不代表抽取准确率。
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the production dashboard on a temporary port and smoke-test critical routes.")
    parser.add_argument("--port", type=int, default=0, help="Temporary local port; 0 selects a free port.")
    parser.add_argument("--json", default=str(OUTPUT_JSON))
    parser.add_argument("--markdown", default=str(OUTPUT_MD))
    args = parser.parse_args()
    payload = run_smoke(args.port)
    _write_report(payload, Path(args.json), Path(args.markdown))
    print(json.dumps({"status": payload["status"], "checks": payload["check_count"], "report": args.markdown}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
