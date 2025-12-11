from __future__ import annotations

from typing import List, Optional

PIPELINE_KEYWORDS = {
    "compile": "run compile",
    "doris_compile": "run compile",
    "fe ut": "run feut",
    "fe_ut": "run feut",
    "be ut": "run beut",
    "be_ut": "run beut",
    "p0": "run p0",
    "cloud_p0": "run cloud_p0",
    "vault_p0": "run cloud_p0",
    "performance": "run performance",
    "external": "run external",
    "nonconcurrent": "run nonConcurrent",
    "non-concurrent": "run nonConcurrent",
    "p1": "run p1",
    "coverage": "run coverage",
    "buildall": "run buildall",
}

COMMAND_CHOICES: List[str] = [
    "run compile",
    "run feut",
    "run beut",
    "run p0",
    "run p1",
    "run cloud_p0",
    "run performance",
    "run external",
    "run nonConcurrent",
    "run coverage",
    "run buildall",
]


def guess_command(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    lowered = name.lower()
    for keyword, command in PIPELINE_KEYWORDS.items():
        if keyword in lowered:
            return command
    return None
