"""First main-agent stdlib stored audit for v85 only; never imports RFL/old fixture/checker."""
import ast,collections,hashlib,itertools,json,math,pathlib,subprocess
root=pathlib.Path.cwd();p=root/'experiments/v03r/a96_dense/b2_prepare/oracle_registered_positive_v85'
def sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def meta(p):
 with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 return {'bytes':p.stat().st_size,'sha256':h}
c=json.loads((p/'evidence/claim.json').read_bytes());e=json.loads((p/'evidence/exit.json').read_bytes())
contract=json.loads((p/'contract.json').read_bytes())
assert c['input_binding_before']==e['input_binding_after'] and e['child_exit_code']==0 and e['input_bytes_unchanged']
assert c['parent_commit']==contract['parent_commit']==subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
tree={}
for line in subprocess.check_output(['git','ls-tree','-r','-z',c['parent_commit']]).split(b'\0'):
 if line:
  h,n=line.split(b'\t',1);tree[n.decode()]=h.split()[2].decode()
assert len(tree)==2885 and len(c['input_binding_before'])==2888
totalbytes=0
for n,m in c['input_binding_before'].items():
 f=root/n;size=f.stat().st_size;h=hashlib.sha256();g=hashlib.sha1(('blob '+str(size)+'\0').encode())
 with f.open('rb') as stream:
  while b:=stream.read(8*1024*1024):h.update(b);g.update(b)
 assert {'bytes':size,'sha256':h.hexdigest()}==m,n
 if n in tree:assert g.hexdigest()==tree[n],n
 totalbytes+=size
for n in ('stdout','stderr'):assert meta(p/'evidence'/(n+'.log'))==e[n]
records=[]
for line in (p/'evidence/stdout.log').read_bytes().splitlines():
 tag,b=line.split(b'=',1);v=json.loads(b)
 assert json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()==b
 records.append((tag.decode(),v))
get=lambda tag:[v for k,v in records if k==tag]
counts=collections.Counter(k for k,v in records)
assert len(records)==675 and records[-1][0]=='FINAL'
final=get('FINAL')[0]
assert final['counts']=={'B1':6,'blocked':0,'mean':6,'mean_completed':6,'patch_builder':2,'patch_validator':2,
 'plan':6,'preflight_contract':12,'rollout':602,'step':3684,'transaction':5}
assert (final['tests'],final['errors'],final['failures'],final['skipped'])==(4,0,0,0)
assert all(final[k]==0 for k in ('CF_replay','DP','training','old_fixture_reruns'))
assert all(final[k] is False for k in ('collector','keys_allocated','native_calibration','scientific_PASS','research_complete'))
assert final['extra_actual_source_work']==2 and final['source_descriptor']==[1,5,0,35,0]
stderr=(p/'evidence/stderr.log').read_text(encoding='utf8')
assert 'Ran 4 tests' in stderr and stderr.rstrip().endswith('OK')
testtree=ast.parse((p/'test_new_integration.py').read_bytes())
ids=[n.name for n in ast.walk(testtree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
assert len(set(ids))==4
for test in ids:
 lines=[l for l in stderr.splitlines() if l.startswith(test+' ')]
 assert len(lines)==1 and lines[0].endswith('... ok')
helper=contract['correct_exact_signature_helper'];assert meta(root/helper['path'])=={k:helper[k] for k in ('bytes','sha256')}
htree=ast.parse((root/helper['path']).read_bytes())
capture=[n for n in ast.walk(htree) if isinstance(n,ast.FunctionDef) and n.name=='capture'][0]
assert [a.arg for a in capture.args.args]==['law','addresses','targets'] and not capture.decorator_list
assert not any(isinstance(n,ast.Attribute) and n.attr in ('__signature__','__wrapped__') for n in ast.walk(htree))
assert not any(isinstance(n,ast.FunctionDef) and n.name=='capture' for n in ast.walk(testtree))
apis=get('PRE_SOURCE_ACTUAL_BOUND_API')
assert len(apis)==12 and all(v['names']==['addresses','targets'] and v['kinds']==['POSITIONAL_OR_KEYWORD']*2
 and not v['real_plan_executed'] and all(x==0 for x in v['native_counts_before_source'].values()) for v in apis)
assert [v['phase'] for v in apis]==['original']*6+['hooked']*6
restored=get('RUNTIME_ALIAS_AND_CAPTURE_RESTORED')[0]
assert all(restored[k] is True for k in ('alias_parent_identity_before_during_after','no_own_alias_plan',
 'all_original_plan_function_and_registry_identities','native_capture_and_original_mean_alias_restored'))
assert restored['extra_real_sources']==2 and restored['old_fixture_or_partial_retry'] is False
catalog={}
for line in (root/'experiments/v03r/a96_dense/b2_prepare/grammar_catalog_v31/evidence/stdout.log').read_bytes().splitlines():
 if line.startswith(b'DECISION_CONTEXT='):
  v=json.loads(line.split(b'=',1)[1]);key=tuple(v['context']);assert key not in catalog
  catalog[key]={a:float.fromhex(x) for a,x in v['q_row_hex']}
assert len(catalog)==13824
def fingerprint(s):
 assert set(s)=={'D','P','X','Q'}
 for k in s:assert s[k]==sorted(s[k]) and len({tuple(a) if type(a) is list else a for a,v in s[k]})==len(s[k])
 ds='\n'.join(sorted('D:'+','.join(map(str,a+[v])) for a,v in s['D']))
 ps='\n'.join(sorted('P:'+str(a)+','+str(v) for a,v in s['P']))
 xs='\n'.join(sorted('X:'+','.join(map(str,a+[v])) for a,v in s['X']))
 qs='\n'.join(sorted('Q:'+','.join(map(str,a))+'|'+v for a,v in s['Q']))
 return hashlib.sha256('\0'.join((ds,ps,xs,qs)).encode()).hexdigest()
deltas=((0,-1),(0,1),(-1,0),(1,0),(0,0))
opened={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
hazard=lambda t,k,ph:t%({0:6,1:3}[k])==ph%({0:6,1:3}[k])
def checkraw(raw,scene,state,ivs):
 k,ph,err,cause,base=scene;z=dict(state['P']).get(base,base);s=[0,2,0,k,ph];m=0
 d={tuple(a):v for a,v in state['D']};q={tuple(a):float.fromhex(v) for a,v in state['Q']};x={tuple(a):v for a,v in state['X']}
 ivmap={}
 for iv in ivs:
  assert iv['kind']=='decision'
  t=iv['t'];text=iv['repr'];prefix="Intervention(kind='decision', t="+str(t)+", action="
  assert text.startswith(prefix) and text.endswith(", option=None, site=None)")
  action=int(text[len(prefix):].split(',',1)[0]);assert action in range(5) and t not in ivmap;ivmap[t]=action
 for i,r in enumerate(raw):
  assert r['pre_state']==s and r['z']==z and r['m']==m and r['illegal'] is False
  row=catalog[tuple(s+[z,m])];effective={a:q.get(tuple(s+[z,m,a]),v) for a,v in row.items()}
  a=ivmap.get(i,d.get(tuple(s+[z,m]),max(effective,key=lambda a:(effective[a],-a))))
  assert a in row and r['a_cmd']==a
  u=x.get(tuple(s+[a]),a);assert u in row and r['u']==r['a_realized']==u
  dx,dy=deltas[u];cell=(s[0]+dx,s[1]+dy)
  if cell not in opened:cell=tuple(s[:2])
  t=i+1;ns=[*cell,t,k,ph];out=None
  if cell==(2,2) and hazard(t,k,ph):out='COLLISION'
  elif cell==(4,2):out='SUCCESS'
  elif t>=12:out='TIMEOUT'
  nm=m
  if m==0:
   if (z==1 and cell==(2,1)) or (z==3 and cell==(2,4)) or (z==2 and tuple(s[:2])==(1,2) and not hazard(i,k,ph)):nm=1
  assert r['post_state']==ns and r['post_control']==[z,nm]
  assert r['outcome']==out and r['terminal']==(out is not None)
  reward=-0.02
  if out is not None:reward+=1.0 if out=='SUCCESS' else -1.0
  assert r['reward_hex']==reward.hex() and (i==len(raw)-1)==r['terminal'];s=ns;m=nm
 assert 1<=len(raw)<=12
 return float(sum(float.fromhex(r['reward_hex']) for r in raw)),z

sources=get('OWNED_SOURCE');inputs=get('SOURCE_INPUT');scopes=get('INSTALL_DECLARED_CONTEXT_SCOPE')
txb=get('TX_BEGIN');txe=get('TX_END');raws=get('NATIVE_RAW_BEFORE_CALLER_TRUTH_TARGET_OR_MEAN')
assert len(sources)==len(inputs)==len(scopes)==2 and len(txb)==len(txe)==5 and len(raws)==602
contexts=sorted([list(a)+[4 in row] for a,row in catalog.items() if a[3:6]==(1,5,2)])
expectedq=sorted([[list(a)+[4],(max(row.values())+1.0).hex()] for a,row in catalog.items() if a[3:6]==(1,5,2) and 4 in row]+
    [[[0,2,0,0,5,2,0,4],(max(catalog[(0,2,0,0,5,2,0)].values())+2.0).hex()]])
expectedd=sorted([[list(a),4] for a,row in catalog.items() if a[3:6]==(1,5,2) and 4 in row]+[[[0,2,0,0,5,2,0],4]])
expectedx=[[[0,2,0,0,5,4],3],[[0,2,0,1,5,4],3],[[1,2,1,1,5,4],2]]
positions=lambda tag:[i for i,(t,v) in enumerate(records) if t==tag]
saved=[];source_meta=[]
for i,architecture in enumerate(('D_Q','D_patch')):
 source=sources[i]['audit'];sp=source['payload']['native_source_payload'];cfg=source['payload']['configuration_declared_before_native']
 assert sha(source['payload'])==source['payload_sha256'] and sha(sp)==source['payload']['native_source_sha256']
 assert sp['scene']==cfg['scene']==[1,5,0,35,0] and sp['regime']=='P' and sp['owned_cf_configuration'] is None
 assert all(v is None for v in cfg['faults'].values()) and cfg['interventions']==[] and cfg['reward_mode']=='A'
 expected={'D':[] if i==0 else expectedd,'P':[[0,2],[3,1]],'Q':expectedq if i==0 else [],'X':expectedx}
 assert sp['full_pre_stores']==inputs[i]['pre']==txe[i]['post']==expected
 assert sp['fingerprint_pre']==fingerprint(expected)
 assert scopes[i]['all_contexts']==contexts and len(contexts)==288 and sum(x[-1] for x in contexts)==276
 assert scopes[i]['illegal_WAIT_contexts_preserved']==[x[:-1] for x in contexts if not x[-1]]
 assert txb[i]['pre']=={'D':[],'P':[],'X':[],'Q':[]} and txb[i]['edits']==scopes[i]['literal_edits'] and len(txb[i]['edits'])==282
 assert txb[i]['ordinal']==txe[i]['ordinal']==i+1
 for site,target in expectedx:
  serving=[row for a,row in catalog.items() if a[:5]==tuple(site[:5]) and site[5] in row]
  assert len(serving)==6 and all(target in row for row in serving)
 factual=raws[i]
 assert factual['ordinal']==i+1 and factual['configuration']==inputs[i]['configuration']==cfg
 assert factual['actual_interventions']==[] and factual['raw']==sp['raw_factual']
 value,z=checkraw(factual['raw'],cfg['scene'],expected,[])
 assert value.hex()==factual['return_hex'] and z==2==factual['option_in_force']
 assert len(factual['raw'])==12 and factual['outcome']=='TIMEOUT' and value==-1.24
 assert positions('TX_BEGIN')[i]<positions('TX_END')[i]<positions('NATIVE_RAW_BEFORE_CALLER_TRUTH_TARGET_OR_MEAN')[i]<positions('OWNED_SOURCE')[i]
 truth=sp['truth_evaluator_only'];times=[];controllers=[];baseline=[]
 for row in factual['raw']:
  a=tuple(row['pre_state']+[row['z'],row['m']]);qrow=catalog[a]
  optimal=sorted(a for a,v in qrow.items() if v>=max(qrow.values())-1e-12)
  if row['a_cmd'] not in optimal:times.append(row['pre_state'][2])
  if row['u']!=row['a_cmd']:controllers.append(row['pre_state']+[row['a_cmd']])
  baseline.append({'pre_state':row['pre_state'],'z':row['z'],'m':row['m'],'a_learner':row['a_cmd'],
                   'u_learner':row['u'],'optimal_actions':optimal})
 gamma=['ProcessCommit']+[f'Decision_{t}' for t in times]+[f'ControllerSite_{a[0]}_{a[1]}_{a[2]}_{a[5]}' for a in controllers]
 assert times==[0,2,4,5,7,8,9] and truth['Gamma_P_star']==gamma
 assert truth['J_L']==[True,True,True] and truth['Gamma_T_star'] is None and truth['R_mech'] is None
 assert truth['source_separated_baseline_rows']==baseline and truth['manifested_decision_timesteps']==times
 assert truth['manifested_controller_sites']==controllers and truth['manifested_process_proposals']==[0]
 saved.append((factual['raw'],truth))
 source_meta.append({'architecture':architecture,'source_sha256':source['payload_sha256'],
    'native_source_sha256':source['payload']['native_source_sha256'],'full_counts':{k:len(v) for k,v in expected.items()},
    'Gamma_P':gamma,'fingerprint':sp['fingerprint_pre'],'raw_steps':12,'outcome':'TIMEOUT','return':value})
assert saved[0]==saved[1]

times=[0,2,4,5,7,8,9]
source_by_arch={v['label'].replace('P_GENERAL_',''):v['audit'] for v in sources}
for x in contract['descriptor']['complete_context_scope']:
 row=catalog[tuple(x['context'])]
 assert x['allowed']==list(row) and x['WAIT_legal']==(4 in row)
 assert x['q_WAIT_override']==((max(row.values())+1).hex() if 4 in row else None)
for group in contract['descriptor']['controller_literal_complete_serving_legality']:
 site=group['site'];target=group['target'];actual=[]
 for z in range(4):
  for m in range(2):
   key=site[:5]+[z,m];row=catalog[tuple(key)]
   if 4 in row:actual.append({'context':key,'allowed':list(row),'cmd':4,'target':target});assert target in row
 assert actual==group['all_original_serving_contexts']
# Full native six-arm whole plans, lowering, transactions and every owner receipt.
plans=get('ORIGINAL_LAW_PLAN');starts=get('B1_BEGIN');ends=get('B1_END')
assert len(plans)==len(starts)==len(ends)==6
envelopes=get('ORIGINAL_PATCH_ENVELOPE');validations=get('ORIGINAL_PATCH_VALIDATION')
patch_src=source_by_arch['D_patch']['payload']['native_source_payload'];fraw=patch_src['raw_factual']
addresses=[','.join(map(str,fraw[t]['pre_state']+[fraw[t]['z'],fraw[t]['m']])) for t in times]
alts=[]
for t,addr in zip(times,addresses):
 r=fraw[t];row=catalog[tuple(r['pre_state']+[r['z'],r['m']])]
 alt=min(a for a,v in row.items() if v>=max(row.values())-1e-12 and a!=r['a_cmd'])
 alts.append({'address':addr,'alternative':alt,'factual_command':r['a_cmd']})
assert len(envelopes)==len(validations)==2
assert all(v['addresses']==addresses and v['targets']==alts and v['label']=='PATCH_L1' for v in envelopes+validations)
assert all(v['result']=='VALID' for v in validations)
expectedstates=[];expectededits=[]
def drepr(a):
 x,y,t,k,ph,z,m=a
 return f'DecisionAddress(state=State(x={x}, y={y}, t={t}, kappa={k}, phi={ph}), z={z}, m={m})'
for i,(plan,start,end) in enumerate(zip(plans,starts,ends)):
 name=('DQ_L3','PATCH_L1','PATCH_L3')[i//2];architecture='D_Q' if i<2 else 'D_patch'
 src=source_by_arch[architecture]['payload']['native_source_payload'];pre=src['full_pre_stores']
 assert plan['label']==start['label']==end['label']==name and start['pre']==pre and start['addresses']==addresses
 assert start['tier']==('L1_CORRECTIVE' if name=='PATCH_L1' else 'L3_ORACLE') and start['law']==plan['law']
 assert plan['law']==('NoWrite' if i%2==0 else 'SetAlternative' if name=='PATCH_L1' else 'LocalOracleRestore')
 full=json.loads(json.dumps(pre));editstrings=[]
 d={tuple(a):v for a,v in pre['D']};q={tuple(a):v for a,v in pre['Q']}
 for j,(addr,pl) in enumerate(zip(addresses,plan['plans'])):
  a=tuple(map(int,addr.split(',')));assert pl['address']==addr and pl['status'] is None
  if i%2==0:assert pl['edits']==[] and pl['row_op'] is None
  elif name=='DQ_L3':
   assert pl['edits']==[] and pl['row_op']=='RestoreRow(context='+drepr(a)+')'
   for qa in sorted(list(q)):
    if qa[:-1]==a:
     x,y,t,k,ph,z,m,action=qa
     editstrings.append(f"Edit(store='q', address=QAddress(state=State(x={x}, y={y}, t={t}, kappa={k}, phi={ph}), z={z}, m={m}, a={action}), value=None)")
     del q[qa]
  else:
   alt=alts[j]['alternative'] if name=='PATCH_L1' else None
   edit=f"Edit(store='decision', address={drepr(a)}, value={alt!r})"
   assert pl['edits']==[edit] and pl['row_op'] is None;editstrings.append(edit)
   if alt is None:d.pop(a,None)
   else:d[a]=alt
 full['Q']=sorted([[list(a),v] for a,v in q.items()]);full['D']=sorted([[list(a),v] for a,v in d.items()])
 assert end['post']==full and len(plan['plans'])==7
 if name=='PATCH_L1':
  assert plan['delivered_fields']==[{'address':v['address'],'fields':{'alternative':v['alternative']}} for v in alts]
 else:assert plan['delivered_fields'] is None
 ledger=end['ledger']
 assert ledger['fingerprint_pre']==fingerprint(pre) and ledger['fingerprint_post']==fingerprint(full)
 assert ledger['scalar_metrics_applicable']==(architecture=='D_Q')
 view='Q' if architecture=='D_Q' else 'D'
 before={tuple(a):v for a,v in pre[view]};after={tuple(a):v for a,v in full[view]}
 changed=sorted(a for a in before.keys()|after.keys() if before.get(a)!=after.get(a));delta=[]
 if architecture=='D_Q':
  for a in changed:
   was=float.fromhex(before[a]) if a in before else catalog[a[:-1]][a[-1]]
   now=float.fromhex(after[a]) if a in after else catalog[a[:-1]][a[-1]];delta.append(abs(now-was))
 assert (ledger['n_scalar'],ledger['sum_abs_delta'],ledger['max_abs_delta'])==(len(delta),math.fsum(delta),max(delta,default=0.0))
 receipts=[]
 for addr in addresses:
  a=tuple(map(int,addr.split(',')));flag=any((v[:-1] if architecture=='D_Q' else v)==a for v in changed)
  receipts.append(addr+('|APPLIED|1' if flag else '|EVALUABLE_NOOP|0'))
 assert ledger['receipts']==receipts and all((a[:-1] if architecture=='D_Q' else a) in [tuple(map(int,x.split(','))) for x in addresses] for a in changed)
 for k in ('P','X'):assert full[k]==pre[k]
 assert full['D' if architecture=='D_Q' else 'Q']==pre['D' if architecture=='D_Q' else 'Q']
 assert all((v is not None for k in full for a,v in full[k])) and full!=dict.fromkeys(full,[]) # retained full persistent defects
 expectedstates.append(full);expectededits.append(editstrings)
for j,i in enumerate((1,3,5),2):
 arch='D_Q' if i==1 else 'D_patch';pre=source_by_arch[arch]['payload']['native_source_payload']['full_pre_stores']
 assert txb[j]['pre']==pre and txb[j]['edits']==expectededits[i] and txe[j]['post']==expectedstates[i]
 assert len(txb[j]['edits'])==7 and txb[j]['ordinal']==txe[j]['ordinal']==j+1
 assert positions('B1_BEGIN')[i]<positions('ORIGINAL_LAW_PLAN')[i]<positions('TX_BEGIN')[j]<positions('TX_END')[j]<positions('B1_END')[i]
# All raw rounds independently checked from actual per-role full stores.
byord={v['ordinal']:v for v in raws};assert sorted(byord)==list(range(1,603))
begins=get('BANK_ROLE_BEGIN');completes=get('BANK_ROLE_NATIVE_COMPLETE');assert len(begins)==len(completes)==6
pairs={v['label']:v['audit'] for v in get('NEW_PAIR')}
futures={v['label']:v['audit'] for v in get('OWNED_FUTURE')}
banks={v['label']:v['audit'] for v in get('OWNED_BANK')}
assert set(pairs)==set(futures)==set(banks)=={'DQ_L3','PATCH_L1','PATCH_L3'}
basegrid=list(itertools.product(range(2),range(6),range(2),range(4)));sample=[]
for n in range(100):
 q,r=divmod(n,96);k,ph,err,z=basegrid[r];sample.append([k,ph,err,(7*q+37*r)%60,z])
assert hashlib.sha256(repr(tuple(map(tuple,sample))).encode()).hexdigest()=='2687229d31bec0afd233dd9fc32ada7117a4f81da6cfd837e6eec13f330f4cd2'
measured=[];banksteps=0
for j,name in enumerate(('DQ_L3','PATCH_L1','PATCH_L3')):
 arch='D_Q' if j==0 else 'D_patch';source=source_by_arch[arch];sp=source['payload']['native_source_payload'];cfg=source['payload']['configuration_declared_before_native']
 pair=pairs[name];assert sha(pair['payload'])==pair['payload_sha256'] and pair['payload']['source_sha256']==source['payload_sha256']
 op=pair['payload']['original_v74_pair'];assert sha(op['payload'])==op['payload_sha256'];pp=op['payload']
 assert pp['source_sha256']==source['payload']['native_source_sha256'] and pp['native_B1_arm_calls']==2
 assert pp['route']=='COMPLETE_ORACLE_WHOLE_B1_PAIR' and pp['architecture']==arch
 assert pp['whole_oracle_units']==sp['truth_evaluator_only']['Gamma_P_star'] and pp['cell_units']==[f'Decision_{t}' for t in times]
 assert pp['residual_units_preserved']==['ProcessCommit','ControllerSite_0_2_0_4','ControllerSite_1_2_1_4']
 full=expectedstates[2*j:2*j+2]
 for i,arm in enumerate(pp['all_owner_receipts']):
  ledger=ends[2*j+i]['ledger']
  assert arm['full_post_stores']==full[i] and json.loads(arm['ledger_canonical'])==ledger
  assert arm['ordered_receipts']==[r.rsplit('|',2)[:2]+[r.endswith('|1')] for r in ledger['receipts']]
 future=futures[name];assert sha(future['payload'])==future['payload_sha256'];fu=future['payload']
 assert fu['pair_sha256']==op['payload_sha256'] and fu['ordered_full_future_starts']==full
 template=fu['shared_template'];assert template['evaluation_units']==sample and template['grid']==list(range(466)) and template['T']==465
 assert template['alpha']==[1,2] and template['epsilon']==[1,10] and template['seed'] is None
 assert template['v_pre_hex']=='0x1.874538ef34d71p-1' and template['lock_sha256']==sp['lock_sha256']
 bank=banks[name];assert sha(bank['payload'])==bank['payload_sha256'];bp=bank['payload']
 assert bp['source_sha256']==source['payload_sha256'] and bp['pair_sha256']==pair['payload_sha256'] and bp['future_input_sha256']==future['payload_sha256']
 assert bp['shared_locked_template']==template and bp['source_configuration_not_reused_as_bank_faults']==cfg
 assert bp['route']=='COMPLETE_ORIGINAL_BANK' and bp['native_bank_rollout_calls']==200 and len(bp['ordered_arms'])==2
 assert bp['curve_created'] is False and bp['training_episodes']==0 and bp['primary_Collateral'] is None
 for i,(role,arm) in enumerate(zip(('reference','treatment'),bp['ordered_arms'])):
  idx=2*j+i;begin=begins[idx];end=completes[idx]
  assert begin['label']==end['label']==name and arm['role']==role and arm['full_start_stores']==full[i] and arm['fingerprint']==fingerprint(full[i])
  assert begin['sample']==sample and begin['pre']==end['post']==full[i] and end['rollout_end']==begin['rollout_offset']+100
  total=0.0;values=[]
  for n,(scene,wire) in enumerate(zip(sample,arm['ordered_scenes'])):
   native=byord[begin['rollout_offset']+1+n]
   assert wire['ordinal']==n and wire['scene']==scene==native['configuration']['scene'] and wire['raw']==native['raw']
   assert all(x is None for x in wire['faults'].values()) and wire['interventions']==native['actual_interventions']==[]
   assert all(x is None for x in native['configuration']['faults'].values())
   value,z=checkraw(wire['raw'],scene,full[i],[]);banksteps+=len(wire['raw'])
   assert wire['option_in_force']==native['option_in_force']==z==dict(full[i]['P']).get(scene[-1],scene[-1])
   assert wire['outcome']==native['outcome']==wire['raw'][-1]['outcome']
   assert value.hex()==wire['return_hex']==native['return_hex'];total+=value;values.append(value.hex())
  assert len(arm['ordered_scenes'])==100 and arm['original_ordered_mean_hex']==(total/100).hex()==end['mean_hex'] and end['ordered_returns']==values
  measured.append(total/100)
assert banksteps+24==3684
assert counts['TX_BEGIN']==counts['TX_END']==5 and counts['ORIGINAL_LAW_PLAN']==6
print(json.dumps({'audit_exit':0,'independence':'MAIN_AGENT_STDLIB_STORED_IMPLEMENTATION_ONLY_NO_RFL_IMPORT_OLD_FIXTURE_CHECKER_NATIVE',
 'inputs_current_full_bytes':2888,'input_bytes':totalbytes,'parent_git_blobs':2885,'canonical_complete_rows':675,
 'actual_extra_sources':2,'source_summaries':source_meta,'extensional_raw_and_truth_equal':True,
 'actual_owners':addresses,'actual_residuals':['ProcessCommit','ControllerSite_0_2_0_4','ControllerSite_1_2_1_4'],
 'original_pre_source_API_checks':12,'original_plans':6,'original_B1_full_owner_ledgers':6,
 'source_installation_transactions':2,'actual_treatment_transactions':3,'actual_transactions':5,
 'original_complete_patch_envelopes':2,'original_patch_validations':2,
 'full_future_roles':6,'native_bank_roles':6,'native_ordered_bank_rollouts':600,'complete_raw_rollouts':602,
 'complete_step_rows':3684,'actual_ordered_means':measured,'means_complete':6,
 'content_seals_and_order_complete':True,'runtime_identity_claim':'Child live assertions only, not reconstructed by stored bytes',
 'case_ids':ids,'native_child_exit':0,'no_scientific_PASS':True,'no_native_retry_or_audit_repair':True},ensure_ascii=False))
