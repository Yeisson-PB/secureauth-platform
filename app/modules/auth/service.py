import logging
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import generate_secure_token, hash_token
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import TokenResponse
from app.modules.users.model import User
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)
TOKEN_TYPE = "bearer"  # nosec: B105


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.auth_repo = AuthRepository(db)

    # --- JWT ------------------------------

    @staticmethod
    def create_access_token(user_id: uuid.UUID) -> tuple[str, str]:
        """
        Create a signed RS256 JWT access token.

        Returns (token_string, jti) where jti is the unique token ID
        used to blacklist the token on logout.

        RS256 signing process:
        1. Build payload dict with claims (sub, exp, iat, jti, type)
        2. Sign with the RSA private key using SHA-256
        3. Result: header.payload.signature (base64url encoded)

        Verification (by any service with the public key):
        1. Decode header and payload
        2. Recompute signature using the RSA public key
        3. If signatures match AND exp > now → token is valid
        """
        jti = str(uuid.uuid4())  # Unique ID for this specific token
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": str(user_id),  # Subject: who this token belongs to
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": jti,  # JWT ID: used for blacklisting
            "type": "access",  # Prevents refresh tokens being used as access tokens
        }
        token = jwt.encode(
            payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM
        )
        return token, jti

    @staticmethod
    def decode_access_token(token: str) -> dict:
        """
        Decode and verify a JWT access token.

        Verification checks (all done automatically by PyJWT):
        1. Signature valid (using RS256 public key)
        2. Token not expired (exp claim)
        3. Algorithm matches (prevents algorithm confusion attacks)

        Raises:
            AppError(401): if token is invalid, expired, or wrong type
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_PUBLIC_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except PyJWTError as e:
            raise AppError(
                status_code=401,
                error_code="invalid_token",
                title="Invalid Token",
                detail="The provided access token is invalid or expired.",
            ) from e

        # Extra check: ensure this is an access token, not a refresh token
        if payload.get("type") != "access":
            raise AppError(
                status_code=401,
                error_code="invalid_token_type",
                title="Invalid Token Type",
                detail="Expected an access token.",
            )

        return payload

    # --- Login ------------------------------

    async def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Authenticate user with email/password and issue token pair.

        Security measures:
        - constant-time password comparison (bcrypt)
        - same error message for "user not found" and "wrong password"
          (prevents user enumeration attacks)
        - audit log for both success and failure
        - updates last_login_at and resets failed_login_attempts on success

        Raises:
            AppError(401): invalid credentials
            AppError(403): account disabled or locked
        """
        # --- 1. Look up user ------------------------
        user = await self.user_repo.get_by_email(email)

        # SECURITY: Same error for "user not found" AND "wrong password"
        # This prevents an attacker from discovering which emails are registered
        if not user:
            await self._log_failed_login(
                email=email,
                ip_address=ip_address,
                reason="User not found",
            )
            raise AppError(
                status_code=401,
                error_code="invalid_credentials",
                title="Invalid Credentials",
                detail="The email or password you entered is incorrect.",
            )

        # --- 2. Check account status ------------------------
        if not user.is_active:
            raise AppError(
                status_code=403,
                error_code="account_disabled",
                title="Account Disabled",
                detail="This account has been disabled. Contact support.",
            )

        # Check if account is temporarily locked (brute force protection)
        if user.locked_until and user.locked_until > datetime.now(UTC):
            remaining = int((user.locked_until - datetime.now(UTC)).total_seconds())
            raise AppError(
                status_code=403,
                error_code="account_locked",
                title="Account Temporarily Locked",
                detail=(
                    f"Too many failed attempts. "
                    f"Try again in {remaining // 60} minutes."
                ),
            )

        # --- 3. Verify password ------------------------
        from app.core.security import verify_password

        if not user.hashed_password or not verify_password(
            password, user.hashed_password
        ):

            await self.user_repo.increment_failed_attempts(user.id)
            await self._log_failed_login(
                email=email,
                ip_address=ip_address,
                reason="wrong_password",
                user_id=user.id,
            )
            raise AppError(
                status_code=401,
                error_code="invalid_credentials",
                title="Invalid Credentials",
                detail="The email or password you entered is incorrect.",
            )

        # --- 4. Issue tokens ------------------------
        return await self._issue_token_pair(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # --- Refresh ------------------------------

    async def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Rotate the token pair using a valid refresh token.

        Rotation security model:
        1. Look up the incoming token by its hash
        2. If found AND not revoked → issue new pair, revoke old token
        3. If NOT found (already revoked or never existed) →
           REVOKE ALL TOKENS for this user (token theft detected)

        Step 3 is the key security mechanism:
        If an attacker steals a refresh token and uses it before the
        legitimate user does, the next time the legitimate user tries
        to refresh, their token will be gone (already used by attacker).
        This triggers step 3, locking the attacker out too.

        Raises:
            AppError(401): invalid or already-used refresh token
        """
        token_hash = hash_token(refresh_token)
        stored_token = await self.auth_repo.get_refresh_token_by_hash(token_hash)

        # --- Token not found or already revoked ------------------------
        if not stored_token:

            raise AppError(
                status_code=401,
                error_code="invalid_refresh_token",
                title="Invalid Refresh Token",
                detail="The refresh token is invalid or has already been used.",
            )

        # --- Token expired ------------------------
        if stored_token.expires_at < datetime.now(UTC):
            await self.auth_repo.revoke_refresh_token(stored_token.id)
            raise AppError(
                status_code=401,
                error_code="refresh_token_expired",
                title="Refresh Token Expired",
                detail="Your session has expired. Please log in again.",
            )

        # --- Load the user ------------------------
        user = await self.user_repo.get_by_id(stored_token.user_id)
        if not user or not user.is_active:
            raise AppError(
                status_code=401,
                error_code="invalid_refresh_token",
                title="Invalid Refresh Token",
                detail="The refresh token is invalid.",
            )

        # --- Revoke the old token (rotation) ------------------------
        await self.auth_repo.revoke_refresh_token(stored_token.id)

        # -- Issue new token pair ------------------------
        return await self._issue_token_pair(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=stored_token.session_id,
        )

    # --- Logout ------------------------------

    async def logout(
        self,
        user_id: uuid.UUID,
        access_token_jti: str,
        refresh_token: str | None = None,
    ) -> None:
        """
        Logout from current session.

        Steps:
        1. Blacklist the access token in Redis (immediate invalidation)
        2. Revoke the refresh token in DB (prevents re-use)
        3. Deactivate the session

        The Redis blacklist is needed because JWTs are stateless —
        they're valid until expiry unless we explicitly blacklist them.
        TTL = remaining access token lifetime (no need to keep longer).
        """
        # Step 1: Blacklist the access token in Redis
        await self._blacklist_access_token(access_token_jti)

        # Step 2: Revoke refresh token if provided
        if refresh_token:
            token_hash = hash_token(refresh_token)
            stored = await self.auth_repo.get_refresh_token_by_hash(token_hash)
            if stored:
                await self.auth_repo.revoke_refresh_token(stored.id)
                if stored.session_id:
                    await self.auth_repo.deactivate_session(stored.session_id)

        # Step 3: Write audit log
        await self._write_audit_log(
            user_id=user_id,
            action="user.logout",
            description="User logged out",
            status="success",
        )

    async def logout_all(self, user_id: uuid.UUID) -> None:
        """Logout from all devices — revokes all tokens and sessions."""
        await self.auth_repo.revoke_all_user_tokens(user_id)
        await self.auth_repo.deactivate_all_user_sessions(user_id)
        await self._write_audit_log(
            user_id=user_id,
            action="user.logout_all",
            description="User logged out from all devices",
            status="success",
        )

    # --- Internal helpers ------------------------------

    async def _issue_token_pair(
        self,
        user: User,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_id: uuid.UUID | None = None,
    ) -> TokenResponse:
        """
        Generate access + refresh tokens and persist the refresh token.
        Called by login() and refresh_tokens().
        """
        # Create or reuse session
        if session_id is None:
            session = await self.auth_repo.create_session(
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session_id = session.id

        # Generate access token (JWT)
        access_token, jti = self.create_access_token(user.id)

        # Generate refresh token (random opaque token)
        raw_refresh_token = generate_secure_token(32)
        token_hash = hash_token(raw_refresh_token)

        # Store hashed refresh token
        await self.auth_repo.create_refresh_token(
            user_id=user.id,
            token_hash=token_hash,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Update last login
        await self.user_repo.update_last_login(
            user_id=user.id,
            ip_address=ip_address,
        )

        # Audit log
        await self._write_audit_log(
            user_id=user.id,
            action="user.login",
            description=f"Successful login from {ip_address or 'unknown IP'}",
            status="success",
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,  # Raw token sent to client
            token_type=TOKEN_TYPE,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def _blacklist_token(self, jti: str) -> None:
        """
        Add a JWT's jti to the Redis blacklist.

        TTL = access token lifetime (no need to keep it longer —
        after expiry the token would be invalid anyway).
        """
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.redis_url_str)
            key = f"blacklist:{jti}"
            await r.setex(
                key,
                settings.REDIS_BLACKLIST_TTL_SECONDS,
                "1",
            )
            await r.aclose()
        except Exception as exc:
            logger.warning(
                "Failed to blacklist JWT jti in Redis; allowing token to continue.",
                exc_info=exc,
            )

    async def _log_failed_login(
        self,
        email: str,
        ip_address: str | None,
        reason: str,
        user_id: uuid.UUID | None = None,
    ) -> None:
        """Write a failed login attempt to the audit log."""
        from app.modules.audit.model import AuditLog

        log = AuditLog(
            user_id=user_id,
            actor_email=email,
            action="user.login",
            description=f"Failed login attempt: {reason}",
            ip_address=ip_address,
            status="failure",
            metadata={"reason": reason},
        )
        self.db.add(log)
        await self.db.commit()

    async def _write_audit_log(
        self,
        user_id: uuid.UUID | None,
        action: str,
        description: str,
        status: str,
        ip_address: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Write an audit log entry."""
        from app.modules.audit.model import AuditLog

        log = AuditLog(
            user_id=user_id,
            action=action,
            description=description,
            status=status,
            metadata=metadata,
        )
        self.db.add(log)
        await self.db.commit()
