#!/usr/bin/env python3
import argparse,base64,csv,datetime,json,re,sys
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('html');ap.add_argument('--out');ap.add_argument('--c04');ap.add_argument('--bulletin')
for k in('ntal','ntol','hydl','slel'):ap.add_argument('--'+k)
a=ap.parse_args();out=a.out or a.html
s=open(a.html,encoding='utf-8').read()
def mjd_of(t):return (datetime.datetime.strptime(t,'%Y-%m-%dT%H:%M:%SZ')-datetime.datetime(1858,11,17)).total_seconds()/86400
def date_of(m):return (datetime.datetime(1858,11,17)+datetime.timedelta(days=float(m))).strftime('%Y-%m-%d')
# ---------------- EOP ----------------
if a.c04 or a.bulletin:
    m=re.search(r'"eop":(\[\[.*?\]\]),"c04":(\d+),"pr":(\d+)',s,re.S);assert m,'EOP block not found'
    old={int(r[0]):r for r in json.loads(m.group(1))};c04={};rap={};pred={};dxy={};issue=''
    if a.c04:
        for ln in open(a.c04):
            f=ln.split()
            if len(f)>=13 and f[0].isdigit() and len(f[0])==4:c04[int(float(f[4]))]=[float(f[7]),float(f[5]),float(f[6]),float(f[8]),float(f[9]),float(f[12])]
        assert c04,'no C04 rows'
    else:c04={int(k):[r[1],r[2],r[3],r[4],r[5],r[6]] for k,r in old.items() if k<=int(m.group(2))}
    c04_last=max(c04)
    if a.bulletin:
        txt=open(a.bulletin).read();mm=re.search(r'(\d+ \w+ \d{4})\s+Vol\. (\S+) No\. (\d+)',txt);issue='%s, Vol. %s No. %s'%mm.groups() if mm else ''
        for ln in txt.split('\n'):
            r=re.match(r'^\s+\d\d\s+\d+\s+\d+\s+(\d{5})\s+(-?[\d.]+)\s+[\d.]+\s+(-?[\d.]+)\s+[\d.]+\s+(-?[\d.]+)\s+[\d.]+\s*$',ln)
            if r:rap[int(r.group(1))]=[float(r.group(4)),float(r.group(2)),float(r.group(3))]
            r=re.match(r'^\s+\d{4}\s+\d+\s+\d+\s+(\d{5})\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$',ln)
            if r:pred[int(r.group(1))]=[float(r.group(4)),float(r.group(2)),float(r.group(3))]
        i=txt.find('IAU2000A Celestial Pole Offset');assert i>0,'dX,dY table not found'
        for ln in txt[i:].split('\n'):
            r=re.match(r'^\s+(\d{5})\s+(-?[\d.]+)\s+[\d.]+\s+(-?[\d.]+)\s+[\d.]+\s*$',ln)
            if r:dxy[int(r.group(1))]=[float(r.group(2))/1e3,float(r.group(3))/1e3]
        assert rap and pred and dxy,'Bulletin A tables not parsed'
    ser={}
    for k,v in c04.items():ser[k]=v
    first_b=min(list(rap)+list(pred)) if a.bulletin else None
    if a.bulletin:
        for k in range(c04_last+1,first_b):
            assert k in old,'gap MJD %d between C04 and Bulletin A is not in the old table: add finals2000A or the previous Bulletin A'%k
            ser[k]=[old[k][1],old[k][2],old[k][3],old[k][4],old[k][5],old[k][6]]
        prev=None
        for k in sorted(set(rap)|set(pred)):
            u,x,y=(rap.get(k) or pred.get(k));p=ser[k-1][0];ser[k]=[u,x,y,0,0,round(-(u-p),7)]
        dlast=max(dxy);d0=min(dxy)
        for k in sorted(ser):
            if k<=c04_last:continue
            if k<d0:f=(k-c04_last)/(d0-c04_last);ser[k][3]=ser[c04_last][3]+f*(dxy[d0][0]-ser[c04_last][3]);ser[k][4]=ser[c04_last][4]+f*(dxy[d0][1]-ser[c04_last][4])
            else:v=dxy[min(k,dlast)];ser[k][3],ser[k][4]=v
        fcn=max(dxy);pr=max(rap);last=max(ser)
    else:
        fcn=None;pr=int(m.group(3));last=max(ser)
    rows=[[float(k)]+[round(x,7) for x in ser[k]] for k in sorted(ser) if k>=51544]
    assert all(rows[i+1][0]-rows[i][0]==1 for i in range(len(rows)-1)),'EOP table must be daily and gap-free'
    s=s[:m.start()]+'"eop":'+json.dumps(rows,separators=(',',':'))+',"c04":%d,"pr":%d'%(c04_last,pr)+s[m.end():]
    if fcn:
        s,n=re.subn(r'const FCN_T0=\d+','const FCN_T0=%d'%fcn,s);assert n==1
        s,n=re.subn(r'last tabulated dX,dY \(MJD \d+\)','last tabulated dX,dY (MJD %d)'%fcn,s);assert n==1
    s,n=re.subn(r'beyond MJD \d+ \(\d{4}-\d\d-\d\d\) the table edge is held','beyond MJD %d (%s) the table edge is held'%(last,date_of(last)),s);assert n==1
    print('EOP: C04 to MJD %d (%s), Bulletin A %s: rapid to %d, predictions to %d (%s); FCN_T0 %s'%(c04_last,date_of(c04_last),issue,pr,last,date_of(last),fcn))
# ---------------- ESMGFZ loading ----------------
files={k:getattr(a,k) for k in('ntal','ntol','hydl','slel') if getattr(a,k)}
if files:
    m=re.search(r'const NTD=(\{.*?\});\n',s,re.S);assert m,'NTD block not found';NT=json.loads(m.group(1));ends=[]
    for k,f in files.items():
        o=NT[k];old=np.frombuffer(base64.b64decode(o['b']),dtype='<f4').reshape(-1,3).copy()
        rows=list(csv.reader(open(f)));h=rows[0];cols=[i for i,c in enumerate(h) if c.startswith(('duEW','duNS','duV'))];assert len(cols)==3,'columns duEW, duNS, duV expected'
        t=np.array([mjd_of(r[0]) for r in rows[1:]]);v=np.array([[float(r[i]) for i in cols] for r in rows[1:]])
        idx=np.round((t-o['t0'])/o['dt']).astype(int);assert np.allclose(t,o['t0']+o['dt']*idx,atol=1e-6),'CSV times are not on the embedded grid'
        ov=(idx>=0)&(idx<len(old));d=np.abs(old[idx[ov]]-v[ov]).max() if ov.any() else 0.
        new=idx>=len(old);order=np.argsort(idx[new]);ii=idx[new][order];vv=v[new][order]
        if len(ii):assert ii[0]==len(old) and np.all(np.diff(ii)==1),'%s: new samples are not contiguous with the embedded series (gap)'%k
        arr=np.vstack([old,vv.astype('<f4')]) if len(ii) else old
        o['n']=len(arr);o['b']=base64.b64encode(arr.astype('<f4').tobytes()).decode();ends.append(o['t0']+o['dt']*(o['n']-1))
        print('%s: +%d samples, now to MJD %.3f (%s); max |embedded - new CSV| over %d overlapping samples = %.2e m%s'%(k.upper(),len(ii),ends[-1],date_of(ends[-1]),ov.sum(),d,'  <-- REVISED DATA: regenerate the audit reference rows' if d>1e-6 else ''))
    s=s[:m.start()]+'const NTD='+json.dumps(NT,separators=(',',':'))+';\n'+s[m.end():]
    last_end=max(o['t0']+o['dt']*(o['n']-1) for o in NT.values())
    s,n=re.subn(r'2024-01-01 to \d{4}-\d\d-\d\d, each interpolated','2024-01-01 to %s, each interpolated'%date_of(last_end),s);assert n==1
open(out,'w',encoding='utf-8').write(s);print('written',out)