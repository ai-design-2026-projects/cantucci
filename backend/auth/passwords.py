import bcrypt


def hash_password(plain: str) -> str:
    """
    Return a bcrypt hash of ``plain``.
    Args:
        plain: Plaintext password.
    Returns:
        bcrypt hash string safe to store in the DB.
    """
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if ``plain`` matches ``hashed``.
    Args:
        plain:  Plaintext candidate password.
        hashed: bcrypt hash from the DB.
    Returns:
        True on match, False otherwise.
    """
    return bcrypt.checkpw(plain.encode(), hashed.encode())
