import os
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "bin", "obj", "Library", "Temp",
             "Generated", "__pycache__"}


def scan(docs, repo_root, cfg):
    referenced = {path for doc in docs for path in doc["auto"]["code"]}
    modules = []
    for entry in (cfg.get("coverage") or {}).get("code", []):
        base = Path(repo_root, "Docs", entry["root"]).resolve()
        if not base.is_dir():
            raise ValueError(f"Не найден coverage root: {entry['root']}")
        for name in entry.get("only") or sorted(p.name for p in base.iterdir() if p.is_dir()):
            folder = base / name
            if name in SKIP_DIRS or not folder.is_dir():
                continue
            files = []
            for root, dirs, names in os.walk(folder):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                files += [Path(root, n) for n in names if Path(n).suffix in {".cs", ".py", ".js", ".ts", ".tsx", ".cpp", ".h", ".go", ".rs"}]
            if len(files) < (cfg.get("coverage") or {}).get("min_files", 1):
                continue
            rel = folder.relative_to(repo_root).as_posix()
            covered = any(path == rel or path.startswith(rel + "/") for path in referenced)
            modules.append((rel, len(files), covered))
    return modules


def render(docs, modules, out_dir, link_fn):
    lines = ["# Покрытие документацией", "", "> Сгенерировано `_brain/build.py`; руками не править.", "",
             "Явные `code:` и распознанные пути в документах связывают описание с кодом.",
             "Наличие ссылки не доказывает полноту описания.", "",
             "| Путь кода от корня проекта | Документы |", "|---|---|"]
    mapping = {}
    for doc in docs:
        for path in doc["auto"]["code"]:
            mapping.setdefault(path, []).append(doc)
    for path, owners in sorted(mapping.items()):
        refs = ", ".join(f"[{doc['meta']['title']}]({link_fn(out_dir, doc['path'])})" for doc in owners)
        lines.append(f"| `{path}` | {refs} |")
    if not mapping:
        lines += ["", "Пути кода ещё не зарегистрированы."]
    lines += ["", "## Модули в настроенных корнях", "",
              "| Модуль | Файлов исходников | Упомянут в документации |", "|---|---:|---|"]
    for path, count, covered in modules:
        lines.append(f"| `{path}` | {count} | {'да' if covered else 'нет'} |")
    return "\n".join(lines) + "\n"
