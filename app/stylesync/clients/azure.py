"""
Azure Generator for StyleSync.
Uses Azure AI/OpenAI endpoints for image style transformation.

Required Environment Variables:
    AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint URL
    AZURE_OPENAI_API_KEY: Azure OpenAI API key
    AZURE_OPENAI_MODEL: Model name (default: flux.1-kontext-pro)
"""
import logging
import os
import requests
import base64
import mimetypes
import time
from .base import BaseGenerator, GeneratorResult

logger = logging.getLogger(__name__)


class AzureGenerator(BaseGenerator):
    """Azure AI image generator using Flux or other models."""
    
    # Environment variable names (consistent with Azure SDK conventions)
    ENV_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
    ENV_API_KEY = "AZURE_OPENAI_API_KEY"
    ENV_MODEL = "AZURE_OPENAI_MODEL"
    
    # Default model if not specified
    DEFAULT_MODEL = "flux.1-kontext-pro"
    
    def __init__(self):
        self.endpoint = os.getenv(self.ENV_ENDPOINT)
        self.api_key = os.getenv(self.ENV_API_KEY)
        self.model = os.getenv(self.ENV_MODEL, self.DEFAULT_MODEL)
        
    def is_configured(self) -> bool:
        """Check if Azure generator is properly configured."""
        return bool(self.endpoint and self.api_key)
    
    def get_missing_config(self) -> list:
        """Return list of missing configuration variables."""
        missing = []
        if not self.endpoint:
            missing.append(self.ENV_ENDPOINT)
        if not self.api_key:
            missing.append(self.ENV_API_KEY)
        return missing
    
    def process_image_bytes(self, image_data: bytes, filename: str, prompt: str, strength: float) -> GeneratorResult:
        """Process image using Azure AI endpoint."""
        if not self.is_configured():
            missing = self.get_missing_config()
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
            
        logger.info(f"Using Azure Endpoint: {self.endpoint}")
        logger.info(f"Using Model: {self.model}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "api-key": self.api_key  # Azure OpenAI uses api-key header
        }

        # Determine mime type
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "image/png" 

        start_time = time.time()
        req_info = f"POST {self.endpoint}\nModel: {self.model}\nPrompt: {prompt[:50]}..."
        resp_info = ""
        
        try:
            # Multipart Form Data
            files = {
                "image": (filename, image_data, mime_type)
            }
             
            data = {
                "model": self.model,
                "prompt": prompt
            }

            logger.info(f"Submitting Azure AI request for {filename}...")
            response = requests.post(self.endpoint, headers=headers, files=files, data=data, timeout=120)
             
            latency = time.time() - start_time
            resp_info = f"Status: {response.status_code}\nLatency: {latency:.2f}s"
             
            response.raise_for_status()

            result = response.json()
             
            result_data = None
            if "data" in result and len(result["data"]) > 0:
                item = result["data"][0]
                 
                if item.get("b64_json"):
                    result_data = base64.b64decode(item["b64_json"])
                elif item.get("url"):
                    logger.info(f"Result is URL, downloading from {item['url']}...")
                    img_resp = requests.get(item['url'], timeout=60)
                    img_resp.raise_for_status()
                    result_data = img_resp.content

            if result_data:
                return GeneratorResult(
                    data=result_data,
                    request_info=req_info,
                    response_info=resp_info
                )

            logger.error(f"Unexpected response structure: {list(result.keys())}")
            return GeneratorResult(None, req_info, resp_info + f"\nError: Unexpected structure")
 
        except requests.exceptions.HTTPError as e:
            logger.error(f"API Error processing {filename}: {e}")
            error_details = e.response.text if e.response is not None else str(e)
            return GeneratorResult(None, req_info, f"HTTP Error: {e}\n{error_details}")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            return GeneratorResult(None, req_info, f"Exception: {e}")
