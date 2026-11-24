# Website Tech Scraper

Requires Python 3.10+, internet access, and a Parquet file with a `root_domain` column (such as `domains.parquet`). Run from the project directory:

```sh
python -m pip install -r requirements.txt
python main.py domains.parquet
```

Fetches up to 10 domains concurrently. Extracts script URLs, generator metadata, and inline JavaScript as text, then matches them against `rules.json` to identify technologies. Saves the collected signals, findings, and request errors to `results.json` in input order.

For domains supplied without a scheme, the crawler tries HTTPS after certain HTTP errors, including `403`, `404`, and `409`. Failed requests record the exception type and, when available, the failed URL and `Retry-After` header.

Press **Ctrl+C** during the crawl to save completed results in `results.partial.tmp`. Run `python main.py domains.parquet -resume` to continue with the remaining domains. A complete crawl saves the full results to `results.json` and clears the temporary file.

Use `--render` to collect additional signals with Chromium after each successful HTTPX fetch. The crawler renders up to two pages concurrently. Browser failures are recorded in `render_error` alongside the HTTPX results.

Chromium also collects destinations of `fetch` and XHR requests in `network_urls`. These entries contain the scheme, hostname, and path. A `network_url` rule matches the hostname and path, and the analyzer ranks both observed endpoints and endpoints that still need a rule.

```sh
python -m playwright install chromium
python main.py domains.parquet --render
python main.py domains.parquet --render -resume
```

Use `--follow-links` to visit up to three internal pages linked from each homepage. The crawler prefers a mix of product, collection, and contact pages and follows secondary redirects only on the same hostname. Secondary pages use HTTPX. If both flags are enabled, Chromium renders the homepage.

```sh
python main.py domains.parquet --follow-links
python main.py domains.parquet --render --follow-links
python main.py domains.parquet --render --follow-links --resume
```

Resume with the same flags as the interrupted run. The crawler prints the number of internal pages accessed and how many detections they added. The output stores each visited page and its evidence in `linked_pages`. The `linked_added_technologies` field lists names absent from the homepage findings. `analyze_res.py` recalculates this comparison, and `report.py` includes the linked findings once per domain.

The crawler also collects linked stylesheet URLs and final-response headers named in `rules.json`. A `css_url` rule uses the same hostname and path filters as script URLs. A `header` rule pairs a header name with a `header_product`, such as `Server` and `nginx`.

Run `python analyze_res.py` to reapply the rules to the saved results and review the most common signals. Run `python report.py` to list technologies by the number of domains where they were found. A new crawl is needed to collect signals that are missing from the saved results.

## Saved crawl results

Each input domain has an entry in [results.json](results.json), including domains that returned an error.

| Metric | Count |
| --- | ---: |
| Input domains | 200 |
| Homepages fetched successfully | 143 |
| Domains with at least one technology detected | 140 |
| Distinct technology names across homepages and internal pages | **290** |
| Domain–technology pairs with evidence | **1,220** |
| Successful Playwright homepage comparisons | 143 |
| Additional homepage pairs found only after rendering | 170 across 71 domains |
| Pairs with fetch or XHR evidence | 103 across 61 domains |
| Pairs identified solely by fetch or XHR evidence | 17 across 16 domains |
| Internal pages fetched successfully | 321 of 339 attempted |
| Additional pairs found only on internal pages | 42 across 25 domains |
| Domains identified as Shopify stores | 2 |

## Shopify analytics validation

The saved crawl produced zero matches for these four products. Separate homepage crawls tested the rules on stores with documented or captured signals. The table lists the evidence returned by those checks.

| Product | Store tested | Evidence returned by the crawler | Where it appeared |
| --- | --- | --- | --- |
| Northbeam | `gld.com` | `j.northbeam.io/vendor/nb-sp.min.js` and the loader under `/ota-sp/` | Playwright script URLs. [Network capture](https://whogetsmydata.com/scan/142533) |
| Triple Whale | `bedjet.com` | `window.TriplePixelData` | Inline JavaScript in the HTTPX response. [Vendor case study](https://www.triplewhale.com/case-studies/bedjet) |
| Elevar | `comfrt.com` | Reference to `shopify-gtm-suite.getelevar.com/configs/…/config.js` | Inline JavaScript in the HTTPX response. [Network capture](https://whogetsmydata.com/scan/208138) |
| Elevar | `brighton.com` | Elevar's `config.js` and `dl-web-pixel.js` under the vendor hostname | Playwright script URLs. [Network capture](https://whogetsmydata.com/scan/204644) |
| Littledata | `olly.com`, `cellucor.com` | `LittledataLayer` | Inline JavaScript in the HTTPX response. [OLLY network capture](https://whogetsmydata.com/website/olly.com) · [Littledata integration documentation](https://www.twilio.com/docs/segment/connections/sources/catalog/libraries/website/shopify-littledata) |

To reproduce a single store check without replacing the benchmark file, call the crawler directly. Replace the domain and product name to check another row.

```sh
python -c "import asyncio; from main import crawl_domains; result = asyncio.run(crawl_domains(['gld.com'], render=True))[0]; print(result.get('error') or result.get('render_error') or [t for t in result['technologies'] if t['name'] == 'Northbeam'])"
```

These checks show which integrations leave visible evidence on a public homepage. Coverage can vary with the store's configuration, consent, and integrations that run only at checkout or on the server.
