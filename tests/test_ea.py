"""EA import failures must not be reported as empty libraries."""

import json
from unittest.mock import Mock

import pytest

from web.sources import ea


@pytest.mark.parametrize("status", [200, 400])
def test_unknown_persisted_query_is_reported_as_api_failure(monkeypatch, status):
    response = Mock(status_code=status)
    response.json.return_value = {
        "data": None,
        "errors": [{"message": "PersistedQueryNotFound"}],
    }
    response.text = '{"data":null,"errors":[{"message":"PersistedQueryNotFound"}]}'
    session = Mock()
    session.get.return_value = response
    monkeypatch.setattr(ea.requests, "Session", lambda: session)

    with pytest.raises(RuntimeError, match="PersistedQueryNotFound"):
        ea.get_owned_games("test-token")


def test_owned_game_products_and_cursor_pagination(monkeypatch):
    session = Mock()
    pages = []
    for offer_id, cursor in [("offer-1", "page-2"), ("offer-2", None)]:
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"me": {"ownedGameProducts": {
            "items": [{"originOfferId": offer_id, "product": {"name": offer_id}}],
            "next": cursor,
        }}}}
        pages.append(response)
    session.get.side_effect = pages
    monkeypatch.setattr(ea.requests, "Session", lambda: session)

    games = ea.get_owned_games("test-token")

    assert [game["offer_id"] for game in games] == ["offer-1", "offer-2"]
    calls = session.get.call_args_list
    assert len(calls) == 2
    params = calls[0].kwargs["params"]
    assert params["operationName"] == "getPreloadedOwnedGames"
    assert json.loads(params["extensions"])["persistedQuery"]["sha256Hash"] == (
        "779f1cd1355699752e20c0b3877847f4e3010ef5de131c248e98f8eff84f0718"
    )
    assert json.loads(params["variables"])["next"] == "0"
    assert json.loads(calls[1].kwargs["params"]["variables"])["next"] == "page-2"
    assert calls[0].kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert calls[0].kwargs["timeout"] == 30


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_errors_request_token_refresh(monkeypatch, status):
    session = Mock()
    session.get.return_value = Mock(status_code=status)
    monkeypatch.setattr(ea.requests, "Session", lambda: session)

    with pytest.raises(RuntimeError, match="refresh your bearer token"):
        ea.get_owned_games("test-token")


def test_failure_after_first_page_does_not_return_partial_library(monkeypatch):
    session = Mock()
    first = Mock(status_code=200)
    first.json.return_value = {"data": {"me": {"ownedGameProducts": {
        "items": [{"originOfferId": "one", "product": {"name": "Game"}}],
        "next": "page-2",
    }}}}
    session.get.side_effect = [first, Mock(status_code=401)]
    monkeypatch.setattr(ea.requests, "Session", lambda: session)

    with pytest.raises(RuntimeError, match="authentication failed"):
        ea.get_owned_games("test-token")


def test_import_reports_query_failure_without_token_advice(monkeypatch, capsys):
    from web.services.database_builder import import_ea_games

    monkeypatch.setattr(ea, "get_ea_library", Mock(
        side_effect=RuntimeError("EA API error: PersistedQueryNotFound")
    ))
    conn = Mock()

    assert import_ea_games(conn) == 0

    output = capsys.readouterr().out
    assert "EA import error: EA API error: PersistedQueryNotFound" in output
    assert "Get a new EA bearer token" not in output
    conn.cursor.return_value.execute.assert_not_called()
    conn.commit.assert_not_called()
