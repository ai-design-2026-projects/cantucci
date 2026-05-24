"""CLI to provision a CinePal user.

Usage:
    python -m db.create_user --email user@example.com --password s3cr3t --role admin
    python -m db.create_user --email oracle@example.com --password s3cr3t --role user

Roles must already exist in the ``roles`` table (seeded by migration 006).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from backend.auth.passwords import hash_password
from backend.data_access.users.queries import create_user
from backend.routers.auth import LoginRequest
import logging

from backend.logging_setup import configure_logging


def main() -> None:
    """Parse args, hash the password, and insert the user row."""
    parser = argparse.ArgumentParser(description="Provision a CinePal user.")
    parser.add_argument("--email", required=True, help="User email address.")
    parser.add_argument("--password", required=True, help="Plaintext password.")
    parser.add_argument(
        "--role",
        required=True,
        choices=["user", "admin"],
        help="Role name (must exist in the roles table).",
    )
    args = parser.parse_args()

    configure_logging()
    _auth_log = logging.getLogger("auth")

    try:
        LoginRequest(email=args.email, password=args.password)
    except ValidationError as exc:
        for err in exc.errors():
            print(f"Error: {err['loc'][-1]}: {err['msg']}", file=sys.stderr)
        sys.exit(1)

    user_id = create_user(
        email=args.email,
        password_hash=hash_password(args.password),
        role_name=args.role,
    )

    _auth_log.info("user_created", extra={"email": args.email, "role": args.role})
    print(f"Created user {user_id}  email={args.email}  role={args.role}")


if __name__ == "__main__":
    main()
