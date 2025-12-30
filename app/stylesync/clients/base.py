"""
Base Generator class for StyleSync.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class GeneratorResult:
    """Result from an AI image generation request."""
    data: Optional[bytes]
    request_info: str = ""
    response_info: str = ""
    
    @property
    def success(self) -> bool:
        return self.data is not None

class BaseGenerator:
    """Abstract base class for image generators."""
    
    def process_image_bytes(self, image_data: bytes, filename: str, prompt: str, strength: float) -> GeneratorResult:
        """
        Process image bytes and return styled image.
        Must be implemented by subclasses.
        
        Args:
            image_data: Input image as bytes
            filename: Original filename (for MIME type detection)
            prompt: Style transformation prompt
            strength: Style intensity (0.0 - 1.0)
            
        Returns:
            GeneratorResult with styled image data
        """
        raise NotImplementedError("Subclasses must implement process_image_bytes")
