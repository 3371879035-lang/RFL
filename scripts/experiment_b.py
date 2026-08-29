"""Experiment B：Integrated Tabular Learning 与 sanity ladder（S08/S09/S10）。

阶段：
    B0  No Monster                    -> Standard tabular success >= 0.95
    B1  High-level only + scripted    -> correct safe option >= 0.90
    B2  Controlled low-level fault    -> H/L attribution 可区分（router）
    B3  Deterministic monster dash=0  -> Standard-HQ success >= 0.70
    B4  Full monster dash=0.10        -> Standard-HQ 稳定非零学习（>= 0.50）

任何前一级未通过则停止，不允许跑 50-seed confirmatory。

用法：
    python scripts/experiment_b.py --stage B0 --smoke
    python scripts/experiment_b.py --stage B1 --smoke
    python scripts/experiment_b.py --stage B2 --smoke
    python scripts/experiment_b.py --stage B3 --pilot --seeds 3 --algo standard
    python scripts/experiment_b.py --stage B4 --pilot --seeds 3 --algo full_rfl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

from rflcc.baselines.cf_only import CFOnly
from rflcc.baselines.er import ER5
from rflcc.baselines.full_rfl import FullRFL
from rflcc.baselines.immediate import Immediate
from rflcc.baselines.standard import StandardHQ
from rflcc.counterfactual import CounterfactualRunner
from rflcc.env import CausalChaseEnv
from rflcc.feedback import FeedbackInjector
from rflcc.metrics import compute_attribution_metrics
from rflcc.oracle import OracleEvaluator
from rflcc.policies import FrozenQLowPolicy, ScriptedRouteFollower
from rflcc.qtables import linear_epsilon
from rflcc.router import UpdateRouter
from rflcc.sequence import SequenceModel
from rflcc.trace import EpisodeTrace
from rflcc.types import (
    TERM_COLLISION,
    TERM_EXIT,
    Transition,
)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


STAGE_ENV = {
    "B0": {"monster_enabled": False, "monster_dash_p": 0.0},
    "B1": {"monster_enabled": True, "monster_dash_p": 0.0},
    "B2": {"monster_enabled": True, "monster_dash_p": 0.0},
    "B3": {"monster_enabled": True, "monster_dash_p": 0.0},
    "B4": {"monster_enabled": True, "monster_dash_p": 0.10},
}

STAGE_GATES = {
    "B0": {"threshold": 0.95, "metric": "success"},
    "B1": {"threshold": 0.90, "metric": "safe_option"},
    "B2": {"threshold": None, "metric": "attribution"},
    "B3": {"threshold": 0.70, "metric": "success"},
    "B4": {"threshold": 0.50, "metric": "success"},
}

B_ALGOS = ("standard", "immediate", "er5", "pe_seq", "cf_only", "full_rfl", "oracle_upper")


# ---------------------------------------------------------------------------
# B2：router 在受控场景上的 H/L/E attribution 验证
# ---------------------------------------------------------------------------

def run_b2(cfg: dict, *, seed: int, outdir: str) -> dict:
    from rflcc.scenarios import ScenarioGenerator

    env_cfg = cfg["environment"]
    env = CausalChaseEnv(
        horizon=env_cfg["horizon"],
        monster_move_period=env_cfg["monster_move_period"],
        monster_dash_p=env_cfg["monster_dash_p"],
        rewards=env_cfg.get("rewards"),
    )
    acc = cfg.get("scenarios", {}).get("acceptance", {})
    gen = ScenarioGenerator(env=env, delta_target_pos=acc.get("delta_target_pos", 0.4),
                            delta_leak=acc.get("delta_leak", 0.1), max_attempts=200)
    router = UpdateRouter(alpha_diag=cfg["learning"]["alpha_diag"])
    rows = []
    for cause in ("H", "L", "E"):
        for s in gen.generate(cause, base_seed=seed + {"H": 0, "L": 100, "E": 200}[cause], n=3):
            r_star = s.oracle.responsibility or {"H": 0, "L": 0, "E": 0}
            last_low = (
                s.trace.transitions[-1].state,
                s.trace.transitions[-1].action,
            )
            routed = router.route(
                responsibility=r_star, s_h=0, option=s.trace.option, last_low=last_low,
            )
            rows.append({
                "scenario": s.scenario_id, "cause": cause, "r_star": r_star,
                "rho_high": routed.high[2] if routed.high else 0.0,
                "rho_low": routed.low[2] if routed.low else 0.0,
            })
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, f"b2_seed{seed}.json"), "w") as f:
        json.dump(rows, f, indent=2)
    # 验收：L-only 场景 rho_low 明显、H-only rho_high 明显
    l_rho = [r["rho_low"] for r in rows if r["cause"] == "L"]
    h_rho = [r["rho_high"] for r in rows if r["cause"] == "H"]
    ok = (
        bool(l_rho) and min(abs(x) for x in l_rho) > 0.5
        and bool(h_rho) and min(abs(x) for x in h_rho) > 0.5
    )
    return {"ok": ok, "n_rows": len(rows)}


# ---------------------------------------------------------------------------
# B0/B1/B3/B4：学习
# ---------------------------------------------------------------------------

class BAgent:
    """Standard-HQ + 可选 diagnostic aux（按算法）。"""

    def __init__(self, algo: str, cfg: dict, env: CausalChaseEnv, rng: np.random.RandomState,
                 seq_model: SequenceModel | None, runner_rfl, runner_exhaustive):
        self.algo = algo
        lr = cfg["learning"]
        self.std = StandardHQ(
            alpha_low=lr["alpha_low"], alpha_high=lr["alpha_high"],
            gamma=cfg["environment"]["gamma"], rng=rng,
        )
        self.router = UpdateRouter(alpha_diag=lr["alpha_diag"])
        self.er5 = ER5(
            alpha_low=lr["alpha_low"], alpha_high=lr["alpha_high"],
            alpha_diag=lr["alpha_diag"], gamma=cfg["environment"]["gamma"],
            replay_k=cfg["replay"]["ordinary_replay_k"], rng=rng,
        ) if algo == "er5" else None
        self.seq_model = seq_model
        self.runner_rfl = runner_rfl
        self.runner_exhaustive = runner_exhaustive
        self.attribution_counts = {"attributed": 0, "collisions": 0}

    # -- 委托 StandardHQ --------------------------------------------------
    def select_option(self, s_h, eps): return self.std.select_option(s_h, eps)
    def select_action(self, s, eps): return self.std.select_action(s, eps)
    def update_low(self, s, a, r, s2, done): return self.std.update_low(s, a, r, s2, done)
    def update_high(self, s_h, o, g): return self.std.update_high(s_h, o, g)

    # -- 诊断归因（COLLISION 时）------------------------------------------
    def on_collision(self, trace: EpisodeTrace, s_h, option, last_low,
                     observed_feedback: str, oracle_r, oracle_primary,
                     policy_snapshot) -> dict:
        self.attribution_counts["collisions"] += 1
        if self.algo == "standard":
            return {"updated": False}
        self.attribution_counts["attributed"] += 1
        if self.algo == "immediate":
            R = Immediate().attribute(trace, observed_feedback, None, None).responsibility
            cf = 0
        elif self.algo == "pe_seq":
            out = PESeq().attribute(trace, observed_feedback, self.seq_model, None)
            R, cf = out.responsibility, 0
        elif self.algo == "cf_only":
            out = CFOnly().attribute(trace, observed_feedback, self.seq_model, self.runner_exhaustive)
            R, cf = out.responsibility, out.cf_transitions
        elif self.algo == "full_rfl":
            out = FullRFL().attribute(trace, observed_feedback, self.seq_model, self.runner_rfl)
            R, cf = out.responsibility, out.cf_transitions
        elif self.algo == "oracle_upper":
            R, cf = oracle_r, 0
        else:
            raise ValueError(self.algo)

        routed = self.router.route(
            responsibility=R, s_h=s_h, option=option, last_low=last_low,
        )
        self.router.apply(self.std.q, routed)
        metrics = compute_attribution_metrics(
            responsibility=R, oracle_r=oracle_r,
            proposed_update_mass=routed.update_mass,
            observed_feedback=observed_feedback,
            cf_transitions=cf,
        )
        return {
            "updated": True, "R": R, "metrics": metrics,
            "cf_transitions": cf, "update_mass": routed.update_mass,
        }

    def replay(self) -> int:
        if self.er5 is not None:
            return self.er5.replay(self.std.q)
        return 0


def _calibrate_sequence(cfg: dict, env: CausalChaseEnv) -> SequenceModel:
    from rflcc.scenarios import ScenarioGenerator

    acc = cfg.get("scenarios", {}).get("acceptance", {})
    gen = ScenarioGenerator(env=env, delta_target_pos=acc.get("delta_target_pos", 0.4),
                            delta_leak=acc.get("delta_leak", 0.1), max_attempts=120)
    traces = {c: [] for c in ("H", "L", "E")}
    for c in ("H", "L", "E"):
        base = cfg.get("scenarios", {}).get("calibration_seed_offset", 1_000_000)
        for s in gen.generate(c, base_seed=base + {"H": 0, "L": 100, "E": 200}[c], n=30):
            traces[c].append(s.trace)
    model = SequenceModel(
        beta=cfg["sequence"].get("beta_prior", 1.0),
        probability_floor=cfg["sequence"].get("probability_floor", 0.01),
        eta=cfg["sequence"].get("adjacent_weight_eta", 0.5),
        tau_seq=cfg["sequence"].get("temperature", 0.5),
    )
    model.calibrate(traces)
    return model


def run_learning(
    cfg: dict, stage: str, algo: str, *, seed: int, episodes: int, eval_every: int,
    use_scripted_low: bool, outdir: str, run_id: str, seq_model=None,
    checkpoint_dir: str | None = None,
) -> dict:
    env_cfg = cfg["environment"]
    over = STAGE_ENV[stage]
    env = CausalChaseEnv(
        horizon=env_cfg["horizon"],
        monster_move_period=env_cfg["monster_move_period"],
        monster_dash_p=over.get("monster_dash_p", env_cfg["monster_dash_p"]),
        monster_enabled=over.get("monster_enabled", True),
        rewards=env_cfg.get("rewards"),
    )
    lr = cfg["learning"]
    gamma = env_cfg["gamma"]
    exp = cfg.get("experiment", {})
    rng = np.random.RandomState(seed + 1000)

    # 共享 calibration（由调用方传入，frozen）+ runner（所有算法）
    runner_rfl = runner_exhaustive = None
    if algo in ("pe_seq", "cf_only", "full_rfl"):
        if seq_model is None:
            seq_model = _calibrate_sequence(cfg, env)

    agent = BAgent(algo, cfg, env, rng, seq_model, runner_rfl, runner_exhaustive)
    # FrozenQLowPolicy 需要引用 agent 的 q；runner 的 policy_for 用闭包修正
    def policy_for(o):
        return FrozenQLowPolicy(agent.std.q.low)

    oracle = None
    if algo in ("pe_seq", "cf_only", "full_rfl"):
        cc = cfg["counterfactual"]
        runner_rfl = CounterfactualRunner(
            policy_for=policy_for, env=env, top_k=cc.get("top_k_causes", 2),
            low_level_window=cc.get("low_level_window", 3),
        )
        runner_exhaustive = CounterfactualRunner(
            policy_for=policy_for, env=env, top_k=3, low_level_window=10**6,
        )
        agent.runner_rfl, agent.runner_exhaustive = runner_rfl, runner_exhaustive
    if algo != "standard":
        # feedback 的 true_primary 需要 evaluator（所有非 standard 算法共享）
        oracle = OracleEvaluator(policy_for=policy_for, env=env)
    script = ScriptedRouteFollower(0)
    feedback_p = exp.get("feedback", {}).get("p_false_symmetric", 0.4)
    injector = FeedbackInjector(p_false=feedback_p, mode="symmetric",
                                rng=np.random.RandomState(seed + 2000))

    def select_low(obs, eps):
        return script.act(obs) if use_scripted_low else agent.select_action(obs.low_state, eps)

    eval_records = []
    t0 = time.time()
    total_bellman = 0
    for ep in range(episodes):
        eps = linear_epsilon(ep, lr["epsilon_start"], lr["epsilon_end"],
                             lr["epsilon_decay_episodes"])
        env_seed = seed * 100000 + ep
        obs, _ = env.reset(seed=env_seed)
        s_h = obs.monster_start_lane
        option = agent.select_option(s_h, eps)
        env.set_option(option)

        trace = EpisodeTrace(seed=env_seed, scenario_id=f"B_{seed}_{ep}",
                             option=option, terminal_type=None, noise_tape=env.tape)
        last_low = None
        rewards = []
        done = False
        while not done:
            a = select_low(obs, eps)
            state = obs.low_state
            obs2, r, term, trunc, info = env.step(a)
            state2 = obs2.low_state
            rewards.append(r)
            if not use_scripted_low:
                agent.update_low(state, a, r, state2, term or trunc)
                if agent.er5 is not None:
                    agent.er5.add_transition(state, a, r, state2, term or trunc)
                total_bellman += 1
            trace.transitions.append(Transition(
                t=len(trace.transitions), state=state, action=a, reward=r,
                next_state=state2, terminated=term, truncated=trunc,
                option=option, agent_xy=obs.agent_xy, monster_xy=obs.monster_xy,
            ))
            trace.causal_events.extend(info["events"])
            last_low = (state, a)
            obs = obs2
            done = term or trunc

        trace.terminal_type = env.terminal_type
        trace.compute_return(gamma)
        G = trace.total_return
        agent.update_high(s_h, option, G)

        # 普通 replay（ER-5）也在每 episode 做
        total_bellman += agent.replay()

        if trace.terminal_type == TERM_COLLISION:
            # evaluator-only：oracle ground truth（所有算法共享，避免重复）
            if oracle is not None:
                ores = oracle.evaluate(trace)
                oracle_r = ores.responsibility
                oracle_primary = ores.primary
            else:
                oracle_r, oracle_primary = None, None
            observed = injector.generate(oracle_primary)
            is_false = injector.is_false(observed, oracle_primary)
            policy_snap = agent.std.q.copy()
            aux = agent.on_collision(
                trace, s_h, option, last_low, observed, oracle_r, oracle_primary, policy_snap,
            )
            agent.attribution_counts["last_feedback_false"] = is_false

        if (ep + 1) % eval_every == 0 or ep == episodes - 1:
            rec = evaluate(env, agent, seed, ep + 1, use_scripted_low=use_scripted_low)
            eval_records.append(rec)

    final = eval_records[-1]
    result = {
        "run_id": run_id, "stage": stage, "algo": algo, "seed": seed,
        "episodes": episodes, "final_success": final["success"],
        "final_safe_option": final["safe_option"], "final_return": final["return"],
        "visited_states": agent.std.q.n_visited_states(),
        "attributed": agent.attribution_counts["attributed"],
        "collisions": agent.attribution_counts["collisions"],
        "total_bellman": total_bellman,
        "wall_s": round(time.time() - t0, 2),
    }
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, f"{stage}_{algo}_seed{seed}.json"), "w") as f:
        json.dump({"result": result, "eval_records": eval_records}, f, indent=2)
    if checkpoint_dir is not None:
        from rflcc.checkpoints import save_checkpoint
        save_checkpoint(agent.std.q, checkpoint_dir, seed=seed, episodes=episodes, config_hash="v02")
    return result


def evaluate(env, agent, seed, ep_done, n_eval=50, use_scripted_low=False) -> dict:
    script = ScriptedRouteFollower(0)
    success = 0
    safe = 0
    returns = []
    for k in range(n_eval):
        env_seed = seed * 1000000 + ep_done * 1000 + k
        obs, _ = env.reset(seed=env_seed)
        s_h = obs.monster_start_lane
        option = agent.select_option(s_h, 0.0)
        env.set_option(option)
        if option != s_h:
            safe += 1
        rewards = []
        done = False
        while not done:
            a = script.act(obs) if use_scripted_low else agent.select_action(obs.low_state, 0.0)
            obs, r, term, trunc, _ = env.step(a)
            rewards.append(r)
            done = term or trunc
        if obs.terminal_type == TERM_EXIT:
            success += 1
        G = 0.0
        for r in reversed(rewards):
            G = r + 0.97 * G
        returns.append(G)
    return {
        "episode": ep_done, "success": success / n_eval,
        "safe_option": safe / n_eval, "return": float(np.mean(returns)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=list(STAGE_ENV))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--algo", default=None, choices=B_ALGOS, nargs="*")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    exp = cfg.get("experiment", {})
    episodes = args.episodes or exp.get("training_episodes", 3000)
    eval_every = max(1, episodes // 8)
    outdir = args.outdir or f"outputs/stage_{args.stage}"
    run_id = f"B-{args.stage}-{time.strftime('%Y%m%d-%H%M%S')}"

    if args.stage == "B2":
        ok_all = []
        for seed in range(args.seeds):
            res = run_b2(cfg, seed=seed, outdir=outdir)
            ok_all.append(res["ok"])
            print(f"[B2] seed {seed}: ok={res['ok']} rows={res['n_rows']}")
        print(f"[B2] H/L attribution distinguishable: {all(ok_all)}")
        return

    use_scripted_low = args.stage in ("B1",)
    algos = list(args.algo) if args.algo else (
        ["standard"] if args.stage in ("B0", "B3", "B4") else ["standard"]
    )
    # frozen sequence model：一次性校准，所有 seed/算法共享
    env_tmp = CausalChaseEnv(
        horizon=cfg["environment"]["horizon"],
        monster_move_period=cfg["environment"]["monster_move_period"],
        monster_dash_p=STAGE_ENV[args.stage].get("monster_dash_p", cfg["environment"]["monster_dash_p"]),
        monster_enabled=STAGE_ENV[args.stage].get("monster_enabled", True),
        rewards=cfg["environment"].get("rewards"),
    )
    seq_model = _calibrate_sequence(cfg, env_tmp) if any(
        a in ("pe_seq", "cf_only", "full_rfl") for a in algos
    ) else None
    results = []
    for seed in range(args.seeds):
        for algo in algos:
            r = run_learning(
                cfg, args.stage, algo, seed=seed, episodes=episodes,
                eval_every=eval_every, use_scripted_low=use_scripted_low,
                outdir=outdir, run_id=run_id, seq_model=seq_model,
            )
            results.append(r)
            print(f"[B{args.stage}/{algo}] seed {seed}: success={r['final_success']:.3f} "
                  f"safe={r['final_safe_option']:.3f} visited={r['visited_states']} "
                  f"attributed={r['attributed']} wall={r['wall_s']:.0f}s")

    gate = STAGE_GATES[args.stage]
    metric = "final_success" if gate["metric"] == "success" else "final_safe_option"
    vals = [r[metric] for r in results]
    mean = float(np.mean(vals)) if vals else 0.0
    print(f"[B{args.stage}] mean {gate['metric']}: {mean:.3f}")
    if gate["threshold"] is not None:
        passed = mean >= gate["threshold"]
        print(f"[B{args.stage}] gate {gate['metric']}>={gate['threshold']}: {'PASS' if passed else 'FAIL'}")
        if not passed:
            print(f"[B{args.stage}] STOP: 不允许进入下一阶段 / confirmatory")
            sys.exit(1)


if __name__ == "__main__":
    main()
