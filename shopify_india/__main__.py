import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from . import export, pipeline, sources
from .fetch import Fetcher

DATA = Path("data")
OUTPUT = Path("output")
CACHE = Path(".cache")


def make_fetcher(args):
    return Fetcher(rate=args.rate, cache_dir=CACHE / "http")


def cmd_candidates(args):
    fetcher = make_fetcher(args)
    candidates, meta = sources.collect(
        fetcher, CACHE, crawls=args.crawls, seed_files=args.seeds, use_tranco=not args.no_tranco
    )
    sources.write_candidates(DATA / "candidates.csv", candidates)
    meta["counts"] = Counter(src.split(":")[0] for src in candidates.values())
    (DATA / "sources.json").write_text(json.dumps(meta, indent=2) + "\n")
    logging.info("wrote %d candidates to %s", len(candidates), DATA / "candidates.csv")


def cmd_verify(args):
    fetcher = make_fetcher(args)
    candidates = sources.read_candidates(DATA / "candidates.csv")
    if args.limit:
        candidates = candidates[: args.limit]
    pipeline.verify(fetcher, candidates, DATA / "verified.jsonl", workers=args.workers, target=args.target)
    logging.info("http: %s", dict(fetcher.stats))


def cmd_recheck(args):
    fetcher = make_fetcher(args)
    pipeline.recheck_dns_misses(fetcher, DATA / "verified.jsonl", workers=args.workers)
    logging.info("http: %s", dict(fetcher.stats))


def cmd_enrich(args):
    fetcher = make_fetcher(args)
    if args.redo:
        (DATA / "stores.jsonl").unlink(missing_ok=True)
    pipeline.enrich(
        fetcher, DATA / "verified.jsonl", DATA / "stores.jsonl", workers=args.workers, logo_dir=OUTPUT / "logos"
    )
    logging.info("http: %s", dict(fetcher.stats))


def cmd_export(args):
    rows = export.write_outputs(DATA, OUTPUT)
    logging.info("wrote %d stores to %s (stores.csv, stores.json, report.md)", len(rows), OUTPUT)


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

    p = sub.add_parser("verify", help="check which candidates are live Shopify stores, and which look Indian")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--limit", type=int, help="only look at the first N candidates")
    p.add_argument("--target", type=int, help="stop once this many Indian stores are found")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("recheck", help="ask domains whose DNS isn't Shopify's for meta.json anyway (stores behind a CDN)")
    p.add_argument("--workers", type=int, default=16)
    p.set_defaults(func=cmd_recheck)

    p = sub.add_parser("enrich", help="fetch contact details, socials, logo etc. for the Indian stores")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--redo", action="store_true", help="start over; pages come from the cache, so it's quick")
    p.set_defaults(func=cmd_enrich)

    p = sub.add_parser("export", help="write output/stores.csv, stores.json and report.md")
    p.set_defaults(func=cmd_export)

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
