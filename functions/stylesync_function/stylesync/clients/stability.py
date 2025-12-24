"""
Stability AI Generator for StyleSync Azure Function.
Adapted to work with byte streams.
"""
import logging
import os
import requests
import base64
import io
import time
from .base import BaseGenerator, GeneratorResult

logger = logging.getLogger(__name__)

class StabilityGenerator(BaseGenerator):
    def process_image_bytes(self, image_data: bytes, filename: str, prompt: str, strength: float) -> GeneratorResult:
        api_key = os.environ.get("STABILITY_API_KEY")
        if not api_key:
            raise ValueError("Environment variable STABILITY_API_KEY must be set.")
            
        url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/image-to-image"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        influence = 1.0 - strength 
        influence = max(0.01, min(0.99, influence))

        start_time = time.time()
        req_info = f"POST {url}\nInfluence: {influence}\nPrompt: {prompt[:50]}..."
        
        try:
            files = {
                "init_image": (filename, io.BytesIO(image_data), "image/png")
            }
            
            data = {
                "image_strength": influence,
                "init_image_mode": "IMAGE_STRENGTH",
                "text_prompts[0][text]": prompt,
                "text_prompts[0][weight]": 1,
                "cfg_scale": 7,
                "samples": 1,
                "steps": 30,
            }

            response = requests.post(url, headers=headers, files=files, data=data)
            latency = time.time() - start_time
            resp_info = f"Status: {response.status_code}\nLatency: {latency:.2f}s"
            
            if response.status_code != 200:
                logger.error(f"Stability API Error: {response.text}")
                return GeneratorResult(None, req_info, resp_info + f"\nError: {response.text}")

            result = response.json()
            for image in result["artifacts"]:
                if image["finishReason"] == "CONTENT_FILTERED":
                    logger.warning("Stability AI: Content Filtered")
                    return GeneratorResult(None, req_info, resp_info + "\nBlocked: Content Filter")
                
                return GeneratorResult(
                    data=base64.b64decode(image["base64"]),
                    request_info=req_info,
                    response_info=resp_info
                )
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API Error processing {filename}: {e}")
            return GeneratorResult(None, req_info, f"Exception: {e}")
            
        return GeneratorResult(None, req_info, "No artifacts returned")
