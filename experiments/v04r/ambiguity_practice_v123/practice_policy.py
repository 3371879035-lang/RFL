"""Explicit bounded practice requests, with no environment or state access."""

def ambiguous_singles(chosen, decision, cap=2):
    scores=decision['scores']
    if not chosen.startswith('single:') or chosen not in scores:
        return (), ()
    top=max(scores.values());key=decision['keys'][chosen]
    eligible=tuple(a for a in scores if a.startswith('single:') and
                   scores[a]==top and decision['keys'][a]==key)
    return (eligible[:cap],eligible) if len(eligible)>1 else ((),eligible)


def choose_actual(returns, costs, order):
    means={a:sum(values)/len(values) for a,values in returns.items()}
    chosen=min(order,key=lambda a:(-means[a],costs[a],order.index(a)))
    return chosen,means
