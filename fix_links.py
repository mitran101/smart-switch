#!/usr/bin/env python3
"""Update all internal links after moving articles into switchinsights/ subfolder."""
import os, re, glob

ARTICLES = [
    "ban-on-acquisition-tariffs",
    "crypto-mining-energy-analysis",
    "energy-bill-rebate-april-2026",
    "energy-debt-crisis",
    "fuse-energy-and-the-history-of-small-suppliers",
    "gas-price-shock-middle-east-2026",
    "gas-value-calculator",
    "home-mover-energy-trap",
    "network-charges-update-2026",
    "ofgem-state-of-market-2026",
    "pounds-for-pylons",
    "price-cap-january-2026",
    "q2-2026-price-cap",
    "sizewell-c-nuclear-charge",
    "standing-charge-increase-2026",
    "warm-home-discount",
    "why-uk-electricity-bills-follow-gas-prices",
]

ARTICLE_SLUGS_RE = "|".join(re.escape(a) for a in ARTICLES)

# ── 1. Fix files inside switchinsights/ ─────────────────────────────────────
si_dir = "switchinsights"

for fname in os.listdir(si_dir):
    if not fname.endswith(".html"):
        continue
    fpath = os.path.join(si_dir, fname)
    with open(fpath, encoding="utf-8") as f:
        html = f.read()

    orig = html

    # Fix: href="switchinsights.html" → href="index.html"
    html = html.replace('href="switchinsights.html"', 'href="index.html"')
    html = html.replace("href='switchinsights.html'", "href='index.html'")

    # Fix: href="archive.html" → href="index.html"
    html = html.replace('href="archive.html"', 'href="index.html"')
    html = html.replace("href='archive.html'", "href='index.html'")

    # Fix favicon links - add ../ prefix for relative favicon refs
    for fav in [
        "switchinsights-favicon.ico",
        "switchinsights-favicon-32x32.png",
        "switchinsights-favicon-16x16.png",
        "switchinsights-apple-touch-icon.png",
        "favicon.ico",
        "favicon-32x32.png",
        "favicon-16x16.png",
        "apple-touch-icon.png",
    ]:
        # Only fix if not already prefixed with ../ or http
        html = re.sub(
            r'href="(?!\.\./)(?!https?://)' + re.escape(fav) + r'"',
            f'href="../{fav}"',
            html,
        )

    # Fix canonical URL: /SLUG.html → /switchinsights/SLUG.html
    # But only for article slugs, and only if not already under /switchinsights/
    html = re.sub(
        r'(<link[^>]+rel="canonical"[^>]+href="https://www\.switch-pilot\.com/)('
        + ARTICLE_SLUGS_RE
        + r')(\.html")',
        r'\1switchinsights/\2\3',
        html,
    )

    # Fix OG URL
    html = re.sub(
        r'(<meta[^>]+property="og:url"[^>]+content="https://www\.switch-pilot\.com/)('
        + ARTICLE_SLUGS_RE
        + r')(\.html")',
        r'\1switchinsights/\2\3',
        html,
    )

    # Fix Schema.org "url" field in JSON-LD
    html = re.sub(
        r'("url"\s*:\s*"https://www\.switch-pilot\.com/)('
        + ARTICLE_SLUGS_RE
        + r')(\.html")',
        r'\1switchinsights/\2\3',
        html,
    )

    # Fix switchinsights.html canonical/og if this is index.html
    if fname == "index.html":
        html = re.sub(
            r'(https://www\.switch-pilot\.com/)switchinsights\.html',
            r'\1switchinsights/',
            html,
        )
        html = html.replace(
            '"url": "https://www.switch-pilot.com/switchinsights.html"',
            '"url": "https://www.switch-pilot.com/switchinsights/"',
        )

    if html != orig:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  updated: {fpath}")
    else:
        print(f"  unchanged: {fpath}")


# ── 2. Fix root-level files ──────────────────────────────────────────────────
ROOT_FILES = [
    "index.html",
    "archive.html",
    "tariff-tracker.html",
    "energy-bill-calculator.html",
    "billing-consumption-interactive.html",
    "homemove-bill-estimate.html",
    "homemove-bill-estimate-calculator.html",
    "switchinsights/gas-value-calculator.html",
    "community.html",
    "Switching-guide.html",
    "watts-in-my-bill.html",
    "coal-renewables-timelapse.html",
    "survey-results.html",
    "sitemap.xml",
]

for fname in ROOT_FILES:
    if not os.path.exists(fname):
        continue
    with open(fname, encoding="utf-8") as f:
        html = f.read()

    orig = html

    # Fix onclick="window.open('SLUG.html','_blank')" → '/switchinsights/SLUG.html'
    def fix_open(m):
        slug = m.group(1)
        if slug in ARTICLES:
            return f"window.open('/switchinsights/{slug}.html','_blank')"
        return m.group(0)

    html = re.sub(
        r"window\.open\('(" + ARTICLE_SLUGS_RE + r")\.html','_blank'\)",
        fix_open,
        html,
    )

    # Fix href="SLUG.html" for article links
    def fix_href(m):
        slug = m.group(1)
        if slug in ARTICLES:
            return f'href="/switchinsights/{slug}.html"'
        return m.group(0)

    html = re.sub(
        r'href="(' + ARTICLE_SLUGS_RE + r')\.html"',
        fix_href,
        html,
    )

    # Fix href="switchinsights.html" → href="/switchinsights/"
    html = html.replace('href="switchinsights.html"', 'href="/switchinsights/"')

    # Fix sitemap entries
    html = re.sub(
        r'(<loc>https://www\.switch-pilot\.com/)(' + ARTICLE_SLUGS_RE + r')(\.html</loc>)',
        r'\1switchinsights/\2\3',
        html,
    )
    # Fix switchinsights.html in sitemap
    html = html.replace(
        '<loc>https://www.switch-pilot.com/switchinsights.html</loc>',
        '<loc>https://www.switch-pilot.com/switchinsights/</loc>',
    )

    if html != orig:
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  updated: {fname}")
    else:
        print(f"  unchanged: {fname}")

print("\nDone.")
