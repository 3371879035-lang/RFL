"""Numerical experience is acquired by this mode, never borrowed from DQ."""
from frozen_memory import span_key


class TrialMemory:
    def __init__(self):
        self.samples={}

    def key(self,mode,terminal,evidence,action):
        return span_key(mode,terminal,evidence,action)

    def snapshot(self):
        return tuple((k,len(v),sum(v)/len(v)) for k,v in sorted(self.samples.items()))

    def observe(self,key,returns):
        self.samples.setdefault(key,[]).extend(float(v) for v in returns)
