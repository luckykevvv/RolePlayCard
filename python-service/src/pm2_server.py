from __future__ import annotations

from waitress import serve

from runtime_config import ROOT_DIR, env_int, env_value
from server import create_app


def main() -> None:
    host = env_value("HOST", "BIND_HOST", "RPC_HOST", default="127.0.0.1")
    port = env_int("PORT", "RPC_PORT", default=8765)
    app_data = env_value("DATA_DIR", "RPC_APP_DATA", default=str(ROOT_DIR / ".role-play-card-data"))
    static_dir = env_value("STATIC_DIR", "RPC_STATIC_DIR", default=str(ROOT_DIR / "vue-renderer" / "dist"))
    app = create_app(app_data, static_dir)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
