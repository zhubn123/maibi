from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "server" / "config.local.json"
HEALTH_URL = "http://127.0.0.1:8000/healthz"


def main() -> int:
    if not CONFIG_PATH.exists():
        print("[Maibi] Missing server/config.local.json.")
        print("[Maibi] Copy server/config.example.json to server/config.local.json and fill in Tencent ASR credentials.")
        return 1

    print("[Maibi] Starting local signing service...")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--reload",
        ],
        cwd=ROOT,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )

    if not _wait_for_healthz():
        print("[Maibi] Signing service did not become ready.")
        print("[Maibi] Check the signing service window for errors.")
        return 1

    print("[Maibi] Starting client...")
    try:
        return subprocess.call([sys.executable, "-m", "client.demo_app"], cwd=ROOT)
    finally:
        server.terminate()


def _wait_for_healthz() -> bool:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
