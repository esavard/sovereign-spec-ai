"""Unit tests for core/llm_client.py — provider dispatch by model prefix."""

from core import llm_client


def test_ollama_prefix_routes_to_ollama_client(mocker):
    mock_chat = mocker.patch("core.ollama_client.chat", return_value="ollama reply")

    result = llm_client.chat("ollama/qwen2.5-coder:14b", "system", "user")

    mock_chat.assert_called_once_with("qwen2.5-coder:14b", "system", "user")
    assert result == "ollama reply"


def test_non_ollama_model_routes_to_litellm(mocker):
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock(message=mocker.Mock(content="claude reply"))]
    mock_completion = mocker.patch("litellm.completion", return_value=mock_response)

    result = llm_client.chat("anthropic/claude-sonnet-4-6", "system", "user")

    mock_completion.assert_called_once_with(
        model="anthropic/claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
    )
    assert result == "claude reply"
