r"""The $F_0$ manifest's path parsing, and the defect that made it a test.

$$\boxed{\text{a status line is } \texttt{XY PATH}\text{, and } X \text{ may be a space}}$$

The shipped manifest of revision 1 contained an entry reading `xperiments/v03r/f0_manifest.json`. The
reviewer read it back verbatim and the author explained it away as a transcription slip. It was not: the
manifest's own helper stripped the whole of `git status --porcelain`, which removes the leading space of
the *first* line -- where a modified-but-unstaged file reports ` M path` -- and slicing three characters
then decapitated the path. The corrupted name was also classified as code rather than evidence, so a dirty
evidence artifact was reported as a dirty instrument.

The parser is therefore a pure function with its own tests. A bug that shipped once does not get to rely on
"the obvious version is fine".
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_manifest_module():
    spec = importlib.util.spec_from_file_location("f0_manifest", ROOT / "scripts" / "f0_manifest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest = _load_manifest_module()


def test_1_a_leading_status_space_does_not_eat_a_character():
    """The exact line that shipped a decapitated path: ` M path` as the *first* line of the output."""
    text = " M experiments/v03r/f0_manifest.json\n"
    assert manifest.parse_porcelain(text) == ["experiments/v03r/f0_manifest.json"]
    # And the reason the old code failed: stripping the whole output first removes that space.
    assert manifest.parse_porcelain(text) != manifest.parse_porcelain(text.strip())


def test_2_a_whole_status_list_parses_with_every_paths_intact():
    text = (" M experiments/v03r/b2_run_gate_selfcheck.json\n"
            "?? src/rfl_rebuild/b2/devstage.py\n"
            "MM scripts/f0_manifest.py\n"
            "\n")
    assert manifest.parse_porcelain(text) == [
        "experiments/v03r/b2_run_gate_selfcheck.json",
        "src/rfl_rebuild/b2/devstage.py",
        "scripts/f0_manifest.py",
    ]


def test_3_a_rename_reports_the_new_path():
    text = "R  old/name.py -> new/name.py\n"
    assert manifest.parse_porcelain(text) == ["new/name.py"]


def test_4_a_short_line_is_refused_rather_than_sliced():
    with pytest.raises(AssertionError, match="unparsable porcelain line"):
        manifest.parse_porcelain("M\n")


def test_5_the_live_tree_parses_and_every_path_exists_or_is_evidence():
    """Against the real repository: no path may come back decapitated."""
    for path in manifest.status_lines():
        assert not path.startswith("xperiments/"), "the decapitation bug is back"
        assert (ROOT / path).exists() or path.endswith("/"), f"{path} does not exist in the tree"
