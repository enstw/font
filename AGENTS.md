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
- **vmtx must be rebuilt after glyph transplant.** Transplanting donor
  glyphs leaves vmtx with fewer entries than the total glyph count, causing
  macOS Font Book validation warnings. Rebuild vmtx for every glyph using
  `advanceHeight=vhea.advanceHeightMax`, `tsb=vhea.ascent-glyph.yMax`.
- **Single-pass transplant, donor overrides base unconditionally.** Iterate
  donor cmap and overwrite any overlap — no range filtering, no code-page
  logic. Base-only glyphs (text from WenKai) are preserved naturally since
  they don't exist in the donor cmap. Since v4 the donor is Symbols Nerd
  Font (PUA icons only), so the only real overlap is the handful of
  Powerline glyphs both fonts carry — donor still wins. Do NOT add range
  filtering to the ICON donor; the fonts naturally partition the Unicode
  space. (The terminal-furniture donor below is the deliberate exception:
  it transplants an explicit curated codepoint list, nothing else.)
- **Terminals allot East-Asian-ambiguous chars ONE cell; LXGW draws them
  full-width.** Box drawing (U+2500-257F), block elements (U+2580-259F),
  `…`, arrows, checkmarks, geometric shapes etc. are wcwidth-narrow, but
  LXGW draws them CJK-style on the full 1000-unit em — the ink overlaps the
  next terminal cell (v4.0 regression: `─(` and `…/` collided in prompts).
  Fix: `transplant_terminal_furniture` pulls the curated set from a PINNED
  Meslo LGSDZ NF Mono (battle-tested Bitstream Vera-lineage terminal
  glyphs) for Mono/Mono Prop builds and fits it to the 500 cell — fill
  glyphs get an x-only map (y is fix_block_elements' job), symbols get a
  uniform baseline-anchored scale, and codepoints LXGW already draws at one
  cell keep the LXGW design. CJK-flavored symbols (※ ‼ ①-⑳ ❶-➓ hexagrams)
  are deliberately NOT in the list. The Meslo tag is pinned in
  build-release.yml and NOT tracked by check_versions.py — these glyphs
  never change upstream, so it must never cause a version bump.
- **Do NOT rescale non-Powerline Nerd icons in non-strict-mono builds —
  except the Mono Prop 2-cell ink clamp.** The symbols-only donor draws
  icons larger than the old patcher-fitted text donors relative to LXGW's
  letterforms ('M' ink 437 vs Atkinson's 517 units), and v4.1.0 tried
  ICON_SCALE = 0.85 to compensate — but the scale anchors at x=0 so the
  shrunken ink sat left-justified in its cell, and the user explicitly
  prefers the larger native icon size (reverted in v4.1.x). Mono Prop and
  proportional builds keep the donor's native icon geometry untouched;
  only strict Mono fits icons (into one cell, centered, via fit_all).
  The ONE exception (v4.1.x): terminals lay out by wcwidth — a PUA icon
  gets one cell regardless of its advance, and the prompt convention
  ("icon + trailing space") buys one more — so Mono Prop icons whose INK
  exceeds 2 cells (~420 of ~10,400; e.g. U+F108 at 1039 units grazed the
  next letter, U+F327 at 1335 plowed through it) are scaled down per-glyph
  to the 2-cell budget minus ICON_INK_GAP per side, centered, advance
  pinned to 2 cells. Advances cannot fix this class of collision;
  ink is the only lever the font has in a terminal.
- **The symbols-only donor is not pre-fitted to the base cell.** When the
  donor was a Nerd-patched text font, the NF patcher had already scaled
  icons to the donor's cell. Symbols Nerd Font glyphs live on their own
  em/line box, so `fit_nerd_icons` must run after transplant: Powerline
  separators stretch to fill `[hhea.descent, hhea.ascent]` edge-to-edge,
  and strict-Mono builds scale ALL icons into one cell with a single shared
  affine transform (per-glyph bbox fitting would break the icon set's
  internal alignment).
- **Block elements (U+2580–U+259F) AND box drawing (U+2500–U+257F) must be
  rescaled after merge.** LXGW draws them on its typographic design box
  (e.g. [-120, 880]), but terminals size the cell from hhea metrics
  (e.g. [-241, 928]) — stacked blocks and vertical strokes show horizontal
  gaps without correction. `fix_block_elements` rescales y-coords from the
  FULL BLOCK's raw bounds to `[hhea.descent, hhea.ascent]` using ONE linear
  transform shared by the whole range, so midlines and block boundaries
  keep meeting at the cell center. Only y-coords are touched; x-coords
  preserve the intentional horizontal bleed for seamless tiling.
- **Glyph order must be sorted for reproducible binary output.** Sort new
  glyphs in `fix_glyph_order` to avoid non-deterministic TTF diffs.
- **WenKai has no Bold or Italic.** Use Medium as the CJK base for Bold styles; use Light as the CJK base for Light styles; use Regular as the CJK base for others.
- **compact_version must preserve dots.** `v3.4.0` and `v34.0` must produce
  distinct git tag tokens — strip the leading `v` but keep dots intact.
  (Previous bug: both mapped to `"340"`.)

### GitHub Actions

- **Always use the latest version when introducing a new action.** Check the action's releases page before adding it. Never copy an old version from an existing workflow — look it up fresh. Floating major tags (e.g. `@v4`) are acceptable when the action author maintains them to track the latest release in that major version.

### CI / workflow

- **`GITHUB_TOKEN` cannot trigger `repository_dispatch`** to launch other
  workflow runs — use `BOT_PAT` (fine-grained PAT with `contents:write` +
  `actions:write`) for any cross-workflow dispatch.
- **check_versions.py overwrites versions.json before build-release runs.**
  Store previous upstream tags as `prev_lxgw_tag` / `prev_nerd_tag` /
  `prev_jbm_tag` in `versions.json` and pass them via dispatch payload so
  build-release can detect which upstream actually changed for release notes.
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
  Prohibited: `LXGW`, `霞鶩`, `Klee`. The OFL compliance check in
  `build-release.yml` enforces this after every build.
- **Upstream `@` mentions in release notes must be escaped.** Replace `@`
  with fullwidth `＠` to avoid accidentally pinging GitHub users in release
  notes.
