# V228: remove unsupported restrictions, not actual evidence

2026-11-12. The user explicitly asked to leave the three-hour V227 run running and remove unnecessary conservative programming. This isolated revision does not alter any V227 running source, criterion, checkpoint or capture.

## 1. Joint representation learning instead of preventive gradient cuts

For mixed agents and N228:

    z = encoder(current observation, goal, actual historical nodes)
    L = L_TD + L_observed_facts + .1 L_actual_effect
        + candidate preference or SLEEP loss when that training stage occurs.

Unlike V227, both factual and actual-effect losses can update the shared encoder, memory reader and applicability network. No `detach(z)` lies on these two training paths. Evaluating a target network, freezing a teacher target, and choosing actions without building a gradient graph remain ordinary numerical semantics, not prohibitions on learning.

Joint gradients can conflict; that is a measurable modeling question, not a reason to set them to zero in advance. We do not add a learned gate whose only job is to suppress these gradients. The architecture and parameter count stay the same for comparability.

## 2. Use signed actual outcomes; eliminate samplewise vetoes

For two actual paired trial outcomes d1,d2, let D=(d1+d2)/2. A candidate preference at the tested source uses:

    g = score(a)-score(b)
    L_preference = |D| softplus(-sign(D) g).

This uses positive AND negative evidence. One unfavorable replicate does not veto a positive mean; a negative mean teaches the opposite conditional preference. D=0 supplies no directional teaching target (ordinary learning and the zero-effect factual target remain). A finite-horizon trial effect still is NOT substituted as a full-horizon Q value target.

New sequence: actual trials -> temporary teacher -> SLEEP student -> ONE paired full-task student/reference comparison. Remove the intermediate teacher gate. The ordinary reference receives the same base optimization batches as the proposed candidate. Adoption uses mean(actual student-reference return)>0; no per-replicate non-degradation requirement, no automatic retry. Individual adverse outcomes remain recorded. This is an engineering selection rule under noisy observations, NOT a confidence guarantee or a theorem that every accepted update truly helps.

## 3. Preserve history; distinguish finite reads from deletion

Actual events live once in an append-only identity-indexed node store. An immutable view is a prefix frontier plus any actual branch-local events. That lets replay refer to the evidence available at that source without copying all history or leaking later outcomes backward. Actual branch experiments may add new events; drawing an event again for training never increases the evidence count.

Network batching supports variable historical length, learned content attention and a null node. There is no 16-node age cutoff. The store offers an explicit optional uniform read budget over the ENTIRE eligible view; this is a compute budget, not deletion or a most-recent-only rule. In this bounded check the network reads all eligible nodes. No claim of affordable full-history attention at millions of events is made.

Keep every transition of completed failed ordinary trajectories as a possible actual-test source, not only the last eight states of the latest failure. For each investigation a uniform candidate batch of at most 16 sources is drawn from that complete source archive, then the existing learned disagreement scores rank it. Every older source remains eligible. This is sampled learned selection, not an assertion that every relevant historical cause is found. Success still receives ordinary learning, not new diagnostic calls.

## Scope

V227's numerical baseline, environment physics, six signal/method conditions and compact parameter count remain reference points; the on-going V227 run is not relabeled V228. Actual legal-action restrictions, data provenance, task budgets and one real adoption comparison remain because they define the experiment and the user's practice-before-adoption requirement. No new approval workflow or review hierarchy is added. This change removes specified restrictions; it does not by itself establish higher task scores, calibrated uncertainty or general-purpose feedback competence.
