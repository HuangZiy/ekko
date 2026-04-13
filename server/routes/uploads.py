"""Image upload API for issue descriptions."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/projects/{project_id}/issues/{issue_id}", tags=["uploads"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


def _get_storage(project_id: str):
    from server.app import get_project_storage
    return get_project_storage(project_id)


@router.post("/uploads")
async def upload_image(project_id: str, issue_id: str, file: UploadFile = File(...)):
    """Upload an image for an issue. Returns the markdown-ready URL."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_TYPES)}")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, f"File too large. Max size: {MAX_SIZE // (1024*1024)}MB")

    storage = _get_storage(project_id)
    issue_dir = storage.issues_dir / issue_id
    if not issue_dir.exists():
        issue_dir.mkdir(parents=True, exist_ok=True)

    uploads_dir = issue_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    # Generate unique filename preserving extension
    ext = Path(file.filename or "image.png").suffix or ".png"
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = uploads_dir / filename
    filepath.write_bytes(data)

    url = f"/api/projects/{project_id}/issues/{issue_id}/uploads/{filename}"
    return {"url": url, "filename": filename}


@router.get("/uploads/{filename}")
def get_upload(project_id: str, issue_id: str, filename: str):
    """Serve an uploaded image."""
    storage = _get_storage(project_id)
    filepath = storage.issues_dir / issue_id / "uploads" / filename

    if not filepath.exists():
        raise HTTPException(404, "File not found")

    # Security: ensure path doesn't escape uploads dir
    try:
        filepath.resolve().relative_to((storage.issues_dir / issue_id / "uploads").resolve())
    except ValueError:
        raise HTTPException(400, "Invalid filename")

    # Determine media type from extension
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
