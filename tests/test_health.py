from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.main import create_app


def test_create_app_returns_fastapi_app() -> None:
    assert isinstance(create_app(), FastAPI)


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
