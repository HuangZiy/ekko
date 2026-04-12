"""Tests for CLI entry point and subcommands."""
import subprocess
import sys
import pytest


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli", *args],
        capture_output=True, text=True,
        cwd="/Users/cn-edisonhuang01/MyWorks/blog-harness",
    )


def test_cli_no_args_shows_help():
    r = run_cli()
    assert r.returncode != 0 or "usage" in r.stdout.lower() or "usage" in r.stderr.lower()


def test_cli_help():
    r = run_cli("--help")
    assert r.returncode == 0
    assert "issue" in r.stdout
    assert "review" in r.stdout


def test_cli_issue_help():
    r = run_cli("issue", "--help")
    assert r.returncode == 0
    assert "create" in r.stdout
    assert "list" in r.stdout
    assert "show" in r.stdout
    assert "move" in r.stdout


def test_cli_review_help():
    r = run_cli("review", "--help")
    assert r.returncode == 0
    assert "approve" in r.stdout.lower() or "approve" in r.stderr.lower()
