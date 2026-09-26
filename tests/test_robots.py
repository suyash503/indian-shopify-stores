from shopify_india.robots import RobotsRules

SHOPIFY_LIKE = """
User-agent: *
Allow: /
Disallow: /admin
Disallow: /checkout
Disallow: /*/cart/
Disallow: /collections/*sort_by*
Allow: /account/login
Disallow: /account

User-agent: adsbot-google
Disallow: /
"""


def test_longest_rule_wins_even_after_allow_all():
    rules = RobotsRules.parse(SHOPIFY_LIKE, "IndianShopifyResearch")
    assert rules.allows("/meta.json")
    assert rules.allows("/pages/contact")
    assert not rules.allows("/admin/settings")
    assert not rules.allows("/checkout")


def test_wildcards():
    rules = RobotsRules.parse(SHOPIFY_LIKE, "IndianShopifyResearch")
    assert not rules.allows("/en/cart/123")
    assert not rules.allows("/collections/all?sort_by=price")
    assert rules.allows("/collections/all")


def test_more_specific_allow_beats_disallow():
    rules = RobotsRules.parse(SHOPIFY_LIKE, "IndianShopifyResearch")
    assert rules.allows("/account/login")
    assert not rules.allows("/account")


def test_other_agents_groups_are_ignored():
    rules = RobotsRules.parse(SHOPIFY_LIKE, "IndianShopifyResearch")
    assert rules.allows("/products/anything")


def test_named_group_takes_priority_over_star():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: indianshopifyresearch\nAllow: /\n"
    assert RobotsRules.parse(text, "IndianShopifyResearch").allows("/meta.json")


def test_dollar_anchor_and_empty_disallow():
    rules = RobotsRules.parse("User-agent: *\nDisallow: /*.json$\nDisallow:\n", "x")
    assert not rules.allows("/meta.json")
    assert rules.allows("/meta.json?x=1")
