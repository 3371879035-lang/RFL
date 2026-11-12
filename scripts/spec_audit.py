"""Specification audit for ``docs/rebuild/``.

The rebuild's whole claim is that implementation can begin with no design
ambiguity. That claim is checkable, at least mechanically, and this script checks
the part of it that machines can decide:

* every ``NN §X`` cross-reference resolves to a real section in a real document;
* every ``NN-NAME.md`` file reference resolves;
* every document uses numbered ``##`` headings, so it *can* be referenced;
* every filesystem path the spec names actually exists on this branch;
* every invariant (I1..I6) and case (C0..C8) is defined exactly once.

It cannot check whether the design is *good*, or whether a sentence is
ambiguous to a human. It checks that the document set is a closed graph rather
than a pile of forward references.

Usage
-----
    python scripts/spec_audit.py
    python scripts/spec_audit.py --json experiments/spec_audit.json

Exit status is 0 when clean and 1 when anything is unresolved, so it can gate a
commit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs" / "rebuild"

# Paths the specification tells an implementer to create or use.
DECLARED_PATHS = (
    "src/rfl_rebuild",
    "tests/semantic",
    "experiments/v01r",
    "experiments/v02r",
    "experiments/v03r",
    "experiments/v04r",
    "scripts/src_fingerprint.py",
    "docs/rebuild/00-INDEX.md",
)

INVARIANTS = ("I1", "I2", "I3", "I4", "I5", "I6")
CASES = ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
AMENDMENTS = tuple(f"A{i}" for i in range(1, 13))

# Sequences that indicate UTF-8 read as a legacy codepage. This is not
# hypothetical: a PowerShell Get-Content/Set-Content round-trip silently
# destroyed every em dash in 12-AMENDMENTS.md, turning "—" into "鈥?". The file
# still parsed, still rendered as text, and looked fine in a diff summary.
MOJIBAKE = ("\ufffd", "鈥", "锛", "銆", "鈻", "芒€")

# Expressions explicitly retired by an amendment. Closing the reference graph is
# not enough: a superseded symbol can survive in live prose and be read as the
# data schema by an implementer. Each entry is a literal that must not appear in
# any document other than the amendment log, which quotes them on purpose in its
# "Was" fields.
#
# Deliberately NOT a bare regex on `C`: that would flag `C_X`, the controller,
# which is alive and load-bearing.
RETIRED = (
    (r"\\hat C\^\{fb\}", "feedback claim is now Z-hat (A13)"),
    (r"predicts\s*\}?\s*C\b", "the predicted label is Z, not C (A13)"),
    (r"distinct \$C\$", "labels are distinct Z (A13)"),
    (r"\$C\s*=\s*\(c_P", "the fault vector is Z = (Z_P, ...) (A13)"),
    (r"\\pi_\{\\text\{ref\}\}", "the global reference policy is retired (A9, A26)"),
    (r"truth fields\s*\(\$C\$", "truth fields are Z, M, z, eps (A13)"),
    (r"A_\{z_1\}\(s\)\s*=\s*A\$", "admissible sets are subsets of A_legal (A20)"),
    (r"\$A_i\$", "but-for relevance is B_i, not A_i (A13, A26)"),
    (r"causal relevance", "it is but-for relevance; the name must not overclaim (A13)"),
    (r"Q_D\(s,\s*z,\s*a\)", "the decision table is Q_D(s,z,m,a) -- m is part of the state (A22)"),
    (r"Q_D\(s,\s*z,\s*\\cdot\)", "the decision table is Q_D(s,z,m,.) (A22)"),
    (r"\\pi_D\^\{\*\}\(s,\s*z\)", "the reference is pi_D*(s,z,m) (A22)"),
    (r"pi_D\^\{\*\}\(\\cdot,\s*z\)", "the reference is pi_D*(.,z,m) (A22)"),
    (r"z\^\{\*\}\(\\kappa\)", "the context-appropriate option is z*(s), not z*(kappa) (A23)"),
    # A27-A31: propagation of the control state, and of the generator change.
    (r"Q_D\^\{\*\}\(s,\s*z,\s*a\)", "the solved table is Q_D*(s,z,m,a) (A27)"),
    (r"A_z\(s\)", "the admissible set is A_z(m,s) (A27)"),
    (r"z\^\{\*\}\(s\)", "the generator must not consult z* at all (A28)"),
    (r"assign \$C\$|carry \$C\$|\$C\$\s+and\s+\$M\$", "the schema is Z, not C (A31)"),
    (r"but-for relevance \$A\$", "but-for relevance is B (A31)"),
    (r"tell you whether that option was the right one", "A27 reword"),
)

# The amendment log quotes superseded text by design.
RETIRED_EXEMPT = {"12-AMENDMENTS.md"}

# A line carrying one of these is a *notice* that the form is retired, not a live
# usage. Without this, every withdrawal notice would trip the check and the check
# would be turned off -- which is worse than not having it.
RETIREMENT_MARKERS = (
    "retire", "Retire", "RETIRE",
    "withdrawn", "Withdrawn",
    "first draft", "earlier draft", "first version",
    "**Was**", "Was `",
)


def strip_code(text: str) -> str:
    """Remove backticks so `` `03` §2 `` reads as `` 03 §2 ``."""
    return text.replace("`", "")


def load() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(SPEC_DIR.glob("*.md"))}


def sections(text: str) -> set[str]:
    return set(re.findall(r"^#{2,4}\s+(\d+(?:\.\d+)*)", text, re.M))


def audit() -> dict:
    docs = load()
    names = set(docs)
    by_num = {n[:2]: n for n in names}

    problems: list[tuple[str, str, str]] = []
    refs_checked = 0
    unnumbered: list[str] = []

    for name, raw in docs.items():
        text = strip_code(raw)

        secs = sections(raw)
        if not secs:
            unnumbered.append(name)

        # The two digits must not be preceded by a letter or digit. Without the
        # lookbehind, "A67 §7" parses as "document 67, section 7", so an
        # amendment label followed by a section sign produced a phantom
        # no-such-document problem.
        for m in re.finditer(r"(?<![A-Za-z0-9])([0-9]{2})\s*§\s*([0-9]+(?:\.[0-9]+)*)",
                             text):
            refs_checked += 1
            target = by_num.get(m.group(1))
            if target is None:
                problems.append((name, "no-such-document", m.group(1)))
            elif m.group(2) not in sections(docs[target]):
                problems.append((name, "no-such-section", f"{target} §{m.group(2)}"))

        for m in re.finditer(r"([0-9]{2}-[A-Z0-9\-]+\.md)", text):
            refs_checked += 1
            if m.group(1) not in names:
                problems.append((name, "no-such-file-ref", m.group(1)))

    # Every invariant and case must be defined exactly once, in doc 04.
    definitions: dict[str, list[str]] = {k: [] for k in INVARIANTS + CASES}
    for name, raw in docs.items():
        for m in re.finditer(r"^###\s+(I[1-6]|C[0-8])\s+—", raw, re.M):
            definitions[m.group(1)].append(name)
    for key, where in definitions.items():
        if len(where) != 1:
            problems.append(("04-SEMANTIC-INVARIANTS.md", "definition-count",
                             f"{key} defined in {len(where)} places: {where}"))

    missing_paths = [p for p in DECLARED_PATHS if not (ROOT / p).exists()]

    # Amendment references must resolve to an amendment heading.
    #
    # "Defined" is sourced *only* from the formal headings of the amendment log.
    # Everything else below is a *reference* source, and a reference to an
    # amendment that has no heading is the failure mode this guards: A71 and A72
    # were fully specified in `17` and named in `17`'s own headings, yet the
    # audit reported clean, because only bold `**Axx**` in a non-amendment doc
    # counted as a reference. The graph closed while two amendments were
    # un-logged -- a query that passes is not evidence that the subject is right.
    amend_doc = docs.get("12-AMENDMENTS.md", "")
    defined_amendments = set(
        re.findall(r"^#{2,6}\s+\d+\.\s+(A\d+)\b", amend_doc, re.M)
    )

    # Reference sources, kept separate so a failure names its own origin.
    ref_sources: dict[str, set[str]] = {}
    headings_scanned = 0
    headed: list[str] = []

    def note(amend: str, origin: str) -> None:
        ref_sources.setdefault(amend, set()).add(origin)

    # A range such as `A55–A64` references both endpoints; the interior is a
    # human-readable span, not a claim, so it is deliberately not expanded.
    def head_refs(text: str, doc: str) -> None:
        for m in re.finditer(r"\b(A\d+)\s*[–—-]\s*(A\d+)\b", text):
            note(m.group(1), f"{doc}: range {m.group(1)}-{m.group(2)}")
            note(m.group(2), f"{doc}: range {m.group(1)}-{m.group(2)}")

    for name, raw in docs.items():
        if name == "12-AMENDMENTS.md":
            continue
        # (a) bold mentions, the original source
        for m in re.finditer(r"\*\*(A\d+)\*\*", raw):
            note(m.group(1), f"{name}: bold")
        # (b) numbered headings: a heading-level declaration is a definition in
        # the reader's eyes, so it must be logged as one. The `\.?` is load
        # bearing: `## 8. A72 — ...` has a period after the number and `### 8.4
        # A71's claim` does not, and a regex without it silently matched only the
        # sub-numbered form -- catching A71 and missing A72.
        for m in re.finditer(r"^#{1,6}\s+(\d+(?:\.\d+)*)\.?\s+(\S.*)$", raw, re.M):
            headings_scanned += 1
            for a in re.findall(r"\b(A\d+)\b", m.group(2)):
                note(a, f"{name}: heading §{m.group(1)}")
                headed.append(f"{name} §{m.group(1)} names {a}")
            head_refs(m.group(2), f"{name} §{m.group(1)}")
        # (c) explicit status declarations, e.g. "Status: ... logged as A66"
        for m in re.finditer(r"(?i)logged as\s+\**\s*(A\d+)\b", raw):
            note(m.group(1), f"{name}: 'logged as'")
        # (d) explicit retirement notices naming an amendment
        for m in re.finditer(r"(?i)(?:retired|withdrawn|superseded)\s+(?:by|as)\s+\**\s*(A\d+)\b",
                             raw):
            note(m.group(1), f"{name}: 'superseded by'")

    # (e) LITERAL amendment tokens -- the total source, and the only one that
    # cannot miss a shape.
    #
    # Sources (a)-(d) each recognise *one way* of writing a reference, so a
    # plain `A999` in prose, or a backticked one, was invisible to all of them --
    # and that is precisely where a phantom number hides. This one is total: it
    # scans every document INCLUDING the amendment log itself, with code spans
    # and fenced blocks deliberately NOT stripped, because a reader reads
    # `A999` as an amendment identifier whatever markup surrounds it.
    #
    # The invariant is therefore unconditional:
    #
    #     every literal A<n> in docs/rebuild resolves to a formal amendment heading
    #
    # The A-namespace belongs to amendments and to nothing else. A non-amendment
    # series that used to be written `A32-A38` is RENAMED out of the namespace
    # (it is a correction pass), never allow-listed here: an allow-list would
    # make this source partial again, which is the defect it exists to close.
    literal_tokens = 0
    for name, raw in docs.items():
        for m in re.finditer(r"\bA\d+\b", raw):
            literal_tokens += 1
            note(m.group(0), f"{name}: literal")

    referenced_amendments = set(ref_sources)
    dangling_amendments = sorted(referenced_amendments - defined_amendments)

    # Same failure, seen from the log's side: a formal heading is present but the
    # amendment is not carried into the summary tables, so a reader who starts at
    # the summary never learns it exists.
    summary_amendments = set(re.findall(r"^\|\s*\**\s*(A\d+)\s*\**\s*\|", amend_doc, re.M))

    # UTF-8 integrity.
    mojibake: list[tuple[str, str]] = []
    for name, raw in docs.items():
        for bad in MOJIBAKE:
            if bad in raw:
                mojibake.append((name, bad))

    # Retired semantics surviving in live prose.
    retired_hits: list[tuple[str, str, str]] = []
    for name, raw in docs.items():
        if name in RETIRED_EXEMPT:
            continue
        for lineno, line in enumerate(raw.splitlines(), 1):
            if any(marker in line for marker in RETIREMENT_MARKERS):
                continue  # a notice that quotes the retired form is not a usage
            for pattern, why in RETIRED:
                for m in re.finditer(pattern, line):
                    retired_hits.append(
                        (name, f"line {lineno}: {m.group(0)[:40]}", why)
                    )

    # Amendment headings that no summary table mentions. Diagnostic, not fatal:
    # the remedy is editorial, and the log has carried this gap since A22.
    unsummarised = sorted(defined_amendments - summary_amendments)

    return {
        "documents": sorted(names),
        "documents_without_numbered_sections": unnumbered,
        "cross_references_checked": refs_checked,
        "problems": sorted(set(problems)),
        "missing_declared_paths": missing_paths,
        "invariants_defined": {k: v for k, v in definitions.items() if k.startswith("I")},
        "cases_defined": {k: v for k, v in definitions.items() if k.startswith("C")},
        "amendments_defined": sorted(defined_amendments),
        "amendments_referenced": sorted(referenced_amendments),
        "dangling_amendments": dangling_amendments,
        "amendment_reference_sources": {
            k: sorted(v) for k, v in sorted(ref_sources.items())
        },
        "numbered_headings_scanned_in_other_docs": headings_scanned,
        "literal_amendment_tokens_scanned": literal_tokens,
        "amendments_named_in_other_doc_headings": sorted(set(headed)),
        "amendments_defined_but_not_in_summary": unsummarised,
        "mojibake": mojibake,
        "retired_semantics": retired_hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if not SPEC_DIR.exists():
        print(f"{SPEC_DIR} not found -- run from the rebuild branch")
        return 1

    r = audit()
    print(f"documents: {len(r['documents'])}")
    print(f"cross-references checked: {r['cross_references_checked']}")

    ok = True

    if r["documents_without_numbered_sections"]:
        ok = False
        print("\nDOCUMENTS WITH NO NUMBERED SECTIONS (cannot be referenced by §):")
        for n in r["documents_without_numbered_sections"]:
            print(f"  {n}")

    if r["problems"]:
        ok = False
        print("\nUNRESOLVED REFERENCES:")
        for doc, kind, detail in r["problems"]:
            print(f"  {doc:<34} {kind:<20} {detail}")

    if r["missing_declared_paths"]:
        ok = False
        print("\nDECLARED PATHS THAT DO NOT EXIST:")
        for p in r["missing_declared_paths"]:
            print(f"  {p}")

    undef = [k for k, v in {**r["invariants_defined"], **r["cases_defined"]}.items() if not v]
    if undef:
        ok = False
        print(f"\nUNDEFINED INVARIANTS/CASES: {undef}")

    if r["dangling_amendments"]:
        ok = False
        print("\nAMENDMENT REFERENCES WITH NO SUCH AMENDMENT HEADING IN 12:")
        for a in r["dangling_amendments"]:
            print(f"  {a}")
            for origin in r["amendment_reference_sources"].get(a, []):
                print(f"      referenced by {origin}")
        print(
            "  A heading-level or 'logged as' declaration is a definition in the\n"
            "  reader's eyes. If the amendment exists in prose but has no `## NN.\n"
            "  Axx —` heading in 12-AMENDMENTS.md, the reference graph closes while\n"
            "  the amendment is un-logged and this audit reports clean.\n"
            "  The A-namespace belongs to amendments. A legacy correction pass that\n"
            "  was written `A32-A38` must be renamed out of the namespace, not\n"
            "  allow-listed here."
        )
    print(
        f"\namendments defined: {len(r['amendments_defined'])} "
        f"{r['amendments_defined']}; referenced from other docs: "
        f"{r['amendments_referenced']}"
    )
    print(
        f"numbered headings scanned in other docs: "
        f"{r['numbered_headings_scanned_in_other_docs']}; amendments named "
        f"therein: {r['amendments_named_in_other_doc_headings']}"
    )
    print(
        f"literal amendment tokens scanned (all docs, code spans included): "
        f"{r['literal_amendment_tokens_scanned']}"
    )

    if r["amendments_defined_but_not_in_summary"]:
        print(
            f"\nDEFINED BUT ABSENT FROM THE SUMMARY TABLE (editorial, non-blocking): "
            f"{r['amendments_defined_but_not_in_summary']}"
        )

    if r["mojibake"]:
        ok = False
        print("\nUTF-8 CORRUPTION DETECTED:")
        for name, bad in r["mojibake"]:
            print(f"  {name}: contains {bad!r}")
        print(
            "  Never round-trip these files through PowerShell "
            "Get-Content/Set-Content; use the editor tools."
        )

    if r["retired_semantics"]:
        ok = False
        print("\nRETIRED SEMANTICS SURVIVING IN LIVE PROSE:")
        for name, where, why in r["retired_semantics"]:
            print(f"  {name:<28} {where:<34} {why}")
        print(
            "  A closed reference graph is not enough: a superseded symbol can\n"
            "  survive in prose and be read as the data schema by an implementer."
        )

    if ok:
        print("\nOK - the specification is a closed reference graph")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
