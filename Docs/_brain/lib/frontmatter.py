from datetime import date, datetime

import yaml

GENERATED = ("id", "title", "domain", "hint", "parent", "side", "related")
ORDER = ("id", "title", "domain", "hint", "parent", "status", "verified", "verified_code", "side",
         "server_doc", "client_doc", "owner", "code", "tables", "config_keys",
         "resources", "protocol_keys", "handlers", "related")


def split(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("Frontmatter не закрыт разделителем ---")
    meta = yaml.safe_load("".join(lines[1:end])) or {}
    if not isinstance(meta, dict):
        raise ValueError("Frontmatter должен быть YAML mapping")
    return meta, "".join(lines[end + 1:]).lstrip("\n")


def build(existing, generated):
    meta = {key: value for key, value in existing.items() if key not in GENERATED}
    meta.setdefault("status", "partial")
    verified = meta.get("verified")
    if isinstance(verified, (date, datetime)):
        meta["verified"] = verified.date().isoformat() if isinstance(verified, datetime) else verified.isoformat()
    elif verified:
        date.fromisoformat(str(verified))
        meta["verified"] = str(verified)
    meta.update(generated)
    return meta


def dump(meta):
    keys = [key for key in ORDER if key in meta]
    keys += sorted(key for key in meta if key not in ORDER)
    ordered = {key: meta[key] for key in keys}
    return "---\n" + yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False, width=10000) + "---\n"
