from httpx import AsyncClient

REGISTER_ENDPOINT = "/api/v1/users/register"
LOGIN_ENDPOINT = "/api/v1/auth/login"
REFRESH_ENDPOINT = "/api/v1/auth/refresh"
SESSIONS_ENDPOINT = "/api/v1/sessions"

VALID_USER = {
    "email": "sessionstest@example.com",
    "password": "MyP@ssw0rd!",
    "password_confirm": "MyP@ssw0rd!",
    "full_name": "Sessions Test User",
}

CHROME_WINDOWS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SAFARI_IOS_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 "
    "Safari/604.1"
)


async def _register_and_login(client: AsyncClient, user_agent: str) -> dict:
    await client.post(REGISTER_ENDPOINT, json=VALID_USER)
    resp = await client.post(
        LOGIN_ENDPOINT,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        headers={"User-Agent": user_agent},
    )
    return resp.json()


class TestListSessions:
    async def test_list_sessions_returns_active_session(self, client: AsyncClient):
        """A freshly logged-in user has exactly one active session listed."""
        tokens = await _register_and_login(client, CHROME_WINDOWS_UA)

        response = await client.get(
            SESSIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 1
        assert sessions[0]["is_current"] is True

    async def test_device_info_parsed_from_user_agent(self, client: AsyncClient):
        """Chrome/Windows UA is parsed into readable device fields."""

        tokens = await _register_and_login(client, CHROME_WINDOWS_UA)

        response = await client.get(
            SESSIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        session = response.json()[0]

        assert session["browser"] == "Chrome"
        assert session["os"] == "Windows 10/11"
        assert session["device_type"] == "desktop"
        assert session["device_name"] == "Chrome on Windows 10/11"

    async def test_mobile_device_detected(self, client: AsyncClient):
        """Mobile Safari UA is classified as device_type 'mobile'."""
        tokens = await _register_and_login(client, SAFARI_IOS_UA)

        response = await client.get(
            SESSIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        session = response.json()[0]

        assert session["device_type"] == "mobile"
        assert session["os"] == "iOS"

    async def test_multiple_sessions_only_one_flagged_current(
        self, client: AsyncClient
    ):
        """Logging in twice creates two sessions; only the caller's own is current."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        session_a = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
                headers={"User-Agent": CHROME_WINDOWS_UA},
            )
        ).json()
        await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
            headers={"User-Agent": SAFARI_IOS_UA},
        )

        response = await client.get(
            SESSIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {session_a['access_token']}"},
        )
        sessions = response.json()

        assert len(sessions) == 2
        current_flags = [s["is_current"] for s in sessions]
        assert current_flags.count(True) == 1

    async def test_list_sessions_requires_auth(self, client: AsyncClient):
        response = await client.get(SESSIONS_ENDPOINT)
        assert response.status_code == 401


class TestRevokeSession:
    async def test_revoke_session_succeds(self, client: AsyncClient):
        tokens = await _register_and_login(client, CHROME_WINDOWS_UA)
        sessions = (
            await client.get(
                SESSIONS_ENDPOINT,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
        ).json()
        session_id = sessions[0]["id"]

        response = await client.delete(
            f"{SESSIONS_ENDPOINT}/{session_id}",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Session revoked successfully"

    async def test_revoked_session_disappears_from_list(self, client: AsyncClient):
        """A device (session B) gets revoked from device A; it must vanish
        from A's session list."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        session_a = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
                headers={"User-Agent": CHROME_WINDOWS_UA},
            )
        ).json()
        await client.post(
            LOGIN_ENDPOINT,
            json={
                "email": VALID_USER["email"],
                "password": VALID_USER["password"],
            },
            headers={"User-Agent": SAFARI_IOS_UA},
        )

        listing = (
            await client.get(
                SESSIONS_ENDPOINT,
                headers={"Authorization": f"Bearer {session_a['access_token']}"},
            )
        ).json()
        session_b_id = next(s["id"] for s in listing if s["is_current"] is False)

        await client.delete(
            f"{SESSIONS_ENDPOINT}/{session_b_id}",
            headers={"Authorization": f"Bearer {session_a['access_token']}"},
        )

        remaining = (
            await client.get(
                SESSIONS_ENDPOINT,
                headers={"Authorization": f"Bearer {session_a['access_token']}"},
            )
        ).json()
        assert len(remaining) == 1
        assert remaining[0]["is_current"] is True

    async def test_revoked_session_refresh_token_rejected(self, client: AsyncClient):
        """Revoking a session must kill its refresh token."""
        tokens = await _register_and_login(client, CHROME_WINDOWS_UA)
        sessions = (
            await client.get(
                SESSIONS_ENDPOINT,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
        ).json()
        session_id = sessions[0]["id"]

        await client.delete(
            f"{SESSIONS_ENDPOINT}/{session_id}",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        response = await client.post(
            REFRESH_ENDPOINT, json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 401

    async def test_cannot_revoke_another_users_session(self, client: AsyncClient):
        """Revoking a session that belongs to a different user returns 404,
        not 403 — avoids leaking whether the session ID exists at all."""
        # User A
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)
        tokens_a = (
            await client.post(
                LOGIN_ENDPOINT,
                json={
                    "email": VALID_USER["email"],
                    "password": VALID_USER["password"],
                },
            )
        ).json()
        session_a_id = (
            await client.get(
                SESSIONS_ENDPOINT,
                headers={"Authorization": f"Bearer {tokens_a['access_token']}"},
            )
        ).json()[0]["id"]

        # User B
        other_user = {
            "email": "other-sessions-user@example.com",
            "password": "MyP@ssw0rd!",
            "password_confirm": "MyP@ssw0rd!",
            "full_name": "Other User",
        }
        await client.post(REGISTER_ENDPOINT, json=other_user)
        tokens_b = (
            await client.post(
                LOGIN_ENDPOINT,
                json={"email": other_user["email"], "password": other_user["password"]},
            )
        ).json()

        response = await client.delete(
            f"{SESSIONS_ENDPOINT}/{session_a_id}",
            headers={"Authorization": f"Bearer {tokens_b['access_token']}"},
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "session_not_found"

    async def test_revoke_nonexistent_session_returns_404(self, client: AsyncClient):
        tokens = await _register_and_login(client, CHROME_WINDOWS_UA)
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.delete(
            f"{SESSIONS_ENDPOINT}/{fake_id}",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 404

    async def test_revoke_session_requires_auth(self, client: AsyncClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"{SESSIONS_ENDPOINT}/{fake_id}")
        assert response.status_code == 401
