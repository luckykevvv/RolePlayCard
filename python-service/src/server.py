from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from service import RolePlayCardService, fail, ok


def create_app(app_data_dir: str) -> Flask:
    service = RolePlayCardService(app_data_dir)
    app = Flask(__name__)

    @app.get("/health")
    def health() -> Any:
        return jsonify(ok({"status": "ok"}))

    @app.get("/settings")
    def get_settings() -> Any:
        return jsonify(service.get_settings())

    @app.post("/settings")
    def save_settings() -> Any:
        return jsonify(service.save_settings(request.get_json(force=True)))

    @app.post("/settings/test")
    def test_settings() -> Any:
        return jsonify(service.test_settings())

    @app.get("/drafts")
    def list_drafts() -> Any:
        return jsonify(service.list_drafts())

    @app.get("/drafts/<draft_id>")
    def load_draft(draft_id: str) -> Any:
        return jsonify(service.load_draft(draft_id))

    @app.post("/drafts")
    def save_draft() -> Any:
        return jsonify(service.save_draft(request.get_json(force=True)))

    @app.post("/ai/field")
    def generate_field() -> Any:
        return jsonify(service.generate_field(request.get_json(force=True)))

    @app.post("/ai/image-prompt")
    def generate_image_prompt() -> Any:
        return jsonify(service.generate_image_prompt(request.get_json(force=True)))

    @app.post("/ai/image")
    def generate_image() -> Any:
        return jsonify(service.generate_image(request.get_json(force=True)))

    @app.post("/card/export")
    def export_card() -> Any:
        return jsonify(service.export_character_card(request.get_json(force=True)))

    @app.errorhandler(Exception)
    def handle_error(error: Exception) -> Any:  # noqa: ANN001
        return jsonify(fail(str(error), "internal_error")), 500

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--app-data", default=str(Path.cwd() / ".role-play-card-data"))
    args = parser.parse_args()

    app = create_app(args.app_data)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
