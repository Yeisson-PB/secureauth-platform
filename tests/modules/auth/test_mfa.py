import pyotp
from httpx import AsyncClient

REGISTER_ENDPOINT = "/api/v1/users/register"
LOGIN_ENDPOINT = "/api/v1/auth/login"
MFA_ENABLE_ENDPOINT = "/api/v1/auth/mfa/enable"
MFA_CONFIRM_ENDPOINT = "/api/v1/auth/mfa/enable/confirm"
MFA_VERIFY_ENDPOINT = "/api/v1/auth/mfa/verify"
MFA_DISABLE_ENDPOINT = "/api/v1/auth/mfa/disable"

VALID_USER = {
    "email": "mfatest@example.com",
    "password": "MyP@ssw0rd!",
    "password_confirm": "MyP@ssw0rd!",
    "full_name": "MFA Test User",
}


async def _register_and_login(client: AsyncClient):
    await client.post(REGISTER_ENDPOINT, json=VALID_USER)
    resp = await client.post(
        LOGIN_ENDPOINT,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    return resp.json()


async def _enable_mfa(client: AsyncClient, access_token: str) -> tuple[str, list[str]]:
    """Run enable + confirm, returning (totp_secret, recovery_codes)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    enable_resp = await client.post(MFA_ENABLE_ENDPOINT, headers=headers)
    secret = enable_resp.json()["secret"]

    code = pyotp.TOTP(secret).now()
    confirm_resp = await client.post(
        MFA_CONFIRM_ENDPOINT, headers=headers, json={"totp_code": code}
    )
    return secret, confirm_resp.json()["recovery_codes"]


class TestMFAEnrollment:
    async def test_enable_requires_auth(self, client: AsyncClient):
        """MFA enrollment requires an authenticated session."""
        response = await client.post(MFA_ENABLE_ENDPOINT)
        assert response.status_code == 401

    async def test_enable_returns_secret_and_otauth_uri(self, client: AsyncClient):
        """Enable returns a base32 secret and a scannable otpauth:// URI."""
        tokens = await _register_and_login(client)
        response = await client.post(
            MFA_ENABLE_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert data["otpauth_uri"].startswith("otpauth://totp/")
        assert data["issuer"] == "SecureAuth"

    async def test_enable_does_not_activate_mfa_yet(self, client: AsyncClient):
        """After enable() but before confirm(), login must still work without MFA."""
        tokens = await _register_and_login(client)
        await client.post(
            MFA_ENABLE_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert "access_token" in login_resp.json()

    async def test_confirm_with_wrong_code_fails(self, client: AsyncClient):
        """A wrong TOTP code at confirmation time is rejected."""
        tokens = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        await client.post(MFA_ENABLE_ENDPOINT, headers=headers)

        response = await client.post(
            MFA_CONFIRM_ENDPOINT, headers=headers, json={"totp_code": "000000"}
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_totp_code"

    async def test_confirm_without_enable_fails(self, client: AsyncClient):
        """Confirming before calling enable() must fail — there's no secret yet."""
        tokens = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.post(
            MFA_CONFIRM_ENDPOINT, headers=headers, json={"totp_code": "123456"}
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "mfa_not_initiated"

    async def test_confirm_with_correct_code_returns_recovery_codes(
        self, client: AsyncClient
    ):
        """A correct confirmation code activates MFA and issues recovery codes."""
        tokens = await _register_and_login(client)
        _, recovery_codes = await _enable_mfa(client, tokens["access_token"])

        assert len(recovery_codes) == 10
        assert all("-" in code for code in recovery_codes)

    async def test_enable_after_confirmed_returns_409(self, client: AsyncClient):
        """Enrolling again once MFA is already active is rejected."""
        tokens = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        await _enable_mfa(client, tokens["access_token"])

        response = await client.post(MFA_ENABLE_ENDPOINT, headers=headers)
        assert response.status_code == 409
        assert response.json()["error_code"] == "mfa_already_enabled"


class TestMFALogin:
    async def test_login_with_mfa_enabled_returns_pending_token(
        self, client: AsyncClient
    ):
        """A password-correct login on an MFA account returns mfa_token, not tokens."""
        tokens = await _register_and_login(client)
        await _enable_mfa(client, tokens["access_token"])

        response = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mfa_required"] is True
        assert "mfa_token" in data
        assert "access_token" not in data

    async def test_verify_with_correct_totp_code_returns_token_pair(
        self, client: AsyncClient
    ):
        """Submitting a valid TOTP code to /mfa/verify completes the login."""
        tokens = await _register_and_login(client)
        secret, _ = await _enable_mfa(client, tokens["access_token"])

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]

        code = pyotp.TOTP(secret).now()
        response = await client.post(
            MFA_VERIFY_ENDPOINT, json={"mfa_token": mfa_token, "totp_code": code}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_verify_with_wrong_totp_code_fails(self, client: AsyncClient):
        """A wrong TOTP code at the verify step is rejected without consuming the token."""
        tokens = await _register_and_login(client)
        await _enable_mfa(client, tokens["access_token"])

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]

        response = await client.post(
            MFA_VERIFY_ENDPOINT, json={"mfa_token": mfa_token, "totp_code": "000000"}
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "invalid_totp_code"

    async def test_verify_rejects_missing_or_both_codes(self, client: AsyncClient):
        """Exactly one of totp_code/recovery_code must be provided."""
        tokens = await _register_and_login(client)
        await _enable_mfa(client, tokens["access_token"])

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]

        response = await client.post(MFA_VERIFY_ENDPOINT, json={"mfa_token": mfa_token})
        assert response.status_code == 422

    async def test_mfa_token_is_single_use(self, client: AsyncClient):
        """Reusing an already-verified mfa_token must fail, even with a valid code."""
        tokens = await _register_and_login(client)
        secret, _ = await _enable_mfa(client, tokens["access_token"])

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]
        code = pyotp.TOTP(secret).now()

        first = await client.post(
            MFA_VERIFY_ENDPOINT, json={"mfa_token": mfa_token, "totp_code": code}
        )
        assert first.status_code == 200

        second = await client.post(
            MFA_VERIFY_ENDPOINT, json={"mfa_token": mfa_token, "totp_code": code}
        )
        assert second.status_code == 401
        assert second.json()["error_code"] == "mfa_token_used"

    async def test_mfa_token_cannot_be_used_as_access_token(self, client: AsyncClient):
        """An mfa_token must be rejected by protected endpoints expecting an access token."""
        tokens = await _register_and_login(client)
        await _enable_mfa(client, tokens["access_token"])

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {mfa_token}"}
        )
        assert response.status_code == 401

    async def test_verify_with_recovery_code_works_and_consumes_it(
        self, client: AsyncClient
    ):
        """A recovery code can substitute for a TOTP code, and is single-use."""
        tokens = await _register_and_login(client)
        _, recovery_codes = await _enable_mfa(client, tokens["access_token"])
        recovery_code = recovery_codes[0]

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]

        response = await client.post(
            MFA_VERIFY_ENDPOINT,
            json={"mfa_token": mfa_token, "recovery_code": recovery_code},
        )
        assert response.status_code == 200

        # A fresh mfa_token + the SAME recovery code must now fail.
        login_resp_2 = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token_2 = login_resp_2.json()["mfa_token"]
        reuse_response = await client.post(
            MFA_VERIFY_ENDPOINT,
            json={"mfa_token": mfa_token_2, "recovery_code": recovery_code},
        )
        assert reuse_response.status_code == 401
        assert reuse_response.json()["error_code"] == "invalid_recovery_code"

    async def test_verify_with_lowercase_recovery_code_still_works(
        self, client: AsyncClient
    ):
        """Recovery code matching is case-insensitive and hyphen-tolerant."""
        tokens = await _register_and_login(client)
        _, recovery_codes = await _enable_mfa(client, tokens["access_token"])
        recovery_code = recovery_codes[0].lower().replace("-", "")

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        mfa_token = login_resp.json()["mfa_token"]

        response = await client.post(
            MFA_VERIFY_ENDPOINT,
            json={"mfa_token": mfa_token, "recovery_code": recovery_code},
        )
        assert response.status_code == 200


class TestMFADisable:
    async def test_diasble_requires_password_and_code(self, client: AsyncClient):
        """Both the password and TOTP code must be independently correct."""
        tokens = await _register_and_login(client)
        secret, _ = await _enable_mfa(client, tokens["access_token"])
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        wrong_password = await client.post(
            MFA_DISABLE_ENDPOINT,
            headers=headers,
            json={"password": "WrongPass1!", "totp_code": pyotp.TOTP(secret).now()},
        )
        assert wrong_password.status_code == 401
        assert wrong_password.json()["error_code"] == "invalid_current_password"

        wrong_code = await client.post(
            MFA_DISABLE_ENDPOINT,
            headers=headers,
            json={"password": VALID_USER["password"], "totp_code": "000000"},
        )
        assert wrong_code.status_code == 401
        assert wrong_code.json()["error_code"] == "invalid_totp_code"

    async def test_disable_with_correct_credentials_succeds(self, client: AsyncClient):
        """Correct password + TOTP code disables MFA and login returns to normal."""
        tokens = await _register_and_login(client)
        secret, _ = await _enable_mfa(client, tokens["access_token"])
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.post(
            MFA_DISABLE_ENDPOINT,
            headers=headers,
            json={
                "password": VALID_USER["password"],
                "totp_code": pyotp.TOTP(secret).now(),
            },
        )
        assert response.status_code == 200

        login_resp = await client.post(
            LOGIN_ENDPOINT,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert "access_token" in login_resp.json()

    async def test_disable_when_not_enabled_returns_400(self, client: AsyncClient):
        """Disabling MFA on an account that never enabled it is rejected."""
        tokens = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.post(
            MFA_DISABLE_ENDPOINT,
            headers=headers,
            json={"password": VALID_USER["password"], "totp_code": "123456"},
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "mfa_not_enabled"

    async def test_disable_requires_auth(self, client: AsyncClient):
        """MFA disable requires an authenticated session."""
        response = await client.post(
            MFA_DISABLE_ENDPOINT,
            json={"password": "whatever", "totp_code": "123456"},
        )
        assert response.status_code == 401
