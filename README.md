# Website Tech Scraper

Requires Python 3.10+, internet access, and a Parquet file with a `root_domain` column (such as `domains.parquet`). Run from the project directory:

```sh
python -m pip install -r requirements.txt
python main.py domains.parquet
```

Fetches up to 10 domains concurrently. Extracts script URLs, generator metadata, and inline JavaScript as text, then matches them against `rules.json` to identify technologies. Saves the collected signals, findings, and request errors to `results.json` in input order.

Press **Ctrl+C** during the crawl to save completed results in `results.partial.tmp`. Run `python main.py domains.parquet -resume` to continue with the remaining domains. A complete crawl saves the full results to `results.json` and clears the temporary file.

Use `--render` to collect additional signals with Chromium after each successful HTTPX fetch. The crawler renders up to two pages concurrently. Browser failures are recorded in `render_error` alongside the HTTPX results.

```sh
python -m playwright install chromium
python main.py domains.parquet --render
python main.py domains.parquet --render -resume
```

The crawler also collects linked stylesheet URLs and final-response headers named in `rules.json`. A `css_url` rule uses the same hostname and path filters as script URLs. A `header` rule pairs a header name with a `header_product`, such as `Server` and `nginx`.

Run `python analyze_res.py` to recheck saved results and print rankings for scripts, meta generators, HTTP headers, and stylesheets. Rerun the crawler to collect missing signals for older results or to capture a newly configured header.
