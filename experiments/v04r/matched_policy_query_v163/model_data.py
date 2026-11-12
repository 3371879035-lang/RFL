"""Recorded immutable learned parameters only, never issued evidence identities."""
from dataclasses import dataclass
from query_value import ValueNode,FrozenQueryValue

@dataclass(frozen=True,slots=True)
class RecordedQueryModelPair:
    raw_sha256:str
    frozen_parameters:dict

    def materialize(self):
        def node(v):
            f=lambda k:float.fromhex(v[k]['binary64_hex'])
            return ValueNode(f('value'),v['n'],f('sse'),v['feature'],None if v['threshold'] is None else f('threshold'),None if v['left'] is None else node(v['left']),None if v['right'] is None else node(v['right']))
        def model(v):
            return FrozenQueryValue(tuple(tuple(float.fromhex(x['binary64_hex']) for x in pair) for pair in v['support']),node(v['root']),v['n'])
        return {k:model(v) for k,v in self.frozen_parameters['models'].items()}
