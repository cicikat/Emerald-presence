"""
tests/memeval/conftest.py — memeval 专用 fixture

复用 tests/conftest.py 的 sandbox 隔离（DataPaths._base 重定向到 tmp_path）。
character_loader / config_loader 都以 cwd 相对路径解析（不吃 DataPaths 沙盒），
所以这里不 chdir，改为在真实 characters/ 目录落一个一次性测试角色卡，
用完即删（见 engine.install_test_character，做法与 tests/conftest.py 的
character_b_registered fixture 一致）。
"""

from pathlib import Path

import pytest

from tests.memeval import engine


@pytest.fixture
def case_env(tmp_path, monkeypatch, sandbox):
    """铺一次性测试角色卡（id 每次唯一，`-n auto` 并发 worker 不共享文件名）。

    产出 char_id 字符串，供 engine.run_case(..., char_id=case_env) 使用。
    """
    char_id = engine.new_test_char_id()
    engine.install_test_character(char_id)
    try:
        yield char_id
    finally:
        engine.remove_test_character(char_id)


@pytest.fixture(autouse=True)
def _production_data_untouched():
    """Brief 44 §5：跑完 memeval 后生产 data/ 目录不得出现任何新文件。

    sandbox fixture 已把 DataPaths._base 重定向到 tmp_path，这里是防御性复核——
    万一某个调用路径绕过了 DataPaths 直接拼裸路径，这个断言能第一时间抓到。
    """
    root = Path(__file__).parent.parent.parent / "data"
    before = set(root.rglob("*")) if root.exists() else set()
    yield
    after = set(root.rglob("*")) if root.exists() else set()
    new_files = after - before
    assert not new_files, f"memeval 用例污染了生产 data/ 目录，新增文件：{new_files}"
