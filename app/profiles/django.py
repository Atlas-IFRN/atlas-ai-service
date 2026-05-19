from app.profiles.base import ProjectProfile

DJANGO_PROFILE = ProjectProfile(
    name="drf",
    canonical_language="Django REST Framework (DRF)",
    aliases=[
        "drf",
        "django rest framework",
        "django-rest-framework",
        "django rest",
        "djangorest",
        "django",
        "python django",
        "django drf",
        "django + drf",
    ],
    tech_stack=[
        "python (.py)",
        "django (manage.py, settings.py, urls.py)",
        "django rest framework — OBRIGATÓRIO (serializers, viewsets, routers)",
    ],
    detection_globs=[
        "**/manage.py",
        "**/settings.py",
        "**/settings/base.py",
        "**/wsgi.py",
        "**/asgi.py",
    ],
    hint_globs=[
        "**/requirements.txt",
        "**/pyproject.toml",
        "**/Pipfile",
    ],
    include_globs=[
        # Núcleo Django (mínimo para confirmar a stack)
        "**/manage.py",
        "**/settings.py",
        "**/settings/*.py",
        "**/wsgi.py",
        "**/asgi.py",
        # ⬇ Foco DRF/avaliação: estes são os arquivos que o analisador estático lê
        "**/urls.py",
        "**/models.py",
        "**/models/*.py",
        "**/views.py",
        "**/views/*.py",
        "**/viewsets.py",
        "**/viewsets/*.py",
        "**/serializers.py",
        "**/serializers/*.py",
        "**/forms.py",
        "**/forms/*.py",
        "**/permissions.py",
        "**/filters.py",
        # Testes (continua útil para o LLM avaliar cobertura)
        "**/tests.py",
        "**/tests/**/*.py",
        # Manifestos
        "requirements.txt",
        "requirements/*.txt",
        "pyproject.toml",
        "Pipfile",
        ".env.example",
        "**/README*",
    ],
    exclude_globs=[
        "**/venv/**",
        "**/.venv/**",
        "**/env/**",
        "**/__pycache__/**",
        "**/migrations/0002_*.py",
        "**/migrations/0003_*.py",
        "**/migrations/0004_*.py",
        "**/migrations/0005_*.py",
        "**/migrations/0[1-9]??_*.py",
        "**/static/**",
        "**/staticfiles/**",
        "**/media/**",
        "**/*.sqlite3",
        "**/.git/**",
        "**/node_modules/**",
        "**/db.sqlite3",
    ],
    must_read_globs=[
        "**/manage.py",
        "**/settings.py",
        "**/settings/base.py",
        "**/urls.py",
        "**/models.py",
        "**/views.py",
        "**/viewsets.py",
        "**/serializers.py",
        "requirements.txt",
    ],
    evaluation_hints=(
        "Stack esperada: Python + Django, com forte preferência por Django REST Framework (DRF).\n"
        "FOCO de avaliação (ordem de importância):\n"
        "  1. models.py — entidades do domínio do desafio, com campos coerentes (CharField, ForeignKey, etc.);\n"
        "  2. serializers.py — Serializer/ModelSerializer com Meta.model + Meta.fields;\n"
        "  3. viewsets.py / views.py — ViewSet/ModelViewSet (DRF) OU APIView, com queryset, serializer_class e permission_classes;\n"
        "  4. urls.py — router.register(...) para viewsets ou path(...) para APIViews;\n"
        "  5. forms.py — relevante apenas se o desafio for Django \"clássico\" (server-rendered).\n"
        "Sinais de aderência:\n"
        "  • requirements.txt cita django e (idealmente) djangorestframework;\n"
        "  • models do domínio do desafio existem (não inventar);\n"
        "  • cada model relevante TEM um serializer (Meta.model = model);\n"
        "  • cada serializer TEM um viewset/APIView que o consome (serializer_class);\n"
        "  • cada viewset TEM rota registrada em urls.py (router.register).\n"
        "Anti-sinais (devem reduzir nota / acionar gates):\n"
        "  • ausência de manage.py/settings.py — não é Django;\n"
        "  • só views.py com TemplateView/HttpResponse string — não é DRF;\n"
        "  • models existem mas nenhum serializer/viewset/url — backend incompleto."
    ),
)
