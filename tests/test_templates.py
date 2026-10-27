"""Regression coverage for rendering pages with the installed Starlette API."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.dependencies import get_db
from web.routes.discover import router


def test_discover_renders_template(db_conn):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_conn

    with TestClient(app) as client:
        response = client.get("/discover")

    assert response.status_code == 200
    assert response.template.name == "discover.html"
    assert "request" in response.context
