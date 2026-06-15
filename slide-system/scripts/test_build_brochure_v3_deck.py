#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path

import build_brochure_v3_deck as builder


ROOT = Path(__file__).resolve().parents[2]
SLOTS = (
    ROOT
    / "outputs/component-extractions/tutu-optimized-full-page/items/page-01"
    / "artifact/text-slots.json"
)


class BrochureV3DeckTest(unittest.TestCase):
    def test_build_emits_semantic_layers_without_full_page_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "deck.html"
            html = builder.build_html(SLOTS, Path(tmp) / "assets", output)

        self.assertEqual(html.count('class="text-slot"'), 77)
        self.assertGreaterEqual(html.count("data-export-native="), 20)
        self.assertGreaterEqual(html.count('data-export-layer="overlay"'), 12)
        self.assertNotIn('data-export-id="full-page-artwork"', html)
        self.assertNotIn("width:842.880000px;height:1272.480000px\" data-export-layer", html)
        self.assertRegex(
            html, r'data-slot-id="why-choose-us"[^>]+color:#17467f'
        )
        self.assertRegex(
            html, r'data-slot-id="our-services"[^>]+color:#ffffff'
        )


if __name__ == "__main__":
    unittest.main()
