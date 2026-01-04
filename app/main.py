import os
import json
import logging
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException, File, Depends, Header, Query, Request, BackgroundTasks
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import List, Optional
import random
from .storage import StorageService
from .stylesync import StyleSyncService
import mimetypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Styles configuration file path
STYLES_FILE_PATH = Path(__file__).parent.parent / "styles.json"

# StyleSync default folder configuration
STYLE_SYNC_DEFAULT_SOURCE = os.getenv("STYLE_SYNC_DEFAULT_SOURCE_FOLDER", "source/")
STYLE_SYNC_DEFAULT_TARGET = os.getenv("STYLE_SYNC_DEFAULT_TARGET_FOLDER", "styled/")
STYLE_SYNC_ICON_FOLDER = os.getenv("STYLE_SYNC_ICON_FOLDER", "icons/")


def load_styles_from_file() -> List[dict]:
    """
    Load style configurations from styles.json file.
    """
    if not STYLES_FILE_PATH.exists():
        raise FileNotFoundError(f"Styles file not found: {STYLES_FILE_PATH}")
    
    with open(STYLES_FILE_PATH, "r") as f:
        data = json.load(f)
    
    return data.get("styles", [])


def sanitize_style_name(name: str) -> str:
    """
    Sanitize a style name for case-insensitive comparison.
    Removes spaces, underscores, hyphens and converts to lowercase.
    """
    return name.lower().replace(" ", "").replace("_", "").replace("-", "")


def find_style_by_name(styles: List[dict], style_name: str) -> dict:
    """
    Find a style by name using case-insensitive and sanitized matching.
    Returns None if no match found.
    """
    sanitized_input = sanitize_style_name(style_name)
    for s in styles:
        if sanitize_style_name(s.get("name", "")) == sanitized_input:
            return s
    return None

app = FastAPI(
    title="Azure File Storage App",
    description="File storage with AI-powered style transfer capabilities",
    version="2.0.0"
)
storage = StorageService()
stylesync_service = StyleSyncService(storage)


@app.get("/health", tags=["Health"])
def health_check():
    """
    Health check endpoint for container orchestration and load balancers.
    Returns basic application status.
    """
    return {
        "status": "healthy",
        "service": "az-spotlight-style-storage",
        "storage_mode": storage.mode
    }


# Setup Templates
templates = Jinja2Templates(directory="app/templates")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Security Configuration
API_KEY = os.getenv("API_KEY", "default-insecure-key")

def get_api_key(
    api_key_header: str = Header(None, alias="X-API-Key"),
    api_key_query: str = Query(None, alias="api_key")
):
    """
    Validate API Key from Header or Query Parameter.
    """
    if not API_KEY:
        return True # Open if no key configured (dev mode)
        
    key = api_key_header or api_key_query
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return key

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """
    Serve the Home Page UI.
    """
    raw_files = storage.list_files()
    files = []
    for f in raw_files:
        parts = f.rsplit("/", 1)
        if len(parts) > 1:
            files.append({"path": f, "folder": parts[0], "name": parts[1]})
        else:
            files.append({"path": f, "folder": None, "name": f})
            
    return templates.TemplateResponse("index.html", {"request": request, "files": files})

@app.get("/files/{filename:path}")
def get_file(
    filename: str, 
    api_key_query: str = Query(None, alias="api_key"),
    api_key_header: str = Header(None, alias="X-API-Key")
):
    """
    Retrieve a file. Public for Images. Protected for others.
    """
    try:
        # 1. Check if public image
        is_image = filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))
        
        # 2. If not image, enforce Auth
        if not is_image:
            # Manually check key since we removed Depends()
            key = api_key_query or api_key_header
            if not API_KEY:
                pass # Dev mode
            elif key != API_KEY:
                raise HTTPException(status_code=403, detail="Invalid API Key. Required for non-image files.")

        file_content = storage.get_file(filename)
        if file_content is None:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Guess mime type
        media_type, _ = mimetypes.guess_type(filename)
        if not media_type:
            media_type = "application/octet-stream"
            
        return Response(content=file_content, media_type=media_type)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/files")
async def upload_file(
    file: UploadFile = File(...), 
    folder: str = Query(None, description="Target folder path"),
    auth: str = Depends(get_api_key)
):
    """
    Upload a file to storage. Requires API Key.
    """
    try:
        content = await file.read()
        filename = file.filename
        if folder:
             # Sanitize folder path (basic)
             folder = folder.strip("/").replace("\\", "/")
             filename = f"{folder}/{filename}"
             
        storage.upload_file(filename, content)
        return {"filename": filename, "status": "uploaded", "mode": storage.mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files")
def list_files():
    """
    List all available files. Public Access.
    """
    return {"files": storage.list_files()}


# Valid image extensions for random selection
VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


@app.get("/images/random", tags=["Images"])
def get_random_images(count: int = Query(default=4, ge=1, le=20, description="Number of random images to return")):
    """
    Get random images from the STYLE_SYNC_SOURCE_FOLDER.
    Returns up to 'count' randomly selected image file paths.
    """
    source_folder = STYLE_SYNC_DEFAULT_SOURCE.strip("/")
    all_files = storage.list_files()
    
    # Filter to only images in the source folder
    images = []
    for file_path in all_files:
        # Check if file is in the source folder (or root if source is empty)
        if source_folder:
            if not file_path.startswith(source_folder + "/") and not file_path.startswith(source_folder):
                continue
        
        # Check if it's a valid image extension
        ext = Path(file_path).suffix.lower()
        if ext in VALID_IMAGE_EXTENSIONS:
            images.append(file_path)
    
    # Randomly select up to 'count' images
    selected_count = min(count, len(images))
    random_images = random.sample(images, selected_count) if images else []
    
    return {
        "source_folder": source_folder or "(root)",
        "total_images": len(images),
        "count": len(random_images),
        "images": random_images
    }


@app.get("/images/styled", tags=["Images"])
def get_styled_file(
    style: str = Query(..., description="The style name (e.g., 'Geometric 3D')"),
    id: str = Query(..., description="The image filename to look up. Use '-1' to get a random image.")
):
    """
    Get a styled file path and icon path by style name and filename.
    If id is '-1', returns a random image from the style folder.
    If style is not found, returns the original image.
    Returns 404 if no matching file exists.
    """
    # Load styles to validate style and get folder_name (case-insensitive)
    styles = load_styles_from_file()
    style_config = find_style_by_name(styles, style)
    
    # Get icon from style config (empty if style not found)
    icon_name = style_config.get("icon", "") if style_config else ""
    icon_folder = STYLE_SYNC_ICON_FOLDER.strip("/")
    icon_path = f"{icon_folder}/{icon_name}" if icon_folder and icon_name else icon_name
    
    # Determine the target folder based on whether style exists
    if style_config:
        # Get the folder_name from the style config
        style_folder = style_config.get("folder_name")
        if not style_folder:
            # Fallback: sanitize the style name
            style_folder = style.lower().replace(" ", "_")
        output_base = STYLE_SYNC_DEFAULT_TARGET.strip("/")
        target_folder = f"{output_base}/{style_folder}" if output_base else style_folder
    else:
        # Style not found - use original/source folder
        style_folder = "original"
        target_folder = STYLE_SYNC_DEFAULT_SOURCE.strip("/")
    
    # Handle random file selection when id is "-1"
    if id == "-1":
        all_files = storage.list_files()
        # Filter to images in the target folder
        folder_images = []
        for file_path in all_files:
            if target_folder:
                if not file_path.startswith(target_folder + "/") and not file_path.startswith(target_folder):
                    continue
            ext = Path(file_path).suffix.lower()
            if ext in VALID_IMAGE_EXTENSIONS:
                folder_images.append(file_path)
        
        if not folder_images:
            raise HTTPException(status_code=404, detail=f"No images found in folder: {target_folder or '(root)'}")
        
        # Select a random image
        styled_file_path = random.choice(folder_images)
        # Extract just the filename from the path
        actual_filename = Path(styled_file_path).name
    else:
        # Build the styled file path
        styled_file_path = f"{target_folder}/{id}" if target_folder else id
        actual_filename = id
        
        # Check if the file exists in storage
        file_content = storage.get_file(styled_file_path)
        if file_content is None:
            raise HTTPException(status_code=404, detail=f"Styled file not found: {styled_file_path}")
    
    return {
        "style": style if style_config else "original",
        "style_folder": style_folder,
        "file_path": styled_file_path,
        "id": actual_filename,
        "icon_path": icon_path,
        "icon_name": icon_name
    }


@app.get("/images/next", tags=["Images"])
def get_next_image(
    style: str = Query(..., description="The style name (e.g., 'Geometric 3D')"),
    id: str = Query(..., description="The current image filename to exclude")
):
    """
    Get a random next image for the given style, excluding the current image.
    If style is not found, returns a random original image.
    """
    # Load styles to validate style and get folder_name (case-insensitive)
    styles = load_styles_from_file()
    style_config = find_style_by_name(styles, style)
    
    # Get icon from style config (empty if style not found)
    icon_name = style_config.get("icon", "") if style_config else ""
    icon_folder = STYLE_SYNC_ICON_FOLDER.strip("/")
    icon_path = f"{icon_folder}/{icon_name}" if icon_folder and icon_name else icon_name
    
    # Determine the target folder based on whether style exists
    if style_config:
        style_folder = style_config.get("folder_name")
        if not style_folder:
            style_folder = style.lower().replace(" ", "_")
        output_base = STYLE_SYNC_DEFAULT_TARGET.strip("/")
        target_folder = f"{output_base}/{style_folder}" if output_base else style_folder
    else:
        style_folder = "original"
        target_folder = STYLE_SYNC_DEFAULT_SOURCE.strip("/")
    
    # Get all images in the target folder
    all_files = storage.list_files()
    folder_images = []
    for file_path in all_files:
        if target_folder:
            if not file_path.startswith(target_folder + "/") and not file_path.startswith(target_folder):
                continue
        ext = Path(file_path).suffix.lower()
        if ext in VALID_IMAGE_EXTENSIONS:
            folder_images.append(file_path)
    
    # Exclude the current image
    current_image_name = Path(id).name
    available_images = [
        img for img in folder_images 
        if Path(img).name != current_image_name
    ]
    
    if not available_images:
        raise HTTPException(
            status_code=404, 
            detail=f"No other images found in folder: {target_folder or '(root)'}"
        )
    
    # Select a random image from available ones
    next_file_path = random.choice(available_images)
    next_filename = Path(next_file_path).name
    
    return {
        "style": style if style_config else "original",
        "style_folder": style_folder,
        "file_path": next_file_path,
        "id": next_filename,
        "icon_path": icon_path,
        "icon_name": icon_name,
        "excluded": current_image_name
    }


@app.delete("/files/{filename:path}")
def delete_file(
    filename: str, 
    auth: str = Depends(get_api_key)
):
    """
    Delete a file. Requires API Key.
    """
    try:
        storage.delete_file(filename)
        return {"filename": filename, "status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/folders/{folder_path:path}")
def delete_folder(
    folder_path: str,
    auth: str = Depends(get_api_key)
):
    """
    Delete all files within a folder. Requires API Key.
    """
    try:
        result = storage.delete_folder(folder_path)
        return {
            "folder": folder_path,
            "status": "deleted",
            "deleted_count": result["deleted_count"],
            "deleted_files": result["deleted_files"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# StyleSync API Endpoints
# =============================================================================

class StyleSyncRequest(BaseModel):
    """Request body for StyleSync operation."""
    source_path: Optional[str] = Field(default=None, description="Source directory path containing images. Falls back to STYLE_SYNC_DEFAULT_SOURCE_FOLDER env var if not provided.")
    output_path: Optional[str] = Field(default=None, description="Output directory for styled images. Falls back to STYLE_SYNC_DEFAULT_TARGET_FOLDER env var if not provided.")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_path": "originals/",
                "output_path": "styled/"
            }
        }


class StyleSyncResponse(BaseModel):
    """Response from StyleSync operation."""
    status: str
    source: str
    output: str
    processed: List[str]
    failed: List[str]
    skipped: List[str]
    deleted: List[str] = []  # Orphaned files that were deleted
    error: Optional[str] = None


# Store for tracking background sync jobs
sync_jobs: dict = {}


@app.post("/stylesync", response_model=StyleSyncResponse, tags=["StyleSync"])
def run_stylesync(
    request: StyleSyncRequest,
    auth: str = Depends(get_api_key)
):
    """
    Execute StyleSync operation synchronously.
    
    Applies AI style transformations to images in the source path
    and saves results to the output path. Styles are loaded from styles.json.
    This operation runs synchronously and may take time depending on the number of images.
    
    Requires API Key authentication.
    """
    try:
        # Load styles from file
        styles = load_styles_from_file()
        
        if not styles:
            raise HTTPException(status_code=400, detail="No styles configured in styles.json")
        
        # Use request values or fall back to environment defaults
        source_path = request.source_path if request.source_path is not None else STYLE_SYNC_DEFAULT_SOURCE
        output_path = request.output_path if request.output_path is not None else STYLE_SYNC_DEFAULT_TARGET
        
        result = stylesync_service.process_sync(
            source_path=source_path,
            output_path=output_path,
            styles=styles,
            provider="azure"
        )
        
        return StyleSyncResponse(
            status=result.status,
            source=result.source,
            output=result.output,
            processed=result.processed,
            failed=result.failed,
            skipped=result.skipped,
            deleted=result.deleted,
            error=result.error
        )
        
    except FileNotFoundError as e:
        logger.error(f"Styles file not found: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"StyleSync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stylesync/async", tags=["StyleSync"])
async def run_stylesync_async(
    request: StyleSyncRequest,
    background_tasks: BackgroundTasks,
    auth: str = Depends(get_api_key)
):
    """
    Execute StyleSync operation asynchronously in the background.
    
    Styles are loaded from styles.json. Returns immediately with a job ID.
    Use GET /stylesync/status/{job_id} to check the status of the operation.
    
    Requires API Key authentication.
    """
    import uuid
    job_id = str(uuid.uuid4())
    
    # Load styles from file (validate before starting job)
    try:
        styles = load_styles_from_file()
        if not styles:
            raise HTTPException(status_code=400, detail="No styles configured in styles.json")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Use request values or fall back to environment defaults
    source_path = request.source_path if request.source_path is not None else STYLE_SYNC_DEFAULT_SOURCE
    output_path = request.output_path if request.output_path is not None else STYLE_SYNC_DEFAULT_TARGET
    
    # Initialize job status
    sync_jobs[job_id] = {
        "status": "running",
        "source": source_path,
        "output": output_path,
        "processed": [],
        "failed": [],
        "skipped": [],
        "deleted": [],
        "error": None
    }
    
    def run_sync_job():
        try:
            result = stylesync_service.process_sync(
                source_path=source_path,
                output_path=output_path,
                styles=styles,
                provider="azure"
            )
            sync_jobs[job_id] = {
                "status": result.status,
                "source": result.source,
                "output": result.output,
                "processed": result.processed,
                "failed": result.failed,
                "skipped": result.skipped,
                "deleted": result.deleted,
                "error": result.error
            }
        except Exception as e:
            sync_jobs[job_id]["status"] = "failed"
            sync_jobs[job_id]["error"] = str(e)
    
    background_tasks.add_task(run_sync_job)
    
    return {
        "job_id": job_id,
        "status": "started",
        "message": "StyleSync job started. Use GET /stylesync/status/{job_id} to check progress."
    }


@app.get("/stylesync/status/{job_id}", response_model=StyleSyncResponse, tags=["StyleSync"])
def get_stylesync_status(job_id: str):
    """
    Get the status of an async StyleSync job.
    
    Returns the current status and results of a background sync operation.
    """
    if job_id not in sync_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = sync_jobs[job_id]
    return StyleSyncResponse(
        status=job["status"],
        source=job["source"],
        output=job["output"],
        processed=job["processed"],
        failed=job["failed"],
        skipped=job["skipped"],
        deleted=job.get("deleted", []),
        error=job["error"]
    )


@app.get("/stylesync/images", tags=["StyleSync"])
def list_styleable_images(
    source_path: str = Query(default="", description="Source path to filter images")
):
    """
    List all valid images that can be styled.
    
    Returns images matching supported formats: .jpg, .jpeg, .png, .webp
    """
    images = stylesync_service.get_valid_images(source_path)
    return {
        "source_path": source_path,
        "count": len(images),
        "images": images
    }


@app.get("/stylesync/styles", tags=["StyleSync"])
def get_configured_styles():
    """
    Get the list of configured styles from styles.json.
    
    Returns all style configurations that will be applied during StyleSync.
    """
    try:
        styles = load_styles_from_file()
        return {
            "count": len(styles),
            "styles": styles
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stylesync/providers", tags=["StyleSync"])
def list_providers():
    """
    List available AI providers and their configuration status.
    """
    from .stylesync.clients.azure import AzureGenerator
    
    azure_gen = AzureGenerator()
    
    return {
        "providers": [
            {
                "name": "azure",
                "description": f"Azure OpenAI with {azure_gen.model} model",
                "configured": azure_gen.is_configured(),
                "model": azure_gen.model,
                "required_env_vars": [
                    AzureGenerator.ENV_ENDPOINT,
                    AzureGenerator.ENV_API_KEY
                ],
                "optional_env_vars": [
                    f"{AzureGenerator.ENV_MODEL} (default: {AzureGenerator.DEFAULT_MODEL})"
                ],
                "missing": azure_gen.get_missing_config() if not azure_gen.is_configured() else []
            }
        ]
    }

