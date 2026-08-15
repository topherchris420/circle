"""Gate KiCad ERC reports; this is not an electrical-safety certification."""
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORTS={"circle-main":ROOT/"hardware/reports/circle-main-erc.json","circle-ppg":ROOT/"hardware/reports/circle-ppg-erc.json"}
ALLOW=ROOT/"hardware/reports/erc-allowlist.json"
def fingerprint(sheet,violation):
    material=json.dumps({"sheet":sheet,"type":violation.get("type"),"description":violation.get("description"),"items":[i.get("description") for i in violation.get("items",[])]},sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()
def main():
    allow=json.loads(ALLOW.read_text(encoding="utf-8")).get("allowlist",[]); allowed={a["fingerprint"]:a for a in allow}; used=set(); errors=[]
    for name,path in REPORTS.items():
        data=json.loads(path.read_text(encoding="utf-8")); violations=[(s["path"],v) for s in data.get("sheets",[]) for v in s.get("violations",[])]
        for sheet,v in violations:
            fp=fingerprint(sheet,v)
            if v.get("severity")=="error": errors.append(f"{name}:{sheet}: error: {v.get('description')}")
            elif fp not in allowed: errors.append(f"{name}:{sheet}: unallowlisted warning: {v.get('description')}")
            else:
                used.add(fp)
                if len(allowed[fp].get("rationale",""))<20: errors.append(f"{name}: short rationale: {fp}")
        print(f"{name}: {len(violations)} ERC items")
    for fp in set(allowed)-used: errors.append(f"stale allowlist entry: {fp}")
    for error in errors: print("ERROR:",error)
    if not errors: print("ERC gate: OK")
    return int(bool(errors))
if __name__=="__main__": raise SystemExit(main())
