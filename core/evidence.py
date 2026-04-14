from __future__ import annotations
import shutil
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


def _collect_diff_content(base_sha: str, workspace: Path, max_lines: int = 200) -> str:
    """Get the actual diff content, truncated to max_lines."""
    diff = _run_cmd(["git", "diff", f"{base_sha}..HEAD"], workspace)
    if not diff:
        return ""
    lines = diff.splitlines()
    truncated = lines[:max_lines]
    if len(lines) > max_lines:
        truncated.append(f"... ({len(lines) - max_lines} more lines truncated)")
    return "\n".join(truncated)


def _parse_eval_checks(eval_report: str) -> list[dict]:
    """Parse [PASS]/[FAIL] lines from eval report into structured checks."""
    checks: list[dict] = []
    for line in eval_report.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [PASS]"):
            text = stripped.removeprefix("- [PASS]").strip()
            checks.append({"criterion": text or "PASS", "passed": True, "detail": ""})
        elif stripped.startswith("- [FAIL]"):
            text = stripped.removeprefix("- [FAIL]").strip()
            checks.append({"criterion": text or "FAIL", "passed": False, "detail": ""})
    return checks


def _collect_screenshots(
    screenshots_dir: Path,
    issue_id: str,
    storage: ProjectStorage,
    project_id: str | None,
) -> list[dict]:
    """Collect screenshots: copy to uploads dir and return structured list."""
    if not screenshots_dir or not screenshots_dir.exists() or not screenshots_dir.is_dir():
        return []

    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    screenshot_files = sorted(
        f for f in screenshots_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    )
    if not screenshot_files:
        return []

    # Copy screenshots to issue uploads dir for self-contained storage
    uploads_dir = storage.issues_dir / issue_id / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    result: list[dict] = []
    for sf in screenshot_files:
        dest = uploads_dir / sf.name
        try:
            shutil.copy2(sf, dest)
        except Exception:
            pass  # Best effort copy

        if project_id:
            url = f"/api/projects/{project_id}/issues/{issue_id}/screenshots/{sf.name}"
        else:
            url = f"screenshots/{sf.name}"
        result.append({"url": url, "alt": sf.stem, "filename": sf.name})

    return result


def _parse_changed_files(base_sha: str, workspace: Path) -> list[dict]:
    """Parse git diff --numstat into structured file change list."""
    numstat = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--numstat"], workspace)
    if not numstat:
        return []

    files: list[dict] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            added = int(parts[0]) if parts[0] != "-" else 0
            deleted = int(parts[1]) if parts[1] != "-" else 0
            filename = parts[2]
            change_type = "modified"
            if added > 0 and deleted == 0:
                change_type = "added"
            elif added == 0 and deleted > 0:
                change_type = "deleted"
            files.append({
                "filename": filename,
                "additions": added,
                "deletions": deleted,
                "change_type": change_type,
            })
    return files


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
    """Collect agent-done evidence: append markdown to content.md AND write evidence.json.

    Args:
        base_sha: If provided, use range diff (base_sha..HEAD) to capture all
                  commits made during the agent run.
        agent_commits: List of commit SHAs actually produced by the agent.
        project_id: Project ID used to construct screenshot API URLs.
        eval_report: Raw evaluator report text containing [PASS]/[FAIL]/[NEW_ISSUE] markers.
        screenshots_dir: Directory containing evaluator screenshots.
    """
    sections = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections.append(f"## Agent Done 证据\n\n收集时间: {now}\n")

    # Structured evidence data
    evidence_data: dict = {
        "collected_at": now,
        "git_diff_stat": "",
        "git_diff_content": "",
        "git_log": "",
        "commits_count": 0,
        "files_changed": 0,
        "changed_files": [],
        "build_result": None,
        "screenshots": [],
        "eval_checks": [],
        "eval_summary": "",
        "change_summary": "",
    }

    _has_range_diff = False

    if base_sha:
        current_head = _run_cmd(["git", "rev-parse", "HEAD"], workspace)
        if not current_head:
            sections.append("### Git Diff\n\nEvidence collection error: unable to determine HEAD\n")
            sections.append("### Commits\n\nEvidence collection error: unable to determine HEAD\n")
        elif current_head == base_sha:
            sections.append("### Git Diff\n\nNo commits during this run\n")
            sections.append("### Commits\n\nNo commits during this run\n")
        elif agent_commits is not None and len(agent_commits) == 0:
            sections.append("### Git Diff\n\nNo file changes by this agent (HEAD moved by external commits)\n")
            sections.append("### Commits\n\nNo commits by this agent\n")
        else:
            _has_range_diff = True

            # --- Change Summary (shortstat) ---
            shortstat = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--shortstat"], workspace)
            if shortstat:
                sections.append(f"### 变更摘要\n\n{shortstat.strip()}\n")
                evidence_data["change_summary"] = shortstat.strip()

            diff_stat = _run_cmd(["git", "diff", f"{base_sha}..HEAD", "--stat"], workspace)
            if diff_stat:
                sections.append(f"### Git Diff\n\n```\n{diff_stat}\n```\n")
                evidence_data["git_diff_stat"] = diff_stat
            else:
                sections.append("### Git Diff\n\n(no diff)\n")

            log = _run_cmd(["git", "log", f"{base_sha}..HEAD", "--oneline"], workspace)
            if log:
                sections.append(f"### Commits\n\n```\n{log}\n```\n")
                evidence_data["git_log"] = log
                evidence_data["commits_count"] = len(log.strip().splitlines())
            else:
                sections.append("### Commits\n\n(no commits)\n")

            # --- Structured file changes ---
            changed_files = _parse_changed_files(base_sha, workspace)
            evidence_data["changed_files"] = changed_files
            evidence_data["files_changed"] = len(changed_files)

            # --- Diff content (truncated) ---
            diff_content = _collect_diff_content(base_sha, workspace, max_lines=200)
            evidence_data["git_diff_content"] = diff_content

            # --- File Diff Details ---
            file_diffs = _collect_file_diffs(base_sha, workspace)
            if file_diffs:
                sections.append(f"### 修改文件详情\n\n{file_diffs}")
    else:
        # Legacy fallback
        shortstat = _run_cmd(["git", "diff", "HEAD~1", "--shortstat"], workspace)
        if shortstat:
            sections.append(f"### 变更摘要\n\n{shortstat.strip()}\n")
            evidence_data["change_summary"] = shortstat.strip()

        diff_stat = _run_cmd(["git", "diff", "HEAD~1", "--stat"], workspace)
        if diff_stat:
            sections.append(f"### Git Diff\n\n```\n{diff_stat}\n```\n")
            evidence_data["git_diff_stat"] = diff_stat

        log = _run_cmd(["git", "log", "-1", "--oneline"], workspace)
        if log:
            sections.append(f"### Latest Commit\n\n`{log}`\n")
            evidence_data["git_log"] = log
            evidence_data["commits_count"] = 1

    # --- Screenshots ---
    if screenshots_dir is None:
        screenshots_dir = storage.root / "runs" / issue_id / "screenshots"

    screenshot_list = _collect_screenshots(screenshots_dir, issue_id, storage, project_id)
    evidence_data["screenshots"] = screenshot_list

    if screenshot_list:
        screenshot_lines = ["### 截图\n"]
        for ss in screenshot_list:
            screenshot_lines.append(f"![{ss['alt']}]({ss['url']})")
        sections.append("\n".join(screenshot_lines) + "\n")

    # --- Eval Summary ---
    if eval_report:
        eval_checks = _parse_eval_checks(eval_report)
        evidence_data["eval_checks"] = eval_checks

        pass_items = []
        fail_items = []
        for check in eval_checks:
            if check["passed"]:
                pass_items.append(f"- ✅ {check['criterion']}")
            else:
                fail_items.append(f"- ❌ {check['criterion']}")

        if pass_items or fail_items:
            eval_lines = ["### 评估摘要\n"]
            eval_lines.extend(fail_items)
            eval_lines.extend(pass_items)
            total = len(pass_items) + len(fail_items)
            summary = f"{len(pass_items)}/{total} 通过"
            eval_lines.append(f"\n评估结果: {summary}")
            sections.append("\n".join(eval_lines) + "\n")
            evidence_data["eval_summary"] = summary

    # Build result
    if run_build:
        build_out = _run_cmd(["npm", "run", "build"], workspace)
        status = "PASS" if build_out else "UNKNOWN"
        sections.append(f"### Build: {status}\n\n```\n{build_out[:500] if build_out else '(no output)'}\n```\n")
        evidence_data["build_result"] = {
            "passed": status == "PASS",
            "status": status,
            "output": build_out[:500] if build_out else "(no output)",
        }

    # Append to existing content
    try:
        existing = storage.load_issue_content(issue_id)
    except FileNotFoundError:
        existing = ""

    evidence_block = "\n".join(sections)
    updated = f"{existing}\n\n{evidence_block}" if existing else evidence_block
    storage.save_issue_content(issue_id, updated)

    # Write structured evidence.json (non-blocking)
    try:
        storage.save_evidence(issue_id, evidence_data)
    except Exception:
        pass  # evidence.json write failure should not block the main flow
