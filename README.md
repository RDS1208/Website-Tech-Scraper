# Website Tech Scraper

Requires Python 3.10+, internet access, and a Parquet file with a `root_domain` column (such as `domains.parquet`). Run from the project directory:

```sh
python -m pip install -r requirements.txt
python main.py domains.parquet
```

Fetches each domain, extracts script URLs and generator metadata, and matches them against `rules.json` to identify technologies. Saves findings and request errors to `results.json`. JavaScript is not executed.

Run `python analyze_res.py` to recheck saved results against the rules and print common script signatures.
