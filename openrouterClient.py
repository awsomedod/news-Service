from typing import Any, Dict, Optional

import requests
import json


OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """OpenRouter API client for text generation and structured outputs."""
    
    def __init__(self, api_key: str, model_id: str):
        """Initialize the OpenRouter client.
        
        Args:
            api_key: OpenRouter API key for authentication
            model_id: Model ID to use for generation (e.g., 'anthropic/claude-3-sonnet')
        """
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = OPENROUTER_API_BASE
        
    def _make_request(self, prompt: str, structured_output: Optional[Dict] = None, online: bool = False) -> Dict[str, Any]:
        """Make a request to the OpenRouter completions endpoint.
        
        Args:
            prompt: The text prompt to send
            structured_output: Optional schema for structured output
            
        Returns:
            Response from the API
            
        Raises:
            RuntimeError: If the request fails
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if online:
            self.model_id = self.model_id+ ":online"

        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "max_tokens": 1000
        }
        
        if structured_output:
            payload["response_format"] = structured_output
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            try:
                error_detail = exc.response.text
            except:
                error_detail = str(exc)
            raise RuntimeError(f"Failed to make OpenRouter request: {exc}. Detail: {error_detail} Payload: {payload}") from exc
    
    def generateText(self, prompt: str, system_message: Optional[str] = None, online: bool = False) -> str:
        """Generate text from a prompt.
        
        Args:
            prompt: The user prompt to generate text from
            system_message: Optional system message to set context
            
        Returns:
            Generated text response
        """
        full_prompt = prompt
        
        if system_message:
            full_prompt = f"{system_message}\n\n{prompt}"
        
        response = self._make_request(full_prompt, online=online)
        
        if "choices" not in response or not response["choices"]:
            raise RuntimeError("No choices in response")
            
        return response["choices"][0]["text"]
    
    def generateStructuredOutput(self, prompt: str, schema: Dict[str, Any], system_message: Optional[str] = None, online: bool = False) -> Dict[str, Any]:
        """Generate structured output from a prompt using a JSON schema.
        
        Args:
            prompt: The user prompt to generate from
            schema: JSON schema defining the expected output structure
            system_message: Optional system message to set context
            
        Returns:
            Parsed JSON response matching the schema
        """
        full_prompt = prompt
        
        if system_message:
            full_prompt = f"{system_message}\n\n{prompt}"
        
        response = self._make_request(full_prompt, structured_output=schema, online=online)
        
        if "choices" not in response or not response["choices"]:
            raise RuntimeError("No choices in response")
            
        content = response["choices"][0]["text"]
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse structured output as JSON: {exc}") from exc


# def get_available_models(api_key) -> List[Dict[str, Any]]:
#     """Return all available models from OpenRouter.

#     Args:
#         api_key: OpenRouter API key used for authorization.

#     Returns:
#         A list of model objects as returned by OpenRouter under the `data` field.

#     Raises:
#         RuntimeError: If the request fails or returns a non-2xx status code.
#     """
#     resolved_api_key = api_key

#     url = f"{OPENROUTER_API_BASE}/models"
#     headers = {}
#     if resolved_api_key:
#         headers["Authorization"] = f"Bearer {resolved_api_key}"

#     try:
#         response = requests.get(url, headers=headers, timeout=15)
#         response.raise_for_status()
#     except requests.RequestException as exc:
#         raise RuntimeError(f"Failed to fetch OpenRouter models: {exc}") from exc

#     payload = response.json()
#     data = payload.get("data", [])
#     if not isinstance(data, list):
#         raise RuntimeError("Unexpected response format: 'data' is not a list")
#     return data


# def get_structured_output_models(api_key, free_tier=False) -> List[Dict[str, Any]]:
#     """Return models that support structured outputs.

#     A model is considered to support structured outputs if `structured_outputs`
#     appears in either `supported_parameters` or `supported_features`.
#     """
#     models = get_available_models(api_key)
#     structured_models: List[Dict[str, Any]] = []
#     for model in models:
#         supported = (
#             model.get("supported_parameters")
#             or []
#         )
#         if isinstance(supported, list) and "structured_outputs" in supported:
#             structured_models.append(model)

#     if free_tier:
#         free_tier_models = []
#         for model in structured_models:
#             pricing = model.get("pricing")
#             if isinstance(pricing, dict):
#                 if pricing.get("prompt") == "0" and pricing.get("completion") == "0" and pricing.get("request") == "0":
#                     free_tier_models.append(model)
#         structured_models = free_tier_models

#     return structured_models


# Test the generateText method



