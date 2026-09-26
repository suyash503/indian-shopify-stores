"""Turn the stage outputs into the deliverables: stores.csv, stores.json and
report.md (the funnel, field coverage and where each field came from)."""
import csv
import json
from collections import Counter
from pathlib import Path

from .pipeline import latest_records, read_jsonl
from .sources import read_candidates

NETWORKS = ["instagram", "facebook", "twitter", "linkedin", "youtube"]
CSV_COLUMNS = [
    "domain", "name", "emails", "phones", *NETWORKS, "category", "tagline", "logo", "state",
    "city", "myshopify_domain", "currency", "india_evidence", "state_source", "found_via",
]


def final_stores(stores):
    """Indian stores only, one row per shop and per domain."""
    keep, seen_ids, seen_domains = [], set(), set()
    for s in stores:
        if s.get("error") or not s.get("is_indian"):
            continue
        domain = (s.get("domain") or "").lower().removeprefix("www.")
        if s.get("shop_id") in seen_ids or domain in seen_domains:
            continue
        seen_ids.add(s.get("shop_id"))
        seen_domains.add(domain)
        keep.append(s)
    return sorted(keep, key=lambda s: s["domain"].lower().removeprefix("www."))


def to_output(s):
    return {
        "domain": s["domain"],
        "name": s.get("name"),
        "emails": s.get("emails", []),
        "phones": s.get("phones", []),
        "socials": s.get("socials", {}),
        "category": s.get("category"),
        "tagline": s.get("tagline"),
        "logo": s.get("logo"),
        "state": s.get("state"),
        "city": s.get("city"),
        "myshopify_domain": s.get("myshopify_domain"),
        "currency": s.get("currency"),
        "india_evidence": s.get("india_evidence", []),
        "state_source": s.get("state_source"),
        "logo_source": s.get("logo_source"),
        "tagline_source": s.get("tagline_source"),
        "found_via": (s.get("source") or "").split(":")[0],
    }


def write_outputs(data_dir, out_dir):
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stores = read_jsonl(data_dir / "stores.jsonl")
    rows = [to_output(s) for s in final_stores(stores)]

    with open(out_dir / "stores.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
        f.write("\n")

    with open(out_dir / "stores.csv", "w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel reads ₹ and Hindi right
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            flat.update({n: row["socials"].get(n, "") for n in NETWORKS})
            for key in ("emails", "phones", "india_evidence"):
                flat[key] = "; ".join(row[key])
            writer.writerow(flat)

    report = build_report(data_dir, stores, rows)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    return rows


def build_report(data_dir, stores, rows):
    candidates = read_candidates(data_dir / "candidates.csv")
    verified = latest_records(data_dir / "verified.jsonl")
    total = len(rows) or 1
    lines = ["# Run report", ""]

    # funnel
    by_source = Counter(src.split(":")[0] for _, src in candidates)
    checked = Counter(r["source"].split(":")[0] for r in verified if "source" in r)
    shopify = Counter(r["source"].split(":")[0] for r in verified if r.get("shopify"))
    first = Counter(r.get("india") for r in verified if r.get("shopify"))
    enriched = [s for s in stores if not s.get("error")]
    lines += [
        "## Funnel", "",
        "| step | count |", "|---|---:|",
        *[f"| candidates from {src} | {n:,} |" for src, n in by_source.most_common()],
        *[f"| checked from {src} | {checked[src]:,} |" for src in by_source if checked[src]],
        *[f"| confirmed Shopify (meta.json) from {src} | {shopify[src]:,} |" for src in by_source if checked[src]],
        f"| first pass: Shopify address in India | {first['yes']:,} |",
        f"| first pass: maybe (INR or .in, address elsewhere) | {first['maybe']:,} |",
        f"| first pass: not Indian | {first['no']:,} |",
        f"| unique shops enriched | {len(stores):,} |",
        f"| homepage failed during enrich | {len(stores) - len(enriched):,} |",
        f"| \"maybe\" stores confirmed Indian from the site | {sum(1 for s in enriched if s.get('is_indian') and 'Shopify business address in India' not in s.get('india_evidence', [])):,} |",
        f"| \"maybe\" stores rejected | {sum(1 for s in enriched if not s.get('is_indian')):,} |",
        f"| **final Indian stores** | **{len(rows):,}** |",
        "",
    ]

    reasons = Counter(_reason_bucket(r.get("reason", "")) for r in verified if not r.get("shopify"))
    lines += ["## Why candidates were dropped", "", "| reason | count |", "|---|---:|"]
    lines += [f"| {reason} | {n:,} |" for reason, n in reasons.most_common(12)] + [""]

    # field coverage
    def filled(key):
        return sum(1 for r in rows if r.get(key))

    coverage = [
        ("domain", filled("domain")),
        ("at least one email", filled("emails")),
        ("at least one phone", filled("phones")),
        ("email or phone", sum(1 for r in rows if r["emails"] or r["phones"])),
        ("at least one social", sum(1 for r in rows if r["socials"])),
        *[(f"  {n}", sum(1 for r in rows if n in r["socials"])) for n in NETWORKS],
        ("category", filled("category")),
        ("tagline", filled("tagline")),
        ("logo", filled("logo")),
        ("state", filled("state")),
    ]
    lines += ["## Field coverage", "", "| field | filled | missing | filled % |", "|---|---:|---:|---:|"]
    lines += [f"| {name} | {n:,} | {len(rows) - n:,} | {100 * n / total:.1f}% |" for name, n in coverage] + [""]

    for key, title in (("state_source", "state"), ("logo_source", "logo"), ("tagline_source", "tagline")):
        counts = Counter(r.get(key) or "missing" for r in rows)
        lines += [f"## Where the {title} came from", "", "| source | stores |", "|---|---:|"]
        lines += [f"| {k} | {v:,} |" for k, v in counts.most_common()] + [""]

    for key, title in (("category", "Categories"), ("state", "States")):
        counts = Counter(r.get(key) or "unknown" for r in rows)
        lines += [f"## {title}", "", "| value | stores |", "|---|---:|"]
        lines += [f"| {k} | {v:,} |" for k, v in counts.most_common(40)] + [""]

    found_via = Counter(r["found_via"] for r in rows)
    lines += ["## Final stores by source", "", "| source | stores |", "|---|---:|"]
    lines += [f"| {k} | {v:,} |" for k, v in found_via.most_common()] + [""]
    return "\n".join(lines)


def _reason_bucket(reason):
    if reason.startswith("meta.json returned"):
        return reason
    return reason or "unknown"
