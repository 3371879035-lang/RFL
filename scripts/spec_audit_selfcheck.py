"""Power test for ``spec_audit``'s amendment-registration checks.

``spec_audit`` reported a *closed reference graph* while A71 and A72 were
un-logged. The check was not wrong about the graph; it was wrong about what
constitutes an edge. The lesson this project keeps re-learning is that a passing
check is evidence only that the check did not look, so the guardrail added for
A71/A72 must itself be shown to fail on demand.

This script copies ``docs/rebuild/`` to a temporary directory, breaks exactly one
thing at a time, and asserts that the audit reports the corresponding failure.
The real documents are never modified.

Usage
-----
    python scripts/spec_audit_selfcheck.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import spec_audit  # noqa: E402


def run_with(mutate) -> dict:
    """Run the audit against a temp copy of the spec dir, mutated in place."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "rebuild"
        shutil.copytree(spec_audit.SPEC_DIR, dst)
        for md in dst.glob("*.md"):
            md.write_text(mutate(md.name, md.read_text(encoding="utf-8")),
                          encoding="utf-8")
        saved = spec_audit.SPEC_DIR
        spec_audit.SPEC_DIR = dst
        try:
            return spec_audit.audit()
        finally:
            spec_audit.SPEC_DIR = saved


def replace_once(text: str, old: str, new: str) -> str:
    assert old in text, f"fixture drifted: {old!r} not found"
    return text.replace(old, new, 1)


failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


print("spec_audit power test -- each case breaks one thing and expects a report")

# --- baseline: the unmutated tree must report nothing dangling. A69 used to be
# the one known historical gap, and this assertion pinned it; now that A69 is
# logged, the baseline is empty and the A69 case below keeps that hole closed.
base = run_with(lambda name, text: text)
print(f"\nbaseline: dangling = {base['dangling_amendments']}")
check("baseline dangling set is empty ([] -- A69 is logged)",
      base["dangling_amendments"] == [],
      f"got {base['dangling_amendments']}")
check("baseline defines A69, A71 and A72",
      {"A69", "A71", "A72"} <= set(base["amendments_defined"]),
      f"missing {sorted({'A69', 'A71', 'A72'} - set(base['amendments_defined']))}")
check("baseline scans a non-trivial number of headings",
      base["numbered_headings_scanned_in_other_docs"] > 100,
      f"scanned {base['numbered_headings_scanned_in_other_docs']}")
check("baseline finds amendment-naming headings",
      len(base["amendments_named_in_other_doc_headings"]) >= 6,
      f"{base['amendments_named_in_other_doc_headings']}")

# --- case 1: remove A71's formal heading from 12. A71 is still named in a
# heading in `17`, so the reference must go dangling.
print("\ncase 1: delete the `## 57. A71 -- ...` heading from 12-AMENDMENTS.md")
r1 = run_with(lambda name, text: (
    replace_once(text, "## 57. A71 \u2014", "## 57. Z71 \u2014")
    if name == "12-AMENDMENTS.md" else text))
check("A71 is reported dangling when its heading is removed",
      "A71" in r1["dangling_amendments"], f"dangling={r1['dangling_amendments']}")
check("the report names the heading scan as the origin",
      any("heading" in s for s in r1["amendment_reference_sources"].get("A71", [])),
      f"{r1['amendment_reference_sources'].get('A71')}")

# --- case 2: remove A72's *level-2* heading. This is the form the first version
# of the scan silently missed, so it regresses the exact near-miss.
print("\ncase 2: delete the `## 8. A72 -- ...` heading from 17 (the level-2 form)")
r2 = run_with(lambda name, text: (
    replace_once(text, "## 8. A72 \u2014", "## 8. Z72 \u2014")
    if name == "17-V02R-METHOD-CONTRACT.md" else text))
check("A72 is no longer referenced once its level-2 heading is renamed",
      "A72" not in r2["amendments_referenced"],
      f"referenced={r2['amendments_referenced']}")
check("A71 remains referenced (the sub-numbered form still matches)",
      "A71" in r2["amendments_referenced"])

# --- case 3: a `logged as Axx` declaration for a number that is not logged.
print("\ncase 3: add a `logged as **A99**` status line to 17")
r3 = run_with(lambda name, text: (
    replace_once(text, "Status: frozen \u2014 logged as **A69**.",
                 "Status: frozen \u2014 logged as **A69**.\nStatus: frozen \u2014 logged as **A99**.")
    if name == "17-V02R-METHOD-CONTRACT.md" else text))
check("an un-logged `logged as` declaration is reported dangling",
      "A99" in r3["dangling_amendments"], f"dangling={r3['dangling_amendments']}")
check("the report attributes it to the 'logged as' scan",
      any("logged as" in s for s in r3["amendment_reference_sources"].get("A99", [])),
      f"{r3['amendment_reference_sources'].get('A99')}")

# --- case 4: a range must take both endpoints.
print("\ncase 4: add a heading naming the range `A55-A77` to document 13")
r4 = run_with(lambda name, text: (
    replace_once(text, "## 10. ", "## 10. A55\u2013A77 boundary note\n\n## 10. ")
    if name == "13-GATE-L-FAILURE.md" else text))
check("a range endpoint that is un-logged is reported",
      "A77" in r4["dangling_amendments"], f"dangling={r4['dangling_amendments']}")
check("the logged endpoint of the range is not falsely reported",
      "A55" not in r4["dangling_amendments"])

# --- case 5: the defined set must come only from formal headings. A bare
# mention of a new number must not be able to define it.
print("\ncase 5: a bare prose mention of A88 must not define it")
r5 = run_with(lambda name, text: (
    replace_once(text, "## 10. ", "## 10. A88 bare mention\n\n## 10. ")
    if name == "13-GATE-L-FAILURE.md" else text))
check("a bare heading mention is a reference, not a definition",
      "A88" in r5["dangling_amendments"], f"dangling={r5['dangling_amendments']}")

# --- case 6: the A69 hole. A69 was logged late, found only by the `logged as`
# scan; removing its formal heading must reopen exactly that hole, so this repair
# is pinned by a power test rather than only by the baseline turning green.
print("\ncase 6: delete the `## 59. A69 -- ...` heading from 12-AMENDMENTS.md")
r6 = run_with(lambda name, text: (
    replace_once(text, "## 59. A69 \u2014", "## 59. Z69 \u2014")
    if name == "12-AMENDMENTS.md" else text))
check("A69 is reported dangling when its heading is removed",
      "A69" in r6["dangling_amendments"], f"dangling={r6['dangling_amendments']}")
check("the report attributes it to the 'logged as' scan (17's Status line)",
      any("logged as" in s for s in r6["amendment_reference_sources"].get("A69", [])),
      f"{r6['amendment_reference_sources'].get('A69')}")
check("the baseline is otherwise still clean (only A69 reopens)",
      r6["dangling_amendments"] == ["A69"],
      f"dangling={r6['dangling_amendments']}")

print()
if failures:
    print(f"POWER TEST FAILED: {len(failures)} case(s) -- {failures}")
    sys.exit(1)
print("POWER TEST PASSED: every guardrail was observed to fail on the mutation "
      "it exists to catch")
