"""Project checks and explicit documentation operations. No shell command strings."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

from agentlib.common import brain, run


def attest(document):
    module = brain(ROOT)
    docs = module.collect(module.config())
    path = (ROOT / document).resolve()
    doc = next((doc for doc in docs if Path(doc["path"]) == path), None)
    if doc is None:
        raise ValueError("Документ должен быть зарегистрирован в brain.yaml")
    hashes = {relative: module.fingerprints.code_hash(ROOT, relative) for relative in doc["auto"]["code"]}
    if any(value is None for value in hashes.values()):
        raise ValueError("Нельзя подтвердить отсутствующий путь кода")
    meta = doc["meta"]
    meta.update(verified=date.today().isoformat(), verified_code=hashes, status="actual")
    path.write_bytes((module.frontmatter.dump(meta) + "\n" + doc["body"]).encode("utf-8"))
    result = run(ROOT, ["{python}", "-B", "Docs/_brain/build.py"])
    print(result.stdout + result.stderr)
    return result.returncode


def status():
    module = brain(ROOT)
    docs = module.collect(module.config())
    current, notes = module_status(module, docs)
    print(json.dumps({"documentation": module.fingerprints.scan(docs, ROOT), "git": current, "notes": notes},
                     ensure_ascii=False, indent=2))
    return 0


def module_status(module, docs):
    import importlib.util
    spec = importlib.util.spec_from_file_location("runtime_stale", ROOT / "Docs/_brain/lib/stale.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.scan(docs, str(ROOT), str(ROOT / "Docs/_brain/registries"), module.render.link)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Read-only environment and adaptation checks")
    doctor.add_argument("--strict", action="store_true")
    doctor.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify", help="Run configured shell-free checks")
    verify.add_argument("profile", choices=("fast", "full"))
    commands.add_parser("sync", help="Explicitly rebuild documentation; writes changed outputs")
    commands.add_parser("status", help="Read-only current Git and document diagnostics")
    review = commands.add_parser("attest", help="Record a real completed review, then sync")
    review.add_argument("document")
    review.add_argument("--reviewed", action="store_true", required=True, help="Confirm the text was actually checked against code")
    args = parser.parse_args()
    if args.command == "doctor":
        from agentlib.checks import doctor
        rows, code = doctor(ROOT, args.strict)
        print(json.dumps(rows, ensure_ascii=False, indent=2) if args.json else "\n".join(f"{r['status'].upper()} {r['name']}: {r.get('detail', '')}" for r in rows))
        return code
    if args.command == "verify":
        from agentlib.checks import verify
        return verify(ROOT, args.profile)
    if args.command == "sync":
        result = run(ROOT, ["{python}", "-B", "Docs/_brain/build.py"])
        print(result.stdout + result.stderr)
        return result.returncode
    return attest(args.document) if args.command == "attest" else status()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
