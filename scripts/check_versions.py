#!/usr/bin/env python3
"""
check_versions.py - Polls upstream GitHub releases and updates versions.json.

Exit codes:
  0  No upstream changes (skip build)
  1  Upstream changed (trigger build)
  2  Error (bad config, network failure, etc.)

GitHub Actions output variables written to $GITHUB_OUTPUT:
  VERSIONS_CHANGED  true | false
  NEW_VERSION       e.g. 3.1.0
  GIT_TAG           e.g. v3.1.0_lxgw1.521_meslo-lgsdz_nerd3.4.0
  LXGW_TAG          e.g. v1.521
  NERD_TAG          e.g. v3.4.0
  PREV_LXGW_TAG     e.g. v1.521
  PREV_NERD_TAG     e.g. v3.4.0

Usage:
    GITHUB_TOKEN=... python scripts/check_versions.py \
        --versions-file versions.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _get_with_retry(
    url: str, headers: dict, timeout: int = 30, retries: int = 3
) -> "requests.Response":
    import requests

    last_exc = None
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(2 ** attempt)
        try:
            return requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
    raise last_exc


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

    try:
        resp = _get_with_retry(url, headers=headers, timeout=30)
    except Exception as e:
        print(f"WARNING: Could not check release tag '{tag}': {e}", file=sys.stderr)
        return True
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    print(
        f"WARNING: Unexpected status {resp.status_code} checking release tag '{tag}'",
        file=sys.stderr,
    )
    return True


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

    resp = _get_with_retry(url, headers=headers, timeout=30)
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
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format (expected X.Y.Z): {version!r}")
    major, minor, _ = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{major}.{minor + 1}.0"


def bump_patch(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format (expected X.Y.Z): {version!r}")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{major}.{minor}.{patch + 1}"


def compact_version(raw: str) -> str:
    """
    Strips leading 'v'/'V' prefix but preserves dots to avoid collisions.
    """
    return raw.lstrip("vV")


def build_git_tag(pkg_version: str, lxgw_tag: str, nerd_tag: str) -> str:
    """
    Construct the git tag encoding package version, tracked upstreams, and
    the selected donor family.

    Example: v3.0.0_lxgw1.521_meslo-lgsdz_nerd3.4.0
    """
    lxgw_compact = compact_version(lxgw_tag)
    nerd_compact = compact_version(nerd_tag)
    return f"v{pkg_version}_lxgw{lxgw_compact}_meslo-lgsdz_nerd{nerd_compact}"


def set_gha_output(key: str, value: str) -> None:
    gha_output = os.environ.get("GITHUB_OUTPUT")
    if gha_output:
        with open(gha_output, "a") as f:
            f.write(f"{key}={value}\n")
    else:
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
        "--dry-run",
        action="store_true",
        help="Print what would change without writing versions.json",
    )
    parser.add_argument(
        "--bump-patch",
        action="store_true",
        help="Bump patch version for a force rebuild (no upstream check)",
    )
    args = parser.parse_args()
    github_token = os.environ.get("GITHUB_TOKEN", "")

    versions_path = Path(args.versions_file)
    if not versions_path.exists():
        print(f"ERROR: {versions_path} not found.", file=sys.stderr)
        sys.exit(2)

    with open(versions_path) as f:
        versions = json.load(f)

    if args.bump_patch:
        current_pkg_ver = versions["packaging"]["version"]
        current_lxgw = versions["upstream"]["lxgw_wenkai"]["tag"]
        current_nerd = versions["upstream"]["nerd_fonts"]["tag"]

        new_pkg_ver = bump_patch(current_pkg_ver)
        new_git_tag = build_git_tag(new_pkg_ver, current_lxgw, current_nerd)

        print(f"Force rebuild: bumping patch {current_pkg_ver} -> {new_pkg_ver}")
        print(f"New git tag: {new_git_tag}")

        versions["packaging"]["version"] = new_pkg_ver
        versions["packaging"]["last_built"] = datetime.now(timezone.utc).isoformat()
        versions["packaging"]["git_tag"] = new_git_tag

        if args.dry_run:
            print("[DRY RUN] Would write versions.json:")
            print(json.dumps(versions, indent=2, ensure_ascii=False))
        else:
            with open(versions_path, "w") as f:
                json.dump(versions, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"Updated {versions_path}")

        set_gha_output("NEW_VERSION", new_pkg_ver)
        set_gha_output("GIT_TAG", new_git_tag)
        set_gha_output("LXGW_TAG", current_lxgw)
        set_gha_output("NERD_TAG", current_nerd)
        sys.exit(0)

    current_lxgw_tag = versions["upstream"]["lxgw_wenkai"]["tag"]
    current_nerd_tag = versions["upstream"]["nerd_fonts"]["tag"]
    current_pkg_ver = versions["packaging"]["version"]
    lxgw_repo = versions["upstream"]["lxgw_wenkai"]["repo"]
    nerd_repo = versions["upstream"]["nerd_fonts"]["repo"]

    print(f"Current versions: lxgw={current_lxgw_tag}, nerd={current_nerd_tag}")
    print("Checking upstream releases...")

    changed = False
    errors = []

    try:
        lxgw_rel = get_latest_release(lxgw_repo, github_token)
        new_lxgw_tag = lxgw_rel["tag_name"]
        if new_lxgw_tag != current_lxgw_tag:
            print(f"  LXGW WenKai TC: {current_lxgw_tag} -> {new_lxgw_tag}  [NEW]")
            versions["upstream"]["lxgw_wenkai"]["tag"] = new_lxgw_tag
            versions["upstream"]["lxgw_wenkai"]["release_date"] = lxgw_rel[
                "published_at"
            ]
            changed = True
        else:
            print(f"  LXGW WenKai TC: {current_lxgw_tag}  [no change]")
    except Exception as e:
        print(f"  WARNING: Could not check LXGW WenKai TC: {e}", file=sys.stderr)
        errors.append(f"LXGW WenKai TC check failed: {e}")

    try:
        nerd_rel = get_latest_release(nerd_repo, github_token)
        new_nerd_tag = nerd_rel["tag_name"]
        if new_nerd_tag != current_nerd_tag:
            print(f"  Nerd Fonts: {current_nerd_tag} -> {new_nerd_tag}  [NEW]")
            versions["upstream"]["nerd_fonts"]["tag"] = new_nerd_tag
            versions["upstream"]["nerd_fonts"]["release_date"] = nerd_rel[
                "published_at"
            ]
            changed = True
        else:
            print(f"  Nerd Fonts: {current_nerd_tag}  [no change]")
    except Exception as e:
        print(f"  WARNING: Could not check Nerd Fonts: {e}", file=sys.stderr)
        errors.append(f"Nerd Fonts check failed: {e}")

    if errors:
        print(
            "\nERROR: Upstream release checks failed; aborting to avoid false 'no change'.",
            file=sys.stderr,
        )
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(2)

    if not changed:
        current_git_tag = versions["packaging"]["git_tag"]
        own_repo = os.environ.get("GITHUB_REPOSITORY", "")
        print(f"GITHUB_REPOSITORY={own_repo!r}")
        if own_repo:
            tag_published = release_tag_exists(own_repo, current_git_tag, github_token)
            print(f"Release tag '{current_git_tag}' exists: {tag_published}")
            if not tag_published:
                print(
                    f"No upstream changes, but Release '{current_git_tag}' not found."
                )
                print("Triggering initial build...")
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

    new_pkg_ver = bump_minor(current_pkg_ver)
    new_lxgw = versions["upstream"]["lxgw_wenkai"]["tag"]
    new_nerd = versions["upstream"]["nerd_fonts"]["tag"]
    new_git_tag = build_git_tag(new_pkg_ver, new_lxgw, new_nerd)

    print(f"Packaging version: {current_pkg_ver} -> {new_pkg_ver}")
    print(f"New git tag:       {new_git_tag}")

    versions["packaging"]["prev_lxgw_tag"] = current_lxgw_tag
    versions["packaging"]["prev_nerd_tag"] = current_nerd_tag
    versions["packaging"]["version"] = new_pkg_ver
    versions["packaging"]["last_built"] = datetime.now(timezone.utc).isoformat()
    versions["packaging"]["git_tag"] = new_git_tag

    if args.dry_run:
        print("[DRY RUN] Would write versions.json:")
        print(json.dumps(versions, indent=2, ensure_ascii=False))
    else:
        with open(versions_path, "w") as f:
            json.dump(versions, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Updated {versions_path}")

    set_gha_output("VERSIONS_CHANGED", "true")
    set_gha_output("NEW_VERSION", new_pkg_ver)
    set_gha_output("GIT_TAG", new_git_tag)
    set_gha_output("LXGW_TAG", new_lxgw)
    set_gha_output("NERD_TAG", new_nerd)
    set_gha_output("PREV_LXGW_TAG", current_lxgw_tag)
    set_gha_output("PREV_NERD_TAG", current_nerd_tag)

    sys.exit(1)


if __name__ == "__main__":
    main()
