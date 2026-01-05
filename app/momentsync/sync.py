"""
MomentSync Service
Handles AI-powered moment-in-time variations (time of day + season) for styled images.
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

from ..stylesync.clients import get_generator, GeneratorResult

logger = logging.getLogger(__name__)

# Valid image extensions for processing
VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize a string to be used as a folder name.
    Replaces spaces with underscores and removes invalid characters.
    """
    sanitized = name.replace(' ', '_')
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '')
    return sanitized.lower().strip('_')


@dataclass
class MomentConfig:
    """Configuration for a moment transformation (time or season)."""
    name: str
    folder_name: str
    prompt_text: str
    strength: float = 0.6


@dataclass
class CompositeMoment:
    """A composite moment combining time of day and season."""
    time: MomentConfig
    season: MomentConfig
    folder_name: str
    prompt_text: str
    strength: float = 0.65


@dataclass
class MomentTask:
    """A single moment sync task."""
    source_path: str
    source_name: str
    style_folder: str  # The style folder the source came from (e.g., 'geometric_3d')
    moment_folder: str  # The moment folder (e.g., 'morning' or 'morning_summer')
    prompt_text: str
    strength: float
    output_filename: str


@dataclass
class MomentSyncResult:
    """Result of a MomentSync operation."""
    status: str = "completed"
    source: str = ""
    output: str = ""
    processed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    error: Optional[str] = None


class MomentSyncService:
    """
    Service for creating moment-in-time variations of styled images.
    Takes styled images and applies time/season transformations.
    """
    
    def __init__(self, storage_service):
        """
        Initialize MomentSyncService.
        
        Args:
            storage_service: StorageService instance for file operations
        """
        self.storage = storage_service
    
    def build_moments(self, config: Dict[str, Any]) -> tuple[List[MomentConfig], List[MomentConfig], List[CompositeMoment]]:
        """
        Build moment configurations from JSON config.
        
        Args:
            config: Parsed moments.json configuration
            
        Returns:
            Tuple of (times, seasons, composites)
        """
        times = []
        for t in config.get("times_of_day", []):
            times.append(MomentConfig(
                name=t["name"],
                folder_name=t.get("folder_name") or sanitize_folder_name(t["name"]),
                prompt_text=t["prompt_text"],
                strength=t.get("strength", 0.6)
            ))
        
        seasons = []
        for s in config.get("seasons", []):
            seasons.append(MomentConfig(
                name=s["name"],
                folder_name=s.get("folder_name") or sanitize_folder_name(s["name"]),
                prompt_text=s["prompt_text"],
                strength=s.get("strength", 0.6)
            ))
        
        # Build composite moments (time + season combinations)
        composite_strength = config.get("composite_strength", 0.65)
        composites = []
        for time in times:
            for season in seasons:
                folder_name = f"{time.folder_name}_{season.folder_name}"
                # Create combined prompt
                prompt = f"Transform this image to show {time.name.lower()} during {season.name.lower()}. {time.prompt_text} Combined with {season.prompt_text}"
                composites.append(CompositeMoment(
                    time=time,
                    season=season,
                    folder_name=folder_name,
                    prompt_text=prompt,
                    strength=composite_strength
                ))
        
        return times, seasons, composites
    
    def get_styled_images(self, styled_path: str, style_folders: List[str]) -> List[Dict[str, str]]:
        """
        Get list of styled images to process.
        
        Args:
            styled_path: Base path for styled images (e.g., 'styled/')
            style_folders: List of style folder names to process
            
        Returns:
            List of dicts with 'name', 'path', and 'style_folder' keys
        """
        all_files = self.storage.list_files()
        styled_images = []
        
        normalized_path = styled_path.strip("/")
        
        for file_path in all_files:
            # Must be in the styled path
            if not file_path.startswith(normalized_path + "/"):
                continue
            
            # Extract relative path after styled/
            relative = file_path[len(normalized_path) + 1:]
            parts = relative.split("/")
            
            if len(parts) < 2:
                continue
            
            style_folder = parts[0]
            
            # Skip 'original' folder and moment output folder
            if style_folder == "original":
                continue
            
            # Only process from specified style folders
            if style_folders and style_folder not in style_folders:
                continue
            
            # Check extension
            ext = Path(file_path).suffix.lower()
            if ext in VALID_IMAGE_EXTENSIONS:
                styled_images.append({
                    "name": Path(file_path).name,
                    "path": file_path,
                    "style_folder": style_folder
                })
        
        return styled_images
    
    def map_expected_state(
        self, 
        styled_images: List[Dict[str, str]], 
        times: List[MomentConfig],
        seasons: List[MomentConfig],
        composites: List[CompositeMoment]
    ) -> Dict[str, MomentTask]:
        """
        Generate a map of expected output files.
        
        Args:
            styled_images: List of styled images to process
            times: List of time of day configurations
            seasons: List of season configurations
            composites: List of composite moment configurations
            
        Returns:
            Dictionary mapping output key to MomentTask
        """
        expected_state = {}
        
        for img in styled_images:
            # Standalone time variations
            for time in times:
                state_key = f"{img['style_folder']}/{time.folder_name}/{img['name']}"
                expected_state[state_key] = MomentTask(
                    source_path=img["path"],
                    source_name=img["name"],
                    style_folder=img["style_folder"],
                    moment_folder=time.folder_name,
                    prompt_text=time.prompt_text,
                    strength=time.strength,
                    output_filename=img["name"]
                )
            
            # Standalone season variations
            for season in seasons:
                state_key = f"{img['style_folder']}/{season.folder_name}/{img['name']}"
                expected_state[state_key] = MomentTask(
                    source_path=img["path"],
                    source_name=img["name"],
                    style_folder=img["style_folder"],
                    moment_folder=season.folder_name,
                    prompt_text=season.prompt_text,
                    strength=season.strength,
                    output_filename=img["name"]
                )
            
            # Composite variations (time + season)
            for composite in composites:
                state_key = f"{img['style_folder']}/{composite.folder_name}/{img['name']}"
                expected_state[state_key] = MomentTask(
                    source_path=img["path"],
                    source_name=img["name"],
                    style_folder=img["style_folder"],
                    moment_folder=composite.folder_name,
                    prompt_text=composite.prompt_text,
                    strength=composite.strength,
                    output_filename=img["name"]
                )
        
        return expected_state
    
    def get_missing_files(self, expected_state: Dict[str, MomentTask], output_path: str) -> List[MomentTask]:
        """
        Identify which files need to be generated.
        
        Args:
            expected_state: Map of expected output files
            output_path: Output directory path
            
        Returns:
            List of MomentTask objects for missing files
        """
        missing_tasks = []
        existing_files = set(self.storage.list_files())
        
        for state_key, task in expected_state.items():
            # Path format: output_path/style_folder/moment_folder/filename
            target_path = f"{output_path.strip('/')}/{task.style_folder}/{task.moment_folder}/{task.output_filename}"
            
            if target_path not in existing_files:
                missing_tasks.append(task)
        
        return missing_tasks
    
    def get_orphaned_files(
        self, 
        expected_state: Dict[str, MomentTask], 
        output_path: str,
        style_folders: List[str],
        moment_folders: List[str]
    ) -> List[str]:
        """
        Identify moment files that no longer have a source styled image.
        
        Args:
            expected_state: Map of expected output files
            output_path: Output directory path
            style_folders: List of style folder names
            moment_folders: List of moment folder names
            
        Returns:
            List of file paths that should be deleted
        """
        orphaned_files = []
        existing_files = self.storage.list_files()
        output_prefix = output_path.strip('/')
        
        # Build set of expected file paths
        expected_paths = set()
        for state_key, task in expected_state.items():
            target_path = f"{output_prefix}/{task.style_folder}/{task.moment_folder}/{task.output_filename}"
            expected_paths.add(target_path)
        
        for file_path in existing_files:
            # Check if file is in the moments output directory
            if not file_path.startswith(output_prefix + '/'):
                continue
            
            # Extract structure: output_path/style_folder/moment_folder/filename
            relative_path = file_path[len(output_prefix) + 1:]
            parts = relative_path.split('/')
            
            if len(parts) < 3:
                continue
            
            style_folder = parts[0]
            moment_folder = parts[1]
            
            # Only check files in known style and moment folders
            if style_folder not in style_folders:
                continue
            if moment_folder not in moment_folders:
                continue
            
            # Check extension
            ext = Path(file_path).suffix.lower()
            if ext not in VALID_IMAGE_EXTENSIONS:
                continue
            
            # Check if this file is in the expected state
            if file_path not in expected_paths:
                orphaned_files.append(file_path)
        
        return orphaned_files
    
    def process_sync(
        self,
        styled_path: str,
        output_path: str,
        moments_config: Dict[str, Any],
        style_folders: Optional[List[str]] = None,
        provider: str = "azure"
    ) -> MomentSyncResult:
        """
        Execute the full moment sync operation.
        
        Args:
            styled_path: Path containing styled images (e.g., 'styled/')
            output_path: Output path for moment variations (e.g., 'moments/')
            moments_config: Parsed moments.json configuration
            style_folders: Optional list of specific style folders to process
            provider: AI provider (currently only 'azure' is supported)
            
        Returns:
            MomentSyncResult with operation details
        """
        result = MomentSyncResult(
            source=styled_path,
            output=output_path
        )
        
        # Build moment configurations
        times, seasons, composites = self.build_moments(moments_config)
        
        if not times and not seasons:
            result.status = "failed"
            result.error = "No time or season configurations found"
            return result
        
        # Get all moment folder names for cleanup
        moment_folders = []
        moment_folders.extend([t.folder_name for t in times])
        moment_folders.extend([s.folder_name for s in seasons])
        moment_folders.extend([c.folder_name for c in composites])
        
        # Initialize generator
        try:
            generator = get_generator(provider)
        except ValueError as e:
            result.status = "failed"
            result.error = f"Generator error: {e}"
            return result
        
        try:
            # Get styled images from all style folders if not specified
            if not style_folders:
                # Auto-detect style folders from styled path
                all_files = self.storage.list_files()
                normalized_path = styled_path.strip("/")
                detected_folders = set()
                for f in all_files:
                    if f.startswith(normalized_path + "/"):
                        relative = f[len(normalized_path) + 1:]
                        parts = relative.split("/")
                        if len(parts) >= 2 and parts[0] != "original":
                            detected_folders.add(parts[0])
                style_folders = list(detected_folders)
            
            if not style_folders:
                result.status = "completed"
                result.error = "No style folders found in styled path"
                return result
            
            logger.info(f"Processing style folders: {style_folders}")
            
            # Get styled images
            styled_images = self.get_styled_images(styled_path, style_folders)
            
            if not styled_images:
                result.status = "completed"
                result.error = "No styled images found to process"
                return result
            
            logger.info(f"Found {len(styled_images)} styled images to process")
            
            # Map expected state
            expected_state = self.map_expected_state(styled_images, times, seasons, composites)
            
            # Clean up orphaned files first
            orphaned_files = self.get_orphaned_files(expected_state, output_path, style_folders, moment_folders)
            for orphan_path in orphaned_files:
                try:
                    self.storage.delete_file(orphan_path)
                    result.deleted.append(orphan_path)
                    logger.info(f"Deleted orphaned moment file: {orphan_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete orphaned file {orphan_path}: {e}")
            
            if orphaned_files:
                logger.info(f"Cleaned up {len(result.deleted)} orphaned moment files")
            
            # Get missing files
            tasks = self.get_missing_files(expected_state, output_path)
            
            logger.info(f"Expected: {len(expected_state)}, Tasks to process: {len(tasks)}")
            
            for task in tasks:
                try:
                    # Read source styled image
                    input_data = self.storage.get_file(task.source_path)
                    
                    if input_data is None:
                        logger.error(f"Could not read source file: {task.source_path}")
                        result.failed.append(f"{task.style_folder}/{task.moment_folder}/{task.output_filename}")
                        continue
                    
                    # Generate moment variation
                    gen_result: GeneratorResult = generator.process_image_bytes(
                        input_data,
                        task.source_name,
                        task.prompt_text,
                        task.strength
                    )
                    
                    if gen_result.success:
                        # Write to output: output_path/style_folder/moment_folder/filename
                        target_path = f"{output_path.strip('/')}/{task.style_folder}/{task.moment_folder}/{task.output_filename}"
                        self.storage.upload_file(target_path, gen_result.data)
                        result.processed.append(f"{task.style_folder}/{task.moment_folder}/{task.output_filename}")
                        logger.info(f"Successfully processed: {task.style_folder}/{task.moment_folder}/{task.output_filename}")
                    else:
                        result.failed.append(f"{task.style_folder}/{task.moment_folder}/{task.output_filename}")
                        logger.warning(f"Failed to process: {task.style_folder}/{task.moment_folder}/{task.output_filename}")
                        
                except Exception as e:
                    logger.error(f"Error processing {task.output_filename}: {e}")
                    result.failed.append(f"{task.style_folder}/{task.moment_folder}/{task.output_filename}")
            
            # Files already existing (skipped)
            processed_keys = {f"{t.style_folder}/{t.moment_folder}/{t.output_filename}" for t in tasks}
            result.skipped = [k for k in expected_state.keys() if k not in processed_keys]
            
        except Exception as e:
            logger.error(f"Critical error during moment sync: {e}")
            result.status = "failed"
            result.error = str(e)
        
        return result
