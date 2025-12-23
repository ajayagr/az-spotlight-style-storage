import os
from fastapi import FastAPI, UploadFile, HTTPException, File, Depends, Header, Query, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .storage import StorageService
import mimetypes

app = FastAPI(title="Azure File Storage App")
storage = StorageService()

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
    files = storage.list_files()
    return templates.TemplateResponse("index.html", {"request": request, "files": files})

@app.get("/files/{filename}")
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
    auth: str = Depends(get_api_key)
):
    """
    Upload a file to storage. Requires API Key.
    """
    try:
        content = await file.read()
        storage.upload_file(file.filename, content)
        return {"filename": file.filename, "status": "uploaded", "mode": storage.mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files")
def list_files():
    """
    List all available files. Public Access.
    """
    return {"files": storage.list_files()}
