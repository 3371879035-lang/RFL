"""Single keyless syntax codec verification. Imports no RFL or old candidate."""
from fractions import Fraction
from hashlib import sha1, sha256
from itertools import combinations, product
from pathlib import Path
import json
import subprocess
from catalog_codec import SubsetCodec

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
PREP=HERE.parent


def canonical(o):
    return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()


def emit(tag, o):
    print(tag+'='+canonical(o).decode().rstrip('\n'),flush=True)


def require(ok, why):
    if not ok:raise AssertionError(why)


def read(p):return json.loads(p.read_bytes())


def bind():
    c=read(HERE/'contract.json');head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==c['parent_commit'],'parent changed')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in
          subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith('experiments/v03r/a96_dense/b2_prepare/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,349,663),'parent extent differs')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in
        ('contract.json','catalog_codec.py','candidate.py','check_stored.py','execute.py')}
    require(len(names)==821,'runtime extent differs')
    return {'parent_HEAD':head,'HEAD_byte_bindings':663,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}


def stored():
    c=read(HERE/'contract.json')['stored_catalog'];f=PREP/c['folder']
    claim,receipt=read(f/'claim.json'),read(f/'exit.json')
    require(receipt['native_child_exit_code']==0 and all(receipt[k]==v for k,v in claim.items()),'stored receipt differs')
    for n,v in receipt['files'].items():
        b=(f/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],n)
    require(receipt['files']['stdout.log']['sha256']==c['stdout_sha256'],'stored catalog binding differs')
    rows=[(l.split('=',1)[0],json.loads(l.split('=',1)[1])) for l in (f/'stdout.log').read_text(encoding='utf8').splitlines()]
    dc=[o for t,o in rows if t=='DECISION_CONTEXT'];xc=[o for t,o in rows if t=='CONTROLLER_SITE']
    require(sha256(b''.join(canonical(o) for o in dc)).hexdigest()==c['decision_sha256'] and
            sha256(b''.join(canonical(o) for o in xc)).hexdigest()==c['controller_sha256'],'full base catalog differs')
    return [r for r in dc if r['alternatives']],[r for r in xc if r['alternatives']],next(o for t,o in rows if t=='CATALOG_SUMMARY')


def allowed(q, groups, shape):
    n=len({groups[i] for i in q})
    return shape in ('singleton','no-shape') or (n==1 if shape=='clustered' else n>=2)


def main():
    before=bind();emit('INPUT_BINDING_BEFORE',before);c=read(HERE/'contract.json')
    subset_count=target_count=prefix_count=cell_count=0
    for toy,groups in enumerate(c['toys']):
        targets=[tuple(range(n)) for n in c['toy_target_counts']]
        codec=SubsetCodec([(g,) for g in groups],targets)
        for k in range(1,9):
            for shape in ('no-shape','singleton') if k==1 else ('no-shape','clustered','distributed'):
                expected=[q for q in combinations(range(8),k) if allowed(q,groups,shape)]
                require(codec.size(k,shape)==len(expected),'toy cell size differs')
                rows=[];mass=Fraction(0);prefixes={()}
                for rank,q in enumerate(expected):
                    require(codec.unrank(rank,k,shape)==q and codec.rank(q,k,shape)==rank,'toy subset bijection differs')
                    for d in range(1,len(q)+1):prefixes.add(q[:d])
                    assignments=[];prob=codec.probability(q,k,shape)
                    for code,actions in enumerate(product(*(targets[i] for i in q))):
                        require(codec.target_unrank(q,code)==actions and codec.target_rank(q,actions)==code,'target bijection differs')
                        assignments.append(list(actions));target_count+=1;mass+=prob
                    rows.append({'rank':rank,'subset':list(q),'target_assignments':assignments,'per_assignment_probability':[prob.numerator,prob.denominator]})
                    subset_count+=1
                require(mass==(1 if expected else 0),'toy probability measure differs')
                prefixrows=[]
                for p in sorted(prefixes):
                    total=codec.completions(p,k,shape)
                    expected_total=sum(q[:len(p)]==p for q in expected)
                    require(total==expected_total,'prefix count differs')
                    branches=[]
                    if len(p)<k:
                        branches=[[i,codec.completions(p+(i,),k,shape)] for i in range(p[-1]+1 if p else 0,8)]
                        require(sum(n for i,n in branches)==total,'branch partition differs')
                    prefixrows.append({'prefix':list(p),'count':total,'branches':branches});prefix_count+=1
                if not expected:
                    try:codec.unrank(0,k,shape)
                    except ValueError:pass
                    else:raise AssertionError('empty cell accepted')
                emit('TOY_CELL',{'toy':toy,'k':k,'shape':shape,'size':len(expected),'rows':rows,'prefixes':prefixrows,'mass':[mass.numerator,mass.denominator]});cell_count+=1
    dc,xc,summary=stored();probes=0
    for kind,rows,cells in [('Decision',dc,summary['decision_cells']),('Controller',xc,summary['controller_cells'])]:
        codec=SubsetCodec([r['group'] for r in rows],[r['alternatives'] for r in rows])
        for item in cells:
            k,shape=item['k'],item['shape'];M=codec.size(k,shape);require(M==item['context_subsets'],'production cell size differs')
            emit('PRODUCTION_CELL',{'kind':kind,'k':k,'shape':shape,'M':M,'full_eligible_support':len(rows)})
            for rank in sorted({r for r in (0,1,2,M//3,M//2,M-3,M-2,M-1) if 0<=r<M}):
                subset=codec.unrank(rank,k,shape);require(codec.rank(subset,k,shape)==rank,'production subset roundtrip differs')
                L=codec.target_size(subset);prob=codec.probability(subset,k,shape);tp=[]
                for code in sorted({r for r in (0,1,L//2,L-2,L-1) if 0<=r<L}):
                    actions=codec.target_unrank(subset,code);require(codec.target_rank(subset,actions)==code,'production target roundtrip differs')
                    tp.append({'code':code,'actions':list(actions)})
                emit('PRODUCTION_PROBE',{'kind':kind,'k':k,'shape':shape,'context_rank':rank,'subset':list(subset),
                    'owners':[rows[i].get('context',rows[i].get('site')) for i in subset],
                    'conditional_target_size':L,'target_probes':tp,'per_assignment_probability':[prob.numerator,prob.denominator]});probes+=1
    base=SubsetCodec([(0,),(1,),(0,)],[(0,),(0,1),(0,1,2)])
    cases=[('bool-rank',lambda:base.unrank(True,1,'singleton')),('float-rank',lambda:base.unrank(0.0,1,'singleton')),
       ('negative-rank',lambda:base.unrank(-1,1,'singleton')),('overflow-rank',lambda:base.unrank(3,1,'singleton')),
       ('shape-k',lambda:base.unrank(0,1,'distributed')),('bool-k',lambda:base.size(True,'singleton')),
       ('bad-shape',lambda:base.size(1,'other')),('duplicate-context',lambda:base.rank((0,0),2,'clustered')),
       ('unsorted-context',lambda:base.rank((2,0),2,'clustered')),('context-range',lambda:base.rank((3,),1,'singleton')),
       ('wrong-shape',lambda:base.rank((0,1),2,'clustered')),('target-bool',lambda:base.target_unrank((1,),True)),
       ('target-overflow',lambda:base.target_unrank((1,),2)),('illegal-target',lambda:base.target_rank((1,),(99,))),
       ('empty-subset-target',lambda:base.target_unrank((),0))]
    for name,call in cases:
        try:call()
        except ValueError:emit('NEGATIVE_CHALLENGE',{'name':name,'rejected':True})
        else:raise AssertionError('invalid request accepted: '+name)
    after=bind();require(before==after,'input drift');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'PURE_SYNTAX_CODEC_COMPONENT_COMPLETE_NOT_SCIENCE','toy_cells':cell_count,'toy_subsets':subset_count,
        'toy_target_assignments':target_count,'toy_prefixes':prefix_count,'production_cells':11,'production_arithmetic_probes':probes,
        'negative_challenges':len(cases),'all_inputs_equal':True,'old_catalog_read_not_reexecuted':True,
        'new_RFL_or_DP_execution':False,'new_native_learner_rollouts':0,'new_B1_arms':0,'random_draws':0,'keys_allocated':0,
        'exact_failure_conditioning_closed':False,'joint_calibration_totality':False,'delta_joint':None,
        'scientific_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})


if __name__=='__main__':main()
