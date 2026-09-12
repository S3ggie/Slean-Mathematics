from pathlib import Path


def test_lean_project_exists() -> None:
    assert Path("lean/lakefile.toml").is_file()
    assert Path("lean/lean-toolchain").is_file()
