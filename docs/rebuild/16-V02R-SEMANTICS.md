# 16 — V0.2R object and type semantics

Status: frozen — logged as **A65**. This document defines the objects V0.2R may
name. It implements no method and specifies no algorithm.

---

## 1. The question this stage exists to answer

V0.1R established *what mechanism actually fired*. V0.2R is about **where learning
responsibility should land** — and that question is unanswerable until one prior
question is settled honestly:

$$\boxed{\text{does "where to change" mean repairing the fault, or compensating for the outcome?}}$$

Legacy v0.4 conflated the two. A55–A64 made the conflation visible: after A57,

$$do(C_P = \text{identity}) \qquad\text{and}\qquad do(z = z')$$

are **not the same kind of thing**. The first repairs the process-commit
mechanism. The second may merely route around it by running a different strategy.
A strategy replay that rescues the outcome does **not** thereby mean strategy
should carry the learning responsibility. So the old implicit identity

$$\text{minimal sufficient rescue} \;\Rightarrow\; \text{credit truth}$$

is **withdrawn**.

## 2. Five objects, not two

$$\boxed{C^{\text{fire}} \neq R^{\text{mech}} \neq R^{\text{rescue}} \neq \Gamma^{\text{credit}} \neq W^{\text{update}}}$$

| object | what it is | owner |
|---|---|---|
| $C^{\text{fire}}$ | which mechanisms actually executed on the factual trajectory | **V0.1R, closed** |
| $R^{\text{mech}}$ | interventions that **restore the faulty mechanism** | evaluator truth, defined here |
| $R^{\text{rescue}}$ | interventions that make the **episode succeed**, by any means | evaluator truth, defined here |
| $\Gamma^{\text{credit}}$ | the unit on which learning responsibility should land | **V0.2R's subject** |
| $W^{\text{update}}$ | the write actually performed | V0.3R onward |

$R^{\text{mech}}$ and $R^{\text{rescue}}$ may coincide, and where they do not, the
difference *is* the structure V0.2R exists to study. Conflating them is what made
"the process was wrong" and "switching strategy fixes it" look like one finding.

## 3. Input contract

$$X_{0.2} = \bigl(I^{\text{factual}}_{0:T},\; Z^{\text{fire}}_{\text{truth}}\bigr)$$

V0.2R keeps `07`'s good instinct — hand over cause truth so attribution error is
isolated rather than compounding. But it is written precisely: the method receives
the factual trajectory and the **fired-mechanism vector**, and must **not** receive

* latent fault parameters ($M$), which would localise credit for free;
* either repair truth $R^{\text{mech}}$ or $R^{\text{rescue}}$;
* $\Gamma^{\text{credit}}$ itself, which is the thing being predicted;
* $W^{\text{update}}$, which is not V0.2R's object at all.

Note the deliberate asymmetry with V0.1R: V0.1R was handed *no* truth and had to
infer it; V0.2R is handed the answer to V0.1R's question and tested on the next
one. That is what "isolate the error" means, and it is why $C^{\text{fire}}$ may be
an input here while being the endpoint there.

## 4. Credit-unit ontology

`07`'s four units — `Plan / Decision_t / Execution_t / Process` — no longer match
the SCM. In particular `Strategy` and `ProcessCommit` were one label covering two
different mechanisms (A55), and a single `Execution` swallowed the controller/plant
boundary that A53 exists to expose.

$$\boxed{\Gamma = \{\;\text{Strategy},\ \text{ProcessCommit},\ \text{Decision}_t,\ \text{ControllerSite},\ \text{ExternalPlant},\ \text{Unknown/NoWrite}\;\}}$$

* `Strategy` — which option the episode is run under. Its intervention is
  $do(z = z')$, a **strategy replay**.
* `ProcessCommit` — the process/commit edge. Its intervention is
  $do(C_P = \text{identity})$, a **mechanism repair**. A57 made this first-class
  precisely so it cannot be confused with the line above.
* `Decision_t` — one decision at one timestep, $do(d_t = d')$.
* `ControllerSite` — one controller cell, $do(C_X(s^\ast, a^{cmd}) = a^{cmd})$.
* `ExternalPlant` — outside the agent; no agent-side write is the honest answer.
* `Unknown/NoWrite` — the answer that must remain **expressible**. A method forced
  to name a responsible unit is being pushed toward false credit by construction.

`Unknown/NoWrite` is not a failure mode; it is the correct answer when $R^\ast$ is
empty or when the evidence cannot localise.

## 5. Two repair truths, both minimal

$$\mathcal R^{\text{mech},\ast}(\ell), \qquad \mathcal R^{\text{rescue},\ast}(\ell)$$

each the set of **minimal-cardinality** interventions of its kind. Freezing both
means a case may have a mechanism repair, a rescue, both, or neither, and the
census can report which.

**Ties are retained.** $|R^\ast| \neq \#R^\ast$ holds exactly as in A57's Gate E:
the cardinality and the number of tied minimisers are separate reported quantities,
and no downstream metric may assume a unique repair.

## 6. The projection, and set-valued responsibility truth

Which repair corresponds to which credit unit must be **frozen**, not decided by
whatever code happens to run:

$$\pi_{\text{credit}}: R^{\text{mech}} \longrightarrow \Gamma$$

$$\boxed{\Gamma^\ast(\ell) = \{\,\pi_{\text{credit}}(r) : r \in \mathcal R^{\text{mech},\ast}(\ell)\,\}}$$

Three consequences worth stating, because each is a place the old design leaked:

* the projection is from **$R^{\text{mech}}$, not $R^{\text{rescue}}$** — rescuing an
  outcome by switching strategy must not mint `Strategy` credit for a process fault;
* $\Gamma^\ast$ is **set-valued**, so tie structure survives into the endpoint;
* $\pi_{\text{credit}}$ must be a total, declared function on the repair lattice,
  including the empty repair (which maps to `Unknown/NoWrite`, not to nothing).

## 7. Endpoints, revised

`07`'s `InterventionSufficiency` is **not** adopted as primary. It requires a
`credit unit → canonical intervention` conversion rule, and that conversion is
already most of V0.3R's repair primitive — so a "representation comparison" would
be measured partly through a repair rule, reintroducing exactly the contamination
this amendment removes.

**Primary, on set-valued credit truth:**
$$\text{CreditCoverage}, \qquad \text{FalseCreditRate}$$

which ask whether the representation expresses *the right place to change at all*,
before any repair is executed.

**Secondary / evaluator diagnostic:** `OutcomeRepairSufficiency`.

## 8. Old Gate E does not carry over

Gate E passed under the **old** repair ontology: $|R^\ast| = 0$ for 925,800 cases,
$|R^\ast| = 1$ for 113,160, with no case needing two or more. That result stays as
a **regression reference** and is **not** a prerequisite theorem for V0.2R,
because it never separated $R^{\text{mech}}$ from $R^{\text{rescue}}$.

Once this ontology is frozen, a **new exhaustive truth census** runs on the
existing 1,038,960-world `DenseSupport`, reporting **DGP-weighted mass alongside
world counts** — a count answers "how many worlds", the mass answers "how
likely", and V0.1R showed those can differ by an order of magnitude (the
enumeration ratio 10.9% versus the DGP mass 0.8%).

## 9. Order

$$\boxed{\text{A65 (this)} \rightarrow \text{A66 repair/rescue enumerator} \rightarrow \text{A67 projection + set-valued truth} \rightarrow \text{new Gate E census} \rightarrow \text{rewrite 07 endpoints} \rightarrow \text{method contract} \rightarrow \text{smoke/dev/confirmatory}}$$
