"""Every file a document names exists, and every `[[wiki link]]` resolves. Pure
— no database.

Docs drift quietly: a module is removed or a test renamed, and the design doc
that sent readers there keeps sending them. This fails the build at the moment
of the rename instead of months later. It reads backticked paths with a file
extension (`app/core/security.py`, `stores/tickets.js`), trying each place a
doc's shorthand can be rooted, and the Obsidian-style links between docs.

It runs wherever the files are. CI checks out the whole repository. `make test`
runs in the `tools` container, which mounts `nova_backend/` at `/app` and
`docs/` at `/docs` but not the frontend, so there only Python paths are held to
account.
"""

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
DOCS = REPO / "docs"
FRONTEND = REPO / "nova-frontend"

#: A reference that is meant not to resolve, and why. Keyed by the document
#: (relative to the repository root) and the path exactly as written.
EXPECTED_MISSING: dict[tuple[str, str], str] = {
    ("CLAUDE.md", "frontend/package.json"): "names the path CI wrongly gates on",
    (
        "docs/02-Backend-FastAPI-DDD-Structure.md",
        "core/nextcloud.py",
    ): "removed; annotated there (ADR-0013)",
    ("docs/10-AI-Agent-Catalog.md", "workers/retention.py"): "the retention agent is not built yet",
    ("docs/14-Threat-Model.md", "media/service.py"): "removed; the doc's 2026-09-23 note says so",
    ("docs/14-Threat-Model.md", "media/domain.py"): "removed; the doc's 2026-09-23 note says so",
    (
        "docs/14-Threat-Model.md",
        "tests/modules/media/test_service.py",
    ): "SR-07/SR-22, moot since ADR-0013",
    (
        "docs/decisions/0004-bilingual-field-strategy.md",
        "tenants/domain.py",
    ): "history: the module became identity",
    (
        "docs/decisions/0013-business-photos-replace-nextcloud-media.md",
        "app/integrations/storage/nextcloud.py",
    ): "the file this ADR removed",
}

#: docs/14 section 8 marks a security requirement's test that is still to be
#: written with "New:". A path on such a line is a plan, not a reference.
PLANNED = "New:"

_BACKTICKED = re.compile(r"`([^`\s]+)`")
_EXTENSION = re.compile(r"\.(py|js|svelte|md|ya?ml|toml|sql|css|json|sh|cfg|ini)$")
_WIKI_LINK = re.compile(r"\[\[([^\]|#]+)")


def _documents() -> list[Path]:
    found = sorted(DOCS.glob("**/*.md")) if DOCS.is_dir() else []
    for extra in (
        REPO / "README.md",
        REPO / "CLAUDE.md",
        BACKEND / "README.md",
        FRONTEND / "README.md",
    ):
        if extra.is_file():
            found.append(extra)
    return found


def _roots(document: Path) -> list[Path]:
    roots = [REPO, BACKEND, BACKEND / "app", BACKEND / "app" / "modules", document.parent]
    lib = FRONTEND / "src" / "lib"
    roots += [FRONTEND, FRONTEND / "src", lib, lib / "i18n", lib / "components"]
    return roots


def _exists(path: str, roots: list[Path]) -> bool:
    # `nova_backend/app/...` names the backend wherever it is mounted: in the
    # tools container that is /app, not /nova_backend.
    candidates = [path]
    if path.startswith("nova_backend/"):
        candidates.append(str(BACKEND / path.removeprefix("nova_backend/")))
    return any((root / candidate).exists() for candidate in candidates for root in roots)


def _name(document: Path) -> str:
    return document.relative_to(REPO).as_posix()


def _paths_in(line: str) -> list[str]:
    paths = []
    for token in _BACKTICKED.findall(line):
        token = re.sub(r":\d+(-\d+)?$", "", token.split("::")[0].rstrip(".,:;"))
        if any(c in token for c in "<>*{}…$|()") or "/" not in token:
            continue  # a pattern, a placeholder, or a bare file name
        if token.startswith(("http", "/", "~")) or not _EXTENSION.search(token):
            continue
        paths.append(token)
    return paths


def _checkable(path: str) -> bool:
    # Without the frontend checked out, only Python paths can be judged.
    return FRONTEND.is_dir() or path.endswith(".py")


def test_the_documents_were_found() -> None:
    assert DOCS.is_dir(), f"{DOCS} is missing; the tools container mounts it at /docs"
    assert len(_documents()) > 10


@pytest.mark.parametrize("document", _documents(), ids=_name)
def test_every_file_a_document_names_exists(document: Path) -> None:
    roots = _roots(document)
    missing = []
    for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
        if PLANNED in line:
            continue
        for path in _paths_in(line):
            if (_name(document), path) in EXPECTED_MISSING or not _checkable(path):
                continue
            if not _exists(path, roots):
                missing.append(f"line {number}: {path}")
    assert missing == [], (
        "these files do not exist; fix the reference, or list it in EXPECTED_MISSING with a reason"
    )


def test_every_expected_miss_is_still_missing_and_still_written() -> None:
    """An exemption for a file that now exists, or a line that is gone, would
    otherwise sit here forever, excusing nothing."""
    stale = []
    for (name, path), _reason in EXPECTED_MISSING.items():
        document = REPO / name
        if not document.is_file():
            continue
        if f"`{path}" not in document.read_text(encoding="utf-8"):
            stale.append(f"{name} no longer mentions {path}")
        elif _exists(path, _roots(document)):
            stale.append(f"{path} exists now")
    assert stale == []


def test_every_wiki_link_resolves() -> None:
    broken = []
    for document in _documents():
        # Inline code talks about the syntax (CLAUDE.md's "`[[links]]`"); it is not a link.
        text = re.sub(r"`[^`\n]*`", "", document.read_text(encoding="utf-8"))
        for target in _WIKI_LINK.findall(text):
            target = target.strip()
            if not (
                (DOCS / f"{target}.md").is_file() or (DOCS / "decisions" / f"{target}.md").is_file()
            ):
                broken.append(f"{_name(document)}: [[{target}]]")
    assert broken == []


#: The `status` a numbered doc may declare; docs/00-Index.md explains each.
STATUSES = frozenset({"current", "design", "reference", "index", "template"})


def test_every_numbered_doc_declares_its_status() -> None:
    """A reader has to know whether a doc describes the code or the plan for it."""
    wrong = []
    for document in sorted(DOCS.glob("[0-9][0-9]-*.md")):
        text = document.read_text(encoding="utf-8")
        frontmatter = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
        match = re.search(r"^status: (\S+)$", frontmatter, re.MULTILINE)
        if match is None or match[1] not in STATUSES:
            wrong.append(f"{document.name}: {match[1] if match else 'no status'}")
    assert wrong == [], f"set `status:` to one of {sorted(STATUSES)}"
