"""Private worker that drives scheduled property catalogue refreshes."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import threading

from .api import Settings, _build_store
from .logging_config import configure_structured_logging
from .service import RibeiraApplication


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ribeira private property refresh worker"
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        raise ValueError("poll-seconds must be positive")
    configure_structured_logging()
    app = RibeiraApplication(_build_store(Settings.from_env()))
    worker_id = os.getenv(
        "RIBEIRA_PROPERTY_REFRESH_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}"
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        while not stop.is_set():
            result = app.property_refresh.run_one(worker_id=worker_id)
            if args.once:
                return
            if result is None:
                stop.wait(args.poll_seconds)
    finally:
        app.store.close()


if __name__ == "__main__":
    main()
