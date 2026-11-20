#!/usr/bin/env python3
"""Re-applies this fork's live-activity chip overrides after syncing upstream.

Upstream ships the stock chip labels. This fork keeps them for the states that
still say something useful (thinking, approval, question, done, failed, phone
control) and replaces only the generic working states, plus stops the island
from falling back to the full chat title.

Idempotent: run it after every merge; a clean tree means nothing to do.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ZH_CHIPS = {
    'liveChipWorking': '吃白饭',
    'liveChipJuggling': '吃白饭',
    'liveChipSweeping': '吃白饭',
}
EN_CHIPS = {key: 'Eating plain rice' for key in ZH_CHIPS}

CHIP_GETTER = 'chip?.takeIf { it.isNotBlank() }'


def patch_arb(path: Path, values: dict[str, str]) -> int:
    """Replace only the value of each key, leaving the file's layout alone."""
    if not path.is_file():
        raise SystemExit(f'missing {path}')
    text = path.read_text(encoding='utf-8')
    changed = 0
    for key, value in values.items():
        pattern = re.compile(r'("' + re.escape(key) + r'"\s*:\s*)"[^"]*"')
        text, hits = pattern.subn(lambda m, v=value: m.group(1) + '"' + v + '"', text)
        changed += hits
    if changed:
        # Bytes on purpose: text mode would turn LF into CRLF on a Windows host.
        path.write_bytes(text.encode('utf-8'))
    return changed


def patch_chip_words(path: Path) -> int:
    """Always hand the chip our own words instead of falling back to the title/clock."""
    if not path.is_file():
        raise SystemExit(f'missing {path}')
    text = path.read_text(encoding='utf-8')
    match = re.search(r'(?m)^([ \t]*)val chipWords: String\? get\(\) = (.+)$', text)
    if match is None:
        raise SystemExit(f'{path}: chipWords accessor not found; upstream changed the shape')
    if match.group(2).strip() == CHIP_GETTER:
        return 0
    text = text[:match.start(2)] + CHIP_GETTER + text[match.end(2):]
    path.write_text(text, encoding='utf-8')
    return 1


def main() -> int:
    changed = 0
    changed += patch_arb(ROOT / 'app/lib/l10n/parts/live_zh.arb', ZH_CHIPS)
    changed += patch_arb(ROOT / 'app/lib/l10n/parts/live_en.arb', EN_CHIPS)
    changed += patch_chip_words(
        ROOT / 'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/notify/LiveContent.kt'
    )
    print(f'chip overrides: {changed} edit(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
