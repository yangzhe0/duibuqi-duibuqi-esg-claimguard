from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


LLAMA_SERVER_BIN = Path(os.environ.get("ESG_LLAMA_SERVER_BIN", "/usr/local/lib/ollama/llama-server"))
QWEN_MODEL_PATH = Path(
    os.environ.get(
        "ESG_QWEN_MODEL_PATH",
        "/usr/share/ollama/.ollama/models/huggingface/ggml-org/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf",
    )
)
QWEN_MMPROJ_PATH = Path(
    os.environ.get(
        "ESG_QWEN_MMPROJ_PATH",
        "/usr/share/ollama/.ollama/models/huggingface/ggml-org/Qwen3.6-27B-GGUF/mmproj-Qwen3.6-27B-Q8_0.gguf",
    )
)
GGML_CUDA_BACKEND = Path(
    os.environ.get("ESG_GGML_CUDA_BACKEND", "/usr/local/lib/ollama/cuda_v13/libggml-cuda.so")
)
QWEN_ALIAS = os.environ.get("ESG_QWEN_ALIAS", "qwen3.6-27b-q4_k_m")


def runtime_assets() -> dict[str, dict[str, object]]:
    paths = {
        "server": LLAMA_SERVER_BIN,
        "model": QWEN_MODEL_PATH,
        "mmproj": QWEN_MMPROJ_PATH,
        "cuda_backend": GGML_CUDA_BACKEND,
    }
    return {
        name: {"ready": path.is_file(), "path": str(path)}
        for name, path in paths.items()
    }


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def llama_server_command(port: int, include_vision: bool = False) -> list[str]:
    command = [
        str(LLAMA_SERVER_BIN),
        "--model",
        str(QWEN_MODEL_PATH),
        "--alias",
        QWEN_ALIAS,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--n-gpu-layers",
        "99",
        "--ctx-size",
        os.environ.get("ESG_QWEN_CONTEXT", "4096"),
        "--parallel",
        "1",
        "--jinja",
        "--metrics",
    ]
    if include_vision:
        command.extend(["--mmproj", str(QWEN_MMPROJ_PATH)])
    return command


def _runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GGML_BACKEND_PATH"] = str(GGML_CUDA_BACKEND)
    library_dir = str(GGML_CUDA_BACKEND.parent)
    current = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = library_dir + (os.pathsep + current if current else "")
    return env


def _wait_until_ready(process: subprocess.Popen, base_url: str, log_path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    health_url = base_url + "/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            with urlopen(health_url, timeout=1.0) as response:
                payload = json.load(response)
            if payload.get("status") == "ok":
                return
        except (OSError, HTTPError, URLError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(0.25)
    tail = ""
    if log_path.is_file():
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-16:])
    raise RuntimeError(f"Qwen3.6 llama-server failed to become ready: {tail}")


@contextmanager
def qwen_runtime(log_path: Path, include_vision: bool = False):
    required = [LLAMA_SERVER_BIN, QWEN_MODEL_PATH, GGML_CUDA_BACKEND]
    if include_vision:
        required.append(QWEN_MMPROJ_PATH)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Qwen3.6 runtime asset missing: " + ", ".join(missing))
    port = int(os.environ.get("ESG_QWEN_PORT", "0")) or _free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            llama_server_command(port, include_vision),
            cwd=log_path.parent,
            env=_runtime_env(),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            _wait_until_ready(
                process,
                base_url,
                log_path,
                float(os.environ.get("ESG_QWEN_START_TIMEOUT", "180")),
            )
            yield base_url + "/v1/chat/completions"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
