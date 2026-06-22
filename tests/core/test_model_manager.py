"""Unit tests for core/model_manager.py — Ollama VRAM management is skipped for remote models."""

import yaml

from core.model_manager import ModelManager


def _write_config(tmp_path, model_overrides):
    config_path = tmp_path / "factory_config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "default_model": "ollama/qwen2.5-coder:14b-instruct-q4_K_M",
                "model_overrides": model_overrides,
            }
        )
    )
    return str(config_path)


def test_ensure_model_loaded_manages_vram_for_ollama_models(tmp_path, mocker):
    config_path = _write_config(tmp_path, {"reviewer": "ollama/codestral:22b"})
    mm = ModelManager(config_path)
    mock_loaded = mocker.patch.object(mm, "_get_loaded_models", return_value=[])
    mock_keep_alive = mocker.patch.object(mm, "_set_keep_alive")

    mm.ensure_model_loaded("reviewer")

    mock_loaded.assert_called_once()
    mock_keep_alive.assert_called_once_with("codestral:22b", keep_alive=-1)


def test_ensure_model_loaded_is_noop_for_anthropic_models(tmp_path, mocker):
    config_path = _write_config(tmp_path, {"reviewer": "anthropic/claude-sonnet-4-6"})
    mm = ModelManager(config_path)
    mock_loaded = mocker.patch.object(mm, "_get_loaded_models")
    mock_keep_alive = mocker.patch.object(mm, "_set_keep_alive")

    mm.ensure_model_loaded("reviewer")

    mock_loaded.assert_not_called()
    mock_keep_alive.assert_not_called()
