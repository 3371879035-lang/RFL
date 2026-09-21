r"""Mutation self-check for B2-1: the view, its builder, and their four gate layers.

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate did not
look}}$$

A75 §62.10 lists four layers — type boundary, AST/import allowlist, constructor-flow, mutation
power — and the fourth exists because the first three can all be present and **inert**. So each
layer is re-run against a deliberately reverted source tree, one mutation at a time, and the gate
that guards it must go **red**.

| # | hole | mutation |
|---|---|---|
| 1 | evidence from evaluator truth feeds the view | the origin comparison disabled |
| 2 | a value-equal *string* origin passes for the member | the nominal origin type check disabled |
| 3 | a bare value (a prefabricated scalar) is admitted as a field | the `FutureField` type check disabled |
| 4 | the field surface is a superset, so an extra feature rides along | `!=` -> `not <=` |
| 5 | the builder can be told which arm it is in | `build` gains a parameter |
| 6 | update metadata enters "what happened next" | the view gains a ledger member |
| 7 | the module reaches a non-allowlisted (truth-bearing) import | an import is added |

Mutation 3 is the fabricated-feature route and mutation 2 is the one the gates found while this
arrow was being written: formatting `origin.value` on a string raised `AttributeError` out of the
guard, where the contract promises a `PROTOCOL_ERROR`.

Usage::

    python scripts/b2_view_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402
SRC = ROOT / "src" / "rfl_rebuild"
TESTS = "tests/rebuild/test_b2_view.py"
VIEW = SRC / "b2" / "view.py"
PRODUCER = SRC / "b2" / "producer.py"
ENVIRONMENT = SRC / "b2" / "environment.py"
UTILITY = SRC / "b2" / "utility.py"
COLLATERAL = SRC / "b2" / "collateral.py"
RETENTION = SRC / "b2" / "retention.py"
RUNNER = SRC / "b2" / "runner.py"
B2_CAND_TESTS = "tests/rebuild/test_b2_candidates.py"
B2_RUN_TESTS = "tests/rebuild/test_b2_runner.py"
B2_ENV_TESTS = "tests/rebuild/test_b2_environment.py"

#: (id, hole, path, old, new, pytest node id[, expected failure text])
MUTATIONS: tuple = (
    (
        "origin_check_removed",
        "evidence tagged as evaluator truth is admitted, so the view can be built from forbidden "
        "truth one step upstream of the metric",
        VIEW,
        "    if rollout.origin is not EvidenceOrigin.LEARNER_FUTURE_ROLLOUT:\n",
        "    if False:                            # MUTATED: origin check disabled\n",
        f"{TESTS}::test_5_only_the_learners_own_future_rollout_may_feed_the_view",
        "DID NOT RAISE",
    ),
    (
        "origin_type_check_removed",
        "a string that spells the right origin is accepted for the member itself -- and the guard "
        "then crashes formatting `origin.value`, so the promised PROTOCOL_ERROR is an "
        "AttributeError: the error path failing first",
        VIEW,
        "    if type(rollout.origin) is not EvidenceOrigin:\n",
        "    if False:                            # MUTATED: nominal origin type unchecked\n",
        f"{TESTS}::test_5_only_the_learners_own_future_rollout_may_feed_the_view",
        "has no attribute 'value'",
    ),
    (
        "rollout_seal_check_removed",
        "any object can be presented as a rollout that reports its own provenance -- the hole "
        "B2-2a closes by minting rather than by labelling",
        VIEW,
        "        if not is_sealed(self._seal):\n",
        "        if False:                        # MUTATED: self-reported provenance accepted\n",
        f"{TESTS}::test_3_the_rollout_is_sealed_and_the_view_is_one_future",
        "DID NOT RAISE",
    ),
    (
        "raw_value_accepted",
        "a bare value is admitted as a view field, which is how an already-computed truth-derived "
        "scalar enters while the metric imports nothing forbidden",
        VIEW,
        "            if type(field) is not FutureField:\n",
        "            if False:                    # MUTATED: bare values admitted\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "has no attribute 'name'",
    ),
    (
        "payload_not_rederived",
        "the payload is trusted instead of re-derived from its own rollout, so a clean shell can "
        "carry a forged, truth-derived value -- B2-1's most dangerous remaining route",
        VIEW,
        "            if tuple(field.value) != tuple(getattr(rollout, name)):\n",
        "            if False:                    # MUTATED: payload trusted\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "t_index_not_bound",
        "the ordinary time indices are supplied separately from the rollout, so they can be "
        "truth-derived while every field is clean",
        VIEW,
        "        if tuple(self.t_index) != tuple(rollout.t_index):\n",
        "        if False:                        # MUTATED: t_index unbound\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "mixed_rollouts_accepted",
        "fields from several different futures are assembled into one view, so 'what happened "
        "next' is no longer one horizon",
        VIEW,
        "        if len(rollouts) != 1:\n",
        "        if False:                        # MUTATED: several futures accepted\n",
        f"{TESTS}::test_3_the_rollout_is_sealed_and_the_view_is_one_future",
        "DID NOT RAISE",
    ),
    (
        "closed_fields_widened",
        "the field surface becomes a superset, so a fabricated feature rides along in the "
        "envelope the metric receives",
        VIEW,
        "        if keys != expected:\n",
        "        if not expected <= keys:             # MUTATED: superset accepted\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "builder_takes_any_callable",
        "the builder goes back to accepting an arbitrary callable, which can close over forbidden "
        "truth while the audited module's AST scan sees nothing -- the B2-1 hole itself",
        VIEW,
        "        if type(producer) is not FutureRolloutProducer:\n",
        "        if not callable(producer):       # MUTATED: an injected callable\n",
        f"{TESTS}::test_4_the_builder_consumes_the_audited_producer_not_a_callable",
        "DID NOT RAISE",
    ),
    (
        "environment_duck_typed",
        "any object with `future_records` is accepted as the environment, which is how an "
        "evaluator-supplied truth table arrives wearing the interface's method name",
        PRODUCER,
        "        if not isinstance(environment, LearnerEnvironment):\n",
        "        if False:                        # MUTATED: duck-typed environment\n",
        f"{TESTS}::test_4_the_builder_consumes_the_audited_producer_not_a_callable",
        "DID NOT RAISE",
    ),
    (
        "arm_parameter_added",
        "the builder can be told which arm it is in. A builder that CAN be told is one that may "
        "one day branch on it, which is why the gate reads the signature rather than the intent",
        VIEW,
        "    def build(self, state) -> FutureConsequenceView:\n",
        "    def build(self, state, arm=None) -> FutureConsequenceView:   # MUTATED\n",
        f"{TESTS}::test_8_arm_blind_by_interface_and_pre_update_by_absence",
        'assert params == ("state",)',
    ),
    (
        "update_metadata_added",
        "the view gains a ledger member, merging 'what was written' into 'what happened next'",
        VIEW,
        "    fields: Mapping\n    t_index: tuple\n",
        "    fields: Mapping\n    t_index: tuple\n    ledger: object = None       # MUTATED\n",
        f"{TESTS}::test_8_arm_blind_by_interface_and_pre_update_by_absence",
        "Extra items in the left set",
    ),
    (
        "import_allowlist_widened",
        "the module reaches a non-allowlisted (truth-bearing) import, which is the AST layer's "
        "job to refuse",
        VIEW,
        "from rfl_rebuild.learner.store import LearnerPersistentState\n",
        "from rfl_rebuild.learner.store import LearnerPersistentState\n"
        "from rfl_rebuild.method import credit                      # MUTATED\n",
        f"{TESTS}::test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous",
        "not on the allowlist",
    ),
    (
        "producer_reads_forbidden_truth",
        "the producer itself derives its records from forbidden truth and labels them as the "
        "learner's -- the mislabelled rollout, which no type can catch and which the audit of the "
        "PRODUCER module is therefore for",
        PRODUCER,
        "        records = self._environment.future_records(state)\n",
        "        records = self._environment.future_records(state)\n"
        "        _leak = Gamma_P_star                                   # MUTATED\n",
        f"{TESTS}::test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous",
        "forbidden dependency set",
    ),
    (
        "fixture_module_reachable",
        "a production module may import the test-only fixture mint, so production code can be "
        "built from the fixtures rather than the other way round",
        VIEW,
        "                if name.startswith(\"rfl_rebuild.b2.testing\"):\n",
        "                if False:                # MUTATED: fixture mint reachable\n",
        f"{TESTS}::test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous",
        "test-only fixture module",
    ),
    (
        "capability_imported_outside_owner",
        "another production module reaches for the mint itself. An allowlisted import is still an "
        "escalation when the name it brings is the ability to mint evidence: with the capability in "
        "hand, a truth-derived payload can be minted with a VALID seal, and no downstream layer can "
        "tell -- which is why the holder is one module and the audit enforces it",
        VIEW,
        "from rfl_rebuild.learner.store import LearnerPersistentState\n",
        "from rfl_rebuild.learner.store import LearnerPersistentState\n"
        "from rfl_rebuild.b2.producer import _mint_rollout          # MUTATED\n",
        f"{TESTS}::test_10_the_mint_capability_has_exactly_one_holder_in_the_production_graph",
        "mint capability",
    ),
    (
        "environment_ignores_the_state",
        "the real environment rolls the future out from a FRESH state instead of the one it was "
        "handed, so the future is no longer a function of W + Delta W -- the defect B2 exists to "
        "measure, and the one a plausible-looking rollout would hide",
        ENVIRONMENT,
        "    snapshot = state.snapshot()\n",
        "    snapshot = LearnerPersistentState().snapshot()   # MUTATED: ignores the passed state\n",
        f"{B2_ENV_TESTS}::test_2_each_persistent_channel_moves_the_future",
        "C_P^L channel is not read",
    ),
    (
        "environment_drops_a_channel",
        "the process channel is not wired into the rollout, so C_P^L is bypassed by the kernel's "
        "identity default: a reference shortcut in the one place where a shortcut is the whole "
        "question",
        ENVIRONMENT,
        "        controller=controller, learner_process_commit=snapshot.process_commit_provider(),\n",
        "        controller=controller, learner_process_commit=None,   # MUTATED: C_P^L dropped\n",
        f"{B2_ENV_TESTS}::test_2_each_persistent_channel_moves_the_future",
        "C_P^L channel is not read",
    ),
    (
        "environment_not_audited",
        "the production environment leaves the audited module list, so the module that decides "
        "where the future evidence comes from is the one module nobody checks",
        ENVIRONMENT,
        '    "rfl_rebuild/b2/environment.py",\n',
        "",
        f"{B2_ENV_TESTS}::test_4_the_environment_is_in_the_audited_production_chain",
        "environment.py",
    ),
    (
        "recovery_window_two",
        "the maintained-recovery window shrinks to K=2, so two checkpoints at the threshold are "
        "reported as a recovery the study never defined",
        UTILITY,
        "K_RECOVERY = 3\n",
        "K_RECOVERY = 2        # MUTATED\n",
        f"{B2_ENV_TESTS}::test_5_recovery_needs_k_consecutive_checkpoints",
        "assert K_RECOVERY == 3",
    ),
    (
        "rmst_returns_the_position",
        "tau is returned as the ARRAY POSITION of the checkpoint rather than its real episode "
        "index, which is invisible on a uniform fixture and wrong on every real grid",
        UTILITY,
        "            return episodes[i]\n",
        "            return i                              # MUTATED\n",
        f"{B2_ENV_TESTS}::test_8_both_estimators_integrate_over_real_episode_indices",
        "== 5",
    ),
    (
        "environment_drops_decision_patch_channel",
        "P_D^L is bypassed: the rollout stays on the Q read path, so a decision patch the learner "
        "holds is never applied. The future is still plausible, which is why only a gate that "
        "writes the channel can see it",
        ENVIRONMENT,
        "    return (snapshot.decision_provider(snapshot.q_decision_provider(q_reference)),\n"
        "            snapshot.controller_mapping())\n",
        "    return (snapshot.q_decision_provider(q_reference),   # MUTATED: decision channel dropped\n"
        "            snapshot.controller_mapping())\n",
        f"{B2_ENV_TESTS}::test_2b_the_decision_patch_channel_moves_the_future",
        "P_D^L is bypassed",
    ),
    (
        "deficit_not_normalised",
        "the 1/T_max of 05 8.3 is dropped, so DeficitAUC becomes an area that grows with the "
        "horizon instead of a mean deficit over it -- and the frozen endpoint is a different number",
        UTILITY,
        "    return total / t_max\n",
        "    return total                              # MUTATED: unnormalised\n",
        f"{B2_ENV_TESTS}::test_8_both_estimators_integrate_over_real_episode_indices",
        "1.06 / 16",
    ),
    (
        "deficit_uses_left_hold",
        "the quadrature reverts to a left rectangle, which assumes each measurement persists across "
        "its whole interval -- an assumption the frozen continuous integral does not make",
        UTILITY,
        "        total += 0.5 * (deficits[i] + deficits[i + 1]) * (episodes[i + 1] - episodes[i])\n",
        "        total += deficits[i] * (episodes[i + 1] - episodes[i])   # MUTATED: left-hold\n",
        f"{B2_ENV_TESTS}::test_8_both_estimators_integrate_over_real_episode_indices",
        "1.06 / 16",
    ),
    (
        "curve_need_not_span_the_horizon",
        "a curve that stops short of T_max is accepted, so RMST and DeficitAUC describe different "
        "intervals and the unobserved tail is silently given a rule",
        UTILITY,
        '    if episodes[-1] != t_max:\n',
        '    if False:                                 # MUTATED: short curves accepted\n',
        f"{B2_ENV_TESTS}::test_9_the_grid_contract_is_enforced",
        "DID NOT RAISE",
    ),
    (
        "unaffected_constructor_takes_an_arm",
        "the unaffected-set constructor can be told which arm it is in: a constructor that CAN be "
        "told is one that may one day branch on it, and the set stops being arm-blind while still "
        "producing a number",
        COLLATERAL,
        "def _unaffected_visited_complement(domain, visited) -> UnaffectedSet:\n",
        "def _unaffected_visited_complement(domain, visited, arm=None) -> UnaffectedSet:  # MUTATED\n",
        f"{B2_CAND_TESTS}::test_1_the_constructors_are_blind_locally_and_the_rest_belongs_to_b2_4",
        "assert not (set(params) & set(forbidden))",
    ),
    (
        "collateral_ignores_the_set",
        "the metric is computed over the values it was handed rather than over the unaffected set, "
        "so the caller's choice of contexts decides the number -- including a choice that leaks the "
        "visited region the set exists to exclude",
        COLLATERAL,
        "        got = set(map(repr, values))\n"
        "        if got != expected:\n",
        "        got = set(map(repr, values))\n"
        "        if not expected <= got:              # MUTATED: superset accepted\n",
        f"{B2_CAND_TESTS}::test_4_the_metric_is_defined_on_exactly_the_set_it_is_given",
        "DID NOT RAISE",
    ),
    (
        "retention_diagnostic_promoted",
        "the tau-conditioned RetentionFraction is registered as a confirmatory candidate, so a form "
        "undefined for a never-recovered seed becomes eligible for the primary endpoint",
        RETENTION,
        '    "LateWindowRetention": LateWindowRetention.value,\n}',
        '    "LateWindowRetention": LateWindowRetention.value,\n'
        '    "RetentionFraction": retention_fraction,          # MUTATED\n}',
        f"{B2_CAND_TESTS}::test_8_the_conditional_form_is_a_diagnostic_by_type_and_by_registry",
        'assert "RetentionFraction" not in CANDIDATE_FORMS',
    ),
    (
        "retention_needs_recovery",
        "RetentionAtH is made to depend on recovery, so it is undefined for exactly the seeds A79 "
        "67.5 requires the confirmatory primary to cover",
        RETENTION,
        "        values, episodes = _require_grid(values, episodes)\n        if isinstance(H, bool)",
        "        values, episodes = _require_grid(values, episodes)\n"
        '        if not [v for v in values if v >= 0.95]:\n'
        '            raise ProtocolError("never recovered")            # MUTATED\n'
        "        if isinstance(H, bool)",
        f"{B2_CAND_TESTS}::test_7_both_eligible_forms_are_defined_for_every_seed_including_never_recovered",
        "never recovered",
    ),
    (
        "utility_reads_forbidden_truth",
        "utility.py -- a real per-scene metric -- reads forbidden truth. It was outside the audited "
        "production chain, so the whole B2 measurement audit could not see it: the number would be "
        "well-formed and the dependency would be invisible",
        UTILITY,
        "def deficit_auc(values, episodes, *, pre_level: float, t_max: int) -> float:\n",
        "def deficit_auc(values, episodes, *, pre_level: float, t_max: int) -> float:\n"
        "    _leak = Gamma_P_star                                  # MUTATED\n",
        f"{B2_CAND_TESTS}::test_10_the_machinery_is_in_the_audited_production_chain",
        "forbidden dependency set",
    ),
    (
        "retention_form_chosen_by_default",
        "select_form acquires a default, so the confirmatory primary is chosen by whoever typed the "
        "signature rather than by the development protocol",
        RETENTION,
        "def select_form(name: str) -> Callable:\n",
        'def select_form(name: str = "RetentionAtH") -> Callable:      # MUTATED\n',
        f"{B2_CAND_TESTS}::test_9_no_form_or_window_is_selected_or_defaulted",
        "inspect.signature(select_form).parameters",
    ),
    (
        "collateral_construction_chosen_by_default",
        "select_construction acquires a default, so the unaffected-set construction -- the choice "
        "A79 67.4 leaves to measurement properties -- is made by inaction",
        COLLATERAL,
        "def select_construction(name: str) -> Callable:\n",
        'def select_construction(name: str = "visited_complement") -> Callable:   # MUTATED\n',
        f"{B2_CAND_TESTS}::test_2_no_construction_is_selected_by_default",
        "inspect.signature(select_construction).parameters",
    ),
    (
        "runner_defaults_the_form",
        "the runner substitutes a default Retention form, so the confirmatory primary is chosen by the instrument rather than by the development protocol",
        RUNNER,
        "        form = select_form(retention_form)\n",
        "        form = select_form(retention_form or \"RetentionAtH\")      # MUTATED\n",
        f"{B2_RUN_TESTS}::test_7_the_candidate_names_and_horizons_are_required_and_never_defaulted",
        "DID NOT RAISE",
    ),
    (
        "runner_defaults_the_construction",
        "the runner substitutes a default unaffected-set construction, so a candidate A79 67.4 leaves to measurement properties is chosen by inaction",
        RUNNER,
        "        if refinement not in REFINEMENTS:\n            raise ProtocolError(\n                f\"{refinement!r} is not one of the six frozen refinements {REFINEMENTS!r}; the runner \"\n                \"has no default and does not choose one\")\n",
        "        refinement = refinement or \"eligible_all\"   # MUTATED: defaults the refinement\n",
        f"{B2_RUN_TESTS}::test_7_the_candidate_names_and_horizons_are_required_and_never_defaulted",
        "DID NOT RAISE",
    ),
    (
        "arm_accepts_arbitrary_callable",
        "the arm's law check is disabled, so an arbitrary callable -- which can close over forbidden truth, a future or the other arm -- arrives as an update. This is B2-1's hole on the update side",
        RUNNER,
        "        if not _is_frozen_law(self.law, LAW_REGISTRIES[self.architecture]):\n",
        "        if False:                            # MUTATED: any law accepted\n",
        f"{B2_RUN_TESTS}::test_8_the_arms_are_nominal_and_dispatch_to_the_frozen_entry_points",
        "DID NOT RAISE",
    ),
    (
        "arm_uses_wrong_architecture_registry",
        "the registries are merged, so a P law runs in an X arm and the reverse. Independent of the callable hole: a foreign law IS a frozen law, just not this architecture's",
        RUNNER,
        "LAW_REGISTRIES = {\"D_Q\": DQ_LAWS, \"P\": P_LAWS, \"X\": X_LAWS}\n",
        "LAW_REGISTRIES = {\"D_Q\": DQ_LAWS, \"P\": X_LAWS, \"X\": P_LAWS}   # MUTATED: P and X swapped\n",
        f"{B2_RUN_TESTS}::test_9_a_law_from_another_architecture_is_refused",
        "DID NOT RAISE",
    ),
    (
        "runner_accepts_forbidden_exogenous_field",
        "the exogenous setup's field surface widens, so routing truth rides along in the object the arms share -- the information boundary B2-4 exists to hold",
        RUNNER,
        "    checkpoints: tuple\n",
        "    checkpoints: tuple\n    world_id: object = None                        # MUTATED\n",
        f"{B2_RUN_TESTS}::test_5_the_paired_futures_share_one_exogenous_setup",
        # Measured: the widened surface is refused by ExogenousSetup.__post_init__ itself,
        # so the closed-surface check is load-bearing production code and the gate never
        # reaches its own assertion. The declaration records the mechanism that fires.
        "but its surface is frozen as",
    ),
    (
        "runner_adds_composite_score",
        "the scene record gains a composite field, so the three dimensions can be collapsed into one primary -- the composite A79 67.1 refuses, re-introduced at the instrument",
        RUNNER,
        "    observations: tuple\n",
        "    observations: tuple\n    score: float = 0.0                            # MUTATED\n",
        f"{B2_RUN_TESTS}::test_10_the_record_keeps_three_dimensions_and_no_composite",
        "record.__dataclass_fields__",
    ),
    (
        "unaffected_constructed_after_treatment",
        "U_unaffected is built AFTER the arms have run, so the set the metric uses has already seen an update -- the order the whole pairing argument rests on",
        RUNNER,
        "        # (1) the shared design material, built from the RAW pre-update state BEFORE any arm exists\n        unaffected = self.pre_update_source(state, credited_site)\n        self._recorder(\"unaffected\", unaffected, id(unaffected))\n\n        # (1b) ONE pre measurement from the RAW pre state, taken once and shared: A85 §73.2.2 fixes\n        #      that the two arms' pre values are the same measurement rather than two that happen to\n        #      agree, so the map is measured here and handed to both collateral computations\n        pre_map = measure_scene_map(state, unaffected.units, q_reference=self._q_reference)\n        self._recorder(\"pre_map\", id(pre_map), len(pre_map))\n\n        # (2) independent clones from ONE pre-update state\n        clones = [state.clone() for _ in arms]\n        pre_fingerprints = {arm.name: fingerprint(clone) for arm, clone in zip(arms, clones)}\n        if len(set(pre_fingerprints.values())) != 1:\n            raise ProtocolError(\n                \"the two arms did not start from one pre-update state: fingerprints \"\n                f\"{pre_fingerprints!r}; a serial chain from one arm into the other is not a pair\")\n\n        # (3) the updates, each on its own clone, before any future exists\n        for arm, clone in zip(arms, clones):\n            self._apply(arm, clone, evidence, self._q_reference)\n            self._recorder(\"update_applied\", arm.name, id(clone))\n",
        "        # MUTATED: the arms run first ...\n        clones = [state.clone() for _ in arms]\n        pre_fingerprints = {arm.name: fingerprint(clone) for arm, clone in zip(arms, clones)}\n        if len(set(pre_fingerprints.values())) != 1:\n            raise ProtocolError(\n                \"the two arms did not start from one pre-update state: fingerprints \"\n                f\"{pre_fingerprints!r}; a serial chain from one arm into the other is not a pair\")\n        for arm, clone in zip(arms, clones):\n            self._apply(arm, clone, evidence, self._q_reference)\n            self._recorder(\"update_applied\", arm.name, id(clone))\n        # ... and only then is the unaffected set built\n        unaffected = self.pre_update_source(state, credited_site)\n        self._recorder(\"unaffected\", unaffected, id(unaffected))\n        pre_map = measure_scene_map(state, unaffected.units, q_reference=self._q_reference)\n        self._recorder(\"pre_map\", id(pre_map), len(pre_map))\n",
        f"{B2_RUN_TESTS}::test_1_the_unaffected_set_is_built_before_the_first_arm_runs",
        "assert names[0] == \"unaffected\"",
    ),
    (
        "per_arm_construction",
        "the metric is handed a SECOND, value-equal construction while the recorder saw the first, so the arms do not share one object -- equality where identity is required",
        RUNNER,
        "            collateral[arm.name] = behavioral_collateral_scenes(\n                unaffected, values_pre=pre_map, values_post=post_maps[arm.name])",
        "            _u_treat = self.pre_update_source(state, credited_site)   # MUTATED: a second construction\n            collateral[arm.name] = behavioral_collateral_scenes(\n                _u_treat, values_pre=pre_map, values_post=post_maps[arm.name])",
        f"{B2_RUN_TESTS}::test_3_the_arms_are_handed_one_object_not_two_equal_ones",
        "the two arms' metrics saw different objects",
    ),
    (
        "per_arm_pre_measurement",
        "the pre map is measured again inside each arm's collateral instead of being measured once and shared, so the two collaterals are two measurements that happen to agree rather than A85 73.2.2's single pre measurement",
        RUNNER,
        "            collateral[arm.name] = behavioral_collateral_scenes(\n                unaffected, values_pre=pre_map, values_post=post_maps[arm.name])",
        "            collateral[arm.name] = behavioral_collateral_scenes(\n                unaffected, values_pre=measure_scene_map(state, unaffected.units,\n                                                      q_reference=self._q_reference),\n                values_post=post_maps[arm.name])   # MUTATED: a second pre measurement",
        f"{B2_RUN_TESTS}::test_11b_the_two_arms_share_one_pre_measurement",
        "one pre map and one per arm",
    ),
    (
        "serial_arm_chain",
        "the second arm is cloned from the first arm's POST-update state instead of from the shared pre-update state, so the pair is a serial chain and the contrast is contaminated",
        RUNNER,
        "        clones = [state.clone() for _ in arms]\n        pre_fingerprints = {arm.name: fingerprint(clone) for arm, clone in zip(arms, clones)}\n        if len(set(pre_fingerprints.values())) != 1:\n            raise ProtocolError(\n                \"the two arms did not start from one pre-update state: fingerprints \"\n                f\"{pre_fingerprints!r}; a serial chain from one arm into the other is not a pair\")\n\n        # (3) the updates, each on its own clone, before any future exists\n        for arm, clone in zip(arms, clones):\n            self._apply(arm, clone, evidence, self._q_reference)\n            self._recorder(\"update_applied\", arm.name, id(clone))\n",
        "        clones = [state.clone()]\n        self._apply(arms[0], clones[0], evidence, self._q_reference)   # MUTATED: arm 1 runs first ...\n        self._recorder(\"update_applied\", arms[0].name, id(clones[0]))\n        clones.append(clones[0].clone())                               # ... arm 2 clones its post-state\n        self._apply(arms[1], clones[1], evidence, self._q_reference)\n        self._recorder(\"update_applied\", arms[1].name, id(clones[1]))\n        pre_fingerprints = {arm.name: fingerprint(clone) for arm, clone in zip(arms, clones)}\n        if len(set(pre_fingerprints.values())) != 1:\n            raise ProtocolError(\n                \"the two arms did not start from one pre-update state: fingerprints \"\n                f\"{pre_fingerprints!r}; a serial chain from one arm into the other is not a pair\")\n",
        f"{B2_RUN_TESTS}::test_4_the_arms_fork_from_one_pre_update_state",
        # Measured: the gate now fails on its OWN parent check rather than on the runner's
        # fingerprint guard, because the mutation changes the derivation while the resulting
        # contents can still converge.
        "a clone was taken from a state that had already been updated",
    ),
    (
        "paired_arms_use_different_future_noise",
        "one arm is given a fresh, value-equal exogenous setup, so the arms no longer share noise and the difference between them is no longer attributable to Delta W",
        RUNNER,
        "            environment = self._environment_factory(exogenous)\n            self._recorder(\"exogenous\", arm.name, id(exogenous))",
        "            _setup = exogenous if arm is arms[0] else ExogenousSetup(       # MUTATED\n                kappa=exogenous.kappa, phi=exogenous.phi, tape=exogenous.tape,\n                base_option=exogenous.base_option, q_reference=exogenous.q_reference,\n                checkpoints=exogenous.checkpoints)\n            environment = self._environment_factory(_setup)\n            self._recorder(\"exogenous\", arm.name, id(_setup))",
        f"{B2_RUN_TESTS}::test_5_the_paired_futures_share_one_exogenous_setup",
        "len(set(setup_ids)) == 1",
    ),
    (
        "future_before_update",
        "a future event is emitted before any update, i.e. the outcome exists before the write whose consequence it is supposed to be",
        RUNNER,
        "        # (3) the updates, each on its own clone, before any future exists\n        for arm, clone in zip(arms, clones):",
        "        # (3) MUTATED: a future is produced before the updates\n        self._recorder(\"future\", arms[0].name, None)\n        for arm, clone in zip(arms, clones):",
        f"{B2_RUN_TESTS}::test_6_no_future_exists_before_the_updates_are_applied",
        "assert first_future > last_update",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "b2_view_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(
        MUTATIONS, ROOT, (VIEW, PRODUCER, ENVIRONMENT, UTILITY, COLLATERAL, RETENTION,
                          RUNNER))
    return harness.summarise("B2-1 view/builder gate mutation self-check", MUTATIONS, results,
                             restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
