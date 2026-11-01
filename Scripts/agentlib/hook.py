import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .common import brain, load, run


def signature(root):
    import yaml
    root = Path(root).resolve()
    cfg = yaml.safe_load((root / "Docs/_brain/brain.yaml").read_text(encoding="utf-8"))
    paths = set((root / "Docs").rglob("*.md"))
    paths.update((root / "Docs/_brain").rglob("*.py"))
    paths.update((root / "Scripts").rglob("*.py"))
    paths.update([root / "Docs/_brain/brain.yaml", root / ".agent/project.json",
                  root / ".claude/hooks/sync-docs.py", root / "Docs/_brain/index/symbols.tsv"])
    roots = (cfg.get("symbols_index") or {}).get("roots", [])
    roots += [entry["root"] for entry in (cfg.get("coverage") or {}).get("code", [])]
    for relative in roots:
        base = (root / "Docs" / relative).resolve()
        if not base.is_relative_to(root):
            raise ValueError("Code root outside checkout")
        for directory, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in {".git", "Library", "Temp", "node_modules", ".venv", "bin", "obj", "__pycache__"}]
            paths.update(Path(directory) / name for name in files)
    module = brain(root)
    for document in module.collect(cfg):
        for path in document["auto"]["code"]:
            base = (root / path).resolve()
            if not base.is_relative_to(root):
                raise ValueError("Document code path outside checkout")
            paths.update(base.rglob("*") if base.is_dir() else [base])
    digest = hashlib.sha256()
    for path in sorted(paths):
        if not path.is_relative_to(root) or "__pycache__" in path.parts:
            continue
        stat = path.stat() if path.exists() else None
        digest.update(f"{path.relative_to(root).as_posix()}:{stat.st_mtime_ns if stat else -1}:{stat.st_size if stat else -1}\n".encode("utf-8"))
    return digest.hexdigest()


def cache_path(root):
    key = hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "coding-agent-checks" / key / "hook.json"


def check(root, payload):
    config = load(root).get("hook", {})
    if config.get("mode", "check") == "off":
        return None
    cache = cache_path(root)
    fingerprint = signature(root) if config.get("cache", True) else None
    if fingerprint and cache.is_file():
        try:
            previous = json.loads(cache.read_text(encoding="utf-8"))
            if previous.get("signature") == fingerprint and previous.get("ok") is True:
                return None
        except (OSError, ValueError):
            pass
    try:
        result = run(root, ["{python}", "-B", "Docs/_brain/build.py", "--check"], timeout=config.get("timeout_seconds", 30))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return feedback(f"Не удалось выполнить проверку, файлы не изменены: {error}", config, payload)
    if result.returncode == 0:
        if fingerprint:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump({"signature": fingerprint, "ok": True}, handle)
                temporary.replace(cache)
            except OSError:
                pass
        return None
    detail = (result.stdout + result.stderr).strip()[-3000:]
    message = "Документация требует внимания; файлы не изменены. " + detail
    return feedback(message, config, payload)


def feedback(message, config, payload):
    if config.get("enforce", False) and not payload.get("stop_hook_active", False):
        return {"decision": "block", "reason": message + " Для разрешённого изменения документации выполните python Scripts/agent.py sync."}
    return {"systemMessage": message}
