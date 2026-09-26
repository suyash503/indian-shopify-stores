from shopify_india.extract import clean_image_url, normalize_phone, parse_page, pick_socials, social_profile

PAGE = """
<html><head>
<title>Acme Naturals – Ayurvedic Skincare</title>
<meta name="description" content="Handmade ayurvedic skincare from Jaipur.">
<meta property="og:site_name" content="Acme Naturals">
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Organization", "name": "Acme Naturals",
 "logo": "//acme.in/cdn/shop/files/acme-logo.png?v=17&width=300",
 "sameAs": ["https://www.instagram.com/acmenaturals/", "https://www.facebook.com/acmenaturals"]}
</script>
</head><body>
<header><a href="/"><img src="//acme.in/cdn/shop/files/acme-logo.png?v=17&width=300" alt="Acme"></a></header>
<nav><a href="/collections/face-wash">Face Wash</a><a href="/collections/serums">Serums</a></nav>
<p>Order #9876543210 shipped</p>
<footer>
  <a href="mailto:hello@acme.in">Email us</a>
  <span class="__cf_email__" data-cfemail="3b54495f5e49487b5a58565e155255">[email protected]</span>
  Call +91 98290 12345 · 1800-123-4567
  <a href="https://wa.me/919829012345">WhatsApp</a>
  <a href="https://www.facebook.com/sharer/sharer.php?u=x">Share</a>
  <a href="https://instagram.com/shopify">Shopify</a>
  <img src="/cdn/shop/files/payment-logos.png" alt="payment logos">
</footer>
</body></html>
"""


def test_parse_page_finds_the_basics():
    found = parse_page(PAGE, "https://acme.in/")
    assert "hello@acme.in" in found["emails"]
    assert "+919829012345" in found["phones"]
    assert "1800-123-4567" in found["phones"]
    assert found["logo"] == ("https://acme.in/cdn/shop/files/acme-logo.png?v=17", "structured data")
    assert found["taglines"][0] == ("Handmade ayurvedic skincare from Jaipur.", "meta description")
    assert "face wash" in found["collections"]


def test_order_numbers_outside_footer_are_not_phones():
    found = parse_page(PAGE, "https://acme.in/")
    assert "+919876543210" not in found["phones"]


def test_cloudflare_obfuscated_email_is_decoded():
    found = parse_page(PAGE, "https://acme.in/")
    assert "orders@acme.in" in found["emails"]
    assert all("[email" not in e for e in found["emails"])


def test_socials_skip_share_buttons_and_shopify():
    socials = pick_socials(parse_page(PAGE, "https://acme.in/")["socials"])
    assert socials == {
        "instagram": "https://instagram.com/acmenaturals",
        "facebook": "https://facebook.com/acmenaturals",
    }


def test_social_profile_shapes():
    assert social_profile("https://www.linkedin.com/company/acme-in/about/") == ("linkedin", "https://linkedin.com/company/acme-in")
    assert social_profile("https://www.youtube.com/@acme") == ("youtube", "https://youtube.com/@acme")
    assert social_profile("https://www.youtube.com/watch?v=abc") is None
    assert social_profile("https://x.com/acme?s=20") == ("twitter", "https://x.com/acme")
    assert social_profile("https://www.facebook.com/profile.php?id=123") == ("facebook", "https://facebook.com/profile.php?id=123")
    assert social_profile("https://www.instagram.com/p/Cxyz/") is None


def test_phone_normalisation():
    assert normalize_phone("+91-98290 12345") == "+919829012345"
    assert normalize_phone("098290 12345") == "+919829012345"
    assert normalize_phone("022 4123 4567") == "+912241234567"
    assert normalize_phone("1800 123 4567") == "1800-123-4567"
    assert normalize_phone("+1 (415) 555-0100") == "+14155550100"
    assert normalize_phone("9999999999") is None
    assert normalize_phone("1234567890") is None
    assert normalize_phone("12345") is None


def test_shopify_image_urls_are_full_size():
    assert clean_image_url("//x.in/cdn/shop/files/logo_200x.png?v=1", "https://x.in/") == "https://x.in/cdn/shop/files/logo.png?v=1"
    assert clean_image_url("/files/logo.png?width=500&v=2", "https://x.in/a") == "https://x.in/files/logo.png?v=2"


def test_hero_and_about_text_skip_theme_boilerplate():
    page = """<html><body><header><a href="/about-us">About</a></header><main>
    <h2>Featured collection</h2>
    <h1>Handwoven Banarasi sarees straight from Varanasi looms</h1>
    <p>Free shipping</p>
    <p>We are a family of weavers who have been making silk sarees in Varanasi since 1952, selling direct.</p>
    </main></body></html>"""
    found = parse_page(page, "https://weave.in/")
    assert found["hero"] == "Handwoven Banarasi sarees straight from Varanasi looms"
    assert found["first_paragraph"].startswith("We are a family of weavers")
    assert found["about_links"] == ["https://weave.in/about-us"]


def test_logo_on_shopify_cdn_is_fine_but_collection_images_are_not():
    page = """<html><body>
    <div class="rail"><img src="//cdn.shopify.com/s/files/1/0/collections/Gold_Shop_Logo_1.png"></div>
    <div class="site-logo"><img src="//cdn.shopify.com/s/files/1/0/files/brand.png" alt="Brand"></div>
    </body></html>"""
    assert parse_page(page, "https://brand.in/")["logo"] == ("https://cdn.shopify.com/s/files/1/0/files/brand.png", "logo image")
