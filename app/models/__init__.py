# app/models/__init__.py

from app.models.user import User  # noqa: F401
from app.models.document import Document  # noqa: F401

# Falls vorhanden, ebenfalls registrieren:
from app.models.category import Category  # noqa: F401
from app.models.document_version import DocumentVersion  # noqa: F401
from app.models.email_verification_token import EmailVerificationToken  # noqa: F401
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
