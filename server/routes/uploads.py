"""Image upload API for issue descriptions."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter(tags=["uploads"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


def _get_storage(project_id: str):
    from server.app import get_project_storage
    return get_project_storage(project_id)


def _validate_and_read(file: UploadFile, data: bytes):
    """Validate file type and size."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_TYPES)}")
    if len(data) > MAX_SIZE:
        raise HTTPException(400, f"File too large. Max size: {MAX_SIZE // (1024*1024)}MB")


def _save_file(uploads_dir: Path, file: UploadFile, data: bytes) -> str:
    """Save file to uploads_dir and return the generated filename."""
    uploads_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image.png").suffix or ".png"
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = uploads_dir / filename
    filepath.write_bytes(data)
    return filename


def _serve_file(uploads_dir: Path, filename: str) -> FileResponse:
    """Serve a file from uploads_dir with security checks."""
    filepath = uploads_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "File not found")
    try:
        filepath.resolve().relative_to(uploads_dir.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid filename")
    ext_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    media_type = ext_map.get(filepath.suffix.lower(), "application/octet-stream")
    return FileResponse(filepath, media_type=media_type)


# --- Project-level uploads (used during issue creation, before issue ID exists) ---

@router.post("/api/projects/{project_id}/uploads")
async def upload_project_image(project_id: str, file: UploadFile = File(...)):
    """Upload an image at project level (e.g. during issue creation). Returns markdown-ready URL."""
    data = await file.read()
    _validate_and_read(file, data)

    storage = _get_storage(project_id)
    uploads_dir = storage.issues_dir / "_shared" / "uploads"
    filename = _save_file(uploads_dir, file, data)

    url = f"/api/projects/{project_id}/uploads/{filename}"
    return {"url": url, "filename": filename}


@router.get("/api/projects/{project_id}/uploads/{filename}")
def get_project_upload(project_id: str, filename: str):
    """Serve a project-level uploaded image."""
    storage = _get_storage(project_id)
    uploads_dir = storage.issues_dir / "_shared" / "uploads"
    return _serve_file(uploads_dir, filename)


# --- Issue-level uploads (used when editing existing issues) ---

@router.post("/api/projects/{project_id}/issues/{issue_id}/uploads")
async def upload_image(project_id: str, issue_id: str, file: UploadFile = File(...)):
    """Upload an image for an issue. Returns the markdown-ready URL."""
    data = await file.read()
    _validate_and_read(file, data)

    storage = _get_storage(project_id)
    uploads_dir = storage.issues_dir / issue_id / "uploads"
    filename = _save_file(uploads_dir, file, data)

    url = f"/api/projects/{project_id}/issues/{issue_id}/uploads/{filename}"
    return {"url": url, "filename": filename}


@router.get("/api/projects/{project_id}/issues/{issue_id}/uploads/{filename}")
def get_upload(project_id: str, issue_id: str, filename: str):
    """Serve an uploaded image."""
    storage = _get_storage(project_id)
    uploads_dir = storage.issues_dir / issue_id / "uploads"
    return _serve_file(uploads_dir, filename)
