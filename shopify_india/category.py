"""What does the store sell?

Keyword scoring over the store's own words. The title and meta description get
the most weight because that's the brand describing itself; every collection
the homepage links to ("Face Wash", "Kurtas", "Neckbands") adds a point. If
that's not enough to go on, the pipeline also pulls product types from
/products.json and calls this again.

An LLM would do this better on the long tail. I kept it rule-based so it's free,
deterministic and easy to audit, and the keyword lists are right here to argue with.
"""
import re
from collections import Counter

CATEGORIES = {
    "skincare": [
        "skincare", "skin care", "face wash", "facewash", "serum", "moisturi*", "sunscreen", "cleanser",
        "toner", "face cream", "face mask", "acne", "facial", "body lotion", "lip balm", "body wash",
        "ubtan", "kumkumadi", "face oil", "soap",
    ],
    "haircare": ["hair care", "haircare", "hair oil", "shampoo", "conditioner", "hair serum", "hair mask", "hair growth", "hair fall", "hair extension*", "wig", "wigs"],
    "makeup": [
        "makeup", "make-up", "lipstick", "kajal", "eyeliner", "mascara", "nail polish", "nail paint",
        "eyeshadow", "concealer", "cosmetic*", "lip gloss", "blush",
    ],
    "fragrances": ["perfume*", "fragrance*", "attar", "ittar", "deodorant*", "body mist", "eau de parfum", "cologne"],
    "men's grooming": ["beard*", "shaving", "shave", "razor*", "trimmer*", "grooming", "aftershave"],
    "health & nutrition": [
        "supplement*", "protein", "whey", "vitamin*", "multivitamin*", "nutrition", "gummies", "capsule*",
        "wellness", "immunity", "ashwagandha", "ayurved*", "herbal", "menstrual", "period care",
        "sanitary", "period pant*",
    ],
    "apparel": [
        "t-shirt*", "tshirt*", "tees", "shirt*", "jeans", "trouser*", "pants", "hoodie*", "sweatshirt*",
        "jogger*", "shorts", "dress*", "tops", "co-ord*", "co ord*", "jacket*", "blazer*", "innerwear",
        "lingerie", "bras", "nightwear", "loungewear", "activewear", "clothing", "apparel", "denim", "polos",
        "abaya*", "hijab*", "modest wear", "jersey*", "underwear",
    ],
    "ethnic wear": [
        "saree*", "sari", "kurta*", "kurti*", "lehenga*", "salwar", "dupatta*", "ethnic wear", "ethnic",
        "sherwani*", "anarkali*", "churidar*", "handloom", "suit set*",
    ],
    "kids & baby": ["baby", "babies", "kids", "infant*", "toddler*", "newborn*", "diaper*", "maternity"],
    "footwear": [
        "shoe*", "sneaker*", "sandal*", "slipper*", "footwear", "heels", "chappal*", "flip flop*", "loafer*",
        "boots", "jutti*", "mojari*", "kolhapuri*",
    ],
    "jewellery": [
        "jewel*", "earring*", "necklace*", "ring", "rings", "bracelet*", "anklet*", "bangle*", "pendant*",
        "mangalsutra*", "nose pin*", "jhumka*", "sterling silver", "gold plated",
    ],
    "bags & accessories": [
        "bag", "bags", "handbag*", "wallet*", "backpack*", "tote*", "belt*", "sunglass*", "eyewear",
        "clutch*", "luggage", "suitcase*",
    ],
    "watches": ["watch", "watches", "wristwatch*"],
    "home decor": [
        "home decor", "decor", "décor", "wall art", "cushion*", "vase*", "candle*", "lamp*", "rug*",
        "carpet*", "curtain*", "planter*", "showpiece*", "painting*", "wall clock*", "figurine*", "idol*",
    ],
    "home & kitchen": [
        "kitchen*", "cookware", "utensil*", "bedsheet*", "bed sheet*", "bedding", "towel*", "dinnerware",
        "drinkware", "bottle*", "storage", "home linen", "table linen", "mattress*", "pillow*", "cutlery",
        "appliance*",
    ],
    "furniture": ["furniture", "sofa*", "chair*", "tables", "beds", "wardrobe*", "bookshel*", "recliner*"],
    "food & beverages": [
        "tea", "teas", "coffee", "snack*", "spice*", "masala*", "pickle*", "achar", "chocolate*", "dry fruit*",
        "nuts", "ghee", "honey", "sweets", "mithai", "namkeen", "millet*", "atta", "jam", "marmalade*",
        "sauce*", "cookie*", "biscuit*", "food", "foods", "beverage*", "juice*", "makhana",
    ],
    "electronics & gadgets": [
        "earbud*", "headphone*", "earphone*", "speaker*", "soundbar*", "smartwatch*", "smart watch*",
        "charger*", "cable*", "power bank*", "powerbank*", "gadget*", "electronic*", "bluetooth", "neckband*",
        "camera*", "laptop*", "keyboard*", "smartphone*", "refurbished", "mobile phone*", "sim card*",
        "esim*",
    ],
    "mobile accessories": ["phone case*", "mobile cover*", "back cover*", "phone cover*", "screen guard*", "tempered glass", "iphone case*"],
    "books & stationery": ["books", "stationery", "notebook*", "journal*", "diary", "diaries", "planner*", "pens", "pencil*", "sticker*", "comic*"],
    "toys & games": ["toy", "toys", "board game*", "puzzle*", "games", "plush*", "soft toy*"],
    "pet supplies": ["pet", "pets", "dog*", "cats", "puppy", "kitten*", "pet food"],
    "sports & fitness": ["fitness", "gym", "yoga", "sports", "cricket", "badminton", "football", "cycling", "dumbbell*", "workout",
        "bicycle*", "mtb", "cycle parts"],
    "art & craft supplies": ["art supplies", "craft supplies", "paints", "canvas", "resin", "diy kit*", "embroidery kit*"],
    "plants & gardening": ["plants", "seeds", "garden*", "succulent*", "potting", "fertili*", "bonsai"],
    "automotive": ["car accessor*", "bike accessor*", "helmet*", "automotive", "car care", "riding gear", "motorcycle*", "motorbike*",
        "used bike*", "second-hand bike*", "royal enfield", "scooter*"],
    "music & instruments": ["vinyl*", "vinyl record*", "guitar*", "ukulele*", "musical instrument*", "turntable*"],
    "collectibles & hobbies": ["collectible*", "diecast", "die-cast", "model car*", "coins", "stamps", "action figure*", "hobby"],
    "body art": ["tattoo*", "temporary tattoo*", "semi-permanent tattoo*"],
    "tobacco & smoking": ["cigar*", "hookah*", "smoking accessor*"],
    "tools & hardware": [
        "tool", "tools", "power tool*", "drill*", "pressure washer*", "tyre inflator*", "hardware",
        "solar light*", "vacuum cleaner*", "inverter*",
    ],
}

MEN_RE = re.compile(r"\b(?:men|men's|mens|man|male|boys?|guys|gents?|him)\b", re.I)
WOMEN_RE = re.compile(r"\b(?:women|women's|womens|woman|ladies|female|girls?|her)\b", re.I)


def _compile(word):
    if word.endswith("*"):
        return re.escape(word[:-1]) + r"\w*"
    return re.escape(word) + r"(?:s|es)?"


PATTERNS = {
    name: re.compile(r"\b(?:" + "|".join(_compile(w) for w in words) + r")\b", re.I)
    for name, words in CATEGORIES.items()
}


def score(texts):
    """texts: list of (text, weight). Returns Counter of category -> score."""
    scores = Counter()
    for text, weight in texts:
        for name, pattern in PATTERNS.items():
            hits = len(pattern.findall(text or ""))
            if hits:
                # one link saying "rings" ten times shouldn't outweigh everything else
                scores[name] += weight * min(hits, 3)
    return scores


def categorize(texts, min_score=3):
    """Returns (category string or None, scores)."""
    scores = score(texts)
    if not scores or scores.most_common(1)[0][1] < min_score:
        return None, scores

    ranked = scores.most_common(2)
    names = [ranked[0][0]]
    if len(ranked) > 1 and ranked[1][1] >= 0.6 * ranked[0][1]:
        names.append(ranked[1][0])  # e.g. "skincare, haircare"
    names = [_gendered(n, texts) if n == "apparel" else n for n in names]
    return ", ".join(names), scores


def _gendered(name, texts):
    blob = " ".join(t for t, _ in texts)
    men, women = len(MEN_RE.findall(blob)), len(WOMEN_RE.findall(blob))
    if men and men >= 3 * women:
        return "men's apparel"
    if women and women >= 3 * men:
        return "women's apparel"
    return "apparel"
