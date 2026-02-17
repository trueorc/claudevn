"""Tests for user registration and authentication API endpoints."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.users import router
from services.user_service import UserService, set_user_service


@pytest.fixture
def service():
    svc = UserService(redis_client=None, secret_key="test-api-key")
    set_user_service(svc)
    yield svc
    set_user_service(None)


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestRegisterEndpoint:
    def test_register_first_user_owner(self, client):
        resp = client.post("/api/v1/users/register", json={"username": "alice"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "alice"
        assert data["role"] == "owner"
        assert "token" in data

    def test_register_second_user_member(self, client):
        client.post("/api/v1/users/register", json={"username": "alice"})
        resp = client.post("/api/v1/users/register", json={"username": "bob"})
        assert resp.status_code == 201
        assert resp.json()["role"] == "member"

    def test_register_duplicate_username(self, client):
        client.post("/api/v1/users/register", json={"username": "alice"})
        resp = client.post("/api/v1/users/register", json={"username": "alice"})
        assert resp.status_code == 409

    def test_register_with_email(self, client):
        resp = client.post(
            "/api/v1/users/register",
            json={"username": "alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 201


class TestLoginEndpoint:
    def test_login_success(self, client):
        client.post("/api/v1/users/register", json={"username": "alice"})
        resp = client.post("/api/v1/users/login", json={"username": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "alice"
        assert "token" in data

    def test_login_unknown_user(self, client):
        resp = client.post("/api/v1/users/login", json={"username": "ghost"})
        assert resp.status_code == 404


class TestProfileEndpoints:
    def _register_and_get_token(self, client, username="alice"):
        resp = client.post("/api/v1/users/register", json={"username": username})
        return resp.json()["token"]

    def test_get_profile(self, client):
        token = self._register_and_get_token(client)
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "alice"
        assert data["role"] == "owner"

    def test_get_profile_no_auth(self, client):
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 401

    def test_get_profile_bad_token(self, client):
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert resp.status_code == 401

    def test_update_profile_username(self, client):
        token = self._register_and_get_token(client)
        resp = client.put(
            "/api/v1/users/me",
            json={"username": "alice2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice2"

    def test_update_profile_email(self, client):
        token = self._register_and_get_token(client)
        resp = client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@example.com"

    def test_update_profile_username_conflict(self, client):
        self._register_and_get_token(client, "alice")
        token2 = self._register_and_get_token(client, "bob")
        resp = client.put(
            "/api/v1/users/me",
            json={"username": "alice"},
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp.status_code == 409
