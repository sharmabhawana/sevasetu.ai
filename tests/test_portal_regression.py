# -*- coding: utf-8 -*-
"""
Portal regression tests: ensures existing portal routes, OAuth discovery,
and new evaluation dashboard operate seamlessly without regressions.
"""

import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
app_dir = os.path.join(BASE_DIR, "app")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

import app as portal
import oauth as portal_oauth
from evals.runner import _EVAL_KEY, _EVAL_KID


@pytest.fixture
def client():
    portal.app.config["TESTING"] = True
    # Populate signing key cache for local test runs
    portal_oauth._KEY_CACHE["kid"] = _EVAL_KID
    portal_oauth._KEY_CACHE["priv"] = _EVAL_KEY
    with portal.app.test_client() as c:
        yield c


def test_portal_index(client):
    """Ensure homepage renders successfully."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Sewa Setu" in res.text or "Pension" in res.text


def test_portal_about(client):
    """Ensure about page renders successfully."""
    res = client.get("/about")
    assert res.status_code == 200


def test_oauth_metadata_discovery(client):
    """Ensure RFC 8414 authorization server metadata is served."""
    res = client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 200
    data = res.get_json()
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "jwks_uri" in data
    assert "scopes_supported" in data
    assert "citizen" in data["scopes_supported"]
    assert "officer" in data["scopes_supported"]


def test_public_jwks(client):
    """Ensure public JWKS contains RS256 keys."""
    res = client.get("/.well-known/jwks.json")
    assert res.status_code == 200
    data = res.get_json()
    assert "keys" in data
    assert len(data["keys"]) > 0
    assert data["keys"][0]["alg"] == "RS256"


def test_eval_dashboard_route(client):
    """Ensure /eval-dashboard renders successfully with metrics and personas."""
    res = client.get("/eval-dashboard")
    assert res.status_code == 200
    assert "AI Agent Evaluation Dashboard" in res.text
    assert "Sewali Gogoi" in res.text
    assert "Pass Percentage" in res.text


def test_eval_api_results(client):
    """Ensure /api/eval-results returns structured JSON data."""
    res = client.get("/api/eval-results")
    assert res.status_code == 200
    data = res.get_json()
    assert "summary" in data
    assert data["summary"]["total_evaluations"] == 16
    assert data["summary"]["pass_percentage"] == 100.0


def test_assessor_admin_login(client):
    """Ensure dedicated assessor administrator account can log in and view admin dashboard."""
    portal.ASSESSOR_USERNAME = "assessor_admin"
    portal.ASSESSOR_PASSWORD = "TestAssessorPassword123!"

    # 1. Invalid password fails
    res_fail = client.post("/admin", data={"username": "assessor_admin", "password": "WrongPassword"}, follow_redirects=True)
    assert "Invalid credentials" in res_fail.text

    # 2. Valid assessor password succeeds and establishes session
    res_ok = client.post("/admin", data={"username": "assessor_admin", "password": "TestAssessorPassword123!"}, follow_redirects=False)
    assert res_ok.status_code == 302
    assert "/admin/dashboard" in res_ok.headers["Location"]

    with client.session_transaction() as sess:
        assert sess.get("admin") is True
        assert sess.get("admin_user") == "assessor_admin"

