from __future__ import annotations

import os

from dotenv import load_dotenv

from app.db import apply_migrations


def main() -> int:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
    apply_migrations(database_url)
    print("migrations applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
