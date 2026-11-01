import hashlib
from pathlib import Path

SKIP = {".git", ".venv", "__pycache__", "Library", "Temp", "node_modules", "bin", "obj"}


def code_hash(repo_root, relative):
    root = Path(repo_root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Путь вне проекта: {relative}")
    if not path.exists():
        return None
    digest = hashlib.sha256()
    candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    for candidate in candidates:
        if any(part in SKIP for part in candidate.relative_to(root).parts):
            continue
        if not candidate.resolve().is_relative_to(root):
            raise ValueError(f"Ссылка вне проекта: {candidate}")
        data = candidate.read_bytes().replace(b"\r\n", b"\n")
        name = candidate.relative_to(path).as_posix() if path.is_dir() else ""
        digest.update(name.encode("utf-8") + b"\0" + len(data).to_bytes(8, "big") + data)
    return "sha256:" + digest.hexdigest()


def scan(docs, repo_root):
    hashes, report = {}, {}
    for doc in docs:
        baseline = doc["meta"].get("verified_code") or {}
        if not isinstance(baseline, dict):
            raise ValueError(f"verified_code должен быть mapping: {doc['rel']}")
        reasons = []
        if not doc["meta"].get("verified"):
            reasons.append(("—", "Нет даты фактической сверки"))
        for relative in doc["auto"]["code"]:
            if relative not in hashes:
                hashes[relative] = code_hash(repo_root, relative)
            current = hashes[relative]
            if current is None:
                reasons.append((relative, "Не найден путь кода"))
            elif relative not in baseline:
                reasons.append((relative, "Нет отпечатка сверенного кода"))
            elif baseline[relative] != current:
                reasons.append((relative, "Содержимое кода изменилось после сверки"))
        if reasons:
            report[doc["id"]] = {"title": doc["meta"]["title"], "path": doc["path"],
                                 "verified": doc["meta"].get("verified") or "—", "reasons": reasons}
    return report
