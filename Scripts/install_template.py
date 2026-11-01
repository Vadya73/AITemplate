"""Install/update a versioned agent template, preserving project-owned data."""

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from agentlib.install import apply, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update", action="store_true", help="Update using the recorded base hashes")
    parser.add_argument("--accept-merged", action="append", default=[], metavar="PATH", help="Record an explicitly reviewed manual merge; keep its local contents")
    args = parser.parse_args()
    result = plan(Path(__file__).resolve().parents[1], args.destination, args.update, args.accept_merged)
    for relative, action in result["actions"]:
        print(f"PLAN {action.upper()} {relative}")
    for message in result["kept"]:
        print(f"KEEP {message}")
    for message in result["conflicts"]:
        print(f"CONFLICT {message}")
    if result["conflicts"]:
        print("Ничего не записано. Объедините конфликтующие файлы вручную и повторите --dry-run.")
        return 1
    if not args.dry_run:
        apply(result)
    print(f"{'Запланировано' if args.dry_run else 'Записано'}: {len(result['actions'])}; версия {result['receipt']['template_version']}")
    print("Настройка проекта: Docs/agent-rules/SETUP.md; изменения продукта проверяются отдельно.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f"Ошибка переноса: {error}")
