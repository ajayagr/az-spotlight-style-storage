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
from .momentsync import MomentSyncService
import mimetypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Styles configuration file path
STYLES_FILE_PATH = Path(__file__).parent.parent / "styles.json"
MOMENTS_FILE_PATH = Path(__file__).parent.parent / "moments.json"

# StyleSync default folder configuration
STYLE_SYNC_DEFAULT_SOURCE = os.getenv("STYLE_SYNC_DEFAULT_SOURCE_FOLDER", "source/")
STYLE_SYNC_DEFAULT_TARGET = os.getenv("STYLE_SYNC_DEFAULT_TARGET_FOLDER", "styled/")
STYLE_SYNC_ICON_FOLDER = os.getenv("STYLE_SYNC_ICON_FOLDER", "icons/")

# MomentSync default folder configuration
MOMENT_SYNC_DEFAULT_OUTPUT = os.getenv("MOMENT_SYNC_DEFAULT_OUTPUT_FOLDER", "moments/")


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
momentsync_service = MomentSyncService(storage)


def load_moments_from_file() -> dict:
    """
    Load moment configurations from moments.json file.
    """
    if not MOMENTS_FILE_PATH.exists():
        raise FileNotFoundError(f"Moments file not found: {MOMENTS_FILE_PATH}")
    
    with open(MOMENTS_FILE_PATH, "r") as f:
        return json.load(f)


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
    api_key_header: str = Header(None, alias="X-API-Key"),
    if_none_match: str = Header(None, alias="If-None-Match")
):
    """
    Retrieve a file. Public for Images. Protected for others.
    Supports HTTP caching with ETag for images.
    """
    import hashlib
    
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
        
        # Set cache headers for images (1 day cache, revalidate)
        headers = {}
        if is_image:
            # Generate ETag from content hash for cache validation
            etag = hashlib.md5(file_content).hexdigest()
            etag_quoted = f'"{etag}"'
            
            # Check if browser has cached version (If-None-Match)
            if if_none_match and (if_none_match == etag_quoted or if_none_match == etag):
                return Response(status_code=304, headers={
                    "Cache-Control": "public, max-age=86400, must-revalidate",
                    "ETag": etag_quoted
                })
            
            headers = {
                "Cache-Control": "public, max-age=86400, must-revalidate",  # 1 day
                "ETag": etag_quoted
            }
            
        return Response(content=file_content, media_type=media_type, headers=headers)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/thumbnail/{filename:path}", tags=["Files"])
def get_thumbnail(
    filename: str,
    height: int = Query(default=140, ge=10, le=500, description="Thumbnail height in pixels"),
    if_none_match: str = Header(None, alias="If-None-Match")
):
    """
    Generate and return a thumbnail for an image file.
    
    Preserves aspect ratio based on the specified height (default 140px).
    Supports HTTP caching with ETag headers.
    Only works with image files (.png, .jpg, .jpeg, .gif, .bmp, .webp).
    """
    import hashlib
    from io import BytesIO
    
    try:
        from PIL import Image
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="Pillow library not installed. Run: pip install Pillow"
        )
    
    # Validate it's an image file
    is_image = filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))
    if not is_image:
        raise HTTPException(status_code=400, detail="Thumbnails only available for image files")
    
    try:
        file_content = storage.get_file(filename)
        if file_content is None:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Generate ETag from content + height for cache validation
        content_hash = hashlib.md5(file_content + str(height).encode()).hexdigest()
        etag_quoted = f'"{content_hash}"'
        
        # Check if browser has cached version
        if if_none_match and (if_none_match == etag_quoted or if_none_match == content_hash):
            return Response(status_code=304, headers={
                "Cache-Control": "public, max-age=604800, immutable",  # 7 days for thumbnails
                "ETag": etag_quoted
            })
        
        # Open image and create thumbnail
        img = Image.open(BytesIO(file_content))
        
        # Handle RGBA/transparency for formats that support it
        original_format = img.format or 'JPEG'
        
        # Calculate new dimensions preserving aspect ratio
        original_width, original_height = img.size
        aspect_ratio = original_width / original_height
        new_height = height
        new_width = int(new_height * aspect_ratio)
        
        # Use high-quality resampling
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Determine output format
        output_format = original_format
        media_type = "image/jpeg"
        
        if original_format.upper() in ('PNG', 'GIF', 'WEBP'):
            output_format = original_format.upper()
            media_type = f"image/{output_format.lower()}"
        else:
            # Convert to RGB for JPEG output (handles RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            output_format = 'JPEG'
            media_type = "image/jpeg"
        
        # Save thumbnail to bytes
        output = BytesIO()
        save_kwargs = {'format': output_format}
        if output_format == 'JPEG':
            save_kwargs['quality'] = 85
            save_kwargs['optimize'] = True
        elif output_format == 'PNG':
            save_kwargs['optimize'] = True
        elif output_format == 'WEBP':
            save_kwargs['quality'] = 85
        
        img.save(output, **save_kwargs)
        thumbnail_bytes = output.getvalue()
        
        return Response(
            content=thumbnail_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=604800, immutable",  # 7 days
                "ETag": etag_quoted
            }
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Thumbnail generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate thumbnail: {str(e)}")


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
    style: Optional[str] = Query(default=None, description="The style name (e.g., 'Geometric 3D'). If not provided with time/season, returns original moment variation."),
    id: str = Query(..., description="The image filename to look up. Use '-1' to get a random image."),
    time: Optional[str] = Query(default=None, description="Time of day for moment variation (e.g., 'morning', 'evening'). Case-insensitive."),
    season: Optional[str] = Query(default=None, description="Season for moment variation (e.g., 'summer', 'winter'). Case-insensitive.")
):
    """
    Get a styled file path and icon path by style name and filename.
    
    If time and/or season are provided, returns a moment-in-time variation.
    - With style + time/season: Returns moment variation of styled image
    - With only time/season (no style): Returns moment variation of original image
    
    If id is '-1', returns a random image from the target folder.
    If style is not found, returns the original image (or its moment variation).
    Returns 404 if no matching file exists.
    """
    # Load styles to validate style and get folder_name (case-insensitive)
    styles = load_styles_from_file()
    style_config = find_style_by_name(styles, style) if style else None
    
    # Get icon from style config (empty if style not found)
    icon_name = style_config.get("icon", "") if style_config else ""
    icon_folder = STYLE_SYNC_ICON_FOLDER.strip("/")
    icon_path = f"{icon_folder}/{icon_name}" if icon_folder and icon_name else icon_name
    
    # Determine the style folder based on whether style exists
    if style_config:
        # Get the folder_name from the style config
        style_folder = style_config.get("folder_name")
        if not style_folder:
            # Fallback: sanitize the style name
            style_folder = style.lower().replace(" ", "_")
    else:
        # Style not found or not provided - use original folder
        style_folder = "original"
    
    # Determine moment folder if time/season provided
    moment_folder = None
    time_config = None
    season_config = None
    
    if time or season:
        # Load moments config to validate time/season
        try:
            moments_config = load_moments_from_file()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="Moments configuration file not found")
        
        # Find matching time (case-insensitive)
        if time:
            time_lower = time.lower().strip()
            for t in moments_config.get("times_of_day", []):
                if t["name"].lower() == time_lower or t.get("folder_name", "").lower() == time_lower:
                    time_config = t
                    break
            if not time_config:
                raise HTTPException(status_code=400, detail=f"Invalid time of day: {time}. Valid options: morning, afternoon, evening, night")
        
        # Find matching season (case-insensitive)
        if season:
            season_lower = season.lower().strip()
            for s in moments_config.get("seasons", []):
                if s["name"].lower() == season_lower or s.get("folder_name", "").lower() == season_lower:
                    season_config = s
                    break
            if not season_config:
                raise HTTPException(status_code=400, detail=f"Invalid season: {season}. Valid options: summer, winter, rain, spring")
        
        # Build moment folder name
        if time_config and season_config:
            # Composite: time_season
            moment_folder = f"{time_config['folder_name']}_{season_config['folder_name']}"
        elif time_config:
            moment_folder = time_config["folder_name"]
        else:
            moment_folder = season_config["folder_name"]
    
    # Build target folder path
    if moment_folder:
        # Moment variation: moments/{style_folder}/{moment_folder}/
        moments_base = MOMENT_SYNC_DEFAULT_OUTPUT.strip("/")
        target_folder = f"{moments_base}/{style_folder}/{moment_folder}"
    elif style_config:
        # Styled image: styled/{style_folder}/
        output_base = STYLE_SYNC_DEFAULT_TARGET.strip("/")
        target_folder = f"{output_base}/{style_folder}" if output_base else style_folder
    else:
        # Original source image: source/
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
            raise HTTPException(status_code=404, detail=f"File not found: {styled_file_path}")
    
    response = {
        "style": style if style_config else "original",
        "style_folder": style_folder,
        "file_path": styled_file_path,
        "id": actual_filename,
        "icon_path": icon_path,
        "icon_name": icon_name
    }
    
    # Add moment info if applicable
    if moment_folder:
        response["moment_folder"] = moment_folder
        response["time"] = time_config["name"] if time_config else None
        response["season"] = season_config["name"] if season_config else None
    
    return response


@app.get("/images/styled/file", tags=["Images"])
def get_styled_image_file(
    style: Optional[str] = Query(default=None, description="The style name (e.g., 'Geometric 3D'). If not provided with time/season, returns original moment variation."),
    id: str = Query(..., description="The image filename to look up. Use '-1' to get a random image."),
    time: Optional[str] = Query(default=None, description="Time of day for moment variation (e.g., 'morning', 'evening'). Case-insensitive."),
    season: Optional[str] = Query(default=None, description="Season for moment variation (e.g., 'summer', 'winter'). Case-insensitive.")
):
    """
    Get a styled image file directly (returns the image, not metadata).
    
    Same parameters as /images/styled but returns the actual image file.
    
    If time and/or season are provided, returns a moment-in-time variation.
    - With style + time/season: Returns moment variation of styled image
    - With only time/season (no style): Returns moment variation of original image
    
    If id is '-1', returns a random image from the target folder.
    If style is not found, returns the original image (or its moment variation).
    Returns 404 if no matching file exists.
    """
    # Load styles to validate style and get folder_name (case-insensitive)
    styles = load_styles_from_file()
    style_config = find_style_by_name(styles, style) if style else None
    
    # Determine the style folder based on whether style exists
    if style_config:
        style_folder = style_config.get("folder_name")
        if not style_folder:
            style_folder = style.lower().replace(" ", "_")
    else:
        style_folder = "original"
    
    # Determine moment folder if time/season provided
    moment_folder = None
    time_config = None
    season_config = None
    
    if time or season:
        try:
            moments_config = load_moments_from_file()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="Moments configuration file not found")
        
        if time:
            time_lower = time.lower().strip()
            for t in moments_config.get("times_of_day", []):
                if t["name"].lower() == time_lower or t.get("folder_name", "").lower() == time_lower:
                    time_config = t
                    break
            if not time_config:
                raise HTTPException(status_code=400, detail=f"Invalid time of day: {time}. Valid options: morning, afternoon, evening, night")
        
        if season:
            season_lower = season.lower().strip()
            for s in moments_config.get("seasons", []):
                if s["name"].lower() == season_lower or s.get("folder_name", "").lower() == season_lower:
                    season_config = s
                    break
            if not season_config:
                raise HTTPException(status_code=400, detail=f"Invalid season: {season}. Valid options: summer, winter, rain, spring")
        
        if time_config and season_config:
            moment_folder = f"{time_config['folder_name']}_{season_config['folder_name']}"
        elif time_config:
            moment_folder = time_config["folder_name"]
        else:
            moment_folder = season_config["folder_name"]
    
    # Build target folder path
    if moment_folder:
        moments_base = MOMENT_SYNC_DEFAULT_OUTPUT.strip("/")
        target_folder = f"{moments_base}/{style_folder}/{moment_folder}"
    elif style_config:
        output_base = STYLE_SYNC_DEFAULT_TARGET.strip("/")
        target_folder = f"{output_base}/{style_folder}" if output_base else style_folder
    else:
        target_folder = STYLE_SYNC_DEFAULT_SOURCE.strip("/")
    
    # Handle random file selection when id is "-1"
    if id == "-1":
        all_files = storage.list_files()
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
        
        styled_file_path = random.choice(folder_images)
    else:
        styled_file_path = f"{target_folder}/{id}" if target_folder else id
    
    # Get the file content
    file_content = storage.get_file(styled_file_path)
    if file_content is None:
        raise HTTPException(status_code=404, detail=f"File not found: {styled_file_path}")
    
    # Determine content type
    ext = Path(styled_file_path).suffix.lower()
    content_type = mimetypes.guess_type(styled_file_path)[0] or "application/octet-stream"
    
    return Response(content=file_content, media_type=content_type)


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


@app.get("/images/variations/{image_id}", tags=["Images"])
def get_image_variations(image_id: str):
    """
    Get all styled and moment variations available for a source image.
    
    Accepts image name without extension (e.g., "photo1" instead of "photo1.jpg").
    Returns only variations that exist, with compact output (style_name + file_path).
    """
    # Get all files from storage
    all_files = set(storage.list_files())  # Use set for O(1) lookup
    
    # Build paths to check
    source_folder = STYLE_SYNC_DEFAULT_SOURCE.strip("/")
    styled_folder = STYLE_SYNC_DEFAULT_TARGET.strip("/")
    moments_folder = MOMENT_SYNC_DEFAULT_OUTPUT.strip("/")
    
    # Find the source image by name (without extension)
    # Look for first matching file in source folder
    source_prefix = f"{source_folder}/" if source_folder else ""
    source_path = None
    image_name = None
    
    for file_path in sorted(all_files):  # Sort for consistent results
        if file_path.startswith(source_prefix):
            # Get filename without the source folder prefix
            filename = file_path[len(source_prefix):] if source_prefix else file_path
            # Skip files in subfolders
            if "/" in filename:
                continue
            # Check if filename (without extension) matches image_id
            name_without_ext = Path(filename).stem
            if name_without_ext == image_id:
                source_path = file_path
                image_name = filename
                break
    
    if not source_path:
        raise HTTPException(
            status_code=404, 
            detail=f"Source image not found with name: {image_id}"
        )
    
    # Load styles configuration
    styles = load_styles_from_file()
    
    # Load moments configuration if available
    try:
        moments_config = load_moments_from_file()
        has_moments = True
    except FileNotFoundError:
        moments_config = None
        has_moments = False
    
    # Build styled variations - only include existing files
    styled_variations = []
    for style in styles:
        style_folder_name = style.get("folder_name", style["name"].lower().replace(" ", "_"))
        styled_path = f"{styled_folder}/{style_folder_name}/{image_name}" if styled_folder else f"{style_folder_name}/{image_name}"
        
        if styled_path in all_files:
            styled_variations.append({
                "style": style["name"],
                "path": styled_path
            })
    
    # Build moment variations - only include existing files
    moment_variations = []
    if has_moments and moments_config:
        times = moments_config.get("times_of_day", [])
        seasons = moments_config.get("seasons", [])
        
        # Build all moment folder combinations
        moment_folders = []
        for t in times:
            moment_folders.append({"name": t["name"], "folder": t["folder_name"]})
        for s in seasons:
            moment_folders.append({"name": s["name"], "folder": s["folder_name"]})
        for t in times:
            for s in seasons:
                moment_folders.append({
                    "name": f"{t['name']} + {s['name']}",
                    "folder": f"{t['folder_name']}_{s['folder_name']}"
                })
        
        # Check each style's moment variations
        for style in styles:
            style_folder_name = style.get("folder_name", style["name"].lower().replace(" ", "_"))
            
            for moment in moment_folders:
                moment_path = f"{moments_folder}/{style_folder_name}/{moment['folder']}/{image_name}" if moments_folder else f"{style_folder_name}/{moment['folder']}/{image_name}"
                
                if moment_path in all_files:
                    moment_variations.append({
                        "style": style["name"],
                        "moment": moment["name"],
                        "path": moment_path
                    })
    
    return {
        "image_id": image_id,
        "image_file": image_name,
        "source_path": source_path,
        "styled_count": len(styled_variations),
        "moment_count": len(moment_variations),
        "styled": styled_variations,
        "moments": moment_variations
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
    # Expected counts (available immediately for async jobs)
    total_expected: int = 0  # Total images expected to be generated
    to_generate: int = 0     # Number of images to be generated (missing)
    to_skip: int = 0         # Number of images to be skipped (already exist)
    to_delete: int = 0       # Number of orphaned files to be deleted
    # Results (populated as processing completes)
    processed: List[str] = []
    failed: List[str] = []
    skipped: List[str] = []
    deleted: List[str] = []  # Orphaned files that were deleted
    error: Optional[str] = None
    created_at: Optional[str] = None  # ISO timestamp when job was created


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
        
        # Calculate counts from results
        to_generate = len(result.processed) + len(result.failed)
        to_skip = len(result.skipped)
        to_delete = len(result.deleted)
        total_expected = to_generate + to_skip
        
        return StyleSyncResponse(
            status=result.status,
            source=result.source,
            output=result.output,
            total_expected=total_expected,
            to_generate=to_generate,
            to_skip=to_skip,
            to_delete=to_delete,
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
    
    # Calculate expected counts before starting the job
    from .stylesync.sync import StyleConfig
    style_configs = [
        StyleConfig(
            index=s.get("index", 0),
            name=s["name"],
            prompt_text=s["prompt_text"],
            folder_name=s.get("folder_name", ""),
            strength=s.get("strength", 0.7)
        )
        for s in styles
    ]
    
    # Map expected state and calculate counts
    expected_state = stylesync_service.map_expected_state(source_path, style_configs)
    missing_tasks = stylesync_service.get_missing_files(expected_state, output_path)
    style_folders = [sc.folder_name if sc.folder_name else sc.name.lower().replace(' ', '_') for sc in style_configs]
    orphaned_files = stylesync_service.get_orphaned_files(expected_state, output_path, style_folders)
    
    total_expected = len(expected_state)
    to_generate = len(missing_tasks)
    to_skip = total_expected - to_generate
    to_delete = len(orphaned_files)
    
    # Initialize job status with counts
    from datetime import datetime
    sync_jobs[job_id] = {
        "status": "running",
        "source": source_path,
        "output": output_path,
        "total_expected": total_expected,
        "to_generate": to_generate,
        "to_skip": to_skip,
        "to_delete": to_delete,
        "processed": [],
        "failed": [],
        "skipped": [],
        "deleted": [],
        "error": None,
        "created_at": datetime.utcnow().isoformat()
    }
    
    def run_sync_job():
        try:
            result = stylesync_service.process_sync(
                source_path=source_path,
                output_path=output_path,
                styles=styles,
                provider="azure"
            )
            sync_jobs[job_id].update({
                "status": result.status,
                "processed": result.processed,
                "failed": result.failed,
                "skipped": result.skipped,
                "deleted": result.deleted,
                "error": result.error
            })
        except Exception as e:
            sync_jobs[job_id]["status"] = "failed"
            sync_jobs[job_id]["error"] = str(e)
    
    background_tasks.add_task(run_sync_job)
    
    return {
        "job_id": job_id,
        "status": "started",
        "message": "StyleSync job started. Use GET /stylesync/status/{job_id} to check progress.",
        "total_expected": total_expected,
        "to_generate": to_generate,
        "to_skip": to_skip,
        "to_delete": to_delete
    }


@app.get("/stylesync/status/{job_id}", response_model=StyleSyncResponse, tags=["StyleSync"])
def get_stylesync_status(job_id: str):
    """
    Get the status of an async StyleSync job.
    
    Returns the current status and results of a background sync operation.
    """
    if job_id not in sync_jobs:
        raise HTTPException(
            status_code=404, 
            detail=f"Job not found: {job_id}. Jobs are stored in-memory and may be lost if the server restarts. Active jobs: {len(sync_jobs)}"
        )
    
    job = sync_jobs[job_id]
    return StyleSyncResponse(
        status=job["status"],
        source=job["source"],
        output=job["output"],
        total_expected=job.get("total_expected", 0),
        to_generate=job.get("to_generate", 0),
        to_skip=job.get("to_skip", 0),
        to_delete=job.get("to_delete", 0),
        processed=job["processed"],
        failed=job["failed"],
        skipped=job["skipped"],
        deleted=job.get("deleted", []),
        error=job["error"],
        created_at=job.get("created_at")
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


@app.get("/stylesync/jobs", tags=["StyleSync"])
def list_stylesync_jobs():
    """
    List all active StyleSync jobs.
    
    Jobs are stored in-memory and will be lost on server restart.
    """
    jobs = []
    for job_id, job in sync_jobs.items():
        jobs.append({
            "job_id": job_id,
            "status": job["status"],
            "source": job["source"],
            "output": job["output"],
            "total_expected": job.get("total_expected", 0),
            "to_generate": job.get("to_generate", 0),
            "processed_count": len(job.get("processed", [])),
            "failed_count": len(job.get("failed", [])),
            "created_at": job.get("created_at")
        })
    return {
        "count": len(jobs),
        "jobs": jobs
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


# ============================================================================
# MomentSync API Endpoints
# ============================================================================

class MomentSyncRequest(BaseModel):
    """Request body for MomentSync operation."""
    styled_path: Optional[str] = Field(
        default=None,
        description="Path containing styled images. Falls back to STYLE_SYNC_DEFAULT_TARGET_FOLDER env var."
    )
    output_path: Optional[str] = Field(
        default=None,
        description="Output path for moment variations. Falls back to MOMENT_SYNC_DEFAULT_OUTPUT_FOLDER env var."
    )
    style_folders: Optional[List[str]] = Field(
        default=None,
        description="Specific style folders to process. If empty, processes all style folders including 'original'."
    )


class MomentSyncResponse(BaseModel):
    """Response from MomentSync operation."""
    status: str
    source: str
    output: str
    # Expected counts (available immediately for async jobs)
    total_expected: int = 0  # Total moment images expected
    to_generate: int = 0     # Number of images to be generated (missing)
    to_skip: int = 0         # Number of images to be skipped (already exist)
    to_delete: int = 0       # Number of orphaned files to be deleted
    # Results (populated as processing completes)
    processed: List[str] = []
    failed: List[str] = []
    skipped: List[str] = []
    deleted: List[str] = []
    error: Optional[str] = None
    created_at: Optional[str] = None  # ISO timestamp when job was created


# Store for tracking background moment sync jobs
moment_sync_jobs: dict = {}


@app.post("/momentsync", response_model=MomentSyncResponse, tags=["MomentSync"])
def run_momentsync(
    request: MomentSyncRequest,
    auth: str = Depends(get_api_key)
):
    """
    Execute MomentSync operation synchronously.
    
    Applies time-of-day and season transformations to styled images.
    Creates 24 variations per styled image (4 times + 4 seasons + 16 composites).
    Moments configuration is loaded from moments.json.
    This operation runs synchronously and may take significant time.
    
    Requires API Key authentication.
    """
    try:
        # Load moments config
        moments_config = load_moments_from_file()
        
        # Use request values or fall back to environment defaults
        styled_path = request.styled_path if request.styled_path is not None else STYLE_SYNC_DEFAULT_TARGET
        output_path = request.output_path if request.output_path is not None else MOMENT_SYNC_DEFAULT_OUTPUT
        
        result = momentsync_service.process_sync(
            styled_path=styled_path,
            output_path=output_path,
            moments_config=moments_config,
            style_folders=request.style_folders,
            provider="azure"
        )
        
        # Calculate counts from results
        to_generate = len(result.processed) + len(result.failed)
        to_skip = len(result.skipped)
        to_delete = len(result.deleted)
        total_expected = to_generate + to_skip
        
        return MomentSyncResponse(
            status=result.status,
            source=result.source,
            output=result.output,
            total_expected=total_expected,
            to_generate=to_generate,
            to_skip=to_skip,
            to_delete=to_delete,
            processed=result.processed,
            failed=result.failed,
            skipped=result.skipped,
            deleted=result.deleted,
            error=result.error
        )
        
    except FileNotFoundError as e:
        logger.error(f"Moments file not found: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"MomentSync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/momentsync/async", tags=["MomentSync"])
async def run_momentsync_async(
    request: MomentSyncRequest,
    background_tasks: BackgroundTasks,
    auth: str = Depends(get_api_key)
):
    """
    Execute MomentSync operation asynchronously in the background.
    
    Moments configuration is loaded from moments.json. Returns immediately with a job ID.
    Use GET /momentsync/status/{job_id} to check the status of the operation.
    
    Requires API Key authentication.
    """
    import uuid
    job_id = str(uuid.uuid4())
    
    # Load moments config (validate before starting job)
    try:
        moments_config = load_moments_from_file()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Use request values or fall back to environment defaults
    styled_path = request.styled_path if request.styled_path is not None else STYLE_SYNC_DEFAULT_TARGET
    output_path = request.output_path if request.output_path is not None else MOMENT_SYNC_DEFAULT_OUTPUT
    
    # Calculate expected counts before starting the job
    # Get style folders to process (including 'original' folder)
    all_files = momentsync_service.storage.list_files()
    available_style_folders = set()
    normalized_styled = styled_path.strip("/")
    for f in all_files:
        if f.startswith(normalized_styled + "/"):
            rel = f[len(normalized_styled) + 1:]
            parts = rel.split("/")
            if len(parts) >= 2:
                available_style_folders.add(parts[0])
    
    style_folders_to_process = request.style_folders if request.style_folders else list(available_style_folders)
    
    # Build moments and calculate expected state
    times, seasons, composites = momentsync_service.build_moments(moments_config)
    styled_images = momentsync_service.get_styled_images(styled_path, style_folders_to_process)
    expected_state = momentsync_service.map_expected_state(styled_images, times, seasons, composites)
    missing_tasks = momentsync_service.get_missing_files(expected_state, output_path)
    
    # Get moment folder names for orphan detection
    moment_folders = [t.folder_name for t in times] + [s.folder_name for s in seasons] + [c.folder_name for c in composites]
    orphaned_files = momentsync_service.get_orphaned_files(expected_state, output_path, style_folders_to_process, moment_folders)
    
    total_expected = len(expected_state)
    to_generate = len(missing_tasks)
    to_skip = total_expected - to_generate
    to_delete = len(orphaned_files)
    
    # Initialize job status with counts
    from datetime import datetime
    moment_sync_jobs[job_id] = {
        "status": "running",
        "source": styled_path,
        "output": output_path,
        "total_expected": total_expected,
        "to_generate": to_generate,
        "to_skip": to_skip,
        "to_delete": to_delete,
        "processed": [],
        "failed": [],
        "skipped": [],
        "deleted": [],
        "error": None,
        "created_at": datetime.utcnow().isoformat()
    }
    
    def run_moment_sync_background():
        try:
            result = momentsync_service.process_sync(
                styled_path=styled_path,
                output_path=output_path,
                moments_config=moments_config,
                style_folders=request.style_folders,
                provider="azure"
            )
            moment_sync_jobs[job_id].update({
                "status": result.status,
                "processed": result.processed,
                "failed": result.failed,
                "skipped": result.skipped,
                "deleted": result.deleted,
                "error": result.error
            })
        except Exception as e:
            logger.error(f"Background MomentSync error: {e}")
            moment_sync_jobs[job_id]["status"] = "failed"
            moment_sync_jobs[job_id]["error"] = str(e)
    
    background_tasks.add_task(run_moment_sync_background)
    
    return {
        "job_id": job_id,
        "status": "started",
        "message": "MomentSync job started in background",
        "styled_path": styled_path,
        "output_path": output_path,
        "total_expected": total_expected,
        "to_generate": to_generate,
        "to_skip": to_skip,
        "to_delete": to_delete
    }


@app.get("/momentsync/status/{job_id}", tags=["MomentSync"])
def get_momentsync_status(job_id: str):
    """
    Check the status of a background MomentSync job.
    
    Returns the current status and results of the specified job.
    """
    if job_id not in moment_sync_jobs:
        raise HTTPException(
            status_code=404, 
            detail=f"Job not found: {job_id}. Jobs are stored in-memory and may be lost if the server restarts. Active jobs: {len(moment_sync_jobs)}"
        )
    
    job = moment_sync_jobs[job_id]
    return MomentSyncResponse(
        status=job["status"],
        source=job["source"],
        output=job["output"],
        total_expected=job.get("total_expected", 0),
        to_generate=job.get("to_generate", 0),
        to_skip=job.get("to_skip", 0),
        to_delete=job.get("to_delete", 0),
        processed=job.get("processed", []),
        failed=job.get("failed", []),
        skipped=job.get("skipped", []),
        deleted=job.get("deleted", []),
        error=job["error"],
        created_at=job.get("created_at")
    )


@app.get("/momentsync/jobs", tags=["MomentSync"])
def list_momentsync_jobs():
    """
    List all active MomentSync jobs.
    
    Jobs are stored in-memory and will be lost on server restart.
    """
    jobs = []
    for job_id, job in moment_sync_jobs.items():
        jobs.append({
            "job_id": job_id,
            "status": job["status"],
            "source": job["source"],
            "output": job["output"],
            "total_expected": job.get("total_expected", 0),
            "to_generate": job.get("to_generate", 0),
            "processed_count": len(job.get("processed", [])),
            "failed_count": len(job.get("failed", [])),
            "created_at": job.get("created_at")
        })
    return {
        "count": len(jobs),
        "jobs": jobs
    }


# ============================================================================
# Image Restyle API Endpoint
# ============================================================================

class RestyleRequest(BaseModel):
    """Request body for image restyle operation."""
    prompt: str = Field(..., description="The prompt describing the desired style transformation")


@app.post("/image/restyle", tags=["Images"])
async def restyle_image(
    file: UploadFile = File(..., description="The image file to restyle"),
    prompt: str = Query(..., description="The prompt describing the desired style transformation"),
    auth: str = Depends(get_api_key)
):
    """
    Restyle an image using the Flux Kontext model.
    
    Takes an input image and a prompt, and generates a new styled image
    using the Azure AI endpoint with the Flux Kontext model.
    The output image preserves the original image dimensions.
    
    Requires API Key authentication.
    
    Returns the restyled image as a binary response.
    """
    from io import BytesIO
    
    try:
        from PIL import Image
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Pillow library not installed. Run: pip install Pillow"
        )
    
    from .stylesync.clients import get_generator, GeneratorResult
    
    # Validate file is an image
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    
    # Read the uploaded image
    try:
        image_data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(e)}")
    
    # Get original image dimensions
    try:
        original_image = Image.open(BytesIO(image_data))
        original_width, original_height = original_image.size
        original_format = original_image.format or "PNG"
        original_mode = original_image.mode
        logger.info(f"Original image dimensions: {original_width}x{original_height}, format: {original_format}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse image: {str(e)}")
    
    # Get the Azure generator
    try:
        generator = get_generator("azure")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize AI generator: {str(e)}")
    
    if not generator.is_configured():
        missing = generator.get_missing_config()
        raise HTTPException(
            status_code=503,
            detail=f"AI generator not configured. Missing environment variables: {', '.join(missing)}"
        )
    
    # Process the image with the prompt
    try:
        result: GeneratorResult = generator.process_image_bytes(
            image_data=image_data,
            filename=file.filename or "image.png",
            prompt=prompt,
            strength=1.0  # Full strength for restyle
        )
    except Exception as e:
        logger.error(f"Error during image processing: {e}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")
    
    if not result.success:
        logger.error(f"Restyle failed. Response info: {result.response_info}")
        raise HTTPException(
            status_code=500,
            detail=f"Image restyle failed. {result.response_info}"
        )
    
    # Resize the result to match original dimensions
    try:
        restyled_image = Image.open(BytesIO(result.data))
        
        # Only resize if dimensions differ
        if restyled_image.size != (original_width, original_height):
            logger.info(f"Resizing from {restyled_image.size} to {original_width}x{original_height}")
            restyled_image = restyled_image.resize(
                (original_width, original_height),
                Image.Resampling.LANCZOS
            )
        
        # Convert mode if necessary (handle RGBA for JPEG)
        output_format = original_format.upper()
        if output_format == "JPEG" and restyled_image.mode in ('RGBA', 'LA', 'P'):
            # Convert to RGB for JPEG
            background = Image.new('RGB', restyled_image.size, (255, 255, 255))
            if restyled_image.mode == 'P':
                restyled_image = restyled_image.convert('RGBA')
            if restyled_image.mode == 'RGBA':
                background.paste(restyled_image, mask=restyled_image.split()[-1])
            else:
                background.paste(restyled_image)
            restyled_image = background
        
        # Save to bytes
        output_buffer = BytesIO()
        save_kwargs = {'format': output_format}
        if output_format == 'JPEG':
            save_kwargs['quality'] = 95
        elif output_format == 'WEBP':
            save_kwargs['quality'] = 95
        
        restyled_image.save(output_buffer, **save_kwargs)
        output_bytes = output_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error resizing result image: {e}")
        # Return the original result if resizing fails
        output_bytes = result.data
        output_format = "PNG"
    
    # Determine content type
    content_type_map = {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
        "BMP": "image/bmp"
    }
    content_type = content_type_map.get(output_format.upper(), "image/png")
    
    return Response(
        content=output_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="restyled_{file.filename or "image.png"}"',
            "X-Original-Dimensions": f"{original_width}x{original_height}",
            "X-Prompt": prompt[:100]  # Truncate prompt for header safety
        }
    )


@app.get("/momentsync/moments", tags=["MomentSync"])
def get_configured_moments():
    """
    Get the list of configured moments from moments.json.
    
    Returns all time-of-day and season configurations.
    """
    try:
        config = load_moments_from_file()
        times = config.get("times_of_day", [])
        seasons = config.get("seasons", [])
        
        # Build composite list
        composites = []
        for t in times:
            for s in seasons:
                composites.append({
                    "name": f"{t['name']} + {s['name']}",
                    "folder_name": f"{t.get('folder_name', t['name'].lower())}_{s.get('folder_name', s['name'].lower())}"
                })
        
        return {
            "times_of_day": {
                "count": len(times),
                "items": times
            },
            "seasons": {
                "count": len(seasons),
                "items": seasons
            },
            "composites": {
                "count": len(composites),
                "items": composites
            },
            "total_variations": len(times) + len(seasons) + len(composites)
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
