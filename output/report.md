# Run report

## Funnel

| step | count |
|---|---:|
| candidates from commoncrawl | 22,386 |
| candidates from tranco | 11,601 |
| checked from tranco | 11,601 |
| checked from commoncrawl | 7,142 |
| confirmed Shopify (meta.json) from tranco | 1,014 |
| confirmed Shopify (meta.json) from commoncrawl | 6,513 |
| first pass: Shopify address in India | 1,090 |
| first pass: maybe (INR or .in, address elsewhere) | 2 |
| first pass: not Indian | 6,435 |
| unique shops enriched | 1,092 |
| homepage failed during enrich | 15 |
| "maybe" stores confirmed Indian from the site | 0 |
| "maybe" stores rejected | 2 |
| **final Indian stores** | **1,066** |

## Why candidates were dropped

| reason | count |
|---|---:|
| dns elsewhere, then meta.json returned 404 | 6,265 |
| dns elsewhere, then robots.txt unreachable | 1,591 |
| dns elsewhere, then no Shopify meta.json | 1,495 |
| disallowed by robots.txt | 471 |
| dns: no dns | 465 |
| dns elsewhere, then meta.json returned 403 | 384 |
| dns elsewhere, then disallowed by robots.txt | 229 |
| robots.txt unreachable | 95 |
| meta.json returned 404 | 68 |
| dns elsewhere, then meta.json returned 500 | 40 |
| dns elsewhere, then meta.json returned 400 | 26 |
| dns elsewhere, then meta.json returned 410 | 14 |

## Field coverage

| field | filled | missing | filled % |
|---|---:|---:|---:|
| domain | 1,066 | 0 | 100.0% |
| at least one email | 1,005 | 61 | 94.3% |
| at least one phone | 949 | 117 | 89.0% |
| email or phone | 1,043 | 23 | 97.8% |
| at least one social | 922 | 144 | 86.5% |
|   instagram | 914 | 152 | 85.7% |
|   facebook | 759 | 307 | 71.2% |
|   twitter | 276 | 790 | 25.9% |
|   linkedin | 233 | 833 | 21.9% |
|   youtube | 615 | 451 | 57.7% |
| category | 1,043 | 23 | 97.8% |
| tagline | 1,018 | 48 | 95.5% |
| logo | 1,050 | 16 | 98.5% |
| state | 1,066 | 0 | 100.0% |

## Where the state came from

| source | stores |
|---|---:|
| Shopify business address | 1,066 |

## Where the logo came from

| source | stores |
|---|---:|
| structured data | 753 |
| header image | 226 |
| logo image | 65 |
| text only (no logo image on the site) | 14 |
| og:image | 3 |
| inline svg, saved as a file | 3 |
| missing | 2 |

## Where the tagline came from

| source | stores |
|---|---:|
| meta description | 881 |
| about page | 105 |
| missing | 48 |
| homepage hero text | 22 |
| og:description | 5 |
| store description (meta.json) | 5 |

## Categories

| value | stores |
|---|---:|
| apparel | 87 |
| ethnic wear | 79 |
| electronics & gadgets | 74 |
| jewellery | 68 |
| health & nutrition | 51 |
| men's apparel | 44 |
| women's apparel | 44 |
| home & kitchen | 38 |
| food & beverages | 31 |
| footwear | 30 |
| fragrances | 28 |
| bags & accessories | 26 |
| unknown | 23 |
| skincare | 23 |
| kids & baby | 22 |
| home decor | 20 |
| automotive | 20 |
| sports & fitness | 18 |
| watches | 17 |
| toys & games | 17 |
| books & stationery | 16 |
| mobile accessories | 13 |
| plants & gardening | 12 |
| makeup | 12 |
| haircare | 11 |
| collectibles & hobbies | 10 |
| furniture | 10 |
| ethnic wear, women's apparel | 6 |
| skincare, haircare | 6 |
| pet supplies | 5 |
| women's apparel, ethnic wear | 5 |
| tobacco & smoking | 4 |
| ethnic wear, apparel | 4 |
| home decor, home & kitchen | 4 |
| apparel, sports & fitness | 3 |
| ethnic wear, men's apparel | 3 |
| kids & baby, apparel | 3 |
| home decor, furniture | 3 |
| health & nutrition, skincare | 3 |
| footwear, bags & accessories | 3 |

## States

| value | stores |
|---|---:|
| Maharashtra | 205 |
| Delhi | 152 |
| Tamil Nadu | 109 |
| Gujarat | 96 |
| Uttar Pradesh | 96 |
| Karnataka | 94 |
| Haryana | 80 |
| Rajasthan | 54 |
| Kerala | 38 |
| West Bengal | 35 |
| Punjab | 29 |
| Telangana | 24 |
| Madhya Pradesh | 18 |
| Chandigarh | 6 |
| Andhra Pradesh | 6 |
| Chhattisgarh | 6 |
| Uttarakhand | 5 |
| Jharkhand | 4 |
| Jammu and Kashmir | 3 |
| Bihar | 2 |
| Himachal Pradesh | 1 |
| Mizoram | 1 |
| Dadra and Nagar Haveli and Daman and Diu | 1 |
| Puducherry | 1 |

## Final stores by source

| source | stores |
|---|---:|
| tranco | 1,010 |
| commoncrawl | 56 |
