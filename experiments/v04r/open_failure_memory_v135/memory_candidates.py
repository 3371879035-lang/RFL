"""Historical feature support proposes tests, not diagnoses or live writes."""
from dataclasses import dataclass
from selector import available_actions
from frozen_memory import span_key


def without_terminal(key):
    return key[:1]+key[2:]


@dataclass(frozen=True)
class MemoryCandidateMenu:
    actions: tuple
    eligible: tuple
    keys: tuple
    supported_families: tuple
    omitted_singles: tuple


def memory_menu(mode, terminal, evidence, samples, cap=2):
    families={without_terminal(k[:-2]) for k,n,value in samples if n>0}
    keys=tuple((a,span_key(mode,terminal,evidence,a))
               for a in available_actions(mode,evidence) if a.startswith('single:'))
    eligible=tuple(a for a,key in keys if without_terminal(key[:-2]) in families)
    chosen=eligible[:cap]
    return MemoryCandidateMenu(('keep',)+chosen,eligible,keys,tuple(sorted(families)),
                               tuple(a for a,key in keys if a not in chosen))
