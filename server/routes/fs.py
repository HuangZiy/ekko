"""Filesystem browsing API — directory picker support."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fs", tags=["fs"])


class DirEntry(BaseModel):
    name: str
    type: str = "directory"


class BrowseResponse(BaseModel):
    current: str
    parent: str | None
    entries: list[DirEntry]


@router.get("/browse", response_model=BrowseResponse)
def browse_directory(path: str | None = None):
    """List subdirectories at the given path. Defaults to ~."""
    target = Path(path) if path else Path.home()
    target = target.resolve()

    if not target.exists():
        raise HTTPException(400, f"Path does not exist: {target}")
    if not target.is_dir():
        raise HTTPException(400, f"Path is not a directory: {target}")

    entries: list[DirEntry] = []
    try:
        for item in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if item.name.startswith("."):
                continue
            if item.is_dir() and not item.is_symlink():
                entries.append(DirEntry(name=item.name))
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {target}")

    parent = str(target.parent) if target.parent != target else None

    return BrowseResponse(current=str(target), parent=parent, entries=entries)
