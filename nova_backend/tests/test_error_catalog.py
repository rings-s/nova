"""docs/15-API-Error-Codes.md lists every error code the API can send, and
nothing else. Pure — no database.

Clients branch on `error.code`, so a code that exists only in the source is a
contract nobody was told about, and a code that exists only in the doc sends a
reader looking for something that cannot happen. Codes come from three places,
and each is read from the code rather than restated here:

  - every public `DomainError` subclass, with its status;
  - `_error_response` calls in `app/core/error_handlers.py` whose code is a
    literal, and the framework's `http_<status>` family;
  - `translate_integrity_error`, driven with each SQLSTATE it recognises.
"""

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import app.main  # noqa: F401  (imports every module, so every error class exists)
from app.core.exceptions import DomainError
from app.db import errors as db_errors

BACKEND = Path(__file__).resolve().parent.parent
CATALOG = BACKEND.parent / "docs" / "15-API-Error-Codes.md"

#: A row of one of the catalog's tables: | `code` | status | ...
_ROW = re.compile(r"^\|\s*`(?P<code>[a-z0-9_<>]+)`\s*\|\s*(?P<status>\d{3}|any)\s*\|")


def _documented() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        code = match["code"]
        assert code not in rows, f"`{code}` is listed twice in {CATALOG.name}"
        rows[code] = match["status"]
    return rows


def _domain_error_codes() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    stack: list[type[DomainError]] = [DomainError]
    while stack:
        cls = stack.pop()
        for sub in cls.__subclasses__():
            stack.append(sub)
            # A leading underscore marks an error that never leaves its module,
            # such as a tool's internal signal inside an AI turn.
            if not sub.__name__.startswith("_"):
                found.setdefault(sub.code, set()).add(str(sub.status_code))
    return found


def _handler_codes() -> dict[str, set[str]]:
    source = (BACKEND / "app" / "core" / "error_handlers.py").read_text(encoding="utf-8")
    found: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_error_response"):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        code, status = keywords.get("code"), keywords.get("status_code")
        if isinstance(code, ast.JoinedStr):
            found.setdefault("http_<status>", set()).add("any")
        elif isinstance(code, ast.Constant) and isinstance(status, ast.Constant):
            found.setdefault(code.value, set()).add(str(status.value))
    return found


def _integrity_codes() -> dict[str, set[str]]:
    def fake(*, constraint: str | None = None, sqlstate: str | None = None) -> Any:
        orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint), sqlstate=sqlstate)
        return SimpleNamespace(orig=orig)

    probes = [fake(constraint=name) for name in db_errors._CONSTRAINT_ERRORS]
    probes += [
        fake(sqlstate=state)
        for state in (
            db_errors._UNIQUE_VIOLATION,
            db_errors._FOREIGN_KEY_VIOLATION,
            db_errors._CHECK_VIOLATION,
            db_errors._EXCLUSION_VIOLATION,
            "unrecognised",
        )
    ]
    found: dict[str, set[str]] = {}
    for probe in probes:
        error = db_errors.translate_integrity_error(probe)
        found.setdefault(error.code, set()).add(str(error.status_code))
    return found


def _emitted() -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {}
    for source in (_domain_error_codes(), _handler_codes(), _integrity_codes()):
        for code, statuses in source.items():
            merged.setdefault(code, set()).update(statuses)
    return merged


def test_every_code_the_api_sends_is_documented() -> None:
    missing = sorted(set(_emitted()) - set(_documented()))
    assert missing == [], f"add these to {CATALOG.name}: {missing}"


def test_every_documented_code_can_be_sent() -> None:
    stale = sorted(set(_documented()) - set(_emitted()))
    assert stale == [], f"remove these from {CATALOG.name}, nothing raises them: {stale}"


def test_each_code_is_documented_with_its_status() -> None:
    emitted = _emitted()
    wrong = [
        f"`{code}` documented as {status}, sent as {sorted(emitted[code])}"
        for code, status in _documented().items()
        if code in emitted and emitted[code] != {status}
    ]
    assert wrong == []
