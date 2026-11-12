import unittest

from orchestration import (
    DiagnosticResult,
    FailureOnlyOrchestrator,
    ProtocolError,
    TaskObservation,
)


class FailureOnlyOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.learning = []
        self.diagnoses = []
        self.applied = []

        def ordinary(obs):
            self.learning.append((obs.terminal, hasattr(obs, "evaluator_metadata")))

        def diagnose(terminal, evidence, budget):
            self.diagnoses.append((terminal, evidence))
            if terminal == "TIMEOUT":
                return DiagnosticResult("keep", query_cost=1)
            return DiagnosticResult("apply", query_cost=1, write_cost=1, payload="bounded")

        self.runner = FailureOnlyOrchestrator(ordinary, diagnose, self.applied.append,
                                              max_queries=2, max_writes=1)

    def test_success_keeps_learning_and_never_diagnoses(self):
        record = self.runner.run(TaskObservation("SUCCESS", learner_evidence="trace",
                                                 evaluator_metadata={"truth": "hidden"}))
        self.assertEqual(record.route, "SUCCESS_NO_DIAGNOSTIC")
        self.assertEqual(self.learning, [("SUCCESS", False)])
        self.assertEqual(self.diagnoses, [])
        self.assertEqual(self.applied, [])

    def test_failures_can_apply_or_keep(self):
        self.assertEqual(self.runner.run(TaskObservation("COLLISION", "e1")).decision, "apply")
        self.assertEqual(self.runner.run(TaskObservation("TIMEOUT", "e2")).decision, "keep")
        self.assertEqual([x.payload for x in self.applied], ["bounded"])
        self.assertEqual([x[0] for x in self.diagnoses], ["COLLISION", "TIMEOUT"])
        self.assertEqual(self.learning, [("COLLISION", False), ("TIMEOUT", False)])

    def test_invalid_terminal_is_protocol_error_before_learning(self):
        for terminal in (None, "RUNNING", "UNKNOWN"):
            with self.assertRaises(ProtocolError):
                self.runner.run(TaskObservation(terminal))
        self.assertEqual(self.learning, [])
        self.assertEqual(self.diagnoses, [])

    def test_truth_metadata_does_not_route_success(self):
        record = self.runner.run(TaskObservation("SUCCESS", "trace", {"cause": "COLLISION"}))
        self.assertEqual(record.route, "SUCCESS_NO_DIAGNOSTIC")
        self.assertEqual(self.diagnoses, [])

    def test_budget_is_explicit(self):
        runner = FailureOnlyOrchestrator(lambda _: None,
                                          lambda *_: DiagnosticResult("apply", query_cost=2, write_cost=0),
                                          lambda _: None, max_queries=1, max_writes=0)
        with self.assertRaises(ProtocolError):
            runner.run(TaskObservation("TRAP"))


if __name__ == "__main__":
    unittest.main()

