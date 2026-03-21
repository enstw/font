import logging
import sys
from fontTools.ttLib import TTFont
from .cmap import get_best_cmap

log = logging.getLogger(__name__)

def assert_donor_is_mono(donor: TTFont, donor_path: str) -> None:
    """
    Verify that the donor font is monospaced by checking if all ASCII
    printable characters share the same advance width.
    """
    cmap = get_best_cmap(donor)
    hmtx = donor["hmtx"]
    widths = set()
    for cp in range(0x0020, 0x007F):
        if cp in cmap:
            gname = cmap[cp]
            if gname in hmtx.metrics:
                widths.add(hmtx.metrics[gname][0])

    if len(widths) > 1:
        log.error(
            f"Donor font '{donor_path}' is NOT monospaced! "
            f"ASCII widths found: {sorted(widths)}"
        )
        sys.exit(1)


def validate_monospace_integrity(
    font: TTFont, is_mono: bool = False, is_mono_prop: bool = False
) -> None:
    """
    Verify half-width glyphs have the expected uniform advance width.

    For mono and mono-prop builds: checks ASCII + Latin Extended-A/B + Greek & Coptic + Cyrillic
    + Greek Extended + Nerd PUA (BMP and Plane 15). Emits log.error + sys.exit(1) on any violation.
    Even for mono-prop, PUA icons are expected to be multiples of the cell width.

    For non-mono builds: checks ASCII only, issues a warning (not error).
    """
    cmap = get_best_cmap(font)
    hmtx = font["hmtx"]

    # Determine cell width from ASCII printable range
    ascii_widths = set()
    for cp in range(0x0020, 0x007F):
        if cp in cmap:
            gname = cmap[cp]
            if gname in hmtx.metrics:
                ascii_widths.add(hmtx.metrics[gname][0])

    if not ascii_widths:
        log.warning("No ASCII glyphs found - cannot verify monospace integrity")
        return

    if len(ascii_widths) > 1:
        msg = (
            f"ASCII glyphs have {len(ascii_widths)} different advance widths: "
            f"{sorted(ascii_widths)}."
        )
        if is_mono or is_mono_prop:
            log.error(f"MONOSPACE INTEGRITY FAIL: {msg}")
            sys.exit(1)
        else:
            log.warning(f"MONOSPACE INTEGRITY: {msg} Expected for non-mono builds.")
            return

    cell_width = ascii_widths.pop()
    log.info(f"Monospace integrity: ASCII cell width = {cell_width} units")

    if not is_mono and not is_mono_prop:
        log.info("Monospace integrity OK (ASCII-only check for non-mono build)")
        return

    # Extended check for mono and mono-prop builds
    extended_ranges = [
        (0x0100, 0x024F, "Latin Extended-A/B"),
        (0x0370, 0x03FF, "Greek & Coptic"),
        (0x0400, 0x04FF, "Cyrillic"),
        (0x1F00, 0x1FFF, "Greek Extended"),
        (0xE000, 0xF8FF, "Nerd PUA BMP"),
        (0xF0000, 0xFFFFF, "Nerd PUA Plane 15"),
    ]

    violations = []
    for start, end, block_name in extended_ranges:
        for cp in range(start, end + 1):
            if cp in cmap:
                gname = cmap[cp]
                if gname in hmtx.metrics:
                    adv = hmtx.metrics[gname][0]
                    if adv != 0 and adv % cell_width != 0:
                        violations.append((cp, adv, block_name))

    if violations:
        log.error(
            f"MONOSPACE INTEGRITY FAIL: {len(violations)} glyphs with non-multiple advance "
            f"width (expected multiple of {cell_width}):"
        )
        for cp, adv, block_name in violations[:10]:
            log.error(f"  U+{cp:04X} in {block_name}: advance={adv}")
        if len(violations) > 10:
            log.error(f"  ... and {len(violations) - 10} more")
        sys.exit(1)

    log.info(f"Monospace integrity OK: all checked glyphs are multiples of {cell_width} units (extended ranges)")
