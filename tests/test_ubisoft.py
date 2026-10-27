"""Ubisoft Connect imports use the Playnite-compatible local cache."""

import json
import sqlite3

from web.sources import ubisoft
from web.services import database_builder


def _varint(value):
    encoded = bytearray()
    while value >= 0x80:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _cache_game(uplay_id, game_info, install_id=0):
    fields = (
        b"\x08" + _varint(uplay_id)
        + b"\x10" + _varint(install_id)
        + b"\x1a" + _varint(len(game_info)) + game_info.encode()
    )
    return b"\x0a" + _varint(len(fields)) + fields


def _write_cache(path):
    games = [
        _cache_game(100, """\
root:
  name: game_name
  icon_image: icon_name
  thumb_image: cover_name
  background_image: background_name
  addons:
    - id: 200
  start_game:
    online: {}
localizations:
  default:
    game_name: Assassin's Creed II
    icon_name: icons/ac2.png
    cover_name: covers/ac2.jpg
    background_name: backgrounds/ac2.jpg
"""),
        _cache_game(200, """\
root:
  name: DLC
  start_game:
    online: {}
"""),
        _cache_game(300, """\
root:
  name: Third Party
  third_party_platform:
    name: Steam
  start_game:
    online: {}
"""),
        _cache_game(400, """\
root:
  name: ULC
  is_ulc: true
  start_game:
    online: {}
"""),
        _cache_game(500, """\
root:
  name: Missing Launcher Entry
"""),
        _cache_game(600, """\
root:
  name: Far Cry
  start_game:
    online: {}
"""),
    ]
    path.write_bytes(b"".join(games))


def test_get_ubisoft_library_matches_playnite_cache_rules(tmp_path, monkeypatch):
    cache_path = tmp_path / "configurations"
    _write_cache(cache_path)
    monkeypatch.setattr(ubisoft, "UBISOFT_CONFIGURATIONS_PATH", cache_path)

    games = ubisoft.get_ubisoft_library()

    assert games == [
        {
            "store_id": "100",
            "name": "Assassin's Creed II",
            "cover_image": "https://ubistatic3-a.akamaihd.net/orbit/uplay_launcher_3_0/assets/covers/ac2.jpg",
            "background_image": "https://ubistatic3-a.akamaihd.net/orbit/uplay_launcher_3_0/assets/backgrounds/ac2.jpg",
            "icon": "https://ubistatic3-a.akamaihd.net/orbit/uplay_launcher_3_0/assets/icons/ac2.png",
            "supported_platforms": ["pc_windows"],
        },
        {
            "store_id": "600",
            "name": "Far Cry",
            "cover_image": None,
            "background_image": None,
            "icon": None,
            "supported_platforms": ["pc_windows"],
        },
    ]


def test_import_ubisoft_games_persists_cache_ids_and_artwork(monkeypatch, tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE games (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            store TEXT NOT NULL,
            store_id TEXT,
            cover_image TEXT,
            background_image TEXT,
            icon TEXT,
            supported_platforms TEXT,
            extra_data TEXT,
            updated_at TEXT,
            removed BOOLEAN DEFAULT 0,
            UNIQUE(store, store_id)
        );
    """)
    games = [{
        "store_id": "100",
        "name": "Assassin's Creed II",
        "cover_image": "cover.jpg",
        "background_image": "background.jpg",
        "icon": "icon.png",
        "supported_platforms": ["pc_windows"],
    }]
    monkeypatch.setattr(ubisoft, "get_ubisoft_library", lambda: games)

    count = database_builder.import_ubisoft_games(conn)

    row = conn.execute(
        "SELECT name, store, store_id, cover_image, background_image, icon, "
        "supported_platforms, extra_data FROM games"
    ).fetchone()
    assert count == 1
    assert row[:6] == ("Assassin's Creed II", "ubisoft", "100", "cover.jpg", "background.jpg", "icon.png")
    assert json.loads(row[6]) == ["pc_windows"]
    assert json.loads(row[7]) == games[0]
