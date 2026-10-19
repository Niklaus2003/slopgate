"""Unit tests for RepoIndex file tree and path extraction."""

from slopgate.state.repo_index import RepoIndex


def test_repo_index_file_paths():
    paths = [
        "src/flask/app.py",
        "src/flask/sessions.py",
        "tests/test_basic.py",
        "README.md",
    ]
    index = RepoIndex.from_file_list(paths)

    assert index.has_file("src/flask/app.py") is True
    assert index.has_file("app.py") is True  # basename check
    assert index.has_file("src\\flask\\sessions.py") is True  # Windows path
    assert index.has_file("nonexistent.py") is False


def test_extract_cited_paths():
    paths = ["flask/sessions.py", "flask/app.py", "tests/test_app.py"]
    index = RepoIndex.from_file_list(paths)

    text = """
    Encountered crash in `flask/sessions.py` line 142 while calling cookie handler.
    Also checked `flask/app.py` and `missing/module.py`.
    """
    found, cited = index.extract_cited_paths(text)
    assert cited == 3
    assert found == 2  # flask/sessions.py and flask/app.py exist; missing/module.py does not


def test_extract_cited_paths_empty():
    index = RepoIndex.from_file_list(["flask/app.py"])
    found, cited = index.extract_cited_paths("No files cited here at all.")
    assert found == 0
    assert cited == 0
