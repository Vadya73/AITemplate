import re

FIELDS = ("code", "tables", "config_keys", "resources", "protocol_keys", "handlers")


def anchor(heading):
    slug = heading.strip().lower()
    slug = re.sub(r"[`*_\[\]()<>«»„“”\"'.,:;!?/\\]", "", slug)
    slug = slug.replace("—", "-").replace("–", "-")
    slug = re.sub(r"[^\w\s\-]", "", slug)
    return re.sub(r"\s+", "-", slug.strip())


def sections(body, offset=0):
    found, counts, fence = [], {}, None
    for number, line in enumerate(body.splitlines(), 1 + offset):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            kind = marker.group(1)[0]
            fence = None if fence == kind else (kind if fence is None else fence)
            continue
        if fence or not line.startswith("## "):
            continue
        heading = line[3:].strip()
        slug = anchor(heading)
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        found.append({"heading": heading, "anchor": slug + (f"-{count}" if count else ""), "line": number})
    return found


def title(body):
    return next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), None)


def metadata(body, manual):
    result = {}
    for key in FIELDS:
        values = manual.get(key) or []
        if not isinstance(values, list):
            raise ValueError(f"{key}: ожидается YAML-массив")
        if any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in values):
            raise ValueError(f"{key}: допустимы только строки и числа")
        result[key] = {str(value) for value in values}
    result["code"] |= set(re.findall(r"`((?:Assets|src|Source|Scripts|app|lib|tests)/[^`\n]+\.[A-Za-z0-9]+)`", body))
    result["resources"] |= set(re.findall(r"\bResId\.([A-Z][A-Z_0-9]*)", body))
    result["protocol_keys"] |= set(re.findall(r"\[Key\((\d+)\)\]", body))
    result["handlers"] |= set(re.findall(r"\b[A-Z][A-Za-z0-9]*(?:Handler|Repository|Service)\b", body))
    if any(not value.isdigit() for value in result["protocol_keys"]):
        raise ValueError("protocol_keys: ожидаются неотрицательные номера")
    return {key: sorted(values, key=int) if key == "protocol_keys" else sorted(values)
            for key, values in result.items()}


def pitfalls(body, offset):
    return [(number, line.strip().lstrip("->*| "))
            for number, line in enumerate(body.splitlines(), 1 + offset) if "⚠" in line]
