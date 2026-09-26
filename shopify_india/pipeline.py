"""The two network-heavy stages.

verify: candidate domain -> is it a live Shopify store, and is it Indian (first pass)?
enrich: Indian (or maybe-Indian) store -> contacts, socials, category, tagline, logo, state.

Both stages append one JSON line per item as they go, so a run that dies halfway
(or a flaky connection) just picks up where it stopped next time.
"""
import json
import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from . import category, india, shopify
from .extract import parse_page, pick_socials

log = logging.getLogger(__name__)

META_FIELDS = {
    "id": "shop_id", "domain": "domain", "url": "url", "myshopify_domain": "myshopify_domain",
    "name": "name", "city": "city", "province": "province", "country": "country", "currency": "currency",
    "description": "description", "ships_to_countries": "ships_to", "published_products_count": "products",
}
MAX_CONTACTS = 6


# plumbing --------------------------------------------------------------------------

def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_parallel(items, work, workers, handle, stop=lambda: False):
    """Like pool.map, but results are handled as they finish (in this thread,
    so writing files needs no locks) and we can stop early."""
    items = iter(items)
    with ThreadPoolExecutor(workers) as pool:
        pending = set()
        while True:
            while len(pending) < workers * 2 and not stop():
                item = next(items, None)
                if item is None:
                    break
                pending.add(pool.submit(_safe, work, item))
            if not pending:
                break
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                handle(future.result())


def _safe(work, item):
    try:
        return work(item)
    except Exception as exc:  # one weird page shouldn't kill a two-hour run
        log.exception("failed on %s", item)
        return {"item": str(item), "error": f"{type(exc).__name__}: {exc}"}


# verify ------------------------------------------------------------------------------

def verify_one(fetcher, candidate):
    domain, source = candidate
    check, dns = shopify.verify(fetcher, domain)
    rec = {"candidate": domain, "source": source, "dns": dns, "shopify": check.is_shopify, "reason": check.reason}
    if check.is_shopify:
        rec |= {ours: check.meta.get(theirs) for theirs, ours in META_FIELDS.items()}
        rec["india"] = india.first_pass(check.meta, rec["domain"] or domain)
    return rec


def verify(fetcher, candidates, out_path, workers=16, target=None):
    out_path = Path(out_path)
    done = read_jsonl(out_path)
    seen = {r["candidate"] for r in done if "candidate" in r}
    indian = sum(1 for r in done if r.get("india") == "yes")
    todo = [c for c in candidates if c[0] not in seen]
    log.info("verify: %d candidates, %d already done, %d Indian so far", len(candidates), len(seen), indian)

    counts = {"done": 0, "shopify": 0, "indian": indian}
    started = time.monotonic()
    with open(out_path, "a", encoding="utf-8") as out:
        def handle(rec):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            counts["done"] += 1
            counts["shopify"] += bool(rec.get("shopify"))
            counts["indian"] += rec.get("india") == "yes"
            if counts["done"] % 200 == 0:
                rate = counts["done"] / (time.monotonic() - started)
                log.info("verify: %d/%d checked (%.1f/s), %d Shopify, %d Indian total",
                         counts["done"], len(todo), rate, counts["shopify"], counts["indian"])

        stop = (lambda: counts["indian"] >= target) if target else (lambda: False)
        run_parallel(todo, lambda c: verify_one(fetcher, c), workers, handle, stop)
    log.info("verify: finished, %d Indian stores so far", counts["indian"])


# enrich --------------------------------------------------------------------------------

def enrich_one(fetcher, rec):
    base = (rec.get("url") or f"https://{rec['domain']}").rstrip("/")
    out = {k: rec.get(k) for k in ("shop_id", "domain", "url", "myshopify_domain", "name", "currency", "source")}

    home = fetcher.get(base + "/")
    if not home.ok:
        return out | {"error": f"homepage: {home.error or home.status}"}
    pages = [parse_page(home.text, home.url)]
    fetched = [home.url]

    # contact page: links with "contact" in the URL, then Shopify's usual URLs, then
    # links that only say "contact" in their text. Stop at the first one with details.
    links = pages[0]["contact_links"]
    tries = [u for u in links if "contact" in u.lower()] + [base + "/pages/contact-us", base + "/pages/contact"]
    tries += [u for u in links if "contact" not in u.lower()]
    for url in _merge([tries])[:3]:
        page = fetcher.get(url)
        if not page.ok or page.url in fetched:
            continue
        parsed = parse_page(page.text, page.url)
        pages.append(parsed)
        fetched.append(page.url)
        if parsed["emails"] or parsed["phones"]:
            break

    emails = _merge(p["emails"] for p in pages)
    phones = _merge(p["phones"] for p in pages)
    # Shopify's "contact information" policy has the legal name, address, phone,
    # email and often a GSTIN. Worth a request when something is still missing.
    if not emails or not phones or rec.get("india") == "maybe" or not rec.get("province"):
        page = fetcher.get(base + "/policies/contact-information")
        if page.ok and "/policies/" in page.url:
            pages.append(parse_page(page.text, page.url))
            fetched.append(page.url)
            emails = _merge(p["emails"] for p in pages)
            phones = _merge(p["phones"] for p in pages)

    home_page = pages[0]
    site_text = " ".join([home_page["footer_text"], *[p["text"] for p in pages[1:]], *_jsonld_addresses(pages)])

    is_indian, evidence = india.decide(rec, rec.get("domain") or "", site_text, phones)
    state, state_source = india.find_state(rec, site_text)

    tagline, tagline_source = _tagline(home_page, rec)
    logo, logo_source = next(((p["logo"]) for p in pages if p["logo"][0]), home_page["logo"])

    texts = [(home_page["title"], 3), (tagline or "", 3), (home_page["site_name"], 1)]
    texts += [(name, 1) for name in home_page["collections"]]
    cat, scores = category.categorize(texts)
    if cat is None:
        texts += _product_texts(fetcher, base)
        cat, scores = category.categorize(texts)
        fetched.append(base + "/products.json")

    return out | {
        "name": rec.get("name") or home_page["site_name"],
        "is_indian": is_indian,
        "india_evidence": evidence,
        "emails": _sort_emails(emails, rec.get("domain") or "")[:MAX_CONTACTS],
        "phones": phones[:MAX_CONTACTS],
        "socials": pick_socials([s for p in pages for s in p["socials"]]),
        "category": cat,
        "category_scores": dict(scores.most_common(3)),
        "tagline": tagline,
        "tagline_source": tagline_source,
        "logo": logo,
        "logo_source": logo_source,
        "state": state,
        "state_source": state_source,
        "city": rec.get("city"),
        "pages": fetched,
    }


def enrich(fetcher, verified_path, out_path, workers=8):
    out_path = Path(out_path)
    done = {r.get("shop_id") for r in read_jsonl(out_path)}
    todo, queued = [], set()
    for rec in read_jsonl(verified_path):
        sid = rec.get("shop_id")
        if rec.get("india") in ("yes", "maybe") and sid not in done and sid not in queued:
            todo.append(rec)
            queued.add(sid)  # the same shop can come in via its myshopify handle and its own domain
    log.info("enrich: %d stores to do, %d already done", len(todo), len(done))

    count = {"n": 0}
    with open(out_path, "a", encoding="utf-8") as out:
        def handle(rec):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            count["n"] += 1
            if count["n"] % 50 == 0:
                log.info("enrich: %d/%d", count["n"], len(todo))

        run_parallel(todo, lambda r: enrich_one(fetcher, r), workers, handle)


# small helpers -----------------------------------------------------------------------------

def _merge(lists):
    seen, out = set(), []
    for items in lists:
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def _sort_emails(emails, domain):
    """Addresses on the store's own domain first; then the rest (often gmail)."""
    root = domain.removeprefix("www.")
    return sorted(emails, key=lambda e: not e.endswith("@" + root))


def _tagline(home, rec):
    for text, source in home["taglines"]:
        if len(text) >= 15 and text.lower() != (home["title"] or "").lower():
            return text[:500], source
    if rec.get("description"):
        return rec["description"].strip()[:500], "store description (meta.json)"
    return None, None


def _jsonld_addresses(pages):
    parts = []
    for page in pages:
        for org in page["jsonld_orgs"]:
            address = org.get("address")
            if isinstance(address, dict):
                parts.append(" ".join(str(v) for k, v in address.items() if not k.startswith("@")))
            elif isinstance(address, str):
                parts.append(address)
    return parts


def _product_texts(fetcher, base):
    page = fetcher.get(base + "/products.json?limit=30")
    data = page.json() if page.ok else None
    texts = []
    for product in (data or {}).get("products", []):
        texts.append((product.get("product_type") or "", 2))
        texts.append((product.get("title") or "", 1))
    return texts
