"""Is this domain a live Shopify store?

Two checks, cheapest first.

1. DNS. Shopify tells merchants to point their domain at 23.227.38.65 or CNAME
   it to shops.myshopify.com, and storefronts resolve into 23.227.38.0/24. A
   lookup never touches the store. It misses stores that put their own CDN in
   front of Shopify, which is a known gap (see README).

2. /meta.json. Every Shopify storefront serves it: the shop's numeric id, its
   *.myshopify.com handle, the business address the merchant entered in admin
   (city, province, country) and the store currency. Nothing else on the web
   answers /meta.json with a "myshopify_domain" key, so this is also the
   false-positive filter. A WordPress site with the Shopify Buy Button loads
   Shopify's JS and would fool an HTML check, but it has no meta.json.
"""
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

SHOPIFY_NET = ipaddress.ip_network("23.227.38.0/24")


def dns_verdict(domain):
    """'shopify', 'elsewhere' or 'no dns'. Tries the bare domain and www."""
    resolved = False
    for host in (domain, "www." + domain):
        try:
            name, aliases, addresses = socket.gethostbyname_ex(host)
        except (OSError, UnicodeError):
            continue
        resolved = True
        # the alias list carries the CNAME chain, e.g. shops.myshopify.com
        if any(n.endswith(".myshopify.com") for n in [name, *aliases]):
            return "shopify"
        if any(ipaddress.ip_address(a) in SHOPIFY_NET for a in addresses):
            return "shopify"
    return "elsewhere" if resolved else "no dns"


@dataclass
class ShopCheck:
    is_shopify: bool
    reason: str
    meta: dict | None = None


def check_meta(fetcher, host):
    page = fetcher.get(f"https://{host}/meta.json")
    if page.error:
        return ShopCheck(False, page.error)
    if urlsplit(page.url).path.startswith("/password"):
        return ShopCheck(False, "password protected")
    if page.status == 402:
        return ShopCheck(False, "store closed (402)")
    if page.status != 200:
        return ShopCheck(False, f"meta.json returned {page.status}")

    data = page.json()
    if not isinstance(data, dict) or not data.get("myshopify_domain"):
        return ShopCheck(False, "no Shopify meta.json")
    return ShopCheck(True, "ok", data)


def verify(fetcher, domain):
    """Returns (ShopCheck, dns_verdict). myshopify.com hosts skip the DNS step."""
    dns = None
    if not domain.endswith(".myshopify.com"):
        dns = dns_verdict(domain)
        if dns != "shopify":
            return ShopCheck(False, f"dns: {dns}"), dns

    check = check_meta(fetcher, domain)
    if check.reason in ("timeout", "connection error") and not domain.endswith(".myshopify.com"):
        check = check_meta(fetcher, "www." + domain)  # a few sites only answer on www
    return check, dns
