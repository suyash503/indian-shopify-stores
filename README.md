# Indian Shopify Stores

This project finds online stores which are built on Shopify and run from India, and for each store it collects:
domain, emails and phone numbers, social media links, category, tagline, logo and the Indian state.

**Final result: 1,066 verified Indian Shopify stores**, in [`output/stores.csv`](output/stores.csv) (opens in Excel) and [`output/stores.json`](output/stores.json).
The full numbers (how many sites were checked, how many were dropped and why, how often each field was found) are in [`output/report.md`](output/report.md). The pipeline generates this file itself.

I have tried to keep every row traceable. For each store the CSV also tells:
- why I have called it Indian (`india_evidence`)
- where the state came from (`state_source`)
- which list the store was found from (`found_via`)

For every site that was checked, including the rejected ones and the reason for rejecting, see [`data/verified.jsonl`](data/verified.jsonl).

---

## How I approached it

Before writing any code, I opened a few Indian Shopify stores I already knew (boAt, Bombay Shaving Company, Snitch) and went through their page source. Shopify stores leave a lot of signs in their HTML, but the most useful thing I found was that **every Shopify store has a public page at `/meta.json`**.

For example, `boat-lifestyle.com/meta.json` shows:

```json
{"name": "boAt Lifestyle", "city": "Mumbai", "province": "Maharashtra", "country": "IN", "currency": "INR",
 "myshopify_domain": "boatlifestylein.myshopify.com", "id": 5789384802, ...}
```

This one small file tells three things together:
1. The site is on Shopify (no other website has this file with a `myshopify_domain` in it).
2. The business is in India (`country`).
3. Which state it is in (`province`).

So I first wrote a 15-line script, tried it on 5 stores I knew, and checked that the answers were correct. After that, the job was basically to:
1. find enough candidate websites,
2. run this check on all of them politely,
3. collect the remaining fields from the Indian ones.

Once the first full run was done, I went through the output store by store and fixed whatever was coming wrong. For example:
- order numbers were getting picked up as phone numbers;
- a search icon was getting picked up as a logo;
- some stores had no meta description at all.

The commit history shows this order.

---

## How the pipeline works

It runs in 5 steps. Each step is one command, and each one saves its output to a file which the next step reads.

```
 Step 1            Step 2               Step 3             Step 4               Step 5
 candidates  ───>  verify         ───>  recheck      ───>  enrich         ───>  export
 (make a list      (is it Shopify?      (second chance     (collect the 7       (remove duplicates,
  of websites)      is it Indian?)       for hidden         fields from the      write CSV, JSON
                                         Shopify stores)    Indian stores)       and report)
```

If a step stops in between (laptop sleeps, internet goes), just run it again. It continues from where it stopped.

### Step 1: Making the list of candidate websites

I have used two free sources:

| source | what I took from it | how many |
|---|---|---|
| [Tranco](https://tranco-list.eu/) (list `L5PZ4`): a ranking of the world's 1 million most-visited websites | all Indian domains: `.in`, `.co.in`, `.org.in` etc. | 11,601 |
| [Common Crawl](https://commoncrawl.org/): a free public copy of a big part of the internet, from its last 3 monthly crawls | every `something.myshopify.com` address it has seen | 22,386 |

Why two sources?
- **Tranco** is small and a good share of it is useful (around 8% of the `.in` sites are on Shopify, and almost all of those are Indian). But it only finds brands which use a `.in` domain.
- **Common Crawl** fills that gap. Every Shopify store gets a free backup address like `brandname.myshopify.com`, and it keeps working even after the brand buys its own `.com` domain. So this list catches Indian brands on `.com` domains. It is all Shopify, but only around 1.5% of it is Indian, so it is slow going.

What I did not use:
- **Google search tricks**: against Google's terms, CAPTCHAs come quickly, and results can't be repeated.
- **BuiltWith, Store Leads and similar tools**: paid, and the brief prefers free sources.

### Step 2: Is it Shopify? Is it Indian?

Two checks, the cheap one first.

1. **Address check (DNS).** Every domain name points to a server address, like an entry in a phone book. Shopify stores point to Shopify's own servers (addresses starting `23.227.38.`). Looking this up does not even touch the website, and it removes around 90% of the `.in` list straightaway.
2. **The `/meta.json` check.** For the remaining sites, I request `/meta.json`. If the file is there, the site is Shopify. The same file tells the country and the state.

I stopped this step after checking 18,743 of the 33,987 candidates, since by then I had well over 1,000 stores. All of Tranco was checked; the remaining ones are Common Crawl addresses, where only around 1.5% are Indian. `verify` can be run again to continue from there.

### Step 3: Second chance for hidden Shopify stores (`recheck`)

Some Shopify stores put another company's server (a CDN) in front of Shopify, so their address does not point to Shopify and step 2 skips them. I noticed this by checking 150 of the rejected `.in` sites by hand, and 3 of them were actually Indian Shopify stores. So this step asks all the rejected `.in` sites for `/meta.json` anyway. It found 33 more stores.

### Step 4: Collecting the fields (`enrich`)

For every Indian store, the program opens:
- the homepage;
- the contact page (whatever the homepage links to, otherwise `/pages/contact-us` or `/pages/contact`);
- Shopify's standard "Contact information" page, only if email or phone is still missing;
- the About page, only if there is no tagline;
- `/products.json`, the store's product list, only if the category is still not clear.

So it is 2 to 5 pages per store. How each field is found is explained [below](#how-each-field-is-found).

### Step 5: Removing duplicates and saving (`export`)

- The same store can come up twice, once with its own domain (from Tranco) and once with its `myshopify.com` address (from Common Crawl). Every Shopify store has a unique shop number in `meta.json`, so I have used that to keep only one row per store.
- The domain in the output is the store's **main** domain as per Shopify. If a store has its own domain, that is used, otherwise the `myshopify.com` one.

---

## What I have counted as "Indian"

**A store is Indian if the business runs from India.** For this I mainly go by the business address the store owner has filled in Shopify's settings, which shows as `country` in `meta.json`. Shopify uses this address for taxes and invoices, so owners have a reason to keep it correct.

| Shopify business address | other signs | my decision |
|---|---|---|
| India | anything | **Indian**, whatever the domain or currency. An Indian exporter selling in US dollars is also Indian. |
| outside India | prices in rupees, or a `.in` domain | **maybe**: then I check the website itself. It is counted only if the site shows a GST number, or an Indian address (PIN code with state or city) along with a +91 number or rupee prices. |
| outside India | neither | **not Indian** |

On the two examples given in the brief:

- **Indian brand on a `.com` domain**: counted. The domain does not matter. For example, `bombayshavingcompany.com` is found through its `myshopify.com` address, and its Shopify address is in Haryana.
- **Brand hosted abroad but with Indian owners**: not counted, unless the store itself runs from India. If a store's business address is in the US and it sells in dollars, I have not counted it, even if the founders are Indian. Checking ownership for thousands of stores is not possible, and such a store works like a US business anyway.

The opposite case comes up quite often. `levi.in`, `jockey.in` and `uspoloassn.in` are foreign brands, but these particular stores are run by Indian companies from Indian addresses, so they are counted.

One example that got rejected: `amantelingerie.in` sells in rupees on a `.in` domain, but its Shopify address is in Sri Lanka and its site did not show an Indian GST number or address. If Rivyou would like to include such cases, the `india_evidence` column makes it easy to filter differently.

---

## How each field is found

For each field, the sources are tried in this order and the first one that works is used.

| field | how it is found |
|---|---|
| **Domain** | From `meta.json`: the store's main domain. |
| **Emails** | "Email us" (`mailto:`) links, then emails hidden by Cloudflare's email protection (these can be decoded), then emails written in the footer, contact page or contact-information page. Fake ones like `you@example.com` and image names like `logo@2x.png` are removed. The store's own-domain email comes first. Maximum 6. |
| **Phones** | "Call us" (`tel:`) links, then WhatsApp links, then Indian mobile, +91 landline and 1800 toll-free numbers written in the footer and contact pages. All saved as `+91XXXXXXXXXX`. Numbers elsewhere on the homepage are ignored, because order IDs and product codes also look like 10-digit numbers. Maximum 6. |
| **Socials** | Instagram, Facebook, X/Twitter, LinkedIn and YouTube links on the pages. "Share on Facebook" buttons, links to single posts and videos, and Shopify's own accounts (some themes link them) are skipped. |
| **Category** | Keyword counting on the store's own words: the page title and description (these count 3 times), the names of collections in the menu (like "Face Wash" or "Kurtas"), and product types from `/products.json` if needed. If two categories are close, both are kept ("haircare, skincare"). All the keyword lists are in [`category.py`](shopify_india/category.py). |
| **Tagline** | The description the store has written for Google (meta description), then the social-sharing description, then the store description in `meta.json`, then the first proper paragraph of the About page, then the main heading on the homepage. If the "description" is just the store name again, it is skipped. |
| **Logo** | The logo declared in the page's structured data (a hidden block of details meant for Google), then an image in the header marked as "logo", then a header image that links to the homepage. Payment icons and badges are ignored. The image link is cleaned to get the full-size file. If the logo is drawn in code (an inline SVG), it is saved as a file in [`output/logos/`](output/logos). It never uses the small browser-tab icon (favicon). |
| **State** | `province` from `meta.json`, then the GST number (its first two digits are a state code, e.g. `27` is Maharashtra), then a state name near a PIN code on the site, then a known city near a PIN code. |

---

## Wrong matches and tricky cases, and how they are handled

| case | what happens |
|---|---|
| Looks like Shopify but is not, e.g. a WordPress site with a Shopify "Buy" button | It does not have `/meta.json`, so it is rejected. |
| Domain still points to Shopify but the store is closed | `meta.json` gives error 402 (closed) or 404. Rejected, with the reason saved. |
| Store is password-protected (not launched yet) | `/meta.json` still works for these, but the homepage sends us to `/password`. Dropped. |
| Demo and test stores made by theme and app developers (e.g. `bookeasy-demo-store`, `gocart-demo`) | They pass every Shopify and India check but are not real businesses. Dropped if the store name or address says demo, test, theme etc., or if it has no own domain and no email, phone or social links at all. |
| A `.in` domain which is not Indian | Its Shopify address says so. Rejected unless the site proves it is Indian. |
| Same store under two domains | Only one row, using the unique shop number. |
| Store has moved (`snitch.co.in` says "we are now snitch.com") | Both are live Shopify stores with different shop numbers, so both are kept. |
| Shopify store with a fully custom front end (headless) | No `/meta.json` on its main domain, so it is **missed**. See limitations. |
| Emails hidden by Cloudflare | Decoded. |
| "Order #9876543210" | Not treated as a phone number. |
| Share buttons, YouTube videos, `instagram.com/shopify` | Not the brand's own profile, so skipped. |
| Logo is only the store name written in text | No logo image exists, so the field is kept empty and the reason is noted. |

---

## Being polite to the websites

- **Speed limit of 8 requests per second in total.** All these stores run on Shopify's servers, so even though each store is a different website, it is all one company's system. So I have kept one common speed limit for the whole program, not one per website. If any store says "too many requests" (error 429), every part of the program slows down.
- **Following robots.txt.** Every website has a `robots.txt` file which says which pages bots are allowed to visit. It is checked before every request, including when one address redirects to another.
- **Wrote my own small robots.txt reader.** Python's built-in one gives a wrong answer for Shopify: it goes by the first rule that matches, and Shopify's file starts with "Allow everything". So it would even allow `/admin` and `/checkout`. [`robots.py`](shopify_india/robots.py) follows the official rule instead (RFC 9309: the most specific rule wins).
- **All the pages the program needs are allowed** by Shopify's default robots.txt: `/meta.json`, homepages, `/pages/...`, `/policies/...` and `/products.json`.
- **Identifies itself.** The program's user-agent (the name it sends with every request) mentions this project and links to this repo.
- **Saves every downloaded page on disk.** When I fix something and run again, nothing is downloaded a second time.
- **Common Crawl.** Common Crawl's own robots.txt blocks all bots. As far as I understand, this is to keep search engines from crawling their data pages. Their index is meant to be used by programs, and the brief also suggests Common Crawl, so I have used it gently: one request at a time, with waiting and retrying on errors, saved on disk, around 26 requests per monthly crawl. I am mentioning it here openly instead of hiding it.

In the steps where I logged it (recheck and enrich, around 8,500 requests), Shopify replied "too many requests" only 4 times.

---

## Missing fields and the reasons

From [`output/report.md`](output/report.md):

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

Why a field can be missing:

- **Phone**: many stores give only an email, a WhatsApp chat button (it loads through JavaScript, so it is not in the page's HTML) or a contact form. A few put the number inside an image.
- **Email**: bigger brands often use a contact form or a helpdesk widget instead of showing an email address.
- **Socials**: some stores load their social icons through JavaScript or an app, so the links are not in the page's HTML. For example, `suta.in` mentions Instagram only inside its loyalty-points app data. I have not used a real browser to run JavaScript (see limitations).
- **Logo**: 14 stores have only their name written in text as the logo, so no logo image exists. The rest keep the logo somewhere my rules don't look, like a background image.
- **Category**: stores that say very little about what they sell. I have kept these empty rather than guessing.
- **State**: this is almost never missing, since Shopify's address has the state.
- **Tagline**: stores that have no description anywhere: not for Google, not in Shopify, not on an About page.

---

## Limitations, and what will break at 10x or 100x

- **The candidate list is the real limit.** Tranco has only popular websites, so most small Indian stores are not in it. And only around 1.5% of the Common Crawl `myshopify.com` list is Indian. For 10x more stores I would collect `.in` domains from certificate-transparency logs (public logs of every HTTPS certificate issued) and put them through the same DNS check.
- **Common Crawl's search server is slow and times out often.** I had to ask for small pages of around 3,000 rows. At 100x, I would query Common Crawl's bulk data files directly (with DuckDB or Amazon Athena) in one go.
- **The verify step is slow on purpose, because of the speed limit.** Each Common Crawl candidate needs 3 requests. At 100x it would take days at 8 requests per second, and using many IP addresses to go faster is exactly the impolite thing. The better fix is to remove more candidates with cheap checks like DNS before asking the website anything.
- **Headless Shopify stores are missed.** These build their own front end and only use Shopify at the back. Catching them needs checks on the page HTML, and that also brings back the "Buy button" type of wrong matches, so it needs care.
- **`/meta.json` is not officially documented by Shopify.** If it is removed some day, detection can use the `x-shopid` header and the `Shopify` variable in the page. The India check can use currency, address and GST number.
- **No JavaScript.** Some contact details and social links appear only after the page's JavaScript runs. A real browser (like Playwright) would find more of them, but it is around 50 times slower per store.
- **Categories are keyword-based.** This works well for common stores but not for unusual ones (gift shops, general stores). With more time, I would use an LLM with a fixed list of categories and test it on 100 stores labelled by hand.
- **Storage.** Plain files work fine up to around a million records. Beyond that I would use a queue, multiple workers and a database.

With more time I would also:
- check that email domains can actually receive mail (MX records);
- hand-check a random sample of 100 stores properly to measure accuracy;
- re-run every month to remove stores that have closed.

---

## How to run

Needs Python 3.11 or above.

```bash
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m shopify_india candidates   # Step 1: make the list -> data/candidates.csv          (~8 min)
python -m shopify_india verify       # Step 2: Shopify? Indian? -> data/verified.jsonl       (~10 min for Tranco, then ~1 site/sec for Common Crawl)
python -m shopify_india recheck      # Step 3: second chance for hidden Shopify stores       (~1 hour)
python -m shopify_india enrich       # Step 4: collect fields -> data/stores.jsonl           (~25 min)
python -m shopify_india export       # Step 5: output/stores.csv, stores.json, report.md     (a few seconds)

python -m pytest                     # tests
```

Useful options:

| option | what it does |
|---|---|
| `verify --target 1200` | stops once 1,200 Indian stores are found |
| `verify --limit 500` | tries only the first 500 candidates, good for a quick test |
| `enrich --redo` | extracts everything again from the saved pages: no internet needed, takes a few minutes |
| `--rate 5` | changes the speed limit |

### What is where

```
shopify_india/
  fetch.py      all internet requests go through here: speed limit, robots.txt, retries, saving pages
  robots.py     the robots.txt reader
  sources.py    Step 1: Tranco and Common Crawl lists
  shopify.py    Step 2: DNS check and /meta.json check
  india.py      what counts as Indian; states, GST numbers, PIN codes
  extract.py    reads the fields out of one web page
  category.py   keyword lists for categories
  pipeline.py   Steps 2 to 4
  export.py     Step 5: CSV, JSON and the report
tests/          tests for robots.txt, field extraction, India checks and categories
data/           the list of candidates and the result of every step
output/         the final stores.csv, stores.json, report.md and saved logos
```

---

## Time spent

Around 2 days (26 to 28 Sept 2026) from first commit to submission, a good part of which was waiting for the long crawl runs to finish on my home internet.
