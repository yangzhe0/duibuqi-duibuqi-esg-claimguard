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
