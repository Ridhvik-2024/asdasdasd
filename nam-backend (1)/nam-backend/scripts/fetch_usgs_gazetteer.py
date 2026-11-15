#!/usr/bin/env python3
"""Connector: fetch the FULL USGS Gazetteer of Planetary Nomenclature for Mars
(IAU-approved names, ~4100 features) from the official center-points KMZ and
store it as data/usgs_gazetteer_full.json so gazetteer search covers the full
nomenclature (Phase 1 scope).

Coordinates in the KMZ are already east longitude 0-360 / planetocentric-ish
center points. Graceful failure: if the network is unavailable, the curated
seed gazetteer remains in use.
"""
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "usgs_gazetteer_full.json"
KMZ_URL = "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MARS_nomenclature_center_pts.kmz"
SRC = "USGS Gazetteer of Planetary Nomenclature (planetarynames.wr.usgs.gov)"

NS = {"kml": "http://www.opengis.net/kml/2.2"}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "NAM-v2-backend/2.2 (gazetteer connector)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fnum(x):
    try:
        return float(x)
    except Exception:
        return None


def main():
    raw = fetch(KMZ_URL)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = [n for n in z.namelist() if n.endswith(".kml")][0]
        kml = z.read(name)
    root = ElementTree.fromstring(kml)
    feats = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        d = {}
        for sd in pm.iter("{http://www.opengis.net/kml/2.2}SimpleData"):
            d[sd.get("name")] = (sd.text or "").strip()
        nm = d.get("clean_name") or (pm.findtext("kml:name", default="", namespaces=NS) or "").strip()
        try:
            lat = float(d["center_lat"]); lon = float(d["center_lon"])
        except Exception:
            continue
        feats.append({
            "id": "usgs-" + re.sub(r"[^a-z0-9]+", "-", nm.lower()).strip("-") + "-" + str(len(feats)),
            "name": nm,
            "type": d.get("type", ""),
            "lat": lat,
            "lon": lon,
            "diameter_km": fnum(d.get("diameter")),
            "note": (d.get("origin") or "")[:300],
            "approval": d.get("approval", ""),
            "approval_date": (d.get("approvaldt") or "")[:10],
            "url": d.get("link") or None,
            "src": SRC,
        })
    OUT.write_text(json.dumps(feats, ensure_ascii=True))
    print("wrote", len(feats), "USGS features to", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("gazetteer fetch failed (staying on curated seed):", e)
        sys.exit(2)
