#!/usr/bin/env python3
"""Inject comments.js script tag into all SwitchInsights article pages."""
import os, re

ARTICLES = [
    "ban-on-acquisition-tariffs.html",
    "crypto-mining-energy-analysis.html",
    "energy-bill-rebate-april-2026.html",
    "energy-debt-crisis.html",
    "fuse-energy-and-the-history-of-small-suppliers.html",
    "gas-price-shock-middle-east-2026.html",
    "gas-value-calculator.html",
    "home-mover-energy-trap.html",
    "network-charges-update-2026.html",
    "ofgem-state-of-market-2026.html",
    "pounds-for-pylons.html",
    "price-cap-january-2026.html",
    "q2-2026-price-cap.html",
    "sizewell-c-nuclear-charge.html",
    "standing-charge-increase-2026.html",
    "warm-home-discount.html",
    "why-uk-electricity-bills-follow-gas-prices.html",
]

SCRIPT_TAG = '\n<script src="comments.js" defer></script>\n'

si_dir = "switchinsights"
updated = 0
skipped = 0

for fname in ARTICLES:
    fpath = os.path.join(si_dir, fname)
    if not os.path.exists(fpath):
        print(f"  MISSING: {fpath}")
        continue
    with open(fpath, encoding="utf-8") as f:
        html = f.read()
    if 'comments.js' in html:
        print(f"  already has comments.js: {fname}")
        skipped += 1
        continue
    # Insert before </body>
    if '</body>' not in html:
        print(f"  no </body> found: {fname}")
        continue
    html = html.replace('</body>', SCRIPT_TAG + '</body>', 1)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  injected: {fname}")
    updated += 1

print(f"\nDone. Updated: {updated}, Skipped: {skipped}")
