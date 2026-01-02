# LLM Instructions for Azure Spotlight Style Storage

> **Purpose**: This document provides context for LLMs to understand and work with this project effectively. Keep this document updated with any architectural or significant changes.

---

## Role Expectations

When working on this project, act as an **expert developer** with deep knowledge in:

- **Python**: FastAPI, Pydantic, async programming, dataclasses, type hints
- **Web Development**: HTML5, CSS3, vanilla JavaScript, REST APIs, responsive design
- **Azure**: Blob Storage, Azure OpenAI, Azure App Service, container deployments
- **DevOps**: Docker, GitHub Actions, CI/CD pipelines

Apply best practices, write clean idiomatic code, and consider edge cases. Prioritize maintainability and performance.

---

## Project Overview

**Azure Spotlight Style Storage** is a FastAPI-based file storage application with integrated AI-powered image style transfer capabilities. It supports dual storage modes (Azure Blob Storage or local filesystem) and uses Azure OpenAI for image transformations.

### Core Capabilities

1. **File Management**: Upload, download, list, and delete files with folder organization
2. **AI Style Transfer**: Apply configurable style transformations to images using Azure OpenAI
3. **Web UI**: Built-in file explorer with multi-file upload and StyleSync integration
4. **Dual Storage**: Seamlessly switch between Azure Blob Storage and local filesystem

---

## Project Structure

```
az-spotlight-style-storage/
├── .github/workflows/           # CI/CD Pipelines
│   ├── azure-devops.yml         # Auto-deploy on push
│   └── manual-deploy.yml        # Manual deployment trigger
├── app/                         # FastAPI Application
│   ├── main.py                  # Routes, endpoints, app configuration
│   ├── storage.py               # StorageService (Azure/Local modes)
│   ├── templates/
│   │   └── index.html           # Web UI (file explorer, upload, StyleSync)
│   └── stylesync/               # AI Style Transfer Module
│       ├── __init__.py          # Module exports
│       ├── sync.py              # StyleSyncService, SyncTask, SyncResult
│       └── clients/
│           ├── __init__.py      # get_generator factory
│           ├── base.py          # BaseGenerator, GeneratorResult
│           └── azure.py         # AzureGenerator (Azure OpenAI)
├── Dockerfile                   # Container configuration
├── requirements.txt             # Python dependencies
├── sample.REST                  # API examples for VS Code REST Client
├── styles.json                  # Style configurations (prompts, strength)
└── instructions.md              # This file - LLM context document
```

---

## Key Files Reference

### `app/main.py`
- **Purpose**: FastAPI application with all route handlers
- **Key Components**:
  - `StorageService` and `StyleSyncService` initialization
  - API key authentication via `get_api_key()` dependency
  - File management endpoints (`/files`, `/files/{path}`, `/folders/{path}`)
  - Image discovery endpoints (`/images/random`, `/images/styled`, `/images/next`)
  - StyleSync endpoints (`/stylesync`, `/stylesync/async`, `/stylesync/status/{job_id}`)
  - Background job tracking via `sync_jobs` dict
- **Helper Functions**:
  - `load_styles_from_file()`: Loads styles from `styles.json`
  - `sanitize_style_name()`: Normalizes style names for matching
  - `find_style_by_name()`: Case-insensitive style lookup

### `app/storage.py`
- **Purpose**: Abstraction layer for file storage
- **Modes**: 
  - `AZURE`: Uses Azure Blob Storage when `AZURE_STORAGE_CONNECTION_STRING` is set
  - `LOCAL`: Uses `local_storage/` directory otherwise
- **Methods**: `upload_file()`, `get_file()`, `list_files()`, `delete_file()`, `delete_folder()`

### `app/stylesync/sync.py`
- **Purpose**: Core style transfer orchestration
- **Key Classes**:
  - `StyleConfig`: Style definition (name, prompt, strength)
  - `SyncTask`: Individual image-style transformation task
  - `SyncResult`: Operation result with processed/failed/skipped lists
  - `StyleSyncService`: Main service class
- **Key Methods**:
  - `get_valid_images()`: Lists images matching extensions (.jpg, .jpeg, .png, .webp)
  - `map_expected_state()`: Builds expected output file map
  - `get_missing_files()`: Identifies which files need generation
  - `process_sync()`: Executes full sync operation

### `app/stylesync/clients/azure.py`
- **Purpose**: Azure OpenAI image generation
- **Environment Variables**:
  - `AZURE_OPENAI_ENDPOINT`: API endpoint URL
  - `AZURE_OPENAI_API_KEY`: Authentication key
  - `AZURE_OPENAI_MODEL`: Model name (default: `flux.1-kontext-pro`)
- **Method**: `process_image_bytes()`: Sends image + prompt to Azure, returns styled image

### `app/templates/index.html`
- **Purpose**: Web-based file explorer UI
- **Features**:
  - Grid/folder view toggle
  - Multi-file upload with progress overlay
  - Auto StyleSync toggle on upload/delete
  - Toast notifications for StyleSync results (10 second display)
  - **StyleSync progress banner** - persistent top banner showing job status
  - View configured styles modal
  - Incremental file list refresh (no page reload)
- **Key JavaScript Functions**:
  - `uploadFiles()`: Handles multi-file upload
  - `deleteFile()`: Deletes file with optional StyleSync trigger
  - `refreshFileList()`: Updates UI without page reload
  - `pollStyleSyncStatus()`: Polls background jobs with visible progress banner
  - `showStyleSyncBanner()` / `hideStyleSyncBanner()`: Manage progress banner visibility
  - `showToast()`: Displays notification messages

### `styles.json`
- **Purpose**: Style configuration file
- **Structure**:
  ```json
  {
    "styles": [
      {
        "name": "StyleName",
        "folder_name": "style_name",
        "icon": "icon_file.webp",
        "prompt_text": "AI transformation prompt...",
        "strength": 0.7
      }
    ]
  }
  ```
- **Used By**: `/stylesync/styles` endpoint and `process_sync()` method

---

## API Endpoints Summary

### File Management
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | No | Web UI |
| GET | `/files` | No | List all files |
| POST | `/files` | Yes | Upload file (supports `folder` query param) |
| GET | `/files/{path}` | Images: No, Others: Yes | Download file |
| DELETE | `/files/{path}` | Yes | Delete file |
| DELETE | `/folders/{path}` | Yes | Delete folder and contents |

### Image Discovery
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/images/random` | No | Get random images from source folder |
| GET | `/images/styled` | No | Get styled image path by style and id |
| GET | `/images/next` | No | Get next random image (excluding current) |

### StyleSync
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/stylesync` | Yes | Run sync (synchronous) |
| POST | `/stylesync/async` | Yes | Run sync (background job) |
| GET | `/stylesync/status/{job_id}` | No | Check job status |
| GET | `/stylesync/images` | No | List styleable images |
| GET | `/stylesync/styles` | No | Get configured styles |
| GET | `/stylesync/providers` | No | List AI providers |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | No | - | Azure Storage connection (uses local if not set) |
| `CONTAINER_NAME` | No | `file-container` | Azure Blob container name |
| `API_KEY` | No | `default-insecure-key` | API authentication key |
| `STYLE_SYNC_DEFAULT_SOURCE_FOLDER` | No | `source/` | Default source path for StyleSync |
| `STYLE_SYNC_DEFAULT_TARGET_FOLDER` | No | `styled/` | Default output path for StyleSync |
| `STYLE_SYNC_ICON_FOLDER` | No | `icons/` | Folder for style icons |
| `AZURE_OPENAI_ENDPOINT` | For StyleSync | - | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | For StyleSync | - | Azure OpenAI API key |
| `AZURE_OPENAI_MODEL` | No | `flux.1-kontext-pro` | Model deployment name |

---

## Coding Patterns & Conventions

### Python
- **Framework**: FastAPI with Pydantic models
- **Async**: Background tasks via `BackgroundTasks`
- **Logging**: Use `logging.getLogger(__name__)`
- **Type Hints**: All functions should have type annotations
- **Dataclasses**: Used for `StyleConfig`, `SyncTask`, `SyncResult`, `GeneratorResult`

### JavaScript (index.html)
- **No Framework**: Vanilla JavaScript
- **DOM Access**: Use `document.getElementById()` and `document.querySelector()`
- **Async/Await**: Preferred for fetch operations
- **Event Handlers**: Mix of inline (`onclick`) and `addEventListener`

### File Naming
- Python: `snake_case.py`
- Folders: `lowercase/`
- Style folders: Sanitized from style name (spaces → underscores, lowercase)

### Output Structure
StyleSync creates this folder structure:
```
<output_path>/
├── original/           # Copy of source images
│   └── image.jpg
├── style_name_1/       # First style outputs
│   └── image.jpg
└── style_name_2/       # Second style outputs
    └── image.jpg
```

---

## Common Tasks

### Adding a New API Endpoint
1. Add route handler in `app/main.py`
2. Define Pydantic models if needed (request/response)
3. Add example to `sample.REST`
4. Update README.md API Reference section
5. **Update this file** with endpoint details

### Adding a New Style
1. Edit `styles.json` - add new style object
2. Optionally add icon to icons folder
3. No code changes needed

### Modifying UI
1. Edit `app/templates/index.html`
2. Test file operations preserve toast notifications
3. Ensure `refreshFileList()` is called after operations

### Adding AI Provider (future)
1. Create new client in `app/stylesync/clients/`
2. Inherit from `BaseGenerator`
3. Implement `process_image_bytes()` method
4. Update `get_generator()` factory in `clients/__init__.py`
5. **Update this file** with new provider details

---

## Important Notes for LLMs

1. **No Azure Functions**: The `functions/` folder has been removed. All StyleSync functionality is integrated into the FastAPI app.

2. **Azure-Only AI**: Only Azure OpenAI is supported. Stability AI code was removed.

3. **Toast Preservation**: UI uses `refreshFileList()` instead of `location.reload()` to preserve toast notifications.

4. **Polling Interval**: StyleSync status polling uses 10-second intervals.

5. **Style Matching**: Style names are matched case-insensitively with spaces, underscores, and hyphens normalized.

6. **Image Extensions**: Valid extensions are `.jpg`, `.jpeg`, `.png`, `.webp` (defined in `sync.py`).

7. **Authentication**: 
   - Images are public (no auth needed)
   - Uploads, deletes, and StyleSync require API key
   - API key via header `X-API-Key` or query param `api_key`

8. **Keep This Document Updated**: When making significant changes, update the relevant sections of this file.
