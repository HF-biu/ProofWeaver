import argparse
import json
from pathlib import Path

from .config import AppConfig
from .datasets import load_examples
from .engine import FormalMathAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Lean-grounded formal mathematics agent")
    commands = parser.add_subparsers(dest="command", required=True)
    solve = commands.add_parser("solve")
    solve.add_argument("--config", required=True)
    solve.add_argument("--problem", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--config", required=True)
    inspect.add_argument("--problem", required=True)
    inspect.add_argument("--derivation", required=True)
    bench = commands.add_parser("bench")
    bench.add_argument("--config", required=True)
    bench.add_argument("--dataset", required=True)
    bench.add_argument("--input", required=True)
    bench.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    config = AppConfig.from_file(args.config)
    if args.command == "solve":
        print(json.dumps(FormalMathAgent(config, args.config).solve(args.problem).to_dict(), ensure_ascii=False, indent=2))
        return
    if args.command == "inspect":
        print(json.dumps(FormalMathAgent(config, args.config).inspect(args.problem, args.derivation).to_dict(), ensure_ascii=False, indent=2))
        return
    rows = []
    for index, item in enumerate(load_examples(args.input, args.limit), 1):
        outcome = FormalMathAgent(config, args.config).solve(item["problem"])
        rows.append({"index": index, "expected": item["expected"], "status": outcome.status, "run": outcome.task_id})
    destination = Path(args.config).resolve().parent / "runs" / (args.dataset + "_summary.json")
    destination.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote {} rows to {}".format(len(rows), destination))


if __name__ == "__main__":
    main()
