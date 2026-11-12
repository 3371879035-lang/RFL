"""A failed successor is a reason to investigate, not a causal blame label."""


def requires_review(pending, epoch, terminal, context):
    if pending is None:
        return False
    return (terminal in ('COLLISION', 'TRAP', 'TIMEOUT')
            and epoch == pending['epoch'] + 1
            and tuple(context) == tuple(pending['context']))
