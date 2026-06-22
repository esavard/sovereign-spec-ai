from core import ollama_client


def chat(model: str, system_prompt: str, user_message: str) -> str:
    """Send a system+user chat turn to *model* and return the assistant's reply.

    Routes by provider prefix:
      - "ollama/<name>"   -> local Ollama instance (core.ollama_client)
      - anything else     -> litellm (e.g. "anthropic/claude-sonnet-4-6"),
                              which reads provider credentials from the environment
                              (e.g. ANTHROPIC_API_KEY).
    """
    if model.startswith("ollama/"):
        return ollama_client.chat(model.removeprefix("ollama/"), system_prompt, user_message)

    import litellm

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content
