from fastapi import FastAPI, UploadFile, HTTPException, File
from fastapi.responses import Response, JSONResponse
from .storage import StorageService
import mimetypes

app = FastAPI(title="Azure File Storage App")
storage = StorageService()

@app.get("/")
def read_root():
    return {"message": "Welcome to Azure File Storage App. Use /docs for API documentation."}

@app.get("/files/{filename}")
def get_file(filename: str):
    """
    Retrieve a file by its name.
    """
    try:
        file_content = storage.get_file(filename)
        if file_content is None:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Guess mime type
        media_type, _ = mimetypes.guess_type(filename)
        if not media_type:
            media_type = "application/octet-stream"
            
        return Response(content=file_content, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/files")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file to storage.
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
    List all available files.
    """
    return {"files": storage.list_files()}
