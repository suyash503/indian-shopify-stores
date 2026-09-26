from shopify_india.category import categorize


def test_skincare_store():
    texts = [("Acme – Ayurvedic Skincare", 3), ("face wash", 1), ("serums", 1), ("sunscreen", 1)]
    assert categorize(texts)[0] == "skincare"


def test_apparel_gets_a_gender_when_it_is_clear():
    texts = [("Snitch – Men's Clothing", 3), ("shirts", 1), ("jeans", 1), ("men t-shirts", 1)]
    assert categorize(texts)[0] == "men's apparel"
    texts = [("Women's dresses and tops", 3), ("dresses", 1), ("co-ords", 1)]
    assert categorize(texts)[0] == "women's apparel"


def test_close_second_category_is_kept():
    texts = [("Hair care and skin care", 3), ("shampoo", 1), ("hair oil", 1), ("face wash", 1), ("serums", 1)]
    assert set(categorize(texts)[0].split(", ")) == {"haircare", "skincare"}


def test_word_boundaries():
    # "earrings" must not count as "rings" twice, "team" is not "tea"
    assert categorize([("earrings", 3)])[1]["jewellery"] == 3
    assert "food & beverages" not in categorize([("meet the team", 3)])[1]


def test_too_little_to_go_on():
    assert categorize([("Welcome to our store", 3)])[0] is None
