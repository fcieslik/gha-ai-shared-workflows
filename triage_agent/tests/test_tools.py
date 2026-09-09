import subprocess
from pathlib import Path

import pytest

from ..tools import LogTools, RepoTools, ToolAccessError
from ..tools.logs import MAX_SLICE_LINES
from ..tools.repo import FALLBACK_COMMITS, MAX_FILE_LINES


def _log(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_read_log_slice_returns_the_requested_window(tmp_path: Path):
    log = _log(tmp_path, "job-1.log", "".join(f"line {n}\n" for n in range(1, 11)))

    tools = LogTools([log])

    assert tools.read_log_slice("job-1.log", start_line=3, line_count=2) == "line 3\nline 4\n"


def test_read_log_slice_is_bounded(tmp_path: Path):
    log = _log(tmp_path, "job-1.log", "".join(f"line {n}\n" for n in range(1, 1000)))

    sliced = LogTools([log]).read_log_slice("job-1.log", line_count=10_000)

    assert len(sliced.splitlines()) == MAX_SLICE_LINES


def test_search_logs_reports_file_and_line(tmp_path: Path):
    log = _log(tmp_path, "job-1.log", "ok\nE   assert 1 == 2\nok\n")

    assert LogTools([log]).search_logs(r"assert") == ["job-1.log:2: E   assert 1 == 2"]


def test_log_tools_refuse_files_collect_did_not_download(tmp_path: Path):
    log = _log(tmp_path, "job-1.log", "ok\n")
    _log(tmp_path, "secrets.txt", "token\n")

    with pytest.raises(ToolAccessError):
        LogTools([log]).read_log_slice("secrets.txt")


def _repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run = lambda *args: subprocess.run(
        args, cwd=workspace, check=True, capture_output=True
    )
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "Test")
    for number in range(1, 4):
        (workspace / f"file{number}.py").write_text(f"value = {number}\n")
        run("git", "add", ".")
        run("git", "commit", "-qm", f"commit {number}")
    return workspace


def test_read_file_and_list_dir_see_the_checkout(tmp_path: Path):
    tools = RepoTools(_repo(tmp_path))

    assert "file1.py" in tools.list_dir(".")
    assert tools.read_file("file1.py") == "value = 1\n"


def test_read_file_is_bounded(tmp_path: Path):
    workspace = _repo(tmp_path)
    (workspace / "big.py").write_text("".join(f"# {n}\n" for n in range(1, 1000)))

    content = RepoTools(workspace).read_file("big.py", line_count=10_000)

    assert len(content.splitlines()) == MAX_FILE_LINES


def test_repo_tools_refuse_paths_outside_the_checkout(tmp_path: Path):
    (tmp_path / "outside.txt").write_text("secret\n")
    tools = RepoTools(_repo(tmp_path))

    with pytest.raises(ToolAccessError):
        tools.read_file("../outside.txt")


def test_grep_finds_matches_in_the_checkout(tmp_path: Path):
    matches = RepoTools(_repo(tmp_path)).grep("value = 2")

    assert matches == ["file2.py:1:value = 2"]


def test_git_history_falls_back_to_the_last_commits_without_a_default_branch(
    tmp_path: Path,
):
    workspace = _repo(tmp_path)

    log = RepoTools(workspace).git_log()

    assert [line.split(" ", 1)[1] for line in log.splitlines()] == [
        "commit 3",
        "commit 2",
        "commit 1",
    ]


def test_git_history_is_capped_at_the_fallback_commit_count(tmp_path: Path):
    workspace = _repo(tmp_path)
    for number in range(4, 25):
        (workspace / f"file{number}.py").write_text(f"value = {number}\n")
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run(
            ["git", "commit", "-qm", f"commit {number}"], cwd=workspace, check=True
        )

    log = RepoTools(workspace).git_log()

    assert len(log.splitlines()) == FALLBACK_COMMITS


def test_git_range_uses_the_merge_base_with_the_default_branch(tmp_path: Path):
    workspace = _repo(tmp_path)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        cwd=workspace,
        check=True,
    )
    (workspace / "file9.py").write_text("value = 9\n")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "branch work"], cwd=workspace, check=True)

    log = RepoTools(workspace).git_log()

    assert [line.split(" ", 1)[1] for line in log.splitlines()] == ["branch work"]


def test_git_diff_covers_the_investigation_range(tmp_path: Path):
    diff = RepoTools(_repo(tmp_path)).git_diff()

    assert "value = 3" in diff


def test_git_show_refuses_commits_outside_the_range(tmp_path: Path):
    workspace = _repo(tmp_path)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        cwd=workspace,
        check=True,
    )
    older = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True
    ).stdout.strip()
    (workspace / "file9.py").write_text("value = 9\n")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "branch work"], cwd=workspace, check=True)
    tools = RepoTools(workspace)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True
    ).stdout.strip()

    assert "branch work" in tools.git_show(head)
    with pytest.raises(ToolAccessError):
        tools.git_show(older)


def test_git_show_accepts_a_commit_inside_the_range(tmp_path: Path):
    workspace = _repo(tmp_path)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        cwd=workspace,
        check=True,
    )
    for name in ("first", "second"):
        (workspace / f"{name}.py").write_text(f"value = '{name}'\n")
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-qm", name], cwd=workspace, check=True)
    middle = subprocess.run(
        ["git", "rev-parse", "HEAD~1"], cwd=workspace, capture_output=True, text=True
    ).stdout.strip()

    assert "first" in RepoTools(workspace).git_show(middle)


def test_grep_returns_nothing_when_there_is_no_match(tmp_path: Path):
    assert RepoTools(_repo(tmp_path)).grep("nothing matches this") == []
