from __future__ import annotations

import fnmatch
import posixpath
from typing import Dict, Iterable, List, Optional

from app.profiles.base import ProjectProfile
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


# As três únicas stacks suportadas. Qualquer outra coisa é rejeitada.
# Ordem importa: REACT_NATIVE antes de REACT porque "react native" contém "react".
ALL_PROFILES: List[ProjectProfile] = [
    DJANGO_PROFILE,
    REACT_NATIVE_PROFILE,
    REACT_PROFILE,
]


SUPPORTED_LANGUAGES_DESCRIPTION = (
    "Stacks suportadas: "
    + " | ".join(f"{p.canonical_language} (aliases: {', '.join(p.aliases[:4])})" for p in ALL_PROFILES)
)


def list_profiles() -> List[Dict[str, object]]:
    return [
        {
            "name": p.name,
            "canonical_language": p.canonical_language,
            "aliases": p.aliases,
        }
        for p in ALL_PROFILES
    ]


def resolve_profile(language: Optional[str]) -> ProjectProfile:
    """Maps a free-form language string to one of the supported profiles.

    Raises ValueError when the language doesn't match DRF, React or React Native.
    """
    if not language or not language.strip():
        raise ValueError(
            "language é obrigatório. " + SUPPORTED_LANGUAGES_DESCRIPTION
        )
    # 1) match exato (alias normalizado).
    for profile in ALL_PROFILES:
        if profile.matches_alias(language):
            return profile
    # 2) substring normalizada — cobre "typescript react native + expo" etc.
    #    React Native vai primeiro na lista, então "react native" não cai em React.
    normalized = "".join(ch.lower() for ch in language if ch.isalnum() or ch == " ")
    for profile in ALL_PROFILES:
        for alias in profile.aliases:
            alias_norm = "".join(ch.lower() for ch in alias if ch.isalnum() or ch == " ")
            if alias_norm and alias_norm in normalized:
                return profile
    raise ValueError(
        f"Stack {language!r} não é suportada. " + SUPPORTED_LANGUAGES_DESCRIPTION
    )


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
