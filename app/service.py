from __future__ import annotations

import time
from typing import Dict, List

from .cache import TTLCache
from .config import AppConfig, TargetConfig
from .github_client import GitHubClient
from .mapping import COMMAND_CHOICES
from .models import PullRequest


class PullRequestService:
    def __init__(self, config: AppConfig, client: GitHubClient) -> None:
        self.config = config
        self.client = client
        self.cache = TTLCache()
        self.recent_actions = TTLCache()

    # Public API -----------------------------------------------------------

    def targets(self) -> List[TargetConfig]:
        return self.config.targets

    def get_target(self, label: str) -> TargetConfig:
        for target in self.config.targets:
            if target.label == label:
                return target
        raise KeyError(f"Unknown target: {label}")

    def list_pull_requests(self, label: str) -> List[PullRequest]:
        cache_key = f"prs:{label}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        target = self.get_target(label)
        prs = self.client.fetch_pull_requests(target)
        self.cache.set(cache_key, prs, ttl_seconds=self.config.polling.interval_seconds)
        return prs

    def rerun_pipeline(
        self,
        label: str,
        repo_full_name: str,
        pr_number: int,
        command: str,
    ) -> Dict:
        command = command.strip()
        if not command.startswith("run "):
            raise ValueError("Command must start with 'run '.")
        action_key = f"rerun:{repo_full_name}#{pr_number}:{command}"
        if self.recent_actions.get(action_key):
            return {"status": "skipped", "message": "Command already triggered recently."}
        self.client.post_comment(repo_full_name, pr_number, command)
        self.recent_actions.set(action_key, True, ttl_seconds=120)
        self.cache.set(f"prs:{label}", None, ttl_seconds=0)
        return {"status": "ok", "message": f"Triggered '{command}'"}

    def rebase_and_rerun(self, label: str, repo_full_name: str, pr_number: int) -> Dict:
        update_result = self.client.update_branch(repo_full_name, pr_number)
        buildall_result = self.rerun_pipeline(label, repo_full_name, pr_number, "run buildall")
        return {
            "status": "ok",
            "update": update_result,
            "rerun": buildall_result,
        }

    def command_choices(self) -> List[str]:
        return COMMAND_CHOICES
