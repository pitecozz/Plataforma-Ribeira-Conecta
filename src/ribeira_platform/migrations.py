from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
LOCK_KEY = 8_619_440_217


def _dsn() -> str:
    value = os.environ.get("RIBEIRA_MIGRATION_DATABASE_URL")
    if not value:
        raise RuntimeError("RIBEIRA_MIGRATION_DATABASE_URL is required")
    return value


def _files() -> list[Path]:
    return sorted(
        path
        for path in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
        if not path.name.endswith(".down.sql")
    )


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(value: str | bytes) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _ensure_table(conn: psycopg.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version text PRIMARY KEY,
          filename text NOT NULL,
          checksum text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    conn.commit()


def upgrade() -> list[str]:
    applied: list[str] = []
    with psycopg.connect(_dsn()) as conn:
        _ensure_table(conn)
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            rows = {
                _text(row[0]): _text(row[1])
                for row in conn.execute(
                    "SELECT version, checksum FROM schema_migrations"
                ).fetchall()
            }
            for path in _files():
                version = path.name.split("_", 1)[0]
                digest = _checksum(path)
                if version in rows:
                    if rows[version] != digest:
                        raise RuntimeError(f"migration checksum mismatch: {path.name}")
                    continue
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT INTO schema_migrations(version,filename,checksum) VALUES (%s,%s,%s)",
                        (version, path.name, digest),
                    )
                applied.append(path.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return applied


def clean() -> None:
    if (
        os.environ.get("RIBEIRA_ENV", "development") != "development"
        or os.environ.get("RIBEIRA_ALLOW_CLEAN") != "1"
    ):
        raise RuntimeError(
            "clean is development-only and requires RIBEIRA_ENV=development and RIBEIRA_ALLOW_CLEAN=1"
        )
    with psycopg.connect(_dsn()) as conn:
        with conn.transaction():
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
            conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            conn.execute("GRANT USAGE ON SCHEMA public TO ribeira_app")


def rollback(steps: int = 1) -> list[str]:
    if steps < 1:
        raise ValueError("steps must be positive")
    rolled_back: list[str] = []
    with psycopg.connect(_dsn()) as conn:
        _ensure_table(conn)
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            rows = conn.execute(
                "SELECT version, filename FROM schema_migrations ORDER BY applied_at DESC, version DESC LIMIT %s",
                (steps,),
            ).fetchall()
            for version, filename in rows:
                down = MIGRATIONS_DIR / filename.replace(".sql", ".down.sql")
                if not down.exists():
                    raise RuntimeError(f"rollback file missing for {filename}")
                with conn.transaction():
                    conn.execute(down.read_text(encoding="utf-8"))
                    conn.execute(
                        "DELETE FROM schema_migrations WHERE version = %s", (version,)
                    )
                rolled_back.append(filename)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return rolled_back


def main() -> None:
    parser = argparse.ArgumentParser(description="Ribeira PostgreSQL migration runner")
    parser.add_argument("command", choices=("upgrade", "clean", "rollback"))
    parser.add_argument("steps", nargs="?", type=int, default=1)
    args = parser.parse_args()
    if args.command == "upgrade":
        for name in upgrade():
            print(f"applied {name}")
    elif args.command == "clean":
        clean()
        print("cleaned development database")
    else:
        for name in rollback(args.steps):
            print(f"rolled back {name}")


if __name__ == "__main__":
    main()
