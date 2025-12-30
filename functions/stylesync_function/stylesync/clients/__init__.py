"""
StyleSync AI Generator Clients
"""
from .base import BaseGenerator, GeneratorResult
from .azure import AzureGenerator


def get_generator(provider: str = "azure") -> BaseGenerator:
    """
    Factory function to get the appropriate generator.
    
    Args:
        provider: 'azure' (only Azure is currently supported)
    
    Returns:
        BaseGenerator instance
    """
    provider = provider.lower()
    if provider == "azure":
        return AzureGenerator()
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'azure'.")

__all__ = ["get_generator", "GeneratorResult", "BaseGenerator", "AzureGenerator"]
