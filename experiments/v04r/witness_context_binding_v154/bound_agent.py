"""Usable v153 policy with the v154 context admission checks composed first."""
from strict_witness import StrictWitnessLoop
from trial_agent import TrialDerivedAgent

class StrictTrialDerivedAgent(StrictWitnessLoop,TrialDerivedAgent):
    """Same experiment policy, narrower source/witness context admission."""
    pass
