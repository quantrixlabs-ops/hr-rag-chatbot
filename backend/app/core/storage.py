"""Storage provider abstraction — Phase 3.

Abstracts file storage behind a common interface.
Backend selection via STORAGE_BACKEND env var:
  - "minio"  → MinIO (self-hosted S3-compatible, default in Phase 3)
  - "local"  → Local filesystem (Phase 1/2 fallback, dev without Docker)

Switching from MinIO to AWS S3:
  Set STORAGE_BACKEND=s3 + AWS_* env vars — zero code changes.

Path convention: /{tenant_id}/{document_id}/{filename}
This gives per-tenant path isolation as a second enforcement layer.

Phase 5 hook: Add CDN URL generation, signed URL expiry.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()


class StorageProvider:
    """Base interface — all backends implement these three methods."""

    def upload(self, tenant_id: str, document_id: str, filename: str, data: bytes) -> str:
        """Upload file. Returns the storage path/key."""
        raise NotImplementedError

    def download(self, storage_path: str) -> bytes:
        """Download file by storage path. Returns raw bytes."""
        raise NotImplementedError

    def delete(self, storage_path: str) -> bool:
        """Delete file. Returns True on success."""
        raise NotImplementedError

    def exists(self, storage_path: str) -> bool:
        """Check if a file exists."""
        raise NotImplementedError

    def get_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Get a presigned or direct URL for the file (Phase 5: CDN hook)."""
        raise NotImplementedError


# ── Local filesystem backend ──────────────────────────────────────────────────

class LocalStorageProvider(StorageProvider):
    """Stores files in local upload directory. For dev without Docker."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _path(self, tenant_id: str, document_id: str, filename: str) -> str:
        tenant_dir = os.path.join(self.base_dir, tenant_id, document_id)
        os.makedirs(tenant_dir, exist_ok=True)
        return os.path.join(tenant_dir, filename)

    def upload(self, tenant_id: str, document_id: str, filename: str, data: bytes) -> str:
        full_path = self._path(tenant_id, document_id, filename)
        with open(full_path, "wb") as f:
            f.write(data)
        # Return relative storage key
        storage_key = f"{tenant_id}/{document_id}/{filename}"
        logger.info("local_storage_upload", path=storage_key, size=len(data))
        return storage_key

    def download(self, storage_path: str) -> bytes:
        full_path = os.path.join(self.base_dir, storage_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {storage_path}")
        with open(full_path, "rb") as f:
            return f.read()

    def delete(self, storage_path: str) -> bool:
        full_path = os.path.join(self.base_dir, storage_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False

    def exists(self, storage_path: str) -> bool:
        return os.path.exists(os.path.join(self.base_dir, storage_path))

    def get_url(self, storage_path: str, expires_in: int = 3600) -> str:
        # Local — return a placeholder (no HTTP serving in dev)
        return f"/local-storage/{storage_path}"


# ── MinIO backend ─────────────────────────────────────────────────────────────

class MinIOStorageProvider(StorageProvider):
    """MinIO (S3-compatible) storage. Production default from Phase 3."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from minio import Minio
                self._client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                )
                # Ensure bucket exists
                if not self._client.bucket_exists(self.bucket):
                    self._client.make_bucket(self.bucket)
                    logger.info("minio_bucket_created", bucket=self.bucket)
            except ImportError:
                raise RuntimeError("minio package not installed — pip install minio")
        return self._client

    def _object_key(self, tenant_id: str, document_id: str, filename: str) -> str:
        return f"{tenant_id}/{document_id}/{filename}"

    def upload(self, tenant_id: str, document_id: str, filename: str, data: bytes) -> str:
        client = self._get_client()
        key = self._object_key(tenant_id, document_id, filename)
        client.put_object(
            self.bucket, key,
            io.BytesIO(data), len(data),
        )
        logger.info("minio_upload", key=key, size=len(data), bucket=self.bucket)
        return key

    def download(self, storage_path: str) -> bytes:
        client = self._get_client()
        response = client.get_object(self.bucket, storage_path)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, storage_path: str) -> bool:
        try:
            client = self._get_client()
            client.remove_object(self.bucket, storage_path)
            return True
        except Exception as e:
            logger.warning("minio_delete_failed", path=storage_path, error=str(e))
            return False

    def exists(self, storage_path: str) -> bool:
        try:
            client = self._get_client()
            client.stat_object(self.bucket, storage_path)
            return True
        except Exception:
            return False

    def get_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for direct download (Phase 5: CDN hook)."""
        from datetime import timedelta
        client = self._get_client()
        return client.presigned_get_object(
            self.bucket, storage_path,
            expires=timedelta(seconds=expires_in),
        )

    def health(self) -> dict:
        try:
            client = self._get_client()
            buckets = client.list_buckets()
            return {"status": "ok", "buckets": [b.name for b in buckets]}
        except Exception as e:
            return {"status": "error", "detail": str(e)}


# ── Factory ───────────────────────────────────────────────────────────────────

_provider: Optional[StorageProvider] = None


def get_storage() -> StorageProvider:
    """Get the configured storage provider (singleton)."""
    global _provider
    if _provider is None:
        s = get_settings()
        backend = getattr(s, "storage_backend", "local")

        if backend == "minio":
            _provider = MinIOStorageProvider(
                endpoint=getattr(s, "minio_endpoint", "localhost:9000"),
                access_key=getattr(s, "minio_access_key", "minioadmin"),
                secret_key=getattr(s, "minio_secret_key", "minioadmin"),
                bucket=getattr(s, "minio_bucket", "hr-documents"),
                secure=False,
            )
            logger.info("storage_provider_selected", backend="minio")
        else:
            _provider = LocalStorageProvider(s.upload_dir)
            logger.info("storage_provider_selected", backend="local")

    return _provider
