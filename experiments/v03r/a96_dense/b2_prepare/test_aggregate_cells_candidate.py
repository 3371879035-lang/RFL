"""Deterministic scalar array fixtures, no environment or training key draws."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from aggregate_cells_candidate import aggregate_paired_cells, validate_cells


class SeedAggregationTests(unittest.TestCase):
    def setUp(self):
        self.ids=[11,12]  # constructed row identifiers, never used as train/env keys
        self.cells=[{"cell_id":c,"weight_numerator":1,"weight_denominator":3} for c in ("a","b","c")]
        self.records=[{"seed":s,"cell_id":c,"regime":"P","statistic":"RMST",
                       "reference":float(v),"treatment":float(v-1)}
                      for s in self.ids for c,v in zip(("a","b","c"),(3,6,9))]

    def run_aggregate(self, records=None,cells=None,ids=None,regime="P",statistic="RMST"):
        return aggregate_paired_cells(self.records if records is None else records,
                                      self.ids if ids is None else ids,
                                      self.cells if cells is None else cells,
                                      regime=regime,statistic=statistic)

    def test_six_cells_become_two_paired_independent_seed_rows(self):
        r=self.run_aggregate()
        self.assertEqual(r,[{"seed":11,"reference":6.,"treatment":5.},
                            {"seed":12,"reference":6.,"treatment":5.}])
        self.assertEqual(len(r),len(self.ids))

    def test_uniform_weights_keep_original_mean_order(self):
        x=copy.deepcopy(self.records)
        for i,r in enumerate(x): r["reference"]=(1e16,1.,-1e16)[i%3]
        self.assertEqual([r["reference"] for r in self.run_aggregate(x)],[0.,0.])

    def test_registered_rational_weights_shared_across_arms(self):
        c=copy.deepcopy(self.cells)
        for x,d in zip(c,(2,4,4)): x["weight_denominator"]=d
        r=self.run_aggregate(cells=c)
        self.assertEqual(r[0]["reference"],5.25)
        self.assertEqual(r[0]["treatment"],4.25)

    def test_partial_cells_or_prefix_seed_rectangle_refused(self):
        for x in (self.records[:-1],self.records[:3],self.records+[self.records[-1]]):
            with self.assertRaises(ValueError): self.run_aggregate(x)

    def test_duplicate_seed_cell_not_accepted_by_row_count(self):
        x=copy.deepcopy(self.records);x[-1]=copy.deepcopy(x[0])
        with self.assertRaises(ValueError): self.run_aggregate(x)

    def test_future_completion_order_not_used_for_reduction(self):
        for x in (self.records[3:]+self.records[:3],list(reversed(self.records))):
            with self.assertRaises(ValueError): self.run_aggregate(x)

    def test_nonfinite_bool_or_nested_scalar_refused(self):
        for v in (float("nan"),float("inf"),True,[3]):
            x=copy.deepcopy(self.records);x[0]["reference"]=v
            with self.assertRaises(ValueError): self.run_aggregate(x)

    def test_boolean_seed_not_an_integer_id(self):
        x=copy.deepcopy(self.records);x[0]["seed"]=True
        with self.assertRaises(ValueError): self.run_aggregate(x)

    def test_extra_scalar_fields_not_hidden_provenance(self):
        x=copy.deepcopy(self.records);x[0]["posthoc_keep"]=True
        with self.assertRaises(ValueError): self.run_aggregate(x)

    def test_T_P_or_endpoint_mixture_refused(self):
        for field,value in (("regime","T"),("statistic","DeficitAUC")):
            x=copy.deepcopy(self.records);x[0][field]=value
            with self.assertRaises(ValueError): self.run_aggregate(x)
        with self.assertRaises(ValueError): self.run_aggregate(regime="T+P")

    def test_duplicate_or_missing_declared_seed_population_refused(self):
        for ids in ([11,11],[11],[]):
            with self.assertRaises(ValueError): self.run_aggregate(ids=ids)

    def test_zero_negative_bool_or_noninteger_weights_refused(self):
        for value in (0,-1,True,.5):
            c=copy.deepcopy(self.cells);c[0]["weight_numerator"]=value
            with self.assertRaises(ValueError): self.run_aggregate(cells=c)

    def test_weights_must_sum_exactly_not_with_float_tolerance(self):
        c=copy.deepcopy(self.cells);c[0]["weight_denominator"]=4
        with self.assertRaises(ValueError): self.run_aggregate(cells=c)

    def test_positive_fraction_cannot_underflow_into_dropped_cell(self):
        huge=10**1000
        cells=[{"cell_id":"a","weight_numerator":1,"weight_denominator":huge},
               {"cell_id":"b","weight_numerator":huge-1,"weight_denominator":huge}]
        with self.assertRaises(ValueError):validate_cells(cells)

    def test_cell_registry_unique_closed_and_named(self):
        for change in (lambda c:c[0].update(cell_id=""),lambda c:c[0].update(cell_id="b"),
                       lambda c:c[0].update(arm_specific=True)):
            c=copy.deepcopy(self.cells);change(c)
            with self.assertRaises(ValueError): validate_cells(c)

    def test_no_caller_owned_fixture_mutation(self):
        before=copy.deepcopy((self.records,self.cells,self.ids))
        self.run_aggregate()
        self.assertEqual((self.records,self.cells,self.ids),before)

    def test_seed_aggregate_overflow_refused(self):
        x=copy.deepcopy(self.records)
        for r in x:r["reference"]=1e308
        with self.assertRaises(ValueError):self.run_aggregate(x)


if __name__=="__main__":unittest.main(verbosity=2)
