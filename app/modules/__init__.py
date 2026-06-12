"""Ensure all models are imported in the correct order so SQLAlchemy can resolve relationships.

This must be imported early in the application lifecycle to avoid:
  - sqlalchemy.exc.InvalidRequestError: mapper failed to locate a name for expression 'X'
  - Circular import issues
"""

from app.modules.audit.model import AuditLog  # noqa: F401

# 3. Models that depend on User and/or Session
from app.modules.auth.model import MFARecoveryCode, RefreshToken  # noqa: F401

# 2. Models that depend on User
from app.modules.sessions.model import Session  # noqa: F401

# Import models in dependency order (base → dependents)
# 1. Base models with NO dependencies
from app.modules.users.model import User  # noqa: F401

__all__ = ["User", "AuditLog", "Session", "RefreshToken", "MFARecoveryCode"]
