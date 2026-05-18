"""Builds profile-level scorecard checks from a static analysis.

A "profile check" is a binary, objective fact about the project (does it have
≥1 model? ≥1 serializer? etc.). Each check carries a `weight` — the penalty
subtracted from the score when the fact is missing.
"""
from __future__ import annotations

from typing import List

from app.schemas import Check
from app.services.analyzers.django_analyzer import DjangoAnalysis

# ---------------------------------------------------------------------------
# Pesos das penalidades para Django/DRF
# ---------------------------------------------------------------------------
# Estes valores são o "esqueleto mínimo" de um backend DRF. A soma máxima
# possível é mantida em ~70 para que os critérios do desafio (até 30+ de
# penalidade somada) ainda consigam levar o score a 0 quando o projeto é ruim.
DJANGO_CHECK_WEIGHTS = {
    "has_manage_py":     15,  # é Django?
    "has_settings_correctly_configured":       8,
    "has_drf_declared":   8,  # djangorestframework no requirements
    "has_models":        12,  # tem domínio?
    "has_serializer":    10,  # tem camada de API?
    "has_drf_view":      10,  # ViewSet/APIView com queryset+serializer
    "has_drf_route":      7,  # router.register em algum urls.py
}


def build_django_checks(analysis: DjangoAnalysis) -> List[Check]:
    """Maps a `DjangoAnalysis` into a list of profile-kind Checks."""
    drf_views_complete = [
        v for v in analysis.viewsets
        if v.kind in {"viewset", "apiview"} and v.queryset_model and v.serializer_class
    ]
    has_router = any(u.kind == "router" for u in analysis.urls)

    raw = [
        ("has_manage_py", "Projeto é Django (existe manage.py)",
         analysis.has_manage_py,
         "manage.py encontrado" if analysis.has_manage_py
         else "Nenhum manage.py no repositório — não parece Django."),

        ("has_settings_correctly_configured", "settings.py devidamente configurado",
         analysis.has_settings_correctly_configured,
         "settings.py encontrado e configurado corretamente" if analysis.has_settings_correctly_configured
         else "settings.py ausente ou mal configurado."),

        ("has_drf_declared", "Django REST Framework declarado no requirements",
         analysis.has_drf,
         "djangorestframework no requirements.txt" if analysis.has_drf
         else "djangorestframework não está no requirements.txt."),

        ("has_models", "Pelo menos um model do domínio",
         bool(analysis.models),
         f"{len(analysis.models)} model(s): {', '.join(m.name for m in analysis.models[:5])}"
         if analysis.models
         else "Nenhum models.Model definido. Sem domínio = sem aplicação real."),

        ("has_serializer", "Pelo menos um Serializer",
         bool(analysis.serializers),
         f"{len(analysis.serializers)} serializer(s): "
         f"{', '.join(s.name for s in analysis.serializers[:5])}"
         if analysis.serializers
         else "Nenhum Serializer/ModelSerializer — não há contrato de API."),

        ("has_drf_view", "ViewSet ou APIView completo (queryset + serializer_class)",
         bool(drf_views_complete),
         f"{len(drf_views_complete)} view(s) DRF completas: "
         f"{', '.join(v.name for v in drf_views_complete[:5])}"
         if drf_views_complete
         else "Nenhum ViewSet/APIView com queryset E serializer_class definidos."),

        ("has_drf_route", "Rota DRF registrada (router.register em urls.py)",
         has_router,
         f"{sum(1 for u in analysis.urls if u.kind == 'router')} rota(s) DRF registradas"
         if has_router
         else "Nenhuma chamada a router.register — endpoints não expostos."),
    ]

    return [
        Check(
            id=cid,
            label=label,
            kind="profile",
            weight=DJANGO_CHECK_WEIGHTS.get(cid, 0),
            present=bool(present),
            evidence=evidence,
        )
        for (cid, label, present, evidence) in raw
    ]


def build_profile_checks(profile_name: str, analysis: object) -> List[Check]:
    """Dispatch by profile name. Returns [] when no analyzer is registered."""
    if profile_name == "django" and isinstance(analysis, DjangoAnalysis):
        return build_django_checks(analysis)
    return []
