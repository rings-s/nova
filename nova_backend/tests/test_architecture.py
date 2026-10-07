"""Executable architecture rules.

The dependency rule in nova_backend/README.md is worth nothing if only a code
reviewer enforces it. These tests fail the build when a layer reaches somewhere
it should not.

No database, no app startup — pure AST inspection.
"""

import ast
import pathlib

import pytest

MODULES_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "modules"
WORKER_DIR = MODULES_DIR.parent / "worker"


def _imports(path: pathlib.Path) -> list[str]:
    """Top-level module name of every import in a file."""
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def _files_named(name: str) -> list[pathlib.Path]:
    return sorted(MODULES_DIR.rglob(name))


def _module_of(path: pathlib.Path) -> str:
    return path.parent.name


@pytest.mark.parametrize("path", _files_named("domain.py"), ids=_module_of)
def test_domain_layer_has_no_framework_imports(path: pathlib.Path) -> None:
    """The rule the whole architecture rests on.

    If domain.py imports FastAPI or SQLAlchemy, business rules can no longer be
    tested or reasoned about without infrastructure, and the layering is
    decorative.
    """
    offenders = [
        imported
        for imported in _imports(path)
        if imported.split(".")[0] in {"fastapi", "sqlalchemy", "starlette", "httpx"}
    ]
    assert not offenders, f"{path.name} in '{_module_of(path)}' imports {offenders}"


@pytest.mark.parametrize("path", _files_named("models.py"), ids=_module_of)
def test_persistence_layer_does_not_import_web_framework(path: pathlib.Path) -> None:
    offenders = [
        imported
        for imported in _imports(path)
        if imported.split(".")[0] in {"fastapi", "starlette"}
    ]
    assert not offenders, f"models.py in '{_module_of(path)}' imports {offenders}"


@pytest.mark.parametrize("path", _files_named("service.py"), ids=_module_of)
def test_application_layer_does_not_import_web_framework(path: pathlib.Path) -> None:
    """Services must be callable from a worker or an AI agent, not just HTTP."""
    offenders = [
        imported
        for imported in _imports(path)
        if imported.split(".")[0] in {"fastapi", "starlette"}
    ]
    assert not offenders, f"service.py in '{_module_of(path)}' imports {offenders}"


@pytest.mark.parametrize("path", _files_named("router.py"), ids=_module_of)
def test_router_does_not_reach_past_the_service_layer(path: pathlib.Path) -> None:
    """Routers talk to services, never straight to models or repositories.

    Bypassing the service layer is how domain rules get skipped.
    """
    own_module = _module_of(path)
    offenders = [
        imported
        for imported in _imports(path)
        if imported.startswith("app.modules.")
        and imported.split(".")[-1] in {"models", "repository"}
        # Importing your own module's ORM class purely for a return type
        # annotation is tolerated; reaching into another module's is not.
        and imported.split(".")[2] != own_module
    ]
    assert not offenders, f"router.py in '{own_module}' reaches into {offenders}"


def test_modules_never_import_another_modules_repository() -> None:
    """Cross-module access goes through services or domain events only.

    See nova_backend/README.md, "Cross-module calls".
    """
    violations: list[str] = []
    for path in MODULES_DIR.rglob("*.py"):
        own_module = _module_of(path)
        for imported in _imports(path):
            if not imported.startswith("app.modules."):
                continue
            parts = imported.split(".")
            if len(parts) < 4:
                continue
            target_module, target_file = parts[2], parts[3]
            if target_module == own_module:
                continue
            if target_file in {"repository", "models"}:
                violations.append(f"{own_module}/{path.name} -> {imported}")

    assert not violations, "cross-module persistence access: " + "; ".join(violations)


def test_the_worker_reaches_modules_through_their_services() -> None:
    """Cron jobs and event handlers obey the same rule as the modules.

    Cross-tenant questions go through each module's sweeper (for example
    `build_billing_sweeper`), built in its `dependencies.py`.
    """
    worker_files = sorted(WORKER_DIR.rglob("*.py"))
    assert worker_files, "no worker files found; did app/worker move?"
    violations = [
        f"worker/{path.name} -> {imported}"
        for path in worker_files
        for imported in _imports(path)
        if imported.startswith("app.modules.")
        and len(imported.split(".")) >= 4
        and imported.split(".")[3] in {"repository", "models"}
    ]
    assert not violations, "worker reaches past a service: " + "; ".join(violations)


def _top_level_app_imports(path: pathlib.Path) -> set[str]:
    """`app.*` modules a file imports when it is loaded, not inside a function."""
    found: set[str] = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("app."))
    return found


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one member (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for nxt in graph.get(node, ()):
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1:
                found.append(sorted(component))

    for node in list(graph):
        if node not in index:
            visit(node)
    return found


def test_no_file_imports_itself_back_through_a_cycle() -> None:
    """Import order must never be load-bearing.

    A cycle between files works or fails depending on which one Python loads
    first, so it breaks on an unrelated import change far from either file.
    Imports inside functions are lazy and do not count.
    """
    app_dir = MODULES_DIR.parent
    files = {
        ".".join(("app", *path.relative_to(app_dir).with_suffix("").parts)).removesuffix(
            ".__init__"
        ): path
        for path in app_dir.rglob("*.py")
    }
    graph = {
        name: {imported for imported in _top_level_app_imports(path) if imported in files}
        for name, path in files.items()
    }
    assert _cycles(graph) == []


def test_modules_depend_on_each_other_one_way_below_the_router() -> None:
    """Services and wiring form a one-way graph between modules.

    A router may compose another module's wiring even when that module depends
    back on its own (discovery's public availability builds a booking service;
    booking asks discovery's attribution service about a referral). Below the
    router, a two-way dependency would make the modules one module.
    """
    graph: dict[str, set[str]] = {}
    for path in MODULES_DIR.rglob("*.py"):
        if path.name == "router.py":
            continue
        own = path.relative_to(MODULES_DIR).parts[0]
        graph.setdefault(own, set()).update(
            imported.split(".")[2]
            for imported in _top_level_app_imports(path)
            if imported.startswith("app.modules.") and imported.split(".")[2] != own
        )
    assert _cycles(graph) == []


def test_every_module_documents_itself() -> None:
    """Each module's __init__.py must carry the context summary.

    This is the file a new reader opens first; an empty one makes the module
    boundary invisible.
    """
    undocumented = []
    for init in sorted(MODULES_DIR.glob("*/__init__.py")):
        tree = ast.parse(init.read_text())
        if not ast.get_docstring(tree):
            undocumented.append(_module_of(init))
    assert not undocumented, f"modules missing a context docstring: {undocumented}"


#: ADR-0011: numpy, pandas and plotly live in two pure analytics files. They are
#: heavy and untyped, and a pandas float anywhere near a service is one step
#: from a money bug.
_DATA_LIBRARIES = {"numpy", "pandas", "plotly"}
_DATA_LIBRARY_HOMES = {("analytics", "metrics.py"), ("analytics", "charts.py")}


def test_data_libraries_stay_inside_analytics_computation() -> None:
    app_dir = MODULES_DIR.parent
    offenders: list[str] = []
    for path in sorted(app_dir.rglob("*.py")):
        if (path.parent.name, path.name) in _DATA_LIBRARY_HOMES:
            continue
        found = {name.split(".")[0] for name in _imports(path)} & _DATA_LIBRARIES
        if found:
            offenders.append(f"{path.relative_to(app_dir.parent)} imports {sorted(found)}")
    assert not offenders, "; ".join(offenders)
