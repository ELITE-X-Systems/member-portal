"""Build public ELITE X portal data from the private workbook.
The browser never calculates Bonds. The workbook remains the source of truth.
This builder supports the current workbook layout and the intended activity-log
reference layout, so blank/current records still produce a functional portal.
"""
import sys,json
from datetime import datetime,date
from openpyxl import load_workbook
if len(sys.argv)!=2: raise SystemExit('Usage: python scripts/build_data.py <private-workbook.xlsx>')
src=sys.argv[1]; wb=load_workbook(src,data_only=True)
reg,bond,att,ded,awards_sheet,arch,act,settings=[wb[s] for s in ['Member Registry','Bond Record','ATTENDANCE','Deductions','Awards & Achievements','Monthly Archive','Activity Log','Settings']]
ALLOWED_STATUS={'ACTIVE','ON LEAVE','INACTIVE','RESIGNED','REMOVED'}
ALLOWED_CAT={'MEDALLION','CREST','ACHIEVEMENT'}; TX={'DEDUCTION','SHOP PURCHASE'}
def text(v): return str(v).strip() if v is not None else ''
def num(v):
 try: return None if v in (None,'') else float(v)
 except: return None
def clean(v):
 n=num(v); return None if n is None else int(n) if n.is_integer() else n
def iso(v): return v.strftime('%Y-%m-%d') if isinstance(v,(datetime,date)) else text(v)
def norm(v): return text(v).upper()
# Activity Log is intentionally tolerant: intended public reference layout is A:F = ID, DATE, ACTIVITY NAME, TYPE, WEEK, # ENTRY.
# The uploaded workbook currently still has the older member-transaction layout A:J. We can read its activity metadata if present, but never use its Bonds to calculate Bond Record values.
activity_map={}
headers=[norm(act.cell(6,c).value) for c in range(1,act.max_column+1)]
if 'ACTIVITY NAME' in headers:
 def col(name): return headers.index(name)+1
 name_c=col('ACTIVITY NAME'); type_c=col('TYPE') if 'TYPE' in headers else None; week_c=col('WEEK') if 'WEEK' in headers else None; entry_c=col('# ENTRY') if '# ENTRY' in headers else None; date_c=col('DATE') if 'DATE' in headers else None
 for r in range(7,act.max_row+1):
  name=text(act.cell(r,name_c).value); week=text(act.cell(r,week_c).value) if week_c else ''; entry=num(act.cell(r,entry_c).value) if entry_c else None
  if not name or not week or entry is None: continue
  key=(norm(week),int(entry)); activity_map[key]={'name':name,'type':text(act.cell(r,type_c).value) if type_c else 'RECORDED ACTIVITY','date':iso(act.cell(r,date_c).value) if date_c else ''}
# Members and actual Bond Record entries. Detect week groups from merged/header cells rather than hardcoding a stale 3-week layout.
week_groups=[]; current=None
for c in range(4,bond.max_column+1):
 h=text(bond.cell(7,c).value)
 sub=text(bond.cell(8,c).value)
 if h.upper().startswith('WEEK '): current=h
 elif h: current=None
 elif current and sub.upper().startswith('ACTIVITY'):
  week_groups.append((current,c))
# unique group starts, up to calculated columns
seen=[]; groups=[]
for w,c in week_groups:
 if (w,c) not in seen: groups.append((w,c)); seen.append((w,c))
# fallback for conventional D:G/H:K/L:O/M... if headers are malformed
if not groups: groups=[('Week 1',4),('Week 2',8),('Week 3',12),('Week 4',16)]
members={}
# only activity cells before first non-week calculated header; current file has D:O, with P:R totals
for r in range(6,106):
 mid=norm(reg.cell(r,1).value); name=text(reg.cell(r,2).value)
 if not mid or not name: continue
 br=r+3; entries=[]
 for week,start in groups:
  for i in range(4):
   c=start+i
   if c>bond.max_column: break
   v=num(bond.cell(br,c).value)
   if v is None or v==0: continue
   key=(norm(week),i+1); meta=activity_map.get(key,{})
   entries.append({'week':week,'entry':i+1,'bonds':clean(v),'name':meta.get('name') or f'Activity {i+1}','type':meta.get('type') or 'RECORDED ACTIVITY','date':meta.get('date','')})
 # Attendance: current workbook uses C:V as 4 groups of 5 days and W as total Bonds.
 aw=att
 att_weeks=[]; perfect=0; present_total=0; required_total=0
 for wi,start in enumerate((3,8,13,18),1):
  vals=[norm(aw.cell(br,start+i).value) for i in range(5)]
  present=sum(v=='✓' for v in vals); required=5; isperfect=present==required; perfect+=int(isperfect); present_total+=present; required_total+=required
  labels=['ID CHECK','TUE','WED','THU','FRI']; att_weeks.append({'week':f'Week {wi}','presentDays':present,'requiredDays':required,'perfect':isperfect,'days':[{'label':labels[i],'present':vals[i]=='✓'} for i in range(5)]})
 att_bonds=clean(aw.cell(br,23).value) or 0
 attendance={'weeks':att_weeks,'perfectWeeks':perfect,'totalWeeks':4,'perfectChronicle':perfect==4,'bonus':att_bonds,'presentDays':present_total,'requiredDays':required_total}
 # Current Bond Record calculated columns are P/Q/R, status S. Use workbook cached values when present, but fallback to direct entry sums for blank/stale caches.
 entry_total=sum(num(a['bonds']) or 0 for a in entries)
 monthly=clean(bond.cell(br,16).value); deductions=clean(bond.cell(br,17).value); net=clean(bond.cell(br,18).value)
 if monthly is None: monthly=clean(entry_total+att_bonds)
 if deductions is None:
  deductions=sum(num(ded.cell(rr,7).value) or 0 for rr in range(7,207) if norm(ded.cell(rr,3).value)==mid and norm(ded.cell(rr,5).value)=='DEDUCTION')
  deductions=clean(deductions)
 if net is None: net=clean((num(monthly) or 0)-(num(deductions) or 0))
 shop=sum(num(ded.cell(rr,7).value) or 0 for rr in range(7,207) if norm(ded.cell(rr,3).value)==mid and norm(ded.cell(rr,5).value)=='SHOP PURCHASE')
 members[mid]={'id':mid,'name':name,'rank':text(reg.cell(r,3).value) or '—','status':norm(reg.cell(r,4).value) if norm(reg.cell(r,4).value) in ALLOWED_STATUS else '', 'joinDate':iso(reg.cell(r,5).value),'crests':int(num(reg.cell(r,6).value) or 0),'medallion':int(num(reg.cell(r,7).value) or 0),'monthlyEarned':monthly,'deductions':deductions,'overallNet':net,'shopSpending':clean(shop),'weeklyEntries':entries,'attendance':attendance}
# Transactions, public-safe fields only.
transactions=[]
for r in range(7,207):
 mid=norm(ded.cell(r,3).value); typ=norm(ded.cell(r,5).value); amount=num(ded.cell(r,7).value)
 if mid not in members or typ not in TX or amount is None: continue
 transactions.append({'memberId':mid,'date':iso(ded.cell(r,2).value),'type':typ,'description':text(ded.cell(r,6).value),'amount':clean(amount)})
# Historical archive.
monthly={}
for r in range(6,106):
 mid=norm(arch.cell(r,1).value)
 if mid in members:
  monthly[mid]={text(arch.cell(5,c).value).title():clean(arch.cell(r,c).value) for c in range(3,7) if text(arch.cell(5,c).value)}
# Earned awards only, with no notes/recorder data.
awards=[]
for r in range(7,207):
 mid=norm(awards_sheet.cell(r,3).value); cat=norm(awards_sheet.cell(r,5).value); status=norm(awards_sheet.cell(r,7).value); name=text(awards_sheet.cell(r,6).value)
 if mid in members and cat in ALLOWED_CAT and status=='EARNED' and name: awards.append({'memberId':mid,'date':iso(awards_sheet.cell(r,2).value),'category':cat,'name':name,'status':'EARNED'})
# Public rules are reference only. They never recalculate records in the browser.
guidelines=[{'label':'ATTENDANCE','value':'2 Bonds','detail':'Per attendance · Tuesday–Friday'},{'label':'ID INSPECTION','value':'5 Bonds','detail':'Per ID check · Monday'},{'label':'GAMBIT','value':'+5–10 Bonds','detail':'Maximum 30 per chronicle'},{'label':'CONQUEST','value':'+15–20 Bonds','detail':'Maximum 50 per chronicle'},{'label':'COMMISSION','value':'+20–30 Bonds','detail':'Maximum 50 per chronicle'},{'label':'WEEKLY LIMIT','value':'100 Bonds','detail':'Maximum earned per member per week'}]
out={'version':'2.0','currency':'BONDS 💴','source':'ELITE X Private Staff Records','generatedAt':date.today().isoformat(),'members':list(members.values()),'transactions':transactions,'awards':awards,'monthlyArchive':monthly,'bondGuidelines':guidelines,'activityLog':activity_map}
with open('data.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
print(f'Wrote data.json · members={len(members)} awards={len(awards)}')
   
