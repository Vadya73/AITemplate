import os
import re

NOTE = ("> Сгенерировано `_brain/build.py` — руками не править, правки затрутся.\n"
        "> Источник: тела документов + `_brain/brain.yaml`.")
QUICK_WORDS = ("грабл", "ловушк", "подводн", "инвариант", "карта файлов", "ключевые файлы",
               "файловая карта", "чек-лист", "рецепт", "что проверять", "кратк", "быстр")


def rel(from_dir, path):
    return os.path.relpath(path, from_dir).replace(os.sep, "/")


def link(from_dir, path, anchor=""):
    target = rel(from_dir, path) + (f"#{anchor}" if anchor else "")
    if re.search(r"[ ()]", target):
        return f"<{target}>"
    return target


def _ranges(doc):
    total = doc["offset"] + doc["body"].count("\n") + 1
    marks = [s["line"] for s in doc["sections"]] + [total]
    return {doc["sections"][i]["anchor"]: (marks[i], marks[i + 1] - 1)
            for i in range(len(doc["sections"]))}


def _quick(doc, from_dir):
    spans = _ranges(doc)
    picked = [s for s in doc["sections"]
              if any(word in s["heading"].lower() for word in QUICK_WORDS)]
    if not picked:
        picked = doc["sections"][:2]
    out = []
    for section in picked[:3]:
        start, end = spans[section["anchor"]]
        out.append(f"[{section['heading']}]({link(from_dir, doc['path'], section['anchor'])}) "
                   f"`L{start}-{end}`")
    return "<br>".join(out)


def _nest(group):
    docs = list(group)
    kids = {}
    for doc in docs:
        parent = doc["meta"].get("parent")
        if parent:
            kids.setdefault(parent, []).append(doc)
    out = []
    for doc in sorted((d for d in docs if not d["meta"].get("parent")), key=lambda d: -d["bytes"]):
        out.append(doc)
        out += sorted(kids.pop(doc["id"], []), key=lambda d: d["id"])
    for orphans in kids.values():
        out += orphans
    return out


def index(docs, cfg, stale_ids, out_dir):
    lines = [f"# Индекс документации — {cfg['title']}", "", NOTE, "",
             "## Как этим пользоваться (кодовому агенту)", "",
             "1. Этот файл — единственная точка входа в документацию. Не грепай по `Docs/` вслепую.",
             "2. Нашёл подсистему — возьми нужный диапазон строк из колонки «Быстрые секции».",
             "   Заголовки можно найти через `rg -n '^## ' <файл>`; не читай весь массив документации.",
             "3. Поперечные вопросы — занятые `Key(N)`, `ResId`, таблицы, конфиг-ключи, известные грабли —",
             "   решаются [реестрами](_brain/registries/), а не чтением механик.",
             "4. Типовая задача («добавить поле в протокол», «добавить ресурс», «добавить язык») —",
             "   начинай с [плейбука](_brain/playbooks/).",
             "5. Пометка `⚠ stale` = отсутствует сверка или отпечаток кода изменился. Подробности в реестре актуальности.",
             "6. Правишь описанный в документе код — обнови `verified:` в его frontmatter и прогони",
             "   `python Docs/_brain/build.py`.", ""]

    counterpart = cfg.get("counterpart")
    if counterpart:
        lines += [f"**Вторая половина системы — {counterpart['side']}:** [{counterpart['index']}]"
                  f"({counterpart['index']}). У документа механики во frontmatter есть "
                  "`server_doc:` / `client_doc:` — прямая ссылка на парный документ.", ""]

    lines += ["## Домены", "", "| Домен | О чём | Документов |", "|---|---|---|"]
    for dom_id, dom in cfg["domains"].items():
        count = sum(1 for d in docs if d["meta"]["domain"] == dom_id)
        lines.append(f"| [{dom['title']}](#{dom_id.lower()}) | {dom['hint']} | {count} |")
    lines += ["", "## Навигация", "",
              "- [Реестры](_brain/registries/): "
              "[Key(N)](_brain/registries/ProtocolKeys.md) · "
              "[ResId](_brain/registries/Resources.md) · "
              "[таблицы БД](_brain/registries/DbTables.md) · "
              "[конфиг-ключи](_brain/registries/ConfigKeys.md) · "
              "[обработчики](_brain/registries/Handlers.md) · "
              "[покрытие](_brain/registries/Coverage.md) · "
              "[грабли](_brain/registries/Pitfalls.md) · "
              "[протухшее](_brain/registries/Stale.md)",
              "- [Плейбуки](_brain/playbooks/) — рецепты типовых задач",
              "- [Карта данных](_brain/DATA.md) — зарегистрированные данные, фикстуры и миграции"]
    if os.path.exists(os.path.join(out_dir, "_brain", "glossary.md")):
        lines.append("- [Глоссарий](_brain/glossary.md) — русский термин → имя в коде. "
                     "Начинай отсюда, если не знаешь имя понятия в коде.")
    lines.append("- [Карта символов C#](_brain/index/symbols.tsv) — эвристический индекс настроенных корней, "
                 "классы и члены с путём и строкой. Искать через `rg`, перепроверять в коде.")
    lines.append("")

    for dom_id, dom in cfg["domains"].items():
        group = _nest(d for d in docs if d["meta"]["domain"] == dom_id)
        if not group:
            continue
        lines += [f"## {dom_id}", "", f"*{dom['title']} — {dom['hint']}*", "",
                  "| Документ | Размер | Открывать когда | Быстрые секции |", "|---|---|---|---|"]
        for doc in group:
            status = doc["meta"].get("status")
            if status == "missing":
                mark = " 🕳 не описано"
            elif status == "partial":
                mark = " ◐ описано частично"
            elif status == "archived":
                mark = " архив"
            elif doc["id"] in stale_ids:
                mark = " ⚠ stale"
            else:
                mark = ""
            if doc["meta"].get("parent"):
                lines.append(f"| ↳ [{doc['meta']['title']}]({link(out_dir, doc['path'])}){mark} "
                             f"| {doc['bytes'] // 1024}К "
                             f"| {doc['meta']['hint']} | подстраница |")
            else:
                lines.append(f"| [{doc['meta']['title']}]({link(out_dir, doc['path'])}){mark} "
                             f"| {doc['bytes'] // 1024}К "
                             f"| {doc['meta']['hint']} | {_quick(doc, out_dir)} |")
        lines.append("")

    lines += ["---", f"Документов: {len(docs)}", ""]
    return "\n".join(lines)


def registry(docs, field, title, intro, column, out_dir, numeric=False):
    bucket = {}
    for doc in docs:
        for value in doc["auto"].get(field, []):
            bucket.setdefault(str(value), []).append(doc)
    keys = sorted(bucket, key=lambda k: int(k)) if numeric else sorted(bucket)

    lines = [f"# {title}", "", NOTE, "", intro, "",
             f"| {column} | Домены | Документы |", "|---|---|---|"]
    for key in keys:
        owners = bucket[key]
        links = ", ".join(f"[{d['meta']['title']}]({link(out_dir, d['path'])})" for d in owners[:5])
        if len(owners) > 5:
            links += f" +{len(owners) - 5}"
        domains = ", ".join(sorted({d["meta"]["domain"] for d in owners}))
        lines.append(f"| `{key}` | {domains} | {links} |")
    lines += ["", f"Записей: {len(keys)}", ""]
    return "\n".join(lines)


def pitfalls(docs, out_dir):
    lines = ["# Известные грабли", "", NOTE, "",
             "Все строки с `⚠` из документации, одним списком. Читать перед правкой механики. "
             "`:N` — номер строки в исходном документе.", ""]
    total = 0
    for doc in sorted(docs, key=lambda d: (d["meta"]["domain"], d["id"])):
        if not doc["pitfalls"]:
            continue
        lines.append(f"### [{doc['meta']['title']}]({link(out_dir, doc['path'])}) "
                     f"· {doc['meta']['domain']}")
        for line_no, text in doc["pitfalls"][:12]:
            plain = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
            lines.append(f"- `:{line_no}` {plain}")
            total += 1
        if len(doc["pitfalls"]) > 12:
            lines.append(f"- … ещё {len(doc['pitfalls']) - 12} в документе")
        lines.append("")
    lines += ["---", f"Записей: {total}", ""]
    return "\n".join(lines)


def stale_report(stale, out_dir):
    lines = ["# Актуальность документации", "", NOTE, "",
             "Сравниваются содержимое путей `code:` и отпечатки `verified_code`, записанные после явной сверки.",
             "Git-состояние и дата запуска не влияют на этот файл; текущая диагностика: `python Scripts/agent.py status`.",
             "Совпадение отпечатков не доказывает качество описания; незарегистрированные зависимости не проверяются.", "",
             "| Документ | Сверен | Путь | Причина |", "|---|---|---|---|"]
    for doc_id, info in sorted(stale.items()):
        for path, reason in info["reasons"]:
            lines.append(f"| [{info['title']}]({link(out_dir, info['path'])}) | {info['verified']} | `{path}` | {reason} |")
    lines += ["", f"Документов с предупреждениями: {len(stale)}", ""]
    return "\n".join(lines)


def data_map(cfg):
    lines = ["# Карта не-документации", "", NOTE, "",
             "Данные и SQL, лежащие рядом с документацией. Агенту: **никогда не читать папку целиком**, "
             "открывать только конкретный файл по делу.", "",
             "| Путь | Что это | Когда открывать |", "|---|---|---|"]
    for path, info in cfg.get("data", {}).items():
        lines.append(f"| `{path}` | {info['what']} | {info['when']} |")
    lines.append("")
    return "\n".join(lines)
