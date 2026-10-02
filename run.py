from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> int:
    docker = shutil.which("docker")
    if not docker:
        print(
            "error: Docker is required to start the FrameFlux backend stack.",
            file=sys.stderr,
        )
        return 1

    compose_check = subprocess.run(
        [docker, "compose", "version"],
        cwd=BACKEND_DIR,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if compose_check.returncode != 0:
        print(
            "error: Docker Compose is required ('docker compose').",
            file=sys.stderr,
        )
        return compose_check.returncode

    print(
        "Starting FrameFlux backend services: PostgreSQL, Redis, API, and ARQ worker...",
        flush=True,
    )

    try:
        subprocess.run(
            [docker, "compose", "up", "--build"],
            cwd=BACKEND_DIR,
            check=True,
        )
    except KeyboardInterrupt:
        print("\nStopping FrameFlux backend services...", flush=True)
        subprocess.run(
            [docker, "compose", "down"],
            cwd=BACKEND_DIR,
            check=False,
        )
        return 0
    except subprocess.CalledProcessError as exc:
        print(
            f"error: backend stack exited with status {exc.returncode}",
            file=sys.stderr,
        )
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
