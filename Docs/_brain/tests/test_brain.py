import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SOURCE = Path(__file__).resolve().parents[3]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-template-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Проект с пробелами"
        self.root.mkdir()
        for name in ("Docs", ".claude", ".obsidian", "Scripts", ".agent", ".agents"):
            if (SOURCE / name).is_dir():
                shutil.copytree(SOURCE / name, self.root / name,
                                ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("AGENTS.md", "CLAUDE.md", "README.md", "template.json", ".gitignore"):
            if (SOURCE / name).is_file():
                shutil.copyfile(SOURCE / name, self.root / name)

    def run_python(self, *args, input=None, expected=0):
        result = subprocess.run([sys.executable, "-B", *args], cwd=self.root, input=input,
                                capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def build(self, *args, expected=0):
        return self.run_python("Docs/_brain/build.py", *args, expected=expected)

    def cfg(self, change):
        path = self.root / "Docs/_brain/brain.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}

    def add_doc(self, rel, text, entry=None):
        path = self.root / "Docs" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.cfg(lambda cfg: cfg["docs"].update({rel: entry or {"domain": "Project", "hint": "fixture"}}))


class BrainTests(Fixture):
    def test_rebuild_is_idempotent(self):
        self.build()
        before = self.snapshot()
        self.assertIn("updated: 0", self.build())
        self.build("--check")
        self.assertEqual(before, self.snapshot())

    def test_check_is_read_only_and_detects_outdated(self):
        self.build()
        path = self.root / "Docs/PROJECT.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n## Новый раздел\n", encoding="utf-8")
        before = self.snapshot()
        self.assertIn("outdated:", self.build("--check", expected=1))
        self.assertEqual(before, self.snapshot())

    def test_broken_link_fails_before_writing(self):
        self.add_doc("broken.md", "# Сломанная ссылка\n\n[нет](missing-file.md)\n")
        before = self.snapshot()
        self.assertIn("broken link:", self.build(expected=1))
        self.assertEqual(before, self.snapshot())

    def test_explicit_metadata_and_unknown_fields_are_preserved(self):
        self.add_doc("feature.md", "---\nstatus: partial\nverified:\ntables: [inventory_entries]\nconfig_keys: [Feature.IsEnabled]\nresources: [Credits]\nprotocol_keys: [7]\ncustom:\n  owner_team: Example\n---\n\n# Feature\n")
        self.build()
        text = (self.root / "Docs/feature.md").read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1])
        self.assertIsNone(meta["verified"])
        self.assertEqual(meta["custom"], {"owner_team": "Example"})
        self.assertEqual(meta["tables"], ["inventory_entries"])
        for name, word in (("DbTables", "inventory_entries"), ("ConfigKeys", "Feature.IsEnabled"), ("Resources", "Credits"), ("ProtocolKeys", "`7`")):
            self.assertIn(word, (self.root / f"Docs/_brain/registries/{name}.md").read_text(encoding="utf-8"))

    def test_unique_ids_for_same_basename_and_parent_links(self):
        self.add_doc("A/README.md", "# Parent\n\n[Child](../B/README.md)\n")
        self.add_doc("B/README.md", "# Child\n", {"domain": "Project", "hint": "child", "parent": "a-readme"})
        self.build()
        text = (self.root / "Docs/B/README.md").read_text(encoding="utf-8")
        self.assertIn("id: b-readme", text)
        self.assertIn("parent: a-readme", text)
        self.build("--check")

    def test_invalid_config_fails_without_writes(self):
        self.cfg(lambda cfg: cfg["symbols_index"].update(roots=["../../outside"]))
        before = self.snapshot()
        self.assertIn("Неверный symbols root", self.build(expected=1))
        self.assertEqual(before, self.snapshot())

    def test_missing_registered_document_fails(self):
        self.cfg(lambda cfg: cfg["docs"].update({"not-there.md": {"domain": "Project", "hint": "bad"}}))
        self.assertIn("Неверный путь документа", self.build(expected=1))

    def test_parent_cycle_is_rejected(self):
        self.add_doc("a.md", "# A\n\n[B](b.md)\n", {"domain": "Project", "hint": "a", "parent": "b"})
        self.add_doc("b.md", "# B\n\n[A](a.md)\n", {"domain": "Project", "hint": "b", "parent": "a"})
        self.assertIn("Цикл parent", self.build(expected=1))

    def test_csharp_symbols_and_coverage_use_configured_roots(self):
        path = self.root / "src/Feature/Editor/Widget.cs"
        path.parent.mkdir(parents=True)
        path.write_text("public class Widget\n{\n    public void Execute()\n    {\n    }\n}\n", encoding="utf-8")
        self.add_doc("widget.md", "---\nverified: 2024-01-01\ncode: [src/Feature/Editor/Widget.cs]\n---\n\n# Widget\n\n## Ключевые файлы\n\nОписание.\n")
        self.cfg(lambda cfg: cfg.update(symbols_index={"roots": ["../src"]}, coverage={"min_files": 1, "code": [{"root": "../src"}]}))
        self.build()
        self.assertIn("Widget\tclass", (self.root / "Docs/_brain/index/symbols.tsv").read_text(encoding="utf-8"))
        self.assertIn("src/Feature/Editor/Widget.cs", (self.root / "Docs/_brain/registries/Coverage.md").read_text(encoding="utf-8"))
        self.assertIn("| `src/Feature` | 1 | да |", (self.root / "Docs/_brain/registries/Coverage.md").read_text(encoding="utf-8"))

    def test_generated_line_ranges_match_actual_headings(self):
        self.build()
        index = (self.root / "Docs/INDEX.md").read_text(encoding="utf-8")
        document = (self.root / "Docs/PROJECT.md").read_text(encoding="utf-8").splitlines()
        line = document.index("## Инварианты и источники истины") + 1
        self.assertIn(f"`L{line}-", index)

    def test_git_stale_and_dirty_detection(self):
        if not shutil.which("git"):
            self.skipTest("Git unavailable")
        code = self.root / "src/Example.cs"
        code.parent.mkdir()
        code.write_text("class Example {}\n", encoding="utf-8")
        self.add_doc("example.md", "---\nverified: 2024-01-01\ncode: [src/Example.cs]\n---\n\n# Example\n")
        self.run_python("Scripts/agent.py", "attest", "Docs/example.md", "--reviewed")
        before_git = self.snapshot()
        for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Template Test", "-c", "user.email=template@example.invalid", "-c", "core.hooksPath=disabled-hooks", "commit", "-qm", "fixture"]):
            result = subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                                    env={**os.environ, "GIT_AUTHOR_DATE": "2024-01-02T12:00:00+00:00", "GIT_COMMITTER_DATE": "2024-01-02T12:00:00+00:00"},
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(result.returncode, 0, result.stderr)
        self.build()
        report = self.root / "Docs/_brain/registries/Stale.md"
        self.assertEqual(before_git, self.snapshot())
        code.write_text("class ChangedExample {}\n", encoding="utf-8")
        self.build()
        self.assertIn("Содержимое кода изменилось после сверки", report.read_text(encoding="utf-8"))
        self.assertIn("Есть незакоммиченные изменения", self.run_python("Scripts/agent.py", "status"))

    def test_hook_checks_active_checkout_without_writing(self):
        self.build()
        self.cfg(lambda cfg: cfg.update(title="Active checkout"))
        payload = json.dumps({"cwd": str(self.root / "Docs")})
        before = self.snapshot()
        output = self.run_python(".claude/hooks/sync-docs.py", input=payload)
        self.assertIn("файлы не изменены", json.loads(output)["systemMessage"])
        self.assertEqual(before, self.snapshot())
        self.build()
        self.assertEqual("", self.run_python(".claude/hooks/sync-docs.py", input=payload))

    def test_installer_dry_run_copy_and_conflict_protection(self):
        if not (SOURCE / "Scripts/install_template.py").is_file():
            self.skipTest("Installer belongs to the source template, not the destination project")
        target = Path(self.temp.name) / "Другой проект"
        target.mkdir()
        self.run_python("Scripts/install_template.py", str(target), "--dry-run")
        self.assertEqual([], list(target.iterdir()))
        (target / "AGENTS.md").write_text("Keep user instructions", encoding="utf-8")
        self.run_python("Scripts/install_template.py", str(target), expected=1)
        self.assertFalse((target / "Docs").exists())
        self.assertEqual("Keep user instructions", (target / "AGENTS.md").read_text(encoding="utf-8"))
        clean = Path(self.temp.name) / "Чистый проект"
        clean.mkdir()
        self.run_python("Scripts/install_template.py", str(clean))
        self.assertTrue((clean / ".claude/settings.json").is_file())
        self.assertFalse((clean / "README.md").exists())
        self.assertTrue((clean / "Scripts/agent.py").is_file())
        self.assertTrue((clean / ".agent/template-lock.json").is_file())
        result = subprocess.run([sys.executable, "-B", str(clean / "Docs/_brain/build.py")], cwd=clean,
                                capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={**os.environ, "PYTHONUTF8": "1"},
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        relocated = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "Docs/_brain/tests", "-q"],
                                   cwd=clean, capture_output=True, text=True, encoding="utf-8", timeout=60,
                                   env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(relocated.returncode, 0, relocated.stderr + relocated.stdout)


if __name__ == "__main__":
    unittest.main()
