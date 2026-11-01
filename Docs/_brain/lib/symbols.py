import os
import re

TYPE_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*(?:(?:public|private|protected|internal|static|sealed|abstract|"
    r"partial|readonly|unsafe)\s+)*(class|struct|interface|enum|record)\s+(\w+)")
METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|async|override|virtual|sealed|"
    r"extern|unsafe|new|partial)\s+)+[\w<>\[\],.?]+\s+(\w+)\s*(?:<[^>(]*>)?\s*\(")
PROP_RE = re.compile(
    r"^\s*(?:(?:public|protected|internal)\s+)(?:(?:static|override|virtual|new)\s+)*"
    r"[\w<>\[\],.?]+\s+([A-Z]\w+)\s*(?:=>|\{\s*get)")
ENUM_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:=\s*[^,]+?)?,?\s*$")
CONST_RE = re.compile(
    r"^\s*(?:public|internal|protected)\s+(?:static\s+)?(?:readonly\s+|const\s+)"
    r"[\w<>\[\],.?]+\s+([A-Z]\w+)\s*=")

NOISE = {"Start", "Update", "Awake", "OnEnable", "OnDisable", "OnDestroy", "FixedUpdate",
         "LateUpdate", "OnApplicationPause", "OnApplicationFocus", "OnGUI", "OnValidate",
         "ToString", "Equals", "GetHashCode", "Dispose", "OnPointerClick", "OnPointerEnter",
         "OnPointerExit", "OnBeforeSerialize", "OnAfterDeserialize", "if", "for", "foreach",
         "while", "switch", "catch", "using", "lock", "return", "get", "set", "new"}
SKIP_DIRS = {"bin", "obj", "Generated", ".git", "Library", "Temp", "node_modules", ".venv", "__pycache__"}


def _depth_delta(line):
    clean = re.sub(r'"[^"]*"|\'[^\']*\'|//.*$', "", line)
    return clean.count("{") - clean.count("}")


def _scan_file(path, rel):
    rows, stack, depth, block, pending = [], [], 0, False, None
    try:
        with open(path, encoding="utf-8-sig", errors="ignore") as handle:
            text = handle.read()
    except OSError:
        return rows
    for no, line in enumerate(text.splitlines(), 1):
        if block:
            block = "*/" not in line
            continue
        if line.lstrip().startswith("//"):
            continue
        open_at, line_cmt = line.find("/*"), line.find("//")
        if open_at != -1 and (line_cmt == -1 or line_cmt > open_at) and "*/" not in line[open_at:]:
            block = True
            continue
        while stack and stack[-1][1] >= depth:
            stack.pop()
        owner = stack[-1][0] if stack else ""
        hit = TYPE_RE.match(line)
        if hit:
            rows.append((hit.group(2), hit.group(1), owner, rel, no))
            pending = (hit.group(2), hit.group(1))
        elif stack and stack[-1][2] == "enum":
            member = ENUM_RE.match(line.split("//")[0])
            if member and member.group(1) not in NOISE:
                rows.append((member.group(1), "enumval", owner, rel, no))
        else:
            for regex, kind in ((METHOD_RE, "method"), (PROP_RE, "prop"), (CONST_RE, "const")):
                found = regex.match(line)
                if found and found.group(1) not in NOISE and len(found.group(1)) > 2:
                    rows.append((found.group(1), kind, owner, rel, no))
                    break
        delta = _depth_delta(line)
        depth += delta
        if pending and delta > 0:
            stack.append((pending[0], depth - 1, pending[1]))
            pending = None
    return rows


def scan(docs_dir, roots):
    repo_root = os.path.dirname(docs_dir)
    rows = []
    for entry in roots:
        base = os.path.normpath(os.path.join(docs_dir, entry))
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if not name.endswith(".cs") or name.endswith(".generated.cs"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
                rows += _scan_file(full, rel)
    return rows


def render(rows):
    out = ["# Карта символов C#. Генерируется _brain/build.py — руками не править.",
           "# Эвристический индекс C#: rg -i \"SymbolName\" Docs/_brain/index/symbols.tsv; перепроверяй исходник.",
           "# symbol\tkind\towner\tpath\tline"]
    seen = set()
    for row in sorted(rows, key=lambda r: (r[0].lower(), r[3], r[4])):
        key = (row[0], row[3], row[4])
        if key in seen:
            continue
        seen.add(key)
        out.append("\t".join(str(part) for part in row))
    return "\n".join(out) + "\n"
