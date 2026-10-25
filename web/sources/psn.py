"""PlayStation Network library integration.

Sony does not expose a documented public library API. This adapter follows the
mobile OAuth and purchased-library requests used by the Playnite PSN extension.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken

from ..services.settings import get_setting, set_setting, delete_setting

AUTHORIZE_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize"
TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
GRAPHQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"
REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
CLIENT_AUTHORIZATION = "MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A=" 
TOKEN_SCOPE = "psn:mobile.v2.core psn:clientapp"
PURCHASED_QUERY_HASH = "827a423f6a8ddca4107ac01395af2ec0eafd8396fc7fa204aaf9b7ed2eefa168"
USER_AGENT = "Mozilla/5.0 (Backlogia PSN integration)"

PSN_NPSSO = "psn_npsso"
PSN_TOKENS = "psn_tokens"
PSN_ALLOW_PLAINTEXT = "PSN_ALLOW_PLAINTEXT"
PSN_ENCRYPTION_KEY = "PSN_ENCRYPTION_KEY"


class PsnConfigurationError(RuntimeError):
    pass


class PsnAuthenticationError(RuntimeError):
    pass


def _fernet() -> Fernet | None:
    key = os.environ.get(PSN_ENCRYPTION_KEY, "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise PsnConfigurationError("PSN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def _protect(value: str) -> str:
    fernet = _fernet()
    if fernet:
        return "fernet:" + fernet.encrypt(value.encode()).decode()
    if os.environ.get(PSN_ALLOW_PLAINTEXT, "false").lower() == "true":
        return "plain:" + value
    raise PsnConfigurationError(
        "Set PSN_ENCRYPTION_KEY, or explicitly set PSN_ALLOW_PLAINTEXT=true for local plaintext storage"
    )


def _unprotect(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("fernet:"):
        fernet = _fernet()
        if not fernet:
            raise PsnConfigurationError("PSN_ENCRYPTION_KEY is required to decrypt PSN credentials")
        try:
            return fernet.decrypt(value[7:].encode()).decode()
        except InvalidToken as exc:
            raise PsnConfigurationError("PSN credentials cannot be decrypted with the configured key") from exc
    if value.startswith("plain:"):
        if os.environ.get(PSN_ALLOW_PLAINTEXT, "false").lower() != "true":
            raise PsnConfigurationError("Plaintext PSN storage is disabled; set PSN_ALLOW_PLAINTEXT=true to use it")
        return value[6:]
    # Legacy/unconfigured values are never silently accepted.
    raise PsnConfigurationError("PSN credentials use an unsupported storage format")


def _parse_npsso(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PsnAuthenticationError("NPSSO input is not valid JSON") from exc
        value = str(parsed.get("npsso", "")).strip()
        if not value:
            raise PsnAuthenticationError('NPSSO JSON must contain a non-empty "npsso" value')
    return value


def _load_tokens() -> dict[str, Any] | None:
    raw = _unprotect(get_setting(PSN_TOKENS, ""))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PsnConfigurationError("Stored PSN token data is invalid") from exc


def _save_tokens(tokens: dict[str, Any]) -> None:
    set_setting(PSN_TOKENS, _protect(json.dumps(tokens, separators=(",", ":"))))


def _request_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


def _token_request(session: requests.Session, data: dict[str, str]) -> dict[str, Any]:
    response = session.post(
        TOKEN_URL,
        data=data,
        headers={"Authorization": f"Basic {CLIENT_AUTHORIZATION}"},
        timeout=30,
    )
    if not response.ok:
        raise PsnAuthenticationError(f"Sony token request failed with HTTP {response.status_code}")
    payload = response.json()
    if not payload.get("access_token"):
        raise PsnAuthenticationError("Sony token response did not contain an access token")
    return payload


def _load_npsso() -> str:
    # Environment credentials are supplied as the raw NPSSO or ssocookie JSON.
    # Database credentials are stored with the provider's encryption wrapper.
    environment_value = os.environ.get("PSN_NPSSO", "").strip()
    if environment_value:
        return _parse_npsso(environment_value)
    return _parse_npsso(_unprotect(get_setting(PSN_NPSSO, "")) or "")


def _get_access_token(session: requests.Session) -> str:
    tokens = _load_tokens() or {}
    expires_at = float(tokens.get("refresh_token_expires_at", 0))
    if tokens.get("refresh_token") and expires_at > datetime.now(timezone.utc).timestamp():
        try:
            payload = _token_request(session, {
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "scope": TOKEN_SCOPE,
                "token_format": "jwt",
            })
            _save_tokens({
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token", tokens["refresh_token"]),
                "refresh_token_expires_at": datetime.now(timezone.utc).timestamp() + float(payload.get("refresh_token_expires_in", 0)),
            })
            return payload["access_token"]
        except requests.RequestException:
            pass
        except PsnAuthenticationError:
            pass

    npsso = _load_npsso()
    if not npsso:
        raise PsnAuthenticationError("PlayStation authentication is required; enter a fresh NPSSO value")

    response = session.get(
        AUTHORIZE_URL,
        params={
            "access_type": "offline",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": TOKEN_SCOPE,
        },
        cookies={"npsso": npsso},
        allow_redirects=False,
        timeout=30,
    )
    location = response.headers.get("Location", "")
    query = parse_qs(urlparse(location).query)
    code = query.get("code", [""])[0]
    if not code:
        if query.get("error", [""])[0] == "login_required":
            raise PsnAuthenticationError("Sony rejected the NPSSO value; sign in again and provide a fresh value")
        raise PsnAuthenticationError("Sony authorization did not return an authorization code")

    payload = _token_request(session, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "token_format": "jwt",
    })
    _save_tokens({
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "refresh_token_expires_at": datetime.now(timezone.utc).timestamp() + float(payload.get("refresh_token_expires_in", 0)),
    })
    return payload["access_token"]


def _graphql(session: requests.Session, token: str, variables: dict[str, Any]) -> dict[str, Any]:
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": PURCHASED_QUERY_HASH}}
    response = session.get(
        GRAPHQL_URL,
        params={
            "operationName": "getPurchasedGameList",
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(extensions, separators=(",", ":")),
        },
        headers={"Authorization": f"Bearer {token}", "x-apollo-operation-name": "pn_psn"},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Sony library request failed with HTTP {response.status_code}")
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError("Sony library request returned an API error")
    return payload


def get_psn_library() -> list[dict[str, Any]]:
    session = _request_session()
    token = _get_access_token(session)
    games: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = _graphql(session, token, {
            "isActive": True,
            "platform": ["ps4", "ps5"],
            "start": offset,
            "size": 100,
            "sortBy": "ACTIVE_DATE",
            "sortDirection": "desc",
        })
        data = payload.get("data", {}).get("purchasedTitlesRetrieve", {})
        page = data.get("games", [])
        for game in page:
            title_id = str(game.get("titleId") or "").strip()
            platform = str(game.get("platform") or "").lower()
            name = str(game.get("name") or "").strip()
            if title_id and name and platform in {"ps4", "ps5"}:
                games.append({
                    "store_id": title_id,
                    "name": name,
                    "platform": platform,
                    "membership": game.get("membership") or game.get("subscriptionService"),
                    "entitlement_type": "subscription" if (game.get("membership") or game.get("subscriptionService")) else "purchased",
                })
        page_info = data.get("pageInfo", {})
        if page_info.get("isLast") or not page:
            return games
        offset += len(page)


def save_npsso(value: str) -> None:
    npsso = _parse_npsso(value)
    if not npsso:
        raise PsnAuthenticationError("NPSSO cannot be empty")
    set_setting(PSN_NPSSO, _protect(npsso))
    delete_setting(PSN_TOKENS)


def disconnect() -> None:
    delete_setting(PSN_NPSSO)
    delete_setting(PSN_TOKENS)


def normalize_browser_games(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for game in games:
        title_id = str(game.get("store_id") or game.get("titleId") or "").strip()
        platform = str(game.get("platform") or "").lower()
        name = str(game.get("name") or game.get("title") or "").strip()
        if title_id and name and platform in {"ps4", "ps5"}:
            normalized.append({
                "store_id": title_id,
                "name": name,
                "platform": platform,
                "membership": game.get("membership"),
                "entitlement_type": game.get("entitlement_type") or "unknown",
            })
    return normalized
