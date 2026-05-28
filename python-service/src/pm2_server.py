from __future__ import annotations

import os
from pathlib import Path

from waitress import serve

from server import create_app

ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    host = os.environ.get("RPC_HOST", "127.0.0.1")
    port = int(os.environ.get("RPC_PORT", "8765"))
    app_data = os.environ.get("RPC_APP_DATA", str(ROOT_DIR / ".role-play-card-data"))
    static_dir = os.environ.get("RPC_STATIC_DIR", str(ROOT_DIR / "vue-renderer" / "dist"))
    app = create_app(app_data, static_dir)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
