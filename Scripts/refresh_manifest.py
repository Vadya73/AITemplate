"""Maintainer command: pin the curated template payload; never run in a project."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = {".agent/project.json", "Docs/agent-rules/PROJECT.md", "Docs/_brain/brain.yaml", "Docs/_brain/glossary.md",
         "Docs/PROJECT.md", "Docs/ARCHITECTURE.md", "Docs/Memory/DECISIONS.md", "Docs/Memory/HANDOFF.md",
         ".obsidian/app.json", ".obsidian/core-plugins.json", ".claude/settings.json"}
GENERATED = ("Docs/INDEX.md", "Docs/_brain/DATA.md", "Docs/_brain/registries/", "Docs/_brain/index/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.version is None:
        marker = ROOT / "template.json"
        if not marker.is_file():
            parser.error("Для первого выпуска нужен --version")
        args.version = json.loads(marker.read_text(encoding="utf-8"))["version"]
    if (ROOT / ".agent/template-lock.json").exists():
        parser.error("Installed projects cannot become a pristine template implicitly")
    paths = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]
    for folder in ("Docs", "Scripts", ".agents", ".claude", ".obsidian", ".agent"):
        paths += [p for p in (ROOT / folder).rglob("*") if p.is_file()]
    excluded = {"__pycache__", ".git", "settings.local.json", "workspace.json", "workspace-mobile.json"}
    files = {}
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        if any(part in excluded or part.endswith(".local.json") for part in path.relative_to(ROOT).parts):
            continue
        if relative.startswith(".agent/reports/") or relative in {"Scripts/install_template.py", "Scripts/refresh_manifest.py"}:
            continue
        seed = relative in SEEDS or any(relative == item or relative.startswith(item) for item in GENERATED)
        files[relative] = {"policy": "seed" if seed else "managed", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    data = {"schema_version": 1, "kind": "coding-agent-template", "template_id": "portable-agent-workspace", "version": args.version, "files": files}
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    target = ROOT / "template.json"
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            raise SystemExit("Manifest is outdated")
    else:
        target.write_text(content, encoding="utf-8")
    print(f"Manifest {args.version}: {len(files)} files")


if __name__ == "__main__":
    main()
