"""Local memory applicability rule, not calibrated statistical uncertainty."""

def reconsider(selected,info,contested):
    if selected is None:return None,'unsupported'
    if any(tuple(k) in contested for k in info['keys'].values()):return None,'contested-key'
    same=[a for a,v in info['scores'].items() if v==info['scores'][selected]
          and info['keys'][a]==info['keys'][selected]]
    if len(same)>1:return None,'duplicate-best-key'
    return selected,'supported-unique'


def conflicting_keys(keys,returns):
    grouped={}
    for action,values in returns.items():
        grouped.setdefault(keys[action],[]).append((action,sum(values)/len(values)))
    return {k:tuple(v) for k,v in grouped.items() if len({m.hex() for a,m in v})>1}
