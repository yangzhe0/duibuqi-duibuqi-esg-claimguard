from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from dashboard_api import repository
from dashboard_api.model_runtime import QWEN_ALIAS, qwen_runtime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = Path(os.environ.get("ESG_TASK_ROOT", PROJECT_ROOT / "outputs/dashboard/tasks"))
MINERU_BIN = Path(os.environ.get("ESG_MINERU_BIN", shutil.which("mineru") or "mineru"))
OLLAMA_URL = os.environ.get("ESG_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
PIPELINE_PROFILE = os.environ.get("ESG_PIPELINE_PROFILE", "claimguard").strip().lower()
if PIPELINE_PROFILE not in {"claimguard", "legacy"}:
    raise ValueError("ESG_PIPELINE_PROFILE must be claimguard or legacy")
MINERU_BACKEND = os.environ.get("ESG_MINERU_BACKEND", "vlm-engine" if PIPELINE_PROFILE == "claimguard" else "pipeline")
LLM_API = os.environ.get("ESG_LLM_API", "openai" if PIPELINE_PROFILE == "claimguard" else "ollama")
if LLM_API not in {"openai", "ollama"}:
    raise ValueError("ESG_LLM_API must be openai or ollama")
MODEL = os.environ.get("ESG_MODEL", QWEN_ALIAS if PIPELINE_PROFILE == "claimguard" else "qwen3:30b")
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
TERMINAL_STATES = {"completed", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def report_metadata(filename: str, sha256: str) -> dict[str, str]:
    stem = Path(filename).stem.strip()
    parts = stem.split("_")
    year_match = re.search(r"(?:19|20)\d{2}", stem)
    if "可持续" in stem:
        report_type = "可持续发展报告"
    elif "社会责任" in stem:
        report_type = "社会责任报告"
    else:
        report_type = "ESG报告"
    return {
        "id": f"upload-{sha256[:16]}",
        "stock_code": parts[0] if parts and re.fullmatch(r"\d{5,6}", parts[0]) else "",
        "company": parts[1] if len(parts) > 1 else stem,
        "year": year_match.group(0) if year_match else "",
        "report_type": report_type,
        "title": stem,
    }


class TaskManager:
    def __init__(self, task_root: Path = TASK_ROOT) -> None:
        self.task_root = task_root
        self.task_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="esg-pipeline")
        self._mark_interrupted_tasks()

    def create_upload(self, filename: str, length: int, source: BinaryIO) -> dict:
        filename = self._validate_filename(filename)
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ValueError("PDF 文件大小必须在 1 字节到 200 MB 之间")
        task_id = uuid.uuid4().hex
        task_dir = self.task_root / task_id
        task_dir.mkdir(parents=True)
        staged = task_dir / "upload.pdf"
        digest = hashlib.sha256()
        remaining = length
        with staged.open("wb") as stream:
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("上传内容不完整")
                stream.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        with staged.open("rb") as stream:
            signature = stream.read(5)
        if signature != b"%PDF-":
            staged.unlink(missing_ok=True)
            raise ValueError("文件内容不是有效的 PDF")
        sha256 = digest.hexdigest()
        report_id = Path(filename).stem
        task = {
            "task_id": task_id,
            "report_id": report_id,
            "filename": filename,
            "sha256": sha256,
            "size": length,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "message": "已创建任务，等待处理",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "error": "",
        }
        self._write_task(task)
        self._executor.submit(self._run, task_id)
        return task

    def get(self, task_id: str) -> dict | None:
        if not re.fullmatch(r"[0-9a-f]{32}", task_id):
            return None
        path = self.task_root / task_id / "task.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def list(self, limit: int = 20) -> list[dict]:
        tasks = []
        for path in self.task_root.glob("*/task.json"):
            try:
                tasks.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]

    def _run(self, task_id: str) -> None:
        task = self.get(task_id)
        if not task:
            return
        try:
            task_dir = self.task_root / task_id
            staged = task_dir / "upload.pdf"
            raw_pdf = self._register_pdf(task, staged)
            task = self._update(task, "running", "mineru", 15, "正在执行 MinerU 版面解析")
            parsed_json = self._parse_pdf(task, raw_pdf, task_dir)
            task = self._update(task, "running", "extracting", 65, "文档解析模型已释放，正在启动 Qwen3.6 并执行 ESG-65 抽取")
            extraction_dir = task_dir / "extraction"
            self._extract(parsed_json, extraction_dir, task_dir / "extraction.log")
            self._update(task, "completed", "completed", 100, "解析、抽取和任务结果已生成")
        except Exception as exc:  # task error must be persisted for the browser
            self._update(task, "failed", "failed", task.get("progress", 0), "处理失败", str(exc))

    def _register_pdf(self, task: dict, staged: Path) -> Path:
        metadata = {
            **report_metadata(task["filename"], task["sha256"]),
            "task_id": task["task_id"],
            "source": "user_upload",
            "original_pdf_filename": task["filename"],
            "local_path": "upload.pdf",
            "file_sha256": task["sha256"],
            "file_size_bytes": task["size"],
            "created_at": task["created_at"],
        }
        self._write_json(self.task_root / task["task_id"] / "report_metadata.json", metadata)
        self._update(task, "running", "registered", 8, "PDF 已校验并登记到隔离任务目录")
        return staged

    def _parse_pdf(self, task: dict, raw_pdf: Path, task_dir: Path) -> Path:
        report_id = task["report_id"]
        output = task_dir / "mineru"
        log_path = task_dir / "mineru.log"
        mineru_bin_dir = str(MINERU_BIN.parent)
        current_path = os.environ.get("PATH", "")
        env = {
            **os.environ,
            "MINERU_MODEL_SOURCE": os.environ.get("MINERU_MODEL_SOURCE", "modelscope"),
            "PATH": mineru_bin_dir + (os.pathsep + current_path if current_path else ""),
        }
        command = [str(MINERU_BIN), "-p", str(raw_pdf), "-o", str(output), "-b", MINERU_BACKEND]
        if MINERU_BACKEND == "pipeline":
            command.extend(["-l", "ch"])
        self._run_command(command, log_path, env)
        matches = list(output.rglob("*content_list_v2.json"))
        if len(matches) != 1:
            raise RuntimeError(f"MinerU 输出异常：找到 {len(matches)} 个 content_list_v2.json")
        source_dir = matches[0].parent
        target_dir = task_dir / "parsed" / report_id
        if target_dir.exists():
            raise RuntimeError(f"解析目录已存在但缺少目标 JSON：{target_dir}")
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = target_dir.parent / f".{report_id}.{task['task_id']}.tmp"
        shutil.copytree(source_dir, temp_dir)
        for path in list(temp_dir.iterdir()):
            if path.name.startswith(raw_pdf.stem):
                path.rename(temp_dir / (report_id + path.name[len(raw_pdf.stem) :]))
        temp_dir.replace(target_dir)
        parsed = target_dir / f"{report_id}_content_list_v2.json"
        if not parsed.is_file():
            raise RuntimeError("规范化后的 MinerU JSON 不存在")
        return parsed

    def _extract(self, parsed_json: Path, output: Path, log_path: Path) -> None:
        if LLM_API == "openai":
            with qwen_runtime(log_path.parent / "qwen_runtime.log") as inference_url:
                self._run_extraction_command(parsed_json, output, log_path, inference_url)
        elif LLM_API == "ollama":
            self._run_extraction_command(parsed_json, output, log_path, OLLAMA_URL)
        else:
            raise RuntimeError(f"不支持的 LLM API：{LLM_API}")
        summary_path = output / "run_summary.json"
        if not (output / "extraction_results.csv").is_file() or not summary_path.is_file():
            raise RuntimeError("Qwen3 抽取未生成完整结果")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if int(summary.get("llm_error_count", 0)):
            raise RuntimeError(f"Qwen3 抽取包含 {summary['llm_error_count']} 个模型调用错误")

    def _run_extraction_command(self, parsed_json: Path, output: Path, log_path: Path, inference_url: str) -> None:
        command = [
            sys.executable,
            str(PROJECT_ROOT / "scripts/esg_system.py"),
            "--input-json",
            str(parsed_json),
            "--out-dir",
            str(output),
            "--model",
            MODEL,
            "--ollama-url",
            inference_url,
            "--llm-api",
            LLM_API,
            "--resume",
        ]
        self._run_command(command, log_path, os.environ.copy())

    @staticmethod
    def _run_command(command: list[str], log_path: Path, env: dict[str, str]) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
        if completed.returncode:
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
            raise RuntimeError(f"命令执行失败（退出码 {completed.returncode}）：{tail}")

    def summary(self, task_id: str) -> dict | None:
        task = self._completed_task(task_id)
        if not task:
            return None
        rows = self.results(task_id)
        assert rows is not None
        status = {name: sum(row.get("status") == name for row in rows) for name in ("found", "missing", "error")}
        return {
            "task_id": task_id,
            "dataset_id": f"task:{task_id}",
            "scope": "single_upload",
            "report_id": task["report_id"],
            "total_results": len(rows),
            "found_count": status["found"],
            "missing_count": status["missing"],
            "error_count": status["error"],
            "completed_at": task.get("updated_at", ""),
        }

    def results(self, task_id: str) -> list[dict] | None:
        task = self._completed_task(task_id)
        if not task:
            return None
        path = self.task_root / task_id / "extraction/extraction_results.csv"
        if not path.is_file():
            return None
        import csv

        with path.open(encoding="utf-8-sig", newline="") as stream:
            return [
                {**row, "task_id": task_id, "dataset_id": f"task:{task_id}", "dataset_scope": "single_upload"}
                for row in csv.DictReader(stream)
            ]

    def preaudit(self, task_id: str) -> dict | None:
        task = self._completed_task(task_id)
        rows = self.results(task_id)
        if not task or rows is None:
            return None
        issues = []
        for row in rows:
            issue_type = ""
            severity = "attention"
            finding = ""
            if row.get("status") == "error":
                issue_type, severity, finding = "pipeline_error", "blocking", "该指标处理失败，需要重新处理或人工检查。"
            elif row.get("status") == "found" and not (row.get("evidence_quote") and row.get("block_id")):
                issue_type, severity, finding = "evidence_integrity", "blocking", "结构化声明缺少可回溯原文证据。"
            elif row.get("status") == "found" and row.get("indicator_type") == "quantitative" and not (row.get("value") and row.get("unit")):
                issue_type, severity, finding = "field_completeness", "important", "定量声明缺少数值或单位。"
            elif row.get("status") == "missing":
                issue_type, severity, finding = "disclosure_gap", "attention", "当前候选证据不足；missing 不等同于违规或人工真值。"
            if issue_type:
                issues.append({
                    "issue_id": f"{task_id}:{row.get('indicator_id', '')}:{issue_type}",
                    "task_id": task_id,
                    "report_id": task["report_id"],
                    "indicator_id": row.get("indicator_id", ""),
                    "indicator_name": row.get("indicator_name", ""),
                    "issue_type": issue_type,
                    "severity": severity,
                    "finding": finding,
                    "evidence_quote": row.get("evidence_quote", ""),
                    "page_no": row.get("page_no", ""),
                    "block_id": row.get("block_id", ""),
                })
        return {
            "task_id": task_id,
            "dataset_id": f"task:{task_id}",
            "scope": "single_upload",
            "report_id": task["report_id"],
            "items": issues,
            "total": len(issues),
        }

    def evidence(self, task_id: str, block_id: str) -> dict | None:
        task = self._completed_task(task_id)
        if not task:
            return None
        match = re.fullmatch(r".+:p(\d+):b(\d+)", block_id)
        if not match:
            return None
        page_no, block_index = map(int, match.groups())
        path = self.task_root / task_id / "parsed" / task["report_id"] / f"{task['report_id']}_content_list_v2.json"
        if not path.is_file():
            return None
        pages = json.loads(path.read_text(encoding="utf-8"))
        if page_no < 1 or page_no > len(pages) or block_index < 0 or block_index >= len(pages[page_no - 1]):
            return None
        block = pages[page_no - 1][block_index]
        return {
            "task_id": task_id,
            "dataset_id": f"task:{task_id}",
            "scope": "single_upload",
            "report_id": task["report_id"],
            "block_id": block_id,
            "page_no": page_no,
            "block_index": block_index,
            "block_type": block.get("type", ""),
            "bbox": block.get("bbox", []),
            "coordinate_space": [0, 0, 1000, 1000],
            "text": repository._block_text(block),
        }

    def pdf_path(self, task_id: str) -> Path | None:
        task = self._completed_task(task_id)
        if not task:
            return None
        path = self.task_root / task_id / "upload.pdf"
        return path if path.is_file() else None

    def _completed_task(self, task_id: str) -> dict | None:
        task = self.get(task_id)
        return task if task and task.get("status") == "completed" else None

    def _update(self, task: dict, status: str, stage: str, progress: int, message: str, error: str = "") -> dict:
        updated = {**task, "status": status, "stage": stage, "progress": progress, "message": message, "error": error, "updated_at": utc_now()}
        self._write_task(updated)
        return updated

    def _write_task(self, task: dict) -> None:
        path = self.task_root / task["task_id"] / "task.json"
        temporary = path.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)

    def _write_json(self, path: Path, payload: dict) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)

    def _mark_interrupted_tasks(self) -> None:
        for task in self.list(1000):
            if task.get("status") not in TERMINAL_STATES:
                self._update(task, "failed", "failed", task.get("progress", 0), "服务重启导致任务中断，请重新提交", "dashboard service restarted")

    @staticmethod
    def _validate_filename(filename: str) -> str:
        filename = Path(filename).name.strip()
        if not filename or Path(filename).suffix.lower() != ".pdf":
            raise ValueError("仅支持 PDF 文件")
        stem = Path(filename).stem
        if len(filename.encode("utf-8")) > 240 or stem in {".", ".."}:
            raise ValueError("文件名过长或无效")
        return filename
