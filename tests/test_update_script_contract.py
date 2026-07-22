from pathlib import Path


def test_update_script_guards_running_service_dirty_tree_and_release_package():
    script = Path("AA更新.bat").read_text(encoding="utf-8")
    assert 'if not exist ".git" goto :release_package' in script
    assert 'findstr /I /C:"main.py"' in script
    assert "git status --porcelain" in script
    assert "输入 Y 继续" in script
    assert ":pull_failed" in script
    assert "不要覆盖 data、config.yaml 或 secrets" in script
