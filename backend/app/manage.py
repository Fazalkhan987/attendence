"""Admin management:  python -m app.manage create-admin --username alice"""
from __future__ import annotations

import argparse
import getpass
import sys

from .config import Settings
from .db import AppDatabase
from .errors import AppError
from .services.auth import AuthService


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="app.manage")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("--username", required=True)
    c.add_argument("--display-name")
    r = sub.add_parser("set-password")
    r.add_argument("--username", required=True)
    args = p.parse_args(argv)
    s = Settings.from_env()
    auth = AuthService(AppDatabase(s.app_db_path), s)
    try:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat: "):
            print("Passwords differ."); return 2
        if args.cmd == "create-admin":
            auth.create_admin(args.username, pw, args.display_name)
            print(f"Admin '{args.username}' created.")
        else:
            auth.set_password(args.username, pw)
            print("Password updated; existing sessions were signed out.")
    except AppError as e:
        print(f"ERROR: {e.message}"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
