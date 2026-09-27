"""
Fetch model rainfall for context from Open-Meteo (https://open-meteo.com).

This is NOT a rain-gauge record. It is Open-Meteo's best-match numerical
weather model output for the grid cell nearest each point, used only to show
the shape of the storm (how the 26-27 Sep rain compares with the rest of
September, and when in the day it fell). The one observed number on the
dashboard -- 11.02 in / 280 mm at Dawei on 27 Sep -- comes from DMH via the
Dawei Watch report, not from here.

The response is cached to data/source/rainfall_openmeteo.json with the fetch
time, because forecast-hour values are replaced by analysis values as time
passes and a re-fetch later will not return identical numbers.
"""

import datetime as dt
import json
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "data", "source", "rainfall_openmeteo.json")

POINTS = {  # MIMU town points
    "Dawei":        (14.07753, 98.19636),
    "Launglon":     (13.97522, 98.11963),
    "Thayetchaung": (13.86871, 98.26252),
}
DAILY_START, DAILY_END = "2026-09-01", "2026-09-29"
HOURLY_START, HOURLY_END = "2026-09-25", "2026-09-28"


def get(params):
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def main():
    out = {
        "source": "Open-Meteo forecast API, best-match model (not gauge data)",
        "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "points": {},
    }
    for name, (lat, lon) in POINTS.items():
        base = {"latitude": lat, "longitude": lon, "timezone": "Asia/Yangon"}
        d = get({**base, "daily": "precipitation_sum",
                 "start_date": DAILY_START, "end_date": DAILY_END})
        h = get({**base, "hourly": "precipitation",
                 "start_date": HOURLY_START, "end_date": HOURLY_END})
        out["points"][name] = {
            "lat": lat, "lon": lon,
            "grid_lat": d["latitude"], "grid_lon": d["longitude"],
            "daily": dict(zip(d["daily"]["time"], d["daily"]["precipitation_sum"])),
            "hourly": dict(zip(h["hourly"]["time"], h["hourly"]["precipitation"])),
        }
        dd = out["points"][name]["daily"]
        print(f"{name:13s} 26 Sep {dd['2026-09-26']:6.1f} mm   27 Sep {dd['2026-09-27']:6.1f} mm   "
              f"28 Sep {dd['2026-09-28']:6.1f} mm")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("wrote", os.path.relpath(OUT))


if __name__ == "__main__":
    main()
