# 17 — V0.2R method contract

Status: frozen — logged as **A69**. Native alphabets, the evaluator-side semantic
expansion, and the typed information boundary. No method is implemented here.

---

## 1. The type problem this document exists to fix

The three real candidate representations do not live in one space:

$$\hat U_{\text{module}} \subseteq \{H, L\}, \qquad
\hat U_{\text{trajectory}} \subseteq \{\text{Episode}\}, \qquad
\hat U_{\text{causal}} \subseteq \Gamma(I)$$

but the primary endpoints are set operations **on $\Gamma$**:

$$\text{Coverage}(\hat\Gamma, \Gamma^\ast), \qquad \text{FCR}(\hat\Gamma, \Gamma^\ast)$$

Without a frozen expansion, $H/L$ and $\{\text{Episode}\}$ cannot be intersected
with `ProcessCommit` / `Decision_t` / `ControllerSite` / `ExternalPlant` /
`Unknown/NoWrite` at all. So the pipeline is

$$\text{native proposal} \;\xrightarrow[\text{evaluator-side, frozen}]{\ \eta_R\ }\; \hat\Gamma \;\xrightarrow{\ \text{Coverage/FCR}\ }\; \Gamma^\ast$$

$$\eta_R: \mathcal U_R \times I^{\text{factual}} \longrightarrow 2^{\Gamma(I)}$$

**This is not the conversion rule A67 demoted.** $\eta_R$ is a *semantic
expansion*: it names which credit units a native proposal means. It executes no
repair. The `credit unit → canonical intervention` conversion is a V0.3R
operational primitive and stays out of the primary comparison. Conflating them is
how a "representation comparison" would quietly become a repair-algorithm
comparison.

$$\boxed{\eta_R \text{ must not read } Z^{\text{fire}}_{\text{truth}}}$$

The **method** may read $Z^{\text{fire}}_{\text{truth}}$ — V0.2R hands it over on
purpose. The **expansion** may not, or a coarse representation's expander could
use cause truth to pick out exactly the right fine-grained units, which is the
evaluator upgrading a coarse schema into a causal one for free. $\eta_R$ is a
function of the native proposal and $I^{\text{factual}}$ only.

---

## 2. Input contract

A73 split what one symbol used to name. `sigma0` returns the learner-visible
evidence as **two** parts, `(rows, feedback)`, so "the method input" and "the
locator input" are different objects:

$$X^{\text{obs}}_{0.2} = \bigl(\text{rows}, \text{feedback}, Z^{\text{fire}}_{\text{truth}}\bigr),
\qquad
X^{\text{loc}}_{0.2} = \bigl(\text{rows}, Z^{\text{fire}}_{\text{truth}}\bigr)$$

$$q : X^{\text{obs}}_{0.2} \to X^{\text{loc}}_{0.2}, \qquad
q(\text{rows}, \text{feedback}, Z^{\text{fire}}) = (\text{rows}, Z^{\text{fire}})$$

All three real methods receive **identical typed input**, namely
$X^{\text{obs}}_{0.2}$; `CausalSetLocator` receives $X^{\text{loc}}_{0.2}$ (A73,
`12` §60). Also allowed, because it
is public mechanism knowledge rather than evaluator truth:

* the public $\Gamma$ ontology and its `agent_writeable` flags;
* the environment/action grammar;
* a **read-only** $\pi_D^\ast(s, z, m)$ reference-policy view, which is what makes
  locating `Decision_t` reasonable rather than oracular.

**Forbidden inputs:** latent fault parameters $M$; $Z^{\text{pres}}$;
$\mathcal R^{\text{mech}}$; $\mathcal R^{\text{rescue}}$; $\Gamma^\ast$; world id;
rows-block id; the `DenseSupport` hypothesis set; DGP weights; any
`outcome_after(intervention)` oracle; any write target.

$$\boxed{B_Q = 0, \quad \text{no query session, no counterfactual evaluator calls}}$$

V0.2R is not V0.1R with a different head: there is nothing to query.

---

## 3. Episode-local credit domain

$$\Gamma(I) = \{\texttt{Strategy}, \texttt{ProcessCommit}, \texttt{ExternalPlant}, \texttt{Unknown/NoWrite}\}
\;\cup\; \{\texttt{Decision}_t : t \in I\}
\;\cup\; \{\texttt{ControllerSite}_t : t \in I\}$$

Episode-local, so a method **cannot name a timestep or site that never occurred**.

---

## 4. Native alphabets and the frozen expansions

| method | native output | $\eta_R$ |
|---|---|---|
| $R_{\text{module}}$ | $\hat U \subseteq \{H, L\}$ | $\eta_{\text{module}}$, section 4.1 |
| $R_{\text{trajectory}}$ | $\hat U \subseteq \{\text{Episode}\}$ | $\eta_{\text{trajectory}}$, section 4.2 |
| $R_{\text{causal}}$ | $\hat U \subseteq \Gamma(I)$ | $\eta_{\text{causal}} = \mathrm{id}$ |

**$R_{\text{repair}}$ is not a fourth method.** `07` calls it a reference ceiling,
so the interface must actually separate it:

$$\texttt{OracleCreditAdapter}(\Gamma^\ast) \longrightarrow \Gamma^\ast$$

evaluator-only, taking truth directly and **not** $X^{\text{obs}}_{0.2}$. It may not share the
ordinary method path — otherwise we repeat A59's risk of a type that claims to be
an oracle while sharing the inference entry point.

### 4.1 $\eta_{\text{module}}$, frozen

$H/L$ is a **granularity** partition of the same unit space, not a second ontology.
The split is between episode-level units and indexed units:

$$\boxed{\eta_{\text{module}}(H) = \{\texttt{Strategy}, \texttt{ProcessCommit}, \texttt{ExternalPlant}, \texttt{Unknown/NoWrite}\}}$$

$$\boxed{\eta_{\text{module}}(L) = \{\texttt{Decision}_t : t \in I\} \cup \{\texttt{ControllerSite}_t : t \in I\}}$$

and for $\hat U \subseteq \{H,L\}$, $\eta_{\text{module}}(\hat U) = \bigcup_{u\in\hat U}\eta_{\text{module}}(u)$.

The two halves are disjoint and their union is $\Gamma(I)$, so a coarse
representation can express any truth — at coarse granularity, and paying FCR for
the units it over-covers. That is what makes the comparison meaningful: coarse
versus fine on one shared space, rather than two scores on two spaces.

**A rejected alternative is recorded.** Mapping `ExternalPlant` and
`Unknown/NoWrite` to *neither* half would make $R_{\text{module}}$ structurally
unable to express an external fault, so it would score Coverage = 0 on every
plant-fault episode for a reason that has nothing to do with the representation's
quality. That collapses the comparison into an oracle-tells-us-apart artefact, so
it is not adopted.

### 4.2 $\eta_{\text{trajectory}}$, frozen

$$\boxed{\eta_{\text{trajectory}}(\{\text{Episode}\}) = \Gamma(I)}$$

"Something in this run" means *every* unit in this episode, and nothing narrower.
Written out rather than left to the name, so the coarsest representation cannot
quietly narrow itself at implementation time. Its signature is Coverage $= 1$
with maximal FCR — the propose-everything baseline that the co-primary pair exists
to punish.

### 4.3 An implementation hazard the freeze prevents

Because $R_{\text{module}}$'s native alphabet is only $\{H,L\}$, an implementer
who is handed $\Gamma^\ast$ could be tempted to let $R_{\text{module}}$ emit
fine-grained units directly. The typed pipeline forbids it: the method returns
$H$ or $L$ and the **evaluator** expands. Without that, $R_{\text{module}}$ would
degenerate into $R_{\text{causal}}$ and the comparison would be between two copies
of the same schema.

---

## 5. Prediction semantics

$$\varnothing \neq \{\texttt{Unknown/NoWrite}\}$$

$\varnothing$ is **abstention**: the method proposed no credit at all.
`{Unknown/NoWrite}` is a **substantive verdict**: the agent's ontology contains no
writable mechanism to blame. With truth $\Gamma^\ast = \{\texttt{Unknown/NoWrite}\}$
they must not be scored alike, otherwise "say nothing" is rewarded as correct.

For an empty prediction the pair punishes it by itself:

$$\boxed{\text{Coverage} = 0, \qquad \text{FCR} = 0}$$

There is no automatic relabelling of abstention into `Unknown/NoWrite`.

**Set-valued output is retained.** No API may demand a single-label argmax:

$$|\hat\Gamma| \ge 0, \qquad |\Gamma^\ast| \ge 1$$

The truth denominator never vanishes: A67 maps an empty mechanism repair to
`Unknown/NoWrite`, so $\Gamma^\ast$ is non-empty for every world — verified on all
1,038,960 of them.

---

## 6. `agent_writeable`, defined here

A67 left `Strategy` unassigned, so the definition is stated rather than inferred.
**Inferring `true` from $do(z = z')$ is exactly the mistake to avoid**: being able
to perform a runtime intervention is not the same as V0.3R being permitted a
persistent write.

> `agent_writeable(u) = true` iff V0.3R's frozen update primitive is permitted to
> write persistently to unit $u$.

| unit | `agent_writeable` | source |
|---|---|---|
| `ProcessCommit` | true | A67 |
| `Decision_t` | true | A67 |
| `ControllerSite` | true | A67 |
| `ExternalPlant` | false | A67 |
| `Unknown/NoWrite` | false | A67 |
| `Strategy` | **false** | **assigned here** |

`Strategy` is a rescue atom, not a credit target; no frozen write primitive
addresses it, and it never appears in $\Gamma^\ast$ (zero occurrences over the full
support). A version that later makes strategy a write target must amend this
explicitly.

---

## 7. S2 — the assertion map

$$\boxed{\text{S2 = interface, typing and information-flow semantics only}}$$

It does **not** test which representation is more accurate. That is the
experiment.

1. **Input invariance under hidden changes.** Holding $I^{\text{factual}}$ fixed,
   varying hidden $M$, $Z^{\text{pres}}$, $\mathcal R^{\text{mech}}$,
   $\mathcal R^{\text{rescue}}$ and $\Gamma^\ast$ must not change any method's
   input.
2. **No support identity.** No method can reach world id, rows-block id, the
   hypothesis set, or DGP weights.
3. **Alphabet closure.** Each native output lies in its own alphabet; a
   $R_{\text{module}}$ run returning a $\Gamma$ unit is a protocol error.
4. **Expansion is truth-independent.** $\eta_R$ gives the same result for the same
   native proposal and $I^{\text{factual}}$ across different truth worlds.
5. **`ExternalPlant` survives scoring.** It stays in the denominator and in the
   scoreable space; `agent_writeable = false` never causes the evaluator to drop it.
6. **Rescue cannot move truth.** A successful strategy rescue changes no
   $\Gamma^\ast$.
7. **Abstention $\neq$ NoWrite.** $\varnothing$ and $\{\texttt{Unknown/NoWrite}\}$
   score differently against the same truth.
8. **Oracle exactness.** `OracleCreditAdapter` reproduces $\Gamma^\ast$ exactly.
9. **Side-effect freedom.** World, kernel and cache fingerprints are unchanged
   across a call.

Acceptance bar, as in S1: a trivially dumb method must be able to walk the whole
interface and pass. S2 proves the pipe, never the method.

---

## 8. A72 — set identification, and the one capability the locator is granted

*(This section appears ahead of sections 9 and 10 in the file because of how the
document grew, but it is numbered for logical order: 9 states the three native
rules and the degeneracy they expose, and section 8.4 records the claim those
rules settled. Read 9 and 10 first if you are following the argument.)*

### 8.0 The capability, frozen verbatim

> CausalSetLocator may use the frozen public SCM and its structural fault-support
> grammar to forward-simulate hypothetical latent worlds and retain those whose
> learner-visible factual evidence and fired-cause vector equal $X_{0.2}$. This is
> **factual-consistency inversion**, not an intervention query. It may not access
> the factual world's latent assignment, DenseSupport identities or weights,
> repair/rescue truth, $\Gamma^\ast$, or any evaluator counterfactual oracle.

A69 allowed only the environment/action grammar and a read-only $\pi_D^\ast$, and
forbade DenseSupport, world ids, DGP weights, $M$, repair truth, $\Gamma^\ast$ and
`outcome_after`. The inversion capability is therefore a **new grant**, and it is
recorded as an amendment rather than assumed to be public knowledge.

$$\boxed{\text{simulate a hypothetical factual world} \;\neq\; \text{intervene on the true world}}$$

The left side is model inversion; the right side is the evaluator counterfactual
query A65/A69 already forbid. $B_Q = 0$ is unchanged.

### 8.1 The compatible set, and the two envelopes

$$\mathcal C_{\text{SCM}}(X) = \bigl\{\tilde\ell \in \mathcal L_{\text{public}} :
\operatorname{Obs}_{\text{learner}}(\operatorname{Rollout}(\tilde\ell)) = I^{\text{factual}},\;
Z^{\text{fire}}(\tilde\ell) = Z^{\text{fire}}_{\text{truth}}\bigr\}$$

$\mathcal L_{\text{public}}$ is the candidate space **generated on the spot** from
the public SCM schema and the public finite fault grammar. It is **not**
DenseSupport.

$$\Gamma^-(X) = \bigcap_{\tilde\ell \in \mathcal C_{\text{SCM}}(X)} \Gamma_{\text{desc}}(\tilde\ell),
\qquad
\Gamma^+(X) = \bigcup_{\tilde\ell \in \mathcal C_{\text{SCM}}(X)} \Gamma_{\text{desc}}(\tilde\ell)$$

$$\boxed{\hat\Gamma_{\text{CSL}}(X) = \Gamma^+(X)}$$

with $\Gamma^-$ reported alongside as the *certain* responsibility diagnostic. A
mixed class therefore does not guess a site; it says honestly that two addresses
are each compatible with the observation. That is set identification, and it is
why the locator cannot be the oracle: `OracleCredit` receives the true
$\Gamma^\ast(\tilde\ell)$; `CausalSetLocator` can only reach the envelope that
$X$ itself supports.

### 8.2 The whitelist is an interface, not a promise

The locator does **not** import the full kernel API. It receives a restricted

```text
PublicSCMView
  public fault grammar
  forward factual rollout
  reference-policy view (read-only pi_D*)
  public descriptor -> credit ontology
```

and no `Intervention` / repair / rescue, no `DenseSupport`, no DGP probability, no
truth-world handle. A59 already showed why a documented promise is weaker than a
type: this way the whitelist is a fact about the object, not a convention.

**Allowed:** public kernel transition and event order; public fault-mechanism
schema; public admissible-parameter domains and structural feasibility rules; the
public $\Gamma$ ontology and descriptor→credit mapping; read-only $\pi_D^\ast$;
enumerating *hypothetical* $Z^{\text{pres}}, M$ and forward-simulating them,
including their own internal $u$, $a^{realized}$ and $Z^{\text{fire}}$.

**Not allowed:** reading the factual world's real latent values; comparing a
candidate against anything beyond the learner-visible fields inside $X_{0.2}$ and
the given $Z^{\text{fire}}$ — in particular not against the real world's hidden
$u$, plant input or proposal provenance; DenseSupport, block id, world id, DGP
weights, class frequencies, or any precomputed `(block, fire) -> Gamma+` table;
either repair truth; the real $\Gamma^\ast$; any repair/rescue oracle; any
`do(...)`.

### 8.3 The 893-class equivalence gate

$$\boxed{\hat\Gamma_{\text{CSL}}(X) = \Gamma^+_{\text{eval}}(X) \quad \forall X \in \{1,\dots,893\}}$$

The two sides must be **independently sourced**: $\Gamma^+_{\text{eval}}$ may be
enumerated from DenseSupport plus the indexed truth, because it is the evaluator
reference; $\hat\Gamma_{\text{CSL}}$ may only be re-derived from $X$ through
`PublicSCMView`. Only if 893/893 agree may we say the locator implements an
**exact SCM set inversion** rather than a support lookup.

**Mutation control:** deliberately merging the controller/plant mechanism boundary
must be killed by the X/E swap classes A71 found. Without that, the gate would
prove the locator runs, not that it inverts.

### 8.4 A71's claim, frozen

$$\boxed{\text{Cause identification does not imply site identification.}}$$

> Under the current SCM, even with $Z^{\text{fire}}$ given, $X^{\text{loc}}_{0.2} =
> (\text{rows}, Z^{\text{fire}})$ does not uniquely determine the indexed
> $\Gamma^\ast$ in every information class: 14 of 893 **locator** information
> classes admit multiple compatible responsibility truths, carrying **0.19% of DGP
> mass**, each with exactly two alternatives differing by one unit.

The full learner-visible observational partition $X^{\text{obs}}_{0.2} =
(\text{rows}, \text{feedback}, Z^{\text{fire}})$ is **4,513** classes, not 893 —
the feedback channel splits all 893. The 893 figure and the 14/893 fraction are
statements about $X^{\text{loc}}$, which is what A72/A73 hand the locator; $X_{0.2}$
must never again be used to denote both objects (A73, `12` §60).

This is an **identifiability negative result, not a method's poor performance** —
it holds against a perfect $Z^{\text{fire}}_{\text{truth}}$. That is markedly
stronger than a purpose-built fallible decoder.

**Claim condition, stated honestly:** this is credit localisation / set
identification **under a known SCM**. It is not a claim that a general learner
which does not know the world's mechanisms has learned to locate responsibility.

### 8.5 Order

$$\boxed{\text{A72 (this)} \rightarrow \texttt{PublicSCMView} \rightarrow \texttt{CausalSetLocator} \rightarrow 893/893 \rightarrow \text{corrected representation census}}$$


---

## 9. Order

$$\boxed{\text{A69 native alphabets + semantic expansion} \rightarrow \text{typed method contract} \rightarrow \text{S2} \rightarrow \text{implementation} \rightarrow \text{smoke/dev/confirmatory}}$$

That ladder applied before A70. A70 removed the smoke/dev/confirmatory rung from
V0.2R **primary** in favour of an exact full-support census, and A71 then falsified
A70's own premise that a causal rule is the ceiling, so the order in force is now
the one recorded in §8.5.

## 10. The three methods' native rules — and a degeneracy that must be decided first

> **HISTORICAL DECISION POINT — SUPERSEDED BY A70–A74.** The text of this section is
> kept as the record of a decision that was open when it was written. **Its central
> derivation is now false**, so it must not be read as current. What replaced it:
>
> $$Z^{\text{fire}} \;\not\Rightarrow\; \Gamma^\ast_{\text{indexed}}$$
>
> A71 falsified the identity $\Gamma^\ast = \pi_{\text{credit}} \circ Z^{\text{fire}}_{\text{truth}}$
> that the whole argument below rests on: five fire bits say *which kind* fired, not
> *which timestep or site*, so D/X carry addresses that the bits cannot supply.
> Consequently $R_{\text{causal}} \equiv \text{OracleCredit}$ is **false**, and the
> "causal rule is the ceiling" premise with it.
>
> The current object is instead
>
> $$X^{\text{loc}} = (\text{rows}, Z^{\text{fire}}_{\text{truth}}), \qquad
> \hat\Gamma_{\text{CSL}}(X^{\text{loc}}) = \Gamma^+(X^{\text{loc}})$$
>
> an exact **set** inversion from the public SCM through `PublicSCMView`, gated at
> **893/893** against an independently sourced evaluator reference, with
> $\Gamma^-$ as the diagnostic. The unidentifiability is real but thin:
> **14 of 893 locator classes**, carrying **0.1881% of DGP mass** (A71). And the
> census no longer crowns a winner at all — A70 replaced the sampled ladder with an
> exact full-support enumeration, and A74 voided that census's `Module` row after
> finding evaluator truth in its proposal construction.
>
> **The (a)/(b)/(c) fork below is therefore closed**, not open: (a) is what was done,
> (b) was rejected for re-importing V0.1R's attribution error, and (c) is moot because
> the premise it was meant to rescue — that a causal rule is the ceiling — is false.
> Nothing here is an outstanding decision.
>
> Subheading labels `9.1`–`9.3` are intentionally retained as historical anchors from
> the original section; they are **not** current section numbering. They are not
> renumbered because the original text is kept verbatim as the record, and because
> amendment A74 cites `17` §9.1 for the frozen $R_{\text{module}}$ rule.

Frozen so far: what each method may **see** ($X^{\text{obs}}_{0.2}$, identical, no query, a
read-only $\pi_D^\ast$ view) and what alphabet each may **emit**. Not yet frozen:
how each derives its proposal. That is algorithm, and it is frozen here — except
that writing it down exposes a structural problem.

### 9.1 The proposed minimal rules

| method | rule, from $X^{\text{obs}}_{0.2}$ alone |
|---|---|
| $R_{\text{module}}$ | emit `H` if any fired cause projects to a non-indexed unit; emit `L` if any projects to an indexed unit; both when both |
| $R_{\text{trajectory}}$ | always emit `{Episode}` — the coarsest baseline, deliberately uninformative |
| $R_{\text{causal}}$ | for each fired cause, emit $\pi_{\text{credit}}(\text{descriptor}_i)$ |

All three are deterministic functions of $(I^{\text{factual}}, Z^{\text{fire}})$ and
none reads $M$, a repair truth, or $\Gamma^\ast$.

### 9.2 The degeneracy

Because V0.2R **hands over $Z^{\text{fire}}_{\text{truth}}$**, A67's projection is
a deterministic function of the input:

$$\Gamma^\ast = \pi_{\text{credit}} \circ Z^{\text{fire}}_{\text{truth}}$$

So the rule in §9.1 for $R_{\text{causal}}$ computes $\Gamma^\ast$ **exactly**. That
makes $R_{\text{causal}}$ coincide with `OracleCreditAdapter`:

$$\boxed{R_{\text{causal}} \equiv \text{the ceiling, under } X^{\text{obs}}_{0.2}}$$

Three consequences, and they are not equivalent:

1. **The causal-versus-ceiling contrast is degenerate.** It cannot distinguish an
   ontology that is right from one that is merely self-consistent, because both
   sides are the same function.
2. **The informative contrasts are coarse-versus-fine only**: how much does
   `H/L` or `{Episode}` lose relative to the rebuild's factorisation. That is a
   real and answerable question, but it is a *granularity* result, not evidence
   that the causal factorisation is correct.
3. **"V0.2R compares credit representations" is therefore weaker than it reads.**
   What V0.2R can establish is that a coarse schema loses information; it cannot
   establish that `Strategy / ProcessCommit / Decision_t / ControllerSite /
   ExternalPlant / Unknown/NoWrite` is the *right* ontology, because it never has
   to compete with a wrong-but-fine alternative.

### 9.3 Three ways out, none taken here

* **(a) Accept it.** Report V0.2R as a granularity study, and say so in the write-up
  rather than implying an ontology competition. Cheapest and honest, but gives up
  the original claim in `07`.
* **(b) Remove $Z^{\text{fire}}$ from $X^{\text{obs}}_{0.2}$** so the method must infer it. This
  restores a genuine inference problem but re-imports V0.1R's attribution error
  into V0.2R, which is exactly what V0.2R's "isolate the error" design exists to
  prevent.
* **(c) Give $R_{\text{causal}}$ its own factorisation rule that is not
  $\pi_{\text{credit}}$** — e.g. one that can merge or split units and therefore can
  be wrong — so the causal schema has to compete rather than copy. This is the only
  route that makes the original claim testable, and it means defining a *second*,
  fallible causal rule whose relationship to $\pi_{\text{credit}}$ is itself the
  thing under test.

**This is a scientific-question decision, not an implementation detail**, and it
changes what V0.2R is allowed to claim. It is deliberately not resolved here. The
typed contract and S2 are unaffected: they are correct under all three routes.

