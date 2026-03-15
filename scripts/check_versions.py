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
  GIT_TAG           e.g. v1.2.0_lxgw1.521_jbsans_jbm2.304_nerd3.4.0
  LXGW_TAG          e.g. v1.521
  NERD_TAG          e.g. v3.4.0
  JBM_TAG           e.g. v2.304
  PREV_JBM_TAG      e.g. v2.304 (previous JBM tag for change detection)
  JBSANS_VERSION    e.g. 2.304 (scraped from JetBrains CDN, "unknown" if not found)

Usage:
    GITHUB_TOKEN=... python scripts/check_versions.py \\
        --versions-file versions.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

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

    import requests

    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"WARNING: Could not check release tag '{tag}': {e}", file=sys.stderr)
        # Assume tag exists on network error to avoid false rebuild triggers
        return True
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    # Unexpected status (5xx, 403, etc.) — treat as unknown, assume exists
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

    import requests

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


def bump_patch(version: str) -> str:
    """Bump patch version: '1.1.0' -> '1.1.1'"""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format (expected X.Y.Z): {version!r}")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{major}.{minor}.{patch + 1}"


def compact_version(raw: str) -> str:
    """
    Convert version strings to tag-safe compact form.
    Strips leading 'v'/'V' prefix but preserves dots to avoid collisions
    (e.g. "v3.4.0" vs "v34.0" must produce distinct results).
    Example: "v1.521" -> "1.521", "v3.4.0" -> "3.4.0".
    """
    return raw.lstrip("vV")


def get_jetbrains_sans_version(source_url: str) -> str:
    """
    Detect the current JetBrains Sans version from the JetBrains CDN.

    The version is embedded in the variable font URL inside the default-page CSS
    (e.g. .../jetbrains-sans/google-fonts/v1.309/variable/JetBrainsSans[wght].woff2).
    The homepage HTML itself does not contain font URLs (they are in CSS files).

    Returns "unknown" on failure — non-fatal, build still proceeds.
    """
    import requests

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        # Step 1: fetch homepage to locate the default-page CSS URL
        resp = requests.get(source_url, headers=headers, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"WARNING: Could not fetch JetBrains homepage: {e}", file=sys.stderr)
        return "unknown"

    m = re.search(r'"(/_assets/default-page\.[a-f0-9]+\.css)"', html)
    if not m:
        print("WARNING: Could not find default-page CSS URL in JetBrains homepage.", file=sys.stderr)
        return "unknown"

    css_url = f"https://www.jetbrains.com{m.group(1)}"
    try:
        # Step 2: fetch CSS and extract version from the variable font URL
        resp = requests.get(css_url, headers=headers, timeout=30)
        resp.raise_for_status()
        css = resp.text
    except Exception as e:
        print(f"WARNING: Could not fetch JetBrains CSS: {e}", file=sys.stderr)
        return "unknown"

    m = re.search(
        r"resources\.jetbrains\.com/storage/jetbrains-sans/google-fonts/"
        r"(v[\d.]+)/variable/JetBrainsSans",
        css,
    )
    if m:
        return m.group(1).lstrip("v")

    print("WARNING: JetBrains Sans version not found in CSS.", file=sys.stderr)
    return "unknown"


def build_git_tag(
    pkg_version: str,
    lxgw_tag: str,
    jbm_tag: str,
    nerd_tag: str,
) -> str:
    """
    Construct the git tag encoding all upstream versions.
    Uses underscores to avoid the '+' character which can cause issues
    in some git clients and shell scripts.

    Example: v1.2.0_lxgw1.521_jbsans_jbm2.304_nerd3.4.0
    """
    lxgw_compact = compact_version(lxgw_tag)
    jbm_compact = compact_version(jbm_tag)
    nerd_compact = compact_version(nerd_tag)
    return f"v{pkg_version}_lxgw{lxgw_compact}_jbsans_jbm{jbm_compact}_nerd{nerd_compact}"


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
        current_jbm = versions["upstream"]["jetbrains_mono"]["tag"]

        new_pkg_ver = bump_patch(current_pkg_ver)
        new_git_tag = build_git_tag(new_pkg_ver, current_lxgw, current_jbm, current_nerd)

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
        set_gha_output("JBM_TAG", current_jbm)
        sys.exit(0)

    current_lxgw_tag = versions["upstream"]["lxgw_wenkai"]["tag"]
    current_nerd_tag = versions["upstream"]["nerd_fonts"]["tag"]
    current_jbm_tag = versions["upstream"]["jetbrains_mono"]["tag"]
    current_pkg_ver = versions["packaging"]["version"]
    lxgw_repo = versions["upstream"]["lxgw_wenkai"]["repo"]
    nerd_repo = versions["upstream"]["nerd_fonts"]["repo"]
    jbm_repo = versions["upstream"]["jetbrains_mono"]["repo"]
    jbsans_source = versions["upstream"]["jetbrains_sans"]["source_url"]

    print(f"Current versions: lxgw={current_lxgw_tag}, jbm={current_jbm_tag}, nerd={current_nerd_tag}")
    print("Checking upstream releases...")
    print("(JetBrains Sans version is scraped at build time by fetch_jbsans.py)")

    changed = False
    errors = []

    # --- Check LXGW WenKai TC ---
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

    # --- Check Nerd Fonts (carries NerdFontsSymbolsOnly + JetBrainsMono Nerd Font) ---
    try:
        nerd_rel = get_latest_release(nerd_repo, github_token)
        new_nerd_tag = nerd_rel["tag_name"]
        if new_nerd_tag != current_nerd_tag:
            print(f"  Nerd Fonts:  {current_nerd_tag} -> {new_nerd_tag}  [NEW]")
            versions["upstream"]["nerd_fonts"]["tag"] = new_nerd_tag
            versions["upstream"]["nerd_fonts"]["release_date"] = nerd_rel[
                "published_at"
            ]
            changed = True
        else:
            print(f"  Nerd Fonts:  {current_nerd_tag}  [no change]")
    except Exception as e:
        print(f"  WARNING: Could not check Nerd Fonts: {e}", file=sys.stderr)
        errors.append(f"Nerd Fonts check failed: {e}")

    # --- Check JetBrains Mono ---
    try:
        jbm_rel = get_latest_release(jbm_repo, github_token)
        new_jbm_tag = jbm_rel["tag_name"]
        if new_jbm_tag != current_jbm_tag:
            print(f"  JetBrains Mono: {current_jbm_tag} -> {new_jbm_tag}  [NEW]")
            versions["upstream"]["jetbrains_mono"]["tag"] = new_jbm_tag
            versions["upstream"]["jetbrains_mono"]["release_date"] = jbm_rel[
                "published_at"
            ]
            changed = True
        else:
            print(f"  JetBrains Mono: {current_jbm_tag}  [no change]")
    except Exception as e:
        print(f"  WARNING: Could not check JetBrains Mono: {e}", file=sys.stderr)
        errors.append(f"JetBrains Mono check failed: {e}")

    # --- Check JetBrains Sans (web scrape, informational only — build fetches it fresh) ---
    try:
        jbsans_ver = get_jetbrains_sans_version(jbsans_source)
        prev_jbsans_ver = versions["upstream"]["jetbrains_sans"].get("version", "unknown")
        if jbsans_ver != "unknown" and jbsans_ver != prev_jbsans_ver:
            print(f"  JetBrains Sans: {prev_jbsans_ver} -> {jbsans_ver}  [NEW]")
            versions["upstream"]["jetbrains_sans"]["version"] = jbsans_ver
            changed = True
        else:
            print(f"  JetBrains Sans: {jbsans_ver}  [{'no change' if jbsans_ver != 'unknown' else 'version undetected'}]")
    except Exception as e:
        print(f"  WARNING: JetBrains Sans version check failed: {e}", file=sys.stderr)
        # Non-fatal: JetBrains Sans is always re-fetched at build time

    if errors:
        print(
            "\nERROR: Upstream release checks failed; aborting to avoid false 'no change'.",
            file=sys.stderr,
        )
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(2)

    if not changed:
        # Even if upstream versions match, check whether a Release for the
        # current git_tag actually exists. On a brand-new repo the versions.json
        # is pre-populated but no Release has been published yet.
        current_git_tag = versions["packaging"]["git_tag"]
        own_repo = os.environ.get("GITHUB_REPOSITORY", "")
        print(f"GITHUB_REPOSITORY={own_repo!r}")
        if own_repo:
            tag_published = release_tag_exists(
                own_repo, current_git_tag, github_token
            )
            print(f"Release tag '{current_git_tag}' exists: {tag_published}")
            if not tag_published:
                print(
                    f"No upstream changes, but Release '{current_git_tag}' not found."
                )
                print("Triggering initial build...")
                # Re-export current versions as outputs so trigger-build can dispatch.
                # prev_* are set to empty so build-release treats both as changed.
                set_gha_output("VERSIONS_CHANGED", "true")
                set_gha_output("NEW_VERSION", current_pkg_ver)
                set_gha_output("GIT_TAG", current_git_tag)
                set_gha_output("LXGW_TAG", current_lxgw_tag)
                set_gha_output("NERD_TAG", current_nerd_tag)
                set_gha_output("JBM_TAG", current_jbm_tag)
                set_gha_output("PREV_LXGW_TAG", "")
                set_gha_output("PREV_NERD_TAG", "")
                set_gha_output("PREV_JBM_TAG", "")
                sys.exit(1)

        print("No upstream changes detected. Build not triggered.")
        set_gha_output("VERSIONS_CHANGED", "false")
        sys.exit(0)

    # --- Bump packaging version and rebuild tag ---
    new_pkg_ver = bump_minor(current_pkg_ver)
    new_lxgw = versions["upstream"]["lxgw_wenkai"]["tag"]
    new_nerd = versions["upstream"]["nerd_fonts"]["tag"]
    new_jbm = versions["upstream"]["jetbrains_mono"]["tag"]
    new_git_tag = build_git_tag(
        new_pkg_ver,
        new_lxgw,
        new_jbm,
        new_nerd,
    )

    print(f"Packaging version: {current_pkg_ver} -> {new_pkg_ver}")
    print(f"New git tag:       {new_git_tag}")

    # Persist previous upstream tags so build-release.yml can detect which
    # upstream actually changed without having to parse the git tag string.
    versions["packaging"]["prev_lxgw_tag"] = current_lxgw_tag
    versions["packaging"]["prev_nerd_tag"] = current_nerd_tag
    versions["packaging"]["prev_jbm_tag"] = current_jbm_tag
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

    # Export variables for GitHub Actions
    set_gha_output("VERSIONS_CHANGED", "true")
    set_gha_output("NEW_VERSION", new_pkg_ver)
    set_gha_output("GIT_TAG", new_git_tag)
    set_gha_output("LXGW_TAG", new_lxgw)
    set_gha_output("NERD_TAG", new_nerd)
    set_gha_output("JBM_TAG", new_jbm)
    set_gha_output("PREV_LXGW_TAG", current_lxgw_tag)
    set_gha_output("PREV_NERD_TAG", current_nerd_tag)
    set_gha_output("PREV_JBM_TAG", current_jbm_tag)

    sys.exit(1)  # Exit code 1 = changes found = trigger build workflow


if __name__ == "__main__":
    main()
