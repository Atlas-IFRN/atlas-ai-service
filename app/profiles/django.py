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
        "Stack: Python + Django, preferência por Django REST Framework (DRF).\n"
        "\n"
        "REGRAS DE AVALIAÇÃO DRF (use junto com R1–R6 do prompt comum):\n"
        "  D1. Classe Python `Foo` ≠ tabela DB `Foo`. A tabela só existe com aquele nome se houver `db_table='Foo'` em Meta, `CREATE TABLE Foo` em migração, ou DDL explícita. Sem isso, Django gera `app_foo` (default). Critério pedindo TABELA literal exige a string `db_table=...` ou migration, NÃO bastam classes.\n"
        "  D2. Para entidade `X` do domínio existir de verdade: precisa model `class X(models.Model)` em models.py OU models/*.py.\n"
        "  D3. Para o endpoint de `X` estar exposto: precisa ViewSet/APIView + rota (`router.register('xs', XViewSet)` ou `path('xs/', XView.as_view())`). Apenas o ViewSet sem rota = NÃO exposto.\n"
        "  D4. Boas práticas Two Scoops / DRF (úteis para critérios de qualidade): settings.py modular (base/dev/prod), DEBUG=False em produção, SECRET_KEY via env, requirements pinned, serializers com Meta explícito, permission_classes definido, paginação configurada.\n"
        "\n"
        "FOCO de leitura (ordem de importância):\n"
        "  1. models.py / models/*.py — entidades do domínio.\n"
        "  2. serializers.py — Meta.model + Meta.fields.\n"
        "  3. viewsets.py / views.py — queryset + serializer_class + permission_classes.\n"
        "  4. urls.py — router.register / path.\n"
        "  5. settings.py — config (D4).\n"
        "  6. migrations/0001_initial.py — db_table reais (D1).\n"
        "\n"
        "Anti-sinais que devem aparecer no diagnóstico:\n"
        "  • ausência de manage.py/settings.py → não é Django;\n"
        "  • models existem mas nenhum serializer/viewset/url → backend incompleto;\n"
        "  • só views.py com TemplateView/HttpResponse → não é DRF."
    ),
)
