r"""Repository hygiene: no unresolved merge markers may be committed.

An unresolved conflict was once committed to a draft branch, and `spec_audit` exited 0 on it: the
markers are invisible to every semantic check this repository has. This gate is deliberately narrow
and mechanical -- it looks for the three marker prefixes git writes and nothing else:

    <<<<<<<    current side
    >>>>>>>    incoming side
    |||||||    base side (diff3 style)

`=======` is deliberately NOT checked: it is exactly seven equals signs with nothing else on the
line, which is also a Markdown setext heading underline, so a check on it would fail on prose rather
than on damage -- and a gate that cries wolf gets disabled.

Scope is *tracked text files*: untracked scratch, and any file git considers binary, are skipped.
"""

from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The three markers git writes around an unresolved hunk. `=======` is excluded on purpose.
MARKER_PREFIXES = ("<<<<<<<", ">>>>>>>", "|||||||")


def _tracked_text_files():
    listing = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    assert listing.returncode == 0, f"git ls-files failed: {listing.stderr.strip()}"
    for rel in listing.stdout.splitlines():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def test_no_unresolved_merge_markers_are_committed():
    offenders = []
    for path, text in _tracked_text_files():
        for number, line in enumerate(text.splitlines(), 1):
            if line.startswith(MARKER_PREFIXES):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line[:48]!r}")
    assert offenders == [], "unresolved merge markers are present: " + "; ".join(offenders[:10])
