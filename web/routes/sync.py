# routes/sync.py
# Store sync and IGDB sync routes

import json
import sqlite3
from datetime import datetime
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import DATABASE_PATH
from ..services.jobs import (
    JobType, create_job, update_job_progress, complete_job, fail_job, run_job_async
)

router = APIRouter(tags=["Sync"])


class StoreType(str, Enum):
    steam = "steam"
    epic = "epic"
    gog = "gog"
    itch = "itch"
    humble = "humble"
    battlenet = "battlenet"
    amazon = "amazon"
    ea = "ea"
    xbox = "xbox"
    ubisoft = "ubisoft"
    psn = "psn"
    local = "local"
    all = "all"


@router.post("/api/sync/store/{store}")
def sync_store(store: StoreType):
    """Sync games from a store."""
    # Import here to avoid circular imports
    from ..services.database_builder import (
        create_database, import_steam_games, import_epic_games,
        import_gog_games, import_itch_games, import_humble_games,
        import_battlenet_games, import_amazon_games, import_ea_games,
        import_xbox_games, import_ubisoft_games, import_local_games, import_psn_games
    )

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        # Ensure database tables exist
        create_database()
        conn = sqlite3.connect(DATABASE_PATH)

        results = {}

        if store == StoreType.steam or store == StoreType.all:
            results["steam"] = import_steam_games(conn)

        if store == StoreType.epic or store == StoreType.all:
            results["epic"] = import_epic_games(conn)

        if store == StoreType.gog or store == StoreType.all:
            results["gog"] = import_gog_games(conn)

        if store == StoreType.itch or store == StoreType.all:
            results["itch"] = import_itch_games(conn)

        if store == StoreType.humble or store == StoreType.all:
            results["humble"] = import_humble_games(conn)

        if store == StoreType.battlenet or store == StoreType.all:
            results["battlenet"] = import_battlenet_games(conn)

        if store == StoreType.amazon or store == StoreType.all:
            results["amazon"] = import_amazon_games(conn)

        if store == StoreType.ea or store == StoreType.all:
            results["ea"] = import_ea_games(conn)

        if store == StoreType.xbox or store == StoreType.all:
            results["xbox"] = import_xbox_games(conn)

        if store == StoreType.psn or store == StoreType.all:
            results["psn"] = import_psn_games(conn)
        if store == StoreType.ubisoft or store == StoreType.all:
            results["ubisoft"] = import_ubisoft_games(conn)
        if store == StoreType.local or store == StoreType.all:
            results["local"] = import_local_games(conn)

        conn.close()

        if store == StoreType.all:
            total = sum(results.values())
            message = f"Synced {total} games: " + ", ".join(
                f"{s.capitalize()}: {c}" for s, c in results.items()
            )
        else:
            count = results.get(store.value, 0)
            message = f"Synced {count} games from {store.value.capitalize()}"

        return {"success": True, "message": message, "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/sync/igdb/{mode}")
def sync_igdb(mode: str):
    """Sync IGDB metadata. Mode can be 'new'/'missing' (unmatched only) or 'all' (resync everything)."""
    # Import here to avoid circular imports
    from ..services.igdb_sync import IGDBClient, sync_games as igdb_sync_games, add_igdb_columns

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # Ensure IGDB columns exist
        add_igdb_columns(conn)

        # Initialize client
        client = IGDBClient()

        # Sync games (force=True for 'all' mode)
        force = (mode == "all")
        matched, failed = igdb_sync_games(conn, client, force=force)

        conn.close()

        message = f"IGDB sync complete: {matched} matched, {failed} failed/no match"
        return {"success": True, "message": message, "matched": matched, "failed": failed}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/sync/metacritic/{mode}")
def sync_metacritic(mode: str):
    """Sync Metacritic scores. Mode can be 'missing' (unmatched only) or 'all' (resync everything)."""
    # Import here to avoid circular imports
    from ..services.metacritic_sync import (
        MetacriticClient, sync_games as metacritic_sync_games, add_metacritic_columns
    )

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # Ensure Metacritic columns exist
        add_metacritic_columns(conn)

        # Initialize client
        client = MetacriticClient()

        # Sync games (force=True for 'all' mode)
        force = (mode == "all")
        matched, failed = metacritic_sync_games(conn, client, force=force)

        conn.close()

        message = f"Metacritic sync complete: {matched} matched, {failed} failed/no match"
        return {"success": True, "message": message, "matched": matched, "failed": failed}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Async Job-based Sync Endpoints
# =============================================================================

@router.post("/api/sync/store/{store}/async")
def sync_store_async(store: StoreType):
    """Start a background job to sync games from a store. Returns job ID for tracking."""
    from ..services.database_builder import (
        create_database, import_steam_games, import_epic_games,
        import_gog_games, import_itch_games, import_humble_games,
        import_battlenet_games, import_amazon_games, import_ea_games,
        import_xbox_games, import_ubisoft_games, import_local_games, import_psn_games
    )

    store_name = "all stores" if store == StoreType.all else store.value.capitalize()
    job_id = create_job(JobType.STORE_SYNC, f"Starting {store_name} sync...")

    def run_sync(job_id: str):
        try:
            # Ensure database tables exist
            create_database()
            conn = sqlite3.connect(DATABASE_PATH)

            stores_to_sync = []
            if store == StoreType.all:
                stores_to_sync = [
                    ("steam", import_steam_games),
                    ("epic", import_epic_games),
                    ("gog", import_gog_games),
                    ("itch", import_itch_games),
                    ("humble", import_humble_games),
                    ("battlenet", import_battlenet_games),
                    ("amazon", import_amazon_games),
                    ("ea", import_ea_games),
                    ("xbox", import_xbox_games),
                    ("psn", import_psn_games),
                    ("ubisoft", import_ubisoft_games),
                    ("local", import_local_games),
                ]
            else:
                store_map = {
                    StoreType.steam: ("steam", import_steam_games),
                    StoreType.epic: ("epic", import_epic_games),
                    StoreType.gog: ("gog", import_gog_games),
                    StoreType.itch: ("itch", import_itch_games),
                    StoreType.humble: ("humble", import_humble_games),
                    StoreType.battlenet: ("battlenet", import_battlenet_games),
                    StoreType.amazon: ("amazon", import_amazon_games),
                    StoreType.ea: ("ea", import_ea_games),
                    StoreType.xbox: ("xbox", import_xbox_games),
                    StoreType.psn: ("psn", import_psn_games),
                    StoreType.ubisoft: ("ubisoft", import_ubisoft_games),
                    StoreType.local: ("local", import_local_games),
                }
                if store in store_map:
                    stores_to_sync = [store_map[store]]

            total = len(stores_to_sync)
            results = {}

            for i, (store_name, import_func) in enumerate(stores_to_sync, 1):
                update_job_progress(job_id, i, total, f"Syncing {store_name.capitalize()}...")
                try:
                    count = import_func(conn)
                    results[store_name] = count
                except Exception as e:
                    results[store_name] = f"Error: {str(e)}"

            conn.close()

            # Build result message
            if store == StoreType.all:
                total_games = sum(v for v in results.values() if isinstance(v, int))
                message = f"Synced {total_games} games: " + ", ".join(
                    f"{s.capitalize()}: {c}" for s, c in results.items()
                )
            else:
                count = results.get(store.value, 0)
                message = f"Synced {count} games from {store.value.capitalize()}"

            complete_job(job_id, json.dumps(results), message)

        except Exception as e:
            fail_job(job_id, str(e))

    run_job_async(job_id, run_sync)

    return {"success": True, "job_id": job_id, "message": f"Started {store_name} sync job"}


@router.post("/api/sync/igdb/{mode}/async")
def sync_igdb_async(mode: str):
    """Start a background job to sync IGDB metadata. Returns job ID for tracking."""
    from ..services.igdb_sync import IGDBClient, sync_games as igdb_sync_games, add_igdb_columns

    mode_text = "all games" if mode == "all" else "missing metadata"
    job_id = create_job(JobType.IGDB_SYNC, f"Starting IGDB sync ({mode_text})...")

    def run_sync(job_id: str):
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row

            # Ensure IGDB columns exist
            add_igdb_columns(conn)

            update_job_progress(job_id, 0, 1, f"Initializing IGDB sync...")

            # Progress callback to update job status
            def on_progress(current, total, message):
                update_job_progress(job_id, current, total, message)

            # Initialize client and sync
            client = IGDBClient()
            force = (mode == "all")
            matched, failed = igdb_sync_games(conn, client, force=force, progress_callback=on_progress)

            conn.close()

            message = f"IGDB sync complete: {matched} matched, {failed} failed/no match"
            complete_job(job_id, json.dumps({"matched": matched, "failed": failed}), message)

        except Exception as e:
            fail_job(job_id, str(e))

    run_job_async(job_id, run_sync)

    return {"success": True, "job_id": job_id, "message": f"Started IGDB sync job ({mode_text})"}


@router.post("/api/sync/metacritic/{mode}/async")
def sync_metacritic_async(mode: str):
    """Start a background job to sync Metacritic scores. Returns job ID for tracking."""
    from ..services.metacritic_sync import (
        MetacriticClient, sync_games as metacritic_sync_games, add_metacritic_columns
    )

    mode_text = "all games" if mode == "all" else "missing scores"
    job_id = create_job(JobType.METACRITIC_SYNC, f"Starting Metacritic sync ({mode_text})...")

    def run_sync(job_id: str):
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row

            # Ensure Metacritic columns exist
            add_metacritic_columns(conn)

            update_job_progress(job_id, 0, 1, f"Initializing Metacritic sync...")

            # Progress callback to update job status
            def on_progress(current, total, message):
                update_job_progress(job_id, current, total, message)

            # Initialize client and sync
            client = MetacriticClient()
            force = (mode == "all")
            matched, failed = metacritic_sync_games(conn, client, force=force, progress_callback=on_progress)

            conn.close()

            message = f"Metacritic sync complete: {matched} matched, {failed} failed/no match"
            complete_job(job_id, json.dumps({"matched": matched, "failed": failed}), message)

        except Exception as e:
            fail_job(job_id, str(e))

    run_job_async(job_id, run_sync)

    return {"success": True, "job_id": job_id, "message": f"Started Metacritic sync job ({mode_text})"}


@router.post("/api/sync/protondb/{mode}")
def sync_protondb(mode: str):
    """Sync ProtonDB data. Mode can be 'missing' (unmatched only) or 'all' (resync everything)."""
    from ..services.protondb_sync import (
        ProtonDBClient, sync_games as protondb_sync_games, add_protondb_columns
    )

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # Ensure ProtonDB columns exist
        add_protondb_columns(conn)

        # Initialize client
        client = ProtonDBClient()

        # Sync games (force=True for 'all' mode)
        force = (mode == "all")
        matched, failed = protondb_sync_games(conn, client, force=force)

        conn.close()

        message = f"ProtonDB sync complete: {matched} matched, {failed} failed/no data"
        return {"success": True, "message": message, "matched": matched, "failed": failed}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/sync/protondb/{mode}/async")
def sync_protondb_async(mode: str):
    """Start a background job to sync ProtonDB data. Returns job ID for tracking."""
    from ..services.protondb_sync import (
        ProtonDBClient, sync_games as protondb_sync_games, add_protondb_columns
    )

    mode_text = "all Steam games" if mode == "all" else "missing data"
    job_id = create_job(JobType.PROTONDB_SYNC, f"Starting ProtonDB sync ({mode_text})...")

    def run_sync(job_id: str):
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row

            # Ensure ProtonDB columns exist
            add_protondb_columns(conn)

            update_job_progress(job_id, 0, 1, f"Initializing ProtonDB sync...")

            # Progress callback to update job status
            def on_progress(current, total, message):
                update_job_progress(job_id, current, total, message)

            # Initialize client and sync
            client = ProtonDBClient()
            force = (mode == "all")
            matched, failed = protondb_sync_games(conn, client, force=force, progress_callback=on_progress)

            conn.close()

            message = f"ProtonDB sync complete: {matched} matched, {failed} failed/no data"
            complete_job(job_id, json.dumps({"matched": matched, "failed": failed}), message)

        except Exception as e:
            fail_job(job_id, str(e))

    run_job_async(job_id, run_sync)

    return {"success": True, "job_id": job_id, "message": f"Started ProtonDB sync job ({mode_text})"}


class PsnGame(BaseModel):
    store_id: str
    name: str
    platform: str
    membership: Optional[str] = None
    entitlement_type: Optional[str] = None


class PsnImportRequest(BaseModel):
    games: List[PsnGame]


@router.post("/api/import/psn")
def import_psn_games_from_browser(request: PsnImportRequest):
    """Import owned PS4/PS5 records normalized by the browser fallback."""
    from ..services.database_builder import create_database, import_psn_games
    from ..sources.psn import normalize_browser_games

    try:
        create_database()
        conn = sqlite3.connect(DATABASE_PATH)
        games = normalize_browser_games([game.dict() for game in request.games])
        count = import_psn_games(conn, games)
        conn.close()
        return {"success": True, "message": f"Imported {count} PlayStation games", "count": count}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class PsnAuthRequest(BaseModel):
    npsso: str


@router.post("/api/psn/auth")
def authenticate_psn(request: PsnAuthRequest):
    """Validate and store an NPSSO value by completing Sony authentication."""
    from ..sources.psn import save_npsso, _request_session, _get_access_token

    try:
        save_npsso(request.npsso)
        _get_access_token(_request_session())
        return {"success": True, "message": "PlayStation authenticated"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
class PsnCallbackRequest(BaseModel):
    redirect_url: str


@router.post("/api/psn/auth/callback")
def complete_psn_callback(request: PsnCallbackRequest):
    """Complete a pasted Sony custom-scheme redirect."""
    from urllib.parse import parse_qs, urlparse
    from ..sources.psn import _request_session, _token_request, _save_tokens, REDIRECT_URI

    code = parse_qs(urlparse(request.redirect_url.strip()).query).get("code", [""])[0]
    if not code:
        raise HTTPException(status_code=400, detail="Redirect URL did not contain an authorization code")
    try:
        payload = _token_request(_request_session(), {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "token_format": "jwt",
        })
        _save_tokens({
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token"),
            "refresh_token_expires_at": datetime.now().timestamp() + float(payload.get("refresh_token_expires_in", 0)),
        })
        return {"success": True, "message": "PlayStation callback completed"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@router.get("/api/psn/status")
def psn_status():
    from ..services.settings import get_setting
    from ..sources.psn import PSN_NPSSO

    return {"authenticated": bool(get_setting(PSN_NPSSO, ""))}


@router.delete("/api/psn/auth")
def disconnect_psn():
    from ..sources.psn import disconnect

    disconnect()
    return {"success": True, "message": "PlayStation disconnected"}




class GOGGame(BaseModel):
    id: str
    title: str
    profileUrl: Optional[str] = None
    storeUrl: Optional[str] = None


class GOGImportRequest(BaseModel):
    games: List[GOGGame]




@router.post("/api/import/gog")
def import_gog_games(request: GOGImportRequest):
    """Import games scraped from GOG library page."""
    from ..services.database_builder import create_database

    try:
        # Ensure database exists
        create_database()
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        count = 0
        for game in request.games:
            try:
                # Store extra data
                extra_data = {
                    "profile_url": game.profileUrl,
                    "store_url": game.storeUrl
                }

                cursor.execute("""
                    INSERT INTO games (
                        name, store, store_id, extra_data, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(store, store_id) DO UPDATE SET
                        name = excluded.name,
                        extra_data = excluded.extra_data,
                        updated_at = excluded.updated_at
                """, (
                    game.title,
                    "gog",
                    game.id,
                    json.dumps(extra_data),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                print(f"  Error importing {game.title}: {e}")

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Imported {count} GOG games",
            "count": count
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
