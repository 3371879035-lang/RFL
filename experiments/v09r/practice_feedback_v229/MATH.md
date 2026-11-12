# V229: learn which practice helps, rather than veto learning

Written before execution, 2026-11-12. This is a bounded repair experiment, not a claim
that writing a network supplies learned competence. V227/V228 and their results stay
unchanged. The strong comparator is V227 F-R, not a deliberately weak nonlearner.

## What was wrong with the previous surrogate

Prediction disagreement is not expected improvement from an investigation.
Moreover, adding a 16-step effect estimate to a 64-step outcome prediction does not
estimate either full-task effect. More permissive gates alone cannot fix this.

At a historical failure state h, let pi be the CURRENT frozen continuation policy,
b its greedy action, and a a legal alternative. With two fresh paired noise tapes,
execute both first actions through the REAL remaining episode, not a model rollout:

    D(h,a,b;pi) = mean_j [U(real(a,pi,j)) - U(real(b,pi,j))].

U is the existing reported task objective: pursuit score/100, or generic terminal
success + 1/(1+distance). Neither reward convention nor physical task is changed.
These are policy-conditional action effects, not unique causes or causal percentages.
An earlier intervention can test part of a failure explanation; it does not recover
every cause. The current model may be used to revisit an old state with knowledge
available NOW, explicitly recorded as a new intervention, not the original rollout.

## Learn a proposal, not a replacement answer

Use the existing trainable 16-output effect head, e_theta(h). Fit

    L_effect = Huber(e_theta(h)_a - e_theta(h)_b, D).

It receives gradients through the encoder AND memory attention. It is used ONLY
to propose new real trials. Old effects are not substituted as current Q targets.
Policy drift, partial observation and finite replication can make them inapplicable;
the next proposal is tested again. Ordinary Q learning uses the real transitions.

Draw 16 source states uniformly from ALL completed failed trajectories. For their
legal alternative actions, the learned condition chooses the maximum predicted
positive improvement; 20% of choices are uniform to keep gathering counterevidence.
The matched random condition uses uniform source/action selection. Both learn the
same effect head; only its use for choosing trials differs. No disagreement bonus,
confidence cutoff, or hand-written 'important cause' label is used. Source batch
size and 20% exploration are disclosed compute/exploration choices, not learned
competence. Learned allocation may still lose to random allocation.

## Practice, consolidation and one actual comparison

All real trials enter ordinary replay, including negative and zero differences.
A signed temporary preference has loss

    L_preference = abs(D) * softplus(-sign(D) * (Q_a-Q_b)).

For D=0 it contributes zero, not a fabricated direction. The temporary student gets
8 rehearsal updates on real history plus this tested preference; a reference gets
8 ordinary updates using the IDENTICAL history minibatches. There is no intermediate
teacher network, teacher test, or requirement that both replicas improve. Compare
student and reference once on two fresh paired full tasks and keep the larger mean.
This is a noisy finite experimental selection, not a guarantee of no harm. Ordinary
learning is never subject to this veto, and rejected candidates' actual data remain.
The rehearsal is SLEEP-inspired consolidation, not a reproduction of SLEEP or a
claim that the network invents research proposals in language.

## Memory and compute

Retain actual events once in an append-only bank. Historical training views retain
their chronology; new trials get a view of knowledge available before those trials.
Read at most 64 uniformly sampled nodes from the ENTIRE eligible view, then use
trainable attention/applicability. This is a read-compute budget, not deletion of
older events. It does not solve large-scale learned retrieval: rare useful events
may be missed. Zero copies of a fact become extra independent observations.

The 101-field memory node still contains public vectors/action/consequences, not
the full spatial image. Current observations include the image. This remaining
representation limit is explicit; this repair does not claim complete spatial memory.

## Fixed experiment and interpretation

Three groups: original V227 F-R, open/random, open/learned. New groups have the SAME
213329-parameter architecture and initialization as the comparator; factual/effect
gradients are open. Different active heads and FLOPs are reported, not called equal.
Three fresh seeds 271/277/283 in pursuit and generic; 6 rounds, each 4096 actual steps
and 256 optimizer calls per model. Total 442368 charged training steps. Trials and
final comparisons consume that budget; their data can also train ordinary learning.
Fixed-weight evaluations at rounds 0,3,6: 32 scenarios for greedy and epsilon .1.
Evaluation experience never enters training. Maximum evaluation steps 452736;
total environment cap 895104. Wall limit 1800 seconds, six CPU workers, one Torch
thread each. No automatic retries or outcome-dependent extensions. Partial/failure
stays partial/failure. These are three training seeds, not 96 independent seeds.

The original-vs-open contrast is a bundled repair, not attribution to a single fix.
Open/random vs open/learned isolates proposal selection. Scores and three-point
curves can be zero or worse; no claim of saturated training or general superiority.
Pure-feedback F0 is NOT silently relabeled: it is not in this targeted mechanism
contrast, and its known weak pursuit control remains unresolved by this experiment.
