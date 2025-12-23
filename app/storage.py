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
            return [p.name for p in self.local_storage_path.glob("*") if p.is_file()]
