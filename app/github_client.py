from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .config import GitHubConfig, TargetConfig
from .mapping import guess_command
from .models import PipelineStatus, PullRequest

logger = logging.getLogger(__name__)

SEARCH_PR_QUERY = """
query ($query: String!, $cursor: String) {
  search(query: $query, type: ISSUE, first: 20, after: $cursor) {
    issueCount
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        ... on PullRequest {
          number
          title
          url
          updatedAt
          mergeable
          mergeStateStatus
          isDraft
          author {
            login
          }
          repository {
            nameWithOwner
          }
          commits(last: 1) {
            nodes {
              commit {
                oid
                status {
                  state
                  contexts {
                    context
                    state
                    targetUrl
                    description
                  }
                }
                checkSuites(first: 10) {
                  nodes {
                    status
                    conclusion
                    checkRuns(first: 10) {
                      nodes {
                        name
                        status
                        conclusion
                        detailsUrl
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


class GitHubClient:
    def __init__(self, config: GitHubConfig) -> None:
        self.config = config
        self.api_base = config.api_base.rstrip("/")
        self.web_base = config.web_base.rstrip("/")
        self.graphql_url = (
            config.api_base if config.api_base.endswith("/graphql") else f"{self.api_base}/graphql"
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "apache-doris-pr-monitor",
            }
        )

    def fetch_pull_requests(self, target: TargetConfig, limit: int = 50) -> List[PullRequest]:
        search_query = self._build_search_query(target)
        cursor: Optional[str] = None
        collected: List[PullRequest] = []
        while len(collected) < limit:
            payload = self._graphql(SEARCH_PR_QUERY, {"query": search_query, "cursor": cursor})
            search = payload["data"]["search"]
            for edge in search["edges"]:
                node = edge.get("node")
                if not node:
                    continue
                collected.append(self._build_pull_request(node))
                if len(collected) >= limit:
                    break
            if not search["pageInfo"]["hasNextPage"]:
                break
            cursor = search["pageInfo"]["endCursor"]
        return collected

    def post_comment(self, repo_full_name: str, pr_number: int, body: str) -> Dict:
        owner, repo = repo_full_name.split("/", 1)
        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        response = self.session.post(url, json={"body": body}, timeout=15)
        self._raise_for_status(response, f"comment on PR #{pr_number}")
        return response.json()

    def update_branch(self, repo_full_name: str, pr_number: int) -> Dict:
        owner, repo = repo_full_name.split("/", 1)
        url = f"{self.api_base}/repos/{owner}/{repo}/pulls/{pr_number}/update-branch"
        response = self.session.put(url, timeout=15)
        if response.status_code == 422:
            logger.info("Update branch skipped for %s#%s", repo_full_name, pr_number)
            return {"message": "Up to date", "status": 422}
        self._raise_for_status(response, f"update branch for PR #{pr_number}")
        return response.json()

    # Internal helpers -----------------------------------------------------

    def _graphql(self, query: str, variables: Dict) -> Dict:
        response = self.session.post(
            self.graphql_url,
            json={"query": query, "variables": variables},
            timeout=20,
        )
        self._raise_for_status(response, "GraphQL query")
        payload = response.json()
        if "errors" in payload:
            raise RuntimeError(f"GitHub GraphQL errors: {payload['errors']}")
        return payload

    def _raise_for_status(self, response: requests.Response, action: str) -> None:
        if response.status_code == 304:
            return
        if response.ok:
            return
        reset_at = response.headers.get("X-RateLimit-Reset")
        if response.status_code == 403 and reset_at:
            raise RuntimeError(
                f"GitHub rate limit exceeded for {action}; resets at {reset_at}."
            )
        detail = response.text[:500]
        raise RuntimeError(f"GitHub API error while {action}: {response.status_code} {detail}")

    @staticmethod
    def _build_search_query(target: TargetConfig) -> str:
        parts = ["is:pr", "is:open", f"author:{target.user}"]
        if target.repos:
            parts.extend([f"repo:{repo}" for repo in target.repos])
        return " ".join(parts)

    def _build_pull_request(self, node: Dict) -> PullRequest:
        updated_at = datetime.fromisoformat(node["updatedAt"].replace("Z", "+00:00"))
        merge_state_status = (node.get("mergeStateStatus") or "UNKNOWN").lower()
        mergeable = (node.get("mergeable") or "UNKNOWN").upper() == "MERGEABLE"
        repo_full_name = node["repository"]["nameWithOwner"]
        pipelines = self._extract_pipelines(node)
        return PullRequest(
            number=node["number"],
            title=node["title"],
            url=node["url"],
            repo_full_name=repo_full_name,
            author=node.get("author", {}).get("login", "unknown"),
            updated_at=updated_at,
            mergeable_state=node.get("mergeStateStatus", "UNKNOWN"),
            mergeable=mergeable,
            has_conflicts=node.get("mergeable", "").upper() == "CONFLICTING",
            update_branch_available=mergeable and merge_state_status in {"behind", "unstable"},
            status_badge=self._status_badge(node),
            pipelines=pipelines,
        )

    @staticmethod
    def _status_badge(node: Dict) -> str:
        if node.get("isDraft"):
            return "Draft"
        merge_state_status = (node.get("mergeStateStatus") or "unknown").replace("_", " ")
        return merge_state_status.title()

    def _extract_pipelines(self, node: Dict) -> List[PipelineStatus]:
        pipelines: Dict[str, PipelineStatus] = {}
        commit_nodes = node.get("commits", {}).get("nodes", [])
        if not commit_nodes:
            return []
        commit = commit_nodes[-1].get("commit", {})
        status_contexts = commit.get("status", {}) or {}
        for context in status_contexts.get("contexts", []) or []:
            pipeline = PipelineStatus(
                name=context.get("context", "Unknown"),
                state=context.get("state", "unknown").lower(),
                conclusion=context.get("state"),
                target_url=context.get("targetUrl"),
                description=context.get("description"),
                suggested_command=guess_command(context.get("context")),
                context_source="status",
            )
            pipelines[pipeline.name] = pipeline
        for suite in commit.get("checkSuites", {}).get("nodes", []) or []:
            for run in suite.get("checkRuns", {}).get("nodes", []) or []:
                name = run.get("name", "Unnamed Check")
                pipeline = PipelineStatus(
                    name=name,
                    state=(run.get("status") or "unknown").lower(),
                    conclusion=(run.get("conclusion") or "").lower() or None,
                    target_url=run.get("detailsUrl"),
                    description=run.get("conclusion"),
                    suggested_command=guess_command(name),
                    context_source="check",
                )
                existing = pipelines.get(name)
                if not existing or pipeline.is_problematic:
                    pipelines[name] = pipeline
        return list(pipelines.values())
