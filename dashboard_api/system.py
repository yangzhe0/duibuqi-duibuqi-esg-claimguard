from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import urlopen

from dashboard_api.model_runtime import runtime_assets
from dashboard_api.tasks import LLM_API, MINERU_BACKEND, MINERU_BIN, MODEL, OLLAMA_URL, PIPELINE_PROFILE


def system_health() -> dict:
    mineru_ready = MINERU_BIN.is_file() and MINERU_BIN.stat().st_mode & 0o111 != 0
    tags_url = OLLAMA_URL.split("/api/", 1)[0].rstrip("/") + "/api/tags"
    ollama_ready = False
    model_ready = False
    model_names: list[str] = []
    error = ""
    if LLM_API == "ollama":
        try:
            with urlopen(tags_url, timeout=1.5) as response:
                payload = json.load(response)
            model_names = [str(item.get("name", "")) for item in payload.get("models", [])]
            ollama_ready = True
            model_ready = MODEL in model_names
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            error = str(exc)
    assets = runtime_assets()
    local_runtime_ready = all(assets[name]["ready"] for name in ("server", "model", "cuda_backend"))
    inference_ready = local_runtime_ready if LLM_API == "openai" else ollama_ready and model_ready
    ready = mineru_ready and inference_ready
    return {
        "status": "ready" if ready else "degraded",
        "pipeline_ready": ready,
        "profile": PIPELINE_PROFILE,
        "mineru": {"ready": mineru_ready, "executable": str(MINERU_BIN), "backend": MINERU_BACKEND},
        "ollama": {"ready": ollama_ready, "url": OLLAMA_URL},
        "model": {"ready": inference_ready, "requested": MODEL, "available_count": len(model_names), "api": LLM_API},
        "runtime_assets": assets,
        "error": error,
    }
