import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from . import sources
from .fetch import Fetcher

DATA = Path("data")
CACHE = Path(".cache")


def cmd_candidates(args):
    fetcher = Fetcher(rate=args.rate, cache_dir=CACHE / "http")
    candidates, meta = sources.collect(
        fetcher, CACHE, crawls=args.crawls, seed_files=args.seeds, use_tranco=not args.no_tranco
    )
    sources.write_candidates(DATA / "candidates.csv", candidates)
    meta["counts"] = Counter(src.split(":")[0] for src in candidates.values())
    (DATA / "sources.json").write_text(json.dumps(meta, indent=2) + "\n")
    logging.info("wrote %d candidates to %s", len(candidates), DATA / "candidates.csv")


def main():
    parser = argparse.ArgumentParser(prog="python -m shopify_india")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--rate", type=float, default=8.0, help="max requests per second, all threads combined")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("candidates", help="collect candidate domains")
    p.add_argument("--crawls", type=int, default=3, help="how many recent Common Crawl crawls to read (0 = skip)")
    p.add_argument("--seeds", nargs="*", default=[], help="extra files with one domain per line")
    p.add_argument("--no-tranco", action="store_true")
    p.set_defaults(func=cmd_candidates)

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    args.func(args)


if __name__ == "__main__":
    main()
