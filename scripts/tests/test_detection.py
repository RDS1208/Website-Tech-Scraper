import unittest

from scripts.tech import detect_tech


class DetectionTests(unittest.TestCase):
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
