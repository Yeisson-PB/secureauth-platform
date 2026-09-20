import uuid

import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.redis_client import blacklist_token, is_token_blacklisted
from app.core.security import (
    generate_recovery_codes,
    generate_totp_secret,
    hash_token,
    normalize_recovery_code,
    verify_password,
)
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    MFADisableRequest,
    MFAEnableConfirmRequest,
    MFAEnableConfirmResponse,
    MFAEnableResponse,
    MFAVerifyRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository


class MFAService:
    """Service for enabling, confirming, verifying, and disabling TOTP MFA."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.auth_repo = AuthRepository(db)
        self.auth_service = AuthService(db)

    # --- Enable, step 1: generate a pending secret ------------------------------

    async def enable(self, user: User) -> MFAEnableResponse:
        """
        Generate a fresh TOTP secret for the user and store it, but do
        NOT flip mfa_enabled yet — that only happens once the user
        proves they can generate a valid code with it, in confirm().

        Calling this again before confirm() simply overwrites the
        pending secret with a new one (e.g. if a QR scan failed and the
        user wants to restart enrollment). It has no effect at all on an
        account that already has MFA enabled — that must go through
        disable() first.
        """
        if user.mfa_enabled:
            raise AppError(
                status_code=409,
                error_code="mfa_already_enabled",
                title="MFA Already Enabled",
                detail="Multi-factor authentication is already enabled for this account.",
            )

        secret = generate_totp_secret()
        await self.user_repo.set_mfa_secret(user.id, secret)

        otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=settings.MFA_ISSUER_NAME,
        )

        await self._write_audit_log(
            user_id=user.id,
            action="mfa.enable_initiated",
            description="MFA enrollment started; awaiting confirmation code",
        )

        return MFAEnableResponse(
            secret=secret,
            otpauth_uri=otpauth_uri,
            issuer=settings.MFA_ISSUER_NAME,
        )

    # --- Enable, step 2: confirm with a valid code ------------------------------

    async def confirm(
        self, user: User, data: MFAEnableConfirmRequest
    ) -> MFAEnableConfirmResponse:
        """
        Verify the user can produce a valid TOTP code from the secret
        generated in enable(), then flip mfa_enabled on and hand back a
        one-time batch of recovery codes.

        The raw recovery codes are returned here, and only here — only
        their SHA-256 hashes are ever persisted (the same approach
        already used for refresh tokens), so if the database is ever
        compromised the codes themselves cannot be recovered from it.
        """
        if user.mfa_enabled:
            raise AppError(
                status_code=409,
                error_code="mfa_already_enabled",
                title="MFA Already Enabled",
                detail="Multi-factor authentication is already enabled for this account.",
            )

        if not user.mfa_secret:
            raise AppError(
                status_code=400,
                error_code="mfa_not_initiated",
                title="MFA Not Initiated",
                detail="Call POST /auth/mfa/enable first to generate a secret.",
            )

        if not pyotp.TOTP(user.mfa_secret).verify(data.totp_code, valid_window=1):
            raise AppError(
                status_code=401,
                error_code="invalid_totp_code",
                title="Invalid Code",
                detail="The provided authenticator code is invalid or expired.",
            )

        await self.user_repo.enable_mfa(user.id)

        raw_codes = generate_recovery_codes(settings.MFA_RECOVERY_CODES_COUNT)
        hashed_codes = [hash_token(normalize_recovery_code(code)) for code in raw_codes]
        await self.auth_repo.create_recovery_codes(user.id, hashed_codes)

        await self._write_audit_log(
            user_id=user.id,
            action="mfa.enabled",
            description="MFA enabled and recovery codes issued",
        )

        return MFAEnableConfirmResponse(
            message=(
                "MFA has been enabled. Store these recovery codes somewhere "
                "safe — they will not be shown again."
            ),
            recovery_codes=raw_codes,
        )

    # --- Verify: second step of login ------------------------------

    async def verify(
        self,
        data: MFAVerifyRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Complete the login flow started by AuthService.login() when
        mfa_enabled is True: exchange a valid mfa_token + TOTP (or
        recovery) code for a real access/refresh token pair.

        The mfa_token is single-use: on success it is blacklisted
        immediately via the same Redis blacklist used for logout
        (Task 9), so it cannot be replayed even though it has not yet
        naturally expired. It is intentionally NOT blacklisted on a
        failed code attempt, so a user who mistypes their code can
        simply retry within the token's short lifetime.
        """
        payload = AuthService.decode_mfa_token(data.mfa_token)
        jti = payload.get("jti")
        user_id = payload.get("sub")

        if not jti or not user_id:
            raise AppError(
                status_code=401,
                error_code="invalid_mfa_token",
                title="Invalid MFA Token",
                detail="The MFA token payload is malformed.",
            )

        if await is_token_blacklisted(jti):
            raise AppError(
                status_code=401,
                error_code="mfa_token_used",
                title="MFA Token Already Used",
                detail="This MFA token has already been used. Please log in again.",
            )

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or not user.is_active or not user.mfa_enabled:
            raise AppError(
                status_code=401,
                error_code="invalid_mfa_token",
                title="Invalid MFA Token",
                detail="This MFA token is no longer valid.",
            )

        if data.totp_code:
            valid = bool(
                user.mfa_secret
                and pyotp.TOTP(user.mfa_secret).verify(data.totp_code, valid_window=1)
            )
            if not valid:
                raise AppError(
                    status_code=401,
                    error_code="invalid_totp_code",
                    title="Invalid Code",
                    detail="The provided authenticator code is invalid or expired.",
                )
        else:
            consumed = await self._consume_recovery_code(user.id, data.recovery_code)
            if not consumed:
                raise AppError(
                    status_code=401,
                    error_code="invalid_recovery_code",
                    title="Invalid Recovery Code",
                    detail=(
                        "The provided recovery code is invalid or has "
                        "already been used."
                    ),
                )

        # Single-use enforcement: blacklist for the token's own remaining
        # lifetime. It's short-lived by design, so this is cheap on Redis.
        await blacklist_token(jti, ttl_seconds=settings.MFA_TOKEN_EXPIRE_MINUTES * 60)

        await self._write_audit_log(
            user_id=user.id,
            action="user.mfa_verify",
            description="MFA code verified; completing login",
        )

        return await self.auth_service._issue_token_pair(
            user=user, ip_address=ip_address, user_agent=user_agent
        )

    async def _consume_recovery_code(
        self, user_id: uuid.UUID, raw_code: str | None
    ) -> bool:
        """
        Hash the provided recovery code and, if it matches an unused
        stored code for this user, mark it used.

        Returns whether a match was found. Loops over the (small, at
        most MFA_RECOVERY_CODES_COUNT) set of active codes and compares
        hashes directly — the codes are high-entropy random values, so
        this is not the kind of low-entropy secret comparison that would
        need a constant-time check to resist timing attacks.
        """
        if not raw_code:
            return False
        code_hash = hash_token(normalize_recovery_code(raw_code))
        active_codes = await self.auth_repo.get_active_recovery_codes(user_id)
        for code in active_codes:
            if code.code_hash == code_hash:
                await self.auth_repo.mark_recovery_code_used(code.id)
                return True
        return False

    # --- Disable ------------------------------

    async def disable(self, user: User, data: MFADisableRequest) -> None:
        """
        Disable MFA. Requires BOTH the current password and a valid TOTP
        code — not just an authenticated session — so that a hijacked
        access token alone can never be used to turn off the second
        factor protecting the account. Also invalidates every
        outstanding recovery code, since re-enrolling later issues a
        brand-new batch.
        """
        if not user.mfa_enabled:
            raise AppError(
                status_code=400,
                error_code="mfa_not_enabled",
                title="MFA Not Enabled",
                detail="Multi-factor authentication is not enabled for this account.",
            )

        if not user.hashed_password or not verify_password(
            data.password, user.hashed_password
        ):
            raise AppError(
                status_code=401,
                error_code="invalid_current_password",
                title="Invalid Password",
                detail="The provided password is incorrect.",
            )

        if not user.mfa_secret or not pyotp.TOTP(user.mfa_secret).verify(
            data.totp_code, valid_window=1
        ):
            raise AppError(
                status_code=401,
                error_code="invalid_totp_code",
                title="Invalid Code",
                detail="The provided authenticator code is invalid or expired.",
            )

        await self.user_repo.disable_mfa(user.id)
        await self.auth_repo.invalidate_recovery_codes(user.id)

        await self._write_audit_log(
            user_id=user.id,
            action="mfa.disabled",
            description="MFA disabled by user",
        )

    # --- Internal helpers ------------------------------

    async def _write_audit_log(
        self, user_id: uuid.UUID, action: str, description: str
    ) -> None:
        from app.modules.audit.model import AuditLog

        log = AuditLog(
            user_id=user_id,
            action=action,
            description=description,
            status="success",
        )
        self.db.add(log)
        await self.db.commit()
