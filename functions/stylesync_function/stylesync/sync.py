"""
Sync logic for StyleSync Azure Function.
Adapted from CLI version.
"""
from .storage import AzureBlobStorageProvider, FileItem
from typing import Dict, List

def get_valid_images(provider: AzureBlobStorageProvider, source_dir: str):
    """
    Generator yielding valid FileItem objects from source directory.
    Supported extensions: .jpg, .jpeg, .png, .webp
    """
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    
    for item in provider.list_files(source_dir):
        if not item.is_dir and any(item.name.lower().endswith(ext) for ext in valid_extensions):
            yield item

def map_expected_state(source_provider: AzureBlobStorageProvider, source_dir: str, styles: List[Dict]):
    """
    Step A: Generate a map of expected output files.
    Returns a dictionary: {output_filename: {source_item, style, output_filename}}
    """
    expected_state = {}
    valid_images = list(get_valid_images(source_provider, source_dir))
    
    for item in valid_images:
        for style in styles:
            name_parts = item.name.rsplit('.', 1)
            stem = name_parts[0]
            suffix = f".{name_parts[1]}" if len(name_parts) > 1 else ""
            
            output_filename = f"{stem}_{style['index']}{suffix}"
            expected_state[output_filename] = {
                'source_item': item,
                'style': style,
                'output_filename': output_filename
            }
    
    return expected_state

def get_missing_files(dest_provider: AzureBlobStorageProvider, expected_state: Dict, output_dir: str):
    """
    Step C: Identify which files need to be generated.
    Returns: List of task dictionaries.
    """
    missing_files = []
    
    for filename, details in expected_state.items():
        target_path = f"{output_dir.rstrip('/')}/{filename}"
        
        if not dest_provider.exists(target_path):
            missing_files.append(details)
            
    return missing_files
