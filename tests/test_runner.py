from rflnext.env import BLOCKED, HORIZON, SUCCESS, TIMEOUT, W
from rflnext.noise import NoiseTape
from rflnext.qtables import QTables
from rflnext.runner import EpisodeRecord, run_episode


def _tape(seed=0, episodes=4, horizon=HORIZON, p_hazard=0.25):
    return NoiseTape.from_seed(seed, episodes=episodes, horizon=horizon, p_hazard=p_hazard)


def _route_q(goal_lane: int, hazard: int, value: float = 1.0) -> QTables:
    """A hand-built policy that drives from (0,0) to the exit on ``goal_lane``.

    Built from the tape's actual goal lane rather than a hardcoded lane, and
    keyed by the timestep that is part of the low-level state, so the fixture
    cannot silently disagree with the sampled scene.
    """
    q = QTables(n_actions=4)  # UP=0 DOWN=1 RIGHT=2 WAIT=3
    q.high[(goal_lane, hazard)] = {goal_lane: 1.0, 1 - goal_lane: 0.0}
    down = [0.0, value, 0.0, 0.0]
    right = [0.0, 0.0, value, 0.0]
    for t in range(1, HORIZON + 1):
        if goal_lane == 1:
            q.low[(0, 0, 1, t)] = list(down)
            for x in range(W):
                q.low[(x, 1, 1, t)] = list(right)
        else:
            for x in range(W):
                q.low[(x, 0, 0, t)] = list(right)
    return q


def test_run_episode_returns_record():
    rec = run_episode(episode=0, tape=_tape(), q=QTables(n_actions=4), epsilon=0.0,
                      reward_mode="A", alpha_low=0.2, alpha_high=0.15)
    assert isinstance(rec, EpisodeRecord)
    assert rec.terminal in (SUCCESS, BLOCKED, TIMEOUT)
    assert rec.steps >= 1
    assert rec.return_value in (-1.0, 0.0, 1.0)


def test_forced_correct_policy_succeeds_without_hazard():
    tape = _tape(seed=5, episodes=1, p_hazard=0.0)
    goal_lane = int(tape.goal_lane[0])
    q = _route_q(goal_lane, hazard=0)
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                      alpha_low=0.0, alpha_high=0.0)
    assert rec.goal_lane == goal_lane
    assert rec.option == goal_lane
    assert rec.terminal == SUCCESS
    assert rec.return_value == 1.0
    assert rec.labels is None


def test_hazard_blocks_a_perfect_policy():
    tape = _tape(seed=5, episodes=1, p_hazard=1.0)
    goal_lane = int(tape.goal_lane[0])
    q = _route_q(goal_lane, hazard=1)
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                      alpha_low=0.0, alpha_high=0.0)
    assert rec.option == goal_lane
    assert rec.terminal == BLOCKED
    assert rec.labels is not None
    assert rec.labels.family == "E_failure"
    assert rec.labels.u == (0, 0)


def test_reward_mode_b_gives_zero_for_failure():
    tape = _tape(seed=5, episodes=1, p_hazard=1.0)
    goal_lane = int(tape.goal_lane[0])
    q = _route_q(goal_lane, hazard=1)
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="B",
                      alpha_low=0.0, alpha_high=0.0)
    assert rec.terminal == BLOCKED
    assert rec.return_value == 0.0


def test_same_seed_is_bit_identical():
    args = dict(epsilon=0.3, reward_mode="A", alpha_low=0.2, alpha_high=0.15)
    a = run_episode(episode=0, tape=_tape(11), q=QTables(n_actions=4), **args)
    b = run_episode(episode=0, tape=_tape(11), q=QTables(n_actions=4), **args)
    assert (a.terminal, a.steps, a.return_value, a.final_x, a.option) == (
        b.terminal, b.steps, b.return_value, b.final_x, b.option
    )


def test_zero_alpha_does_not_mutate_q_tables():
    tape = _tape(seed=3, episodes=1)
    q = QTables(n_actions=4)
    before = q.deep_hash()
    run_episode(episode=0, tape=tape, q=q, epsilon=0.5, reward_mode="A",
                alpha_low=0.0, alpha_high=0.0)
    assert q.deep_hash() == before
    assert q.low == {}
    assert q.high == {}


def test_gamma_one_negative_td_is_counted():
    """Reward mode B still produces negative TD errors: Q drops from its
    optimistic value toward the zero terminal reward."""
    tape = _tape(seed=5, episodes=1, p_hazard=1.0)
    goal_lane = int(tape.goal_lane[0])
    q = _route_q(goal_lane, hazard=1, value=0.5)
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="B",
                      alpha_low=0.2, alpha_high=0.0)
    assert rec.terminal == BLOCKED
    assert rec.return_value == 0.0
    assert rec.n_negative_td >= 1


def test_low_level_state_includes_the_timestep():
    """Regression: with gamma=1 and no step reward, omitting t from the state
    lets a no-op action satisfy the Bellman equation for any value, so stalling
    becomes co-optimal and the greedy policy collapses to never moving."""
    tape = _tape(seed=1, episodes=1)
    q = QTables(n_actions=4)
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0,
                      reward_mode="A", alpha_low=0.1, alpha_high=0.1)
    states = [s for s, _ in rec.visited_low]
    assert states, "episode recorded no low-level decisions"
    assert all(len(s) == 4 for s in states), f"state is not (x, y, option, t): {states[0]}"
    assert [s[3] for s in states] == list(range(1, len(states) + 1))


def test_horizon_comes_from_the_tape_not_the_module_constant():
    """Regression: iterating over the module HORIZON while the tape was built
    for a shorter horizon indexes past the end of the tape."""
    for span in (4, 5, 6, 7, 9, 12):
        tape = _tape(seed=2, episodes=1, horizon=span)
        rec = run_episode(episode=0, tape=tape, q=QTables(n_actions=4), epsilon=0.0,
                          reward_mode="A", alpha_low=0.1, alpha_high=0.1)
        assert rec.steps <= span
        assert [s[3] for s, _ in rec.visited_low] == list(range(1, rec.steps + 1))


def test_short_horizon_still_allows_the_long_lane_with_full_slack():
    """At horizon 5 the DOWN-then-RIGHT lane is exactly reachable and no more."""
    span = 5
    tape = _tape(seed=5, episodes=4, horizon=span, p_hazard=0.0)
    for ep in range(4):
        gl = int(tape.goal_lane[ep])
        q = _route_q(gl, hazard=0)
        rec = run_episode(episode=ep, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                          alpha_low=0.0, alpha_high=0.0)
        assert rec.terminal == SUCCESS, (ep, gl, rec.steps)
