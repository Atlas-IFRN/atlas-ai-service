from __future__ import annotations

import fnmatch
import posixpath
from typing import Dict, Iterable, List, Optional

from app.profiles.base import FALLBACK_PROFILE, ProjectProfile
from app.profiles.django import DJANGO_PROFILE
from app.profiles.react import REACT_NATIVE_PROFILE, REACT_PROFILE


def _glob_match(path: str, pattern: str) -> bool:
    """Globstar-friendly match: ``**/X`` also matches ``X`` at the root.

    fnmatch is purely textual and doesn't understand `**` as a separator
    wildcard, so we additionally check the basename when the pattern is of
    the form ``**/<basename>``.
    """
    if fnmatch.fnmatch(path, pattern):
        return True
    if pattern.startswith("**/"):
        return fnmatch.fnmatch(posixpath.basename(path), pattern[3:])
    return False

ALL_PROFILES: List[ProjectProfile] = [
    DJANGO_PROFILE,
    REACT_NATIVE_PROFILE,  # antes do react porque o alias "react native" contém "react"
    REACT_PROFILE,
]


def list_profiles() -> List[Dict[str, object]]:
    return [
        {
            "name": p.name,
            "canonical_language": p.canonical_language,
            "aliases": p.aliases,
        }
        for p in ALL_PROFILES + [FALLBACK_PROFILE]
    ]


def resolve_profile(language: Optional[str]) -> ProjectProfile:
    """Maps a free-form language string to a known ProjectProfile.

    Falls back to FALLBACK_PROFILE when nothing matches.
    """
    if not language:
        return FALLBACK_PROFILE
    for profile in ALL_PROFILES:
        if profile.matches_alias(language):
            return profile
    # Heurística adicional: tenta por substring normalizada (cobre coisas como
    # "typescript react native + expo" → react-native, mas precisa testar RN antes do React).
    normalized = "".join(ch.lower() for ch in language if ch.isalnum() or ch == " ")
    for profile in ALL_PROFILES:
        for alias in profile.aliases:
            alias_norm = "".join(ch.lower() for ch in alias if ch.isalnum() or ch == " ")
            if alias_norm and alias_norm in normalized:
                return profile
    return FALLBACK_PROFILE


def detect_profile_from_tree(file_paths: Iterable[str]) -> Optional[ProjectProfile]:
    """Detects the most likely profile from a list of repo file paths.

    Scoring: each detection_glob match = 2 points, hint_glob match = 1 point.
    Returns the highest-scoring profile, or None if nothing scored.
    """
    paths = list(file_paths)
    if not paths:
        return None

    scores: Dict[str, int] = {p.name: 0 for p in ALL_PROFILES}
    for profile in ALL_PROFILES:
        for glob in profile.detection_globs:
            if any(_glob_match(p, glob) for p in paths):
                scores[profile.name] += 2
        for glob in profile.hint_globs:
            if any(_glob_match(p, glob) for p in paths):
                scores[profile.name] += 1

    best_name, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score <= 0:
        return None
    for p in ALL_PROFILES:
        if p.name == best_name:
            return p
    return None
