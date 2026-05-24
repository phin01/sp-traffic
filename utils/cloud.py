"""Cloud storage utilities

This module provides cloud-agnostic interfaces for storage read-write operations.
Currently implemented with Azure Blob Storage
All credentials are loaded from the project root .env file via dotenv.
"""

import os
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from azure.storage.blob import BlobServiceClient


# Load environment variables from .env file at project root
load_dotenv(dotenv_path=find_dotenv())

AZURE_STORAGE_KEY = os.getenv('AZURE_STORAGE_KEY')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME')


class CloudStorage:
    """Cloud storage interface for blob operations.

    This class provides a cloud-agnostic API implemented with Azure Blob Storage.
    Methods can be extended or replaced to support other cloud providers in the future.
    """

    def __init__(self, container_name: str | None = None):
        """Initialize cloud storage client.

        Args:
            container_name: Optional override for AZURE_CONTAINER_NAME env var.
        """
        if not AZURE_STORAGE_KEY:
            raise ValueError("AZURE_STORAGE_KEY not found in environment variables")

        self._client = BlobServiceClient.from_connection_string(AZURE_STORAGE_KEY)
        self._container_name = container_name or AZURE_CONTAINER_NAME

    def upload(self, data: bytes | str, blob_name: str, content_type: str | None = None) -> str:
        """Upload data to a blob.

        Args:
            data: Data to upload (bytes or JSON string).
            blob_name: Name of the blob in the container.
            content_type: Optional MIME type for the content.

        Returns:
            The full URL/path of the uploaded blob.
        """
        if isinstance(data, str):
            data = data.encode('utf-8')

        container_client = self._client.get_container_client(self._container_name)
        blob_client = container_client.get_blob_client(blob_name)

        blob_client.upload_blob(
            data=data,
            content_type=content_type or 'application/octet-stream',
            overwrite=True,
        )

        return f"{self._container_name}/{blob_name}"

    def upload_json(self, data: dict | list, blob_name: str, indent: int = 2) -> str:
        """Upload JSON data to a blob.

        Args:
            data: Dictionary or list to serialize as JSON.
            blob_name: Name of the blob in the container.
            indent: JSON indentation level for pretty printing.

        Returns:
            The full URL/path of the uploaded blob.
        """
        import json
        content = json.dumps(data, indent=indent).encode('utf-8')
        return self.upload(content, blob_name, 'application/json')

    def generate_blob_name(self, path: str, prefix: str, timestamp_format: str = "%Y-%m-%dT%H:%M:%S") -> str:
        """Generate a blob name with timestamp.

        Args:
            path: Path for the blob.
            prefix: Base filename prefix.
            timestamp_format: Python strftime format for the timestamp.

        Returns:
            Blob name including current UTC timestamp.
        """
        return f"{path}/{prefix}_{datetime.utcnow().strftime(timestamp_format)}.json"


__all__ = ["CloudStorage"]
