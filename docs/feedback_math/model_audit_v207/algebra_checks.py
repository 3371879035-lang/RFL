"""V207 mathematical audit only: exact finite examples and source AST.

No learner, torch, environment, RNG, old checker, or stored trajectory execution.
Counterexamples demonstrate possible failures of an inference, not diagnoses of
which mechanism caused each previously measured native outcome.
"""
import ast
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V206 = ROOT / 'experiments/v09r/memory_trial_model_v206'
old_pins = json.loads((V206/'native_exit.json').read_text())['inputs_before']
for name, digest in old_pins.items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
additional = ['docs/feedback_math/MATHEMATICAL_MODEL_V1.md', 'docs/feedback_math/NETWORK_SPEC_V1.md',
              'docs/feedback_math/model_audit_v207/AUDIT.md', 'docs/feedback_math/model_audit_v207/algebra_checks.py',
              'experiments/v09r/memory_trial_model_v206/RESULTS.md',
              'experiments/v09r/memory_trial_model_v206/diagnostics.json']
pins = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in list(old_pins)+additional}
with (HERE/'input_binding.json').open('x', encoding='utf-8') as f:
    json.dump(pins, f, indent=2)
checks = []


def save(name, **values):
    checks.append(dict(name=name, verified=True, **values))


# Same decision input, opposite equiprobable correct actions.
for p in (F(0), F(1,5), F(1,2), F(1)):
    assert (1-p)/2 + p/2 == F(1,2)
save('aliasing_bound', expected_correctness=F(1,2))

# Identity used by V2 is correct, but concerns prediction under a given law.
for p in (F(0), F(1,4), F(1,2), F(3,4), F(1)):
    for q in (F(0), F(1,4), F(1,2), F(3,4), F(1)):
        assert p*(1-q)**2 + (1-p)*q**2 == (q-p)**2+p*(1-p)
save('brier_identity', exact_grid_points=25)

# Smaller behavior-weighted prediction error can induce the worse action.
truth = [F(1,2), F(9,10)]
behavior = [F(99,100), F(1,100)]
expert_a, expert_b = [F(1,2), F(49,100)], [F(2,5), F(4,5)]
risk = lambda pred: sum(mu*(p-q)**2 for mu,p,q in zip(behavior,truth,pred))
assert risk(expert_a) == F(1681,1000000) < risk(expert_b) == F(1,100)
assert max(range(2), key=lambda a:expert_a[a]) == 0
assert max(range(2), key=lambda a:expert_b[a]) == 1
save('prediction_control_mismatch', excess_brier_a=risk(expert_a), excess_brier_b=risk(expert_b),
     chosen_true_value_a=truth[0], chosen_true_value_b=truth[1])

# XOR: a two-unit fixed ReLU construction exists; an additive threshold cannot
# realize all four labels (the inequality proof is in AUDIT.md).
relu = lambda x:max(F(0),x)
truth_table = []
for x in (0,1):
    for y in (0,1):
        nonlinear = relu(F(x+y))-2*relu(F(x+y-1))
        assert nonlinear == (x ^ y)
        additive_or = int(x+y > 0)
        truth_table.append(dict(x=x,y=y,xor=x^y,relu=nonlinear,additive_or=additive_or))
assert sum(r['xor']==r['additive_or'] for r in truth_table)==3
save('xor_constructive_network_and_additive_witness', table=truth_table,
     best_additive_noisy_success_upper_bound=F(3,4)*F(9,10)+F(1,4)*F(1,10))

# Full-history behavior is randomized with positive support. Coarsening away X
# changes association into a misleading action estimate, even without drift.
joint = {(0,0):F(9,20),(0,1):F(1,20),(1,0):F(1,20),(1,1):F(9,20)}
observed, interventional, ips = [], [], []
for a in (0,1):
    observed.append(sum(p*x for (x,b),p in joint.items() if b==a)/sum(p for (x,b),p in joint.items() if b==a))
    interventional.append(F(1,2))  # Structural equation Y=X, unaffected by action.
    ips.append(sum(p*x/(2*p) for (x,b),p in joint.items() if b==a))
assert observed == [F(1,10),F(9,10)]
assert interventional == ips == [F(1,2),F(1,2)]
save('coarsening_selection_bias', observed=observed, do_action=interventional, known_behavior_ips=ips)

# V2's posterior readout and distinction between latent mean and next outcome.
alpha = [F(3),F(4),F(2),F(3)]
total = sum(alpha)
delta = (alpha[1]-alpha[2])/total
second = (alpha[1]*(alpha[1]+1)+alpha[2]*(alpha[2]+1)-2*alpha[1]*alpha[2])/(total*(total+1))
variance = second-delta**2
predictive_variance = (alpha[1]+alpha[2])/total-delta**2
assert delta == F(1,6) and variance == F(17,468)
assert predictive_variance == (total+1)*variance
assert 1-(5*F(1,2)**4-4*F(1,2)**5) == F(13,16)
save('dirichlet_algebra', delta=delta, posterior_variance=variance,
     next_difference_variance=predictive_variance, probability_positive=F(13,16))

# One allowed pair, B=4: independent exact hand enumeration, not old DP code.
after_pair_values = []
for outcome in range(4):
    a = [F(1)]*4
    a[outcome] += 1
    old,new=(a[2]+a[3])/5,(a[1]+a[3])/5
    after_pair_values.append(2*max(old,new))
trial_value = 1-F(1,50)+sum(after_pair_values)/4
assert trial_value == F(52,25) > 2
save('restricted_bellman_exact_value', trial_value=trial_value, keep_value=F(2))

# Positive expected gain is compatible with a nonzero harmful-adoption risk.
gain = F(9,10)*F(1,10)+F(1,10)*F(-4,5)
assert gain == F(1,100)>0
save('expected_gain_does_not_bound_harm', mean_delta=gain, harmful_probability=F(1,10))

# If both policy functions are known to be identical, independent outcome noise
# may produce 01, but true mean difference is exactly zero.
same_policy_actual_delta = F(0)
unconstrained_alpha = [F(1),F(2),F(1),F(1)]
unconstrained_delta = (unconstrained_alpha[1]-unconstrained_alpha[2])/sum(unconstrained_alpha)
assert unconstrained_delta == F(1,5) != same_policy_actual_delta
save('known_policy_identity_prior_counterexample', known_delta=same_policy_actual_delta,
     unconstrained_dirichlet_delta_after_01=unconstrained_delta)

# Separating labels does not license a product-of-marginals approximation.
q = [F(1,2), F(0), F(0), F(1,2)]
q_product = [F(1,4)]*4
tv = sum(abs(a-b) for a,b in zip(q,q_product))/2
assert tv == F(1,2)
save('structure_regime_dependence', joint=q, product=q_product, total_variation=tv)

# eta=4 fails this particular exp-concavity/Jensen step. This does not refute
# all possible expert regret bounds or change V2's explicitly heuristic status.
lhs = math.exp(-4*.5**2)
rhs = (math.exp(-4*0**2)+math.exp(-4*1**2))/2
assert lhs < rhs
save('eta4_not_plain_exp_concavity_certificate', lhs=lhs, rhs=rhs,
     does_not_refute_all_regret_bounds=True)

# A retained raw event can still be inaccessible to the finite selector bank.
obs0 = [[i,0,0] for i in range(15)]
obs1 = [row[:] for row in obs0]
obs1[12][1] = 1
def visible(obs):
    return [0]+obs[-1][1:]+[v for row in obs[:-1][:12] for v in row[1:]]
assert obs0 != obs1 and visible(obs0)==visible(obs1)
save('retained_but_unread_history', differing_past_index=12, selector_count=27, visible_equal=True)

# Static source inspection only; no torch import or parameter initialization.
tree = ast.parse((ROOT/'src/feedback_program_v206/network.py').read_text())
shapes = []
for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='nn' and node.func.attr=='Linear':
        assert any(k.arg=='bias' and isinstance(k.value,ast.Constant) and k.value.value is False for k in node.keywords)
        shapes.append((ast.literal_eval(node.args[0]),ast.literal_eval(node.args[1])))
assert shapes == [(1,1),(1,1),(4,3)]
parameter_scalars = sum(a*b for a,b in shapes)
assert parameter_scalars == 14
save('neural_arithmetic_source_boundary', linear_shapes=shapes, parameter_scalars=parameter_scalars,
     expert_state_weights=3*27, factual_count_cells=3*27*2*3*2, runtime_model_imports=0)

for name,digest in pins.items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
result = dict(status='ALGEBRA_AND_STATIC_CHECKS_MATCH', check_groups=len(checks), checks=checks,
              source_pins_unchanged=len(pins), original_v206_pins_matched=len(old_pins),
              new_environment_episodes=0, new_parameter_updates=0, old_fixture_or_checker_runs=0,
              claims='Exact examples and static mapping only; not an end-to-end corrected-model experiment.')
with (HERE/'algebra_result.json').open('x',encoding='utf-8') as f:
    json.dump(result,f,ensure_ascii=False,indent=2,default=str,allow_nan=False)
print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
