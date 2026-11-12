"""Finite verification from actual trial outcomes, without state/mask access."""


def probe_order(menu,hypothesis):
    if hypothesis is None or hypothesis=='keep':return tuple(menu)
    return ('keep',hypothesis)+tuple(a for a in menu if a not in ('keep',hypothesis))


def needs_alternate(observed,hypothesis):
    outcome,value=observed[hypothesis]
    return outcome!='SUCCESS' or value<observed['keep'][1]
