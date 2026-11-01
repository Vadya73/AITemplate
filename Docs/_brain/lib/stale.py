import os
import re
import subprocess
from pathlib import Path


def _git(repo_root, args):
    try:
        result = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=repo_root,
                                capture_output=True, text=True, encoding="utf-8", timeout=45,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def scan(docs, repo_root, out_dir, link_fn):
    root = _git(repo_root, ["rev-parse", "--show-toplevel"])
    valid_git = bool(root and Path(root.strip()).resolve() == Path(repo_root).resolve())
    paths = {path for doc in docs for path in doc["auto"]["code"]}
    history = _git(repo_root, ["log", "--format=DATE:%cs", "--name-only", "--", *sorted(paths)]) if valid_git and paths else ""
    dates, current = {}, None
    for line in (history or "").splitlines():
        if re.fullmatch(r"DATE:\d{4}-\d{2}-\d{2}", line):
            current = line[5:]
        elif line.strip() and current:
            dates.setdefault(line.strip().replace("\\", "/"), current)
    dirty = set()
    if valid_git:
        for args in (["diff", "--name-only", "-z"], ["diff", "--cached", "--name-only", "-z"],
                     ["ls-files", "--others", "--exclude-standard", "-z"]):
            dirty.update(path.replace("\\", "/") for path in (_git(repo_root, args) or "").split("\0") if path)
    found, notes = {}, []
    if not valid_git or history is None:
        notes.append("Git-история этого корня недоступна: актуальность по коммитам не установлена.")
    for doc in docs:
        verified = doc["meta"].get("verified")
        refs = doc["auto"]["code"]
        missing = [p for p in refs if not os.path.exists(os.path.join(repo_root, p))]
        changed = [p for p in refs if p in dirty]
        newest = max((dates[p], p) for p in refs if p in dates) if any(p in dates for p in refs) else None
        reason, stamp, file = None, "—", "—"
        if missing:
            reason, file = "Не найден путь кода", missing[0]
        elif changed:
            reason, file = "Есть незакоммиченные изменения: нужна сверка", changed[0]
        elif not verified:
            reason = "Нет даты фактической сверки"
        elif newest and newest[0] > str(verified):
            reason, stamp, file = "Код закоммичен позже даты сверки", *newest
        elif refs and any(p not in dates for p in refs):
            reason = "Недостаточно Git-истории для проверки путей"
        if reason:
            found[doc["id"]] = {"title": doc["meta"]["title"], "link": link_fn(out_dir, doc["path"]),
                                 "verified": verified or "—", "changed": stamp, "file": file, "reason": reason}
    return found, notes
