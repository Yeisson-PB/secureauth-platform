from httpx import AsyncClient


class TestUserRegister:
    """Tests for POST /api/v1/users/register"""

    ENDPOINT = "/api/v1/users/register"

    VALID_PAYLOAD = {
        "email": "testuser@example.com",
        "password": "MyP@ssw0rd!",
        "password_confirm": "MyP@ssw0rd!",
        "full_name": "Test User",
    }

    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration"""
        response = await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        assert response.status_code == 201
        data = response.json()

        assert data["email"] == "testuser@example.com"
        assert data["full_name"] == "Test User"
        assert data["is_active"] is True
        assert data["is_verified"] is False
        assert data["mfa_enabled"] is False
        assert "id" in data
        assert "created_at" in data

    async def test_register_no_sensitive_fields_in_response(self, client: AsyncClient):
        """Test that sensitive fields are not included in the response"""
        response = await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)
        data = response.json()

        forbidden_fields = [
            "hashed_password",
            "password",
            "mfa_secret",
            "failed_login_attempts",
            "locked_until",
        ]

        for field in forbidden_fields:
            assert (
                field not in data
            ), f"Sensitive field '{field}' should not be in the response"

    async def test_register_email_normalized_to_lowercase(self, client: AsyncClient):
        """Test that email is normalized to lowercase during registration"""
        payload = {**self.VALID_PAYLOAD, "email": "UPPER@EXAMPLE.COM"}
        response = await client.post(self.ENDPOINT, json=payload)

        assert response.status_code == 201
        assert response.json()["email"] == "upper@example.com"

    async def test_register_duplicate_email_returns_409(self, client: AsyncClient):
        """Test that registering with an email that already exists returns 409 Conflict"""
        # First registration should succeed
        await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        # Second registration with the same email should fail
        response = await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "email_already_registered"

    async def test_register_duplicate_email_case_insensitive(self, client: AsyncClient):
        """Emails are deduplicated case-insensitively."""
        await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        payload = {**self.VALID_PAYLOAD, "email": "TESTUSER@EXAMPLE.COM"}
        response = await client.post(self.ENDPOINT, json=payload)

        assert response.status_code == 409

    async def test_register_weak_password_no_uppercase(self, client: AsyncClient):
        """Test that a password without uppercase letters is rejected"""
        payload = {
            **self.VALID_PAYLOAD,
            "password": "myp@ssw0rd!",
            "password_confirm": "myp@ssw0rd!",
        }
        response = await client.post(self.ENDPOINT, json=payload)
        assert response.status_code == 422

    async def test_register_weak_password_no_special_char(self, client: AsyncClient):
        """Test that a password without special characters is rejected"""
        payload = {
            **self.VALID_PAYLOAD,
            "password": "MyPassw0rd",
            "password_confirm": "MyPassw0rd",
        }
        response = await client.post(self.ENDPOINT, json=payload)
        assert response.status_code == 422

    async def test_register_passwords_too_short(self, client: AsyncClient):
        """Test that a password that is too short is rejected"""
        payload = {
            **self.VALID_PAYLOAD,
            "password": "M@1a",
            "password_confirm": "M@1a",
        }
        response = await client.post(self.ENDPOINT, json=payload)
        assert response.status_code == 422

    async def test_register_passwords_dont_match(self, client: AsyncClient):
        # Test that non-matching passwords are rejected
        payload = {
            **self.VALID_PAYLOAD,
            "password": "MyP@ssw0rd!",
            "password_confirm": "DifferentP@ssw0rd!",
        }
        response = await client.post(self.ENDPOINT, json=payload)
        assert response.status_code == 422

    async def test_register_invalid_email_format(self, client: AsyncClient):
        """Test that an invalid email format is rejected"""
        payload = {**self.VALID_PAYLOAD, "email": "invalid-email-format"}
        response = await client.post(self.ENDPOINT, json=payload)
        assert response.status_code == 422

    async def test_register_without_full_name(self, client: AsyncClient):
        """full_name is optional — registration succeeds without it"""
        payload = {
            "email": "nofullname@example.com",
            "password": "MyP@ssw0rd!",
            "password_confirm": "MyP@ssw0rd!",
        }
        response = await client.post(self.ENDPOINT, json=payload)
        assert response.status_code == 201
        assert response.json()["full_name"] is None

    async def test_register_error_follows_rfc7807(self, client: AsyncClient):
        """Test that error responses follow RFC 7807 format"""
        await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)
        response = await client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        data = response.json()
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "error_code" in data
        assert data["status"] == 409
