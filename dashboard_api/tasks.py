from __future__ import annotations

import csv
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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = PROJECT_ROOT / "outputs/dashboard/tasks"
RAW_PDF_ROOT = PROJECT_ROOT / "data/raw_pdfs"
PARSED_ROOT = PROJECT_ROOT / "data/parsed_reports_v1/reports"
REPORT_INDEX = PROJECT_ROOT / "data/report_index.csv"
DOWNLOAD_LOG = PROJECT_ROOT / "data/download_log.csv"
MINERU_BIN = Path(os.environ.get("ESG_MINERU_BIN", "/home/sues01/.conda/envs/mineru/bin/mineru"))
OLLAMA_URL = os.environ.get("ESG_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
MODEL = os.environ.get("ESG_MODEL", "qwen3:30b")
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
            task = self._update(task, "running", "extracting", 65, "正在执行 ESG-65 候选召回与 Qwen3 抽取")
            extraction_dir = task_dir / "extraction"
            self._extract(parsed_json, extraction_dir, task_dir / "extraction.log")
            repository.clear_caches()
            self._update(task, "completed", "completed", 100, "解析、抽取和结果入库均已完成")
        except Exception as exc:  # task error must be persisted for the browser
            self._update(task, "failed", "failed", task.get("progress", 0), "处理失败", str(exc))

    def _register_pdf(self, task: dict, staged: Path) -> Path:
        RAW_PDF_ROOT.mkdir(parents=True, exist_ok=True)
        target = RAW_PDF_ROOT / task["filename"]
        if target.exists():
            if _sha256(target) != task["sha256"]:
                raise ValueError("原始报告目录中已存在同名但内容不同的 PDF，请调整文件名后重试")
        else:
            shutil.copy2(staged, target)
        self._append_ledgers(task, target)
        self._update(task, "running", "registered", 8, "PDF 已校验并登记到原始报告库")
        return target

    def _parse_pdf(self, task: dict, raw_pdf: Path, task_dir: Path) -> Path:
        report_id = task["report_id"]
        existing = PARSED_ROOT / report_id / f"{report_id}_content_list_v2.json"
        if existing.is_file():
            return existing
        output = task_dir / "mineru"
        log_path = task_dir / "mineru.log"
        env = {**os.environ, "MINERU_MODEL_SOURCE": os.environ.get("MINERU_MODEL_SOURCE", "modelscope")}
        command = [str(MINERU_BIN), "-p", str(raw_pdf), "-o", str(output), "-b", "pipeline", "-l", "ch"]
        self._run_command(command, log_path, env)
        matches = list(output.rglob("*content_list_v2.json"))
        if len(matches) != 1:
            raise RuntimeError(f"MinerU 输出异常：找到 {len(matches)} 个 content_list_v2.json")
        source_dir = matches[0].parent
        target_dir = PARSED_ROOT / report_id
        if target_dir.exists():
            raise RuntimeError(f"解析目录已存在但缺少目标 JSON：{target_dir}")
        temp_dir = PARSED_ROOT / f".{report_id}.{task['task_id']}.tmp"
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
            OLLAMA_URL,
            "--resume",
        ]
        self._run_command(command, log_path, os.environ.copy())
        if not (output / "extraction_results.csv").is_file():
            raise RuntimeError("Qwen3 抽取未生成 extraction_results.csv")

    @staticmethod
    def _run_command(command: list[str], log_path: Path, env: dict[str, str]) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
        if completed.returncode:
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
            raise RuntimeError(f"命令执行失败（退出码 {completed.returncode}）：{tail}")

    def _append_ledgers(self, task: dict, target: Path) -> None:
        metadata = report_metadata(task["filename"], task["sha256"])
        index_row = {
            **metadata,
            "announcement_date": "",
            "source": "user_upload",
            "source_url": "",
            "original_title": metadata["title"],
            "original_adjunct_url": "",
            "pdf_url": "",
            "original_pdf_filename": task["filename"],
            "normalized_filename": task["filename"],
            "local_path": str(target.relative_to(PROJECT_ROOT)),
            "file_sha256": task["sha256"],
            "file_size_bytes": str(task["size"]),
            "error": "",
        }
        log_row = {
            "id": metadata["id"],
            "stock_code": metadata["stock_code"],
            "company": metadata["company"],
            "title": metadata["title"],
            "status": "uploaded",
            "error": "",
        }
        with self._lock:
            _append_unique_csv(REPORT_INDEX, index_row, "file_sha256")
            _append_unique_csv(DOWNLOAD_LOG, log_row, "id")

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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_unique_csv(path: Path, row: dict[str, str], unique_key: str) -> None:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or row.keys())
        rows = list(reader)
    if any(existing.get(unique_key) == row.get(unique_key) for existing in rows):
        return
    rows.append({key: row.get(key, "") for key in fields})
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
