"""Independent stdlib stored-output oracle. Never imports codec/candidate/RFL."""
from bisect import bisect_left
from collections import defaultdict
from fractions import Fraction
from hashlib import sha1, sha256
from itertools import combinations, product
from math import comb, prod
from pathlib import Path
import json
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
PREP=HERE.parent


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def read(p):return json.loads(p.read_bytes())
def require(ok,why):
    if not ok:raise AssertionError(why)


def records(folder, expected=None):
    claim,receipt=read(folder/'claim.json'),read(folder/'exit.json')
    require(receipt['native_child_exit_code']==0 and all(receipt[k]==v for k,v in claim.items()),'native receipt differs')
    for n,v in receipt['files'].items():
        b=(folder/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],n)
    require((folder/'stderr.log').read_bytes()==b'','native stderr nonempty')
    if expected:require(receipt['files']['stdout.log']['sha256']==expected,'stored output differs')
    out=[]
    for line in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete line')
        tag,v=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
        require(canonical(o).rstrip(b'\n')==v,'noncanonical tagged content')
        out.append((tag.decode(),o))
    return out,receipt


def choose(n,k):return comb(n,k) if 0<=k<=n else 0


def ordinary_rank(q,n):
    # Hockey-stick sum of all unrestricted lexicographic predecessor blocks.
    out,start=0,0;k=len(q)
    for d,i in enumerate(q):
        out+=choose(n-start,k-d)-choose(n-i,k-d);start=i+1
    return out


def monochrome_predecessors(q, group_indices):
    # Count each group's entire lexicographic predecessor set without querying codec prefixes.
    out=0;k=len(q)
    for indices in group_indices.values():
        start=0;N=len(indices)
        for d,i in enumerate(q):
            pos=bisect_left(indices,i)
            out+=choose(N-start,k-d)-choose(N-pos,k-d)
            if pos==N or indices[pos]!=i:break
            start=pos+1
    return out


def main():
    c=read(HERE/'contract.json');rows,receipt=records(HERE/'evidence')
    for n,d in receipt['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,n)
    scalar={t:o for t,o in rows if t in ('INPUT_BINDING_BEFORE','INPUT_BINDING_AFTER','FINAL')}
    before,after=scalar['INPUT_BINDING_BEFORE'],scalar['INPUT_BINDING_AFTER'];require(before==after,'inputs differ')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==before['parent_HEAD']==c['parent_commit'],'parent changed')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith('experiments/v03r/a96_dense/b2_prepare/')}
    bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    require((len(source),len(native),len(prior),len(bound),len(before['input_sha256']))==(313,153,349,663,821),'binding extent differs')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (source|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    toys=[o for t,o in rows if t=='TOY_CELL'];expected_ids=[];subsets=assignments=prefixes=0
    for toy,groups in enumerate(c['toys']):
        targets=[tuple(range(n)) for n in c['toy_target_counts']]
        for k in range(1,9):
            for shape in ('no-shape','singleton') if k==1 else ('no-shape','clustered','distributed'):
                expected_ids.append((toy,k,shape))
                item=next(o for o in toys if (o['toy'],o['k'],o['shape'])==(toy,k,shape))
                expected=[q for q in combinations(range(8),k) if shape in ('singleton','no-shape') or
                    (len({groups[i] for i in q})==1 if shape=='clustered' else len({groups[i] for i in q})>=2)]
                require(item['size']==len(expected) and len(item['rows'])==len(expected),'toy subset extent differs')
                mass=Fraction(0);ps={()}
                for rank,(q,row) in enumerate(zip(expected,item['rows'])):
                    actions=[list(v) for v in product(*(targets[i] for i in q))];P=Fraction(1,len(expected)*len(actions))
                    require(row=={'rank':rank,'subset':list(q),'target_assignments':actions,'per_assignment_probability':[P.numerator,P.denominator]},'complete toy targets/order/mass differ')
                    mass+=P*len(actions);subsets+=1;assignments+=len(actions)
                    for d in range(1,k+1):ps.add(q[:d])
                expected_prefix=[]
                for p in sorted(ps):
                    count=sum(q[:len(p)]==p for q in expected);branches=[]
                    if len(p)<k:
                        branches=[[i,sum(q[:len(p)+1]==p+(i,) for q in expected)] for i in range(p[-1]+1 if p else 0,8)]
                        require(sum(n for i,n in branches)==count,'independent branch total differs')
                    expected_prefix.append({'prefix':list(p),'count':count,'branches':branches});prefixes+=1
                require(item['prefixes']==expected_prefix and item['mass']==[mass.numerator,mass.denominator] and mass==(1 if expected else 0),'prefix/mass differs')
    require([(o['toy'],o['k'],o['shape']) for o in toys]==expected_ids,'toy cell missing/duplicate/reordered')
    old,unused=records(PREP/c['stored_catalog']['folder'],c['stored_catalog']['stdout_sha256'])
    dc=[o for t,o in old if t=='DECISION_CONTEXT'];xc=[o for t,o in old if t=='CONTROLLER_SITE']
    require(sha256(b''.join(canonical(o) for o in dc)).hexdigest()==c['stored_catalog']['decision_sha256'] and
            sha256(b''.join(canonical(o) for o in xc)).hexdigest()==c['stored_catalog']['controller_sha256'],'catalog differs')
    catalog={'Decision':[o for o in dc if o['alternatives']],'Controller':[o for o in xc if o['alternatives']]}
    oldsummary=next(o for t,o in old if t=='CATALOG_SUMMARY')
    cells=[o for t,o in rows if t=='PRODUCTION_CELL'];probe=[o for t,o in rows if t=='PRODUCTION_PROBE'];expected_probes=[];target_probes=0
    expected_cells=[]
    for kind,base in catalog.items():
        bygroup=defaultdict(list)
        for i,r in enumerate(base):bygroup[tuple(r['group'])].append(i)
        oldcells=oldsummary['decision_cells' if kind=='Decision' else 'controller_cells']
        for cell in oldcells:
            k,shape,M=cell['k'],cell['shape'],cell['context_subsets']
            total=choose(len(base),k);mono=sum(choose(len(v),k) for v in bygroup.values())
            require(M==(mono if shape=='clustered' else total-mono if shape=='distributed' else total),'production count differs')
            expected_cells.append({'kind':kind,'k':k,'shape':shape,'M':M,'full_eligible_support':len(base)})
            ranks=sorted({r for r in (0,1,2,M//3,M//2,M-3,M-2,M-1) if 0<=r<M})
            for rank in ranks:
                item=next(o for o in probe if (o['kind'],o['k'],o['shape'],o['context_rank'])==(kind,k,shape,rank))
                q=tuple(item['subset']);require(len(q)==k and tuple(sorted(set(q)))==q and all(type(i)is int and 0<=i<len(base) for i in q),'invalid production subset')
                groups={tuple(base[i]['group']) for i in q}
                require(shape in ('singleton','no-shape') or (len(groups)==1 if shape=='clustered' else len(groups)>=2),'production shape differs')
                unrestricted=ordinary_rank(q,len(base));monochrome=monochrome_predecessors(q,bygroup)
                independent=monochrome if shape=='clustered' else unrestricted-monochrome if shape=='distributed' else unrestricted
                require(independent==rank,'independent production lexicographic rank differs')
                targets=[base[i]['alternatives'] for i in q];radices=[len(v) for v in targets];L=prod(radices);P=Fraction(1,M*L)
                codes=sorted({r for r in (0,1,L//2,L-2,L-1) if 0<=r<L})
                require([o['code'] for o in item['target_probes']]==codes,'target probe missing/duplicate')
                for v in item['target_probes']:
                    actions=v['actions'];require(len(actions)==k and all(a in options for a,options in zip(actions,targets)),'target outside support')
                    code=sum(options.index(a)*prod(radices[j+1:]) for j,(a,options) in enumerate(zip(actions,targets)))
                    require(code==v['code'],'independent mixed radix code differs');target_probes+=1
                require(item['owners']==[base[i].get('context',base[i].get('site')) for i in q] and item['conditional_target_size']==L and item['per_assignment_probability']==[P.numerator,P.denominator],'production owner/full-target mass differs')
                expected_probes.append((kind,k,shape,rank))
    require(cells==expected_cells and [(p['kind'],p['k'],p['shape'],p['context_rank']) for p in probe]==expected_probes,'production probes incomplete')
    negatives=[o for t,o in rows if t=='NEGATIVE_CHALLENGE']
    names=['bool-rank','float-rank','negative-rank','overflow-rank','shape-k','bool-k','bad-shape','duplicate-context','unsorted-context','context-range','wrong-shape','target-bool','target-overflow','illegal-target','empty-subset-target']
    require(negatives==[{'name':name,'rejected':True} for name in names],'negative challenges differ')
    final=scalar['FINAL']
    require(final['toy_cells']==len(toys) and final['toy_subsets']==subsets and final['toy_target_assignments']==assignments and
        final['toy_prefixes']==prefixes and final['production_cells']==len(cells)==11 and final['production_arithmetic_probes']==len(probe) and final['negative_challenges']==15,'actual counts differ')
    for key in ('new_RFL_or_DP_execution','exact_failure_conditioning_closed','joint_calibration_totality','scientific_rules_adopted','scientific_PASS','collection_authorized','research_complete'):
        require(final[key] is False,'scientific scope overclaimed')
    require(all(final[k]==0 for k in ('new_native_learner_rollouts','new_B1_arms','random_draws','keys_allocated')) and final['delta_joint'] is None,'acquisition unexpected')
    print(json.dumps({'role':'PRIMARY_INDEPENDENT_STDLIB_STORED_CODEC_ORACLE_NOT_EXPERT_OR_SCIENCE','status':'FULL_STORED_CODEC_CONTENT_CHECKED',
        'runtime_inputs_checked':821,'parent_HEAD_byte_bindings':663,'source_count':313,'old_native_count':153,'prior_preparation_count':349,
        'toy_cells':len(toys),'toy_subsets':subsets,'toy_target_assignments':assignments,'toy_prefixes':prefixes,
        'production_cells':len(cells),'production_arithmetic_probes':len(probe),'production_target_probes':target_probes,
        'negative_challenges':15,'all11_whole_support_counts_checked':True,'production_rank_checked_by_independent_predecessor_formula':True,
        'new_codec_candidate_RFL_or_solver_execution':False,'old_v31_reexecuted':False,'independent_expert':False,'scientific_PASS':False,'collection_authorized':False},sort_keys=True))


if __name__=='__main__':main()
