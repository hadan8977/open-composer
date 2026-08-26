from __future__ import annotations

import hashlib
from typing import Any, Protocol

from open_composer.config import default_openai_model, openai_api_key, openai_base_url


class LLMBackend(Protocol):
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class LocalTestStub:
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        properties = output_schema.get("properties")
        required = output_schema.get("required")
        keys = required if isinstance(required, list) and required else []
        if isinstance(properties, dict):
            keys = keys or list(properties)
        digest = hashlib.sha256(
            (prompt + repr(sorted(input_payload.items()))).encode("utf-8")
        ).hexdigest()
        score = (int(digest[:8], 16) / 0xFFFFFFFF) * 2 - 1
        result: dict[str, Any] = {}
        for key in keys:
            schema = properties.get(key, {}) if isinstance(properties, dict) else {}
            value_type = schema.get("type") if isinstance(schema, dict) else None
            if key == "confidence":
                result[key] = 0.5
            elif value_type == "integer":
                result[key] = int(round(score * 10))
            elif value_type == "boolean":
                result[key] = score > 0
            elif value_type == "string":
                result[key] = "neutral"
            else:
                result[key] = round(score, 6)
        return result or {"score": round(score, 6), "confidence": 0.5}


class OpenAIBackend:
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        if not openai_api_key():
            raise RuntimeError("OPENAI_API_KEY is required for openai materialization backend")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openai package is required for openai backend") from exc
        client_options: dict[str, Any] = {"api_key": openai_api_key()}
        if base_url := openai_base_url():
            client_options["base_url"] = base_url
        client = OpenAI(**client_options)
        response = client.responses.create(
            model=model or default_openai_model(),
            input=[
                {
                    "role": "system",
                    "content": "Return only JSON matching the requested schema.",
                },
                {"role": "user", "content": prompt + "\n\nInput:\n" + repr(input_payload)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "llm_factor_output",
                    "schema": output_schema,
                    "strict": True,
                }
            },
        )
        import json

        return json.loads(response.output_text)


def get_backend(name: str) -> LLMBackend:
    if name == "local_test_stub":
        return LocalTestStub()
    if name == "openai":
        return OpenAIBackend()
    raise ValueError(f"unsupported LLM materialization backend: {name}")
