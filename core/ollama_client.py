import json
import urllib.request
from urllib.error import URLError


def chat(model: str, system_prompt: str, user_message: str, base_url: str = "http://localhost:11434") -> str:
    """Send a chat request to Ollama and return the assistant's response text."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data["message"]["content"]
    except URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {base_url}. Is it running?\nDetails: {e}") from e
