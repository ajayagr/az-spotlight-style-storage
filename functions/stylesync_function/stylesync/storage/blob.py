"""
Azure Blob Storage Provider for StyleSync Azure Function.
"""
from azure.storage.blob import BlobServiceClient, ContainerClient
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class FileItem:
    name: str
    path: str
    is_dir: bool = False

class AzureBlobStorageProvider:
    def __init__(self, connection_string: str, container_name: str):
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
        # Ensure container exists
        if not self.container_client.exists():
            self.container_client.create_container()
    
    def exists(self, path: str) -> bool:
        """Check if a blob exists."""
        blob_client = self.container_client.get_blob_client(path)
        return blob_client.exists()
    
    def list_files(self, prefix: str = "") -> List[FileItem]:
        """List blobs with given prefix."""
        blobs = self.container_client.list_blobs(name_starts_with=prefix)
        items = []
        for blob in blobs:
            items.append(FileItem(
                name=blob.name.rsplit("/", 1)[-1],
                path=blob.name,
                is_dir=False
            ))
        return items
    
    def read_file(self, path: str) -> bytes:
        """Read blob content."""
        blob_client = self.container_client.get_blob_client(path)
        return blob_client.download_blob().readall()
    
    def write_file(self, path: str, data: bytes):
        """Write data to blob."""
        blob_client = self.container_client.get_blob_client(path)
        blob_client.upload_blob(data, overwrite=True)
    
    def delete_file(self, path: str):
        """Delete a blob."""
        blob_client = self.container_client.get_blob_client(path)
        blob_client.delete_blob()
    
    def mkdir(self, path: str):
        """No-op for blob storage (no real folders)."""
        pass
