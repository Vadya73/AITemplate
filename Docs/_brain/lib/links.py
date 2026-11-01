import os
import re
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"(\[[^\]]*\]\()(?:<([^>]+)>|([^)\s]+))(\))")
FENCE_RE = re.compile(r"^\s*```")
CODESPAN_RE = re.compile(r"`[^`]*`")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "data:")
SKIP_DIRS = ("bin", "obj", ".git", ".obsidian", "__pycache__")


def _walk(docs_dir):
    for root, dirs, files in os.walk(docs_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            if name.endswith(".md"):
                yield os.path.join(root, name)


def _outside_code(text):
    inside = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            inside = not inside
            continue
        if not inside:
            yield line


def _targets(line):
    for _, angled, plain, _ in LINK_RE.findall(line):
        target = (angled or plain).strip()
        if not target or target.startswith(SKIP_PREFIXES):
            continue
        yield target


def _resolves(root, target, planned=None):
    path = Path(root, unquote(target.split("#", 1)[0])).resolve()
    return path in (planned or {}) or path.exists() or any(p.is_relative_to(path) for p in (planned or {}))


def check(docs_dir, planned=None):
    broken = []
    planned = {Path(path).resolve(): text for path, text in (planned or {}).items()}
    paths = set(Path(path).resolve() for path in _walk(docs_dir))
    paths.update(path for path in planned if path.suffix == ".md")
    for path in sorted(paths):
        root = os.path.dirname(path)
        text = planned[path] if path in planned else path.read_text(encoding="utf-8-sig")
        for line in _outside_code(text):
            for target in _targets(CODESPAN_RE.sub('', line)):
                if not _resolves(root, target, planned):
                    broken.append((os.path.relpath(path, docs_dir), target))
    return broken


def _basename_map(docs_dir):
    index = {}
    for path in _walk(docs_dir):
        index.setdefault(os.path.basename(path).lower(), []).append(path)
    return index


def fix(docs_dir):
    index = _basename_map(docs_dir)
    fixed, unresolved = [], []

    for path in _walk(docs_dir):
        root = os.path.dirname(path)
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
        original, inside = text, False
        out = []
        for line in text.splitlines(keepends=True):
            if FENCE_RE.match(line):
                inside = not inside
            if inside:
                out.append(line)
                continue
            out.append(_fix_line(line, root, docs_dir, index, path, fixed, unresolved))
        text = "".join(out)
        if text != original:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    return fixed, unresolved


def _fix_line(line, root, docs_dir, index, path, fixed, unresolved):
    spans = [m.span() for m in CODESPAN_RE.finditer(line)]

    def replace(match):
        if any(a <= match.start() < b for a, b in spans):
            return match.group(0)
        head, angled, plain, tail = match.groups()
        target = (angled or plain).strip()
        if not target or target.startswith(SKIP_PREFIXES) or _resolves(root, target):
            return match.group(0)

        file_part, _, anchor = target.partition("#")
        candidates = index.get(os.path.basename(file_part).lower(), [])
        if len(candidates) != 1:
            unresolved.append((os.path.relpath(path, docs_dir), target))
            return match.group(0)

        new = os.path.relpath(candidates[0], root).replace(os.sep, "/")
        if anchor:
            new += f"#{anchor}"
        if re.search(r"[ ()]", new):
            new = f"<{new}>"
        fixed.append((os.path.relpath(path, docs_dir), target, new))
        return f"{head}{new}{tail}"

    return LINK_RE.sub(replace, line)
