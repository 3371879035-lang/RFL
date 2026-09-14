"""Source-tree fingerprint — mechanical enforcement of the no-mid-run-change rule.

The rule (``docs/SEED_BLOCK_PROTOCOL.md`` §10):

    Never change the algorithm while increasing seeds.

If the code moves between N=100 and N=200, those two results no longer come from
the same experimental distribution and cannot be pooled, compared, or plotted on
one curve.  Tuning a parameter, swapping a threshold, or "just fixing the
environment a little" after seeing an intermediate look is optional stopping
wearing a different hat.

The corollary is harsh and is applied literally: **if a bug is found, the entire
seed set is void.**  It is not patched in place and resumed.  The fix lands, and
collection restarts from N=0 on the new code.

This script makes that checkable.  It hashes the contents of ``src/`` and
compares against a recorded fingerprint, so a run's provenance can be verified
after the fact rather than asserted.

Usage
-----
    python scripts/src_fingerprint.py                # print current fingerprints
    python scripts/src_fingerprint.py --check FILE   # verify against a record
    python scripts/src_fingerprint.py --record FILE  # write a record

Exit status is 0 when ``--check`` matches and 1 when it does not, so a driver
script or CI step can gate a run on it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("src/rflv04", "src/rflnext")


def fingerprint(root: Path) -> str:
    """SHA-256 over every ``.py`` file's repo-relative path and normalized bytes.

    Two details make the digest usable rather than merely well-defined:

    * Paths are hashed *relative to the repository root*, so the fingerprint is
      portable.  An absolute path would be machine-specific and therefore
      useless for verification.  Paths are included at all so that renaming or
      moving a module changes the digest — a pure content hash would miss it, and
      a move can change import resolution.
    * Line endings are normalized to ``\\n`` before hashing.  This repository
      has ``core.autocrlf`` on, so git rewrites LF to CRLF on checkout while
      still reporting the tree clean.  Hashing raw working-tree bytes would
      therefore raise false alarms on a file git considers unmodified — and a
      provenance check that cries wolf gets ignored, which is worse than not
      having one.
    """
    digest = hashlib.sha256()
    if not root.exists():
        return "MISSING"
    for path in sorted(root.rglob("*.py")):
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        body = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "UNKNOWN"


def git_dirty(scope: str = "src") -> bool:
    """True when tracked files under ``scope`` differ from HEAD."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", scope],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        return bool(out.strip())
    except Exception:
        return False


def snapshot() -> dict:
    return {
        "git_commit": git_commit(),
        "src_dirty": git_dirty("src"),
        "fingerprints": {pkg: fingerprint(ROOT / pkg) for pkg in PACKAGES},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--record", metavar="FILE", help="write the current state here")
    ap.add_argument("--check", metavar="FILE", help="verify against this record")
    ap.add_argument(
        "--allow-dirty", action="store_true",
        help="do not fail when src/ has uncommitted changes",
    )
    args = ap.parse_args()

    current = snapshot()

    if args.record:
        Path(args.record).write_text(
            json.dumps(current, indent=1), encoding="utf-8"
        )
        print(f"recorded -> {args.record}")
        for pkg, fp in current["fingerprints"].items():
            print(f"  {pkg:<14} {fp}")

    if args.check:
        recorded = json.loads(Path(args.check).read_text(encoding="utf-8"))
        ok = True
        for pkg, fp in recorded["fingerprints"].items():
            now = current["fingerprints"].get(pkg, "MISSING")
            match = now == fp
            ok &= match
            print(f"{'OK  ' if match else 'DIFF'} {pkg:<14} {now}")
        if current["src_dirty"] and not args.allow_dirty:
            print("FAIL src/ has uncommitted changes -- the algorithm is not frozen")
            ok = False
        if not ok:
            print(
                "\nProvenance check failed. If a bug was found, the entire seed "
                "set is void: fix it, then restart collection from N=0. Do not "
                "resume, extend, or pool across the change."
            )
        return 0 if ok else 1

    if not args.record and not args.check:
        for pkg, fp in current["fingerprints"].items():
            print(f"{pkg:<14} {fp}")
        print(f"git_commit     {current['git_commit']}")
        print(f"src_dirty      {current['src_dirty']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
