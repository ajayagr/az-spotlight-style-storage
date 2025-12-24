"""
Azure Generator for StyleSync Azure Function.
Adapted to work with byte streams instead of file paths.
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
    def process_image_bytes(self, image_data: bytes, filename: str, prompt: str, strength: float) -> GeneratorResult:
        endpoint = os.environ.get("AZURE_ENDPOINT_URL")
        api_key = os.environ.get("AZURE_API_KEY")

        if not endpoint or not api_key:
            raise ValueError("Environment variables AZURE_ENDPOINT_URL and AZURE_API_KEY must be set.")
            
        logger.info(f"Using Endpoint: {endpoint}")

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        # Determine mime type
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "image/png" 

        start_time = time.time()
        req_info = f"POST {endpoint}\nData: model=flux.1-kontext-pro, prompt={prompt[:50]}..."
        resp_info = ""
        
        try:
            # Multipart Form Data
            files = {
                "image": (filename, image_data, mime_type)
            }
             
            data = {
                "model": "flux.1-kontext-pro",
                "prompt": prompt
            }

            logger.info(f"Submitting request for {filename}...")
            response = requests.post(endpoint, headers=headers, files=files, data=data)
             
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
                    img_resp = requests.get(item['url'])
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
