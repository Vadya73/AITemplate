import json
import os
import subprocess
import sys
from pathlib import Path


def is_template(root):
    path = Path(root) / "template.json"
    if not path.is_file() or (Path(root) / ".agent/template-lock.json").exists():
        return False
    return json.loads(path.read_text(encoding="utf-8")).get("kind") == "coding-agent-template"


def load(root):
    config = json.loads((Path(root) / ".agent/project.json").read_text(encoding="utf-8-sig"))
    if config.get("schema_version") != 1:
        raise ValueError("Неподдерживаемая schema_version в .agent/project.json")
    if not isinstance(config.get("verification", {}).get("tooling_tests", False), bool):
        raise ValueError("verification.tooling_tests: требуется bool")
    for group in ("fast", "full"):
        for step in config.get("verification", {}).get(group, []):
            if not isinstance(step.get("argv"), list) or not step["argv"] or not all(isinstance(x, str) for x in step["argv"]):
                raise ValueError("Проверка требует непустой массив строк argv")
            if not isinstance(step.get("name"), str):
                raise ValueError("Проверка требует имя name")
    hook = config.get("hook", {})
    if hook.get("mode", "check") not in ("off", "check"):
        raise ValueError("hook.mode: поддерживаются off и check; sync запускается явно")
    for field in ("enforce", "cache"):
        if field in hook and not isinstance(hook[field], bool):
            raise ValueError(f"hook.{field}: требуется bool")
    for group in ("verification", "hook"):
        timeout = config.get(group, {}).get("timeout_seconds", 30)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 1800:
            raise ValueError(f"{group}.timeout_seconds: ожидается число от 0 до 1800")
    return config


def run(root, argv, timeout=120, cwd="."):
    root = Path(root).resolve()
    working = (root / cwd).resolve()
    if not working.is_dir() or not working.is_relative_to(root):
        raise ValueError(f"Рабочий каталог вне проекта или не существует: {cwd}")
    arguments = [part.replace("{python}", sys.executable).replace("{root}", str(root)) for part in argv]
    return subprocess.run(arguments, cwd=working, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, shell=False,
                          env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def brain(root):
    import importlib.util
    path = Path(root) / "Docs/_brain/build.py"
    spec = importlib.util.spec_from_file_location("project_brain", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
