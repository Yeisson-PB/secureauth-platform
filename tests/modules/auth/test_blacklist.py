from httpx import AsyncClient

REGISTER_ENDPOINT = "/api/v1/users/register"
LOGIN_ENDPOINT = "/api/v1/auth/login"
LOGOUT_ENDPOINT = "/api/v1/auth/logout"
LOGOUT_ALL_ENDPOINT = "/api/v1/auth/logout-all"
ME_ENDPOINT = "/api/v1/auth/me"
REFRESH_ENDPOINT = "/api/v1/auth/refresh"

VALID_USER = {
    "email": "blacklisttest@example.com",
    "password": "MyP@ssw0rd!",
    "password_confirm": "MyP@ssw0rd!",
    "full_name": "Blacklist Test User",
}


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(REGISTER_ENDPOINT, json=VALID_USER)
    resp = await client.post(
        LOGIN_ENDPOINT,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    return resp.json()


class TestLogoutBlacklist:
    async def test_logout_succeeds_without_error(self, client: AsyncClient):
        """
        Regression test: logout must not raise (previously threw
        AttributeError because AuthService.logout() called a
        non-existent `_blacklist_access_token` method).
        """
        tokens = await _register_and_login(client)

        response = await client.post(
            LOGOUT_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"

    async def test_access_token_rejected_after_logout(self, client: AsyncClient):
        """The access token must be unusable immediately after logout."""
        tokens = await _register_and_login(client)

        await client.post(
            LOGOUT_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"refresh_token": tokens["refresh_token"]},
        )

        response = await client.get(
            ME_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 401
        assert response.json()["error_code"] == "token_revoked"

    async def test_refresh_token_rejected_after_logout(self, client: AsyncClient):
        """The refresh token must be unusable after logout (revoked in DB)."""
        tokens = await _register_and_login(client)

        await client.post(
            LOGOUT_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"refresh_token": tokens["refresh_token"]},
        )

        response = await client.post(
            REFRESH_ENDPOINT, json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_refresh_token"

    async def test_logout_without_token_returns_401(self, client: AsyncClient):
        """Logout requires authentication."""
        response = await client.post(LOGOUT_ENDPOINT, json={"refresh_token": "x"})
        assert response.status_code == 401

    async def test_other_sessions_survive_single_logout(self, client: AsyncClient):
        """
        Logging out one session must not blacklist a different session's
        access token.
        """
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        session_a = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
            )
        ).json()
        session_b = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
            )
        ).json()

        await client.post(
            LOGOUT_ENDPOINT,
            headers={"Authorization": f"Bearer {session_a['access_token']}"},
            json={"refresh_token": session_a["refresh_token"]},
        )

        # Session A is dead
        resp_a = await client.get(
            ME_ENDPOINT,
            headers={"Authorization": f"Bearer {session_a['access_token']}"},
        )
        assert resp_a.status_code == 401

        # Session B is still alive
        resp_b = await client.get(
            ME_ENDPOINT,
            headers={"Authorization": f"Bearer {session_b['access_token']}"},
        )
        assert resp_b.status_code == 200


class TestLogoutAll:
    async def test_logout_all_revokes_every_session(self, client: AsyncClient):
        """logout-all must revoke every refresh token/session for the user."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        session_a = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
            )
        ).json()
        session_b = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
            )
        ).json()

        await client.post(
            LOGOUT_ALL_ENDPOINT,
            headers={"Authorization": f"Bearer {session_a['access_token']}"},
        )

        # Neither refresh token should work anymore
        for tokens in (session_a, session_b):
            response = await client.post(
                REFRESH_ENDPOINT, json={"refresh_token": tokens["refresh_token"]}
            )
            assert response.status_code == 401
