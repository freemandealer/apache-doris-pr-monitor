from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
from pathlib import Path

from .config import AppConfig, load_config
from .github_client import GitHubClient
from .service import PullRequestService


def create_app(config_path: Optional[str] = None) -> Flask:
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )
    app_config: AppConfig = load_config(config_path)
    service = PullRequestService(app_config, GitHubClient(app_config.github))
    app.config["APP_CONFIG"] = app_config
    app.config["PR_SERVICE"] = service

    @app.template_filter("humantime")
    def humantime(value: datetime) -> str:
        if not value:
            return "—"
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    @app.before_request
    def enforce_api_key() -> None:
        if request.method == "GET":
            return None
        api_key = app_config.auth.api_key
        if not api_key:
            return None
        provided = request.headers.get("X-API-Key") or request.form.get("api_key") or request.args.get("api_key")
        if provided != api_key:
            abort(401)
        return None

    @app.get("/")
    def index() -> str:
        target_label = request.args.get("target") or app_config.targets[0].label
        try:
            pull_requests = service.list_pull_requests(target_label)
        except KeyError:
            return redirect(url_for("index", target=app_config.targets[0].label))
        return render_template(
            "index.html",
            targets=app_config.targets,
            active_label=target_label,
            pull_requests=pull_requests,
            command_choices=service.command_choices(),
            refreshed_at=datetime.now(timezone.utc),
        )

    @app.post("/rerun")
    def rerun() -> tuple:
        form = request.form
        target_label = form.get("target") or app_config.targets[0].label
        repo_full_name = form.get("repo")
        pr_number = int(form.get("pr", 0))
        command = form.get("command", "")
        try:
            result = service.rerun_pipeline(target_label, repo_full_name, pr_number, command)
            return jsonify(result)
        except Exception as exc:  # pylint: disable=broad-except
            return jsonify({"status": "error", "message": str(exc)}), 400

    @app.post("/rebase-rerun")
    def rebase_rerun() -> tuple:
        form = request.form
        target_label = form.get("target") or app_config.targets[0].label
        repo_full_name = form.get("repo")
        pr_number = int(form.get("pr", 0))
        try:
            result = service.rebase_and_rerun(target_label, repo_full_name, pr_number)
            return jsonify(result)
        except Exception as exc:  # pylint: disable=broad-except
            return jsonify({"status": "error", "message": str(exc)}), 400

    @app.get("/healthz")
    def health() -> dict:
        return {"status": "ok"}

    return app
