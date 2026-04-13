"""CLI main entry point with argparse subcommands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import ARTIFACTS_DIR


def _get_platform():
    from core.storage import PlatformStorage
    return PlatformStorage(ARTIFACTS_DIR)


def _get_storage(args: argparse.Namespace):
    from core.storage import ProjectStorage
    project_dir = getattr(args, "project", None)
    if project_dir:
        return ProjectStorage(Path(project_dir))
    # Use active project
    platform = _get_platform()
    active_id = platform.get_active_project_id()
    if not active_id:
        print("No active project. Create one with: harness project create \"name\" /path/to/workspace", file=sys.stderr)
        sys.exit(1)
    return platform.get_project_storage(active_id)


# ---------------------------------------------------------------------------
# Project subcommands
# ---------------------------------------------------------------------------

def _project_create(args: argparse.Namespace) -> None:
    platform = _get_platform()
    workspace_path = str(Path(args.workspace_path).resolve())
    key = args.key.upper()
    project, store = platform.create_project(name=args.name, workspace_path=workspace_path, key=key)
    print(f"Created project {project.id}: {project.name}  (issue prefix: {project.key})")
    print(f"  Workspace: {workspace_path}")
    print(f"  Storage:   {store.root}")


def _project_list(args: argparse.Namespace) -> None:
    platform = _get_platform()
    projects = platform.list_projects()
    active_id = platform.get_active_project_id()
    if not projects:
        print("No projects. Create one with: harness project create \"name\" /path/to/workspace")
        return
    for pid, project in projects:
        marker = " *" if pid == active_id else ""
        print(f"  {pid}  {project.name}  workspaces={len(project.workspaces)}{marker}")


def _project_switch(args: argparse.Namespace) -> None:
    platform = _get_platform()
    if platform.switch_project(args.project_id):
        print(f"Switched to project {args.project_id}")
    else:
        print(f"Project not found: {args.project_id}", file=sys.stderr)
        sys.exit(1)


def _project_show(args: argparse.Namespace) -> None:
    platform = _get_platform()
    active_id = args.project_id or platform.get_active_project_id()
    if not active_id:
        print("No active project.", file=sys.stderr)
        sys.exit(1)
    store = platform.get_project_storage(active_id)
    project = store.load_project_meta()
    if not project:
        print(f"Project not found: {active_id}", file=sys.stderr)
        sys.exit(1)
    issues = store.list_issues()
    by_status = {}
    for i in issues:
        by_status.setdefault(i.status.value, []).append(i)
    print(f"Project:    {project.id}")
    print(f"Name:       {project.name}")
    print(f"Workspaces: {', '.join(project.workspaces)}")
    print(f"Issues:     {len(issues)} total")
    for status, items in sorted(by_status.items()):
        print(f"  {status:<15} {len(items)}")


def _project_update(args: argparse.Namespace) -> None:
    platform = _get_platform()
    project_id = args.project_id or platform.get_active_project_id()
    if not project_id:
        print("No active project. Specify --project-id or create one first.", file=sys.stderr)
        sys.exit(1)
    store = platform.get_project_storage(project_id)
    project = store.load_project_meta()
    if not project:
        print(f"Project not found: {project_id}", file=sys.stderr)
        sys.exit(1)

    changed = False
    if args.name is not None:
        project.name = args.name
        changed = True
    if args.key is not None:
        new_key = args.key.strip().upper()
        if not new_key:
            print("Error: --key cannot be empty.", file=sys.stderr)
            sys.exit(1)
        project.key = new_key
        changed = True

    if not changed:
        print("Nothing to update. Use --name or --key to specify changes.")
        return

    store.save_project_meta(project)
    print(f"Updated project {project.id}: {project.name}  (issue prefix: {project.key})")


def _project_delete(args: argparse.Namespace) -> None:
    import shutil
    platform = _get_platform()
    project_dir = platform.projects_dir / args.project_id
    if not project_dir.exists():
        print(f"Project not found: {args.project_id}", file=sys.stderr)
        sys.exit(1)
    store = platform.get_project_storage(args.project_id)
    project = store.load_project_meta()
    name = project.name if project else args.project_id
    if not args.yes:
        confirm = input(f"Delete project \"{name}\" ({args.project_id})? [y/N] ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            return
    shutil.rmtree(project_dir)
    if platform.get_active_project_id() == args.project_id:
        active_file = platform.root / "active_project"
        if active_file.exists():
            active_file.unlink()
    print(f"Deleted project {args.project_id}: {name}")


# ---------------------------------------------------------------------------
# Issue subcommands
# ---------------------------------------------------------------------------

def _issue_create(args: argparse.Namespace) -> None:
    from core.models import Issue
    import json
    store = _get_storage(args)

    # Determine issue prefix from project key
    project = store.load_project_meta()
    if project is None:
        print("Error: project metadata not found in storage directory.", file=sys.stderr)
        sys.exit(1)
    issue_id = store.next_issue_id(project.key)

    issue = Issue.create(
        id=issue_id,
        title=args.title,
        priority=args.priority,
        labels=args.label or [],
    )
    store.save_issue(issue)

    # Add to board backlog
    board_file = store.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if col["id"] == "backlog":
                col["issues"].append(issue.id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print(f"Created {issue.id}: {issue.title}")


def _issue_list(args: argparse.Namespace) -> None:
    store = _get_storage(args)
    issues = store.list_issues()
    if args.status:
        issues = [i for i in issues if i.status.value == args.status]
    if not issues:
        print("No issues found.")
        return
    for issue in issues:
        blocked = " [BLOCKED]" if issue.is_blocked() else ""
        labels = f" ({', '.join(issue.labels)})" if issue.labels else ""
        print(f"  {issue.id}  [{issue.status.value:<12}] {issue.priority.value:<6}  {issue.title}{labels}{blocked}")


def _issue_show(args: argparse.Namespace) -> None:
    store = _get_storage(args)
    try:
        issue = store.load_issue(args.issue_id)
    except FileNotFoundError:
        print(f"Issue not found: {args.issue_id}", file=sys.stderr)
        sys.exit(1)
    print(f"ID:         {issue.id}")
    print(f"Title:      {issue.title}")
    print(f"Status:     {issue.status.value}")
    print(f"Priority:   {issue.priority.value}")
    print(f"Labels:     {', '.join(issue.labels) or '—'}")
    print(f"Assignee:   {issue.assignee or '—'}")
    print(f"Blocked by: {', '.join(issue.blocked_by) or '—'}")
    print(f"Blocks:     {', '.join(issue.blocks) or '—'}")
    print(f"Created:    {issue.created_at}")
    print(f"Updated:    {issue.updated_at}")
    # Show markdown content if exists
    try:
        content = store.load_issue_content(issue.id)
        print(f"\n--- Content ---\n{content}")
    except FileNotFoundError:
        pass


def _issue_move(args: argparse.Namespace) -> None:
    from core.models import IssueStatus
    store = _get_storage(args)
    try:
        issue = store.load_issue(args.issue_id)
    except FileNotFoundError:
        print(f"Issue not found: {args.issue_id}", file=sys.stderr)
        sys.exit(1)
    try:
        new_status = IssueStatus(args.status)
    except ValueError:
        print(f"Invalid status: {args.status}", file=sys.stderr)
        sys.exit(1)
    old = issue.status.value
    try:
        issue.move_to(new_status)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    store.save_issue(issue)
    print(f"Moved {issue.id}: {old} -> {new_status.value}")


def _issue_delete(args: argparse.Namespace) -> None:
    import shutil
    store = _get_storage(args)
    issue_dir = store.issues_dir / args.issue_id
    if not issue_dir.exists():
        print(f"Issue not found: {args.issue_id}", file=sys.stderr)
        sys.exit(1)

    issue = store.load_issue(args.issue_id)
    if not args.yes:
        confirm = input(f"Delete issue \"{issue.title}\" ({args.issue_id})? [y/N] ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            return
    shutil.rmtree(issue_dir)

    # Remove from board
    board_file = store.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if args.issue_id in col["issues"]:
                col["issues"].remove(args.issue_id)
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print(f"Deleted {args.issue_id}: {issue.title}")


# ---------------------------------------------------------------------------
# Review subcommands
# ---------------------------------------------------------------------------

def _review(args: argparse.Namespace) -> None:
    from core.models import IssueStatus
    store = _get_storage(args)
    try:
        issue = store.load_issue(args.issue_id)
    except FileNotFoundError:
        print(f"Issue not found: {args.issue_id}", file=sys.stderr)
        sys.exit(1)

    if issue.status != IssueStatus.AGENT_DONE:
        print(f"Issue {issue.id} is in '{issue.status.value}', expected 'agent_done'.", file=sys.stderr)
        sys.exit(1)

    if args.approve:
        issue.move_to(IssueStatus.HUMAN_DONE)
        store.save_issue(issue)
        # Unlock dependents
        all_issues = store.list_issues()
        unlocked = []
        for other in all_issues:
            if issue.id in other.blocked_by:
                other.remove_blocker(issue.id)
                store.save_issue(other)
                unlocked.append(other.id)
        print(f"Approved {issue.id}: agent_done -> human_done")
        if unlocked:
            print(f"Unblocked: {', '.join(unlocked)}")

    elif args.reject:
        issue.move_to(IssueStatus.REJECTED)
        # Then move back to todo so it can be reworked
        issue.move_to(IssueStatus.TODO)
        store.save_issue(issue)
        # Append feedback to issue content
        if args.comment:
            try:
                content = store.load_issue_content(issue.id)
            except FileNotFoundError:
                content = ""
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            content += f"\n\n## Review Feedback ({ts})\n\n{args.comment}\n"
            store.save_issue_content(issue.id, content)
        print(f"Rejected {issue.id}: agent_done -> todo")
        if args.comment:
            print(f"Feedback: {args.comment}")
    else:
        print("Specify --approve or --reject", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Serve
# ---------------------------------------------------------------------------

def _serve(args: argparse.Namespace) -> None:
    import subprocess
    import os
    import socket

    def _find_free_port(preferred: int) -> int:
        """Try preferred port, fallback to OS-assigned."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]

    port = _find_free_port(args.port)
    harness_root = ARTIFACTS_DIR
    harness_root.mkdir(parents=True, exist_ok=True)

    web_dir = Path(__file__).resolve().parent.parent / "web"

    if args.dev and web_dir.exists():
        print(f"Starting Vite dev server (web/) + FastAPI on :{port}...", flush=True)
        vite_proc = subprocess.Popen(
            ["npx", "vite"],
            cwd=str(web_dir),
            env={**os.environ, "BROWSER": "none", "VITE_API_PORT": str(port)},
        )
        try:
            from server.app import run_server
            run_server(port=port, harness_root=harness_root)
        finally:
            vite_proc.terminate()
    else:
        # Production: serve built assets via FastAPI static files
        from server.app import create_app, run_server
        dist_dir = web_dir / "dist"
        if dist_dir.exists():
            app = create_app(harness_root=harness_root)
            from fastapi.staticfiles import StaticFiles
            app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")
            import uvicorn
            print(f"Serving on http://127.0.0.1:{port}", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=port)
        else:
            print(f"No built assets at {dist_dir}. Run 'cd web && npm run build' first, or use --dev.", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------------
# Migrate
# ---------------------------------------------------------------------------

def _migrate(args: argparse.Namespace) -> None:
    from core.migrate import migrate_fix_plan
    from config import WORKSPACE_DIR

    fix_plan_path = Path(args.fix_plan) if args.fix_plan else WORKSPACE_DIR / "fix_plan.md"
    if not fix_plan_path.exists():
        print(f"fix_plan.md not found at {fix_plan_path}", file=sys.stderr)
        sys.exit(1)

    store = _get_storage(args)
    issues = migrate_fix_plan(fix_plan_path, store)

    todo = sum(1 for i in issues if i.status.value == "todo")
    done = sum(1 for i in issues if i.status.value == "human_done")
    print(f"Migrated {len(issues)} issues ({todo} todo, {done} done)")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def _plan(args: argparse.Namespace) -> None:
    import anyio
    from agents.planner import run_planner
    from core.models import Issue, IssueStatus, Board
    from core.storage import ProjectStorage
    import json
    import re

    store = _get_storage(args)

    async def _run():
        result, session_id = await run_planner(args.prompt)
        if not result:
            print("Planner returned no result.", file=sys.stderr)
            return

        # Check if planner wrote fix_plan.md
        from config import WORKSPACE_DIR
        fix_plan = WORKSPACE_DIR / "fix_plan.md"
        if fix_plan.exists() and "- [ ]" in fix_plan.read_text():
            # Migrate fix_plan to issues
            from core.migrate import migrate_fix_plan
            issues = migrate_fix_plan(fix_plan, store)
            print(f"Planner created {len(issues)} issues from fix_plan.md")
        else:
            print("Planner did not create fix_plan.md with tasks.")

    anyio.run(_run)


# ---------------------------------------------------------------------------
# Plan Issue (per-issue planning agent)
# ---------------------------------------------------------------------------

def _plan_issue(args: argparse.Namespace) -> None:
    import anyio
    from pathlib import Path

    store = _get_storage(args)
    project = store.load_project_meta()
    if not project or not project.workspaces:
        print("Error: project has no workspace configured.", file=sys.stderr)
        sys.exit(1)
    workspace = Path(project.workspaces[0]).resolve()

    try:
        issue = store.load_issue(args.issue_id)
    except FileNotFoundError:
        print(f"Issue not found: {args.issue_id}", file=sys.stderr)
        sys.exit(1)

    async def _execute():
        from core.planner import run_issue_planning

        print(f"Planning {issue.id}: {issue.title}", flush=True)
        stats = await run_issue_planning(issue, store, workspace)

        if stats.get("plan_generated"):
            print(f"\nPlan generated for {issue.id}", flush=True)
            plan = store.load_issue_plan(issue.id)
            if plan:
                print(f"\n{plan}", flush=True)
        else:
            print(f"\nNo plan generated for {issue.id}", flush=True)

        if stats.get("split_issues"):
            print(f"\nSplit into {len(stats['split_issues'])} child issues:", flush=True)
            for cid in stats["split_issues"]:
                child = store.load_issue(cid)
                print(f"  {cid}: {child.title}", flush=True)

        cost = stats.get("cost_usd", 0)
        print(f"\nCost: ${cost:.2f}", flush=True)

    anyio.run(_execute)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _run(args: argparse.Namespace) -> None:
    import anyio
    from pathlib import Path

    store = _get_storage(args)
    project = store.load_project_meta()
    if not project or not project.workspaces:
        print("Error: project has no workspace configured.", file=sys.stderr)
        sys.exit(1)
    workspace = Path(project.workspaces[0]).resolve()

    async def _execute():
        from core.ralph_loop import run_issue_loop, run_board, find_ready_issues

        if args.issue_id:
            try:
                issue = store.load_issue(args.issue_id)
            except FileNotFoundError:
                print(f"Issue not found: {args.issue_id}", file=sys.stderr)
                return
            print(f"Running {issue.id}: {issue.title}", flush=True)
            stats = await run_issue_loop(issue, store, workspace)
            status = "PASSED" if stats["success"] else "NEEDS REVIEW"
            print(f"\n{status} — ${stats['cost_usd']:.2f}, {stats['attempts']} attempts", flush=True)
        else:
            ready = find_ready_issues(store)
            if not ready:
                print("No actionable issues (todo + unblocked).")
                return
            print(f"Running {len(ready)} actionable issues...", flush=True)
            all_stats = await run_board(store, workspace)
            total_cost = sum(s.get("cost_usd", 0) for s in all_stats)
            ok = sum(1 for s in all_stats if s.get("success"))
            print(f"\nCompleted: {ok}/{len(all_stats)} passed, total cost=${total_cost:.2f}", flush=True)

    anyio.run(_execute)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Ekko — AI-driven development with kanban issue management",
    )
    parser.add_argument("--project", help="Project storage directory", default=None)
    sub = parser.add_subparsers(dest="command")

    # -- project --
    project_parser = sub.add_parser("project", help="Manage projects")
    project_sub = project_parser.add_subparsers(dest="project_command")

    p = project_sub.add_parser("create", help="Create a new project")
    p.add_argument("name", help="Project name")
    p.add_argument("workspace_path", help="Path to workspace directory")
    p.add_argument("--key", default="ISS", help="Issue ID prefix (e.g. BLOG → BLOG-1, BLOG-2). Default: ISS")
    p.set_defaults(func=_project_create)

    p = project_sub.add_parser("list", help="List all projects")
    p.set_defaults(func=_project_list)

    p = project_sub.add_parser("switch", help="Switch active project")
    p.add_argument("project_id", help="Project ID to switch to")
    p.set_defaults(func=_project_switch)

    p = project_sub.add_parser("show", help="Show project details")
    p.add_argument("project_id", nargs="?", default=None, help="Project ID (default: active)")
    p.set_defaults(func=_project_show)

    p = project_sub.add_parser("update", help="Update project settings")
    p.add_argument("project_id", nargs="?", default=None, help="Project ID (default: active)")
    p.add_argument("--name", default=None, help="New project name")
    p.add_argument("--key", default=None, help="New issue ID prefix (e.g. BLOG → BLOG-1, BLOG-2)")
    p.set_defaults(func=_project_update)

    p = project_sub.add_parser("delete", help="Delete a project")
    p.add_argument("project_id", help="Project ID to delete")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p.set_defaults(func=_project_delete)

    # -- issue --
    issue_parser = sub.add_parser("issue", help="Manage issues")
    issue_sub = issue_parser.add_subparsers(dest="issue_command")

    # issue create
    p = issue_sub.add_parser("create", help="Create a new issue")
    p.add_argument("title", help="Issue title")
    p.add_argument("--label", action="append", help="Add label (repeatable)")
    p.add_argument("--priority", default="medium", choices=["low", "medium", "high", "urgent"])
    p.set_defaults(func=_issue_create)

    # issue list
    p = issue_sub.add_parser("list", help="List issues")
    p.add_argument("--status", default=None, help="Filter by status")
    p.set_defaults(func=_issue_list)

    # issue show
    p = issue_sub.add_parser("show", help="Show issue details")
    p.add_argument("issue_id", help="Issue ID (e.g. ISS-abc123)")
    p.set_defaults(func=_issue_show)

    # issue move
    p = issue_sub.add_parser("move", help="Move issue to a new status")
    p.add_argument("issue_id", help="Issue ID")
    p.add_argument("status", help="Target status (e.g. todo, in_progress)")
    p.set_defaults(func=_issue_move)

    # issue delete
    p = issue_sub.add_parser("delete", help="Delete an issue")
    p.add_argument("issue_id", help="Issue ID (e.g. ISS-1)")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p.set_defaults(func=_issue_delete)

    # -- review --
    review_parser = sub.add_parser("review", help="Review an agent-done issue")
    review_parser.add_argument("issue_id", help="Issue ID to review")
    review_parser.add_argument("--approve", action="store_true", help="Approve the issue")
    review_parser.add_argument("--reject", action="store_true", help="Reject the issue")
    review_parser.add_argument("--comment", default=None, help="Feedback comment (used with --reject)")
    review_parser.set_defaults(func=_review)

    # -- serve --
    serve_parser = sub.add_parser("serve", help="Start Web UI (FastAPI + Vite)")
    serve_parser.add_argument("--port", type=int, default=8080, help="Backend port (default 8080)")
    serve_parser.add_argument("--dev", action="store_true", help="Run Vite dev server alongside")
    serve_parser.set_defaults(func=_serve)

    # -- migrate --
    migrate_parser = sub.add_parser("migrate", help="Migrate fix_plan.md to kanban issues")
    migrate_parser.add_argument("--fix-plan", default=None, help="Path to fix_plan.md")
    migrate_parser.set_defaults(func=_migrate)

    # -- plan --
    plan_parser = sub.add_parser("plan", help="Run interactive planner → create issues")
    plan_parser.add_argument("prompt", help="Requirement description")
    plan_parser.set_defaults(func=_plan)

    # -- plan-issue --
    plan_issue_parser = sub.add_parser("plan-issue", help="Run planning agent for a specific issue")
    plan_issue_parser.add_argument("issue_id", help="Issue ID to plan (e.g. ISS-4)")
    plan_issue_parser.set_defaults(func=_plan_issue)

    # -- run --
    run_parser = sub.add_parser("run", help="Run execution loop for pending issues")
    run_parser.add_argument("issue_id", nargs="?", default=None, help="Run a specific issue (optional)")
    run_parser.set_defaults(func=_run)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    func = getattr(args, "func", None)
    if func:
        func(args)
    else:
        # Subcommand without sub-subcommand (e.g. `harness issue` with no action)
        # Find the subparser and print its help
        for action in parser._subparsers._actions:
            if isinstance(action, argparse._SubParsersAction):
                if args.command in action.choices:
                    action.choices[args.command].print_help()
                    break
        sys.exit(1)
