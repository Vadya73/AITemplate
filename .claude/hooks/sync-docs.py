"""Read-only Stop hook. Success cache lives outside the checkout."""

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Hook input must be a JSON object")
        candidate = Path(payload.get("cwd") or Path(__file__).resolve().parents[2]).resolve()
        root = None
        for path in (candidate, *candidate.parents):
            if (path / "Scripts/agent.py").is_file() and (path / "Docs/_brain/build.py").is_file():
                root = path
                break
            if (path / ".git").exists():
                break
        if root is None:
            return
        sys.path.insert(0, str(root / "Scripts"))
        from agentlib.hook import check
        message = check(root, payload)
    except Exception as error:
        message = {"systemMessage": f"Ошибка проверки документации, файлы не изменены: {error}"}
    if message:
        print(json.dumps(message, ensure_ascii=True))


if __name__ == "__main__":
    main()
