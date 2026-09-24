"""Private, idempotent registration of automatic refresh for existing AOIs."""

from __future__ import annotations

import argparse

from .api import Settings, _build_store
from .service import RibeiraApplication


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register existing property AOIs for automatic refresh"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write policies and initial runs"
    )
    args = parser.parse_args()
    app = RibeiraApplication(_build_store(Settings.from_env()))
    try:
        candidates = app.property_refresh.bootstrap_existing(
            actor="operator:property-refresh-bootstrap", apply=args.apply
        )
        print(
            f"mode={'APPLY' if args.apply else 'DRY_RUN'} candidates={len(candidates)}"
        )
    finally:
        app.store.close()


if __name__ == "__main__":
    main()
