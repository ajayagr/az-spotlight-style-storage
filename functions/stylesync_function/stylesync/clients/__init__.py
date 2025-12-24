"""
StyleSync AI Generator Clients
"""
from .base import BaseGenerator, GeneratorResult
from .azure import AzureGenerator
from .stability import StabilityGenerator

def get_generator(provider: str) -> BaseGenerator:
    """
    Factory function to get the appropriate generator.
    
    Args:
        provider: 'azure' or 'stability'
    
    Returns:
        BaseGenerator instance
    """
    provider = provider.lower()
    if provider == "azure":
        return AzureGenerator()
    elif provider == "stability":
        return StabilityGenerator()
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'azure' or 'stability'.")

__all__ = ["get_generator", "GeneratorResult", "BaseGenerator"]
