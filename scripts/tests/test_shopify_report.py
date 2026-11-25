import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.report import generate_shopify_report


class ShopifyReportTests(unittest.TestCase):
    def test_reports_competitor_found_on_an_internal_page(self):
        product_url = "https://store-a.example/products/example"
        northbeam_url = "https://j.northbeam.io/vendor/nb-sp.min.js"
        results = [
            {
                "domain": "store-a.example",
                "final_url": "https://store-a.example/",
                "technologies": [{"name": "Shopify"}],
                "linked_pages": [
                    {
                        "final_url": product_url,
                        "technologies": [
                            {
                                "name": "Northbeam",
                                "evidence": [{"source": "script src", "value": northbeam_url}],
                            }
                        ],
                    }
                ],
            },
            {
                "domain": "store-b.example",
                "final_url": "https://store-b.example/",
                "technologies": [{"name": "Shopify"}],
            },
        ]

        with TemporaryDirectory() as directory:
            results_path = Path(directory) / "results.json"
            results_path.write_text(json.dumps(results), encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                generate_shopify_report(results_path=results_path)

        report = output.getvalue()
        self.assertIn("Shopify stores detected: 2\n", report)
        self.assertIn("Stores with a tracked competitor detected: 1\n", report)
        self.assertIn(
            f"\nstore-a.example\n  Northbeam | {product_url}\n    script src: {northbeam_url}\n",
            report,
        )
        self.assertIn("\nstore-b.example\n  No tracked competitor detected.\n", report)
