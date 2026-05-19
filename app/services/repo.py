from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from repomix import RepoProcessor, RepomixConfig

from app.profiles import (
    FALLBACK_PROFILE,
    ProjectProfile,
    detect_profile_from_tree,
    resolve_profile,
)
from app.services.analyzers import (
    DjangoAnalysis,
    analyze_django_project,
    format_django_analysis,
)


@dataclass
class PackedRepository:
    """Bundle returned to the LLM layer: focused code + metadata."""

    profile: ProjectProfile
    detected_profile: Optional[ProjectProfile]
    declared_profile: ProjectProfile
    packed_code: str
    file_tree: str
    file_count: int
    static_analysis: Optional[str] = None      # texto pronto para o prompt
    django_analysis: Optional[DjangoAnalysis] = None  # análise tipada (Django) para profile checks


def _safe_repo_url(repo_url: str) -> str:
    """Light validation — avoid passing weird stuff to git."""
    if not re.match(r"^https?://", repo_url):
        raise ValueError(f"Repo URL must be http(s): {repo_url!r}")
    return repo_url


def _git_clone(repo_url: str, target: str) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", _safe_repo_url(repo_url), target],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _walk_repo(root: str) -> List[str]:
    """Returns repo-relative POSIX-style paths, skipping VCS/heavy dirs."""
    skip_dirs = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", ".next", ".expo", "ios", "android"}
    out: List[str] = []
    root_path = Path(root)
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root_path).parts
        if any(part in skip_dirs for part in parts):
            continue
        out.append("/".join(parts))
    return out


def _build_tree(paths: List[str], limit: int = 200) -> str:
    """Compact ASCII listing of repo paths, capped at `limit`."""
    paths = sorted(paths)
    if len(paths) > limit:
        head = paths[:limit]
        return "\n".join(head) + f"\n... ({len(paths) - limit} arquivo(s) a mais omitido(s))"
    return "\n".join(paths)


def _build_repomix_config(output_path: str, profile: ProjectProfile) -> RepomixConfig:
    config = RepomixConfig()
    config.output.file_path = output_path
    config.output.style = "markdown"
    config.output.show_line_numbers = False
    config.output.remove_comments = False
    config.output.remove_empty_lines = True
    config.output.directory_structure = True
    config.output.show_directory_structure = True
    # include == globs do perfil; quando vazio, repomix pega tudo (fallback)
    config.include = list(profile.include_globs)
    config.ignore.custom_patterns = list(profile.exclude_globs)
    config.ignore.use_gitignore = True
    config.ignore.use_default_ignore = True
    return config


def _pack_local(repo_path: str, profile: ProjectProfile, output_path: str) -> str:
    config = _build_repomix_config(output_path, profile)
    config.cwd = repo_path
    processor = RepoProcessor(directory=repo_path, config=config)
    processor.process()
    return Path(output_path).read_text(encoding="utf-8", errors="replace")


def _pack_sync(repo_url: str, declared_language: Optional[str], tmpdir: str) -> PackedRepository:
    repo_path = os.path.join(tmpdir, "src")
    output_path = os.path.join(tmpdir, "packed.md")

    _git_clone(repo_url, repo_path)
    paths = _walk_repo(repo_path)

    declared_profile = resolve_profile(declared_language)
    detected_profile = detect_profile_from_tree(paths)
    # Prioriza o perfil declarado quando ele é reconhecido; senão usa o detectado;
    # senão cai no fallback. Isso preserva o gate de linguagem no LLM.
    effective_profile = (
        declared_profile
        if declared_profile is not FALLBACK_PROFILE
        else (detected_profile or FALLBACK_PROFILE)
    )

    packed = _pack_local(repo_path, effective_profile, output_path)
    static_text, django_analysis = _run_static_analysis(repo_path, effective_profile)

    return PackedRepository(
        profile=effective_profile,
        detected_profile=detected_profile,
        declared_profile=declared_profile,
        packed_code=packed,
        file_tree=_build_tree(paths),
        file_count=len(paths),
        static_analysis=static_text,
        django_analysis=django_analysis,
    )


def _run_static_analysis(repo_path: str, profile: ProjectProfile) -> tuple[Optional[str], Optional[DjangoAnalysis]]:
    """Runs the profile-specific static analyzer. Returns (formatted_text, typed_analysis)."""
    if profile.name == "drf":
        try:
            analysis = analyze_django_project(repo_path)
            return format_django_analysis(analysis), analysis
        except Exception as exc:
            # Análise é "bom ter": nunca quebra o pipeline.
            return f"(falha na análise estática do Django: {exc})", None
    return None, None


async def pack_repository(repo_url: str, declared_language: Optional[str] = None) -> PackedRepository:
    """Clones repo + packs it, focused on the relevant profile's files."""
    tmpdir = tempfile.mkdtemp(prefix="repomix-")
    try:
        return await asyncio.to_thread(_pack_sync, repo_url, declared_language, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def detect_repository_profile(repo_url: str) -> Tuple[Optional[ProjectProfile], List[str]]:
    """Lighter call: clones and returns (detected_profile, file_paths). Skips repomix packing."""
    def _run() -> Tuple[Optional[ProjectProfile], List[str]]:
        tmpdir = tempfile.mkdtemp(prefix="detect-")
        try:
            repo_path = os.path.join(tmpdir, "src")
            _git_clone(repo_url, repo_path)
            paths = _walk_repo(repo_path)
            return detect_profile_from_tree(paths), paths
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return await asyncio.to_thread(_run)
