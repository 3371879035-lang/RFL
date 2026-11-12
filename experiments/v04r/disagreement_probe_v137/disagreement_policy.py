"""An extra hypothesis test can be requested by prediction disagreement."""


def comparison_candidate(primary,info,menu):
    secondary=info['comparison']['selected']
    if primary is None or secondary in (None,'keep',primary):
        return None
    if secondary in menu and info['coverage'][secondary]['exact_terminal_point_samples']==0:
        return secondary
    return None
