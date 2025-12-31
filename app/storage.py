import os
import shutil
from pathlib import Path
from typing import Generator, Union

try:
    from azure.storage.blob import BlobServiceClient
    from azure.core.exceptions import ResourceNotFoundError
except ImportError:
    BlobServiceClient = None

class StorageService:
    def __init__(self):
        # Allow switching between Local and Azure via env var
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("CONTAINER_NAME", "file-container")
        self.local_storage_path = Path("local_storage")
        
        if self.connection_string:
            print("Initializing Azure Blob Storage...")
            self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
            self.container_client = self.blob_service_client.get_container_client(self.container_name)
            if not self.container_client.exists():
                self.container_client.create_container()
            self.mode = "AZURE"
        else:
            print("No connection string found. Using LOCAL storage mode.")
            self.mode = "LOCAL"
            self.local_storage_path.mkdir(exist_ok=True)

    def upload_file(self, filename: str, data: bytes):
        if self.mode == "AZURE":
            blob_client = self.container_client.get_blob_client(filename)
            blob_client.upload_blob(data, overwrite=True)
        else:
            file_path = self.local_storage_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(data)

    def get_file(self, filename: str) -> Union[bytes, None]:
        if self.mode == "AZURE":
            blob_client = self.container_client.get_blob_client(filename)
            try:
                download_stream = blob_client.download_blob()
                return download_stream.readall()
            except ResourceNotFoundError:
                return None
        else:
            file_path = self.local_storage_path / filename
            if file_path.exists():
                with open(file_path, "rb") as f:
                    return f.read()
            return None

    def list_files(self):
        if self.mode == "AZURE":
            return [b.name for b in self.container_client.list_blobs()]
        else:
            files = []
            for p in self.local_storage_path.rglob("*"):
                if p.is_file():
                    # Return relative path with forward slashes
                    rel_path = p.relative_to(self.local_storage_path)
                    files.append(str(rel_path).replace("\\", "/"))
            return files

    def delete_file(self, filename: str):
        if self.mode == "AZURE":
            blob_client = self.container_client.get_blob_client(filename)
            try:
                blob_client.delete_blob()
            except ResourceNotFoundError:
                pass # Already deleted or not found
        else:
            file_path = self.local_storage_path / filename
            if file_path.exists():
                file_path.unlink()

    def delete_folder(self, folder_path: str) -> dict:
        """
        Delete all files within a folder.
        Returns a dict with deleted files count and list.
        """
        deleted_files = []
        
        # Normalize folder path - ensure it ends with /
        folder_prefix = folder_path.rstrip("/") + "/" if folder_path else ""
        
        if self.mode == "AZURE":
            # List all blobs with the folder prefix
            blobs_to_delete = [b.name for b in self.container_client.list_blobs(name_starts_with=folder_prefix)]
            for blob_name in blobs_to_delete:
                try:
                    blob_client = self.container_client.get_blob_client(blob_name)
                    blob_client.delete_blob()
                    deleted_files.append(blob_name)
                except Exception:
                    pass  # Skip files that fail to delete
        else:
            folder_full_path = self.local_storage_path / folder_path
            if folder_full_path.exists() and folder_full_path.is_dir():
                # Get all files in the folder
                for file_path in folder_full_path.rglob("*"):
                    if file_path.is_file():
                        rel_path = str(file_path.relative_to(self.local_storage_path)).replace("\\", "/")
                        try:
                            file_path.unlink()
                            deleted_files.append(rel_path)
                        except Exception:
                            pass  # Skip files that fail to delete
                # Remove empty directories
                try:
                    import shutil
                    shutil.rmtree(folder_full_path)
                except Exception:
                    pass
        
        return {
            "folder": folder_path,
            "deleted_count": len(deleted_files),
            "deleted_files": deleted_files
        }
