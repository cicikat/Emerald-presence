"""C1: user-authored assets live under userdata/ with legacy read fallback."""

import json
from pathlib import Path

from core.asset_registry import AssetRegistry
from core.data_paths import DataPaths


def test_userdata_is_primary_for_authored_assets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    user_card_dir = tmp_path / "userdata" / "characters" / "cards"
    user_card_dir.mkdir(parents=True)
    (user_card_dir / "companion.json").write_text(
        json.dumps({"name": "Migrated"}), encoding="utf-8"
    )
    legacy_card_dir = tmp_path / "characters"
    legacy_card_dir.mkdir()
    (legacy_card_dir / "companion.json").write_text(
        json.dumps({"name": "Legacy"}), encoding="utf-8"
    )

    paths = DataPaths(mode="production")
    assert paths.user_stickers_dir() == Path("userdata/assets/stickers")
    assert paths.authored_character_dir(char_id="companion") == (
        Path("content/characters/companion")
    )

    authored = tmp_path / "userdata" / "characters" / "authored" / "companion"
    authored.mkdir(parents=True)
    assert paths.authored_character_dir(char_id="companion") == (
        Path("userdata/characters/authored/companion")
    )

    registry = AssetRegistry()
    entry = registry.resolve("companion", "character")
    assert entry.label == "Migrated"
    assert entry.path() == Path("userdata/characters/cards/companion.json")


def test_userdata_falls_back_to_legacy_when_not_migrated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = DataPaths(mode="production")

    legacy_stickers = tmp_path / "assets" / "stickers"
    legacy_stickers.mkdir(parents=True)
    assert paths.stickers_dir() == Path("assets/stickers")

    legacy_authored = tmp_path / "content" / "characters" / "companion"
    legacy_authored.mkdir(parents=True)
    assert paths.authored_character_dir(char_id="companion") == (
        Path("content/characters/companion")
    )
