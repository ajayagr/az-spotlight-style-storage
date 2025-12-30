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


@dataclass
class SyncResult:
    """Result of a StyleSync operation."""
    status: str = "completed"
    source: str = ""
    output: str = ""
    processed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
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
                name_parts = item["name"].rsplit('.', 1)
                stem = name_parts[0]
                suffix = f".{name_parts[1]}" if len(name_parts) > 1 else ""
                
                output_filename = f"{stem}_{style.index}{suffix}"
                expected_state[output_filename] = SyncTask(
                    source_path=item["path"],
                    source_name=item["name"],
                    style=style,
                    output_filename=output_filename
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
        
        for filename, task in expected_state.items():
            target_path = f"{output_path.strip('/')}/{filename}"
            
            if target_path not in existing_files:
                missing_tasks.append(task)
                
        return missing_tasks
    
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
            provider: AI provider ('azure' or 'stability')
            
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
            # Map expected state
            expected_state = self.map_expected_state(source_path, style_configs)
            
            if not expected_state:
                result.status = "completed"
                result.error = "No valid images found in source path"
                return result
            
            # Get missing files
            tasks = self.get_missing_files(expected_state, output_path)
            
            logger.info(f"Expected: {len(expected_state)}, Tasks to process: {len(tasks)}")
            
            for task in tasks:
                try:
                    # Read source image
                    input_data = self.storage.get_file(task.source_path)
                    
                    if input_data is None:
                        logger.error(f"Could not read source file: {task.source_path}")
                        result.failed.append(task.output_filename)
                        continue
                    
                    # Generate styled image
                    gen_result: GeneratorResult = generator.process_image_bytes(
                        input_data,
                        task.source_name,
                        task.style.prompt_text,
                        task.style.strength
                    )
                    
                    if gen_result.success:
                        # Write to output
                        target_path = f"{output_path.strip('/')}/{task.output_filename}"
                        self.storage.upload_file(target_path, gen_result.data)
                        result.processed.append(task.output_filename)
                        logger.info(f"Successfully processed: {task.output_filename}")
                    else:
                        result.failed.append(task.output_filename)
                        logger.warning(f"Failed to process: {task.output_filename} - {gen_result.response_info}")
                        
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
