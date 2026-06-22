import json
import urllib.request
from urllib.error import URLError

# Per-chunk read timeout in seconds. Large models can take several minutes to
# load into VRAM and emit the first token, so this must be generous.
_TIMEOUT = 600


def chat(
    model: str,
    system_prompt: str,
    user_message: str,
    base_url: str = "http://localhost:11434",
) -> str:
    """Send a chat request to Ollama and return the assistant's response text.

    Uses streaming so the HTTP connection stays alive while the model generates,
    avoiding premature timeouts on large models or long outputs.
    """
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": True,
        # Ollama silently truncates the response once total tokens (prompt +
        # generated output) hit num_ctx, producing invalid JSON with no error
        # from Ollama itself (confirmed via done_reason: "length" on the raw
        # API response). The architect_plan.md system prompt alone is ~3.4k
        # tokens, so num_ctx must comfortably exceed prompt + full output size,
        # not just the output. num_predict=-1 means "generate until done,
        # bounded only by num_ctx" (no separate output cap).
        "options": {"num_ctx": 6144, "num_predict": -1},
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        chunks: list[str] = []
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    chunks.append(content)
                if chunk.get("done"):
                    break
        return "".join(chunks)
    except URLError as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {base_url}. Is it running?\nDetails: {e}"
        ) from e
