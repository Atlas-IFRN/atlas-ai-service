"""Static analysis for Django/DRF projects.

Focus: pinpoint the DRF building blocks that a code-evaluator needs.
Walks the repo with `ast` and extracts:
- urls.py             → URL patterns (path/re_path/router.register/include)
- models.py           → models, fields, foreign keys
- viewsets.py / views.py → ViewSets (DRF) and APIViews, with queryset/serializer
- serializers.py      → Serializer classes (Meta.model, Meta.fields, declared fields)
- forms.py            → Form / ModelForm classes
- requirements.txt    → dependencies (with BOM tolerance)

The output is a structured `DjangoAnalysis` plus `format_django_analysis()`
that renders a compact, LLM-friendly text block.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Caps to keep the prompt section short even for huge repos.
MAX_URLS = 80
MAX_MODELS = 30
MAX_VIEWSETS = 40
MAX_SERIALIZERS = 40
MAX_FORMS = 20
MAX_FIELDS_PER_MODEL = 15
MAX_FIELDS_PER_SERIALIZER = 15


@dataclass
class UrlEntry:
    pattern: str            # "api/login/"
    target: str             # "LoginView.as_view()" / "UserViewSet" / "include('apps.foo.urls')"
    name: Optional[str]     # name="login"
    source_file: str
    kind: str               # "path" | "re_path" | "router" | "include"


@dataclass
class ModelEntry:
    name: str
    bases: List[str]
    fields: List[str]       # ["email = EmailField", "scholarship = ForeignKey(Scholarship)"]
    source_file: str


@dataclass
class ViewSetEntry:
    name: str
    bases: List[str]
    kind: str               # "viewset" (DRF) | "apiview" (DRF) | "generic" (Django CBV) | "function"
    queryset_model: Optional[str]    # "User" if `queryset = User.objects.all()`
    serializer_class: Optional[str]  # "UserSerializer"
    permission_classes: List[str]    # ["IsAuthenticated"]
    filterset_class: Optional[str]   # "UserFilter"
    http_methods: List[str]          # ["get", "post"] — para APIView / @action
    source_file: str


@dataclass
class SerializerEntry:
    name: str
    bases: List[str]                 # ["ModelSerializer"]
    meta_model: Optional[str]        # do Meta.model
    meta_fields: Optional[str]       # "__all__" / "[a,b,c]"
    declared_fields: List[str]       # campos explícitos: "name = CharField"
    source_file: str


@dataclass
class FormEntry:
    name: str
    bases: List[str]                 # ["ModelForm"] | ["Form"]
    meta_model: Optional[str]
    meta_fields: Optional[str]
    declared_fields: List[str]
    source_file: str


@dataclass
class DjangoAnalysis:
    urls: List[UrlEntry] = field(default_factory=list)
    models: List[ModelEntry] = field(default_factory=list)
    viewsets: List[ViewSetEntry] = field(default_factory=list)
    serializers: List[SerializerEntry] = field(default_factory=list)
    forms: List[FormEntry] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    has_manage_py: bool = False
    has_settings_correctly_configured: bool = False
    has_drf: bool = False
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparsable>"


def _str_const(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _attr_chain(node: ast.AST) -> Optional[str]:
    """"X.Y.Z" for an Attribute chain rooted in a Name. None otherwise."""
    parts: List[str] = []
    cur: Optional[ast.AST] = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _call_func_name(call: ast.Call) -> str:
    name = _attr_chain(call.func)
    if name:
        return name
    if isinstance(call.func, ast.Name):
        return call.func.id
    return _safe_unparse(call.func)


def _base_name(base: ast.AST) -> str:
    chain = _attr_chain(base)
    if chain:
        return chain
    if isinstance(base, ast.Name):
        return base.id
    return _safe_unparse(base)


def _base_short(base: ast.AST) -> str:
    return _base_name(base).rsplit(".", 1)[-1]


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def _extract_urls_from_file(tree: ast.AST, source_file: str) -> List[UrlEntry]:
    entries: List[UrlEntry] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        short = _call_func_name(node).rsplit(".", 1)[-1]

        if short in {"path", "re_path"}:
            if not node.args:
                continue
            pattern = _str_const(node.args[0])
            if pattern is None:
                continue
            target_node = node.args[1] if len(node.args) > 1 else None
            target = _safe_unparse(target_node) if target_node is not None else "<none>"
            kind = short
            if isinstance(target_node, ast.Call):
                tname = _call_func_name(target_node).rsplit(".", 1)[-1]
                if tname == "include":
                    kind = "include"
            name = None
            for kw in node.keywords:
                if kw.arg == "name":
                    name = _str_const(kw.value)
            entries.append(UrlEntry(
                pattern=pattern, target=target, name=name,
                source_file=source_file, kind=kind,
            ))

        elif short == "register":
            if len(node.args) < 2:
                continue
            pattern = _str_const(node.args[0])
            if pattern is None:
                continue
            target = _safe_unparse(node.args[1])
            name = None
            for kw in node.keywords:
                if kw.arg == "basename":
                    name = _str_const(kw.value)
            entries.append(UrlEntry(
                pattern=pattern, target=target, name=name,
                source_file=source_file, kind="router",
            ))
    return entries


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_MODEL_BASE_HINTS = {"Model", "AbstractBaseUser", "AbstractUser", "TimeStampedModel"}


def _is_model_class(cls: ast.ClassDef) -> bool:
    return any(_base_short(b) in _MODEL_BASE_HINTS for b in cls.bases)


def _extract_field_from_assign(stmt: ast.AST) -> Optional[str]:
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        target_name = stmt.target.id
        value = stmt.value
    elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        target_name = stmt.targets[0].id
        value = stmt.value
    else:
        return None
    if not isinstance(value, ast.Call):
        return None
    short = _call_func_name(value).rsplit(".", 1)[-1]
    if not (short.endswith("Field") or short in {"ForeignKey", "OneToOneField", "ManyToManyField"}):
        return None
    relation_target = None
    if short in {"ForeignKey", "OneToOneField", "ManyToManyField"} and value.args:
        relation_target = _str_const(value.args[0]) or _safe_unparse(value.args[0])
    return f"{target_name} = {short}({relation_target})" if relation_target else f"{target_name} = {short}"


def _extract_models_from_file(tree: ast.AST, source_file: str) -> List[ModelEntry]:
    entries: List[ModelEntry] = []
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.ClassDef) or not _is_model_class(node):
            continue
        bases = [_base_name(b) for b in node.bases]
        fields: List[str] = []
        for stmt in node.body:
            f = _extract_field_from_assign(stmt)
            if f:
                fields.append(f)
                if len(fields) >= MAX_FIELDS_PER_MODEL:
                    fields.append("... (mais campos omitidos)")
                    break
        entries.append(ModelEntry(name=node.name, bases=bases, fields=fields, source_file=source_file))
    return entries


# ---------------------------------------------------------------------------
# ViewSets / APIViews / Generic CBVs
# ---------------------------------------------------------------------------

_DRF_VIEWSET_BASES = {"ViewSet", "GenericViewSet", "ModelViewSet", "ReadOnlyModelViewSet"}
_DRF_APIVIEW_BASES = {
    "APIView", "GenericAPIView",
    "ListAPIView", "RetrieveAPIView", "CreateAPIView", "UpdateAPIView", "DestroyAPIView",
    "ListCreateAPIView", "RetrieveUpdateAPIView", "RetrieveUpdateDestroyAPIView",
    "RetrieveDestroyAPIView",
}
_DJANGO_GENERIC_VIEW_BASES = {
    "View", "TemplateView", "ListView", "DetailView",
    "CreateView", "UpdateView", "DeleteView", "FormView",
}

_HTTP_METHOD_NAMES = {"get", "post", "put", "patch", "delete", "head", "options"}


def _view_kind(cls: ast.ClassDef) -> Optional[str]:
    """Returns 'viewset' / 'apiview' / 'generic' if any base matches, else None."""
    for base in cls.bases:
        short = _base_short(base)
        if short in _DRF_VIEWSET_BASES:
            return "viewset"
        if short in _DRF_APIVIEW_BASES:
            return "apiview"
        if short in _DJANGO_GENERIC_VIEW_BASES:
            return "generic"
    return None


def _queryset_model_from_value(value: ast.AST) -> Optional[str]:
    """`User.objects.all()` → 'User'; `User.objects` → 'User'."""
    if isinstance(value, ast.Call):
        chain = _attr_chain(value.func)
        if chain:
            return chain.split(".")[0]
    chain = _attr_chain(value)
    return chain.split(".")[0] if chain else None


def _str_list_from_value(value: ast.AST) -> List[str]:
    """[A, B.C] → ['A', 'B.C']."""
    if not isinstance(value, (ast.List, ast.Tuple)):
        return []
    out: List[str] = []
    for elt in value.elts:
        chain = _attr_chain(elt)
        if chain:
            out.append(chain)
        elif isinstance(elt, ast.Name):
            out.append(elt.id)
        else:
            s = _str_const(elt)
            if s is not None:
                out.append(s)
    return out


def _extract_action_methods(cls: ast.ClassDef) -> List[str]:
    """Captura métodos HTTP de APIView (def get/post/...) e @action(methods=[...])."""
    methods: Set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name in _HTTP_METHOD_NAMES:
                methods.add(stmt.name.upper())
            for deco in stmt.decorator_list:
                if isinstance(deco, ast.Call) and _call_func_name(deco).rsplit(".", 1)[-1] == "action":
                    for kw in deco.keywords:
                        if kw.arg == "methods":
                            for m in _str_list_from_value(kw.value):
                                methods.add(m.upper())
    return sorted(methods)


def _extract_viewsets_from_file(tree: ast.AST, source_file: str) -> List[ViewSetEntry]:
    entries: List[ViewSetEntry] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef):
            kind = _view_kind(node)
            if kind is None:
                continue
            bases = [_base_name(b) for b in node.bases]
            queryset_model = None
            serializer_class = None
            permission_classes: List[str] = []
            filterset_class: Optional[str] = None
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    tname = stmt.targets[0].id
                    if tname == "queryset":
                        queryset_model = queryset_model or _queryset_model_from_value(stmt.value)
                    elif tname == "serializer_class":
                        if isinstance(stmt.value, ast.Name):
                            serializer_class = stmt.value.id
                        else:
                            serializer_class = _attr_chain(stmt.value) or _safe_unparse(stmt.value)
                    elif tname == "permission_classes":
                        permission_classes = _str_list_from_value(stmt.value)
                    elif tname == "filterset_class":
                        if isinstance(stmt.value, ast.Name):
                            filterset_class = stmt.value.id
                        else:
                            filterset_class = _attr_chain(stmt.value) or _safe_unparse(stmt.value)
            entries.append(ViewSetEntry(
                name=node.name, bases=bases, kind=kind,
                queryset_model=queryset_model,
                serializer_class=serializer_class,
                permission_classes=permission_classes,
                filterset_class=filterset_class,
                http_methods=_extract_action_methods(node),
                source_file=source_file,
            ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decos: List[str] = []
            http_methods: Set[str] = set()
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call):
                    short = _call_func_name(deco).rsplit(".", 1)[-1]
                    if short == "api_view":
                        decos.append("api_view")
                        for arg in deco.args:
                            for m in _str_list_from_value(arg):
                                http_methods.add(m.upper())
                else:
                    short = _base_short(deco)
                    if short in {"require_POST", "require_GET", "require_http_methods"}:
                        decos.append(short)
            if decos:
                entries.append(ViewSetEntry(
                    name=node.name, bases=decos, kind="function",
                    queryset_model=None, serializer_class=None,
                    permission_classes=[], filterset_class=None,
                    http_methods=sorted(http_methods),
                    source_file=source_file,
                ))
    return entries


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

_SERIALIZER_BASE_HINTS = {
    "Serializer", "ModelSerializer", "HyperlinkedModelSerializer",
    "ListSerializer", "BaseSerializer",
}


def _is_serializer_class(cls: ast.ClassDef) -> bool:
    return any(_base_short(b) in _SERIALIZER_BASE_HINTS for b in cls.bases)


def _read_meta(cls: ast.ClassDef) -> tuple[Optional[str], Optional[str]]:
    """Procura `class Meta:` na classe e devolve (model, fields-as-string)."""
    for stmt in cls.body:
        if isinstance(stmt, ast.ClassDef) and stmt.name == "Meta":
            model = None
            fields = None
            for inner in stmt.body:
                if isinstance(inner, ast.Assign) and len(inner.targets) == 1 and isinstance(inner.targets[0], ast.Name):
                    name = inner.targets[0].id
                    if name == "model":
                        if isinstance(inner.value, ast.Name):
                            model = inner.value.id
                        else:
                            model = _attr_chain(inner.value) or _safe_unparse(inner.value)
                    elif name == "fields":
                        s = _str_const(inner.value)
                        if s is not None:
                            fields = s  # "__all__"
                        else:
                            fields = _safe_unparse(inner.value)
            return model, fields
    return None, None


def _serializer_declared_fields(cls: ast.ClassDef) -> List[str]:
    out: List[str] = []
    for stmt in cls.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            continue
        tname = stmt.targets[0].id
        if tname.startswith("_") or tname in {"Meta"}:
            continue
        if not isinstance(stmt.value, ast.Call):
            continue
        short = _call_func_name(stmt.value).rsplit(".", 1)[-1]
        # heurística: campos DRF típicos terminam em "Field" ou são *RelatedField, SerializerMethodField, etc.
        if short.endswith("Field") or short in {"SerializerMethodField"}:
            out.append(f"{tname} = {short}")
            if len(out) >= MAX_FIELDS_PER_SERIALIZER:
                out.append("... (mais campos omitidos)")
                break
    return out


def _extract_serializers_from_file(tree: ast.AST, source_file: str) -> List[SerializerEntry]:
    entries: List[SerializerEntry] = []
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.ClassDef) or not _is_serializer_class(node):
            continue
        bases = [_base_name(b) for b in node.bases]
        model, fields = _read_meta(node)
        entries.append(SerializerEntry(
            name=node.name, bases=bases,
            meta_model=model, meta_fields=fields,
            declared_fields=_serializer_declared_fields(node),
            source_file=source_file,
        ))
    return entries


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

_FORM_BASE_HINTS = {"Form", "ModelForm", "BaseForm", "BaseModelForm", "UserCreationForm", "UserChangeForm"}


def _is_form_class(cls: ast.ClassDef) -> bool:
    return any(_base_short(b) in _FORM_BASE_HINTS for b in cls.bases)


def _form_declared_fields(cls: ast.ClassDef) -> List[str]:
    out: List[str] = []
    for stmt in cls.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            continue
        tname = stmt.targets[0].id
        if tname.startswith("_") or tname in {"Meta"}:
            continue
        if not isinstance(stmt.value, ast.Call):
            continue
        short = _call_func_name(stmt.value).rsplit(".", 1)[-1]
        if short.endswith("Field"):
            out.append(f"{tname} = {short}")
    return out


def _extract_forms_from_file(tree: ast.AST, source_file: str) -> List[FormEntry]:
    entries: List[FormEntry] = []
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.ClassDef) or not _is_form_class(node):
            continue
        bases = [_base_name(b) for b in node.bases]
        model, fields = _read_meta(node)
        entries.append(FormEntry(
            name=node.name, bases=bases,
            meta_model=model, meta_fields=fields,
            declared_fields=_form_declared_fields(node),
            source_file=source_file,
        ))
    return entries


# ---------------------------------------------------------------------------
# Requirements + file reading
# ---------------------------------------------------------------------------

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")


def _read_text_tolerant(path: Path) -> Optional[str]:
    """Reads a text file detecting BOMs and tolerating truncated multibyte data."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _read_requirements(repo_root: Path) -> List[str]:
    packages: List[str] = []
    for candidate in ["requirements.txt", "requirements/base.txt", "requirements/dev.txt", "requirements/prod.txt"]:
        f = repo_root / candidate
        if not f.exists():
            continue
        text = _read_text_tolerant(f)
        if text is None:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = _REQ_LINE.match(line)
            if m:
                packages.append(m.group(1).lower())
    seen: Set[str] = set()
    out: List[str] = []
    for p in packages:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


_SKIP_DIRS = {".git", "venv", ".venv", "env", "__pycache__", "node_modules", "static", "staticfiles", "media", "migrations"}

# Apenas estes arquivos passam pelo AST (foco DRF + nichado).
_TARGET_BASENAMES = {"urls.py", "models.py", "views.py", "viewsets.py", "serializers.py", "forms.py"}
_TARGET_DIR_SEGMENTS = ("/models/", "/views/", "/viewsets/", "/serializers/", "/forms/")


def _is_target_file(rel_path: str, basename: str) -> bool:
    if basename in _TARGET_BASENAMES:
        return True
    return any(seg in rel_path for seg in _TARGET_DIR_SEGMENTS)


def _iter_python_files(repo_root: Path):
    for path in repo_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        yield path


def _parse_safe(path: Path) -> Optional[ast.AST]:
    source = _read_text_tolerant(path)
    if source is None:
        return None
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        logger.debug("Skipping %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def analyze_django_project(repo_root: str) -> DjangoAnalysis:
    root = Path(repo_root)
    analysis = DjangoAnalysis()

    analysis.requirements = _read_requirements(root)
    analysis.has_drf = any(pkg in analysis.requirements for pkg in ("djangorestframework", "django-rest-framework"))

    for py_path in _iter_python_files(root):
        rel = py_path.relative_to(root).as_posix()
        basename = py_path.name
        if basename == "manage.py":
            analysis.has_manage_py = True
            continue
        if basename == "settings.py" or "/settings/" in rel:
            analysis.has_settings_correctly_configured = True
            continue

        if not _is_target_file(rel, basename):
            continue

        tree = _parse_safe(py_path)
        if tree is None:
            continue

        if basename == "urls.py":
            analysis.urls.extend(_extract_urls_from_file(tree, rel))
        if basename == "models.py" or "/models/" in rel:
            analysis.models.extend(_extract_models_from_file(tree, rel))
        if basename in {"views.py", "viewsets.py"} or "/views/" in rel or "/viewsets/" in rel:
            analysis.viewsets.extend(_extract_viewsets_from_file(tree, rel))
        if basename == "serializers.py" or "/serializers/" in rel:
            analysis.serializers.extend(_extract_serializers_from_file(tree, rel))
        if basename == "forms.py" or "/forms/" in rel:
            analysis.forms.extend(_extract_forms_from_file(tree, rel))

    # Caps
    def _cap(items, max_n, label):
        if len(items) > max_n:
            analysis.notes.append(f"{len(items)} {label} — truncado(s) em {max_n}.")
            return items[:max_n]
        return items

    analysis.urls = _cap(analysis.urls, MAX_URLS, "URLs")
    analysis.models = _cap(analysis.models, MAX_MODELS, "models")
    analysis.viewsets = _cap(analysis.viewsets, MAX_VIEWSETS, "views/viewsets")
    analysis.serializers = _cap(analysis.serializers, MAX_SERIALIZERS, "serializers")
    analysis.forms = _cap(analysis.forms, MAX_FORMS, "forms")
    return analysis


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def _fmt_list(items: List[str], sep: str = ", ") -> str:
    return sep.join(items) if items else "-"


def format_django_analysis(a: DjangoAnalysis) -> str:
    lines: List[str] = []
    lines.append("[FATOS EXTRAÍDOS ESTATICAMENTE — confie nesta seção mais do que no texto bruto]")
    lines.append(
        f"manage.py: {'sim' if a.has_manage_py else 'NÃO'}  |  "
        f"settings.py: {'sim' if a.has_settings_correctly_configured else 'NÃO'}  |  "
        f"DRF declarado: {'sim' if a.has_drf else 'não'}"
    )

    if a.requirements:
        head = ", ".join(a.requirements[:25])
        more = "" if len(a.requirements) <= 25 else f"  (+{len(a.requirements) - 25} pacotes)"
        lines.append(f"Dependências: {head}{more}")
    else:
        lines.append("Dependências: (requirements.txt não encontrado / vazio)")

    # ----- URLs -----
    lines.append("")
    lines.append(f"URLs ({len(a.urls)}):")
    if not a.urls:
        lines.append("  (nenhuma rota encontrada — urls.py ausente ou sem path/router)")
    else:
        for u in a.urls:
            name = f"  name={u.name}" if u.name else ""
            lines.append(f"  [{u.kind:7s}] {u.pattern!r:35s} → {u.target}{name}   ({u.source_file})")

    # ----- Models -----
    lines.append("")
    lines.append(f"Models ({len(a.models)}):")
    if not a.models:
        lines.append("  (nenhum model detectado)")
    else:
        for m in a.models:
            lines.append(f"  • {m.name}  bases=[{_fmt_list(m.bases)}]   ({m.source_file})")
            for f in m.fields:
                lines.append(f"      - {f}")

    # ----- ViewSets / APIViews -----
    lines.append("")
    drf_count = sum(1 for v in a.viewsets if v.kind in {"viewset", "apiview"})
    lines.append(f"ViewSets/APIViews/Views ({len(a.viewsets)} total, {drf_count} são DRF):")
    if not a.viewsets:
        lines.append("  (nenhuma view detectada)")
    else:
        for v in a.viewsets:
            extras = []
            if v.queryset_model:
                extras.append(f"queryset={v.queryset_model}")
            if v.serializer_class:
                extras.append(f"serializer={v.serializer_class}")
            if v.permission_classes:
                extras.append(f"permissions=[{_fmt_list(v.permission_classes)}]")
            if v.filterset_class:
                extras.append(f"filterset={v.filterset_class}")
            if v.http_methods:
                extras.append(f"methods=[{_fmt_list(v.http_methods)}]")
            tail = f"  [{'; '.join(extras)}]" if extras else ""
            lines.append(f"  • {v.name} <{v.kind}>  bases=[{_fmt_list(v.bases)}]{tail}   ({v.source_file})")

    # ----- Serializers -----
    lines.append("")
    lines.append(f"Serializers ({len(a.serializers)}):")
    if not a.serializers:
        lines.append("  (nenhum serializer detectado)")
    else:
        for s in a.serializers:
            meta = []
            if s.meta_model:
                meta.append(f"model={s.meta_model}")
            if s.meta_fields:
                meta.append(f"fields={s.meta_fields}")
            tail = f"  Meta[{'; '.join(meta)}]" if meta else ""
            lines.append(f"  • {s.name}  bases=[{_fmt_list(s.bases)}]{tail}   ({s.source_file})")
            for f in s.declared_fields:
                lines.append(f"      - {f}")

    # ----- Forms -----
    lines.append("")
    lines.append(f"Forms ({len(a.forms)}):")
    if not a.forms:
        lines.append("  (nenhum form detectado)")
    else:
        for fm in a.forms:
            meta = []
            if fm.meta_model:
                meta.append(f"model={fm.meta_model}")
            if fm.meta_fields:
                meta.append(f"fields={fm.meta_fields}")
            tail = f"  Meta[{'; '.join(meta)}]" if meta else ""
            lines.append(f"  • {fm.name}  bases=[{_fmt_list(fm.bases)}]{tail}   ({fm.source_file})")
            for f in fm.declared_fields:
                lines.append(f"      - {f}")

    if a.notes:
        lines.append("")
        lines.append("Notas:")
        for n in a.notes:
            lines.append(f"  - {n}")

    return "\n".join(lines)
