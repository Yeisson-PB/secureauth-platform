from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.modules.users.model import User
from tests.conftest import TestSessionLocal

REGISTER_ENDPOINT = "/api/v1/users/register"
LOGIN_ENDPOINT = "/api/v1/auth/login"

VALID_USER = {
    "email": "bruteforce@example.com",
    "password": "MyP@ssw0rd!",
    "password_confirm": "MyP@ssw0rd!",
    "full_name": "Brute Force Test User",
}

WRONG_PASSWORD = "WrongP@ssw0rd!"


async def _login(client: AsyncClient, password: str):
    return await client.post(
        LOGIN_ENDPOINT,
        json={"email": VALID_USER["email"], "password": password},
    )


async def _set_locked_until(email: str, when: datetime):
    """
    Directly manipulate locked_until in the test DB to simulate the
    lockout window having already elapsed, without needing to sleep
    for real in the test suite.
    """
    async with TestSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.locked_until = when
        await session.commit()


class TestBruteForceLockout:
    async def test_account_locks_after_max_failed_attempts(self, client: AsyncClient):
        """The account must lock exactly on the MAX_LOGIN_ATTEMPTS-th failure."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        for _ in range(settings.MAX_LOGIN_ATTEMPTS - 1):
            response = await _login(client, WRONG_PASSWORD)
            assert response.status_code == 401
            assert response.json()["error_code"] == "invalid_credentials"

        response = await _login(client, WRONG_PASSWORD)
        assert response.status_code == 403
        assert response.json()["error_code"] == "account_locked"

    async def test_locked_account_rejects_correct_password(self, client: AsyncClient):
        """Once locked, even the correct password must be rejected until
        the lockout window elapses."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        for _ in range(settings.MAX_LOGIN_ATTEMPTS):
            await _login(client, WRONG_PASSWORD)

        response = await _login(client, VALID_USER["password"])
        assert response.status_code == 403
        assert response.json()["error_code"] == "account_locked"

    async def test_successful_login_resets_failed_attempts(self, client: AsyncClient):
        """A successful login must reset the counter so old failures don't
        carry over toward a future lockout."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        for _ in range(settings.MAX_LOGIN_ATTEMPTS - 2):
            await _login(client, WRONG_PASSWORD)

        success = await _login(client, VALID_USER["password"])
        assert success.status_code == 200

        # A fresh run of failures (one short of the limit) must NOT lock
        # the account, proving the counter was reset on success.
        for _ in range(settings.MAX_LOGIN_ATTEMPTS - 1):
            response = await _login(client, WRONG_PASSWORD)
            assert response.status_code == 401

    async def test_lockout_resets_after_window_expires(self, client: AsyncClient):
        """Once the lockout window has genuinely elapsed, the next attempt
        must start a fresh count instead of instantly re-locking."""
        await client.post(REGISTER_ENDPOINT, json=VALID_USER)

        for _ in range(settings.MAX_LOGIN_ATTEMPTS):
            await _login(client, WRONG_PASSWORD)

        # Simulate the lockout window having already passed.
        await _set_locked_until(
            VALID_USER["email"],
            datetime.now(UTC) - timedelta(seconds=1),
        )

        response = await _login(client, WRONG_PASSWORD)
        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_credentials"

        # A second consecutive failure must not immediately re-lock —
        # confirms the counter genuinely restarted at 1, not resumed
        # from the stale pre-expiry count.
        response = await _login(client, WRONG_PASSWORD)
        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_credentials"

    async def test_nonexistent_user_never_locks(self, client: AsyncClient):
        """Login attempts against an email with no account must always
        return invalid_credentials — there's no user row to lock, and
        this response must never be distinguishable from a real
        temporarily-locked account."""
        for _ in range(settings.MAX_LOGIN_ATTEMPTS + 2):
            response = await client.post(
                LOGIN_ENDPOINT,
                json={"email": "nobody-bf@example.com", "password": "whatever123!"},
            )
            assert response.status_code == 401
            assert response.json()["error_code"] == "invalid_credentials"
