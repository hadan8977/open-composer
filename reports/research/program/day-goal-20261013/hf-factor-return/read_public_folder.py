"""Parse retained public Drive HTML file metadata, without executing source scripts."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path)
    body = path.read_text()
    match = re.search(r"window\['_DRIVE_ivd'\] = '((?:\\.|[^'\\])*)';", body)
    assert match, "No retained public folder listing payload"
    value = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), match[1])
    value = value.replace(r"\/", "/").replace(r"\'", "'")
    obj = json.loads(value)
    rows = {}

    def walk(item):
        if isinstance(item, list):
            if (
                len(item) > 14 and isinstance(item[0], str)
                and isinstance(item[2], str) and isinstance(item[3], str)
                and re.fullmatch(r"[\w-]{20,}", item[0]) and "/" in item[3]
            ):
                rows[item[0]] = {
                    "id": item[0], "name": item[2], "mime": item[3],
                    "prefix_metadata": item[:14],
                    "size_field_13": item[13],
                    "other_scalar_numeric_fields": {
                        str(i): x for i, x in enumerate(item)
                        if isinstance(x, (int, float)) and 1000 < x < 100_000_000_000
                    },
                }
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            for child in item.values():
                walk(child)

    walk(obj)
    output = {
        "source_path": str(path), "source_SHA256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "parser": "Retained published _DRIVE_ivd escaped JSON, never evaluated JavaScript",
        "rows": list(rows.values()),
    }
    path.with_suffix(".inventory.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
