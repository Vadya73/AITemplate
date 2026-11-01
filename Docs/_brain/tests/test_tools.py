import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

from test_brain import Fixture, SOURCE

sys.path.insert(0, str(SOURCE / "Scripts"))
from agentlib.common import brain
from agentlib.install import apply, plan


class ToolTests(Fixture):
    def project_config(self, update):
        path = self.root / ".agent/project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        update(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def refresh(self, version):
        if not (self.root / "Scripts/refresh_manifest.py").is_file():
            self.skipTest("Release commands belong to the source template")
        self.run_python("Scripts/refresh_manifest.py", "--version", version)

    def test_static_outputs_ignore_clock_and_git_state(self):
        module = brain(self.root)
        docs = module.collect(module.config())
        with patch("datetime.date") as clock:
            clock.today.return_value = date(2026, 11, 1)
            first = module.outputs(module.config(), docs)
            clock.today.return_value = date(2026, 11, 2)
            second = module.outputs(module.config(), docs)
        self.assertEqual(first, second)

    def test_attestation_detects_same_day_edit_and_normalizes_eol(self):
        (self.root / "src").mkdir()
        path = self.root / "src/example.cs"
        path.write_bytes(b"class Example {}\r\n")
        self.add_doc("example.md", "# Example\n", {"domain": "Project", "hint": "fixture"})
        doc = self.root / "Docs/example.md"
        doc.write_text("---\ncode: [src/example.cs]\n---\n\n# Example\n", encoding="utf-8")
        self.run_python("Scripts/agent.py", "attest", "Docs/example.md", "--reviewed")
        module = brain(self.root)
        old = module.fingerprints.code_hash(self.root, "src/example.cs")
        path.write_bytes(b"class Example {}\n")
        self.assertEqual(old, module.fingerprints.code_hash(self.root, "src/example.cs"))
        self.build("--check")
        path.write_bytes(b"class Changed {}\n")
        self.build("--check", expected=1)
        self.assertIn("Содержимое кода изменилось", self.run_python("Scripts/agent.py", "status"))

    def test_doctor_reports_unconfigured_project_and_missing_product_checks(self):
        marker = self.root / "template.json"
        if marker.exists():
            marker.unlink()
        self.build()
        before = self.snapshot()
        rows = json.loads(self.run_python("Scripts/agent.py", "doctor", "--json"))
        self.assertTrue(any(row["status"] == "warning" for row in rows))
        self.run_python("Scripts/agent.py", "doctor", "--strict", expected=1)
        self.assertIn("INCOMPLETE", self.run_python("Scripts/agent.py", "verify", "fast", expected=2))
        self.assertEqual(before, self.snapshot())

    def test_verify_runs_real_argv_and_propagates_failure(self):
        marker = self.root / "template.json"
        if marker.exists():
            marker.unlink()
        self.build()
        self.project_config(lambda cfg: cfg["verification"].update(fast=[{"name": "Fixture", "argv": ["{python}", "-c", "raise SystemExit(7)"]}]))
        self.assertIn("FAIL Fixture", self.run_python("Scripts/agent.py", "verify", "fast", expected=1))
        self.project_config(lambda cfg: cfg["verification"].update(fast=[{"name": "Fixture", "argv": ["{python}", "-c", "print('actual-check-ran')"]}]))
        self.assertIn("actual-check-ran", self.run_python("Scripts/agent.py", "verify", "fast"))

    def test_verify_rejects_external_working_directory(self):
        marker = self.root / "template.json"
        if marker.exists():
            marker.unlink()
        self.build()
        self.project_config(lambda cfg: cfg["verification"].update(fast=[{"name": "Bad cwd", "argv": ["{python}", "-c", "pass"], "cwd": ".."}]))
        self.assertIn("Рабочий каталог вне проекта", self.run_python("Scripts/agent.py", "verify", "fast", expected=1))

    def test_hook_enforcement_and_loop_guard_do_not_mutate_project(self):
        self.build()
        self.project_config(lambda cfg: cfg["hook"].update(enforce=True, cache=False))
        self.cfg(lambda cfg: cfg.update(title="Needs sync"))
        before = self.snapshot()
        payload = {"cwd": str(self.root), "stop_hook_active": False}
        result = json.loads(self.run_python(".claude/hooks/sync-docs.py", input=json.dumps(payload)))
        self.assertEqual(result["decision"], "block")
        payload["stop_hook_active"] = True
        result = json.loads(self.run_python(".claude/hooks/sync-docs.py", input=json.dumps(payload)))
        self.assertIn("systemMessage", result)
        self.assertEqual(before, self.snapshot())

    def test_hook_success_cache_avoids_second_scan_and_invalidates_on_code(self):
        (self.root / "src").mkdir()
        code = self.root / "src/A.cs"
        code.write_text("class A {}", encoding="utf-8")
        self.cfg(lambda cfg: cfg.update(symbols_index={"roots": ["../src"]}))
        self.build()
        from agentlib import hook
        cache = Path(self.temp.name) / "external-cache/hook.json"
        with patch.object(hook, "cache_path", return_value=cache), patch.object(hook, "run", wraps=hook.run) as runner:
            self.assertIsNone(hook.check(self.root, {}))
            self.assertIsNone(hook.check(self.root, {}))
            self.assertEqual(runner.call_count, 1)
            code.write_text("class ChangedA {}", encoding="utf-8")
            self.assertIsNotNone(hook.check(self.root, {}))
            self.assertEqual(runner.call_count, 2)

    def test_hook_timeout_is_not_reported_as_success(self):
        self.build()
        self.project_config(lambda cfg: cfg["hook"].update(enforce=True, cache=False))
        from agentlib import hook
        with patch.object(hook, "run", side_effect=subprocess.TimeoutExpired("check", 1)):
            result = hook.check(self.root, {})
        self.assertEqual(result["decision"], "block")
        self.assertIn("Не удалось", result["reason"])

    def test_update_preserves_seeds_and_detects_simultaneous_edits(self):
        self.refresh("2.0.0")
        target = Path(self.temp.name) / "target"
        target.mkdir()
        apply(plan(self.root, target))
        memory = target / "Docs/Memory/HANDOFF.md"
        memory.write_text("My ongoing task", encoding="utf-8")
        managed = self.root / "Docs/agent-rules/WORKFLOW.md"
        managed.write_text(managed.read_text(encoding="utf-8") + "\nNew shared convention.\n", encoding="utf-8")
        self.refresh("2.1.0")
        planned = plan(self.root, target, True)
        self.assertFalse(planned["conflicts"])
        apply(planned)
        self.assertEqual(memory.read_text(encoding="utf-8"), "My ongoing task")
        self.assertIn("New shared convention", (target / "Docs/agent-rules/WORKFLOW.md").read_text(encoding="utf-8"))
        (target / "AGENTS.md").write_text("Local rules", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("Upstream rules", encoding="utf-8")
        self.refresh("2.2.0")
        snapshot = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
        conflict = plan(self.root, target, True)
        self.assertTrue(conflict["conflicts"])
        with self.assertRaises(ValueError):
            apply(conflict)
        self.assertEqual(snapshot, {p: p.read_bytes() for p in target.rglob("*") if p.is_file()})
        apply(plan(self.root, target, True, ["AGENTS.md"]))
        self.assertEqual((target / "AGENTS.md").read_text(encoding="utf-8"), "Local rules")

    def test_update_rejects_user_edit_after_plan(self):
        self.refresh("2.0.0")
        target = Path(self.temp.name) / "target"
        target.mkdir()
        apply(plan(self.root, target))
        (self.root / "AGENTS.md").write_text("New upstream", encoding="utf-8")
        self.refresh("2.1.0")
        planned = plan(self.root, target, True)
        (target / "AGENTS.md").write_text("User edit after plan", encoding="utf-8")
        with self.assertRaises(ValueError):
            apply(planned)
        self.assertEqual((target / "AGENTS.md").read_text(encoding="utf-8"), "User edit after plan")

    def test_evaluation_grading_requires_artifacts_scope_and_independent_review(self):
        self.refresh("2.0.0")
        from agentlib.evals import prepare, score
        output = Path(self.temp.name) / "evaluation"
        self.assertEqual(prepare(self.root, output, "baseline", "fixture-model"), 6)
        case = output / "lookup"
        self.assertFalse(score(self.root, case)["passed"])
        (case / "answer.md").write_text("WIN_THRESHOLD in src/settings.py", encoding="utf-8")
        self.assertIsNone(score(self.root, case)["manual_review"])
        (case / "review.json").write_text(json.dumps({"reviewer": "test-independent", "passed": True, "evidence": "Checked actual symbol and trace"}), encoding="utf-8")
        self.assertTrue(score(self.root, case)["passed"])
        (case / "workspace/USER_NOTES.md").write_text("Unwanted edit", encoding="utf-8")
        report = score(self.root, case)
        self.assertFalse(report["passed"])
        self.assertIn("USER_NOTES.md", report["unwanted_changes"])
