"""Two interpretations of one actual dataset, not independent evidence."""
from coverage_memory import PointFirstMemory
from hypothesis_memory import HypothesisMemory


class DualMemory:
    def __init__(self,record):
        self.primary=PointFirstMemory('point-first',record)
        self.secondary=HypothesisMemory('terminal-backoff',record)

    def snapshot(self):
        current=self.primary.snapshot()
        assert current==self.secondary.snapshot()
        return current

    def key(self,mode,terminal,evidence,action):
        return self.primary.key(mode,terminal,evidence,action)

    def observe(self,key,returns):
        self.primary.observe(key,returns)
        self.secondary.observe(key,returns)

    def recall(self,mode,terminal,evidence,actions,costs):
        primary,info=self.primary.recall(mode,terminal,evidence,actions,costs)
        secondary,other=self.secondary.recall(mode,terminal,evidence,actions,costs)
        return primary,dict(info,representation='dual-point-first',
                            comparison={'selected':secondary,'info':other})
