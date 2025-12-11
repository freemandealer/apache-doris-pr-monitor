from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass(slots=True)
class PipelineStatus:
    name: str
    state: str
    conclusion: Optional[str]
    target_url: Optional[str]
    description: Optional[str]
    suggested_command: Optional[str] = None
    context_source: str = "status"

    @property
    def is_problematic(self) -> bool:
        """Return True when the pipeline is pending or failing."""
        if self.state.lower() in {"pending", "queued", "in_progress"}:
            return True
        if self.conclusion is None:
            return True
        return self.conclusion.lower() not in {"success", "neutral", "skipped"}


@dataclass(slots=True)
class PullRequest:
    number: int
    title: str
    url: str
    repo_full_name: str
    author: str
    updated_at: datetime
    mergeable_state: str
    mergeable: bool
    has_conflicts: bool
    update_branch_available: bool
    status_badge: str
    pipelines: List[PipelineStatus] = field(default_factory=list)

    @property
    def problematic_pipelines(self) -> List[PipelineStatus]:
        return [p for p in self.pipelines if p.is_problematic]
