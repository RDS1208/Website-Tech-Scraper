# Website Tech Scraper

Detects technologies on public websites and saves the evidence for each match. It also identifies Shopify stores and reports the tracking products found on their pages.

## Stack

| Technology | Role |
| --- | --- |
| Python and `asyncio` | Run concurrent crawls and limit active HTTP requests. |
| HTTPX | Fetch homepages and internal pages and collect selected response headers. |
| Beautiful Soup | Extract scripts, stylesheets, generator metadata, and links from HTML. |
| Playwright and Chromium | Render homepages and observe resources and `fetch` or XHR activity. |
| PyArrow | Read the `root_domain` column from the input Parquet file. |

Detection rules live in [rules/rules.json](rules/rules.json). Each match stores its source and value, such as a script URL or a network endpoint.

## Run the project

Use Python 3.10 or later. Run the commands from the repository root. Install Chromium if you plan to use `--render`.

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Crawl the supplied domains with homepage rendering and internal links enabled.

```sh
python -m scripts.main domains.parquet --render --follow-links
```

| Flag | Effect |
| --- | --- |
| `--render` | Renders each accessible homepage in Chromium to collect JavaScript and network signals. |
| `--follow-links` | Fetches up to four internal pages per domain with HTTPX. |
| `--resume` | Continues from the checkpoint written on Ctrl+C. Use the same input and crawl flags. |
| `--shopify` | Selects the Shopify competitor report in `scripts.report`. |

A completed crawl writes [results/results.json](results/results.json). You can inspect the included results immediately.

```sh
python -m scripts.analyze_res
python -m scripts.report
python -m scripts.report --shopify
python -m unittest discover -s scripts/tests -v
```

The analyzer reapplies the rules to saved signals. The default report groups the leaderboard by category. The Shopify report shows the page URL and evidence for each competitor match.

## Saved crawl results

| Metric | Count |
| --- | ---: |
| Input domains | 200 |
| Accessible homepages | 143 of 200 (71.5%) |
| Domains with at least one detection | 140 |
| Distinct technologies and components | **301** |
| Domain–technology matches with evidence | 1,221 |
| Internal pages fetched successfully | 414 of 441 |
| Additional homepage matches from Chromium | 149 across 68 domains |
| Additional matches from internal pages | 52 across 31 domains |
| Shopify stores detected | 2 |
| Shopify stores with a tracked competitor detected | 0 |

### Detection example

On `herbalwise.ie`, the crawler found the script `/cdn/shop/t/3/assets/global.js`. Its path starts with `/cdn/shop/t/`, the prefix used by the Shopify theme asset rule. The crawler reported Shopify and saved the script URL alongside the match so the detection can be checked. [Detection rules](rules/rules.json) · [Saved evidence](results/results.json)

### Single-site Shopify report

Run this example in PowerShell from the repository root with the project environment active. It crawls `gld.com` and passes the results to the same report used by `--shopify`. The report checks for Shopify and lists tracked competitors with their page URLs and evidence. The single-site results are stored in a temporary directory.

```powershell
@'
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.main import crawl_domains, save_json
from scripts.report import generate_shopify_report

results = asyncio.run(crawl_domains(["https://gld.com/"], render=True, follow_links=True))
if "error" in results[0]:
    raise SystemExit(results[0]["error"])
with TemporaryDirectory() as directory:
    path = Path(directory) / "results.json"
    save_json(path, results)
    generate_shopify_report(path)
'@ | python -
```

On November 26, 2026, the rendered crawl of `gld.com` returned these examples of script evidence. This was a separate run from the 200-domain dataset.

| Technology | Observed script URL |
| --- | --- |
| Northbeam | `https://j.northbeam.io/vendor/nb-sp.min.js` |
| Elevar | `https://shopify-gtm-suite.getelevar.com/getelevar/3.40.0/dl-web-pixel.js` |

### Top 10 technologies and components

Counts come from `python -m scripts.report`. A technology counts once per domain, even when it appears on several pages.

| Rank | Technology | Websites |
| ---: | --- | ---: |
| 1 | jQuery | 69 |
| 2 | Google Fonts | 62 |
| 3 | WordPress | 57 |
| 4 | jQuery Migrate | 46 |
| 5 | Google Analytics | 44 |
| 6 | Google tag | 44 |
| 7 | Cloudflare | 39 |
| 8 | Apache HTTP Server | 37 |
| 9 | WordPress Hooks | 27 |
| 10 | WordPress i18n | 27 |

### Performance

The extractor used to build a Beautiful Soup tree for each type of signal. It now builds one tree per HTML document and shares it across the extractors, including the internal link extractor when enabled.

| Benchmark | Separate trees | Shared tree | Time saved |
| --- | ---: | ---: | ---: |
| Extraction on the same 354 documents | 21.20 s | 5.48 s | 74.1% |
| Live crawl of the first 100 input domains with `--render --follow-links` | 184.95 s | 176.47 s | 4.6% |

Both versions returned identical signals and links for all 354 documents in the extraction benchmark. The live figures cover one run per version and include network and Chromium time. Both runs accessed 70 homepages. The first reached 212 internal pages and the second reached 214.

## Limitations and future work

The crawler measures what is visible on the pages it visits. Some tools load after consent, during checkout, or on the server, so a crawl can miss them. The output keeps an error entry for each inaccessible domain, making the coverage visible.

One bottleneck was the documentation research behind new rules. The crawler can list an unfamiliar script in seconds, but a filename such as `global.js` can appear in many products. Checking vendor documentation or public source code takes time and helps identify which part of the URL actually distinguishes the product.

**Scaling.** To crawl 3 million domains in 30–60 days, I would target an average of 0.58–1.16 completed domains per second. I would read domains in batches and use two bounded queues. HTTPX workers would fetch homepages and internal links under per-host limits. Chromium workers would render selected homepages while HTTPX continues fetching. Once all tasks for a domain finish, I would save its result in a batch and use those saved records to resume after an interruption.

I would size each worker pool from a representative run by multiplying its target tasks per second by its average seconds per task. If the render queue kept growing while HTTPX kept up, I would add Chromium workers as memory allowed. I would also test a shorter browser wait or navigation timeout on the same sample and compare both runtime and detections before changing the defaults. [Python queues](https://docs.python.org/3/library/asyncio-queue.html) · [Playwright navigation](https://playwright.dev/python/docs/api/class-page#page-goto)

**Discovering technologies.** Extend the analyzer's candidate list to cover unmatched scripts, CSS, metadata, headers, and network URLs from saved pages. Group recurring signatures, verify each signature with vendor documentation or a public example, and add a specific rule. Rerun `scripts.analyze_res` to apply it to the saved crawl.
