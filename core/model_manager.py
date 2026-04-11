import json
import os
import urllib.request
from urllib.error import URLError

import yaml


class ModelManager:
    """Resolves the correct Ollama model for a given pipeline role and ensures
    it is loaded in VRAM before use.

    Config schema (factory_config.yaml):
        default_model: "ollama/qwen2.5-coder:14b-instruct-q4_K_M"
        model_overrides:
          architect: "ollama/qwen2.5-coder:32b-instruct-q4_K_M"
          # roles not listed fall back to default_model
    """

    def __init__(self, config_path: str) -> None:
        with open(config_path) as f:
            config: dict = yaml.safe_load(f)
        self._default: str = config["default_model"]
        self._overrides: dict[str, str] = config.get("model_overrides", {})
        self._base_url: str = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")

    def get_model_for_role(self, role: str) -> str:
        """Return the model name for *role*, falling back to the default."""
        return self._overrides.get(role, self._default)

    def ensure_model_loaded(self, role: str) -> None:
        """Guarantee the model for *role* is resident in Ollama.

        If a different model is currently loaded, it is unloaded first to free
        VRAM before the target model is pulled into memory.
        """
        target = self.get_model_for_role(role)
        # Strip the "ollama/" prefix used by aider — Ollama's own API uses bare names.
        target_bare = target.removeprefix("ollama/")

        loaded = self._get_loaded_models()
        loaded_names = {m["name"] for m in loaded}

        if target_bare in loaded_names:
            return

        for model in loaded:
            self._set_keep_alive(model["name"], keep_alive=0)

        self._set_keep_alive(target_bare, keep_alive=-1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_loaded_models(self) -> list[dict]:
        """Return the list of models currently resident in Ollama (GET /api/ps)."""
        req = urllib.request.Request(f"{self._base_url}/api/ps", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read()).get("models", [])
        except URLError as e:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. Is it running?\nDetails: {e}"
            ) from e

    def _set_keep_alive(self, model: str, keep_alive: int) -> None:
        """Load (keep_alive=-1) or unload (keep_alive=0) a model via the generate endpoint."""
        payload = json.dumps(
            {"model": model, "keep_alive": keep_alive, "prompt": ""}
        ).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp.read()
        except URLError as e:
            raise RuntimeError(
                f"Ollama model operation failed for '{model}'.\nDetails: {e}"
            ) from e
