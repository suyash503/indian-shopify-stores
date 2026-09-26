from shopify_india import india


def test_state_names_codes_and_old_names():
    assert india.normalize_state("MH") == "Maharashtra"
    assert india.normalize_state("maharashtra") == "Maharashtra"
    assert india.normalize_state("Orissa") == "Odisha"
    assert india.normalize_state("New Delhi") == "Delhi"
    assert india.normalize_state("Bavaria") is None


def test_first_pass():
    assert india.first_pass({"country": "IN", "currency": "USD"}, "brand.com") == "yes"
    assert india.first_pass({"country": "AE", "currency": "INR"}, "brand.com") == "maybe"
    assert india.first_pass({"country": "AE", "currency": "AED"}, "brand.in") == "maybe"
    assert india.first_pass({"country": "US", "currency": "USD"}, "brand.com") == "no"


def test_shopify_address_decides_when_it_says_india():
    ok, evidence = india.decide({"country": "IN", "currency": "USD"}, "brand.com", "", [])
    assert ok and evidence == ["Shopify business address in India"]


def test_foreign_address_needs_proof_on_the_site():
    meta = {"country": "AE", "currency": "INR"}
    assert not india.decide(meta, "brand.in", "Ships worldwide", [])[0]
    assert india.decide(meta, "brand.in", "GSTIN: 27AAPFU0939F1ZV", [])[0]
    address = "Unit 4, Andheri East, Mumbai, Maharashtra 400069"
    assert india.decide(meta, "brand.in", address, ["+919829012345"])[0]


def test_find_state_order():
    assert india.find_state({"country": "IN", "province": "Karnataka"}, "GSTIN 27AAPFU0939F1ZV") == ("Karnataka", "Shopify business address")
    assert india.find_state({"country": "AE"}, "GSTIN 27AAPFU0939F1ZV") == ("Maharashtra", "GSTIN")
    assert india.find_state({}, "Plot 7, Sector 62, Noida 201301") == ("Uttar Pradesh", "city in address on site")
    assert india.find_state({}, "Call us on 98290 12345") == (None, None)


def test_pin_codes_skip_phone_numbers_and_prices():
    assert india.address_snippets("call 9829012345 or pay ₹1,20,000") == []
    assert len(india.address_snippets("Jaipur 302 001")) == 1
