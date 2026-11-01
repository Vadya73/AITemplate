"""Prepare isolated agent tasks, score artifacts and compare matching runs. No model calls."""

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
from agentlib.evals import prepare, score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("prepare")
    new.add_argument("output", type=Path)
    new.add_argument("--variant", required=True)
    new.add_argument("--model", required=True, help="Exact agent/model/settings label for a fair comparison")
    check = commands.add_parser("score")
    check.add_argument("run", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(f"Prepared {prepare(ROOT, args.output, args.variant, args.model)} cases. Run each task.md in its workspace using your agent.")
        return 0
    if args.command == "score":
        report = score(ROOT, args.run)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    left, right = score(ROOT, args.baseline), score(ROOT, args.candidate)
    if any(left[key] != right[key] for key in ("suite_hash", "model", "case_id")):
        raise ValueError("Comparison requires identical suite, model/settings and case")
    print(json.dumps({"baseline": left, "candidate": right}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        sys.exit(f"Evaluation error: {error}")
