import re

# Mindestens 8 Zeichen, 1 Ziffer, 1 Sonderzeichen
_PASSWORD_RE = re.compile(r"^(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")

class PasswordPolicyError(ValueError):
    pass

def validate_password(password: str) -> None:
    if not _PASSWORD_RE.match(password or ""):
        raise PasswordPolicyError("WEAK_PASSWORD")
