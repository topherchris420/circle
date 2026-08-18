"""Run the reproducible CIRCLE engineering-review verification suite."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KICAD=Path(os.environ.get("KICAD_CLI",Path.home()/"AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe"))
def run(command):
    start=time.perf_counter(); result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True); elapsed=round(time.perf_counter()-start,3)
    print("$"," ".join(map(str,command))); print(result.stdout,end=""); print(result.stderr,end="",file=sys.stderr)
    return {"command":list(map(str,command)),"exit_code":result.returncode,"elapsed_seconds":elapsed}
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    py=sys.executable; k=str(KICAD); steps=[]
    commands=[[py,"-m","unittest","discover","-s","tests"],[py,"tools/check_design_manifest.py"],[py,"tools/check_record_schema.py"],[py,"tools/render_diagrams.py"],[py,"tools/generate_schematics.py"],[py,"tools/generate_schematics.py","--board","circle-ppg"],[k,"version"],[k,"sch","erc","--format","json","--severity-all","--output","hardware/reports/circle-main-erc.json","hardware/circle-main/legacy/00_root.sch"],[k,"sch","erc","--format","json","--severity-all","--output","hardware/reports/circle-ppg-erc.json","hardware/circle-ppg/legacy/00_ppg_root.sch"],[py,"tools/check_erc.py"]]
    for command in commands:
        result=run(command); steps.append(result)
        if result["exit_code"]: break
    disallowed=[]
    pattern=re.compile(r"\b(TODO|TBD|PLACEHOLDER)\b")
    for path in list((ROOT/"hardware").rglob("*.json"))+list((ROOT/"docs").rglob("*.md")):
        if pattern.search(path.read_text(encoding="utf-8",errors="ignore")): disallowed.append(str(path.relative_to(ROOT)))
    artifacts=[]
    patterns=["docs/superpowers/specs/*.md","hardware/*.json","hardware/circle-main/legacy/00_root.sch","hardware/circle-ppg/legacy/00_ppg_root.sch","hardware/reports/*-erc.json","hardware/reports/bom/*.csv","hardware/reports/pdf/*.pdf"]
    for pattern_glob in patterns:
        for path in sorted(ROOT.glob(pattern_glob)): artifacts.append({"path":str(path.relative_to(ROOT)),"sha256":digest(path)})
    ok=all(s["exit_code"]==0 for s in steps) and not disallowed
    summary={"verified":ok,"release_class":"ENGINEERING_REVIEW_ONLY","steps":steps,"artifacts":artifacts,"disallowed_placeholders":disallowed,"limitations":["KiCad 10 CLI parses, ERC-checks, and exports legacy sources but does not import legacy .sch into native .kicad_sch.","ERC validates parser-visible structure; architecture-level NET annotations do not constitute fabrication-ready electrical connectivity.","No fabrication, powered-electrode, human, EMC, or regulatory validation performed."]}
    out=ROOT/"hardware/reports/verification-summary.json"; out.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8",newline="\n")
    if ok: print("CIRCLE Rev B review package: VERIFIED")
    else: print("CIRCLE Rev B review package: FAILED")
    return int(not ok)
if __name__=="__main__": raise SystemExit(main())
