"""
Hand-encode the Dawei Watch report (27 Sep) into structured data and geocode
every named place against MIMU.

Source: Dawei Watch, "ရေကြီး တောင်ပြိုမှုတွေနဲ့ ဒုက္ခပင်လယ်ဝေတဲ့ ထားဝယ်ဒေသ",
27 September, Facebook post https://web.facebook.com/share/p/18PNp9p4T4/
(copied to data/source/dawei_watch_2026-09-27.txt). `src` on every record is
the line number in that file, so each figure can be traced back to the text.

Geocoding is by the Myanmar-script village name (VLG_MMR) in the MIMU PCode
village points, restricted to the township the report places it in. Every
record carries a `match` grade:

  exact     MIMU has the name as written, in that township
  variant   MIMU spells it differently (ရှင်မုတ္ထီး -> ရှင်မုတ္တီး), or files it
            under the neighbouring township
  probable  best candidate, not certain (e.g. the report's ရေဖြူ near
            Kadet Nge is taken as MIMU's အောက်ရေဖြူ, 1.6 km away, which
            fits the report's "about a mile")
  approx    not in MIMU; placed at a stated reference (village-tract centre,
            or midway between the two places the report names)
  unlocated not in MIMU and no defensible position; listed, not mapped

English wording is a close translation; the Myanmar original is kept for
every quote.
"""

import json
import os
import warnings

import geopandas as gpd
from shapely.geometry import Point

# Nearest-feature searches in degrees are fine at district scale; areas and
# distances that get reported are computed in UTM.
warnings.filterwarnings("ignore", message="Geometry is in a geographic CRS")

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "..", "data", "raw")
OUT = os.path.join(HERE, "..", "data", "processed", "flood.json")

# ---------------------------------------------------------------------------
# Severity (ordinal) -- what happened to people at the site
#   fatal     confirmed deaths or people missing
#   severe    houses buried, people trapped, or deaths reported but unconfirmed
#   affected  named as flooded or hit by landslides, no further detail
# Hazard: landslide | flood | both
# Roles (non-ordinal flags): relief (camp / shelter), needs (aid requested),
#   access (road or bridge cut), observe (observation only)
# ---------------------------------------------------------------------------

SITES = [
    # ---------------------------------------------------- Launglon, north of town
    dict(id="ka-myaw-gyi", mm="ကမြောကြီး", en="Ka Myaw Gyi", ts="Launglon", hazard="both",
         sev="affected", area="Launglon north", src=8,
         text="Listed among villages between Dawei and Launglon hit by flooding and landslides."),
    dict(id="inn-wun", mm="အင်းဝန်း", en="Inn Wun", ts="Launglon", hazard="both",
         sev="affected", area="Launglon north", src=8,
         text="Listed among villages between Dawei and Launglon hit by flooding and landslides."),
    dict(id="min-yat", mm="မင်းရပ်", en="Min Yat", ts="Launglon", hazard="landslide",
         sev="fatal", area="Launglon north", src=19, dead=1, rescued=1,
         text="A landslide at Min Yat Chaung, west of the village, buried houses. A mother and her "
              "child were buried; rescuers recovered the mother's body and found the child alive."),
    dict(id="way-di", mm="ဝေဒီ", en="Way Di", ts="Launglon", hazard="both",
         sev="affected", area="Launglon north", src=8,
         text="Listed among villages between Dawei and Launglon hit by flooding and landslides."),
    dict(id="tha-byar", mm="သဗျာ", en="Tha Byar", ts="Launglon", hazard="both",
         sev="severe", area="Launglon north", src=20, roles=["access"],
         text="Hillsides collapsed and water in the village stood about a person's height deep, "
              "trapping people in their homes. Rescue teams that left Dawei early on 27 Sep only "
              "reached Tha Byar, at the entrance to Launglon town, around midday."),

    # ---------------------------------------------------- Launglon town
    dict(id="launglon-town", mm="လောင်းလုံးမြို့", en="Launglon town", ts="Launglon",
         town="Launglon", hazard="both", sev="fatal", area="Launglon town", src=7, dead=3,
         text="The worst-hit township. Flooding and landslides struck the town and more than 20 "
              "villages. Tens of people are dead or missing, including children. Three bodies had "
              "been recovered in the township by the afternoon of 27 Sep; houses in the tens were "
              "buried and people in the tens were still missing.",
         dead_note="Township total by 27 Sep afternoon; the same three deaths are also listed at "
                   "Kadet Nge (2) and Min Yat (1)."),

    # ---------------------------------------------------- Launglon, south of town
    dict(id="nyin-maw", mm="ညင်းမော်", en="Nyin Maw", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides. "
              "The Poe Zar Pin landslide between Launglon town and Nyin Maw stopped rescue teams "
              "heading south."),
    dict(id="ka-htaung-ni", mm="ကထောင်းနီ", en="Ka Htaung Ni", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="ka-nyon-kyun", mm="ကညုံကျွန်း", en="Ka Nyon Kyun", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="gawt-inn", mm="ဂေါ့အင်း", en="Gawt Inn", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="yay-phyu", mm="ရေဖြူ", en="Yay Phyu", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=24, roles=["relief", "needs"],
         mimu_mm="အောက်ရေဖြူ", match="probable", sheltering=500,
         match_note="MIMU has no plain ရေဖြူ in Launglon; its အောက်ရေဖြူ (Lower Yay Phyu) is "
                    "1.6 km from Kadet Nge Htein, matching the report's 'a little over a mile'.",
         text="An emergency relief camp is open at the village school and on the pagoda hill, "
              "sheltering about 500 people. Some Kadet Nge residents moved here. People in the "
              "camp need assistance."),
    dict(id="ka-det-gyi", mm="ကဒက်ကြီး", en="Ka Det Gyi", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="ka-det-nge", mm="ကဒက်ငယ်", en="Ka Det Nge", ts="Launglon", hazard="landslide",
         sev="fatal", area="Launglon south", src=15, dead=2, missing=10, match="approx",
         approx_vt="Ka Det Nge Seik",
         match_note="Not in MIMU village points. Shown at the centre of Ka Det Nge Seik village "
                    "tract; the report puts it about three miles south of Launglon town.",
         text="About three miles south of Launglon town. Landslides left people in the tens "
              "missing. The bodies of a child and a woman were recovered; about 10 people are "
              "still missing. With no search-and-rescue specialists yet, villagers are searching "
              "on their own. Some residents moved to Yay Phyu."),
    dict(id="ka-det-nge-htein", mm="ကဒက်ငယ်ထိန်", en="Ka Det Nge Htein", ts="Launglon",
         hazard="landslide", sev="fatal", area="Launglon south", src=23, houses=50,
         missing_text="dozens",
         text="A hillside right next to the village collapsed, burying at least 50 houses. "
              "Dozens of people are still missing."),
    dict(id="taw-kye", mm="တောကျဲ", en="Taw Kye", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="tha-pyay-shaung", mm="သပြေရှောင်", en="Tha Pyay Shaung", ts="Launglon",
         hazard="both", sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="tha-kyet-taw", mm="သကျက်တော", en="Tha Kyet Taw", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="za-lut", mm="ဇလွတ်", en="Za Lut", ts="Launglon", hazard="both",
         sev="affected", area="Launglon south", src=8,
         text="Listed among villages between Launglon and Shin Maw hit by flooding and landslides."),
    dict(id="kyauk-ni-maw", mm="ကျောက်နီမော်", en="Kyauk Ni Maw", ts="Launglon",
         hazard="landslide", sev="fatal", area="Launglon south", src=13, missing=2,
         roles=["access"],
         text="A village hemmed in by hills and the sea. From about 5 pm on 26 Sep landslides "
              "buried houses and people. A child and a man are missing. Slides were still coming "
              "down on the morning of 27 Sep, so no rescue was possible, and contact with the "
              "village was lost around midday."),
    dict(id="nyaw-pyin", mm="ညောပြင်", en="Nyaw Pyin", ts="Launglon", hazard="landslide",
         sev="severe", area="Launglon south", src=22,
         text="Landslides hit the village. Deaths are reported but not yet confirmed."),

    # ---------------------------------------------------- Launglon, north-west coast
    dict(id="tha-bawt-seik", mm="သဘော့ဆိပ်", en="Tha Bawt Seik", ts="Launglon", hazard="both",
         sev="affected", area="Launglon north-west", src=8,
         text="Near Maungmagan beach, north-west of Launglon. Listed among villages hit by "
              "flooding and landslides."),
    dict(id="kayin-gyi", mm="ကရင်ကြီး", en="Kayin Gyi", ts="Launglon", hazard="landslide",
         sev="severe", area="Launglon north-west", src=26, houses=30, sheltering=60,
         roles=["relief", "needs"],
         text="Landslides on the night of 26 Sep and the morning of 27 Sep buried about 30 houses "
              "and carried away two-wheel tractors and motorcycles. No one was hurt. About 30 "
              "households, more than 60 people, moved to the monastery and other safe places and "
              "need help."),
    dict(id="maungmagan", mm="မောင်းမကန်", en="Maungmagan", ts="Launglon", hazard="flood",
         sev="affected", area="Launglon north-west", src=29, roles=["observe"],
         text="At the well-known Maungmagan beach and the beaches around it, the blue-green sea "
              "turned a muddy yellow."),

    # ---------------------------------------------------- Launglon, other named villages
    dict(id="sit-pyay", mm="စစ်ပြဲ", en="Sit Pyay", ts="Launglon", hazard="flood",
         sev="affected", area="Launglon north", src=11,
         text="Flooded on the night of 26 Sep. Residents stayed awake for fear of landslides.",
         quote_mm="တစ်ရွာလုံးလည်း ပင်လယ်ပြင်ကြီးလိုဖြစ်သွားပြီ။ လူတွေလည်း ညမအိပ်ရဲကြဘူး။ တောင်ပြိုမှာ ကြောက်နေကြတယ်",
         quote_en="The whole village has turned into an open sea. People don't dare to sleep at "
                  "night. They are afraid of landslides.",
         quote_by="Sit Pyay resident, night of 26 Sep"),
    dict(id="thea-pon", mm="သဲပုံ", en="Thea Pon", ts="Launglon", hazard="landslide",
         sev="affected", area="Launglon north", src=21,
         text="A landslide on Inwa hill buried land and destroyed orchards and gardens."),
    dict(id="ka-det-nge-seik", mm="ကဒက်ငယ်ဆိပ်", en="Ka Det Nge Seik", ts="Launglon",
         hazard="both", sev="affected", area="Launglon south", src=24, roles=["needs", "access"],
         text="Cut off by broken roads. The village needs food and drinking water."),

    # ---------------------------------------------------- Thayetchaung
    dict(id="ti-tut-pyin", mm="တီတွတ်ပြင်", en="Ti Tut Pyin", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="pe-det", mm="ပဲဒက်", en="Pe Det", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=33,
         text="Listed among flooded villages. A Kin Shey resident said villages were flooded all "
              "the way from past the Pauk Taing bridge checkpoint at the entrance to Dawei to "
              "beyond Pe Det."),
    dict(id="shin-moke-tee", mm="ရှင်မုတ္ထီး", en="Shin Moke Tee", ts="Thayetchaung",
         hazard="flood", sev="affected", area="Thayetchaung", src=32,
         mimu_mm="ရှင်မုတ္တီး", mimu_ts="Dawei", match="variant",
         match_note="MIMU spells it ရှင်မုတ္တီး and places it in Dawei Township, just north of "
                    "the Thayetchaung boundary.",
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="yaung-maw", mm="ရောင်းမော်", en="Yaung Maw", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32, mimu_ts="Dawei", match="variant",
         match_note="MIMU places this village in Dawei Township, beside the Thayetchaung boundary.",
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="nyaung-zin", mm="ညောင်ဇင်", en="Nyaung Zin", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="kyar-inn", mm="ကြာအင်း", en="Kyar Inn", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="kin-shey", mm="ကင်းရှေ့", en="Kin Shey", ts="Thayetchaung", hazard="flood",
         sev="severe", area="Thayetchaung", src=33, depth_ft=6,
         text="On the morning of 27 Sep the whole ground floor of houses was under water. Families "
              "moved belongings upstairs overnight and took the children to houses in town.",
         quote_mm="တစ်သက်နဲ့တစ်ကိုယ် တစ်ခါမှ မမြင်ဖူးဘူး။ ကျွန်မတို့ရွာမှာ ရေတက်လာလည်း ဒူးဆစ်လောက်ပဲ တက်ဖူးတယ်။ အခုက လူတစ်ရပ်လောက်အထိ မြုပ်တယ်။",
         quote_en="I have never seen anything like it in my life. When water rose in our village "
                  "it only ever came up to the knee. Now it is over a person's height.",
         quote_by="Kin Shey resident, a woman, 27 Sep"),
    dict(id="moe-shwe-kone", mm="မိုးရွှေကုန်း", en="Moe Shwe Kone", ts="Thayetchaung",
         hazard="flood", sev="affected", area="Thayetchaung", src=32, match="probable",
         ward="Maw Shi Kone Ward",
         match_note="Not in MIMU village points. Taken as Maw Shi Kone Ward (မော်ရှီကုန်း) of "
                    "Thayetchaung town, the closest name in MIMU; shown at the ward centre.",
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="saw-hpyar", mm="စော်ဖျား", en="Saw Hpyar", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=35,
         text="Listed among flooded villages. A resident said she had never experienced a flood "
              "like it.",
         quote_mm="ကျွန်မတို့ အိမ်ဆိုတာ တစ်ခါမှ အခုလို ရေမရောက်ဖူးဘူး။ ကျွန်မအသက် သုံးဆယ်ကျော်လာတဲ့အထိ တစ်သက်နဲ့ တစ်ကိုယ် ဒီလိုမျိုး ရေကြီးတာ တစ်ခါမှ မမြင်ဖူးဘူး",
         quote_en="Water has never reached our house like this. I'm past thirty and I have never "
                  "seen a flood like this in my life.",
         quote_by="Saw Hpyar resident, a woman, 27 Sep"),
    dict(id="yan-taung", mm="ရန်တောင်", en="Yan Taung", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="thin-kyun", mm="သင်းကျွန်း", en="Thin Kyun", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="tha-yet-hnit-khwa", mm="သရက်နှစ်ခွ", en="Tha Yet Hnit Khwa", ts="Thayetchaung",
         hazard="flood", sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="oke-tu", mm="ဥတ္တူ", en="Oke Tu", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32,
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="htee-hpa-doe", mm="ထီးဖဒို", en="Htee Hpa Doe", ts="Thayetchaung", hazard="flood",
         sev="affected", area="Thayetchaung", src=32, match="unlocated",
         match_note="No village of this name, or a close spelling, in MIMU for Dawei District.",
         text="Listed among flooded villages in Thayetchaung Township."),
    dict(id="taung-pyauk", mm="တောင်ပျောက်", en="Taung Pyauk area", ts="Thayetchaung",
         hazard="flood", sev="affected", area="Thayetchaung", src=32, match="approx",
         approx_vt="Kayin Taung Pyauk",
         match_note="The report names 'villages in the Taung Pyauk area' without listing them. "
                    "Shown at the centre of Kayin Taung Pyauk village tract.",
         text="Villages in the Taung Pyauk area are flooded."),

    # ---------------------------------------------------- Dawei
    dict(id="dawei-town", mm="ထားဝယ်မြို့", en="Dawei town", ts="Dawei", town="Dawei",
         hazard="flood", sev="severe", area="Dawei", src=40, roles=["access"],
         text="Record rainfall. Drains overflowed and main roads went under water in some wards. "
              "Elderly people and children trapped in their homes were brought out by social "
              "welfare groups. Water covered the road in front of a private hospital on Ka Myaw "
              "Kin road, and strong wind brought down at least five large trees. Homes flooded "
              "in places that had never flooded before."),
    dict(id="pauk-taing", mm="ပေါက်တိုင်း", en="Pauk Taing bridge", ts="Dawei", hazard="flood",
         sev="affected", area="Dawei", src=33, roles=["access"], bridge="Pauk Taing Bridge",
         text="The checkpoint at Pauk Taing bridge, at the entrance to Dawei, marks the northern "
              "end of the flooded stretch that runs south past Pe Det."),
    dict(id="za-lun", mm="ဇလွန်း", en="Za Lun", ts="Dawei", hazard="flood", sev="affected",
         area="Dawei east", src=42, roles=["access"],
         text="On the Dawei to Htee Khee road, which was under water in the forest area east of "
              "Dawei."),
    dict(id="ta-laing-taung", mm="တလိုင်းတောင်", en="Ta Laing Taung", ts="Dawei",
         hazard="flood", sev="affected", area="Dawei east", src=42, roles=["access"],
         text="On the Dawei to Htee Khee road, which was under water in the forest area east of "
              "Dawei."),
    dict(id="pa-kar-ri", mm="ပကာရီ", en="Pa Kar Ri", ts="Dawei", hazard="flood",
         sev="affected", area="Dawei east", src=42, roles=["access"],
         text="Flooded. Water was flowing over the San Chi bridge at Pa Kar Ri."),

    # ---------------------------------------------------- Yebyu
    dict(id="kaleinaung", mm="ကလိန်အောင်", en="Kaleinaung", ts="Yebyu", town="Kaleinaung",
         hazard="flood", sev="affected", area="Yebyu", src=46, roles=["access"],
         text="Water over the road in places on the Union highway and around Kaleinaung. "
              "Residents reported nothing else unusual in Yebyu Township."),
]

# Places the report uses only as reference points, not as affected sites
REFERENCES = [
    dict(id="shin-maw", mm="ရှင်မော်", en="Shin Maw", src=8,
         note="Southern end of the affected stretch of the Launglon peninsula, home to one of the "
              "'nine Shins' pagodas. Not in MIMU village points, so not mapped."),
    dict(id="htee-khee", mm="ထီးခီး", en="Htee Khee", src=42,
         note="Thai-Myanmar border crossing at the far end of the Dawei to Htee Khee road."),
]

# Incidents that are not a village: roads, slides on named hills
INCIDENTS = [
    dict(id="poe-zar-pin", kind="road-block", en="Poe Zar Pin landslide",
         mm="ပိုးဇာပင်တောင်ပြို", src=9, between=["launglon-town", "nyin-maw"],
         text="A landslide on Poe Zar Pin hill, between Launglon town and Nyin Maw, stopped the "
              "rescue convoy heading for southern Launglon at about 2:30 pm on 27 Sep.",
         match_note="Hill not in MIMU. Placed midway between Launglon town and Nyin Maw, the two "
                    "places the report names, then moved onto the nearest MIMU road."),
    dict(id="san-chi-bridge", kind="bridge", en="San Chi bridge overtopped",
         mm="ဆန်းချီတံတား ရေကျော်", src=42, at="pa-kar-ri",
         text="Water flowing over the San Chi bridge at Pa Kar Ri village, on the Dawei to Htee "
              "Khee road."),
    dict(id="min-yat-chaung", kind="landslide", en="Min Yat Chaung landslide",
         mm="မင်းရပ်ချောင် တောင်ပြို", src=19, at="min-yat",
         text="The slide came down in Min Yat Chaung, west of the village."),
]

# `t` only orders the entries and places them on the rainfall chart; `when` is what the
# report actually says about timing and is what the page shows.
TIMELINE = [
    dict(t="2026-09-26T08:00", when="26 Sep, morning", approx=True, area="District", src=10,
         en="Heavy rain sets in from the morning."),
    dict(t="2026-09-26T17:00", when="26 Sep, ~5:00 pm", area="Launglon", src=13, site="kyauk-ni-maw", kind="landslide",
         en="Landslides begin burying houses and people at Kyauk Ni Maw."),
    dict(t="2026-09-26T20:00", when="26 Sep, night", approx=True, area="Launglon", src=10, kind="flood",
         en="Night: floodwater overtops roads and pours into homes. People move out in the dark. "
            "Village-to-village roads are cut the same night."),
    dict(t="2026-09-26T22:00", when="26 Sep night – 27 Sep morning", approx=True, area="Launglon", src=26, site="kayin-gyi",
         kind="landslide", en="Night into morning: landslides bury about 30 houses at Kayin Gyi."),
    dict(t="2026-09-27T07:00", when="27 Sep, morning", approx=True, area="Thayetchaung", src=33, site="kin-shey",
         kind="flood", en="Morning: the ground floors of houses in Kin Shey are under water."),
    dict(t="2026-09-27T07:30", when="27 Sep, early morning", approx=True, area="Dawei", src=9, kind="rescue",
         en="Early morning: rescue teams set out from Dawei for Launglon."),
    dict(t="2026-09-27T09:30", when="27 Sep", approx=True, area="Dawei", src=44, kind="rain",
         en="DMH records 11.02 in (280 mm) at Dawei, a new record. The old record was 9.68 in."),
    dict(t="2026-09-27T12:00", when="27 Sep, 12:00 noon", area="Launglon", src=25, kind="landslide",
         en="Landslides are still coming down across Launglon and the rain is still heavy. "
            "Rescuers urge people by streams and hillsides to move to safety."),
    dict(t="2026-09-27T12:30", when="27 Sep, midday", approx=True, area="Launglon", src=14, site="kyauk-ni-maw",
         kind="access", en="Midday: contact with Kyauk Ni Maw is lost."),
    dict(t="2026-09-27T13:00", when="27 Sep, midday", approx=True, area="Launglon", src=9, site="tha-byar",
         kind="rescue", en="Midday: the rescue teams reach Tha Byar at the entrance to Launglon."),
    dict(t="2026-09-27T14:30", when="27 Sep, ~2:30 pm", area="Launglon", src=9, site="poe-zar-pin", kind="access",
         en="About 2:30 pm: the Poe Zar Pin landslide between Launglon and Nyin Maw stops the "
            "rescue teams heading south."),
    dict(t="2026-09-27T15:00", when="27 Sep, 3:00 pm", area="District", src=51, kind="rain",
         en="From 3 pm strong winds sweep the whole of Dawei District; rain does not let up."),
    dict(t="2026-09-27T15:30", when="27 Sep, afternoon", approx=True, area="Launglon", src=28, kind="toll",
         en="Afternoon: three bodies recovered in Launglon Township. Tens of people still missing."),
    dict(t="2026-09-27T18:00", when="27 Sep, evening", approx=True, area="Dawei", src=43, kind="flood",
         en="Evening: rain continues over most of Dawei town. Water enters compounds that had "
            "never flooded before."),
    dict(t="2026-09-28T12:00", when="28 Sep (forecast)", approx=True, area="Region", src=48, kind="forecast",
         en="Forecast: heavy rain continues across Tanintharyi through 28 Sep, easing but still "
            "strong."),
]

FACTS = dict(
    record_in=11.02, record_mm=280, prev_record_in=9.68, record_date="2026-09-27",
    forecast_3day_mm=[360, 470], forecast_by="U Win Naing, weather analyst",
    forecast_multiple=">3x the rain on other days this month",
    thayetchaung_official=dict(wards=5, depth_ft=[6, 8], affected=18000,
                               by="military government figures"),
    thayetchaung_reported_depth_ft=6,
    launglon_villages="20+", launglon_bodies=3,
    cause="A low-pressure area moving in from Thailand over the Tanintharyi coast",
    context="Environmental destruction across the region, including hills cut away and streams "
            "wrecked by mining, is being blamed for making the disaster worse, as a strong "
            "El Niño sets in.",
)


def norm(s):
    return (s or "").replace("​", "").replace(" ", "").strip()


def main():
    vp = gpd.read_file(os.path.join(RAW, "village_points_tni.geojson"))
    vp = vp[vp.DT == "Dawei"]
    towns = gpd.read_file(os.path.join(RAW, "town_points.geojson"))
    vt = gpd.read_file(os.path.join(RAW, "adm4_vt_tanintharyi.geojson"))
    wards = gpd.read_file(os.path.join(RAW, "adm5_wards.geojson"))
    bridges = gpd.read_file(os.path.join(RAW, "bridges.geojson"))
    roads = gpd.read_file(os.path.join(RAW, "roads.geojson"))

    for s in SITES:
        s.setdefault("match", "exact")
        s.setdefault("roles", [])
        if s["match"] == "unlocated":
            s["lon"] = s["lat"] = None
            continue
        if "town" in s:
            r = towns[towns.Town == s["town"]].iloc[0]
            s.update(lon=round(r.Longitude, 5), lat=round(r.Latitude, 5),
                     pcode=r.Town_Pcode, mimu_name=r.Town, mimu_mm=r.Town_MMR4)
            continue
        if "bridge" in s:
            r = bridges[bridges.nmEng == s["bridge"]].iloc[0]
            s.update(lon=round(r.geometry.x, 5), lat=round(r.geometry.y, 5),
                     mimu_name=r.nmEng, mimu_mm=r.nmMya)
            continue
        if "ward" in s:
            r = wards[wards.WARD == s["ward"]].iloc[0]
            p = r.geometry.representative_point()
            s.update(lon=round(p.x, 5), lat=round(p.y, 5), pcode=r.WARD_PCODE,
                     mimu_name=r.WARD, mimu_mm=r.WARD_MMR)
            continue
        if "approx_vt" in s:
            r = vt[vt.VT == s["approx_vt"]].iloc[0]
            p = r.geometry.representative_point()
            s.update(lon=round(p.x, 5), lat=round(p.y, 5), pcode=r.VT_PCODE,
                     mimu_name=r.VT + " (village tract)", mimu_mm=r.VT_MMR)
            continue
        want = norm(s.get("mimu_mm", s["mm"]))
        ts = s.get("mimu_ts", s["ts"])
        m = vp[(vp.VLG_MMR.map(norm) == want) & (vp.TS == ts)]
        if len(m) != 1:
            raise SystemExit(f"{s['id']}: {len(m)} MIMU matches for {want} in {ts}")
        r = m.iloc[0]
        s.update(lon=round(r.Longitude, 5), lat=round(r.Latitude, 5), pcode=str(r.VLG_PCODE),
                 mimu_name=r.VILLAGE, mimu_mm=r.VLG_MMR, vt=r.VT, mimu_ts=r.TS)

    by_id = {s["id"]: s for s in SITES}
    for inc in INCIDENTS:
        if "between" in inc:
            a, b = (by_id[k] for k in inc["between"])
            mid = Point((a["lon"] + b["lon"]) / 2, (a["lat"] + b["lat"]) / 2)
            # a road block sits on the road: snap the midpoint to the nearest MIMU road
            near = roads[roads.distance(mid) < 0.03]
            if len(near):
                line = near.geometry.iloc[near.distance(mid).argmin()]
                mid = line.interpolate(line.project(mid))
            inc.update(lon=round(mid.x, 5), lat=round(mid.y, 5), match="approx")
        else:
            s = by_id[inc["at"]]
            inc.update(lon=s["lon"], lat=s["lat"], match="exact")

    grades = {}
    for s in SITES:
        grades[s["match"]] = grades.get(s["match"], 0) + 1

    out = dict(
        source=dict(outlet="Dawei Watch", date="2026-09-27",
                    title_mm="ရေကြီး တောင်ပြိုမှုတွေနဲ့ ဒုက္ခပင်လယ်ဝေတဲ့ ထားဝယ်ဒေသ",
                    title_en="Floods and landslides bring a sea of suffering to the Dawei region",
                    url="https://web.facebook.com/share/p/18PNp9p4T4/"),
        facts=FACTS, sites=SITES, references=REFERENCES, incidents=INCIDENTS,
        timeline=TIMELINE, match_grades=grades,
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {os.path.relpath(OUT)}: {len(SITES)} sites, {len(INCIDENTS)} incidents, "
          f"{len(TIMELINE)} timeline entries")
    print("match grades:", grades)


if __name__ == "__main__":
    main()
