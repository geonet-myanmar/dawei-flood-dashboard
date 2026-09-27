"""
Clip, simplify and join the MIMU layers for Dawei District, and run the spatial
analysis the dashboard reports.

The dashboard draws these vectors itself -- MIMU is the basemap -- so these
files are the map. Admin polygons are simplified to ~40 m and coordinates are
rounded to 4-5 decimal places, well inside the 1:250,000 source accuracy.
Distances and areas are measured in UTM 47N (EPSG:32647).

Analysis written to data/processed/analysis.json:
  townships   per-township counts: MIMU villages, schools, hospitals, land
              below 5 m, mapped mining area, and reported sites
  near_sites  schools and hospitals within 1 km of a reported site
  cutoff      what lies on the Launglon peninsula south of the Poe Zar Pin
              landslide that stopped the rescue convoy -- road access from
              Dawei runs through Launglon town and past that point
"""

import json
import os
import warnings

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

# Nearest-feature searches in degrees are fine at district scale; areas and
# distances that get reported are computed in UTM.
warnings.filterwarnings("ignore", message="Geometry is in a geographic CRS")

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "..", "data", "raw")
OUT = os.path.join(HERE, "..", "data", "processed")

DAWEI_DT = "MMR006D001"
UTM = 32647
VIEW = box(97.45, 12.95, 99.35, 15.45)   # map canvas; context outside it is dropped
TOL_ADM = 0.0004                        # ~40 m
TOL_CTX = 0.002
NEAR_M = 1000


def load(name):
    return gpd.read_file(os.path.join(RAW, name))


def round_coords(obj, p):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), p) for v in obj]
        return [round_coords(v, p) for v in obj]
    return obj


def dump(gdf, name, keep, prec=4):
    feats = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        g = geom.__geo_interface__
        g = {"type": g["type"], "coordinates": round_coords(g["coordinates"], prec)}
        props = {}
        for k in keep:
            v = row.get(k)
            if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
                continue
            if hasattr(v, "item"):
                v = v.item()
            if isinstance(v, float):
                v = round(v, 3)
            props[k] = v
        feats.append({"type": "Feature", "properties": props, "geometry": g})
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {name:26s} {len(feats):5,d} features  {os.path.getsize(path)/1024:8.1f} KB")


def km2(geom_or_gdf):
    s = gpd.GeoSeries([geom_or_gdf], crs=4326) if not isinstance(geom_or_gdf, gpd.GeoSeries) else geom_or_gdf
    return float(s.to_crs(UTM).area.sum() / 1e6)


def main():
    flood = json.load(open(os.path.join(OUT, "flood.json"), encoding="utf-8"))
    sites = [s for s in flood["sites"] if s.get("lon") is not None]
    sg = gpd.GeoDataFrame(sites, geometry=[Point(s["lon"], s["lat"]) for s in sites], crs=4326)

    # ------------------------------------------------------------ admin
    print("admin")
    ts_all = load("adm3_townships.geojson")
    ts = ts_all[ts_all.DT_PCODE == DAWEI_DT].copy()
    district = unary_union(ts.geometry)
    near = district.buffer(0.03)

    a1 = load("adm1_states.geojson")
    myanmar = unary_union(a1.geometry)
    ctx = ts_all[(ts_all.DT_PCODE != DAWEI_DT) & ts_all.intersects(VIEW)].copy()
    ctx["geometry"] = ctx.geometry.intersection(VIEW.buffer(0.2)).simplify(TOL_CTX, preserve_topology=True)
    dump(ctx, "context_townships.geojson", ["TS", "DT", "ST"])

    # Thailand = what is left of the canvas once Myanmar is removed, keeping only
    # pieces that reach the canvas's east edge (the rest of the remainder is sea).
    rest = VIEW.buffer(0.2).difference(myanmar)
    parts = list(rest.geoms) if hasattr(rest, "geoms") else [rest]
    east = VIEW.buffer(0.2).bounds[2]
    thai = [p for p in parts if p.bounds[2] >= east - 1e-6 and p.area > 0.01]
    thai_g = gpd.GeoDataFrame({"name": ["Thailand"]},
                              geometry=[unary_union(thai).simplify(TOL_CTX)], crs=4326)
    dump(thai_g, "thailand.geojson", ["name"])

    # township stats joined onto the polygons
    tsu = ts.to_crs(UTM)
    ts["area_km2"] = (tsu.area / 1e6).round(0)
    rp = ts.geometry.representative_point()
    ts["lx"], ts["ly"] = rp.x.round(4), rp.y.round(4)

    # ------------------------------------------------------------ village tracts, wards
    vt = load("adm4_vt_tanintharyi.geojson")
    vt = vt[vt.DT_PCODE == DAWEI_DT].copy()
    hits = gpd.sjoin(sg[["id", "geometry"]], vt[["VT_PCODE", "geometry"]], predicate="within")
    hit_vt = hits.groupby("VT_PCODE").id.apply(list).to_dict()
    vt["sites"] = vt.VT_PCODE.map(lambda p: len(hit_vt.get(p, [])))
    vt["geometry"] = vt.geometry.simplify(TOL_ADM, preserve_topology=True)
    dump(vt, "village_tracts.geojson", ["VT", "VT_MMR", "VT_PCODE", "TS", "sites"])

    wards = load("adm5_wards.geojson")
    wards = wards[wards.DT_PCODE == DAWEI_DT].copy()
    # Official figure: five urban wards of Thayetchaung flooded 6-8 ft. MIMU maps
    # exactly five wards in Thayetchaung town, so the figure covers the whole town.
    wards["flooded"] = (wards.TOWN == "Thayetchaung Town").astype(int)
    wards["named"] = wards.WARD.isin(["Myo Ma (Tha Yet Chaung Ward)", "Kyauk Myaung Ward",
                                      "Pan Taw Ward"]).astype(int)
    wards["geometry"] = wards.geometry.simplify(0.0001, preserve_topology=True)
    dump(wards, "wards.geojson", ["WARD", "WARD_MMR", "TOWN", "TS", "flooded", "named"], prec=5)

    # ------------------------------------------------------------ villages
    print("villages")
    vp = load("village_points_tni.geojson")
    vp = vp[vp.DT_PCODE == DAWEI_DT].copy()
    reported_pcodes = {s.get("pcode") for s in sites}
    vp["rep"] = vp.VLG_PCODE.astype(str).isin(reported_pcodes).astype(int)
    dump(vp, "villages.geojson", ["VILLAGE", "VLG_MMR", "TS", "VT", "rep"], prec=5)

    towns = load("town_points.geojson")
    towns = towns[towns.intersects(VIEW)]
    dump(towns, "towns.geojson", ["Town", "Town_MMR4", "Township", "Level"], prec=5)

    # ------------------------------------------------------------ infrastructure
    print("infrastructure")
    rd = load("roads.geojson")
    rd = rd[rd.intersects(VIEW)].copy()
    rd["geometry"] = rd.geometry.intersection(VIEW).simplify(0.0003, preserve_topology=True)
    dump(rd, "roads.geojson", ["Road_Type"])

    rl = load("railways.geojson")
    rl["geometry"] = rl.geometry.intersection(VIEW).simplify(0.0003)
    dump(rl, "railway.geojson", ["Div_Name", "Track"])

    br = load("bridges.geojson")
    br = br[br.within(near)].copy()
    dump(br, "bridges.geojson", ["nmEng", "nmMya", "length_ft", "nmTsEng"], prec=5)

    hs = load("health_facilities.geojson")
    hs = hs[hs.DT_PCODE == DAWEI_DT].copy()
    dump(hs, "hospitals.geojson", ["nmHsp_eng", "nmHsp_mya", "lvlHsp_eng", "bedClass", "TS_en"], prec=5)

    sc = load("schools_lower.geojson")
    sc = sc[sc.mm_dtcode == DAWEI_DT].copy()
    sc["geometry"] = sc.geometry.apply(lambda g: g.geoms[0] if g.geom_type == "MultiPoint" else g)
    dump(sc, "schools.geojson", ["schoolname", "urbanrural", "mm_tsname"], prec=5)

    sez = load("sez_polygons.geojson")
    sez = sez[sez.intersects(near)]
    dump(sez, "sez.geojson", ["nmEng", "nmMya", "zoneType"])

    # ------------------------------------------------------------ hydrography, terrain
    print("hydrography and land")
    rv = load("rivers_detail.geojson")
    rv = rv[rv.intersects(VIEW)].copy()
    rv["name"] = rv.NAME.replace({"TAVOY": "Dawei River", "UNK": ""})
    rv["geometry"] = rv.geometry.simplify(0.0003, preserve_topology=True)
    dump(rv, "rivers.geojson", ["name"])

    rvl = load("rivers_250k.geojson")
    rvl["geometry"] = rvl.geometry.intersection(VIEW).simplify(0.0005)
    dump(rvl, "river_lines.geojson", ["Name"])

    lo = load("below5m.geojson")
    lo_d = unary_union(lo.geometry.buffer(0)).intersection(district)
    lo_g = gpd.GeoDataFrame(geometry=[lo_d.simplify(0.0004)], crs=4326)
    dump(lo_g, "lowland.geojson", [])

    mn = load("mining_areas.geojson")
    mn = mn[mn.intersects(near)].copy()
    mn["Mineral1"] = mn.Mineral1.replace("", None)
    dump(mn, "mining.geojson", ["Township", "Notes", "Mineral1", "Area_hect", "Certainty", "ImageYear1"])

    # ------------------------------------------------------------ township analysis
    print("analysis")
    by_ts = {}
    for _, t in ts.iterrows():
        g = t.geometry
        lo_ts = lo_d.intersection(g)
        rep = [s for s in flood["sites"] if s["ts"] == t.TS]
        by_ts[t.TS] = dict(
            ts=t.TS, ts_mm=t.TS_MMR, pcode=t.TS_PCODE, area_km2=int(t.area_km2),
            villages=int((vp.TS_PCODE == t.TS_PCODE).sum()),
            village_tracts=int((vt.TS_PCODE == t.TS_PCODE).sum()),
            schools=int((sc.mm_tscode == t.TS_PCODE).sum()),
            hospitals=int((hs.TS_PCODE == t.TS_PCODE).sum()),
            hospital_beds=int(pd.to_numeric(hs[hs.TS_PCODE == t.TS_PCODE].bedClass).sum()),
            lowland_km2=round(km2(lo_ts), 1),
            lowland_pct=round(100 * km2(lo_ts) / km2(g), 1),
            mining_sites=int(mn.within(g.buffer(0.001)).sum()),
            mining_ha=round(float(mn[mn.within(g.buffer(0.001))].Area_hect.sum()), 0),
            reported_sites=len(rep),
            fatal=sum(1 for s in rep if s["sev"] == "fatal"),
            severe=sum(1 for s in rep if s["sev"] == "severe"),
            affected=sum(1 for s in rep if s["sev"] == "affected"),
            vt_hit=int((vt[vt.TS_PCODE == t.TS_PCODE].sites > 0).sum()),
        )
    ts["sites"] = ts.TS.map(lambda n: by_ts[n]["reported_sites"])
    ts["geometry"] = ts.geometry.simplify(TOL_ADM, preserve_topology=True)
    dump(ts, "townships.geojson", ["TS", "TS_MMR", "TS_PCODE", "area_km2", "lx", "ly", "sites"])
    d_g = gpd.GeoDataFrame({"DT": ["Dawei"]}, geometry=[district.simplify(TOL_ADM)], crs=4326)
    dump(d_g, "district.geojson", ["DT"])

    # ------------------------------------------------------------ facilities near sites
    sgu = sg[~sg.roles.map(lambda r: "observe" in r)].to_crs(UTM)
    near_rows = []
    for layer, name_col, kind in ((sc, "schoolname", "school"), (hs, "nmHsp_eng", "hospital")):
        lu = layer.to_crs(UTM)
        for _, f in lu.iterrows():
            d = sgu.distance(f.geometry)
            i = d.idxmin()
            if d[i] <= NEAR_M:
                near_rows.append(dict(kind=kind, name=f[name_col], site=sgu.loc[i, "id"],
                                      site_en=sgu.loc[i, "en"], sev=sgu.loc[i, "sev"],
                                      dist_m=int(round(d[i])),
                                      lon=round(layer.loc[f.name].geometry.x, 5),
                                      lat=round(layer.loc[f.name].geometry.y, 5)))
    near_rows.sort(key=lambda r: (r["kind"], r["dist_m"]))

    # ------------------------------------------------------------ south of the slide
    block = next(i for i in flood["incidents"] if i["id"] == "poe-zar-pin")
    lg = ts[ts.TS == "Launglon"].geometry.iloc[0]
    lg_full = ts_all[ts_all.TS == "Launglon"].geometry.iloc[0]
    parts = list(lg_full.geoms) if isinstance(lg_full, MultiPolygon) else [lg_full]
    mainland = max(parts, key=lambda p: p.area)
    south = mainland.intersection(box(97, 0, 100, block["lat"]))

    def inside(gdf):
        return gdf[gdf.within(south)]

    v_s, s_s, h_s = inside(vp), inside(sc), inside(hs)
    rep_s = [s for s in sites if s["ts"] == "Launglon" and south.contains(Point(s["lon"], s["lat"]))]
    cutoff = dict(
        block_lat=block["lat"], block_lon=block["lon"],
        villages=len(v_s), village_tracts=int(vt[vt.representative_point().within(south)].shape[0]),
        schools=len(s_s), hospitals=len(h_s), hospital_names=h_s.nmHsp_eng.tolist(),
        reported_sites=len(rep_s), reported_ids=[s["id"] for s in rep_s],
        fatal=sum(1 for s in rep_s if s["sev"] == "fatal"),
        area_km2=round(km2(south), 0),
        launglon_villages=by_ts["Launglon"]["villages"],
    )
    sg_ = gpd.GeoDataFrame(geometry=[south.simplify(TOL_ADM)], crs=4326)
    dump(sg_, "cutoff_area.geojson", [])

    district_tot = dict(
        villages=len(vp), village_tracts=len(vt), schools=len(sc), hospitals=len(hs),
        area_km2=int(round(km2(district))), mining_sites=int(len(mn[mn.within(district.buffer(0.001))])),
        mining_ha=round(float(mn[mn.within(district.buffer(0.001))].Area_hect.sum()), 0),
        lowland_km2=round(km2(lo_d), 0),
    )
    analysis = dict(townships=by_ts, district=district_tot, near_sites=near_rows,
                    near_m=NEAR_M, cutoff=cutoff)
    with open(os.path.join(OUT, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=1)

    print("\nTownships:")
    for t in by_ts.values():
        print("  ", {k: t[k] for k in ("ts", "villages", "schools", "hospitals", "lowland_km2",
                                       "lowland_pct", "mining_ha", "reported_sites", "vt_hit")})
    print("District:", district_tot)
    print(f"Near sites (<= {NEAR_M} m): {sum(r['kind']=='school' for r in near_rows)} schools, "
          f"{sum(r['kind']=='hospital' for r in near_rows)} hospitals")
    print("South of Poe Zar Pin:", {k: v for k, v in cutoff.items() if k != 'reported_ids'})


if __name__ == "__main__":
    main()
