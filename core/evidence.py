from __future__ import annotations
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from core.storage import ProjectStorage


def _run_cmd(cmd: list[str], cwd: Path) -> str:
    """Run a shell command and return stdout, swallowing errors."""
    try:
        result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except Exception:
        return ""


def collect_evidence(
    issue_id: str,
    storage: ProjectStorage,
    workspace: Path,
    run_build: bool = False,
) -> None:
    """Collect agent-done evidence and append to issue markdown."""
    sections = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections.append(f"## Agent Done 证据\n\n收集时间: {now}\n")

    # Git diff
    diff = _run_cmd(["git", "diff", "HEAD~1", "--stat"], workspace)
    if diff:
        sections.append(f"### Git Diff\n\n```\n{diff}\n```\n")

    # Latest commit
    log = _run_cmd(["git", "log", "-1", "--oneline"], workspace)
    if log:
        sections.append(f"### Latest Commit\n\n`{log}`\n")

    # Build result
    if run_build:
        build_out = _run_cmd(["npm", "run", "build"], workspace)
        status = "PASS" if build_out else "UNKNOWN"
        sections.append(f"### Build: {status}\n\n```\n{build_out[:500] if build_out else '(no output)'}\n```\n")

    # Append to existing content
    try:
        existing = storage.load_issue_content(issue_id)
    except FileNotFoundError:
        existing = ""

    evidence_block = "\n".join(sections)
    updated = f"{existing}\n\n{evidence_block}" if existing else evidence_block
    storage.save_issue_content(issue_id, updated)
