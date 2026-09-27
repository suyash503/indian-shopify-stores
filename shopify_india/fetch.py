"""Every HTTP request in the pipeline goes through Fetcher.

Each Shopify store has its own domain, but they all sit on the same Shopify
infrastructure. Ten requests a second to ten different stores is still ten
requests a second to one service, so the rate limit here is global across
threads, and a 429 from any store slows everyone down.
"""
import gzip
import hashlib
import json
import logging
import random
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from .robots import RobotsRules

log = logging.getLogger(__name__)

BOT_NAME = "IndianShopifyResearch"
USER_AGENT = (
    f"Mozilla/5.0 (compatible; {BOT_NAME}/0.1; "
    "+https://github.com/suyash503/indian-shopify-stores)"
)
KEEP_HEADERS = ("content-type", "location", "retry-after", "x-shopid", "powered-by")
RETRY_STATUSES = {429, 500, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
MAX_BYTES = 4_000_000  # some homepages inline megabytes of JSON; the head and footer are enough


@dataclass
class Page:
    url: str
    status: int = 0
    text: str = ""
    headers: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self):
        return self.error is None and 200 <= self.status < 300

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return None


class Fetcher:
    def __init__(self, rate=8.0, timeout=20, retries=3, cache_dir=".cache/http"):
        self.timeout = (10, timeout)
        self.retries = retries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.stats = Counter()

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"})
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self._gap = 1.0 / rate
        self._next_slot = 0.0
        self._lock = threading.Lock()
        self._robots = {}

    def get(self, url, *, retries=None, respect_robots=True):
        """GET a URL. Redirects are followed by hand so that every hop is checked
        against its own host's robots.txt (xyz.myshopify.com usually redirects to
        the store's real domain)."""
        retries = self.retries if retries is None else retries
        for _ in range(MAX_REDIRECTS + 1):
            if respect_robots:
                verdict = self._robots_verdict(url)
                if verdict:
                    return Page(url, error=verdict)
            page = self._get_once(url, retries)
            location = page.headers.get("location")
            if page.error or page.status not in REDIRECT_STATUSES or not location:
                return page
            url = urljoin(url, location)
        return Page(url, error="too many redirects")

    # robots.txt -----------------------------------------------------------

    def _robots_verdict(self, url):
        """None if we may fetch the URL, otherwise the reason we may not."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rules = self._robots.get(origin)
        if rules is None:
            rules, reachable = self._load_robots(origin)
            if not reachable:
                # don't remember this: a 429 on robots.txt now shouldn't block the store forever
                return "robots.txt unreachable"
            self._robots[origin] = rules

        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        return None if rules.allows(path) else "disallowed by robots.txt"

    def _load_robots(self, origin):
        page = self._get_once(origin + "/robots.txt", self.retries, follow=True)
        if page.error or page.status == 429 or page.status >= 500:
            return RobotsRules.disallow_all(), False
        if page.status >= 400:
            return RobotsRules.allow_all(), True  # no robots.txt, nothing is off limits
        return RobotsRules.parse(page.text, BOT_NAME), True

    # the actual request -----------------------------------------------------

    def _get_once(self, url, retries, follow=False):
        cached = self._read_cache(url)
        if cached:
            self._count("cache hits")
            return cached

        page = None
        for attempt in range(retries + 1):
            self._wait_turn()
            page = self._request(url, follow)
            if page.error is None and page.status not in RETRY_STATUSES:
                self._write_cache(url, page)
                return page
            if attempt < retries:
                self._back_off(page, attempt)
        return page

    def _request(self, url, follow):
        self._count("requests")
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=follow, stream=True)
            body = bytearray()
            for chunk in resp.iter_content(64 * 1024):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            resp.close()
        except requests.Timeout:
            return Page(url, error="timeout")
        except requests.RequestException as exc:
            log.debug("GET %s failed: %s", url, exc)
            return Page(url, error="connection error")

        if resp.status_code == 429:
            self._count("429s")
        # requests falls back to latin-1 when there's no charset, which mangles the ₹ sign
        charset = resp.encoding if "charset" in resp.headers.get("content-type", "") else "utf-8"
        headers = {k: resp.headers[k] for k in KEEP_HEADERS if k in resp.headers}
        try:
            text = body.decode(charset or "utf-8", "replace")
        except LookupError:  # sites do declare charsets like "cp-1251" that don't exist
            text = body.decode("utf-8", "replace")
        return Page(resp.url, resp.status_code, text, headers)

    def _wait_turn(self):
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._gap
        time.sleep(slot - now)

    def _back_off(self, page, attempt):
        delay = min(60, 2 ** (attempt + 1)) + random.uniform(0, 1)
        if page.status == 429:
            retry_after = page.headers.get("retry-after", "")
            if retry_after.isdigit():
                delay = min(120, int(retry_after)) + random.uniform(0, 1)
            # a 429 is about our IP, not this one store, so every thread waits a bit
            with self._lock:
                self._next_slot = max(self._next_slot, time.monotonic() + delay / 2)
        time.sleep(delay)

    def _count(self, key):
        with self._lock:
            self.stats[key] += 1

    # disk cache ---------------------------------------------------------------
    # Re-running extraction shouldn't mean re-downloading 1,000 homepages.

    def _cache_path(self, url):
        digest = hashlib.sha1(url.encode()).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json.gz"

    def _read_cache(self, url):
        if not self.cache_dir:
            return None
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return Page(**json.load(f))
        except (OSError, ValueError, EOFError, TypeError):
            return None

    def _write_cache(self, url, page):
        if not self.cache_dir:
            return
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{threading.get_ident()}.tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(asdict(page), f)
        tmp.replace(path)
