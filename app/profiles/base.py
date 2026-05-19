from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ProjectProfile:
    """Static profile describing a project stack.

    A profile encodes everything the IA service needs to evaluate a given
    stack consistently: which files matter, which language string is the
    canonical one, and which hints should reach the LLM prompt.
    """

    name: str
    canonical_language: str
    aliases: List[str] = field(default_factory=list)
    # Tecnologias/keywords que, presentes no código, indicam stack correta.
    # Usado pelo LLM no gate de linguagem (em vez de comparar strings literais).
    tech_stack: List[str] = field(default_factory=list)

    # File names / globs that *strongly* indicate this stack (used for detection).
    detection_globs: List[str] = field(default_factory=list)
    # File globs whose presence weakly hints at this stack (tie-breaker only).
    hint_globs: List[str] = field(default_factory=list)

    # Globs that should be packed and sent to the LLM (high signal).
    include_globs: List[str] = field(default_factory=list)
    # Globs to always drop (low signal / noise).
    exclude_globs: List[str] = field(default_factory=list)

    # Files the evaluator MUST see when present (e.g., entrypoints, settings).
    must_read_globs: List[str] = field(default_factory=list)

    # Free-form text inserted into the LLM prompt for stack-specific scoring.
    evaluation_hints: str = ""

    def matches_alias(self, value: str) -> bool:
        if not value:
            return False
        normalized = _normalize(value)
        if normalized == _normalize(self.name):
            return True
        return any(_normalize(a) == normalized for a in self.aliases)


def _normalize(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
