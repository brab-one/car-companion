"""A small client for OpenAI-compatible chat servers, standard library only.

On the board that is App Lab's LLM brick (arduino:llm): llama.cpp serving a
small Qwen model at http://llamacpp-models-runner:9999/v1. On a PC any
compatible server works, e.g. llama.cpp's llama-server
(tools/run_pc.py --llm http://localhost:8080/v1)."""

import json
import re
import urllib.error
import urllib.request

BOARD_URL = "http://llamacpp-models-runner:9999/v1"
MAX_CHARS = 400  # longer answers are cut at the last full sentence
_THINK = re.compile(r"<think>.*?(</think>|$)", re.S)


def clean(text):
    """The answer as plain text: no thinking, no markdown, one line."""
    text = _THINK.sub(" ", text or "")
    text = re.sub(r"[*_#`>]+", "", text)
    text = " ".join(text.split())
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:end + 1] if end > 0 else cut.rstrip() + "..."
    return text


class LlmClient:
    def __init__(self, base_url=BOARD_URL, model=None):
        self.base_url = base_url.rstrip("/")
        self.model = model  # None: the first model the server lists

    def chat(self, messages, max_tokens=120, temperature=0.3, timeout=60):
        """The answer to a chat (a list of {"role", "content"}), as plain text."""
        if self.model is None:
            self.model = self._request("/models", None, timeout)["data"][0]["id"]
        reply = self._request("/chat/completions", {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            # Qwen models think aloud first unless told not to; on the board's CPU
            # that would take far longer than the answer itself.
            "chat_template_kwargs": {"enable_thinking": False},
        }, timeout)
        return clean(reply["choices"][0]["message"]["content"])

    def _request(self, path, body, timeout):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ConnectionError(f"no AI model at {self.base_url} ({e.reason})") from None
