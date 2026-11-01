"""Hash-based template updates; project-owned seeds are never replaced on update."""

import hashlib
import json
import tempfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    path = root / rel
    if rel.is_absolute() or not relative or not path.resolve().is_relative_to(root):
        raise ValueError(f"Путь вне проекта: {relative}")
    return path


def manifest(source):
    source = Path(source).resolve()
    data = json.loads((source / "template.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("kind") != "coding-agent-template":
        raise ValueError("Неверный template.json")
    if not data.get("version") or not data.get("files"):
        raise ValueError("Manifest требует version и files")
    for relative, info in data["files"].items():
        path = safe(source, relative)
        if info.get("policy") not in ("managed", "seed") or not path.is_file() or digest(path) != info.get("sha256"):
            raise ValueError(f"Источник не совпадает с manifest: {relative}. Пересоберите manifest только в исходном шаблоне.")
    return data


def plan(source, target, update=False, accepted=()):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("Источник и назначение не должны совпадать или содержать друг друга")
    if not target.is_dir():
        raise ValueError("Каталог назначения должен существовать")
    spec = manifest(source)
    receipt_path = safe(target, ".agent/template-lock.json")
    previous = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
    if update and previous is None:
        raise ValueError("Нет template-lock.json: неизвестна исходная версия; выполните первоначальное объединение вручную")
    if previous and previous.get("template_id") != spec["template_id"]:
        raise ValueError("Каталог установлен из другого шаблона")
    if previous and previous.get("template_version") != spec["version"] and not update:
        raise ValueError("Для изменения установленной версии используйте --update")
    old_files = previous.get("files", {}) if previous else {}
    accepted = set(accepted)
    if accepted and (not update or not accepted.issubset(spec["files"])):
        raise ValueError("--accept-merged допустим только для известных файлов при --update")
    actions, conflicts, kept, expected = [], [], [], {}
    for relative, info in sorted(spec["files"].items()):
        destination = safe(target, relative)
        if any(p.exists() and not p.is_dir() for p in destination.parents if p.is_relative_to(target)):
            conflicts.append(relative + ": родитель занят файлом")
            continue
        if not destination.exists():
            if relative in old_files:
                kept.append(relative + ": локально удалён, не восстанавливается автоматически")
            else:
                actions.append((relative, "create"))
                expected[relative] = None
            continue
        if not destination.is_file():
            conflicts.append(relative + ": занят каталогом")
            continue
        current = digest(destination)
        old = old_files.get(relative, {}).get("sha256")
        if current == info["sha256"]:
            continue
        if relative in accepted:
            kept.append(relative + ": ручное объединение явно подтверждено")
            continue
        if info["policy"] == "seed":
            if update:
                kept.append(relative + ": настройки/знания проекта сохранены")
            else:
                conflicts.append(relative + ": уже существует; требуется первоначальное объединение")
        elif old == info["sha256"]:
            kept.append(relative + ": локальная правка, upstream не изменён")
        elif old and current == old:
            actions.append((relative, "update"))
            expected[relative] = current
        else:
            conflicts.append(relative + ": локальная и входящая версии различаются")
    for relative in sorted(set(old_files) - set(spec["files"])):
        kept.append(relative + ": удалён из upstream; локальный файл оставлен для ручного решения")
    receipt = {"schema_version": 1, "template_id": spec["template_id"], "template_version": spec["version"],
               "files": spec["files"]}
    return {"source": source, "target": target, "actions": actions, "conflicts": conflicts,
            "kept": kept, "receipt": receipt, "receipt_path": receipt_path, "expected": expected,
            "old_receipt": receipt_path.read_bytes() if receipt_path.is_file() else None}


def apply(planned):
    if planned["conflicts"]:
        raise ValueError("Конфликты не разрешены; ничего не записано")
    # Recheck all paths and contents before the first write, including user edits since planning.
    originals = {}
    for relative, action in planned["actions"]:
        target = safe(planned["target"], relative)
        current = digest(target) if target.is_file() else None
        if current != planned["expected"][relative]:
            raise ValueError(f"Файл изменился после планирования: {relative}")
        originals[relative] = target.read_bytes() if target.is_file() else None
    receipt_path = safe(planned["target"], ".agent/template-lock.json")
    if (receipt_path.read_bytes() if receipt_path.is_file() else None) != planned["old_receipt"]:
        raise ValueError("Receipt изменился после планирования")
    written = []
    try:
        for relative, action in planned["actions"]:
            target = safe(planned["target"], relative)
            current = target.read_bytes() if target.is_file() else None
            if current != originals[relative]:
                raise ValueError(f"Файл изменился во время обновления: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = safe(planned["source"], relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != planned["receipt"]["files"][relative]["sha256"]:
                raise ValueError(f"Источник изменился во время обновления: {relative}")
            if action == "create":
                with target.open("xb") as handle:
                    handle.write(data)
            else:
                target.write_bytes(data)
            written.append(relative)
        receipt = safe(planned["target"], ".agent/template-lock.json")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=receipt.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(planned["receipt"], ensure_ascii=False, indent=2) + "\n")
        try:
            temporary.replace(receipt)
        finally:
            if temporary.exists():
                temporary.unlink()
    except Exception:
        for relative in reversed(written):
            target = safe(planned["target"], relative)
            if originals[relative] is None:
                target.unlink()
            else:
                target.write_bytes(originals[relative])
        raise
