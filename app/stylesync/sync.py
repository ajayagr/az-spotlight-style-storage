"""
StyleSync Service
Handles AI-powered image style transfer and sync operations.
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

from .clients import get_generator, GeneratorResult

logger = logging.getLogger(__name__)

# Valid image extensions for processing
VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize a string to be used as a folder name.
    Replaces spaces with underscores and removes invalid characters.
    """
    # Replace spaces with underscores
    sanitized = name.replace(' ', '_')
    # Remove characters that are invalid in folder names
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '')
    # Convert to lowercase for consistency
    return sanitized.lower().strip('_')


@dataclass
class StyleConfig:
    """Configuration for a style transformation."""
    index: int
    name: str
    prompt_text: str
    strength: float = 0.7


@dataclass
class SyncTask:
    """A single sync task representing an image to be styled."""
    source_path: str
    source_name: str
    style: StyleConfig
    output_filename: str
    style_folder: str  # Sanitized style name for folder path


@dataclass
class SyncResult:
    """Result of a StyleSync operation."""
    status: str = "completed"
    source: str = ""
    output: str = ""
    processed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)  # Orphaned files that were deleted
    error: Optional[str] = None


class StyleSyncService:
    """
    Service for synchronizing styled images.
    Takes source images and applies AI style transformations.
    """
    
    def __init__(self, storage_service):
        """
        Initialize StyleSyncService.
        
        Args:
            storage_service: StorageService instance for file operations
        """
        self.storage = storage_service
        
    def get_valid_images(self, source_path: str = "") -> List[Dict[str, str]]:
        """
        Get list of valid image files from source path.
        
        Args:
            source_path: Path prefix to filter files
            
        Returns:
            List of dicts with 'name' and 'path' keys
        """
        all_files = self.storage.list_files()
        valid_images = []
        
        for file_path in all_files:
            # Filter by source path prefix
            if source_path and not file_path.startswith(source_path.strip("/")):
                continue
                
            # Check extension
            ext = Path(file_path).suffix.lower()
            if ext in VALID_IMAGE_EXTENSIONS:
                name = Path(file_path).name
                valid_images.append({
                    "name": name,
                    "path": file_path
                })
                
        return valid_images
    
    def map_expected_state(self, source_path: str, styles: List[StyleConfig]) -> Dict[str, SyncTask]:
        """
        Generate a map of expected output files.
        
        Args:
            source_path: Source directory path
            styles: List of style configurations
            
        Returns:
            Dictionary mapping output filename to SyncTask
        """
        expected_state = {}
        valid_images = self.get_valid_images(source_path)
        
        for item in valid_images:
            for style in styles:
                # Use original filename, organized by style folder
                style_folder = sanitize_folder_name(style.name)
                output_filename = item["name"]  # Keep original filename
                
                # Unique key combines style folder and filename
                state_key = f"{style_folder}/{output_filename}"
                expected_state[state_key] = SyncTask(
                    source_path=item["path"],
                    source_name=item["name"],
                    style=style,
                    output_filename=output_filename,
                    style_folder=style_folder
                )
                
        return expected_state
    
    def get_missing_files(self, expected_state: Dict[str, SyncTask], output_path: str) -> List[SyncTask]:
        """
        Identify which files need to be generated.
        
        Args:
            expected_state: Map of expected output files
            output_path: Output directory path
            
        Returns:
            List of SyncTask objects for missing files
        """
        missing_tasks = []
        existing_files = set(self.storage.list_files())
        
        for state_key, task in expected_state.items():
            # Path format: output_path/style_folder/original_filename
            target_path = f"{output_path.strip('/')}/{task.style_folder}/{task.output_filename}"
            
            if target_path not in existing_files:
                missing_tasks.append(task)
                
        return missing_tasks
    
    def get_orphaned_files(self, expected_state: Dict[str, SyncTask], output_path: str, style_folders: List[str]) -> List[str]:
        """
        Identify styled files that no longer have a source image (orphaned).
        
        Args:
            expected_state: Map of expected output files based on current source images
            output_path: Output directory path
            style_folders: List of style folder names to check
            
        Returns:
            List of file paths that should be deleted
        """
        orphaned_files = []
        existing_files = self.storage.list_files()
        output_prefix = output_path.strip('/')
        
        # Build set of expected file paths
        expected_paths = set()
        for state_key, task in expected_state.items():
            target_path = f"{output_prefix}/{task.style_folder}/{task.output_filename}"
            expected_paths.add(target_path)
            # Also add the original folder copy
            original_path = f"{output_prefix}/original/{task.output_filename}"
            expected_paths.add(original_path)
        
        # Check all style folders (including 'original') for orphaned files
        all_style_folders = style_folders + ['original']
        
        for file_path in existing_files:
            # Check if file is in the output directory
            if not file_path.startswith(output_prefix + '/'):
                continue
            
            # Extract the style folder from the path
            relative_path = file_path[len(output_prefix) + 1:]
            parts = relative_path.split('/', 1)
            if len(parts) < 2:
                continue
            
            folder_name = parts[0]
            
            # Only check files in known style folders
            if folder_name not in all_style_folders:
                continue
            
            # Check if this file is in the expected state
            if file_path not in expected_paths:
                orphaned_files.append(file_path)
                
        return orphaned_files
    
    def process_sync(
        self,
        source_path: str,
        output_path: str,
        styles: List[Dict[str, Any]],
        provider: str = "azure"
    ) -> SyncResult:
        """
        Execute the full sync operation.
        
        Args:
            source_path: Source directory containing images
            output_path: Output directory for styled images
            styles: List of style configuration dicts
            provider: AI provider (currently only 'azure' is supported)
            
        Returns:
            SyncResult with operation details
        """
        result = SyncResult(
            source=source_path,
            output=output_path
        )
        
        # Convert style dicts to StyleConfig objects
        style_configs = []
        for s in styles:
            style_configs.append(StyleConfig(
                index=s.get("index", 1),
                name=s.get("name", "Style"),
                prompt_text=s.get("prompt_text", ""),
                strength=s.get("strength", 0.7)
            ))
        
        if not style_configs:
            result.status = "failed"
            result.error = "No styles provided"
            return result
        
        # Initialize generator
        try:
            generator = get_generator(provider)
        except ValueError as e:
            result.status = "failed"
            result.error = f"Generator error: {e}"
            return result
        
        try:
            # Get style folder names for cleanup
            style_folders = [sanitize_folder_name(s.name) for s in style_configs]
            
            # Map expected state
            expected_state = self.map_expected_state(source_path, style_configs)
            
            # Clean up orphaned files first (styled images without source)
            orphaned_files = self.get_orphaned_files(expected_state, output_path, style_folders)
            for orphan_path in orphaned_files:
                try:
                    self.storage.delete_file(orphan_path)
                    result.deleted.append(orphan_path)
                    logger.info(f"Deleted orphaned file: {orphan_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete orphaned file {orphan_path}: {e}")
            
            if orphaned_files:
                logger.info(f"Cleaned up {len(result.deleted)} orphaned files")
            
            if not expected_state:
                result.status = "completed"
                if not orphaned_files:
                    result.error = "No valid images found in source path"
                return result
            
            # Get missing files
            tasks = self.get_missing_files(expected_state, output_path)
            
            logger.info(f"Expected: {len(expected_state)}, Tasks to process: {len(tasks)}")
            
            # Track which originals have been copied to avoid duplicates
            copied_originals = set()
            existing_files = set(self.storage.list_files())
            
            for task in tasks:
                try:
                    # Read source image
                    input_data = self.storage.get_file(task.source_path)
                    
                    if input_data is None:
                        logger.error(f"Could not read source file: {task.source_path}")
                        result.failed.append(task.output_filename)
                        continue
                    
                    # Copy original to 'original' folder if not already copied
                    original_target = f"{output_path.strip('/')}/original/{task.output_filename}"
                    if task.output_filename not in copied_originals and original_target not in existing_files:
                        self.storage.upload_file(original_target, input_data)
                        copied_originals.add(task.output_filename)
                        logger.info(f"Copied original: original/{task.output_filename}")
                    
                    # Generate styled image
                    gen_result: GeneratorResult = generator.process_image_bytes(
                        input_data,
                        task.source_name,
                        task.style.prompt_text,
                        task.style.strength
                    )
                    
                    if gen_result.success:
                        # Write to output: output_path/style_folder/original_filename
                        target_path = f"{output_path.strip('/')}/{task.style_folder}/{task.output_filename}"
                        self.storage.upload_file(target_path, gen_result.data)
                        result.processed.append(f"{task.style_folder}/{task.output_filename}")
                        logger.info(f"Successfully processed: {task.style_folder}/{task.output_filename}")
                    else:
                        result.failed.append(f"{task.style_folder}/{task.output_filename}")
                        logger.warning(f"Failed to process: {task.style_folder}/{task.output_filename} - {gen_result.response_info}")
                        
                except Exception as e:
                    logger.error(f"Error processing {task.output_filename}: {e}")
                    result.failed.append(task.output_filename)
            
            # Files already existing (skipped)
            processed_names = {t.output_filename for t in tasks}
            result.skipped = [k for k in expected_state.keys() if k not in processed_names]
            
        except Exception as e:
            logger.error(f"Critical error during sync: {e}")
            result.status = "failed"
            result.error = str(e)
        
        return result
