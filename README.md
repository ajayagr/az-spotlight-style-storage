# Azure Spotlight Style Storage

A comprehensive Azure-based file storage and AI image style transfer application. This project provides a FastAPI web application for file management with Azure Blob Storage, featuring integrated AI-powered image style transformations using Azure OpenAI.

## 🌟 Features

- **Dual Storage Mode**: Seamlessly switch between Azure Blob Storage and local file system storage
- **File Management API**: RESTful API for uploading, downloading, listing, and deleting files
- **Web UI**: Built-in file explorer interface with grid/list view toggle
- **Integrated AI Style Transfer**: Built-in StyleSync service for batch processing images with AI-generated styles
- **Azure OpenAI Integration**: Uses Azure OpenAI Flux model for high-quality image generation
- **Sync & Async Operations**: Run style transfers synchronously or as background jobs
- **API Key Authentication**: Secure endpoints with configurable API key protection
- **Docker Support**: Ready-to-deploy containerized application

---

## 📁 Project Structure

```
az-spotlight-style-storage/
├── .github/
│   └── workflows/                    # CI/CD Pipelines
│       ├── azure-devops.yml          # Auto-deploy on push
│       └── manual-deploy.yml         # Manual deployment trigger
├── app/                              # FastAPI Web Application
│   ├── main.py                       # FastAPI routes and API endpoints
│   ├── storage.py                    # Storage service (Azure/Local)
│   ├── templates/
│   │   └── index.html                # File explorer web UI
│   └── stylesync/                    # Integrated StyleSync module
│       ├── __init__.py               # Module exports
│       ├── sync.py                   # Sync service and logic
│       └── clients/                  # AI generator clients
│           ├── __init__.py           # Client factory
│           ├── base.py               # Base generator class
│           └── azure.py              # Azure OpenAI generator
├── Dockerfile                        # Container configuration
├── requirements.txt                  # Python dependencies
├── sample.REST                       # Sample API requests
└── styles.json                       # Style transformation configurations
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- Azure Storage Account (optional, for cloud storage)
- Azure OpenAI API access (for style transfer function)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd az-spotlight-style-storage
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   .\venv\Scripts\activate   # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   # For Azure Blob Storage (optional - defaults to local storage)
   export AZURE_STORAGE_CONNECTION_STRING="your-connection-string"
   export CONTAINER_NAME="file-container"
   
   # For API authentication
   export API_KEY="your-secure-api-key"
   ```

5. **Run the application**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

### Docker Deployment

```bash
# Build the image
docker build -t az-spotlight-storage .

# Run the container
docker run -p 8000:8000 \
  -e AZURE_STORAGE_CONNECTION_STRING="your-connection-string" \
  -e API_KEY="your-api-key" \
  az-spotlight-storage
```

---

## 📖 API Reference

### Base URL
```
http://localhost:8000
```

### Authentication

The API supports two authentication methods:

1. **Header**: `X-API-Key: your-api-key`
2. **Query Parameter**: `?api_key=your-api-key`

> **Note**: Image files (`.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp`) can be accessed publicly without authentication.

---

## 🌐 Web UI

#### Home Page

```http
GET /
```

Returns the HTML file explorer interface with file management capabilities.

**Response**: HTML page with file browser

---

## 📁 File Management APIs

### 1. List All Files

```http
GET /files
```

Retrieves a list of all files in storage.

**Authentication**: Not required

**Response**:
```json
{
  "files": [
    "images/photo1.jpg",
    "documents/report.pdf",
    "styles/watercolor/image_1.png"
  ]
}
```

---

### 2. Upload a File

```http
POST /files
```

Upload a file to storage.

**Authentication**: Required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `file` | file | form-data | The file to upload (required) |
| `folder` | string | query | Target folder path (optional) |

**Example**:
```bash
curl -X POST "http://localhost:8000/files?folder=images" \
  -H "X-API-Key: your-api-key" \
  -F "file=@photo.jpg"
```

**Response**:
```json
{
  "filename": "images/photo.jpg",
  "status": "uploaded",
  "mode": "AZURE"
}
```

---

### 3. Get/Download a File

```http
GET /files/{filename}
```

Download a file from storage.

**Authentication**: 
- **Not required** for image files
- **Required** for non-image files

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `filename` | string | path | Full path to the file |

**Example**:
```bash
# Public image access
curl "http://localhost:8000/files/images/photo.jpg" --output photo.jpg

# Protected file access
curl "http://localhost:8000/files/documents/report.pdf" \
  -H "X-API-Key: your-api-key" \
  --output report.pdf
```

**Response**: File content with appropriate MIME type

---

### 4. Delete a File

```http
DELETE /files/{filename}
```

Delete a file from storage.

**Authentication**: Required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `filename` | string | path | Full path to the file |

**Example**:
```bash
curl -X DELETE "http://localhost:8000/files/images/photo.jpg" \
  -H "X-API-Key: your-api-key"
```

**Response**:
```json
{
  "filename": "images/photo.jpg",
  "status": "deleted"
}
```

---

### 5. Delete a Folder

```http
DELETE /folders/{folder_path}
```

Delete all files within a folder.

**Authentication**: Required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `folder_path` | string | path | Path to the folder to delete |

**Example**:
```bash
curl -X DELETE "http://localhost:8000/folders/styled/geometric_3d" \
  -H "X-API-Key: your-api-key"
```

**Response**:
```json
{
  "folder": "styled/geometric_3d",
  "status": "deleted",
  "deleted_count": 15,
  "deleted_files": [
    "styled/geometric_3d/photo1.jpg",
    "styled/geometric_3d/photo2.jpg"
  ]
}
```

---

## 🖼️ Image APIs

These endpoints provide image discovery and styled image lookup functionality.

### 1. Get Random Images

```http
GET /images/random
```

Get randomly selected images from the `STYLE_SYNC_DEFAULT_SOURCE_FOLDER`.

**Authentication**: Not required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `count` | integer | query | Number of random images to return (1-20, default: 4) |

**Example**:
```bash
curl "http://localhost:8000/images/random?count=6"
```

**Response**:
```json
{
  "source_folder": "originals",
  "total_images": 15,
  "count": 6,
  "images": [
    "originals/photo1.jpg",
    "originals/photo5.png",
    "originals/photo12.jpeg",
    "originals/photo8.webp",
    "originals/photo3.jpg",
    "originals/photo9.png"
  ]
}
```

---

### 2. Get Styled File Path

```http
GET /images/styled
```

Get the path for a styled file if it exists, along with the icon path.

**Authentication**: Not required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `style` | string | query | The style name (e.g., "Geometric3D"). Case-insensitive. (required) |
| `id` | string | query | The image filename to look up. Use `-1` to get a random image. (required) |

**Behavior**:
- Style matching is **case-insensitive** and ignores spaces, underscores, and hyphens
- If `id` is `-1`: Returns a random image from the style folder
- If `style` is not found: Returns the original image from the source folder instead

**Example - Specific file**:
```bash
curl "http://localhost:8000/images/styled?style=Geometric3D&id=photo1.jpg"
```

**Example - Random image**:
```bash
curl "http://localhost:8000/images/styled?style=geometric3d&id=-1"
```

**Response** (200):
```json
{
  "style": "Geometric3D",
  "style_folder": "geometric_3d",
  "file_path": "styled/geometric_3d/photo1.jpg",
  "id": "photo1.jpg",
  "icon_path": "icons/03_Geometic3D.webp",
  "icon_name": "03_Geometic3D.webp"
}
```

**Response when style not found** (200 - returns original):
```json
{
  "style": "original",
  "style_folder": "original",
  "file_path": "originals/photo1.jpg",
  "id": "photo1.jpg",
  "icon_path": "",
  "icon_name": ""
}
```

**Error Response** (404):
```json
{
  "detail": "Styled file not found: styled/geometric_3d/photo1.jpg"
}
```

---

### 3. Get Next Image

```http
GET /images/next
```

Get a random image for the given style, excluding the current image. Useful for "next" or "shuffle" functionality.

**Authentication**: Not required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `style` | string | query | The style name (e.g., "Geometric3D"). Case-insensitive. (required) |
| `id` | string | query | The current image filename to exclude (required) |

**Behavior**:
- Style matching is **case-insensitive** and ignores spaces, underscores, and hyphens
- Returns a random image from the style folder, excluding the current image
- If `style` is not found: Returns a random original image instead

**Example**:
```bash
curl "http://localhost:8000/images/next?style=Geometric3D&id=photo1.jpg"
```

**Response** (200):
```json
{
  "style": "Geometric3D",
  "style_folder": "geometric_3d",
  "file_path": "styled/geometric_3d/photo5.jpg",
  "id": "photo5.jpg",
  "icon_path": "icons/03_Geometic3D.webp",
  "icon_name": "03_Geometic3D.webp",
  "excluded": "photo1.jpg"
}
```

**Error Response** (404):
```json
{
  "detail": "No other images found in folder: styled/geometric_3d"
}
```

---

## ⚡ StyleSync APIs

The integrated StyleSync service provides AI-powered image style transfer capabilities directly within the FastAPI application.

**Style Configuration**: Styles are configured in the `styles.json` file at the project root. The API reads styles from this file, so you don't need to include them in each request.

---

### 1. Run StyleSync (Synchronous)

```http
POST /stylesync
```

Execute style transformation synchronously. Waits for all images to be processed before returning.

**Authentication**: Required

**Request Body**:
```json
{
  "source_path": "originals/",
  "output_path": "styled/"
}
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_path` | string | No | Path prefix for source images. Falls back to `STYLE_SYNC_DEFAULT_SOURCE_FOLDER` env var (default: `""`) |
| `output_path` | string | No | Output path prefix. Falls back to `STYLE_SYNC_DEFAULT_TARGET_FOLDER` env var (default: `styled/`) |

> **Note**: If both request parameters and environment variables are empty, the service will process images from the root of storage.

**Example**:
```bash
curl -X POST "http://localhost:8000/stylesync" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_path": "photos/",
    "output_path": "styled-photos/"
  }'
```

**Response**:
```json
{
  "status": "completed",
  "source": "photos/",
  "output": "styled-photos/",
  "processed": ["watercolor/photo1.jpg", "oil_painting/photo1.jpg"],
  "failed": [],
  "skipped": ["watercolor/photo2.jpg"],
  "deleted": []
}
```

**Output Structure**:
Processed images are organized by style folder:
```
styled-photos/
├── original/           # Copy of source images
│   ├── photo1.jpg
│   └── photo2.jpg
├── watercolor/         # Style 1 outputs
│   ├── photo1.jpg
│   └── photo2.jpg
└── oil_painting/       # Style 2 outputs
    ├── photo1.jpg
    └── photo2.jpg
```

**Orphan Cleanup**: When a source image is deleted, running StyleSync will automatically remove the corresponding styled images and return them in the `deleted` array.

---

### 2. Run StyleSync (Async/Background)

```http
POST /stylesync/async
```

Execute style transformation as a background job. Returns immediately with a job ID.

**Authentication**: Required

**Request Body**: Same as `/stylesync`

**Example**:
```bash
curl -X POST "http://localhost:8000/stylesync/async" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"source_path": "photos/", "output_path": "styled/"}'
```

**Response**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started",
  "message": "StyleSync job started. Use GET /stylesync/status/{job_id} to check progress."
}
```

---

### 3. Get StyleSync Job Status

```http
GET /stylesync/status/{job_id}
```

Check the status of a background StyleSync job.

**Authentication**: Not required

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `job_id` | string | path | UUID of the background job |

**Example**:
```bash
curl "http://localhost:8000/stylesync/status/550e8400-e29b-41d4-a716-446655440000"
```

**Response**:
```json
{
  "status": "completed",
  "source": "photos/",
  "output": "styled/",
  "processed": ["photo1_1.jpg"],
  "failed": [],
  "skipped": [],
  "error": null
}
```

---

### 4. List Styleable Images

```http
GET /stylesync/images
```

List all valid images that can be styled from a source path.

**Authentication**: Not required

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `source_path` | string | Optional path prefix to filter images |

**Example**:
```bash
curl "http://localhost:8000/stylesync/images?source_path=photos/"
```

**Response**:
```json
{
  "source_path": "photos/",
  "count": 3,
  "images": [
    {"name": "photo1.jpg", "path": "photos/photo1.jpg"},
    {"name": "photo2.png", "path": "photos/photo2.png"},
    {"name": "photo3.webp", "path": "photos/photo3.webp"}
  ]
}
```

---

### 5. Get Configured Styles

```http
GET /stylesync/styles
```

Get the list of styles configured in `styles.json` that will be applied during StyleSync.

**Authentication**: Not required

**Example**:
```bash
curl "http://localhost:8000/stylesync/styles"
```

**Response**:
```json
{
  "count": 3,
  "styles": [
    {
      "index": 1,
      "name": "Geometric 3D",
      "prompt_text": "Transform this image into a geometric 3D art style...",
      "strength": 0.7
    },
    {
      "index": 2,
      "name": "Animated",
      "prompt_text": "Convert this image to an animated cartoon style...",
      "strength": 0.75
    }
  ]
}
```

**Style Object Properties**:
| Field | Type | Description |
|-------|------|-------------|
| `index` | number | Unique style identifier |
| `name` | string | Human-readable style name (used for output folder) |
| `prompt_text` | string | AI prompt describing the style transformation |
| `strength` | number | Style intensity (0.0 - 1.0) |

---

### 6. List AI Providers

```http
GET /stylesync/providers
```

List available AI providers and their configuration status.

**Authentication**: Not required

**Example**:
```bash
curl "http://localhost:8000/stylesync/providers"
```

**Response**:
```json
{
  "providers": [
    {
      "name": "azure",
      "description": "Azure OpenAI with Flux model",
      "configured": true,
      "required_env_vars": ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"]
    }
  ]
}
```

### Supported Image Formats

- `.jpg` / `.jpeg`
- `.png`
- `.webp`

---

## ⚙️ Environment Variables

### Application Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | No | - | Azure Storage connection string. If not set, uses local storage |
| `CONTAINER_NAME` | No | `file-container` | Azure Blob container name |
| `API_KEY` | No | `default-insecure-key` | API key for protected endpoints |
| `STYLE_SYNC_DEFAULT_SOURCE_FOLDER` | No | `""` | Default source path for StyleSync when not specified in request |
| `STYLE_SYNC_DEFAULT_TARGET_FOLDER` | No | `styled/` | Default output path for StyleSync when not specified in request |
| `STYLE_SYNC_ICON_FOLDER` | No | `icons/` | Folder where style icons are stored |

### Azure OpenAI Provider Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes* | - | Azure OpenAI endpoint URL (e.g., `https://your-resource.openai.azure.com/...`) |
| `AZURE_OPENAI_API_KEY` | Yes* | - | Azure OpenAI API key |
| `AZURE_OPENAI_MODEL` | No | `flux.1-kontext-pro` | Model deployment name to use |

*Required when using StyleSync

---

## 🔧 Storage Modes

### Azure Blob Storage Mode
When `AZURE_STORAGE_CONNECTION_STRING` is configured, files are stored in Azure Blob Storage:
- Automatic container creation if it doesn't exist
- Full blob path support with folders
- Scalable cloud storage

### Local Storage Mode
When no connection string is provided, files are stored locally:
- Files saved in `local_storage/` directory
- Full folder structure support
- Ideal for development and testing

---

## 🎨 AI Provider

### Azure OpenAI (Flux)
Uses the Flux.1-Kontext-Pro model (or custom model) for high-quality image transformations.

**Configuration**:
```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/openai/deployments/your-deployment/images/generations?api-version=2024-02-01"
export AZURE_OPENAI_API_KEY="your-azure-openai-api-key"
export AZURE_OPENAI_MODEL="flux.1-kontext-pro"  # Optional, this is the default
```

---

## 📋 Style Configuration (styles.json)

StyleSync reads style definitions from the `styles.json` file in the project root. This file defines what transformations will be applied to your images.

**File Location**: `./styles.json`

**Example styles.json**:
```json
{
  "styles": [
    {
      "index": 1,
      "name": "Geometric 3D",
      "prompt_text": "Transform this image into a geometric 3D art style with bold shapes and vibrant colors",
      "strength": 0.7
    },
    {
      "index": 2,
      "name": "Animated",
      "prompt_text": "Convert this image to an animated cartoon style with smooth lines and expressive features",
      "strength": 0.75
    },
    {
      "index": 3,
      "name": "Vintage",
      "prompt_text": "Apply a vintage film photography look with muted colors and subtle grain",
      "strength": 0.6
    }
  ]
}
```

**Style Properties**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | number | Yes | Unique identifier for the style |
| `name` | string | Yes | Human-readable name (used as output folder name) |
| `prompt_text` | string | Yes | AI prompt describing the desired transformation |
| `strength` | number | No | Style intensity from 0.0 to 1.0 (default: 0.7) |

> **Tip**: The `name` field is sanitized and used as the output folder name. Spaces are converted to underscores and special characters are removed.

---

## 📝 Usage Examples

### Upload and Retrieve Images

```bash
# Upload an image to the 'photos' folder
curl -X POST "http://localhost:8000/files?folder=photos" \
  -H "X-API-Key: my-api-key" \
  -F "file=@vacation.jpg"

# Access the image (public - no auth needed)
curl "http://localhost:8000/files/photos/vacation.jpg" --output vacation.jpg
```

### Batch Style Transfer (Synchronous)

```bash
# Run StyleSync to transform all images in photos/
# Styles are loaded from styles.json
curl -X POST "http://localhost:8000/stylesync" \
  -H "X-API-Key: my-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_path": "photos/",
    "output_path": "styled-photos/"
  }'
```

### Batch Style Transfer (Async Background Job)

```bash
# Start background job
JOB_RESPONSE=$(curl -s -X POST "http://localhost:8000/stylesync/async" \
  -H "X-API-Key: my-api-key" \
  -H "Content-Type: application/json" \
  -d '{"source_path": "photos/", "output_path": "styled/"}')

# Extract job ID and check status
JOB_ID=$(echo $JOB_RESPONSE | jq -r '.job_id')
curl "http://localhost:8000/stylesync/status/$JOB_ID"
```

---

## 🛠️ Development

### Running Locally

```bash
# Start the FastAPI server with auto-reload
uvicorn app.main:app --reload --port 8000

# The API will be available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

---

## 📦 Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `azure-storage-blob` - Azure Blob Storage SDK
- `python-multipart` - File upload support
- `jinja2` - HTML templating
- `requests` - HTTP client for AI APIs

---

## 📄 License

This project is licensed under the MIT License.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
