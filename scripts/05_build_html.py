"""
Inline the processed data into the template and emit the dashboard.

src/template.html is a BODY FRAGMENT and the single source of truth. It has no
<html>/<head>/<body> of its own because the Claude Artifact platform wraps the
file in its own document skeleton at publish time. Two outputs:

  index.html               complete standalone document, served by GitHub
                           Pages at SITE from the main branch root. Adds doctype, charset, viewport, an
                           inline SVG favicon and a minimal reset.
  dist/artifact-body.html  the same page as a fragment, for the Artifact.

Leaflet's JS loads from cdnjs; its CSS is inlined from src/vendor/leaflet.css
because the Artifact sandbox only admits stylesheets from Google Fonts. All
data is inline -- no fetch at runtime. The MIMU vectors are the basemap; the
optional satellite/topographic tiles work on the standalone page only.

Never hand-edit either output -- change src/template.html and re-run this.
"""

import json
import os
import re

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PROC = os.path.join(ROOT, "data", "processed")
SRC = os.path.join(ROOT, "src", "template.html")
VENDOR_CSS = os.path.join(ROOT, "src", "vendor", "leaflet.css")
RAIN = os.path.join(ROOT, "data", "source", "rainfall_openmeteo.json")
DIST = os.path.join(ROOT, "dist")

SITE = "https://geonet-myanmar.github.io/dawei-flood-dashboard/"

FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
    "%3Crect width='100' height='100' rx='18' fill='%230b6f7a'/%3E"
    "%3Cpath d='M18 70 L42 30 L58 56 L66 44 L84 70 Z' fill='%23fbfcfc'/%3E"
    "%3Cpath d='M10 80c10 0 10-7 20-7s10 7 20 7 10-7 20-7 10 7 20 7' fill='none' "
    "stroke='%23f0a08c' stroke-width='7' stroke-linecap='round'/%3E%3C/svg%3E"
)

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<meta name="color-scheme" content="light dark" />
{title}
{description}
<link rel="icon" href="{favicon}" />
<link rel="canonical" href="{site}" />
<meta name="author" content="geonet-myanmar" />
<meta property="og:type" content="website" />
<meta property="og:url" content="{site}" />
<meta property="og:title" content="{og_title}" />
<meta property="og:description" content="{og_desc}" />
<style>
*, *::before, *::after {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{ margin: 0; }}
img, svg, canvas {{ max-width: 100%; }}
[hidden] {{ display: none !important; }}
</style>
</head>
<body>
"""
FOOT = "\n</body>\n</html>\n"

LAYERS = {
    "thailand":   "thailand.geojson",
    "context":    "context_townships.geojson",
    "townships":  "townships.geojson",
    "district":   "district.geojson",
    "vt":         "village_tracts.geojson",
    "wards":      "wards.geojson",
    "lowland":    "lowland.geojson",
    "mining":     "mining.geojson",
    "rivers":     "rivers.geojson",
    "riverLines": "river_lines.geojson",
    "roads":      "roads.geojson",
    "railway":    "railway.geojson",
    "cutoff":     "cutoff_area.geojson",
    "sez":        "sez.geojson",
    "villages":   "villages.geojson",
    "towns":      "towns.geojson",
    "schools":    "schools.geojson",
    "hospitals":  "hospitals.geojson",
    "bridges":    "bridges.geojson",
}


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    flood = jload(os.path.join(PROC, "flood.json"))
    analysis = jload(os.path.join(PROC, "analysis.json"))
    rain = jload(RAIN)
    geo = {k: jload(os.path.join(PROC, fn)) for k, fn in LAYERS.items()}

    html = open(SRC, encoding="utf-8").read()

    def inject(marker, text):
        nonlocal html
        if marker not in html:
            raise SystemExit(f"marker {marker} not found in template")
        html = html.replace(marker, text, 1)

    def blob(obj):
        # "</" inside JSON string data would close the <script> block early
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    inject("/*__LEAFLET_CSS__*/", open(VENDOR_CSS, encoding="utf-8").read())
    inject("/*__FLOOD__*/", blob(flood))
    inject("/*__GEO__*/", blob(geo))
    inject("/*__ANALYSIS__*/", blob(analysis))
    inject("/*__RAIN__*/", blob(rain))

    m_title = re.search(r"<title>(.*?)</title>", html, re.S)
    m_desc = re.search(r'<meta name="description" content="(.*?)"\s*/?>', html, re.S)
    if not m_title:
        raise SystemExit("template is missing a <title>")
    body = html
    for m in (m_title, m_desc):
        if m:
            body = body.replace(m.group(0), "", 1)
    doc = HEAD.format(
        title=m_title.group(0), description=m_desc.group(0) if m_desc else "",
        favicon=FAVICON, site=SITE, og_title=m_title.group(1).strip(),
        og_desc=m_desc.group(1).strip() if m_desc else "",
    ) + body.lstrip("\n") + FOOT

    out = os.path.join(ROOT, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    os.makedirs(DIST, exist_ok=True)
    frag = os.path.join(DIST, "artifact-body.html")
    with open(frag, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"wrote index.html              {os.path.getsize(out)/1_048_576:.2f} MB (standalone)")
    print(f"wrote dist/artifact-body.html {os.path.getsize(frag)/1_048_576:.2f} MB (Artifact fragment)")
    print("  layers:", ", ".join(f"{k}={len(v['features'])}" for k, v in geo.items()))


if __name__ == "__main__":
    main()
