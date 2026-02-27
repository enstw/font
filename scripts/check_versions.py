#!/usr/bin/env python3
"""
check_versions.py - Polls upstream GitHub releases and updates versions.json.

Exit codes:
  0  No upstream changes (skip build)
  1  Upstream changed (trigger build)
  2  Error (bad config, network failure, etc.)

GitHub Actions output variables written to $GITHUB_OUTPUT:
  VERSIONS_CHANGED  true | false
  NEW_VERSION       e.g. 1.2.0
  GIT_TAG           e.g. v1.2.0_lxgw1521_nerd340
  LXGW_TAG          e.g. v1.521
  NERD_TAG          e.g. v3.4.0

Usage:
    python scripts/check_versions.py \\
        --versions-file versions.json \\
        --github-token $GITHUB_TOKEN
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


def release_tag_exists(owner_repo: str, tag: str, token: str) -> bool:
    """
    Check whether a GitHub Release with the given tag already exists
    in this repository. Used to detect the first-run case where
    versions.json is pre-populated but no Release has been published yet.
    """
    url = f"https://api.github.com/repos/{owner_repo}/releases/tags/{tag}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(url, headers=headers, timeout=30)
    return resp.status_code == 200


def get_latest_release(repo: str, token: str) -> dict:
    """
    Query GitHub API for the latest release of a repository.
    Returns dict: {tag_name, published_at, assets[{name, browser_download_url}]}.
    Raises requests.HTTPError on failure.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    return {
        "tag_name": data["tag_name"],
        "published_at": data["published_at"],
        "assets": [
            {"name": a["name"], "browser_download_url": a["browser_download_url"]}
            for a in data.get("assets", [])
        ],
    }


def bump_minor(version: str) -> str:
    """Bump minor version: '1.0.0' -> '1.1.0'"""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format (expected X.Y.Z): {version!r}")
    major, minor, _ = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{major}.{minor + 1}.0"


def build_git_tag(pkg_version: str, lxgw_tag: str, nerd_tag: str) -> str:
    """
    Construct the git tag encoding all upstream versions.
    Uses underscores to avoid the '+' character which can cause issues
    in some git clients and shell scripts.

    Example: v1.2.0_lxgw1521_nerd340
    """
    # Strip 'v' prefix and dots for compact encoding: v1.521 -> 1521
    lxgw_compact = lxgw_tag.lstrip("v").replace(".", "")
    nerd_compact  = nerd_tag.lstrip("v").replace(".", "")
    return f"v{pkg_version}_lxgw{lxgw_compact}_nerd{nerd_compact}"


def set_gha_output(key: str, value: str) -> None:
    """Write a key=value pair to GitHub Actions $GITHUB_OUTPUT file."""
    gha_output = os.environ.get("GITHUB_OUTPUT")
    if gha_output:
        with open(gha_output, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        # Local dev: just print
        print(f"[GHA Output] {key}={value}")


def main():
    parser = argparse.ArgumentParser(
        description="Check upstream font versions and update versions.json"
    )
    parser.add_argument(
        "--versions-file",
        default="versions.json",
        help="Path to versions.json (default: versions.json)",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing versions.json",
    )
    args = parser.parse_args()

    versions_path = Path(args.versions_file)
    if not versions_path.exists():
        print(f"ERROR: {versions_path} not found.", file=sys.stderr)
        sys.exit(2)

    with open(versions_path) as f:
        versions = json.load(f)

    current_lxgw_tag = versions["upstream"]["lxgw_wenkai"]["tag"]
    current_nerd_tag = versions["upstream"]["meslo_nerd"]["tag"]
    current_pkg_ver  = versions["packaging"]["version"]

    print(f"Current versions: lxgw={current_lxgw_tag}, nerd={current_nerd_tag}")
    print("Checking upstream releases...")

    changed = False

    # --- Check LXGW WenKai ---
    try:
        lxgw_rel = get_latest_release("lxgw/LxgwWenKai", args.github_token)
        new_lxgw_tag = lxgw_rel["tag_name"]
        if new_lxgw_tag != current_lxgw_tag:
            print(f"  LXGW WenKai: {current_lxgw_tag} -> {new_lxgw_tag}  [NEW]")
            versions["upstream"]["lxgw_wenkai"]["tag"] = new_lxgw_tag
            versions["upstream"]["lxgw_wenkai"]["release_date"] = lxgw_rel["published_at"]
            changed = True
        else:
            print(f"  LXGW WenKai: {current_lxgw_tag}  [no change]")
    except Exception as e:
        print(f"  WARNING: Could not check LXGW WenKai: {e}", file=sys.stderr)

    # --- Check Nerd Fonts (also carries MesloLGM) ---
    try:
        nerd_rel = get_latest_release("ryanoasis/nerd-fonts", args.github_token)
        new_nerd_tag = nerd_rel["tag_name"]
        if new_nerd_tag != current_nerd_tag:
            print(f"  Nerd Fonts:  {current_nerd_tag} -> {new_nerd_tag}  [NEW]")
            versions["upstream"]["meslo_nerd"]["tag"] = new_nerd_tag
            versions["upstream"]["meslo_nerd"]["release_date"] = nerd_rel["published_at"]
            changed = True
        else:
            print(f"  Nerd Fonts:  {current_nerd_tag}  [no change]")
    except Exception as e:
        print(f"  WARNING: Could not check Nerd Fonts: {e}", file=sys.stderr)

    if not changed:
        # Even if upstream versions match, check whether a Release for the
        # current git_tag actually exists. On a brand-new repo the versions.json
        # is pre-populated but no Release has been published yet.
        current_git_tag = versions["packaging"]["git_tag"]
        own_repo = os.environ.get("GITHUB_REPOSITORY", "")
        if own_repo:
            tag_published = release_tag_exists(own_repo, current_git_tag, args.github_token)
            if not tag_published:
                print(f"No upstream changes, but Release '{current_git_tag}' not found.")
                print("Triggering initial build...")
                # Re-export current versions as outputs so trigger-build can dispatch.
                # prev_* are set to empty so build-release treats both as changed.
                set_gha_output("VERSIONS_CHANGED", "true")
                set_gha_output("NEW_VERSION", current_pkg_ver)
                set_gha_output("GIT_TAG", current_git_tag)
                set_gha_output("LXGW_TAG", current_lxgw_tag)
                set_gha_output("NERD_TAG", current_nerd_tag)
                set_gha_output("PREV_LXGW_TAG", "")
                set_gha_output("PREV_NERD_TAG", "")
                sys.exit(1)

        print("No upstream changes detected. Build not triggered.")
        set_gha_output("VERSIONS_CHANGED", "false")
        sys.exit(0)

    # --- Bump packaging version and rebuild tag ---
    new_pkg_ver = bump_minor(current_pkg_ver)
    new_lxgw = versions["upstream"]["lxgw_wenkai"]["tag"]
    new_nerd  = versions["upstream"]["meslo_nerd"]["tag"]
    new_git_tag = build_git_tag(new_pkg_ver, new_lxgw, new_nerd)

    print(f"Packaging version: {current_pkg_ver} -> {new_pkg_ver}")
    print(f"New git tag:       {new_git_tag}")

    # Persist previous upstream tags so build-release.yml can detect which
    # upstream actually changed without having to parse the git tag string.
    versions["packaging"]["prev_lxgw_tag"] = current_lxgw_tag
    versions["packaging"]["prev_nerd_tag"] = current_nerd_tag
    versions["packaging"]["version"]   = new_pkg_ver
    versions["packaging"]["last_built"] = datetime.now(timezone.utc).isoformat()
    versions["packaging"]["git_tag"]   = new_git_tag

    if args.dry_run:
        print("[DRY RUN] Would write versions.json:")
        print(json.dumps(versions, indent=2, ensure_ascii=False))
    else:
        with open(versions_path, "w") as f:
            json.dump(versions, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Updated {versions_path}")

    # Export variables for GitHub Actions
    set_gha_output("VERSIONS_CHANGED", "true")
    set_gha_output("NEW_VERSION", new_pkg_ver)
    set_gha_output("GIT_TAG", new_git_tag)
    set_gha_output("LXGW_TAG", new_lxgw)
    set_gha_output("NERD_TAG", new_nerd)
    set_gha_output("PREV_LXGW_TAG", current_lxgw_tag)
    set_gha_output("PREV_NERD_TAG", current_nerd_tag)

    sys.exit(1)  # Exit code 1 = changes found = trigger build workflow


if __name__ == "__main__":
    main()
