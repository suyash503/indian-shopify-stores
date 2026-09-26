"""Is a Shopify store Indian, and which state is it in?

What "Indian" means here: the business operates from India. The strongest
signal is the business address the merchant entered in Shopify admin, which
/meta.json exposes as "country". Shopify uses that address for taxes and
invoices, so merchants have a reason to get it right.

  country == IN                          -> Indian, whatever the domain or currency
                                            (an Indian exporter selling in USD still counts)
  country elsewhere, but INR or .in      -> maybe; decided later from the site itself:
                                            needs a GSTIN, or an Indian postal address
                                            plus a +91 number or INR prices
  anything else                          -> not Indian (a .com brand owned by Indians
                                            but run from Dubai is out; I can't verify
                                            ownership at scale)
"""
import re

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # union territories
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

ALIASES = {
    "orissa": "Odisha", "pondicherry": "Puducherry", "uttaranchal": "Uttarakhand",
    "new delhi": "Delhi", "nct of delhi": "Delhi", "national capital territory of delhi": "Delhi",
    "jammu & kashmir": "Jammu and Kashmir", "j&k": "Jammu and Kashmir",
    "andaman & nicobar islands": "Andaman and Nicobar Islands", "andaman & nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "tamilnadu": "Tamil Nadu", "chattisgarh": "Chhattisgarh", "telengana": "Telangana",
}

# ISO 3166-2:IN codes, which some themes and apps use instead of names
CODES = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar", "CT": "Chhattisgarh",
    "CG": "Chhattisgarh", "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh",
    "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra",
    "MN": "Manipur", "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland", "OR": "Odisha", "OD": "Odisha",
    "PB": "Punjab", "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TG": "Telangana",
    "TS": "Telangana", "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand", "UT": "Uttarakhand",
    "WB": "West Bengal", "AN": "Andaman and Nicobar Islands", "CH": "Chandigarh",
    "DH": "Dadra and Nagar Haveli and Daman and Diu", "DN": "Dadra and Nagar Haveli and Daman and Diu",
    "DD": "Dadra and Nagar Haveli and Daman and Diu", "DL": "Delhi", "JK": "Jammu and Kashmir",
    "LA": "Ladakh", "LD": "Lakshadweep", "PY": "Puducherry",
}

# The first two digits of a GSTIN are the state's GST code.
GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Dadra and Nagar Haveli and Daman and Diu", "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}

# Big e-commerce cities, for addresses that name the city but not the state
CITIES = {
    "mumbai": "Maharashtra", "navi mumbai": "Maharashtra", "thane": "Maharashtra", "pune": "Maharashtra",
    "nagpur": "Maharashtra", "nashik": "Maharashtra", "bengaluru": "Karnataka", "bangalore": "Karnataka",
    "mysuru": "Karnataka", "mysore": "Karnataka", "gurugram": "Haryana", "gurgaon": "Haryana",
    "faridabad": "Haryana", "noida": "Uttar Pradesh", "greater noida": "Uttar Pradesh",
    "ghaziabad": "Uttar Pradesh", "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh",
    "agra": "Uttar Pradesh", "varanasi": "Uttar Pradesh", "hyderabad": "Telangana",
    "secunderabad": "Telangana", "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "tiruppur": "Tamil Nadu", "madurai": "Tamil Nadu", "kolkata": "West Bengal", "howrah": "West Bengal",
    "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat", "rajkot": "Gujarat",
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan", "kochi": "Kerala",
    "cochin": "Kerala", "ernakulam": "Kerala", "thiruvananthapuram": "Kerala", "kozhikode": "Kerala",
    "ludhiana": "Punjab", "amritsar": "Punjab", "jalandhar": "Punjab", "mohali": "Punjab",
    "indore": "Madhya Pradesh", "bhopal": "Madhya Pradesh", "patna": "Bihar", "bhubaneswar": "Odisha",
    "guwahati": "Assam", "dehradun": "Uttarakhand", "panaji": "Goa", "visakhapatnam": "Andhra Pradesh",
    "vijayawada": "Andhra Pradesh", "raipur": "Chhattisgarh", "ranchi": "Jharkhand",
    "jamshedpur": "Jharkhand", "srinagar": "Jammu and Kashmir", "shimla": "Himachal Pradesh",
}

GSTIN_RE = re.compile(r"\b(\d{2})[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
# PIN codes are six digits and never start with 0 or 9; allow "560 001" too
PIN_RE = re.compile(r"(?<![\d.,])([1-8]\d{2})\s?(\d{3})(?![\d.,])")

_NAMES = {s.lower(): s for s in STATES} | ALIASES
_NAME_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _NAMES), key=len, reverse=True)) + r")\b", re.I)
_CITY_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, CITIES), key=len, reverse=True)) + r")\b", re.I)


def normalize_state(value):
    """'MH', 'maharashtra', 'Orissa' -> canonical name, or None."""
    value = (value or "").strip()
    if not value:
        return None
    if value.upper() in CODES:
        return CODES[value.upper()]
    return _NAMES.get(value.lower().replace("  ", " "))


def gstins(text):
    return sorted({m.group(0) for m in GSTIN_RE.finditer(text or "") if m.group(1) in GST_STATE_CODES})


def address_snippets(text, width=120):
    """Bits of text around PIN codes, which is where addresses live."""
    text = text or ""
    return [text[max(0, m.start() - width): m.end() + 20] for m in PIN_RE.finditer(text)]


def state_from_text(text):
    """Looks for a state name, then a known city, in address-looking parts of
    the text. Returns (state, how) or (None, None)."""
    for snippet in address_snippets(text):
        if m := _NAME_RE.search(snippet):
            return _NAMES[m.group(1).lower()], "address on site"
    for snippet in address_snippets(text):
        if m := _CITY_RE.search(snippet):
            return CITIES[m.group(1).lower()], "city in address on site"
    return None, None


def first_pass(meta, domain):
    """'yes', 'maybe' or 'no', from meta.json alone."""
    if (meta.get("country") or "").upper() == "IN":
        return "yes"
    if meta.get("currency") == "INR" or domain.endswith(".in"):
        return "maybe"
    return "no"


def decide(meta, domain, site_text, phones):
    """Final call. Returns (is_indian, evidence list)."""
    evidence = []
    country = (meta.get("country") or "").upper()
    if country == "IN":
        evidence.append("Shopify business address in India")
    elif country:
        evidence.append(f"Shopify business address in {country}")
    if meta.get("currency") == "INR":
        evidence.append("prices in INR")
    if domain.endswith(".in"):
        evidence.append(".in domain")

    has_gstin = bool(gstins(site_text))
    has_address = any(_NAME_RE.search(s) or _CITY_RE.search(s) for s in address_snippets(site_text))
    has_phone = any(p.startswith("+91") for p in phones)
    if has_gstin:
        evidence.append("GSTIN on site")
    if has_address:
        evidence.append("Indian postal address on site")
    if has_phone:
        evidence.append("+91 phone number")

    if country == "IN":
        return True, evidence
    return has_gstin or (has_address and (has_phone or meta.get("currency") == "INR")), evidence


def find_state(meta, site_text):
    """Returns (state, source). meta.json first, then GSTIN, then the address."""
    if (meta.get("country") or "").upper() == "IN":
        state = normalize_state(meta.get("province"))
        if state:
            return state, "Shopify business address"
    for gstin in gstins(site_text):
        return GST_STATE_CODES[gstin[:2]], "GSTIN"
    state, how = state_from_text(site_text)
    if state:
        return state, how
    if (meta.get("country") or "").upper() == "IN" and meta.get("city"):
        city = CITIES.get(meta["city"].strip().lower())
        if city:
            return city, "city in Shopify business address"
    return None, None
