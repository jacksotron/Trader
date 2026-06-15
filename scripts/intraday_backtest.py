import json, datetime, statistics
SLIP=0.0005
import sys, os
DATA=sys.argv[1] if len(sys.argv)>1 else 'data'
def load(s):
    j=json.load(open(os.path.join(DATA, f'intra_{s}.json')))
    r=j['chart']['result'][0]; ts=r['timestamp']; q=r['indicators']['quote'][0]
    bars=[]
    for i,t in enumerate(ts):
        o,h,l,c=q['open'][i],q['high'][i],q['low'][i],q['close'][i]
        if None in (o,h,l,c): continue
        dt=datetime.datetime.fromtimestamp(t,datetime.timezone.utc)
        mins=dt.hour*60+dt.minute
        if mins<810 or mins>=1200: continue   # 13:30-20:00 UTC = regular session
        bars.append({'date':dt.strftime('%Y-%m-%d'),'mins':mins,'o':o,'h':h,'l':l,'c':c})
    return bars
def maxdd(curve):
    peak=-1e9; dd=0
    for e in curve:
        peak=max(peak,e); dd=max(dd,(peak-e)/peak*100 if peak>0 else 0)
    return dd
def run(s, gated=True):
    bars=load(s); days={}
    for b in bars: days.setdefault(b['date'],[]).append(b)
    dates=sorted(days); equity=100.0; curve=[100.0]; trades=[]; prior_close=None
    OR_END=840; ENTRY_CUT=1170   # OR thru 10:00 ET; entries until 15:30 ET
    for d in dates:
        day=sorted(days[d],key=lambda x:x['mins'])
        orb=[b for b in day if b['mins']<OR_END]
        if len(orb)<3: prior_close=day[-1]['c']; continue
        or_high=max(b['h'] for b in orb); or_low=min(b['l'] for b in orb)
        day_open=orb[0]['o']
        gap_up = prior_close is not None and day_open>=prior_close
        or_up = orb[-1]['c']>orb[0]['o']
        take = (gap_up and or_up) if gated else True
        entered=False; entry=stop=exitp=None
        if take:
            for b in day:
                if b['mins']<OR_END or b['mins']>ENTRY_CUT: continue
                if not entered and b['c']>or_high:
                    entry=b['c']*(1+SLIP); stop=or_low; entered=True; continue
                if entered and b['l']<=stop:
                    exitp=stop*(1-SLIP); break
            if entered and exitp is None: exitp=day[-1]['c']*(1-SLIP)
        if entered:
            r=exitp/entry-1; equity*=(1+r); curve.append(equity); trades.append(r)
        prior_close=day[-1]['c']
    bh=bars[-1]['c']/bars[0]['o']-1
    wins=[t for t in trades if t>0]
    return {'sym':s,'gate':'optimal' if gated else 'every-day','days':len(dates),
        'trades':len(trades),'traded%':round(len(trades)/len(dates)*100),
        'win%':round(len(wins)/len(trades)*100,1) if trades else 0,
        'avgTrade%':round(statistics.mean(trades)*100,3) if trades else 0,
        'totRet%':round((equity-1)*100,1),'maxDD%':round(maxdd(curve),1),
        'buyhold%':round(bh*100,1)}
hdr=f"{'sym':<5}{'gate':<11}{'days':>5}{'trds':>5}{'trd%':>5}{'win%':>6}{'avgTr%':>8}{'totRet%':>9}{'maxDD%':>8}{'buyhold%':>9}"
print(hdr); print('-'*len(hdr))
for s in ['SPY','QQQ','TQQQ']:
    for g in (True,False):
        r=run(s,g)
        print(f"{r['sym']:<5}{r['gate']:<11}{r['days']:>5}{r['trades']:>5}{r['traded%']:>5}{r['win%']:>6}{r['avgTrade%']:>8}{r['totRet%']:>9}{r['maxDD%']:>8}{r['buyhold%']:>9}")
