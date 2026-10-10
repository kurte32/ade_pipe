"""Blob storage access for the staging and documents containers.

Only the Blob API is used (never the Data Lake SDK) so Azurite locally and ADLS Gen2 in Azure
behave the same. Local: connection string to Azurite. Azure: account URLs + managed identity.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobBlock, BlobClient, BlobServiceClient, ContainerClient

from app.core.config import Settings, get_settings


def block_id(index: int) -> str:
    return base64.b64encode(f"{index:08d}".encode()).decode()


def block_index(bid: str) -> int:
    return int(base64.b64decode(bid).decode())


@dataclass
class BlobInfo:
    size: int
    content_type: str | None
    tags: dict[str, str]


class BlobStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if settings.storage_mode == "azurite":
            conn = (
                "DefaultEndpointsProtocol=http;"
                f"AccountName={settings.storage_account_name};"
                f"AccountKey={settings.storage_account_key};"
                f"BlobEndpoint={settings.storage_blob_endpoint};"
            )
            svc = BlobServiceClient.from_connection_string(conn)
            self._staging = svc.get_container_client(settings.storage_staging_container)
            self._documents = svc.get_container_client(settings.storage_documents_container)
        else:
            from azure.identity import DefaultAzureCredential

            cred = DefaultAzureCredential()
            self._staging = BlobServiceClient(
                settings.storage_staging_account_url, credential=cred
            ).get_container_client(settings.storage_staging_container)
            self._documents = BlobServiceClient(
                settings.storage_documents_account_url, credential=cred
            ).get_container_client(settings.storage_documents_container)

    # --- containers -------------------------------------------------------------------
    def ensure_containers(self) -> None:
        """Local only. In Azure, containers are created by Bicep."""
        for c in (self._staging, self._documents):
            try:
                c.create_container()
            except ResourceExistsError:
                pass

    def container(self, which: str) -> ContainerClient:
        return self._staging if which == "staging" else self._documents

    def ping(self) -> bool:
        return bool(self._staging.exists()) and bool(self._documents.exists())

    # --- block upload (staging) -------------------------------------------------------
    def stage_block(self, path: str, index: int, data: bytes) -> None:
        self._staging.get_blob_client(path).stage_block(block_id(index), data, length=len(data))

    def uncommitted_blocks(self, path: str) -> set[int]:
        try:
            _, uncommitted = self._staging.get_blob_client(path).get_block_list("uncommitted")
        except ResourceNotFoundError:
            return set()
        return {block_index(b.id) for b in uncommitted}

    def commit_blocks(self, path: str, count: int, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        blocks = [BlobBlock(block_id(i)) for i in range(count)]
        self._staging.get_blob_client(path).commit_block_list(
            blocks, content_settings=ContentSettings(content_type=content_type)
        )

    # --- generic -----------------------------------------------------------------------
    def upload(self, which: str, path: str, data: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self.container(which).get_blob_client(path).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )

    def download(
        self, which: str, path: str, offset: int | None = None, length: int | None = None
    ) -> Iterator[bytes]:
        stream = (
            self.container(which).get_blob_client(path).download_blob(offset=offset, length=length)
        )
        return stream.chunks()

    def read_all(self, which: str, path: str) -> bytes:
        return self.container(which).get_blob_client(path).download_blob().readall()

    def info(self, which: str, path: str) -> BlobInfo | None:
        client: BlobClient = self.container(which).get_blob_client(path)
        try:
            props = client.get_blob_properties()
        except ResourceNotFoundError:
            return None
        try:
            tags = client.get_blob_tags() or {}
        except Exception:  # noqa: BLE001 - tags unsupported on some accounts
            tags = {}
        return BlobInfo(
            size=int(props.size), content_type=props.content_settings.content_type, tags=tags
        )

    def set_tags(self, which: str, path: str, tags: dict[str, str]) -> None:
        self.container(which).get_blob_client(path).set_blob_tags(tags)

    def copy_staging_to_documents(self, src_path: str, dst_path: str) -> None:
        src = self._staging.get_blob_client(src_path)
        dst = self._documents.get_blob_client(dst_path)
        if self.settings.storage_mode == "azurite":
            # Azurite copies within the same emulated account by URL.
            poller: Any = dst.start_copy_from_url(src.url)
        else:
            # Cross-account copy with managed identity: pass a short-lived bearer token.
            from azure.identity import DefaultAzureCredential

            token = DefaultAzureCredential().get_token("https://storage.azure.com/.default").token
            poller = dst.start_copy_from_url(src.url, source_authorization=f"Bearer {token}")
        status = poller.get("copy_status") if isinstance(poller, dict) else None
        if status not in (None, "success"):
            props = dst.get_blob_properties()
            if props.copy.status != "success":
                raise RuntimeError(f"copy failed: {props.copy.status}")

    def delete(self, which: str, path: str) -> None:
        try:
            self.container(which).get_blob_client(path).delete_blob()
        except ResourceNotFoundError:
            pass

    def exists(self, which: str, path: str) -> bool:
        return bool(self.container(which).get_blob_client(path).exists())


@lru_cache
def get_blob_store() -> BlobStore:
    return BlobStore(get_settings())
