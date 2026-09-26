"""Pulling fields out of one HTML page.

parse_page() returns what it found on that page, and the pipeline merges the
homepage, the contact page and the contact-information policy.
"""
import html
import json
import re
from collections import Counter
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

SOCIAL_HOSTS = {
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.com", "fb.me"),
    "twitter": ("twitter.com", "x.com"),
    "linkedin": ("linkedin.com",),
    "youtube": ("youtube.com",),
}
# first path segments that mean "share button / embed / a single post", not the brand's profile
NOT_A_PROFILE = {
    "sharer", "sharer.php", "share", "share.php", "intent", "dialog", "plugins", "tr", "hashtag",
    "home.php", "p", "reel", "reels", "tv", "watch", "embed", "shorts", "results", "explore",
    "stories", "search", "login", "privacy", "legal", "help", "feed", "shareArticle", "sharing",
}
# profile paths with two parts: linkedin.com/company/x, youtube.com/channel/x, facebook.com/groups/x
TWO_PART_PATHS = {"company", "in", "showcase", "school", "channel", "c", "user", "groups", "pages", "people"}
# Shopify's own accounts sometimes sneak in through theme or app templates
SHOPIFY_HANDLES = {"shopify", "shopifyplus", "shopifyindia", "shopify.in"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com", "domain.com", "email.com", "yourdomain.com", "yourstore.com", "company.com",
    "test.com", "mysite.com", "sentry.io", "wixpress.com", "shopify.com", "sentry-next.wixpress.com",
}
PLACEHOLDER_EMAIL_USERS = {"you", "your", "yourname", "name", "email", "user", "username", "john", "johndoe"}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif")

# +91 98765 43210, 098765-43210, 9876543210, 987 654 3210
MOBILE_RE = re.compile(r"(?<![\d+])(?:\+?91[\s-]?|0)?[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)"
                       r"|(?<![\d+])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
# +91 22 4123 4567, +91-80-41234567 (landlines only count with the +91 prefix, otherwise too noisy)
LANDLINE_RE = re.compile(r"\+91[\s-]?\(?0?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{4}(?!\d)")
TOLL_FREE_RE = re.compile(r"(?<!\d)1800[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)")

LOGO_BLOCKLIST = (
    "payment", "visa", "mastercard", "amex", "rupay", "upi", "paytm", "razorpay", "gpay", "phonepe",
    "google-play", "googleplay", "app-store", "appstore", "playstore", "badge", "trust", "award",
    "featured", "as-seen", "press", "partner", "shopify",
)
# section headings every Shopify theme ships with; not a brand's own words
GENERIC_HEADING = re.compile(
    r"^(welcome|featured|shop|new|best|top|trending|our|all|view|explore|subscribe|join|follow|"
    r"testimonials?|customer|reviews?|faq|blog|latest|collections?|categories|products?|bestsellers?|"
    r"sign up|what our|as seen|free shipping|sale)\b",
    re.I,
)
SHOPIFY_SIZE_SUFFIX = re.compile(r"_(?:\{width\}x|\d+x\d*|\d*x\d+)(?:@\dx)?(?=\.\w+$)")

ORG_TYPES = {"organization", "corporation", "brand", "store", "onlinestore", "localbusiness", "onlinebusiness"}


def parse_page(page_html, url):
    soup = BeautifulSoup(page_html, "lxml")
    found = {
        "url": url,
        "title": _clean(soup.title.string if soup.title else ""),
        "site_name": _meta(soup, "og:site_name"),
        "jsonld_orgs": _jsonld_orgs(soup),
    }
    found["emails"] = _emails_from_markup(soup)
    found["phones"] = _phones_from_links(soup)
    found["socials"] = _social_links(soup, found["jsonld_orgs"])
    found["logo"] = _logo(soup, url, found["jsonld_orgs"])
    found["logo_svg"] = None
    if not found["logo"][0]:
        kind, found["logo_svg"] = _logo_without_image(soup, url)
        found["logo"] = (None, kind)
    found["taglines"] = _taglines(soup)
    found["collections"] = _collection_names(soup)
    found["contact_links"] = _contact_links(soup, url)
    found["about_links"] = _same_site_links(soup, url, "about")

    # everything below reads visible text, so scripts and styles go now
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    footer = soup.find("footer") or soup.select_one("[class*=footer], [id*=footer]")
    found["text"] = text
    found["footer_text"] = footer.get_text(" ", strip=True) if footer else ""
    found["hero"] = _hero_text(soup)
    found["first_paragraph"] = _first_paragraph(soup)

    found["emails"] = _unique(found["emails"] + _emails_in_text(text))
    # phone numbers in running text are only trusted in the footer or on contact pages;
    # elsewhere 10-digit numbers are too often order ids or SKUs
    phone_text = text if _is_contact_page(url) else found["footer_text"]
    found["phones"] = _unique(found["phones"] + _phones_in_text(phone_text))
    for org in found["jsonld_orgs"]:
        found["emails"] = _unique(found["emails"] + [e for e in _as_list(org.get("email")) if _good_email(e)])
        found["phones"] = _unique(found["phones"] + [p for p in map(normalize_phone, _as_list(org.get("telephone"))) if p])
    return found


# emails ---------------------------------------------------------------------

def _emails_from_markup(soup):
    emails = []
    for a in soup.select("a[href^='mailto:' i]"):
        address = a["href"].split(":", 1)[1].split("?")[0]
        emails.append(html.unescape(address))
    # Cloudflare's email obfuscation: the address is XOR-ed with the first byte
    for tag in soup.select("[data-cfemail]"):
        emails.append(_decode_cfemail(tag["data-cfemail"]))
    for a in soup.select("a[href*='/cdn-cgi/l/email-protection#']"):
        emails.append(_decode_cfemail(a["href"].split("#", 1)[1]))
    return [e.strip().lower() for e in emails if _good_email(e)]


def _decode_cfemail(hex_string):
    try:
        key = int(hex_string[:2], 16)
        return "".join(chr(int(hex_string[i:i + 2], 16) ^ key) for i in range(2, len(hex_string), 2))
    except ValueError:
        return ""


def _emails_in_text(text):
    return [m.group(0).lower() for m in EMAIL_RE.finditer(text) if _good_email(m.group(0))]


def _good_email(email):
    email = (email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email) or email.endswith(IMAGE_EXTENSIONS):
        return False
    user, domain = email.rsplit("@", 1)
    return domain not in PLACEHOLDER_EMAIL_DOMAINS and user not in PLACEHOLDER_EMAIL_USERS


# phones ---------------------------------------------------------------------

def normalize_phone(raw):
    """Indian numbers -> +91XXXXXXXXXX, toll-free -> 1800-XXX-XXXX,
    other international numbers kept as +<digits>. None if it doesn't look real."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("1800") and len(digits) in (10, 11):
        return f"1800-{digits[4:7]}-{digits[7:]}"
    if raw.startswith("+") and not digits.startswith("91"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    # 9999999999, 1234567890 and friends are placeholders
    if len(digits) != 10 or len(set(digits)) < 4 or digits in "01234567890123456789":
        return None
    return f"+91{digits}"


def _phones_from_links(soup):
    phones = []
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        lower = href.lower()
        if lower.startswith("tel:"):
            phones.append(normalize_phone(href[4:]))
        elif "wa.me/" in lower:
            phones.append(normalize_phone("+" + urlsplit(href).path.strip("/").split("/")[0]))
        elif "whatsapp.com/send" in lower or lower.startswith("whatsapp://send"):
            number = parse_qs(urlsplit(href).query).get("phone", [""])[0]
            phones.append(normalize_phone("+" + number if number else ""))
    return _unique(p for p in phones if p)


def _phones_in_text(text):
    found = []
    for regex in (MOBILE_RE, LANDLINE_RE, TOLL_FREE_RE):
        found += [normalize_phone(m.group(0)) for m in regex.finditer(text or "")]
    return _unique(p for p in found if p)


# socials ----------------------------------------------------------------------

def social_profile(href):
    """(network, clean url) if href is a brand profile, else None."""
    try:
        parts = urlsplit(href.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "m.", "mobile.", "in.", "web."):
        host = host.removeprefix(prefix)
    network = next((n for n, hosts in SOCIAL_HOSTS.items() if host in hosts), None)
    if not network:
        return None

    segments = [s for s in parts.path.split("/") if s]
    if not segments or segments[0] in NOT_A_PROFILE:
        return None
    two_part = segments[0] in TWO_PART_PATHS
    if two_part and len(segments) < 2:
        return None
    handle = segments[1] if two_part else segments[0]
    if handle.lower().lstrip("@") in SHOPIFY_HANDLES:
        return None

    keep = 2 if two_part else 1
    if segments[0] in ("people", "pages"):  # facebook.com/people/Name/100089.../ needs the id
        keep = 3
    path = "/" + "/".join(segments[:keep])
    query = ""
    if segments[0] == "profile.php":  # facebook pages without a vanity name
        page_id = parse_qs(parts.query).get("id", [""])[0]
        if not page_id:
            return None
        query = urlencode({"id": page_id})
    return network, urlunsplit(("https", host, path, query, ""))


def _social_links(soup, orgs):
    hrefs = [a["href"] for a in soup.select("a[href]")]
    for org in orgs:
        hrefs += [s for s in _as_list(org.get("sameAs")) if isinstance(s, str)]
    return [p for p in map(social_profile, hrefs) if p]


def pick_socials(pairs):
    """Most linked profile per network; ties go to whichever came first."""
    best = {}
    for network in SOCIAL_HOSTS:
        urls = [u for n, u in pairs if n == network]
        if urls:
            counts = Counter(urls)
            best[network] = max(urls, key=lambda u: (counts[u], -urls.index(u)))
    return best


# logo -------------------------------------------------------------------------

def _logo(soup, page_url, orgs):
    """(url, where it came from) or (None, None). Never the favicon."""
    for org in orgs:
        logo = org.get("logo")
        if isinstance(logo, dict):
            logo = logo.get("url") or logo.get("contentUrl")
        if isinstance(logo, str) and logo.strip():
            return clean_image_url(logo, page_url), "structured data"

    header = soup.find("header") or soup.select_one("[class*=header], [id*=header]")
    for scope, label in ((header, "header image"), (soup, "logo image")):
        if scope is None:
            continue
        for img in scope.find_all("img"):
            src = _img_src(img)
            if src and "logo" in _hints(img) and not any(b in _hints(img) for b in LOGO_BLOCKLIST):
                return clean_image_url(src, page_url), label

    if header:
        # a header image that links to the homepage is almost always the logo
        for a in header.find_all("a", href=True):
            img = a.find("img")
            if img and _img_src(img) and urlsplit(urljoin(page_url, a["href"])).path in ("", "/"):
                return clean_image_url(_img_src(img), page_url), "header image"

    og = _meta(soup, "og:image")
    if og and "logo" in og.lower():
        return clean_image_url(og, page_url), "og:image"
    return None, None


def _logo_without_image(soup, page_url):
    """No logo image anywhere. Is the logo an inline <svg> (which we can save as a
    file), or just the store name in text? Returns (kind, svg markup)."""
    header = soup.find("header") or soup.select_one("[class*=header], [id*=header]")
    if not header:
        return None, None
    # only elements whose *own* class says logo; a class on <header> like
    # "header--logo-center" would otherwise make every icon in it look like a logo
    spots = [el for el in header.find_all(True) if any("logo" in c.lower() for c in el.get("class", []))]
    spots += [a for a in header.find_all("a", href=True) if urlsplit(urljoin(page_url, a["href"])).path in ("", "/")]
    for el in spots:
        svg = el if el.name == "svg" else el.find("svg")
        if svg and svg.find(["path", "text", "polygon", "circle", "rect", "g"]) and not svg.find("use"):
            return "inline svg", str(svg)  # <use> points at a sprite elsewhere, useless on its own
    for el in spots:
        if el.get_text(strip=True) and not el.find(["img", "svg"]):
            return "text only (no logo image on the site)", None
    return None, None


def _hints(img):
    """Text around an <img> that might say 'logo': its own attributes and its
    two nearest parents, stopping at the header itself."""
    parts = [img.get("alt", ""), img.get("src", ""), img.get("data-src", ""), img.get("id", "")]
    parts += img.get("class", [])
    for parent in list(img.parents)[:2]:
        if parent.name in ("header", "body"):
            break
        parts += parent.get("class", []) or []
        parts.append(parent.get("id", "") or "")
    return " ".join(str(p) for p in parts).lower()


def _img_src(img):
    src = img.get("src") or img.get("data-src") or ""
    if not src and img.get("srcset"):
        src = img["srcset"].split(",")[0].split()[0]
    src = src.strip()
    return None if not src or src.startswith("data:") else src


def clean_image_url(src, page_url):
    """Absolute URL of the original image: Shopify's CDN resizes via ?width= or
    a _200x filename suffix, and dropping those gives the full-size file."""
    url = urljoin(page_url, src.strip())
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qs(parts.query).items() if k not in ("width", "height", "crop")]
    path = SHOPIFY_SIZE_SUFFIX.sub("", parts.path)
    return urlunsplit(("https", parts.netloc, path, urlencode(query, doseq=True), ""))


# tagline, collections, contact links -----------------------------------------------

def _taglines(soup):
    found = []
    for key in ("description", "og:description", "twitter:description"):
        value = _meta(soup, key)
        if value:
            found.append((value, "meta description" if key == "description" else key))
    return found


def _collection_names(soup):
    """Names of the collections the store links to, e.g. 'Face Wash', 'Kurtas'.
    Best free signal for what the store sells."""
    names = []
    for a in soup.select("a[href*='/collections/']"):
        text = _clean(a.get_text(" "))
        if text and len(text) < 40:
            names.append(text)
        path = urlsplit(a["href"]).path
        handle = path.split("/collections/", 1)[1].split("/")[0] if "/collections/" in path else ""
        if handle and handle not in ("all", "frontpage"):
            names.append(handle.replace("-", " "))
    return _unique(n.lower() for n in names)


def _contact_links(soup, page_url):
    """Same-site links that look like contact pages; ones with 'contact' in
    the URL come before ones that only say it in the link text."""
    site = urlsplit(page_url).netloc
    by_url, by_text = [], []
    for a in soup.select("a[href]"):
        href = urljoin(page_url, a["href"]).split("#")[0]
        if urlsplit(href).netloc != site:
            continue
        if "contact" in urlsplit(href).path.lower():
            by_url.append(href)
        elif "contact" in a.get_text(" ").lower():
            by_text.append(href)
    return _unique(by_url + by_text)


def _same_site_links(soup, page_url, word):
    site = urlsplit(page_url).netloc
    links = [urljoin(page_url, a["href"]).split("#")[0] for a in soup.select("a[href]")]
    return _unique(u for u in links if urlsplit(u).netloc == site and word in urlsplit(u).path.lower())


def _main_content(soup):
    return soup.find("main") or soup.select_one("#MainContent, [role=main]") or soup.body or soup


def _hero_text(soup):
    """First real heading on the homepage, e.g. 'Handwoven Sarees from Varanasi'."""
    for tag in _main_content(soup).find_all(["h1", "h2"], limit=10):
        text = _clean(tag.get_text(" "))
        if 5 <= len(text.split()) <= 25 and not GENERIC_HEADING.match(text):
            return text
    return None


def _first_paragraph(soup):
    """First paragraph with some substance, for About pages."""
    for p in _main_content(soup).find_all("p", limit=40):
        text = _clean(p.get_text(" "))
        if 60 <= len(text) <= 700:
            return text
    return None


def _is_contact_page(url):
    path = urlsplit(url).path.lower()
    return "contact" in path or "/policies/" in path


# helpers --------------------------------------------------------------------------

def _jsonld_orgs(soup):
    orgs = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                stack.extend(_as_list(item.get("@graph")))
                types = {t.lower() for t in _as_list(item.get("@type")) if isinstance(t, str)}
                if types & ORG_TYPES:
                    orgs.append(item)
    return orgs


def _meta(soup, key):
    tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    return _clean(tag.get("content", "")) if tag else ""


def _clean(value):
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _unique(items):
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
