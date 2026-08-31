import json
from urllib import error, request


class OllamaClient:
    def __init__(self, model: str, url: str, timeout: int = 300):
        self.model = model
        self.url = url
        self.timeout = timeout
        self.opener = request.build_opener(request.ProxyHandler({}))

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1024},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"Cannot connect to Ollama: {exc.reason}") from exc
        if "error" in result:
            raise RuntimeError(result["error"])
        if "response" not in result:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result["response"]


class OpenAICompatibleClient:
    """Minimal chat-completions client used by the local llama-server runtime."""

    def __init__(self, model: str, url: str, timeout: int = 300):
        self.model = model
        self.url = url
        self.timeout = timeout
        self.opener = request.build_opener(request.ProxyHandler({}))

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return only the requested JSON object."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"Cannot connect to OpenAI-compatible inference server: {exc.reason}") from exc
        if "error" in result:
            detail = result["error"]
            raise RuntimeError(detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail))
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(json.dumps(result, ensure_ascii=False)) from exc


def build_llm_client(model: str, url: str, api: str = "ollama"):
    if api == "ollama":
        return OllamaClient(model=model, url=url)
    if api == "openai":
        return OpenAICompatibleClient(model=model, url=url)
    raise ValueError(f"Unsupported LLM API: {api}")
