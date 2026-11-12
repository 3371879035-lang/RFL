"""Prospective analysis equivalence tests, engineering keys only; no formal data."""
from __future__ import annotations
import copy
from dataclasses import replace
from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "tests/rebuild"))
from rfl_rebuild.b2 import parallel_design as d
from rfl_rebuild.b2 import parallel_validation as pv
import test_b2_design_selection as legacy
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.training import BaselineAcquisitionPlan
from rfl_rebuild.b2.rmst_policy import benchmark_rmst_policy

CALIBRATION=legacy.CALIBRATION
SAMPLE=d.prefix(1024)


def rows_fixture(seeds=(980200,980201),cap=4,kind="normal"):
    base=legacy.synthetic_material(1024)
    domains={"D_Q":d.ba._fixed_domain("D_Q"),"P":d.ba._fixed_domain("P"),"X":base.domains["X"]}
    incidence={a:{domain[0]:tuple(range(0,1024,4))} for a,domain in domains.items()}
    base=replace(base,domains=domains,consulted=incidence,
        uncontacted={a:len(incidence[a])<len(domains[a]) for a in d.ds.CHANNELS})
    rows=[]
    plateaus=(.98,1.,1.02,1.,1.02,.98,1.02,.98)
    for number,seed in enumerate(seeds):
        for e in range(cap+1):
            levels=base.levels
            success=base.success
            if kind == "nonbinary_constant":levels=(.7,)*1024
            elif kind == "zero":levels=(0.,)*1024
            elif kind == "undefined_odd":success=tuple(u.phase%2 == 0 for u in SAMPLE)
            elif kind == "all_failed":success=(False,)*1024
            elif kind == "late_tail" and seed == seeds[-1] and e == cap:levels=tuple([1.]*300+[0.]*724)
            elif kind == "admissible":
                tau=(1,2,3,1,2,3,1,2)[number%8]
                centre=.3+.02*e if e<tau else plateaus[number%8]
                levels=tuple(centre+(-.03125 if i%2 == 0 else .03125) for i in range(1024))
                success=(True,)*1024
            rows.append(replace(base,seed=seed,episode=e,levels=levels,success=success))
    return rows


def fixture_index(tmp_path,*,count=2,cap=4,kind="normal"):
    seeds=tuple(range(980200,980200+count))
    rows=rows_fixture(seeds,cap,kind)
    plan=BaselineAcquisitionPlan(seeds[0],Fraction(1,2),Fraction(1,10),cap,SAMPLE)
    path=tmp_path / "fixture.json"
    index=d.ba.write_acquisition(path,plan=plan,seeds=seeds,records=rows,
        constants={"engineering_fixture_only":True},execution={"role":"OPERATIONAL_FIXTURE"},role="OPERATIONAL_REHEARSAL")
    return path,index,rows


def summaries(rows,seeds,cap):
    return [d.summarize_records((r for r in rows if r.seed == seed),seed=seed,cap=cap,
                sample=SAMPLE,calibration=CALIBRATION) for seed in seeds]


def parallel_fixture(path,index,folder,guard=lambda:None):
    def validator(candidate):
        pv.verify_parallel(candidate)
        return d.ba.read_index(candidate)
    return d.calculate_parallel(path,seeds=index["seeds"],cap=len(index["episodes"])-1,
        sample=SAMPLE,pre_level=1.,calibration=CALIBRATION,validator=validator,guard=guard,folder=folder)


@pytest.mark.parametrize("kind",["normal","nonbinary_constant","zero","undefined_odd","all_failed","late_tail"])
def test_every_selector_result_exact_original_canonical_bytes(kind):
    seeds=tuple(range(980200,980232))
    rows=rows_fixture(seeds,kind=kind)
    kwargs=dict(seeds=seeds,cap=4,sample=SAMPLE,pre_level=1.,calibration=CALIBRATION)
    serial=d.ds.derive_design(rows,**kwargs)
    result=d.select_from_states(summaries(rows,seeds,4),**kwargs)
    assert d.ba.canonical_bytes(serial) == d.ba.canonical_bytes(result)


def test_join_preserves_all_site_multiplicities_and_authoritative_spreads():
    seeds=(980200,980201,980202)
    rows=rows_fixture(seeds)
    n,c,curves=d.join_states(summaries(rows,seeds,4),seeds=seeds,cap=4,sample=SAMPLE,calibration=CALIBRATION)
    sn,sc=d.ds.PrefixSelector(),d.ds.CollateralSelector(SAMPLE,calibration=CALIBRATION)
    for row in rows:sn.update(row.levels);sc.update(row)
    assert n.metrics == sn.metrics and c.metrics == sc.metrics
    assert c.spreads == sc.spreads and c.coverage == sc.coverage
    assert n.records == c.records == sn.records == sc.records == len(rows)
    assert curves == [[d.ds.mean(r.levels) for r in rows if r.seed == s] for s in seeds]
    assert sum(c.spreads["eligible_all"].values()) > len(c.spreads["eligible_all"])


def test_summary_canonical_roundtrip_does_not_change_float_bits_or_undefined():
    seeds=tuple(range(980200,980232))
    rows=rows_fixture(seeds,kind="nonbinary_constant")
    states=summaries(rows,seeds,4)
    copied=json.loads(d.ba.canonical_bytes(states))
    kwargs=dict(seeds=seeds,cap=4,sample=SAMPLE,pre_level=1.,calibration=CALIBRATION)
    assert d.ba.canonical_bytes(d.select_from_states(states,**kwargs)) == d.ba.canonical_bytes(d.select_from_states(copied,**kwargs))


def test_real_spawn_32_seed_analysis_matches_original_and_all_leaf_receipts(tmp_path):
    path,index,rows=fixture_index(tmp_path,count=32,cap=4)
    expected=d.ds.derive_design(rows,seeds=index["seeds"],cap=4,sample=SAMPLE,pre_level=1.,calibration=CALIBRATION)
    before={s["path"]:pv.file_digest(path.parent / s["path"]) for s in index["shards"]}
    actual=parallel_fixture(path,index,tmp_path / "analysis")
    assert d.ba.canonical_bytes(actual) == d.ba.canonical_bytes(expected)
    receipt=json.loads((tmp_path / "analysis/completed.json").read_bytes())
    assert receipt["seeds"] == index["seeds"] and receipt["records"] == 160
    assert receipt["max_workers"] == 16 and receipt["start_method"] == "spawn"
    assert 2 <= len({r["pid"] for r in receipt["workers"]}) <= 16
    assert len(list((tmp_path / "analysis").glob("seed-*.completed.json"))) == 32
    assert before == {s["path"]:pv.file_digest(path.parent / s["path"]) for s in index["shards"]}
    assert receipt["floating_moment_reduction"] is False


def test_real_spawn_positive_design_exact_same_laws(tmp_path):
    path,index,rows=fixture_index(tmp_path,count=32,cap=8,kind="admissible")
    kwargs=dict(seeds=index["seeds"],cap=8,sample=SAMPLE,pre_level=1.,calibration=CALIBRATION)
    expected=d.ds.derive_design(rows,**kwargs)
    actual=parallel_fixture(path,index,tmp_path / "analysis")
    assert d.ba.canonical_bytes(actual) == d.ba.canonical_bytes(expected)
    assert actual["status"] == "ADMISSIBLE"
    policy=benchmark_rmst_policy(ratified=True)
    assert d.ba.canonical_bytes(d.ds.combine_design_and_thresholds(actual,rmst_policy=policy)) == \
           d.ba.canonical_bytes(d.ds.combine_design_and_thresholds(expected,rmst_policy=policy))
    assert d.ds.combine_design_and_thresholds(actual,rmst_policy=policy)["status"] == "LOCKABLE"


@pytest.mark.parametrize("damage",["missing","duplicate","wrong_seed","wrong_count","bad_curve","negative_multiplicity","nan","duplicate_spread","order"])
def test_join_refuses_invalid_or_partial_worker_states(damage):
    seeds=(980200,980201)
    states=summaries(rows_fixture(seeds),seeds,4)
    if damage == "missing":states.pop()
    elif damage == "duplicate":states[1]=copy.deepcopy(states[0])
    elif damage == "wrong_seed":states[-1]["seed"]+=1
    elif damage == "wrong_count":states[-1]["records"]-=1
    elif damage == "bad_curve":states[-1]["curve"].pop()
    elif damage == "negative_multiplicity":states[-1]["spreads"][0][1][0][1]=-1
    elif damage == "nan":states[-1]["prefix"][0][1]=float("nan")
    elif damage == "duplicate_spread":states[-1]["spreads"][0][1].append(states[-1]["spreads"][0][1][0])
    elif damage == "order":states.reverse()
    with pytest.raises(ProtocolError):d.select_from_states(states,seeds=seeds,cap=4,sample=SAMPLE,pre_level=1.,calibration=CALIBRATION)


@pytest.mark.parametrize("damage",["hash","truncate","extra","unknown"])
def test_bad_late_shard_blocks_before_any_analysis_worker(tmp_path,damage,monkeypatch):
    path,index,_=fixture_index(tmp_path,cap=1)
    shard=path.parent / index["shards"][-1]["path"]
    lines=gzip.decompress(shard.read_bytes()).splitlines(keepends=True)
    record=json.loads(lines[-1])
    if damage == "hash":record["levels"][0]+=.1
    elif damage == "unknown":record["unknown"]=False
    lines[-1]=d.ba.canonical_bytes(record)
    if damage == "truncate":lines.pop()
    elif damage == "extra":lines.append(lines[-1])
    shard.write_bytes(gzip.compress(b"".join(lines),mtime=0))
    def forbidden(*args,**kwargs):raise AssertionError("invalid global input reached analysis workers")
    monkeypatch.setattr(d,"ProcessPoolExecutor",forbidden)
    with pytest.raises(ProtocolError):parallel_fixture(path,index,tmp_path / "analysis")
    assert not (tmp_path / "analysis").exists()


def test_postvalidation_shard_damage_refused_by_worker_no_design_publication(tmp_path):
    path,index,_=fixture_index(tmp_path,cap=1)
    calls=0
    def mutate():
        nonlocal calls
        calls+=1
        if calls == 2:
            shard=path.parent / index["shards"][-1]["path"]
            lines=gzip.decompress(shard.read_bytes()).splitlines(keepends=True)
            record=json.loads(lines[-1]);record["levels"][0]+=.1
            lines[-1]=d.ba.canonical_bytes(record)
            shard.write_bytes(gzip.compress(b"".join(lines),mtime=0))
    with pytest.raises(ProtocolError):parallel_fixture(path,index,tmp_path / "analysis",guard=mutate)
    assert not (tmp_path / "analysis/completed.json").exists()


def test_changed_bound_source_postworkers_refuses_global_design(tmp_path):
    path,index,_=fixture_index(tmp_path,cap=1)
    calls=0
    def guard():
        nonlocal calls
        calls+=1
        if calls == 3:raise ProtocolError("source drift")
    with pytest.raises(ProtocolError,match="drift"):parallel_fixture(path,index,tmp_path / "analysis",guard=guard)
    assert not (tmp_path / "analysis/completed.json").exists()
