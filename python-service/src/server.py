from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from service import RolePlayCardService, fail, ok


def create_app(app_data_dir: str) -> Flask:
    service = RolePlayCardService(app_data_dir)
    app = Flask(__name__)

    @app.get("/health")
    @app.get("/api/health")
    def health() -> Any:
        return jsonify(ok({"status": "ok"}))

    @app.get("/api/settings")
    def get_settings() -> Any:
        return jsonify(service.get_settings())

    @app.post("/api/settings")
    def save_settings() -> Any:
        return jsonify(service.save_settings(request.get_json(force=True)))

    @app.post("/api/settings/test")
    def test_settings() -> Any:
        return jsonify(service.test_settings(request.get_json(force=True)))

    @app.get("/api/drafts")
    def list_drafts() -> Any:
        return jsonify(service.list_drafts())

    @app.get("/api/drafts/<draft_id>")
    def load_draft(draft_id: str) -> Any:
        return jsonify(service.load_draft(draft_id))

    @app.post("/api/drafts")
    def save_draft() -> Any:
        return jsonify(service.save_draft(request.get_json(force=True)))

    @app.post("/api/ai/field")
    def generate_field() -> Any:
        return jsonify(service.generate_field(request.get_json(force=True)))

    @app.post("/api/ai/image-prompt")
    def generate_image_prompt() -> Any:
        return jsonify(service.generate_image_prompt(request.get_json(force=True)))

    @app.post("/api/ai/image")
    def generate_image() -> Any:
        return jsonify(service.generate_image(request.get_json(force=True)))

    @app.post("/api/files/upload-image")
    def upload_image() -> Any:
        upload = request.files.get("file")
        if upload is None:
            return jsonify(fail("No upload file found.", "validation_error")), 400
        file_bytes = upload.read()
        return jsonify(ok(service.upload_image_file(upload.filename or "upload.png", file_bytes), "Image uploaded."))

    @app.get("/api/files/image")
    def get_image() -> Any:
        image_path = request.args.get("path", "").strip()
        if not image_path:
            return jsonify(fail("Missing image path.", "validation_error")), 400
        try:
            resolved = service.resolve_image_path(image_path)
        except Exception as exc:  # noqa: BLE001
            return jsonify(fail(str(exc), "file_access_error")), 400
        return send_file(resolved)

    @app.post("/api/card/import")
    def import_card_path() -> Any:
        payload = request.get_json(force=True)
        input_path = str(payload.get("inputPath", "")).strip()
        if not input_path:
            return jsonify(fail("Input path is required.", "validation_error")), 400
        return jsonify(service.import_character_card_path(input_path))

    @app.post("/api/card/import-file")
    def import_card_file() -> Any:
        upload = request.files.get("file")
        if upload is None:
            return jsonify(fail("No import file found.", "validation_error")), 400
        file_bytes = upload.read()
        return jsonify(service.import_character_card_file(upload.filename or "import.bin", file_bytes))

    @app.post("/api/card/export-download")
    def export_download() -> Any:
        return jsonify(service.export_character_card_download(request.get_json(force=True)))

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
