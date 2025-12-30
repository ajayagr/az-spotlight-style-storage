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
from .storage import StorageService
from .stylesync import StyleSyncService
import mimetypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Styles configuration file path
STYLES_FILE_PATH = Path(__file__).parent.parent / "styles.json"


def load_styles_from_file() -> List[dict]:
    """
    Load style configurations from styles.json file.
    """
    if not STYLES_FILE_PATH.exists():
        raise FileNotFoundError(f"Styles file not found: {STYLES_FILE_PATH}")
    
    with open(STYLES_FILE_PATH, "r") as f:
        data = json.load(f)
    
    return data.get("styles", [])

app = FastAPI(
    title="Azure File Storage App",
    description="File storage with AI-powered style transfer capabilities",
    version="2.0.0"
)
storage = StorageService()
stylesync_service = StyleSyncService(storage)

# Setup Templates
templates = Jinja2Templates(directory="app/templates")

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


# =============================================================================
# StyleSync API Endpoints
# =============================================================================

class StyleSyncRequest(BaseModel):
    """Request body for StyleSync operation."""
    source_path: str = Field(default="", description="Source directory path containing images")
    output_path: str = Field(default="styled/", description="Output directory for styled images")
    provider: str = Field(default="azure", description="AI provider: 'azure' or 'stability'")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_path": "originals/",
                "output_path": "styled/",
                "provider": "azure"
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
        
        result = stylesync_service.process_sync(
            source_path=request.source_path,
            output_path=request.output_path,
            styles=styles,
            provider=request.provider
        )
        
        return StyleSyncResponse(
            status=result.status,
            source=result.source,
            output=result.output,
            processed=result.processed,
            failed=result.failed,
            skipped=result.skipped,
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
    
    # Initialize job status
    sync_jobs[job_id] = {
        "status": "running",
        "source": request.source_path,
        "output": request.output_path,
        "processed": [],
        "failed": [],
        "skipped": [],
        "error": None
    }
    
    def run_sync_job():
        try:
            result = stylesync_service.process_sync(
                source_path=request.source_path,
                output_path=request.output_path,
                styles=styles,
                provider=request.provider
            )
            sync_jobs[job_id] = {
                "status": result.status,
                "source": result.source,
                "output": result.output,
                "processed": result.processed,
                "failed": result.failed,
                "skipped": result.skipped,
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
    from .stylesync.clients.stability import StabilityGenerator
    
    azure_gen = AzureGenerator()
    stability_gen = StabilityGenerator()
    
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
            },
            {
                "name": "stability",
                "description": "Stability AI with Stable Diffusion XL",
                "configured": stability_gen.is_configured(),
                "required_env_vars": ["STABILITY_API_KEY"],
                "missing": ["STABILITY_API_KEY"] if not stability_gen.is_configured() else []
            }
        ]
    }

