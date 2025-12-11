from __future__ import annotations

from app import create_app

app = create_app()

if __name__ == "__main__":
    config = app.config["APP_CONFIG"]
    app.run(host=config.server.host, port=config.server.port)
