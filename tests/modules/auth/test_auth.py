"""
Tests for authentication endpoints.

Covers:
- Login success and failure
- JWT token structure
- Refresh token rotation
- Logout and blacklisting
- Protected endpoint access
"""

from httpx import AsyncClient

REGISTER_ENDPOINT = "/api/v1/users/register"
LOGIN_ENDPOINT = "/api/v1/auth/login"
REFRESH_ENDPOINT = "/api/v1/auth/refresh"
LOGOUT_ENDPOINT = "/api/v1/auth/logout"
ME_ENDPOINT = "/api/v1/auth/me"

VALID_USER = {
    "email": "authtest@example.com",
    "password": "MyP@ssw0rd!",
    "password_confirm": "MyP@ssw0rd!",
    "full_name": "Auth Test User",
}


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        """Successful login returns access and refresh tokens."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        response = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_login_wrong_password(self, client: AsyncClient):
        """Wrong password returns 401 with generic error."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        response = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": "WrongP@ssw0rd!"},
        )

        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_credentials"

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Nonexistent user returns 401 with generic error."""
        response = await client.post(
            LOGIN_ENDPOINT,
            json={"email": "nobody@example.com", "password": "My@ssw0rd!"},
        )

        assert response.status_code == 401
        # CRITICAL: same error code as wrong password
        assert response.json()["error_code"] == "invalid_credentials"

    async def test_login_returns_valid_jwt(self, client: AsyncClient):
        """Access token is a valid JWT with correct claims."""
        import jwt

        from app.core.config import settings

        await client.post(REGISTER_ENDPOINT, json=VALID_USER)
        response = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )

        token = response.json()["access_token"]
        payload = jwt.decode(
            token, settings.JWT_PUBLIC_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        assert payload["type"] == "access"
        assert "sub" in payload
        assert "jti" in payload
        assert "exp" in payload


class TestProtectedEndpoint:
    async def test_access_protected_endpoint_with_valid_token(
        self, client: AsyncClient
    ):
        """Valid token grants access to protected endpoint."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)
        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        token = login_resp.json()["access_token"]

        response = await client.get(
            ME_ENDPOINT, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == VALID_USER["email"]

    async def test_access_protected_endpoint_without_token(self, client: AsyncClient):
        """Missing token returns 401."""
        response = await client.get(ME_ENDPOINT)
        assert response.status_code == 401
        assert response.json()["error_code"] == "missing_token"

    async def test_access_protected_endpoint_with_invalid_token(
        self, client: AsyncClient
    ):
        """Invalid JWT returns 401."""
        response = await client.get(
            ME_ENDPOINT, headers={"Authorization": "Bearer this.is.not.a.valid.jwt"}
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_token"


class TestRefreshToken:
    async def test_refresh_returns_new_token_pair(self, client: AsyncClient):
        """Refresh token returns a new token pair."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)
        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        refresh_token = login_resp.json()["refresh_token"]
        old_access = login_resp.json()["access_token"]

        response = await client.post(
            REFRESH_ENDPOINT, json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New access token must be different from the old one
        assert data["access_token"] != old_access
        # New refresh token must be different (rotation)
        assert data["refresh_token"] != refresh_token

    async def test_refresh_token_cannot_be_reused(self, client: AsyncClient):
        """Used refresh token is rejected (rotation enforcement)."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)
        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Use it once (valid)
        await client.post(REFRESH_ENDPOINT, json={"refresh_token": refresh_token})

        # Try to use it again (should fail)
        response = await client.post(
            REFRESH_ENDPOINT, json={"refresh_token": refresh_token}
        )

        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_refresh_token"

    async def test_invalid_refresh_token_rejected(self, client: AsyncClient):
        """Completely fake refresh token is rejected."""
        response = await client.post(
            REFRESH_ENDPOINT,
            json={"refresh_token": "fake-refresh-token-that-does-not-exist"},
        )
        assert response.status_code == 401
