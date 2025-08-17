import os
from typing import Any, Dict, List, Optional

import requests


OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


def get_available_models(api_key) -> List[Dict[str, Any]]:
    """Return all available models from OpenRouter.

    Args:
        api_key: OpenRouter API key used for authorization.

    Returns:
        A list of model objects as returned by OpenRouter under the `data` field.

    Raises:
        RuntimeError: If the request fails or returns a non-2xx status code.
    """
    resolved_api_key = api_key

    url = f"{OPENROUTER_API_BASE}/models"
    headers = {}
    if resolved_api_key:
        headers["Authorization"] = f"Bearer {resolved_api_key}"

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch OpenRouter models: {exc}") from exc

    payload = response.json()
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError("Unexpected response format: 'data' is not a list")
    return data


def get_structured_output_models(api_key, free_tier=False) -> List[Dict[str, Any]]:
    """Return models that support structured outputs.

    A model is considered to support structured outputs if `structured_outputs`
    appears in either `supported_parameters` or `supported_features`.
    """
    models = get_available_models(api_key)
    structured_models: List[Dict[str, Any]] = []
    for model in models:
        supported = (
            model.get("supported_parameters")
            or []
        )
        if isinstance(supported, list) and "structured_outputs" in supported:
            structured_models.append(model)

    if free_tier:
        free_tier_models = []
        for model in structured_models:
            pricing = model.get("pricing")
            if isinstance(pricing, dict):
                if pricing.get("prompt") == "0" and pricing.get("completion") == "0" and pricing.get("request") == "0":
                    free_tier_models.append(model)
        structured_models = free_tier_models

    return structured_models



output = get_structured_output_models("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", free_tier=False)


for model in output:
    print(model.get("id"))
    print("=========================")
