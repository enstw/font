#!/usr/bin/env python3
"""
build_release_notes.py - Assembles the GitHub Release body for ENS Font.

Fetches upstream changelogs from LXGW WenKai TC and Nerd Fonts releases,
then combines them with ENS Font metadata into a single Markdown document.
"""

import argparse
import os
import sys
from pathlib import Path

import requests


def get_release_body(repo: str, tag: str, token: str) -> str:
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        body = resp.json().get("body") or ""
        return body.replace("@", "＠")
    except Exception as e:
        print(
            f"WARNING: Could not fetch release notes for {repo}@{tag}: {e}",
            file=sys.stderr,
        )
        return ""


def truncate_body(body: str, max_lines: int = 50) -> str:
    lines = body.splitlines()
    if len(lines) <= max_lines:
        return body
    return "\n".join(lines[:max_lines]) + "\n\n_...（完整內容請見上游 Release 頁面）_"


def build_notes(
    version: str,
    lxgw_tag: str,
    nerd_tag: str,
    lxgw_body: str,
    nerd_body: str,
    lxgw_changed: bool = True,
    nerd_changed: bool = True,
) -> str:
    lxgw_url = f"https://github.com/lxgw/LxgwWenKaiTC/releases/tag/{lxgw_tag}"
    nerd_url = f"https://github.com/ryanoasis/nerd-fonts/releases/tag/{nerd_tag}"

    if lxgw_changed:
        lxgw_section = truncate_body(lxgw_body.strip()) if lxgw_body.strip() else "_（無變更記錄）_"
    else:
        lxgw_section = "_（此版本無變更）_"

    if nerd_changed:
        nerd_section = truncate_body(nerd_body.strip()) if nerd_body.strip() else "_（無變更記錄）_"
    else:
        nerd_section = "_（此版本無變更）_"

    return f"""\
## ENS Font v{version}

**Elegant · Nerd · Sino** — 終端機專用中英混排字體 (Traditional Chinese CJK Base)

| 來源 | 版本 | 用途 |
|------|------|------|
| LXGW WenKai TC / LXGW WenKai Mono TC | [{lxgw_tag}]({lxgw_url}) | CJK 字元基底 |
| Meslo LGSDZ Nerd Font | [{nerd_tag}]({nerd_url}) | ENS Font ASCII / Latin / PUA donor |
| Meslo LGSDZ Nerd Font Mono | [{nerd_tag}]({nerd_url}) | ENS Font Mono donor |

### 字元優先權
1. **Meslo LGSDZ Nerd Font / Meslo LGSDZ Nerd Font Mono** — donor 字型涵蓋的所有字元，一律優先覆蓋 WenKai
2. **LXGW WenKai TC** — donor 沒有的字元，主要為 CJK、假名、全形標點

> 對應規則：`ENS Font = LXGW WenKai TC + Meslo LGSDZ Nerd Font`，`ENS Font Mono = LXGW WenKai Mono TC + Meslo LGSDZ Nerd Font Mono`。

### 字體檔案

| 檔案 | 字重 |
|------|------|
| `ENSFont-Regular.ttf`      | Regular      |
| `ENSFont-Bold.ttf`         | Bold         |
| `ENSFontMono-Regular.ttf`  | Regular Mono |
| `ENSFontMono-Bold.ttf`     | Bold Mono    |

下載 `ENSFont-{version}.zip` 取得所有字重。

### 授權
- 最終字體：[SIL OFL 1.1](https://openfontlicense.org)
- ASCII/拉丁字形（Meslo LG）：[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- Nerd Fonts 補丁與 PUA 圖標：[MIT License](https://github.com/ryanoasis/nerd-fonts/blob/master/LICENSE)

保留字型名稱：**"ENS Font"** 與 **"Elegant Nerd Sino"**。
原始保留名稱 "LXGW"、"霞鶩"、"Klee" 均**未使用**於本衍生字體。

### Contributors
@enstw · [Claude](https://github.com/claude)

---

## 上游變更記錄

### LXGW WenKai TC {lxgw_tag}

{lxgw_section}

> 完整內容：[{lxgw_url}]({lxgw_url})

---

### Nerd Fonts {nerd_tag}

{nerd_section}

> 完整內容：[{nerd_url}]({nerd_url})
"""


def parse_bool(value: str) -> bool:
    low = value.lower()
    if low in ("true", "1", "yes"):
        return True
    if low in ("false", "0", "no"):
        return False
    raise ValueError(f"Unrecognized boolean value: {value!r} (expected true/false/yes/no/1/0)")


def main():
    parser = argparse.ArgumentParser(description="Build ENS Font GitHub Release notes")
    parser.add_argument("--version", required=True, help="ENS Font packaging version (e.g. 3.0.0)")
    parser.add_argument("--lxgw-tag", required=True, help="LXGW WenKai release tag (e.g. v1.521)")
    parser.add_argument("--nerd-tag", required=True, help="Nerd Fonts release tag (e.g. v3.4.0)")
    parser.add_argument(
        "--lxgw-changed",
        default="true",
        help="Include LXGW WenKai changelog (true/false, default: true)",
    )
    parser.add_argument(
        "--nerd-changed",
        default="true",
        help="Include Nerd Fonts changelog (true/false, default: true)",
    )
    parser.add_argument("--output", required=True, help="Output file path for release notes Markdown")
    args = parser.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN", "")
    lxgw_changed = parse_bool(args.lxgw_changed)
    nerd_changed = parse_bool(args.nerd_changed)

    lxgw_body = ""
    if lxgw_changed:
        print(f"Fetching LXGW WenKai TC changelog for {args.lxgw_tag}...")
        lxgw_body = get_release_body("lxgw/LxgwWenKaiTC", args.lxgw_tag, github_token)
    else:
        print(f"LXGW WenKai TC {args.lxgw_tag}: no change, skipping fetch.")

    nerd_body = ""
    if nerd_changed:
        print(f"Fetching Nerd Fonts changelog for {args.nerd_tag}...")
        nerd_body = get_release_body("ryanoasis/nerd-fonts", args.nerd_tag, github_token)
    else:
        print(f"Nerd Fonts {args.nerd_tag}: no change, skipping fetch.")

    notes = build_notes(
        version=args.version,
        lxgw_tag=args.lxgw_tag,
        nerd_tag=args.nerd_tag,
        lxgw_body=lxgw_body,
        nerd_body=nerd_body,
        lxgw_changed=lxgw_changed,
        nerd_changed=nerd_changed,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(notes, encoding="utf-8")
    print(f"Release notes written to {output} ({len(notes)} chars)")


if __name__ == "__main__":
    main()
