"""One reproducible command: python -m strategy_lab experiment --help."""
import argparse
import json
import sys
from pathlib import Path
from .catalog import ROOT, catalog, discover
from .experiment import DATA, create_job, pause, run, status, write_report


def main():
    if sys.stdout is not None and hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Strategy Lab — offline eksperimenti bez igre i klikova")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gui")
    sub.add_parser("catalog")
    disc = sub.add_parser("discover"); disc.add_argument("--day")
    exp = sub.add_parser("experiment")
    exp.add_argument("--job",type=Path,default=DATA / "experiment.sqlite")
    exp.add_argument("--runs",type=Path,default=ROOT / "Debug" / "runs")
    exp.add_argument("--day")
    exp.add_argument("--mode",action="append",default=[])
    exp.add_argument("--format",action="append",default=[])
    exp.add_argument("--seed",type=int,default=1729)
    exp.add_argument("--limit",type=int,default=120,help="Najviše jedinstvenih tabli po modu")
    exp.add_argument("--detail",choices=("quick","detailed"),default="quick")
    for name in ("resume","pause","status","report"):
        cmd=sub.add_parser(name);cmd.add_argument("job",type=Path)
    args=parser.parse_args()
    if args.command=="gui":
        from .ui import show
        show(); return
    if args.command=="catalog": result=catalog()
    elif args.command=="discover": result=discover(ROOT / "Debug" / "runs",args.day)
    elif args.command=="experiment":
        if args.limit<1: parser.error("--limit mora biti pozitivan")
        create_job(args.job,runs=args.runs,day=args.day,modes=args.mode,formats=args.format,
                   seed=args.seed,limit=args.limit,detail=args.detail)
        result=run(args.job)
    elif args.command=="resume": result=run(args.job)
    elif args.command=="pause": pause(args.job); result=status(args.job)
    elif args.command=="status": result=status(args.job)
    else: result=write_report(args.job)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
