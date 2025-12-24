"""
Base Generator class for StyleSync.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class GeneratorResult:
    data: Optional[bytes]
    request_info: str = ""
    response_info: str = ""

class BaseGenerator:
    """Abstract base class for image generators."""
    
    def process_image_bytes(self, image_data: bytes, filename: str, prompt: str, strength: float) -> GeneratorResult:
        """
        Process image bytes and return styled image.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement process_image_bytes")
