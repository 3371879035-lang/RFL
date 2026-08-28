"""防泄漏回归：learner baselines 与 counterfactual 绝不依赖 evaluator ground truth。

规范要求：
    - Full-RFL 源码不含 OracleEvaluator / oracle_delta / oracle_R / oracle_responsibility
    - learner inference 期间调用 OracleEvaluator.evaluate 必须抛错
"""

import inspect
import pytest

import rflcc.baselines.cf_only
import rflcc.baselines.full_rfl
import rflcc.baselines.immediate
import rflcc.baselines.pe_seq
import rflcc.baselines.oracle_upper
import rflcc.counterfactual
import rflcc.attribution

FORBIDDEN = [
    "OracleEvaluator",
    "oracle_delta",
    "oracle_R",
    "oracle_responsibility",
]


@pytest.mark.parametrize(
    "mod",
    [
        rflcc.baselines.cf_only,
        rflcc.baselines.full_rfl,
        rflcc.baselines.immediate,
        rflcc.baselines.pe_seq,
        rflcc.baselines.oracle_upper,
        rflcc.counterfactual,
        rflcc.attribution,
    ],
)
def test_module_has_no_oracle_dependency(mod):
    src = inspect.getsource(mod)
    for name in FORBIDDEN:
        assert name not in src, (mod.__name__, name)


def test_baseline_signatures_have_no_oracle():
    for cls in (
        rflcc.baselines.immediate.Immediate,
        rflcc.baselines.pe_seq.PESeq,
        rflcc.baselines.cf_only.CFOnly,
        rflcc.baselines.full_rfl.FullRFL,
        rflcc.baselines.oracle_upper.OracleUpper,
    ):
        sig = inspect.signature(cls.attribute)
        assert "oracle" not in str(sig).lower()


def test_oracle_not_called_during_learner_inference(monkeypatch):
    """Full-RFL attribution 必须在 evaluator 被炸掉的情况下正常工作。"""
    from rflcc.counterfactual import CounterfactualRunner
    from rflcc.env import CausalChaseEnv
    from rflcc.feedback import FeedbackInjector
    from rflcc.noise import NoiseTape
    from rflcc.oracle import OracleEvaluator
    from rflcc.policies import ScriptedRouteFollower, rollout_to_trace
    from rflcc.sequence import SequenceModel
    from rflcc.trace import EpisodeTrace

    def explode(*args, **kwargs):
        raise AssertionError("ORACLE LEAKAGE: evaluator called during learner inference")

    monkeypatch.setattr(OracleEvaluator, "evaluate", explode)

    env = CausalChaseEnv()
    tape = NoiseTape.from_seed(42)
    opt = tape.monster_start_lane
    trace = rollout_to_trace(
        env, tape=tape, option=opt, policy=ScriptedRouteFollower(opt),
        seed=42, scenario_id="LEAK_TEST",
    )
    # 合成校准模型
    seq_model = SequenceModel()
    tr2 = EpisodeTrace(seed=1, scenario_id="x", option=0, terminal_type="COLLISION")
    from rflcc.types import TraceEvent
    tr2.causal_events = [TraceEvent(t=i, token=t, module=None, source="t")
                         for i, t in enumerate(trace.tokens[: max(2, len(trace.tokens) // 2)])]
    seq_model.calibrate({"H": [tr2], "L": [tr2], "E": [tr2]})

    runner = CounterfactualRunner(
        policy_for=lambda o: ScriptedRouteFollower(o), env=env, top_k=2,
        low_level_window=3,
    )
    algo = rflcc.baselines.full_rfl.FullRFL()
    outcome = algo.attribute(trace, "L", seq_model, runner)
    assert outcome.responsibility is not None
    assert abs(sum(outcome.responsibility.values()) - 1.0) < 1e-9


def test_oracle_upper_is_explicitly_evaluator_side():
    """oracle_upper 只读取 trace 中 evaluator 写入的 r_star（实验装配注入）。"""
    src = inspect.getsource(rflcc.baselines.oracle_upper)
    # 它不导入 OracleEvaluator，也不自己计算 delta
    assert "OracleEvaluator" not in src
