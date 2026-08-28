"""性能标定：真实环境下吞吐量（S10）。

用法：
    python scripts/benchmark.py --steps 100000

输出：
    env_steps_per_second
    cf_steps_per_second
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from rflcc.env import CausalChaseEnv
from rflcc.noise import NoiseTape
from rflcc.policies import ScriptedRouteFollower, rollout_to_trace
from rflcc.oracle import OracleEvaluator


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=100000)
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    env = CausalChaseEnv()
    # 1. env throughput：随机动作 + 随机 tape
    n_env_steps = 0
    t0 = time.time()
    tape = NoiseTape.from_seed(0)
    env.reset(noise_tape=tape, option=0)
    while n_env_steps < args.steps:
        if env.terminated or env.truncated:
            env.reset(noise_tape=NoiseTape.from_seed(np.random.randint(0, 10**9)), option=0)
        env.step(int(np.random.randint(0, 5)))
        n_env_steps += 1
    dt_env = time.time() - t0
    env_sps = n_env_steps / dt_env

    # 2. cf throughput：一次完整 oracle（含脚本 rollout）
    oracle = OracleEvaluator(policy_for=lambda o: ScriptedRouteFollower(o), env=env)
    tape2 = NoiseTape.from_seed(12345)
    trace = rollout_to_trace(
        env, tape=tape2, option=tape2.monster_start_lane,
        policy=ScriptedRouteFollower(tape2.monster_start_lane),
        seed=12345, scenario_id="bench",
    )
    t1 = time.time()
    res = oracle.evaluate(trace)
    dt_cf = time.time() - t1
    cf_sps = res.cf_transitions / dt_cf

    print(f"[benchmark] env_steps_per_second = {env_sps:.0f}")
    print(f"[benchmark] cf_steps_per_second  = {cf_sps:.0f}")
    print(f"[benchmark] one-oracle transitions = {res.cf_transitions}, "
          f"wall = {dt_cf:.2f}s")

    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "benchmark.txt"), "w") as f:
        f.write(f"env_steps_per_second {env_sps:.0f}\n")
        f.write(f"cf_steps_per_second {cf_sps:.0f}\n")


if __name__ == "__main__":
    main()
