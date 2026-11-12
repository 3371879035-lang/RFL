"""Singleton-only source-transcribed predictor. No RFL, solver or randomness."""
DELTAS=((0,-1),(0,1),(-1,0),(1,0),(0,0))
OPEN={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}


def predict(qrows, basis, architecture=None, address=None, target=None):
    kappa,phi,z=basis;x,y,t,m=0,2,0,0;trace=[];gamma=[]
    while t<12:
        s=[x,y,t,kappa,phi];context=tuple(s+[z,m]);q=qrows[context]
        cmd=max(q,key=lambda a:(q[a],-a))
        if architecture=='D' and context==tuple(address):cmd=target
        u=target if architecture=='X' and tuple(s+[cmd])==tuple(address) else cmd
        if cmd not in [a for a,v in q.items() if v>=max(q.values())-1e-12]:gamma.append('Decision_'+str(t))
        if u!=cmd:gamma.append(f'ControllerSite_{x}_{y}_{t}_{cmd}')
        dx,dy=DELTAS[u];nx,ny=x+dx,y+dy
        if (nx,ny) not in OPEN:nx,ny=x,y
        nt=t+1;outcome=None
        if (nx,ny)==(2,2) and nt%(6 if kappa==0 else 3)==phi%(6 if kappa==0 else 3):outcome='COLLISION'
        elif (nx,ny)==(4,2):outcome='SUCCESS'
        elif nt>=12:outcome='TIMEOUT'
        nm=m
        if m==0 and ((z==1 and (nx,ny)==(2,1)) or (z==3 and (nx,ny)==(2,4))
                     or (z==2 and (x,y)==(1,2) and t%(6 if kappa==0 else 3)!=phi%(6 if kappa==0 else 3))):nm=1
        reward=-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)
        trace.append({'pre_state':s,'z':z,'m':m,'a_cmd':cmd,'u':u,'a_realized':u,
                      'reward_hex':reward.hex(),'post_state':[nx,ny,nt,kappa,phi],'post_control':[z,nm],
                      'terminal':outcome is not None,'outcome':outcome,'illegal':False})
        x,y,t,m=nx,ny,nt,nm
        if outcome:break
    return {'trace':trace,'outcome':trace[-1]['outcome'],
            'return_hex':float(sum(float.fromhex(r['reward_hex']) for r in trace)).hex(),
            'Gamma_P_star':gamma}
