"""Where candidate domains come from.

1. Tranco top 1M: every domain under India's ccTLD (.in, .co.in, .org.in ...).
   Most aren't Shopify stores, but the verify step checks DNS first, which is
   nearly free, so a big noisy list is fine here.
2. Common Crawl's URL index: every *.myshopify.com host seen in the last few
   crawls. All of them are Shopify by definition, but only ~2% are Indian, so
   this source is big and low-yield. It's how Indian brands on .com domains
   get found.
3. Optional seed files, one domain per line.

Note on Common Crawl: index.commoncrawl.org serves "Disallow: /" to everyone.
That keeps search engines out of the query pages; the API itself is documented
for programmatic use. I treat it as an API rather than a site to crawl: one
request at a time, cached, about 26 requests per crawl.
"""
import csv
import io
import json
import logging
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

TRANCO_ZIP = "https://tranco-list.eu/top-1m.csv.zip"
TRANCO_ID = "https://tranco-list.eu/top-1m-id"
CC_INDEX = "https://index.commoncrawl.org"

# .in also covers the second-level zones (.co.in, .net.in, .firm.in ...)
# xn--h2brj9c is .भारत
INDIAN_TLDS = (".in", ".xn--h2brj9c")


def normalize_domain(value):
    """'https://WWW.Foo.in/abc' -> 'foo.in'. Returns None for junk."""
    value = (value or "").strip().lower()
    if not value or value.startswith("#"):
        return None
    if "://" not in value:
        value = "//" + value
    try:
        host = urlsplit(value).hostname
    except ValueError:
        return None
    if not host or "." not in host:
        return None
    host = host.rstrip(".")
    return host[4:] if host.startswith("www.") else host


def tranco_indian_domains(cache_dir):
    """All Indian-ccTLD domains in the current Tranco list, in rank order."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "tranco-top-1m.csv.zip"
    id_path = cache_dir / "tranco-list-id.txt"

    if not zip_path.exists():
        log.info("downloading Tranco top 1M (~10 MB)")
        list_id = requests.get(TRANCO_ID, timeout=30).text.strip()
        resp = requests.get(TRANCO_ZIP, timeout=300)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)
        id_path.write_text(list_id)

    list_id = id_path.read_text().strip() if id_path.exists() else "unknown"
    with zipfile.ZipFile(zip_path) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as raw:
            rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            domains = [d for _, d in rows if d.endswith(INDIAN_TLDS)]
    log.info("Tranco list %s: %d Indian-TLD domains", list_id, len(domains))
    return domains, list_id


def recent_crawls(fetcher, how_many):
    page = fetcher.get(f"{CC_INDEX}/collinfo.json", respect_robots=False, retries=5)
    crawls = page.json() if page.ok else None
    if not crawls:
        raise RuntimeError(f"couldn't list Common Crawl crawls ({page.error or page.status})")
    return [c["id"] for c in crawls[:how_many]]


def myshopify_hosts(fetcher, crawl_id):
    """Every *.myshopify.com host in one crawl, minus ones that only ever
    answered 402/403/404/410 (closed or deleted stores)."""
    base = f"{CC_INDEX}/{crawl_id}-index?url=*.myshopify.com&output=json"
    # pageSize=1 keeps each page (~3,000 rows) under the server's ~10s gateway
    # timeout; bigger pages fail with 504 most of the time.
    info = fetcher.get(f"{base}&showNumPages=true&pageSize=1", respect_robots=False, retries=6)
    if not info.ok:
        log.warning("%s: couldn't get page count (%s)", crawl_id, info.error or info.status)
        return []
    pages = info.json()["pages"]

    alive, dead = set(), set()
    for n in range(pages):
        page = fetcher.get(f"{base}&fl=url,status&pageSize=1&page={n}", respect_robots=False, retries=6)
        if not page.ok:
            log.warning("%s page %d/%d failed (%s), skipping it", crawl_id, n + 1, pages, page.error or page.status)
            continue
        for line in page.text.splitlines():
            try:
                row = json.loads(line)
                host = urlsplit(row["url"]).hostname
            except (ValueError, KeyError):
                continue
            if not host or not host.endswith(".myshopify.com"):
                continue
            if row.get("status") in ("402", "403", "404", "410"):
                dead.add(host)
            else:
                alive.add(host)
        log.info("%s page %d/%d: %d hosts so far", crawl_id, n + 1, pages, len(alive))
    log.info("%s: %d live hosts, %d dropped as closed", crawl_id, len(alive), len(dead - alive))
    return sorted(alive)


def read_seed_file(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def collect(fetcher, cache_dir, crawls=3, seed_files=(), use_tranco=True):
    """Build the candidate list. Earlier sources win when a domain repeats,
    so the high-yield ones go first."""
    candidates = {}
    meta = {"tranco_list_id": None, "common_crawl": []}

    def add(domains, source):
        added = 0
        for d in domains:
            d = normalize_domain(d)
            if d and d not in candidates:
                candidates[d] = source
                added += 1
        log.info("%s: %d new candidates", source, added)

    for path in seed_files:
        add(read_seed_file(path), f"seed:{Path(path).name}")

    if use_tranco:
        domains, list_id = tranco_indian_domains(cache_dir)
        meta["tranco_list_id"] = list_id
        add(domains, "tranco")

    if crawls:
        for crawl_id in recent_crawls(fetcher, crawls):
            add(myshopify_hosts(fetcher, crawl_id), f"commoncrawl:{crawl_id}")
            meta["common_crawl"].append(crawl_id)

    return candidates, meta


def write_candidates(path, candidates):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["domain", "source"])
        writer.writerows(candidates.items())


def read_candidates(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [(row["domain"], row["source"]) for row in csv.DictReader(f)]
