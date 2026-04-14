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


def _collect_file_diffs(base_sha: str, workspace: Path, max_lines_per_file: int = 30) -> str:
    """Get per-file diff details, truncated to max_lines_per_file lines each."""
    stat_output = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--name-only"], workspace)
    if not stat_output:
        return ""

    parts: list[str] = []
    for filename in stat_output.splitlines():
        filename = filename.strip()
        if not filename:
            continue
        file_diff = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--", filename], workspace)
        if not file_diff:
            continue
        lines = file_diff.splitlines()
        truncated = lines[:max_lines_per_file]
        suffix = f"\n... ({len(lines) - max_lines_per_file} more lines)" if len(lines) > max_lines_per_file else ""
        parts.append(f"#### {filename}\n\n```diff\n{chr(10).join(truncated)}{suffix}\n```\n")

    return "\n".join(parts)


def collect_evidence(
    issue_id: str,
    storage: ProjectStorage,
    workspace: Path,
    run_build: bool = False,
    base_sha: str | None = None,
    agent_commits: list[str] | None = None,
    project_id: str | None = None,
    eval_report: str | None = None,
    screenshots_dir: Path | None = None,
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
        project_id: Project ID used to construct screenshot API URLs. When None,
                    screenshots are still referenced but with relative paths.
        eval_report: Raw evaluator report text containing [PASS]/[FAIL]/[NEW_ISSUE] markers.
        screenshots_dir: Directory containing evaluator screenshots. When None,
                         falls back to storage.root / "runs" / issue_id / "screenshots".
    """
    sections = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections.append(f"## Agent Done 证据\n\n收集时间: {now}\n")

    # Track whether we have a valid diff range for file details later
    _has_range_diff = False
    _diff_base = base_sha

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
            _has_range_diff = True

            # --- Change Summary (shortstat) ---
            shortstat = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--shortstat"], workspace)
            if shortstat:
                sections.append(f"### 变更摘要\n\n{shortstat.strip()}\n")

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

            # --- File Diff Details ---
            file_diffs = _collect_file_diffs(base_sha, workspace)
            if file_diffs:
                sections.append(f"### 修改文件详情\n\n{file_diffs}")
    else:
        # Legacy fallback: HEAD~1 snapshot (kept for backward compatibility)
        # --- Change Summary for legacy mode ---
        shortstat = _run_cmd(["git", "diff", "HEAD~1", "--shortstat"], workspace)
        if shortstat:
            sections.append(f"### 变更摘要\n\n{shortstat.strip()}\n")

        diff = _run_cmd(["git", "diff", "HEAD~1", "--stat"], workspace)
        if diff:
            sections.append(f"### Git Diff\n\n```\n{diff}\n```\n")

        log = _run_cmd(["git", "log", "-1", "--oneline"], workspace)
        if log:
            sections.append(f"### Latest Commit\n\n`{log}`\n")

    # --- Screenshots ---
    if screenshots_dir is None:
        screenshots_dir = storage.root / "runs" / issue_id / "screenshots"
    if screenshots_dir.exists() and screenshots_dir.is_dir():
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        screenshot_files = sorted(
            f for f in screenshots_dir.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        )
        if screenshot_files:
            screenshot_lines = ["### 截图\n"]
            for sf in screenshot_files:
                if project_id:
                    url = f"/api/projects/{project_id}/issues/{issue_id}/screenshots/{sf.name}"
                else:
                    url = f"screenshots/{sf.name}"
                screenshot_lines.append(f"![{sf.stem}]({url})")
            sections.append("\n".join(screenshot_lines) + "\n")

    # --- Eval Summary ---
    if eval_report:
        pass_items = []
        fail_items = []
        for line in eval_report.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [PASS]"):
                text = stripped.removeprefix("- [PASS]").strip()
                pass_items.append(f"- ✅ {text}" if text else "- ✅ PASS")
            elif stripped.startswith("- [FAIL]"):
                text = stripped.removeprefix("- [FAIL]").strip()
                fail_items.append(f"- ❌ {text}" if text else "- ❌ FAIL")
        if pass_items or fail_items:
            eval_lines = ["### 评估摘要\n"]
            eval_lines.extend(fail_items)
            eval_lines.extend(pass_items)
            total = len(pass_items) + len(fail_items)
            eval_lines.append(f"\n评估结果: {len(pass_items)}/{total} 通过")
            sections.append("\n".join(eval_lines) + "\n")

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
