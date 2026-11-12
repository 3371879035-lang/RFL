"""Mode-neutral historical patterns propose tests, not numerical transfers."""
from dataclasses import dataclass
from selector import available_actions
from frozen_memory import span_key


@dataclass(frozen=True)
class ModeNeutralCandidateMenu:
    actions: tuple
    eligible: tuple
    keys: tuple
    supported_families: tuple
    omitted_singles: tuple


def memory_menu(mode,terminal,evidence,catalog,cap=2):
    families={key[2:-2] for key in catalog}
    keys=tuple((a,span_key(mode,terminal,evidence,a))
               for a in available_actions(mode,evidence) if a.startswith('single:'))
    eligible=tuple(a for a,key in keys if key[2:-2] in families)
    chosen=eligible[:cap]
    return ModeNeutralCandidateMenu(('keep',)+chosen,eligible,keys,tuple(sorted(families)),
                                    tuple(a for a,key in keys if a not in chosen))
