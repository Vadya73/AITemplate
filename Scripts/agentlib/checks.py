import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .common import brain, is_template, load, run


def doctor(root, strict=False):
    root = Path(root)
    rows = [{"name": "Python >= 3.10", "status": "ok" if sys.version_info >= (3, 10) else "error"},
            {"name": "PyYAML", "status": "ok" if importlib.util.find_spec("yaml") else "error"},
            {"name": "Git executable (optional)", "status": "ok" if shutil.which("git") else "warning"}]
    try:
        config = load(root)
        rows.append({"name": "project.json schema", "status": "ok"})
        source_template = is_template(root)
        configured = config.get("project", {}).get("configured") is True and bool(config.get("project", {}).get("name"))
        rows.append({"name": "Project adaptation", "status": "ok" if configured or source_template else "warning",
                     "detail": "Source template" if source_template else "Fill project.name/configured and passport"})
        commands = config.get("verification", {})
        rows.append({"name": "Product checks", "status": "ok" if source_template or commands.get("fast") or commands.get("full") else "warning",
                     "detail": "No product verification is implied by documentation checks"})
        module = brain(root)
        module.collect(module.config())
        rows.append({"name": "Brain configuration and metadata", "status": "ok"})
    except (OSError, ValueError, KeyError, TypeError) as error:
        rows.append({"name": "Configuration", "status": "error", "detail": str(error)})
    for path in ("AGENTS.md", "CLAUDE.md", ".claude/hooks/sync-docs.py"):
        rows.append({"name": path, "status": "ok" if (root / path).is_file() else "error"})
    if (root / "ProjectSettings/ProjectVersion.txt").is_file():
        rows.append({"name": "Unity Editor connection", "status": "info", "detail": "Not contacted by doctor; use unity-validation skill for Editor tasks"})
    failed = any(row["status"] == "error" or strict and row["status"] == "warning" for row in rows)
    return rows, int(failed)


def validate_assets(root):
    errors = []
    paths = list((Path(root) / ".agent").rglob("*.json"))
    paths += list((Path(root) / "Scripts").rglob("*.json"))
    paths += [Path(root) / ".claude/settings.json"]
    for path in paths:
        if path.is_file() and not path.name.endswith(".local.json") and "reports" not in path.parts:
            json.loads(path.read_text(encoding="utf-8-sig"))
    module = brain(root)
    errors += [f"{source} -> {target}" for source, target in module.links.check(str(Path(root) / "Docs"))]
    for folder in (".agents/skills", ".claude/skills"):
        for path in sorted((Path(root) / folder).glob("*/SKILL.md")):
            meta, body = module.frontmatter.split(path.read_text(encoding="utf-8"))
            if meta.get("name") != path.parent.name or not isinstance(meta.get("description"), str) or not meta["description"].strip():
                errors.append(f"Invalid skill metadata: {path}")
            for line in module.links._outside_code(body):
                for target in module.links._targets(module.links.CODESPAN_RE.sub("", line)):
                    if not module.links._resolves(str(path.parent), target):
                        errors.append(f"Broken skill reference: {path} -> {target}")
    return errors


def verify(root, profile):
    config = load(root)
    steps = [{"name": "Documentation", "argv": ["{python}", "-B", "Docs/_brain/build.py", "--check"]}]
    if is_template(root):
        steps.append({"name": "Source manifest", "argv": ["{python}", "-B", "Scripts/refresh_manifest.py", "--check"]})
    commands = config.get("verification", {})
    steps += commands.get("fast", [])
    if profile == "full":
        steps += commands.get("full", [])
        if is_template(root) or commands.get("tooling_tests", False):
            steps.append({"name": "Template tooling tests", "argv": ["{python}", "-B", "-m", "unittest", "discover", "-s", "Docs/_brain/tests", "-q"]})
    errors = validate_assets(root)
    for error in errors:
        print(f"FAIL {error}")
    failed = bool(errors)
    for step in steps:
        try:
            result = run(root, step["argv"], timeout=step.get("timeout_seconds", commands.get("timeout_seconds", 120)), cwd=step.get("cwd", "."))
            print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {step['name']}", flush=True)
            print((result.stdout + result.stderr).strip(), flush=True)
            failed |= result.returncode != 0
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"FAIL {step['name']}: {error}")
            failed = True
    selected = commands.get("fast", []) + (commands.get("full", []) if profile == "full" else [])
    if not is_template(root) and not selected:
        print("INCOMPLETE: Product checks are not configured; only template infrastructure was checked.")
        return 2 if not failed else 1
    return int(failed)
