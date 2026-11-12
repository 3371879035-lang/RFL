"""Controller checks only: no scientific/operational training or source edits."""
import importlib.util
import pathlib
import pytest

PATH = pathlib.Path(__file__).with_name("continue_pipeline.py")
SPEC = importlib.util.spec_from_file_location("takeover_pipeline", PATH)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def test_locked_needs_next_stage_review():
    assert pipeline.classify_lock(0, {"status": "LOCKED", "written": True}) == "F1_LOCKED_REQUIRES_NEXT_STAGE_REVIEW"


@pytest.mark.parametrize("name", ["NO_ADMISSIBLE_T", "NO_ADMISSIBLE_GRID", "NO_ADMISSIBLE_RETENTION", "NO_ADMISSIBLE_THRESHOLD"])
def test_no_admissible_is_not_invalid(name):
    assert pipeline.classify_lock(3, {"status": name, "written": False}) == "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN"


@pytest.mark.parametrize("code,payload", [
    (0, {"status": "LOCKED", "written": False}),
    (2, {"status": "PROTOCOL_ERROR", "written": False}),
    (0, {"status": "NO_ADMISSIBLE_T", "written": False}),
    (3, {"status": "NO_ADMISSIBLE_T", "written": True}),
    (3, {"status": "LOCKED", "written": True}),
    (3, {}), (0, None),
])
def test_never_promote_invalid_completion(code, payload):
    with pytest.raises(pipeline.ProtocolError):
        pipeline.classify_lock(code, payload)


def test_existing_benchmark_refused_before_git_or_seed_draw(tmp_path):
    benchmark = tmp_path / "occupied"
    benchmark.mkdir()
    with pytest.raises(pipeline.ProtocolError, match="fresh benchmark reservation"):
        pipeline.validate_launch(tmp_path, benchmark, tmp_path / "manifest.json", {})


def test_existing_manifest_refused(tmp_path):
    manifest = tmp_path / "existing.json"
    manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(pipeline.ProtocolError, match="new manifest path"):
        pipeline.validate_launch(tmp_path, tmp_path / "new-benchmark", manifest, {})


@pytest.mark.parametrize("name", pipeline.FORMAL_OUTPUTS)
def test_spent_formal_outputs_refused(tmp_path, name):
    folder = tmp_path / "experiments/v03r"
    folder.mkdir(parents=True)
    (folder / name).write_text("reserved", encoding="utf-8")
    with pytest.raises(pipeline.ProtocolError, match="spent formal output"):
        pipeline.validate_launch(tmp_path, tmp_path / "benchmark", tmp_path / "manifest", {})


def registration():
    return pipeline.read_json(PATH.with_name("preregistration.json"))


def test_restart_population_is_prospective_and_exact():
    pipeline.validate_restart_population(registration())


@pytest.mark.parametrize("field,value", [
    ("fresh_smoke_seeds", [0, 1, 2, 3, 4]),
    ("fresh_smoke_seeds", [True, 2026100801, 2026100802, 2026100803, 2026100804]),
    ("fresh_smoke_seeds", [2026100800] * 5),
    ("spent_smoke_seeds", []),
    ("development_seeds", [2000]),
])
def test_restart_population_mutations_refused(field, value):
    item = registration()
    item[field] = value
    with pytest.raises(pipeline.ProtocolError):
        pipeline.validate_restart_population(item)


def test_restart_cannot_change_scientific_cap():
    item = registration()
    item["unchanged_scientific_parameters"]["acquisition_cap"] = 600
    with pytest.raises(pipeline.ProtocolError, match="scientific constant"):
        pipeline.validate_restart_population(item)
