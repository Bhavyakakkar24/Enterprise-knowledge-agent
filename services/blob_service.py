"""
services/blob_service.py - Azure Blob Storage Service

Provides clean abstractions for uploading, listing, and downloading documents
from Azure Blob Storage using the official Azure SDK.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.core.exceptions import (
    ResourceNotFoundError,
    ClientAuthenticationError,
    ServiceRequestError,
    AzureError,
)
import config


class BlobService:
    """Service to interact with Azure Blob Storage container."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: Optional[str] = None,
    ):
        self.connection_string = connection_string or config.AZURE_STORAGE_CONNECTION_STRING
        self.container_name = container_name or config.AZURE_STORAGE_CONTAINER_NAME

        if not self.connection_string:
            raise ValueError("Azure Storage connection string is missing or empty in configuration.")
        if not self.container_name:
            raise ValueError("Azure Storage container name is missing or empty in configuration.")

        try:
            self.blob_service_client: BlobServiceClient = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            self.container_client: ContainerClient = self.blob_service_client.get_container_client(
                self.container_name
            )
        except Exception as e:
            raise ValueError(f"Failed to initialize Azure Blob Storage client. Check connection string format.") from e

    def ensure_container_exists(self) -> bool:
        """
        Verifies that the target container exists, or creates it if missing.
        Returns True if container exists or was created.
        """
        try:
            if not self.container_client.exists():
                self.container_client.create_container()
            return True
        except ClientAuthenticationError as e:
            raise PermissionError("Authentication failed when accessing Blob Storage. Check connection string credentials.") from e
        except AzureError as e:
            raise RuntimeError(f"Failed to verify or create container '{self.container_name}': {e}") from e

    def upload_file(
        self,
        file_path: Path | str,
        blob_name: Optional[str] = None,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """
        Uploads a local file to the Azure Blob Storage container.

        :param file_path: Path to local file.
        :param blob_name: Optional custom blob name. Defaults to file basename.
        :param overwrite: Whether to overwrite existing blob if it already exists (default: True).
        :return: Dict containing uploaded blob details.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Local file not found for upload: {path}")

        target_name = blob_name or path.name
        try:
            blob_client = self.container_client.get_blob_client(target_name)
            with open(path, "rb") as file_data:
                blob_client.upload_blob(file_data, overwrite=overwrite)

            return {
                "name": target_name,
                "size_bytes": path.stat().st_size,
                "container": self.container_name,
            }
        except ResourceNotFoundError as e:
            raise FileNotFoundError(f"Container '{self.container_name}' does not exist.") from e
        except ClientAuthenticationError as e:
            raise PermissionError("Authentication failed when uploading blob. Check storage access keys.") from e
        except AzureError as e:
            raise RuntimeError(f"Azure Blob upload error for '{target_name}': {e}") from e

    def list_blobs(self) -> List[Dict[str, Any]]:
        """
        Lists all blobs in the target container along with size and metadata.

        :return: List of dicts with blob metadata.
        """
        try:
            blobs_list = []
            for blob in self.container_client.list_blobs():
                blobs_list.append({
                    "name": blob.name,
                    "size_bytes": blob.size,
                    "last_modified": blob.last_modified,
                    "content_type": blob.content_settings.content_type if blob.content_settings else None,
                })
            return blobs_list
        except ResourceNotFoundError as e:
            raise FileNotFoundError(f"Container '{self.container_name}' does not exist.") from e
        except ClientAuthenticationError as e:
            raise PermissionError("Authentication failed when listing blobs. Check storage access keys.") from e
        except AzureError as e:
            raise RuntimeError(f"Azure Blob listing error in container '{self.container_name}': {e}") from e

    def download_blob(self, blob_name: str, destination_path: Path | str) -> Path:
        """
        Downloads a blob from the container to a local destination file.

        :param blob_name: Name of the blob to download.
        :param destination_path: Local file path where the blob will be written.
        :return: Path object of the downloaded file.
        """
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            with open(dest, "wb") as f:
                stream = blob_client.download_blob()
                stream.readinto(f)
            return dest
        except ResourceNotFoundError as e:
            raise FileNotFoundError(f"Blob '{blob_name}' not found in container '{self.container_name}'.") from e
        except ClientAuthenticationError as e:
            raise PermissionError("Authentication failed when downloading blob.") from e
        except AzureError as e:
            raise RuntimeError(f"Azure Blob download error for '{blob_name}': {e}") from e

    def get_blob_bytes(self, blob_name: str) -> bytes:
        """
        Downloads a blob content directly into bytes in memory.

        :param blob_name: Name of the blob.
        :return: Content of the blob as bytes.
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            return blob_client.download_blob().readall()
        except ResourceNotFoundError as e:
            raise FileNotFoundError(f"Blob '{blob_name}' not found in container '{self.container_name}'.") from e
        except ClientAuthenticationError as e:
            raise PermissionError("Authentication failed when reading blob bytes.") from e
        except AzureError as e:
            raise RuntimeError(f"Azure Blob read error for '{blob_name}': {e}") from e
