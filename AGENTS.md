# ENS Font — Agent Instructions

## Versioning policy

Version format: `X.Y.Z` (SemVer) tracked in `versions.json`.

| Column | When to bump | Examples |
|--------|-------------|---------|
| **Major** (`X`) | Breaking font or logic change | Donor font switch, family rename, glyph encoding overhaul |
| **Minor** (`Y`) | Upstream font update | New lxgw/nerd-fonts release detected by `check_versions.py` |
| **Patch** (`Z`) | Force rebuild, no content change | CI failure retry, infrastructure fix |

Rules:
- Minor bump resets patch to `0` (e.g. `1.1.3 → 1.2.0`)
- Major bump resets minor and patch to `0` (e.g. `1.2.0 → 2.0.0`)
- **Never touch `versions.json` without explicit user confirmation.**
- Minor bumps are automated by `check_versions.py` on upstream change — do not replicate this manually.
- Patch bumps are automated by `--bump-patch` flag on force rebuild — do not replicate this manually.
- Major bumps always require an explicit user instruction such as "bump major" or "release 2.0".

When the project is updated (e.g. scripts changed, CI modified, font logic
altered), recommend the appropriate version bump to the user based on the
nature of the change, then **wait for the user to confirm** before editing
`versions.json`.

When confirmed: edit `versions.json` (`version` and `git_tag` fields),
commit, then trigger `build-release.yml` via `workflow_dispatch`.

---

## Lessons learned

### Font merge (`scripts/merge.py`)

- **cmap format 4 is BMP-only.** Non-BMP codepoints (>U+FFFF, e.g. Nerd
  Fonts Plane 15 PUA) must go into format 12 subtables only. Putting them
  in format 4 causes `OverflowError` at compile time.
- **vmtx must be rebuilt after glyph transplant.** Transplanting ~11,646
  Meslo glyphs leaves vmtx with fewer entries than the total glyph count,
  causing macOS Font Book validation warnings. Rebuild vmtx for every glyph
  using `advanceHeight=vhea.advanceHeightMax`, `tsb=vhea.ascent-glyph.yMax`.
- **Single-pass transplant, donor overrides WenKai.** MesloLGMNerdFont
  already bundles Meslo + Nerd Fonts; no range filtering needed. Iterate
  donor cmap directly and overwrite any overlap. WenKai-only glyphs (CJK)
  are preserved naturally since they don't exist in donor cmap.
- **Glyph order must be sorted for reproducible binary output.** Sort new
  glyphs in `fix_glyph_order` to avoid non-deterministic TTF diffs.
- **WenKai has no Bold or Italic.** Use Medium as the CJK base for Bold and
  Bold Italic styles; use Regular as the CJK base for Italic.
- **compact_version must preserve dots.** `v3.4.0` and `v34.0` must produce
  distinct git tag tokens — strip the leading `v` but keep dots intact.
  (Previous bug: both mapped to `"340"`.)

### CI / workflow

- **`GITHUB_TOKEN` cannot trigger `repository_dispatch`** to launch other
  workflow runs — use `BOT_PAT` (fine-grained PAT with `contents:write` +
  `actions:write`) for any cross-workflow dispatch.
- **check_versions.py overwrites versions.json before build-release runs.**
  Store previous upstream tags as `prev_lxgw_tag` / `prev_nerd_tag` in
  `versions.json` and pass them via dispatch payload so build-release can
  detect which upstream actually changed for release notes.
- **First-run bootstrap.** On a new repo, versions.json is pre-populated so
  `check_versions.py` always sees "no change". Use `release_tag_exists()` to
  check whether the Release actually exists; if missing, exit 1 to trigger
  the initial build.
- **force_build with no upstream changes produces empty job outputs.** The
  `trigger-build` job must fall back to reading `versions.json` directly
  when `check-versions` outputs are empty strings.
- **Git tag push must be idempotent.** Check remote tag existence before
  pushing; skip if already present to avoid errors on re-runs.
- **Skip empty commits.** On first-run, `VERSIONS_CHANGED=true` but
  `versions.json` may have no staged diff. Guard with
  `git diff --cached --quiet` before committing.

### Security / tokens

- **Never pass tokens via CLI args.** Pass `GITHUB_TOKEN` via environment
  variable only to avoid process table exposure.
- **validate boolean inputs with parse_bool.** Reject unrecognized values
  with a clear error instead of silently treating them as `False`.

### OFL compliance

- **Reserved font names must not appear in family or PostScript name.**
  Prohibited: `LXGW`, `霞鶩`, `Klee`, `Meslo`. The OFL compliance check in
  `build-release.yml` enforces this after every build.
- **Upstream `@` mentions in release notes must be escaped.** Replace `@`
  with fullwidth `＠` to avoid accidentally pinging GitHub users in release
  notes.
