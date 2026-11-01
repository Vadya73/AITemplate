"""Build portable documentation indexes; --check never writes files."""

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

try:
    import yaml
except ImportError:
    sys.exit("Нужен PyYAML: python -m pip install -r Docs/_brain/requirements.txt")

import coverage
import extract
import frontmatter
import links
import render
import fingerprints
import symbols

BRAIN_DIR = Path(__file__).resolve().parent
DOCS_DIR = BRAIN_DIR.parent
REPO_ROOT = DOCS_DIR.parent


def config():
    cfg = yaml.safe_load((BRAIN_DIR / "brain.yaml").read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or not all(key in cfg for key in ("title", "side", "domains", "docs")):
        raise ValueError("brain.yaml: нужны title, side, domains и docs")
    if not isinstance(cfg["docs"], dict) or not isinstance(cfg["domains"], dict):
        raise ValueError("docs и domains должны быть YAML mappings")
    for entry in (cfg.get("symbols_index") or {}).get("roots", []):
        code_root = (DOCS_DIR / entry).resolve()
        if not code_root.is_dir() or not code_root.is_relative_to(REPO_ROOT):
            raise ValueError(f"Неверный symbols root: {entry}")
    for entry in (cfg.get("coverage") or {}).get("code", []):
        code_root = (DOCS_DIR / entry["root"]).resolve()
        if not code_root.is_dir() or not code_root.is_relative_to(REPO_ROOT):
            raise ValueError(f"Неверный coverage root: {entry['root']}")
    return cfg


def collect(cfg):
    docs, ids = [], set()
    for rel_path, entry in cfg["docs"].items():
        path = (DOCS_DIR / rel_path).resolve()
        if not path.is_relative_to(DOCS_DIR) or path.suffix != ".md" or not path.is_file():
            raise ValueError(f"Неверный путь документа: {rel_path}")
        doc_id = entry.get("id") or re.sub(r"[^\w-]+", "-", Path(rel_path).with_suffix("").as_posix()).strip("-").lower()
        if not re.fullmatch(r"[\w-]+", doc_id) or doc_id in ids:
            raise ValueError(f"Неверный или повторяющийся id: {doc_id}")
        ids.add(doc_id)
        if entry.get("domain") not in cfg["domains"] or not entry.get("hint"):
            raise ValueError(f"Для {rel_path} нужны известный domain и непустой hint")
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        manual, body = frontmatter.split(text)
        generated = {"id": doc_id, "title": extract.title(body) or doc_id, "domain": entry["domain"],
                     "hint": entry["hint"], "side": cfg["side"], "related": []}
        if entry.get("parent"):
            generated["parent"] = entry["parent"]
        meta = frontmatter.build(manual, generated)
        if meta["status"] not in ("actual", "partial", "missing", "archived"):
            raise ValueError(f"Неизвестный status: {rel_path}")
        auto = extract.metadata(body, meta)
        for code_path in auto["code"]:
            if not (REPO_ROOT / code_path).resolve().is_relative_to(REPO_ROOT):
                raise ValueError(f"code: путь вне проекта: {code_path}")
        docs.append({"rel": rel_path, "path": str(path), "entry": entry, "id": doc_id,
                     "meta": meta, "body": body, "bytes": len(body.encode("utf-8")), "auto": auto})
    by_path = {Path(doc["path"]): doc for doc in docs}
    by_id = {doc["id"]: doc for doc in docs}
    for doc in docs:
        related = set()
        for line in links._outside_code(doc["body"]):
            for target in links._targets(links.CODESPAN_RE.sub("", line)):
                candidate = (Path(doc["path"]).parent / unquote(target.split("#", 1)[0])).resolve()
                if candidate in by_path and candidate != Path(doc["path"]):
                    related.add(by_path[candidate]["id"])
        parent = doc["meta"].get("parent")
        if parent and (parent not in by_id or doc["id"] not in _links_to_ids(by_id[parent], by_path)):
            raise ValueError(f"Неверный parent или нет ссылки из родителя: {doc['rel']}")
        visited = {doc["id"]}
        ancestor = parent
        while ancestor:
            if ancestor in visited:
                raise ValueError(f"Цикл parent: {doc['rel']}")
            visited.add(ancestor)
            ancestor = by_id[ancestor]["meta"].get("parent") if ancestor in by_id else None
        doc["meta"]["related"] = sorted(related)
        offset = len(frontmatter.dump(doc["meta"]).splitlines()) + 1
        doc.update(offset=offset, sections=extract.sections(doc["body"], offset),
                   pitfalls=extract.pitfalls(doc["body"], offset))
    return docs


def _links_to_ids(doc, by_path):
    found = set()
    for line in links._outside_code(doc["body"]):
        for target in links._targets(links.CODESPAN_RE.sub("", line)):
            path = (Path(doc["path"]).parent / unquote(target.split("#", 1)[0])).resolve()
            if path in by_path:
                found.add(by_path[path]["id"])
    return found


def outputs(cfg, docs):
    registry_dir = str(BRAIN_DIR / "registries")
    status = fingerprints.scan(docs, REPO_ROOT)
    result = {Path(doc["path"]): frontmatter.dump(doc["meta"]) + "\n" + doc["body"] for doc in docs}
    result[DOCS_DIR / "INDEX.md"] = render.index(docs, cfg, set(status), str(DOCS_DIR))
    registries = [
        ("ProtocolKeys", "protocol_keys", "Ключи протокола", "Упоминания Key(N), не полный список ID. Область номера — конкретный тип. Сверяй определения контракта. [Плейбук](../playbooks/extend-protocol.md).", "Key", True),
        ("Resources", "resources", "Ресурсы", "Ресурсы, явно перечисленные в документах или распознанные по ResId. Владельца баланса определяет проект.", "Ресурс", False),
        ("DbTables", "tables", "Таблицы БД", "Таблицы из метаданных документов. Прямые обращения к БД запрещены; схему сверяй по коду и миграциям.", "Таблица", False),
        ("ConfigKeys", "config_keys", "Ключи конфигурации", "Ключи из метаданных документов; формат и источник истины задаёт проект.", "Ключ", False),
        ("Handlers", "handlers", "Обработчики и сервисы", "Упоминания обработчиков и сервисов. Наличие имени не доказывает полноту описания.", "Тип", False),
    ]
    for name, field, title, intro, column, numeric in registries:
        result[BRAIN_DIR / "registries" / f"{name}.md"] = render.registry(docs, field, title, intro, column, registry_dir, numeric)
    result[BRAIN_DIR / "registries" / "Pitfalls.md"] = render.pitfalls(docs, registry_dir)
    result[BRAIN_DIR / "registries" / "Stale.md"] = render.stale_report(status, registry_dir)
    result[BRAIN_DIR / "registries" / "Coverage.md"] = coverage.render(docs, coverage.scan(docs, REPO_ROOT, cfg), registry_dir, render.link)
    result[BRAIN_DIR / "DATA.md"] = render.data_map(cfg)
    roots = (cfg.get("symbols_index") or {}).get("roots", [])
    result[BRAIN_DIR / "index" / "symbols.tsv"] = symbols.render(symbols.scan(str(DOCS_DIR), roots))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Проверить без записи; exit 1 при ошибках/устаревших результатах")
    args = parser.parse_args()
    try:
        cfg = config()
        docs = collect(cfg)
        planned = outputs(cfg, docs)
        broken = links.check(str(DOCS_DIR), planned)
        if broken:
            for source, target in broken:
                print(f"broken link: {source} -> {target}")
            return 1
        changed = []
        for path, content in planned.items():
            if not path.exists() or path.read_bytes() != content.encode("utf-8"):
                changed.append(path)
        if args.check:
            for path in changed:
                print(f"outdated: {path.relative_to(REPO_ROOT).as_posix()}")
        else:
            for path in changed:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(planned[path].encode("utf-8"))
        print(f"docs: {len(docs)}; {'outdated' if args.check else 'updated'}: {len(changed)}; links: ok")
        return 1 if args.check and changed else 0
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
