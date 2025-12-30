import os
import logging
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

class StyleDefinition(BaseModel):
    """Style configuration for image transformation."""
    index: int = Field(..., description="Unique style index (used in output filename)")
    name: str = Field(..., description="Human-readable style name")
    prompt_text: str = Field(..., description="AI prompt describing the style transformation")
    strength: float = Field(default=0.7, ge=0.0, le=1.0, description="Style intensity (0.0 - 1.0)")


class StyleSyncRequest(BaseModel):
    """Request body for StyleSync operation."""
    source_path: str = Field(default="", description="Source directory path containing images")
    output_path: str = Field(default="styled/", description="Output directory for styled images")
    styles: List[StyleDefinition] = Field(..., description="List of style configurations to apply")
    provider: str = Field(default="azure", description="AI provider: 'azure' or 'stability'")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_path": "originals/",
                "output_path": "styled/",
                "provider": "azure",
                "styles": [
                    {
                        "index": 1,
                        "name": "Watercolor",
                        "prompt_text": "Transform this image into a beautiful watercolor painting",
                        "strength": 0.7
                    }
                ]
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
    and saves results to the output path. This operation runs synchronously
    and may take time depending on the number of images.
    
    Requires API Key authentication.
    """
    try:
        # Convert Pydantic models to dicts
        styles = [s.model_dump() for s in request.styles]
        
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
    
    Returns immediately with a job ID. Use GET /stylesync/status/{job_id}
    to check the status of the operation.
    
    Requires API Key authentication.
    """
    import uuid
    job_id = str(uuid.uuid4())
    
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
            styles = [s.model_dump() for s in request.styles]
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
                "description": "Azure AI with Flux model",
                "configured": azure_gen.is_configured(),
                "required_env_vars": ["AZURE_ENDPOINT_URL", "AZURE_API_KEY"]
            },
            {
                "name": "stability",
                "description": "Stability AI with Stable Diffusion XL",
                "configured": stability_gen.is_configured(),
                "required_env_vars": ["STABILITY_API_KEY"]
            }
        ]
    }

