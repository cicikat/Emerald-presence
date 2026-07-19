from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
INDEX = ROOT / "admin" / "static" / "index.html"
I18N = ROOT / "admin" / "static" / "i18n.js"


def test_i18n_runtime_is_wired_with_persistent_chinese_default():
    index = INDEX.read_text(encoding="utf-8")
    runtime = I18N.read_text(encoding="utf-8")

    assert '<script src="/static/i18n.js"></script>' in index
    assert "const DEFAULT_LANGUAGE = 'zh-CN';" in runtime
    assert "presence.admin.language" in runtime
    assert "localStorage.setItem(STORAGE_KEY, language)" in runtime
    assert "window.dispatchEvent(new CustomEvent('admin-language-changed'" in runtime
    assert "console.debug(`[admin-i18n] missing ${currentLanguage}: ${key}`)" in runtime


def test_all_navigation_links_use_semantic_i18n_keys():
    index = INDEX.read_text(encoding="utf-8")
    nav = re.search(r"<nav>(.*?)</nav>", index, re.S)
    assert nav is not None

    links = re.findall(r'<a\b[^>]*data-page="[^"]+"[^>]*>(.*?)</a>', nav.group(1), re.S)
    assert links
    assert all('data-i18n="nav.' in link for link in links)
    assert 'id="admin-language-select"' in index
