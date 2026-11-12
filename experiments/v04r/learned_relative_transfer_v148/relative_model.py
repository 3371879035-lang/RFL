"""Small learned relative-value tree; real historical pairs, visible features only."""
import json,hashlib

def number(x):return float.fromhex(x['binary64_hex'])

def features(evidence,current):
    for i,step in enumerate(evidence['steps']):
        if step['a_cmd']!=step['a_realized']:
            site={'state':{k:step[k] for k in ('x','y','t','kappa','phi')},'cmd':step['a_cmd']}
            present=any(x['address']==site for x in current['X'])
            return (len(evidence['steps'])-i-1,int(present))
    return None

def read_training(root,specs):
    points=[]
    for spec in specs:
        p=root/spec['raw']['path'];data=p.read_bytes()
        assert len(data)==spec['raw']['bytes'] and hashlib.sha256(data).hexdigest()==spec['raw']['sha256']
        for field in ('exit','review'):
            raw=(root/spec[field]['path']).read_bytes();assert len(raw)==spec[field]['bytes'] and hashlib.sha256(raw).hexdigest()==spec[field]['sha256']
        ex=json.loads((root/spec['exit']['path']).read_bytes());review=json.loads((root/spec['review']['path']).read_bytes())
        assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and ex['raw']=={k:spec['raw'][k] for k in ('bytes','sha256')} and review['complete']
        records=[json.loads(s) for s in data.decode('ascii').splitlines()]
        selected=[r for r in records if r['context'].get('arm')==spec['arm'] and r['context'].get('case')==spec['case']]
        d=next(r for r in selected if r['tag']=='DIAGNOSE_BEGIN');e=d['payload']['evidence'];cur=d['payload']['state_before']['current']
        trial={r['context']['candidate']:[number(v) for v in r['payload']['returns']] for r in selected if r['tag']=='TRIAL_COMPLETE'}
        assert set(trial)=={'keep','controller-delete'} and all(len(v)==2 for v in trial.values())
        means={k:sum(v)/2 for k,v in trial.items()};x=features(e,cur);assert x is not None
        points.append({'id':spec['id'],'x':list(x),'y':means['controller-delete']-means['keep'],'paired_returns':trial,
                       'context':[e['kappa'],e['phi']],'raw_sha256':spec['raw']['sha256'],'factual_seq':d['seq']})
    return points

def fit(points):
    data=[(tuple(p['x']),p['y']) for p in points]
    def mean(data):return sum(y for x,y in data)/len(data)
    def loss(data):
        m=mean(data);return sum((y-m)**2 for x,y in data)
    def grow(data):
        avg=mean(data);base=loss(data);choices=[]
        for f in range(2):
            values=sorted({x[f] for x,y in data})
            for a,b in zip(values,values[1:]):
                cut=(a+b)/2;left=[v for v in data if v[0][f]<=cut];right=[v for v in data if v[0][f]>cut]
                choices.append((loss(left)+loss(right),f,cut,left,right))
        if not choices:return {'mean':avg,'n':len(data)}
        score,f,cut,left,right=min(choices,key=lambda c:c[:3])
        if score>=base:return {'mean':avg,'n':len(data)}
        return {'feature':f,'threshold':cut,'left':grow(left),'right':grow(right)}
    return grow(data)

def predict(tree,x):
    if x is None:return 0.0
    while 'mean' not in tree:tree=tree['left'] if x[tree['feature']]<=tree['threshold'] else tree['right']
    return tree['mean']
