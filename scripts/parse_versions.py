#!/usr/bin/env python3
"""Read a value from versions.json by dotted key path."""
import argparse
import json
import sys
from pathlib import Path


def get_nested(data, path, default=None):
    for key in path.split("."):
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("file")
parser.add_argument("key", help="Dotted path, e.g. packaging.git_tag")
parser.add_argument("--default", default="")
parser.add_argument("--required", action="store_true")
args = parser.parse_args()

data = json.loads(Path(args.file).read_text())
value = get_nested(data, args.key)
if value is None:
    if args.required:
        print(f"ERROR: required key '{args.key}' not found in {args.file}", file=sys.stderr)
        sys.exit(1)
    value = args.default
print(value)
