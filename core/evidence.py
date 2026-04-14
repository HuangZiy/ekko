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
    base_sha: str | None = None,
    agent_commits: list[str] | None = None,
) -> None:
    """Collect agent-done evidence and append to issue markdown.

    Args:
        base_sha: If provided, use range diff (base_sha..HEAD) to capture all
                  commits made during the agent run, instead of a HEAD~1 snapshot.
                  This prevents evidence from pointing to unrelated commits when
                  other work lands between the fix and evidence collection.
        agent_commits: List of commit SHAs actually produced by the agent during
                       this run. When provided as an empty list, it means the agent
                       produced no commits (even if HEAD moved due to external commits).
                       When None, backward-compatible behavior is used.
    """
    sections = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections.append(f"## Agent Done 证据\n\n收集时间: {now}\n")

    if base_sha:
        # Range-based: capture all changes during this agent run
        current_head = _run_cmd(["git", "rev-parse", "HEAD"], workspace)
        if not current_head:
            # git rev-parse HEAD failed — workspace may not be a git repo or HEAD is detached
            sections.append("### Git Diff\n\nEvidence collection error: unable to determine HEAD\n")
            sections.append("### Commits\n\nEvidence collection error: unable to determine HEAD\n")
        elif current_head == base_sha:
            # HEAD hasn't moved at all — agent produced no commits
            sections.append("### Git Diff\n\nNo commits during this run\n")
            sections.append("### Commits\n\nNo commits during this run\n")
        elif agent_commits is not None and len(agent_commits) == 0:
            # Agent explicitly tracked commits and produced none.
            # HEAD moved due to external commits (parallel agent, manual push, etc.)
            sections.append("### Git Diff\n\nNo file changes by this agent (HEAD moved by external commits)\n")
            sections.append("### Commits\n\nNo commits by this agent\n")
        else:
            # agent_commits is either a non-empty list or None (backward compat)
            diff = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--stat"], workspace)
            if diff:
                sections.append(f"### Git Diff\n\n```\n{diff}\n```\n")
            else:
                sections.append("### Git Diff\n\n(no diff)\n")

            log = _run_cmd(["git", "log", f"{base_sha}..HEAD", "--oneline"], workspace)
            if log:
                sections.append(f"### Commits\n\n```\n{log}\n```\n")
            else:
                sections.append("### Commits\n\n(no commits)\n")
    else:
        # Legacy fallback: HEAD~1 snapshot (kept for backward compatibility)
        diff = _run_cmd(["git", "diff", "HEAD~1", "--stat"], workspace)
        if diff:
            sections.append(f"### Git Diff\n\n```\n{diff}\n```\n")

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
