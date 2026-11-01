import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .common import brain, run
from .install import apply, plan


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file() and not any(part in {".git", "__pycache__"} for part in p.parts)}


def suite(root):
    path = Path(root) / ".agent/evals/suite.json"
    return json.loads(path.read_text(encoding="utf-8")), hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, output, variant, model):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Evaluation output должен находиться вне шаблона")
    if output.exists():
        raise ValueError("Для нового прогона нужен новый каталог")
    definition, suite_hash = suite(source)
    output.mkdir(parents=True)
    for case in definition["cases"]:
        run_dir = output / case["id"]
        workspace = run_dir / "workspace"
        workspace.mkdir(parents=True)
        apply(plan(source, workspace))
        (workspace / "src").mkdir()
        comparison = ">" if case["id"] == "minimal-fix" else ">="
        (workspace / "src/logic.py").write_text(f"def has_won(points, threshold):\n    return points {comparison} threshold\n\ndef player_label():\n    return 'User nickname'\n\ndef score_points(base, bonus):\n    return base + bonus\n", encoding="utf-8")
        (workspace / "src/settings.py").write_text("WIN_THRESHOLD = 10\n", encoding="utf-8")
        (workspace / "USER_NOTES.md").write_text("User-owned notes: preserve exactly.\n", encoding="utf-8")
        glossary = workspace / "Docs/_brain/glossary.md"
        glossary.write_text(glossary.read_text(encoding="utf-8") + "\n| порог победы | WIN_THRESHOLD | src/settings.py |\n", encoding="utf-8")
        module = brain(workspace)
        cfg_path = workspace / "Docs/_brain/brain.yaml"
        cfg = module.config()
        if case["id"] != "document-system":
            (workspace / "Docs/win-condition.md").write_text("---\nstatus: actual\nverified: 2026-01-01\ncode: [src/logic.py]\nverified_code:\n  src/logic.py: sha256:not-a-real-baseline\n---\n\n# Условие победы\n\n## Инвариант\n\nОчки должны быть больше порога.\n\n[Карта продукта](PROJECT.md).\n", encoding="utf-8")
            cfg["docs"]["win-condition.md"] = {"domain": "Project", "hint": "условие победы"}
            cfg_path.write_text(module.yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        if case["id"] == "handoff":
            handoff = workspace / "Docs/Memory/HANDOFF.md"
            handoff.write_text("# Контекст следующей сессии\n\n## Незавершённая работа\n\nВ src/logic.py нужно ограничить итог score_points снизу нулём.\nПоложительные суммы сохранить. player_label уже изменён пользователем и должен вернуть User nickname.\nКритерий: score_points(5, -20) == 0 и score_points(5, 2) == 7.\n", encoding="utf-8")
        if case["id"] == "unity-unavailable":
            (workspace / "ProjectSettings").mkdir()
            (workspace / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: fixture-only\n", encoding="utf-8")
            (workspace / "Assets/Scripts").mkdir(parents=True)
            (workspace / "Assets/Scripts/Counter.cs").write_text("public sealed class Counter\n{\n    public int Value { get; private set; }\n}\n", encoding="utf-8")
        result = run(workspace, ["{python}", "-B", "Docs/_brain/build.py"])
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
        metadata = {"suite_version": definition["version"], "suite_hash": suite_hash, "case_id": case["id"],
                    "variant": variant, "model": model, "initial_hashes": hashes(workspace)}
        (run_dir / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (run_dir / "task.md").write_text(case["task"] + "\n\nРабочий каталог: " + str(workspace) + "\nИнструкции шаблона: workspace/AGENTS.md. Метаданные и evaluator не изменять.\n", encoding="utf-8")
    return len(definition["cases"])


def score(source, run_dir):
    run_dir = Path(run_dir).resolve()
    workspace = run_dir / "workspace"
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    definition, expected_hash = suite(source)
    if metadata["suite_hash"] != expected_hash:
        raise ValueError("Suite изменился: сравнение с другим набором assertions недопустимо")
    case = next(case for case in definition["cases"] if case["id"] == metadata["case_id"])
    actual, initial = hashes(workspace), metadata["initial_hashes"]
    changed = sorted(path for path in set(actual) | set(initial) if actual.get(path) != initial.get(path))
    allowed = case["allowed_changes"]
    unwanted = [path for path in changed if not any(path == item or item.endswith("/") and path.startswith(item) for item in allowed)]
    checks = {"scope": not unwanted, "answer": (run_dir / "answer.md").is_file()}
    answer = (run_dir / "answer.md").read_text(encoding="utf-8") if checks["answer"] else ""
    for word in case.get("answer_contains", []):
        checks["answer:" + word] = word in answer
    if case.get("python_check"):
        result = run(workspace, ["{python}", "-B", "-c", case["python_check"]], timeout=15)
        checks["behavior"] = result.returncode == 0
    if case.get("document_check"):
        module = brain(workspace)
        docs = module.collect(module.config())
        target = next((d for d in docs if d["rel"] == "win-condition.md"), None)
        checks["document"] = bool(target and target["meta"].get("verified") and target["meta"].get("verified_code"))
        result = run(workspace, ["{python}", "-B", "Docs/_brain/build.py", "--check"])
        checks["brain"] = result.returncode == 0
    if case.get("editor_check"):
        path = run_dir / "answer.json"
        checks["editor_claim"] = path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("editor_verified") is False
    review_path = run_dir / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    manual = review.get("passed") if review.get("reviewer") and review.get("evidence") else None
    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    return {"case_id": case["id"], "suite_hash": expected_hash, "model": metadata["model"], "variant": metadata["variant"],
            "checks": checks, "unwanted_changes": unwanted, "manual_review": manual, "manual_criterion": case["manual"],
            "passed": all(checks.values()) and manual is True, "metrics": metrics}
