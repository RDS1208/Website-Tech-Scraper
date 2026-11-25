import unittest

from scripts.tech import detect_tech, validate_rules


class DetectionTests(unittest.TestCase):
    def test_validation_warns_for_each_rejected_rule(self):
        good = {"name": "Example", "hostname": "cdn.example.com"}
        rules = [
            good,
            {"name": "Shopify", "path_prefx": "/cdn/shop/"},
            {"name": "Example CSS", "css_url": {"paths": "/theme.css"}},
            {"name": "Example header", "header": "server"},
        ]
        with self.assertLogs("scripts.tech", level="WARNING") as log:
            self.assertEqual(validate_rules(rules), [good])

        self.assertEqual(len(log.records), 3)
        self.assertIn("rule 2 ('Shopify'): unexpected field 'path_prefx'", log.output[0])
        self.assertIn("css_url: paths must be", log.output[1])
        self.assertIn("header_product", log.output[2])

    def test_northbeam_matches_the_vendor_script(self):
        url = "https://j.northbeam.io/vendor/nb-sp.min.js"

        hits = detect_tech([url])

        self.assertIn(
            {"name": "Northbeam", "evidence": [{"source": "script src", "value": url}]},
            hits,
        )

    def test_northbeam_ignores_the_same_filename_on_another_host(self):
        hits = detect_tech(["https://example.com/vendor/nb-sp.min.js"])

        self.assertNotIn("Northbeam", {hit["name"] for hit in hits})
