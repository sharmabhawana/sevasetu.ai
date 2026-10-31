# -*- coding: utf-8 -*-
"""
Authentication and token verification for Sewa Setu MCP servers.
Validates RS256 JWT access tokens issued by the Sewa Setu OAuth 2.1 server.
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
from mcp.server.auth.provider import TokenVerifier, AccessToken
from mcp.server.auth.middleware.auth_context import get_access_token, auth_context_var

logger = logging.getLogger("sewasetu.mcp.auth")

DEFAULT_ISSUER = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
ISSUER = os.environ.get("OAUTH_ISSUER", DEFAULT_ISSUER).rstrip("/")
JWKS_URL = os.environ.get("JWKS_URL", f"{ISSUER}/.well-known/jwks.json")

_JWKS_CACHE: Dict[str, Any] = {}
_JWKS_CACHE_TIME: float = 0.0
JWKS_CACHE_TTL = 300  # 5 minutes


def fetch_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch public JWKS keys from the portal authorization server."""
    global _JWKS_CACHE, _JWKS_CACHE_TIME
    now = time.time()
    if not force_refresh and _JWKS_CACHE and (now - _JWKS_CACHE_TIME) < JWKS_CACHE_TTL:
        return _JWKS_CACHE

    try:
        resp = requests.get(JWKS_URL, timeout=5)
        if resp.status_code == 200:
            _JWKS_CACHE = resp.json()
            _JWKS_CACHE_TIME = now
            return _JWKS_CACHE
    except Exception as e:
        logger.warning(f"Could not fetch JWKS from {JWKS_URL}: {e}")

    # Fallback: check if we can read directly from database if on same machine
    try:
        from mcp_common.db import get_db_connection
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT kid, private_pem FROM oauth_keys ORDER BY created_at ASC LIMIT 1")
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                from cryptography.hazmat.primitives import serialization
                priv = serialization.load_pem_private_key(row[1].encode("ascii"), password=None)
                jwk = json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
                jwk.update({"kid": row[0], "alg": "RS256", "use": "sig"})
                _JWKS_CACHE = {"keys": [jwk]}
                _JWKS_CACHE_TIME = now
                return _JWKS_CACHE
    except Exception as e:
        logger.warning(f"Database JWKS fallback failed: {e}")

    return _JWKS_CACHE or {"keys": []}


def verify_oauth_jwt(
    token: str,
    expected_role: str,
    expected_scope: str,
    expected_audience: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Verify RS256 JWT token against Sewa Setu OAuth 2.1 specs:
    - Signature check against JWKS
    - Issuer check
    - Audience check (resource indicator)
    - Expiration check
    - Role & Scope verification
    """
    if not token:
        return None

    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as e:
        logger.warning(f"Invalid token header: {e}")
        return None

    kid = unverified_header.get("kid")
    jwks = fetch_jwks()
    key_dict = None
    for k in jwks.get("keys", []):
        if kid is None or k.get("kid") == kid:
            key_dict = k
            break

    if not key_dict:
        # Retry with force refresh in case key was rotated
        jwks = fetch_jwks(force_refresh=True)
        for k in jwks.get("keys", []):
            if kid is None or k.get("kid") == kid:
                key_dict = k
                break

    if not key_dict:
        logger.warning(f"Signing key kid={kid} not found in JWKS")
        return None

    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(key_dict))
        decode_options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_iss": True,
            "verify_aud": False,  # Manual flexible audience check below
        }
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=ISSUER,
            options=decode_options
        )

        # Audience verification
        aud = claims.get("aud")
        if expected_audience:
            if isinstance(aud, list):
                if expected_audience not in aud and ISSUER not in aud:
                    logger.warning(f"Audience mismatch: expected {expected_audience}, got {aud}")
                    return None
            elif aud != expected_audience and aud != ISSUER:
                logger.warning(f"Audience mismatch: expected {expected_audience}, got {aud}")
                return None

        # Role verification (critical security boundary)
        token_role = claims.get("role")
        if token_role != expected_role:
            logger.warning(f"Role mismatch: expected {expected_role}, got {token_role}")
            return None

        # Scope verification
        token_scope = claims.get("scope", "")
        scopes = token_scope.split()
        if expected_scope not in scopes:
            logger.warning(f"Scope mismatch: expected {expected_scope}, got {token_scope}")
            return None

        # Subject verification
        sub = claims.get("sub", "")
        if not sub.startswith(f"{expected_role}:"):
            logger.warning(f"Subject format invalid for role {expected_role}: {sub}")
            return None

        return claims
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return None
    except jwt.InvalidIssuerError:
        logger.warning(f"Invalid token issuer, expected {ISSUER}")
        return None
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return None


class BaseSewaSetuTokenVerifier(TokenVerifier):
    def __init__(self, expected_role: str, expected_scope: str, expected_audience: Optional[str] = None):
        self.expected_role = expected_role
        self.expected_scope = expected_scope
        self.expected_audience = expected_audience

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        claims = verify_oauth_jwt(
            token,
            expected_role=self.expected_role,
            expected_scope=self.expected_scope,
            expected_audience=self.expected_audience
        )
        if not claims:
            return None

        return AccessToken(
            token=token,
            client_id=claims.get("client_id", "unknown"),
            scopes=claims.get("scope", "").split(),
            expires_at=claims.get("exp"),
            resource=claims.get("aud") if isinstance(claims.get("aud"), str) else None,
            subject=claims.get("sub"),
            claims=claims
        )


class CitizenTokenVerifier(BaseSewaSetuTokenVerifier):
    def __init__(self, expected_audience: Optional[str] = None):
        super().__init__(
            expected_role="citizen",
            expected_scope="citizen",
            expected_audience=expected_audience
        )


class OfficerTokenVerifier(BaseSewaSetuTokenVerifier):
    def __init__(self, expected_audience: Optional[str] = None):
        super().__init__(
            expected_role="officer",
            expected_scope="officer",
            expected_audience=expected_audience
        )


def get_current_user_claims() -> Optional[Dict[str, Any]]:
    """Retrieve claims of the currently authenticated request."""
    token = get_access_token()
    if token and token.claims:
        return token.claims
    return None


def get_current_citizen_mobile() -> Optional[str]:
    """Retrieve verified mobile number of authenticated citizen."""
    claims = get_current_user_claims()
    if claims and claims.get("role") == "citizen":
        sub = claims.get("sub", "")
        if sub.startswith("citizen:"):
            return sub.split(":", 1)[1]
    return None


def get_current_officer_username() -> Optional[str]:
    """Retrieve verified username of authenticated officer."""
    claims = get_current_user_claims()
    if claims and claims.get("role") == "officer":
        sub = claims.get("sub", "")
        if sub.startswith("officer:"):
            return sub.split(":", 1)[1]
    return None
