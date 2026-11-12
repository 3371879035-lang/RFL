"""V0.8 candidate: factual one-step readout, not a native learner or runner.

Only public successors, own outcome counts, own downstream Q and the explicit
reward convention enter this function. It neither changes Q nor draws samples.
Unknown edges use the declared Beta(1, 1) prior, not a fabricated observation.
"""


def factual_one_step_readout(state, successors, goal, counts, q, failure_reward):
    """Return an action and its complete two-command arithmetic explanation.

    successors[(state, command)] is the publicly given forward destination.
    Collision is terminal. Every ordinary state has commands 0 and 1.
    Counts and Q use tuple keys; this is a new, explicit candidate interface.
    """
    rows = []
    for action in (0, 1):
        forward, collision = counts.get((state, action), (0, 0))
        probability = (forward + 1) / (forward + collision + 2)
        nxt = successors[(state, action)]
        continuation = (
            1.0 if nxt == goal
            else max(q.get((nxt, a), 0.0) for a in (0, 1))
        )
        score = probability * continuation + (1.0 - probability) * failure_reward
        rows.append({
            "action": action,
            "counts": (forward, collision),
            "probability": probability,
            "successor": nxt,
            "continuation": continuation,
            "score": score,
        })
    best = max(rows, key=lambda row: (row["score"], row["probability"], -row["action"]))
    return best["action"], tuple(rows)
