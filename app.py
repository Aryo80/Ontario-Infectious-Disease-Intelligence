"""Ontario Infectious Disease Intelligence dashboard.

Purpose
-------
An interactive, descriptive public-health portfolio application for exploring
aggregate reported infectious-disease cases and population-based rates. Users
can view one disease or compare exactly two diseases side by side.

Data sources
------------
Prepared CSV tables from notebooks/04_dashboard_preparation.ipynb, stored in
outputs/dashboard/. Optional Ontario PHU boundaries are cached in data/.

Run locally
-----------
python -m streamlit run app.py

Interpretation
--------------
Rates are disease-specific, reported cases are not distinct patients, and
PHU boundaries may not align with all historical reporting regions.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from html import escape

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# Configure a wide layout for side-by-side disease comparisons.
st.set_page_config(
    page_title="Ontario | Infectious Disease Intelligence",
    page_icon="🩺", layout="wide", initial_sidebar_state="collapsed"
)
# Resolve paths relative to this file so local runs and cloud deployments work.
BASE = Path(__file__).resolve().parent
DATA = BASE / "outputs" / "dashboard"
MAP_CACHE_DIR = BASE / "data"
BLUE = "#2868ed"
TEAL = "#10988f"
NAVY = "#102947"
BLUE_SCALE = [
    [0.00, "#EFF6FF"], [0.18, "#DBEAFE"], [0.38, "#93C5FD"],
    [0.58, "#60A5FA"], [0.80, "#2563EB"], [1.00, "#1E40AF"],
]
TEAL_SCALE = [
    [0.00, "#F0FDFA"], [0.18, "#CCFBF1"], [0.38, "#99F6E4"],
    [0.58, "#5EEAD4"], [0.80, "#0D9488"], [1.00, "#115E59"],
]
ONTARIO_MAP_CENTER = {"lat": 49.1, "lon": -84.4}
ONTARIO_MAP_ZOOM = 4.05
MAP_URLS = [
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer/44/query",
    "https://ws.lioservices.lrc.gov.on.ca/arcgis1071a/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer/44/query",
]
BOUNDARY_CACHE = MAP_CACHE_DIR / "ontario_phu_boundaries.geojson"

# Dashboard design system: custom typography and the blue/teal visual identity.
st.markdown("""<style>
.block-container{max-width:1880px!important;width:96%!important;padding:1rem 1.2rem 3rem!important}
[data-testid="stAppViewContainer"]{background:#f4f7fe}
.hero{padding:28px 36px;min-height:158px;background:linear-gradient(90deg,#122f56 0%,rgba(18,47,86,.96) 40%,rgba(18,47,86,.42) 76%,rgba(18,47,86,.06) 100%),linear-gradient(115deg,#122f56,#23629c);border-radius:19px;color:#fff;margin-bottom:18px;background-position:center,right center;background-size:100% 100%,auto 100%;background-repeat:no-repeat}
.hero h1{color:#fff!important;font-size:2.15rem;letter-spacing:-.04em;margin:5px 0}
.hero p{color:#d8e9fc;margin:6px 0 0;font-size:1rem}
.eyebrow{letter-spacing:.14em;font-size:.74rem;color:#a4ceff;font-weight:750}
.section{font-size:1.24rem;font-weight:800;color:#173c6e;margin:24px 0 12px}
[data-testid="stMetric"]{background:white;border:1px solid #dce7f5;border-radius:15px;padding:18px;min-height:112px}
[data-testid="stVerticalBlockBorderWrapper"]>div{background:white;border-color:#dae4f3!important;border-radius:16px!important}
[data-testid="stPlotlyChart"]{width:100%!important}
[data-testid="stCaptionContainer"]{font-size:.83rem!important}
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, textarea, select {font-family:"Segoe UI",Inter,Arial,sans-serif!important}
html,body,[class*="css"]{font-family:"Segoe UI",Inter,Arial,sans-serif}
.hero h1{font-size:2.42rem!important;font-weight:780!important;letter-spacing:-.035em!important;line-height:1.17!important}
.hero p{font-size:1.02rem!important;line-height:1.45!important}
.eyebrow{font-size:.78rem!important;letter-spacing:.13em!important}
.section{font-size:1.36rem!important;font-weight:760!important;letter-spacing:-.018em;line-height:1.35}
[data-testid="stMetricLabel"]{font-size:.96rem!important;font-weight:600!important;color:#425675!important}
[data-testid="stMetricValue"]{font-size:2.02rem!important;font-weight:730!important;letter-spacing:-.025em!important;color:#163556!important}
[data-testid="stMetricDelta"]{font-size:.92rem!important}
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{font-size:.94rem!important;font-weight:600!important;color:#253e5e!important}
[data-testid="stMarkdownContainer"] p{line-height:1.5}
[data-testid="stCaptionContainer"]{font-size:.89rem!important;line-height:1.45!important}
[data-testid="stVerticalBlockBorderWrapper"] strong{font-size:1.01rem;font-weight:700;color:#1c3654}
@media(max-width:900px){.hero h1{font-size:1.85rem!important}.section{font-size:1.2rem!important}}
/* Panel text hierarchy: highly legible in wide side-by-side cards */
.pho-panel-title{font-family:"Segoe UI",Arial,sans-serif;font-size:1.45rem;font-weight:800;color:#142e50;line-height:1.22;letter-spacing:-.015em;margin:0 0 .35rem 0}
.pho-panel-detail{font-family:"Segoe UI",Arial,sans-serif;font-size:1.02rem;font-weight:600;color:#506683;line-height:1.4;margin:0 0 .75rem 0}
.pho-panel-cases{font-family:"Segoe UI",Arial,sans-serif;display:flex;align-items:baseline;gap:.55rem;flex-wrap:wrap;color:#19395c;margin:.2rem 0 .7rem}
.pho-panel-cases .label{font-size:1.08rem;font-weight:700}
.pho-panel-cases .number{font-size:1.46rem;font-weight:800;letter-spacing:-.02em;color:#132e51}
@media(max-width:900px){.pho-panel-title{font-size:1.23rem}.pho-panel-detail{font-size:.92rem}.pho-panel-cases .number{font-size:1.27rem}}


/* Final readable typography pass: charts have stronger headings than sections. */
.section{font-size:1.20rem!important;font-weight:750!important;letter-spacing:-.01em!important}
.pho-panel-title{font-size:1.50rem!important;font-weight:800!important;line-height:1.25!important}
.pho-panel-detail{font-size:1.07rem!important;font-weight:600!important;color:#435c7b!important}
.pho-panel-cases .label{font-size:1.14rem!important;font-weight:750!important}
.pho-panel-cases .number{font-size:1.54rem!important;font-weight:850!important}
/* Streamlit renders metric and widget text as nested paragraphs in many versions. */
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] div{font-size:1.16rem!important;font-weight:750!important;line-height:1.35!important;color:#223b5c!important}
[data-testid="stMetricValue"], [data-testid="stMetricValue"]>div{font-size:2.12rem!important;font-weight:800!important;line-height:1.12!important;color:#143555!important}
[data-testid="stMetricDelta"], [data-testid="stMetricDelta"] p{font-size:1.02rem!important;font-weight:700!important}
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label, div[data-testid="stWidgetLabel"]{font-size:1.10rem!important;font-weight:750!important;color:#243f61!important}
[data-baseweb="select"] [role="combobox"], [data-baseweb="select"] input,
[data-testid="stSelectSlider"] span, [data-testid="stRadio"] label p,
[data-testid="stMultiSelect"] [data-baseweb="tag"] span{font-size:1.04rem!important;font-weight:600!important}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{font-size:.98rem!important;line-height:1.45!important;color:#516480!important}
@media(max-width:900px){.pho-panel-title{font-size:1.30rem!important}.section{font-size:1.14rem!important}
[data-testid="stMetricLabel"] p{font-size:1.04rem!important}}


/* Final visual hierarchy: section headings 01-06, and real dropdown VALUES. */
.section {
  font-size: 1.78rem !important;
  font-weight: 800 !important;
  line-height: 1.32 !important;
  letter-spacing: -0.02em !important;
  color: #173c6e !important;
  margin: 1.85rem 0 1rem !important;
}
/* Streamlit selectboxes use BaseWeb nested divs, not a native <select>. */
[data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"],
[data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"] *,
[data-testid="stMultiSelect"] [data-baseweb="select"] [role="combobox"],
[data-testid="stMultiSelect"] [data-baseweb="select"] [role="combobox"] * {
  font-family: "Segoe UI", Arial, sans-serif !important;
  font-size: 1.13rem !important;
  font-weight: 650 !important;
  color: #1d3757 !important;
}
/* Also cover BaseWeb's selected-value and placeholder nodes across versions. */
[data-baseweb="select"] [data-baseweb="select-value"],
[data-baseweb="select"] [data-baseweb="select-value"] *,
[data-baseweb="select"] [data-baseweb="select-placeholder"],
[data-baseweb="select"] input,
[data-baseweb="select"] div[aria-selected] {
  font-size: 1.13rem !important;
  font-weight: 650 !important;
  color: #1d3757 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  min-height: 2.95rem !important;
}
/* Options in the expanded dropdown portal. */
[data-baseweb="popover"] [role="option"],
[data-baseweb="popover"] [role="option"] *,
[role="listbox"] [role="option"] {
  font-size: 1.07rem !important;
  font-weight: 600 !important;
}
/* Year slider values are rendered separately from widget labels. */
[data-testid="stSlider"] [data-testid="stTickBar"] *,
[data-testid="stSelectSlider"] [data-testid="stTickBar"] *,
[data-testid="stSelectSlider"] span {
  font-size: 1.03rem !important;
  font-weight: 700 !important;
}
@media (max-width: 900px) {
  .section { font-size: 1.48rem !important; }
  [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"],
  [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"] * {
    font-size: 1rem !important;
  }
}


/* Filter values: target the actual selected text nodes in Streamlit/BaseWeb. */
[data-testid="stSelectbox"] [data-baseweb="select"] div,
[data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stMultiSelect"] [data-baseweb="select"] div,
[data-testid="stMultiSelect"] [data-baseweb="select"] span {
  font-family: "Segoe UI", Arial, sans-serif !important;
  font-size: 1.18rem !important;
  font-weight: 700 !important;
  letter-spacing: 0 !important;
  color: #193858 !important;
}
/* Do not blow up the decorative dropdown arrow. */
[data-testid="stSelectbox"] [data-baseweb="select"] svg,
[data-testid="stMultiSelect"] [data-baseweb="select"] svg {
  width: 17px !important;
  height: 17px !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  min-height: 3.2rem !important;
}
/* Year range slider endpoints: Streamlit's current thumb-label DOM. */
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"],
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"] *,
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] ~ div,
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] ~ div span,
[data-testid="stSlider"] [data-testid="stThumbValue"],
[data-testid="stSelectSlider"] [data-testid="stThumbValue"] {
  font-size: 1.14rem !important;
  font-weight: 800 !important;
  color: #2563eb !important;
}
/* Ensure header labels and slider values are not visually out of balance. */
[data-testid="stWidgetLabel"] p {font-size:1.18rem!important;font-weight:750!important}


/* PHO FILTER VALUES FIX 2026-10-26. Targets actual BaseWeb rendered values,
   including inner text nodes that are not inputs or combobox elements. */
.stSelectbox div[data-baseweb="select"] *,
.stMultiSelect div[data-baseweb="select"] *,
[data-testid="stSelectbox"] div[data-baseweb="select"] *,
[data-testid="stMultiSelect"] div[data-baseweb="select"] *,
[data-testid="stSelectbox"] input,
[data-testid="stMultiSelect"] input {
  font-family: "Segoe UI", Arial, sans-serif !important;
  font-size: 20px !important;
  font-weight: 700 !important;
  line-height: 1.38 !important;
  color: #153452 !important;
}
/* Keep icons from inheriting text dimensions. */
[data-testid="stSelectbox"] svg,
[data-testid="stMultiSelect"] svg {
  height: 18px !important;
  width: 18px !important;
}
/* The input box needs more height when text is 20px. */
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
  min-height: 53px !important;
}
/* Streamlit slider endpoint numbers, including newer BaseWeb structures. */
[data-testid="stSlider"] [data-testid="stThumbValue"],
[data-testid="stSlider"] [data-testid="stThumbValue"] *,
[data-testid="stSelectSlider"] [data-testid="stThumbValue"],
[data-testid="stSelectSlider"] [data-testid="stThumbValue"] *,
[data-testid="stSelectSlider"] [data-baseweb="slider"] [aria-hidden="true"] ~ div,
.stSlider div[data-testid="stThumbValue"] {
  font-size: 19px !important;
  font-weight: 800 !important;
  color: #1d4ed8 !important;
}
/* Additional fallback for the thumb numbers in Streamlit's value labels. */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] + div,
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] + div * {
  font-size: 19px !important;
  font-weight: 800 !important;
}


/* Explicit, legible year endpoints, separate from Streamlit's tiny thumb labels. */
.pho-year-values {
  display:flex; align-items:center; justify-content:space-between;
  margin:0.16rem 0 0.1rem; padding:0 0.1rem;
  font-family:"Segoe UI",Arial,sans-serif;
  font-size:1.18rem; font-weight:800; line-height:1.3;
  color:#234361;
}
.pho-year-values span {font-size:inherit!important;font-weight:inherit!important;color:inherit!important;}

/* Analysis-mode radio options only. Other radio buttons retain their styling.
   Streamlit assigns st-key-analysis_mode to the keyed widget wrapper. */
.st-key-analysis_mode [data-testid="stRadio"] label p,
.st-key-analysis_mode [data-testid="stRadio"] label span,
.st-key-analysis_mode [data-testid="stRadio"] [role="radiogroup"] label,
.st-key-analysis_mode [role="radiogroup"] label p,
.st-key-analysis_mode [role="radiogroup"] label span {
  font-family: "Segoe UI", Arial, sans-serif !important;
  font-size: 1.27rem !important;
  font-weight: 800 !important;
  line-height: 1.45 !important;
  color: #193858 !important;
}
/* Keep long option labels readable without clipping at narrower widths. */
.st-key-analysis_mode [role="radiogroup"] {
  row-gap: .35rem !important;
}

/* Header typography: larger and consistent on desktop and laptop screens. */
.hero{min-height:185px!important;padding:30px 38px!important}
.hero .eyebrow{font-size:1.08rem!important;font-weight:800!important;letter-spacing:.12em!important;line-height:1.35!important}
.hero h1{font-size:3.15rem!important;font-weight:850!important;line-height:1.12!important;letter-spacing:-.035em!important;margin:9px 0 10px!important}
.hero p{font-size:1.27rem!important;font-weight:650!important;line-height:1.45!important;margin:8px 0 0!important}
@media(max-width:1050px){
 .hero{min-height:165px!important;padding:26px!important}
 .hero .eyebrow{font-size:.96rem!important}
 .hero h1{font-size:2.35rem!important}
 .hero p{font-size:1.1rem!important}
}
@media(max-width:650px){
 .hero .eyebrow{font-size:.82rem!important}
 .hero h1{font-size:1.9rem!important}
 .hero p{font-size:.98rem!important}
}
/* Portfolio KPI hierarchy: labels are slightly larger than the Analysis mode
   label and radio options. Keep the large numeric values unchanged. */
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] *,
[data-testid="stMetricLabel"] p {
  font-family: "Segoe UI", Arial, sans-serif !important;
  font-size: 1.38rem !important;
  font-weight: 800 !important;
  line-height: 1.38 !important;
  color: #193858 !important;
}
/* First disease is blue; second disease is green/teal. */
.st-key-kpi_disease_1 [data-testid="stMetricLabel"],
.st-key-kpi_disease_1 [data-testid="stMetricLabel"] * {
  color: #2868ed !important;
}
.st-key-kpi_disease_2 [data-testid="stMetricLabel"],
.st-key-kpi_disease_2 [data-testid="stMetricLabel"] * {
  color: #10988f !important;
}
</style>""", unsafe_allow_html=True)

# The skyline is a decorative local asset: the app works even when it is absent.
# Data URI avoids relying on a remote URL or a separate static-file server.
SKYLINE = BASE / "assets" / "toronto_skyline.png"
if SKYLINE.exists():
    import base64
    encoded_skyline = base64.b64encode(SKYLINE.read_bytes()).decode("ascii")
    st.markdown(
        '<style>.hero{background-image:linear-gradient(90deg,'
        '#122f56 0%,rgba(18,47,86,.98) 39%,rgba(18,47,86,.40) 76%,'
        'rgba(18,47,86,.05) 100%),url("data:image/png;base64,'
        + encoded_skyline + '")!important;}</style>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_data():
    sources = {
        "trends": "dashboard_ontario_trends.csv",
        "phu": "dashboard_phu_rates.csv",
        "demographics": "dashboard_demographics.csv",
        "outcomes": "dashboard_outcomes.csv",
    }
    missing = [filename for filename in sources.values() if not (DATA / filename).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing dashboard exports in {DATA}: {', '.join(missing)}. "
            "Run the dashboard preparation notebook or copy the original dashboard CSV exports "
            "into outputs/dashboard/."
        )
    d = {k: pd.read_csv(DATA / filename, low_memory=False) for k, filename in sources.items()}
    for name, frame in d.items():
        frame["Year"] = pd.to_numeric(frame["Year"], errors="coerce").astype("Int64")
        if name in ("trends", "phu"):
            for field in ("Cases", "Population", "Rate per 100,000"):
                frame[field] = pd.to_numeric(frame[field], errors="coerce")
        elif name == "demographics":
            frame["Number of cases"] = pd.to_numeric(frame["Number of cases"], errors="coerce")
        elif name == "outcomes":
            frame["Cases with outcome"] = pd.to_numeric(frame["Cases with outcome"], errors="coerce")
    return d


# Real city reference points, not calculated PHU centroids. Used only when boundaries are unavailable
# and as selective map-label anchor points. The displayed choropleth uses official boundary polygons.
PHU_CITY = {
    "Algoma Public Health": (46.52, -84.35, "Algoma"),
    "Chatham-Kent Public Health": (42.40, -82.18, "Chatham-Kent"),
    "City of Hamilton Public Health Services": (43.26, -79.87, "Hamilton"),
    "Durham Region Health Department": (43.90, -78.86, "Durham"),
    "Eastern Ontario Health Unit": (45.02, -74.73, "Eastern Ontario"),
    "Grand Erie Public Health": (43.14, -80.26, "Grand Erie"),
    "Grey Bruce Health Unit": (44.57, -80.94, "Grey Bruce"),
    "Halton Region Public Health": (43.52, -79.88, "Halton"),
    "Huron Perth Public Health": (43.37, -80.98, "Huron Perth"),
    "Lakelands Public Health": (44.35, -78.74, "Lakelands"),
    "Lambton Public Health": (42.97, -82.40, "Lambton"),
    "Middlesex-London Health Unit": (42.99, -81.24, "London"),
    "Niagara Region Public Health": (43.06, -79.25, "Niagara"),
    "North Bay Parry Sound District Health Unit": (46.31, -79.46, "North Bay"),
    "Northeastern Public Health": (48.47, -81.33, "Northeastern"),
    "Northwestern Health Unit": (49.77, -94.49, "Northwestern"),
    "Ottawa Public Health": (45.42, -75.69, "Ottawa"),
    "Peel Public Health": (43.69, -79.76, "Peel"),
    "Public Health Sudbury & Districts": (46.49, -80.99, "Sudbury"),
    "Region of Waterloo Public Health and Emergency Services": (43.45, -80.49, "Waterloo"),
    "Renfrew County and District Health Unit": (45.82, -77.11, "Renfrew"),
    "Simcoe Muskoka District Health Unit": (44.39, -79.69, "Simcoe Muskoka"),
    "Southeast Public Health": (44.23, -76.49, "Southeast"),
    "Southwestern Public Health": (42.77, -80.98, "Southwestern"),
    "Thunder Bay District Health Unit": (48.38, -89.25, "Thunder Bay"),
    "Toronto Public Health": (43.65, -79.38, "Toronto"),
    "Wellington-Dufferin-Guelph Public Health": (43.54, -80.25, "Wellington"),
    "Windsor-Essex County Health Unit": (42.31, -83.04, "Windsor"),
    "York Region Public Health": (44.06, -79.46, "York"),
}
KEY_LABELS = {"Toronto", "Ottawa", "Thunder Bay", "Sudbury", "London", "Northwestern", "Windsor"}
PHU_ALIASES = {
    "southeast public health": ["southeast public health", "kingston frontenac lennox and addington"],
    "grand erie public health": ["grand erie", "brant county health unit", "haldimand norfolk health unit"],
    "northeastern public health": ["northeastern public health", "porcupine health unit", "timiskaming health unit"],
    "lakelands public health": ["lakelands public health", "haliburton kawartha pine ridge district health unit"],
}


def clean_name(value):
    s = str(value).lower().replace("&", "and")
    for word in ("public health", "health unit", "health department", "health", "region", "district"):
        s = s.replace(word, "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def boundary_match(name, official_names):
    lookup = {clean_name(item): item for item in official_names if item}
    match = lookup.get(clean_name(name))
    if match:
        return match
    for alias in PHU_ALIASES.get(str(name).lower(), ()):
        match = lookup.get(clean_name(alias))
        if match:
            return match
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def get_boundaries():
    if BOUNDARY_CACHE.exists():
        try:
            geo = json.loads(BOUNDARY_CACHE.read_text(encoding="utf-8"))
            if len(geo.get("features", [])) >= 20:
                return geo
        except (ValueError, OSError):
            pass
    for url in MAP_URLS:
        try:
            resp = requests.get(url, params={
                "where": "1=1", "outFields": "PHU_NAME_ENG,PHU_ID",
                "returnGeometry": "true", "outSR": "4326",
                "geometryPrecision": "3", "maxAllowableOffset": "0.012",
                "f": "geojson",
            }, timeout=9)
            resp.raise_for_status()
            geo = resp.json()
            if geo.get("type") != "FeatureCollection" or len(geo.get("features", [])) < 20:
                continue
            try:
                BOUNDARY_CACHE.parent.mkdir(exist_ok=True, parents=True)
                BOUNDARY_CACHE.write_text(json.dumps(geo), encoding="utf-8")
            except OSError:
                pass
            return geo
        except (requests.RequestException, ValueError):
            continue
    return None


def px_map(kind, frame, **kwargs):
    """Use modern map traces where available, with old-Plotly Mapbox fallback."""
    modern = getattr(px, f"{kind}_map", None)
    if modern is not None:
        return modern(frame, **kwargs)
    legacy = getattr(px, f"{kind}_mapbox", None)
    if legacy is not None:
        kwargs["mapbox_style"] = kwargs.pop("map_style")
        return legacy(frame, **kwargs)
    raise RuntimeError("Upgrade Plotly: python -m pip install --upgrade plotly")


def plot_map_labels(fig, frame, kind="Key PHUs"):
    if kind == "Off":
        return
    labels = []
    for phu in frame["Public health unit"].dropna().unique():
        if phu not in PHU_CITY:
            continue
        lat, lon, text = PHU_CITY[phu]
        if kind == "All PHUs" or text in KEY_LABELS:
            labels.append((lat, lon, text))
    if not labels:
        return
    # Match label trace to the type of Plotly map created (modern map or legacy mapbox).
    modern = bool(fig.data and fig.data[0].type in {"choroplethmap", "scattermap"})
    cls = go.Scattermap if modern else go.Scattermapbox
    fig.add_trace(cls(
        lat=[p[0] for p in labels], lon=[p[1] for p in labels],
        text=[p[2] for p in labels], mode="markers+text",
        marker={"size": 3, "color": "#202735", "opacity": 0.9},
        textfont={"size": 12, "color": "#17243a", "family": "Arial Black, Segoe UI, Arial"},
        textposition="top center", hoverinfo="skip", showlegend=False,
    ))


def enforce_ontario_view(fig, view_id="ontario"):
    """Apply the same fixed Ontario viewport to every Plotly map trace type.

    Reset map UI state per chart so comparing diseases cannot retain the
    previous chart's world zoom. Keep the independent disease color scale.
    """
    modern = any(getattr(trace, "type", "") in {"choroplethmap", "scattermap"}
                 for trace in fig.data)
    if modern:
        fig.update_layout(map=dict(center=ONTARIO_MAP_CENTER,
                                   zoom=ONTARIO_MAP_ZOOM,
                                   style="carto-positron", uirevision=view_id))
    else:
        fig.update_layout(mapbox=dict(center=ONTARIO_MAP_CENTER,
                                      zoom=ONTARIO_MAP_ZOOM,
                                      style="carto-positron", uirevision=view_id))
    return fig

def tidy(fig, height=360, margin_left=10):
    fig.update_layout(
        height=height, margin=dict(l=margin_left, r=15, t=24, b=25),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI Semibold, Arial", color="#263e5d", size=16),
        xaxis=dict(tickfont=dict(family="Segoe UI Semibold, Arial", size=15, color="#263e5d"),
                   title_font=dict(family="Segoe UI Semibold, Arial", size=16)),
        yaxis=dict(tickfont=dict(family="Segoe UI Semibold, Arial", size=15, color="#263e5d"),
                   title_font=dict(family="Segoe UI Semibold, Arial", size=16)),
        legend=dict(orientation="h", y=1.1, x=0),
        hoverlabel=dict(bgcolor="white", font_color="#173353"),
    )
    fig.update_xaxes(gridcolor="#e7edf7", zeroline=False)
    fig.update_yaxes(gridcolor="#eff3f9", zeroline=False)
    return fig


def render(fig, key=None):
    st.plotly_chart(fig, use_container_width=True,
                    config={"displaylogo": False, "responsive": True}, key=key)


def title(text, detail=None):
    """Prominent, consistent headings for each chart card."""
    st.markdown(f'<div class="pho-panel-title">{escape(str(text))}</div>',
                unsafe_allow_html=True)
    if detail:
        st.markdown(f'<div class="pho-panel-detail">{escape(str(detail))}</div>',
                    unsafe_allow_html=True)


def short_phu(name):
    if name in PHU_CITY:
        return PHU_CITY[name][2]
    return str(name).replace("Public Health", "").replace("Health Unit", "").strip()


def scale_for_disease(frame):
    """Fixed scale over selected years & PHUs, shared by that disease's map and heatmap."""
    rates = frame["Rate per 100,000"].dropna()
    if rates.empty:
        return 1.0
    return max(1.0, float(rates.max()))


def make_incidence_map(current, geo, upper, label_style, color_scale, view_id="ontario"):
    """Return (figure, boundary_count_missing, used_city_fallback)."""
    frame = current.dropna(subset=["Rate per 100,000"]).copy()
    if frame.empty:
        return None, 0, False
    if geo is not None:
        official_names = [feature.get("properties", {}).get("PHU_NAME_ENG")
                          for feature in geo.get("features", [])]
        frame["official_name"] = frame["Public health unit"].map(
            lambda phu: boundary_match(phu, official_names)
        )
        matches = frame.dropna(subset=["official_name"]).copy()
        if not matches.empty:
            fig = px_map(
                "choropleth", matches, geojson=geo, locations="official_name",
                featureidkey="properties.PHU_NAME_ENG",
                color="Rate per 100,000",
                hover_name="Public health unit",
                hover_data={"Cases": ":,.0f", "Rate per 100,000": ":.1f", "official_name": False},
                color_continuous_scale=color_scale, range_color=(0, upper),
                map_style="carto-positron", zoom=4.05,
                center={"lat": 49.1, "lon": -84.4}, opacity=0.88,
            )
            plot_map_labels(fig, matches, label_style)
            fig.update_layout(height=490, margin=dict(l=0, r=0, t=0, b=0),
                              coloraxis_colorbar=dict(title=dict(text="Rate / 100k", font=dict(size=15)), thickness=15, len=0.83,
                                                      tickfont=dict(size=13, family="Segoe UI Semibold, Arial")))
            return enforce_ontario_view(fig, view_id), len(frame) - len(matches), False
    # City-marker fallback, explicitly not polygons.
    frame["Lat"] = frame["Public health unit"].map(lambda phu: PHU_CITY.get(phu, (None, None, None))[0])
    frame["Lon"] = frame["Public health unit"].map(lambda phu: PHU_CITY.get(phu, (None, None, None))[1])
    frame = frame.dropna(subset=["Lat", "Lon"])
    if frame.empty:
        return None, 0, True
    fig = px_map("scatter", frame, lat="Lat", lon="Lon", color="Rate per 100,000",
                 hover_name="Public health unit",
                 hover_data={"Cases": ":,.0f", "Rate per 100,000": ":.1f", "Lat": False, "Lon": False},
                 size="Rate per 100,000", size_max=28,
                 color_continuous_scale=color_scale, range_color=(0, upper),
                 map_style="carto-positron", center={"lat": 49.1, "lon": -84.4},
                 zoom=4.05, opacity=0.88)
    plot_map_labels(fig, frame, label_style)
    fig.update_layout(height=490, margin=dict(l=0, r=0, t=0, b=0),
                      coloraxis_colorbar=dict(title=dict(text="Rate / 100k", font=dict(size=15)), thickness=15, len=0.83,
                                                      tickfont=dict(size=13, family="Segoe UI Semibold, Arial")))
    return enforce_ontario_view(fig, view_id), 0, True


def make_bubble_map(current, label_style, color_scale, view_id="ontario"):
    frame = current.dropna(subset=["Cases"]).copy()
    frame["Lat"] = frame["Public health unit"].map(lambda phu: PHU_CITY.get(phu, (None, None, None))[0])
    frame["Lon"] = frame["Public health unit"].map(lambda phu: PHU_CITY.get(phu, (None, None, None))[1])
    frame["Bubble size"] = frame["Cases"].clip(lower=0)
    frame = frame.dropna(subset=["Lat", "Lon"])
    if frame.empty:
        return None
    fig = px_map("scatter", frame, lat="Lat", lon="Lon", size="Bubble size",
                 color="Cases", hover_name="Public health unit",
                 hover_data={"Cases": ":,.0f", "Lat": False, "Lon": False, "Bubble size": False},
                 color_continuous_scale=color_scale, size_max=38, map_style="carto-positron",
                 center={"lat": 49.1, "lon": -84.4}, zoom=4.05, opacity=0.85)
    plot_map_labels(fig, frame, label_style)
    fig.update_layout(height=490, margin=dict(l=0, r=0, t=0, b=0),
                      coloraxis_colorbar=dict(title=dict(text="Cases", font=dict(size=15)), thickness=15, len=0.83,
                                               tickfont=dict(size=13, family="Segoe UI Semibold, Arial")))
    return enforce_ontario_view(fig, view_id)


def make_rank_chart(current, shared_max, color):
    """Highest-rate PHU at the TOP; identical x-axis range in both compare charts.

    The single-disease version uses this same figure in a full-width container.
    Rates are never added across diseases.
    """
    ranking = current.dropna(subset=["Rate per 100,000"]).copy()
    if ranking.empty:
        return None
    ranking = (ranking.sort_values(
        ["Rate per 100,000", "Public health unit"],
        ascending=[False, True], kind="stable"
    ).head(10).reset_index(drop=True))
    ranking["Ranked PHU"] = [
        f"{i:>2}.  {short_phu(name)}"
        for i, name in enumerate(ranking["Public health unit"], 1)
    ]
    # In a Plotly horizontal bar chart, reversing the y-axis places category
    # 1 at the TOP. Pin category order rather than relying on row order.
    highest_first = ranking["Ranked PHU"].tolist()
    fig = px.bar(
        ranking, x="Rate per 100,000", y="Ranked PHU", orientation="h",
        text="Rate per 100,000", color_discrete_sequence=[color],
        custom_data=["Public health unit", "Cases"],
    )
    fig.update_traces(
        texttemplate="%{text:.1f}", textposition="outside", cliponaxis=False,
        textfont=dict(family="Segoe UI Semibold, Arial", size=16, color="#193b60"),
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       "Incidence: %{x:.1f} / 100k<br>"
                       "Reported cases: %{customdata[1]:,.0f}<extra></extra>"),
    )
    tidy(fig, height=400, margin_left=35)
    fig.update_layout(
        showlegend=False, xaxis_title="Rate per 100,000", yaxis_title=None,
        margin=dict(l=15, r=75, t=10, b=40),
    )
    # Deliberately SAME domain in disease 1 and disease 2 (shared_max computed
    # from BOTH selected diseases for the selected reporting year).
    fig.update_xaxes(range=[0, max(1.0, shared_max) * 1.12], fixedrange=True)
    fig.update_yaxes(
        categoryorder="array", categoryarray=highest_first,
        autorange="reversed", tickfont=dict(family="Segoe UI Semibold, Arial", size=15, color="#233a58"), automargin=True,
    )
    return fig


def make_heatmap(history, all_years, upper, color_scale):
    """Per-disease color scale is EXACTLY the same as the disease's incidence map."""
    frame = history.dropna(subset=["Public health unit", "Year"]).copy()
    if frame.empty:
        return None
    frame["Year"] = frame["Year"].astype(int)
    heat = frame.pivot(index="Public health unit", columns="Year", values="Rate per 100,000")
    heat = heat.reindex(columns=list(all_years))
    order = heat.mean(axis=1, skipna=True).sort_values(ascending=False).index
    heat = heat.loc[order]
    if heat.empty or not heat.notna().any().any():
        return None
    display_names = [short_phu(name) for name in heat.index]
    fig = go.Figure(go.Heatmap(
        z=heat.to_numpy(dtype=float), x=list(all_years), y=display_names,
        zmin=0, zmax=upper, colorscale=color_scale,
        colorbar={"title": {"text": "Rate / 100k", "font": {"size": 17}},
                   "tickfont": {"size": 15, "family": "Segoe UI Semibold, Arial"},
                   "thickness": 15, "len": 0.77},
        customdata=np.repeat(np.array(heat.index, dtype=object)[:, None], len(all_years), axis=1),
        hovertemplate="<b>%{customdata}</b><br>Year: %{x}<br>Rate / 100k: %{z:.1f}<extra></extra>",
        xgap=2, ygap=2, hoverongaps=False,
    ))
    tidy(fig, height=max(540, min(880, len(heat) * 24 + 100)), margin_left=85)
    fig.update_layout(margin=dict(l=10, r=10, t=18, b=35),
                      xaxis_title="Year", yaxis_title=None)
    fig.update_yaxes(tickfont=dict(family="Segoe UI Semibold, Arial", size=15, color="#273c59"),
                     autorange="reversed", automargin=True)
    fig.update_xaxes(type="category", side="bottom",
                     tickfont=dict(family="Segoe UI Semibold, Arial", size=15, color="#273c59"))
    return fig


# ------------------- APP -------------------
try:
    tables = load_data()
except (OSError, pd.errors.ParserError) as exc:
    st.error("Could not load the surveillance exports from outputs/dashboard/. Check the four dashboard CSV filenames.")
    st.exception(exc)
    st.stop()

tr = tables["trends"]
phu = tables["phu"]
demo = tables["demographics"]
out = tables["outcomes"]
years = sorted(int(y) for y in tr["Year"].dropna().unique())
diseases = sorted(tr["Disease"].dropna().unique().tolist())

st.markdown('''<div class="hero"><div class="eyebrow">ONTARIO · HEALTH ANALYTICS PORTFOLIO</div>
<h1>Infectious Disease Intelligence</h1>
<p>Interactive surveillance · Public health unit comparisons · Demographic insights · 2016–2025</p></div>''',
            unsafe_allow_html=True)

# Global interaction controls: mode, diseases, year window, and PHU filter.
with st.container(border=True):
    mode_col, first_col, second_col, years_col, region_col = st.columns([2.2, 2.6, 2.6, 2.1, 2.4])
    with mode_col:
        # Exactly one or two diseases are permitted; the mode drives the layout.
        mode = st.radio("Analysis mode", ["Single disease", "Compare two diseases"],
                        horizontal=True, index=1, key="analysis_mode")
    with first_col:
        default_first = diseases.index("Chlamydial Infections") if "Chlamydial Infections" in diseases else 0
        disease_one = st.selectbox("Disease 1", diseases, index=default_first, key="disease_one")
    if mode == "Compare two diseases":
        # Exclude the first choice to prevent duplicate-disease comparisons.
        with second_col:
            other_diseases = [name for name in diseases if name != disease_one]
            default_second = (other_diseases.index("Gonorrhoea (All Types)")
                              if "Gonorrhoea (All Types)" in other_diseases else 0)
            disease_two = st.selectbox("Disease 2", other_diseases,
                                       index=default_second, key="disease_two")
        chosen = [disease_one, disease_two]
    else:
        with second_col:
            st.caption("Single-disease analysis: maps and heatmaps expand to full width.")
        chosen = [disease_one]
    with years_col:
        start, end = st.select_slider("Year range", options=years, value=(years[0], years[-1]), key="year_range")
        # Streamlit's built-in thumb labels can render very small across versions.
        # Always display the selected endpoints using the same typography as filter labels.
        st.markdown(
            f'<div class="pho-year-values" aria-label="Selected years">'
            f'<span>{start}</span><span>{end}</span></div>',
            unsafe_allow_html=True,
        )
    with region_col:
        selected_phus = st.multiselect("Public health units",
                                      sorted(phu["Public health unit"].dropna().unique()),
                                      placeholder="All PHUs", key="selected_phus")

# Slice the provincial and PHU-level tables once, using the current UI state.
# PHU filtering affects regional charts, not province-wide KPI totals.
T = tr[tr["Disease"].isin(chosen) & tr["Year"].between(start, end)].copy()
P = phu[phu["Disease"].isin(chosen) & phu["Year"].between(start, end)].copy()
if selected_phus:
    P = P[P["Public health unit"].isin(selected_phus)].copy()
A = demo[demo["Disease"].isin(chosen) & demo["Year"].between(start, end)].copy()
O = out[out["Disease"].isin(chosen) & out["Year"].between(start, end)].copy()
color_by_disease = {name: [BLUE, TEAL][i] for i, name in enumerate(chosen)}
scale_by_disease = {name: [BLUE_SCALE, TEAL_SCALE][i] for i, name in enumerate(chosen)}

# Each disease receives its own provincial KPI. Never combine diseases and
# present the resulting number as if it describes one disease or unique people.
# The reporting-year slider controls these totals independently of the PHU filter.
def disease_kpi(disease_name):
    current = T[(T["Disease"] == disease_name) & (T["Year"] == end)]
    prior = T[(T["Disease"] == disease_name) & (T["Year"] == end - 1)]
    if current.empty or current["Cases"].isna().all():
        return "N/A", None
    current_cases = float(current["Cases"].sum())
    previous_cases = float(prior["Cases"].sum()) if not prior.empty else None
    delta = (100 * (current_cases - previous_cases) / previous_cases
             if previous_cases is not None and previous_cases > 0 else None)
    return f"{current_cases:,.0f}", (f"{delta:+.1f}% YoY" if delta is not None else None)

k1, k2, k3, k4 = st.columns(4)
with k1:
    # Consistent visual identity: first disease KPI uses the blue palette.
    with st.container(key="kpi_disease_1"):
        value, change = disease_kpi(chosen[0])
        st.metric(f"🔵 {chosen[0]} · {end}", value, delta=change)
with k2:
    if len(chosen) == 2:
        # The second disease uses teal, matching its map and chart series.
        with st.container(key="kpi_disease_2"):
            value, change = disease_kpi(chosen[1])
            st.metric(f"🟢 {chosen[1]} · {end}", value, delta=change)
    else:
        st.metric("Analysis mode", "Single disease")
with k3:
    st.metric("PHUs displayed", P["Public health unit"].nunique())
with k4:
    st.metric("Years selected", end - start + 1)
st.caption("KPI counts are reported cases, not distinct patients. The PHU filter affects regional maps, heatmaps, and rankings, not provincial or demographic totals.")

st.markdown('<div class="section">01 / Ontario public health unit maps</div>', unsafe_allow_html=True)
c_map_type, c_map_year, c_labels = st.columns([2.8, 1.3, 2])
with c_map_type:
    map_type = st.radio("Map type", ["Incidence rate / 100k", "Case count (bubbles)"],
                        horizontal=True, key="map_type")
with c_map_year:
    map_year = st.selectbox("Reporting year", list(range(start, end + 1)),
                            index=end - start, key="map_year")
with c_labels:
    label_style = st.selectbox("PHU labels on map", ["Key PHUs", "All PHUs", "Off"], key="label_style")

if len(chosen) == 2:
    st.info("**Independent map and heatmap scales:** each disease has its own blue or teal color range for readable regional patterns. "
            "**Shared regional ranking scale:** the two Top 10 bar charts use the same x-axis maximum. "
            "Compare ranking values directly, not color intensity between different diseases.")
else:
    st.info("The map and heatmap use the same blue color scale for the selected disease. Darker shades indicate higher reported incidence, not disease severity.")

# Prefer locally cached official PHU polygons; use labelled city points as fallback.
geo = get_boundaries() if map_type == "Incidence rate / 100k" else None
currents = {d: P[(P["Disease"] == d) & (P["Year"] == map_year)].copy() for d in chosen}
histories = {d: P[P["Disease"] == d].copy() for d in chosen}
# Each disease's incidence-map upper bound equals that disease's heatmap upper bound.
map_heat_scales = {d: scale_for_disease(histories[d]) for d in chosen}
# Crucial: regional ranking charts use ONE common x-axis upper bound for BOTH diseases.
regional_max = max([1.0] + [float(c["Rate per 100,000"].max())
                            for c in currents.values() if c["Rate per 100,000"].notna().any()])

# Adaptive layout: one disease uses full width; two diseases share the row.
map_cols = st.columns(2, gap="medium") if len(chosen) == 2 else [st.container()]
for index, disease in enumerate(chosen):
    with map_cols[index]:
        with st.container(border=True):
            title(f"{disease} · {map_year}", "PHU geography · reported cases per 100,000 residents" if map_type == "Incidence rate / 100k"
                  else "PHU case counts · bubble size corresponds to reported cases")
            reported = T[(T["Disease"] == disease) & (T["Year"] == map_year)]
            if not reported.empty:
                total_cases = reported["Cases"].sum()
                st.markdown(
                    '<div class="pho-panel-cases">'
                    '<span class="label">Provincial reported cases:</span>'
                    f'<span class="number">{total_cases:,.0f}</span>'
                    '</div>', unsafe_allow_html=True)
            current = currents[disease]
            if current.empty:
                st.warning(f"No PHU records for {disease} in {map_year}.")
                continue
            if map_type == "Incidence rate / 100k":
                fig, unmatched, fallback = make_incidence_map(
                    current, geo, map_heat_scales[disease], label_style,
                    scale_by_disease[disease], view_id=f"ontario-{index}-{disease}-{map_year}"
                )
            else:
                fig = make_bubble_map(current, label_style, scale_by_disease[disease],
                                      view_id=f"ontario-bubbles-{index}-{disease}-{map_year}")
                unmatched, fallback = 0, True
            if fig is None:
                st.info("No geographic observations available for this selection.")
            else:
                render(fig, key=f"phu_map_{index}_{disease}_{map_year}_{map_type}")
                if map_type == "Incidence rate / 100k":
                    st.caption(f"Color scale: 0–{map_heat_scales[disease]:.1f} cases per 100k. "
                               "The same scale is used in this disease's heatmap.")
                if unmatched:
                    st.caption(f"{unmatched} PHU(s) could not be matched to the available boundary version; they remain in the ranking and heatmap.")
                if fallback:
                    st.caption("City-marker reference map (not administrative boundaries); official boundary polygons were unavailable. "
                               "Marker locations are representative cities, not PHU centroids.")

# The ranking charts share one x-axis maximum, permitting meaningful comparisons.
st.markdown('<div class="section">02 / Regional incidence ranking</div>', unsafe_allow_html=True)
if len(chosen) == 2:
    st.caption(f"**Shared x-axis: 0–{regional_max * 1.12:.1f} per 100k for BOTH diseases.** "
               "Each ranking is ordered from highest incidence (top) to lowest (bottom). "
               "Equal bar lengths represent equal rates across both charts.")
# A single selected disease gets the ENTIRE width, matching its map above.
rank_cols = st.columns(2, gap="medium") if len(chosen) == 2 else [st.container()]
for i, disease in enumerate(chosen):
    with rank_cols[i]:
        with st.container(border=True):
            title(f"Top 10 PHUs by incidence rate · {disease}",
                  "Rank 1 (highest) at top · 10 (lowest among Top 10) at bottom" +
                  (" · shared comparison axis" if len(chosen) == 2 else ""))
            fig = make_rank_chart(currents[disease], regional_max, color_by_disease[disease])
            if fig is None:
                st.info("No incidence-rate observations available for this disease and year.")
            else:
                render(fig, key=f"rank_{i}")

# Disease-specific heatmaps reuse the exact color ranges of their maps.
st.markdown('<div class="section">03 / PHU-by-year incidence heatmaps</div>', unsafe_allow_html=True)
st.caption("Each heatmap uses **the same blue or teal gradient and numeric range as its own disease map**. "
           "A dark shade means a higher rate within that disease's scale, not necessarily a higher rate than the other disease.")
heat_cols = st.columns(2, gap="medium") if len(chosen) == 2 else [st.container()]
for i, disease in enumerate(chosen):
    with heat_cols[i]:
        with st.container(border=True):
            title(disease, f"PHUs × years · rate / 100k · fixed color range: 0–{map_heat_scales[disease]:.1f}")
            fig = make_heatmap(histories[disease], range(start, end + 1),
                               map_heat_scales[disease], scale_by_disease[disease])
            if fig is None:
                st.info("No numeric incidence-rate observations available for this disease and date range.")
            else:
                render(fig, key=f"heat_{i}")

# Trend and comparison plots show both selected diseases consistently.
st.markdown('<div class="section">04 / Disease trends and comparisons</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2, gap="medium")
with c1:
    with st.container(border=True):
        title("Reported cases over time", "Provincial reported cases by disease")
        fig = px.line(T.sort_values("Year"), x="Year", y="Cases", color="Disease",
                      markers=True, color_discrete_map=color_by_disease)
        tidy(fig, 340); fig.update_layout(xaxis_title=None, yaxis_title="Reported cases", legend_title_text="")
        render(fig)
with c2:
    with st.container(border=True):
        title("Compare selected diseases", "Cumulative provincial reported cases over selected years")
        totals = T.groupby("Disease", as_index=False)["Cases"].sum()
        fig = px.bar(totals, x="Disease", y="Cases", color="Disease",
                     text_auto=",.0f", color_discrete_map=color_by_disease)
        tidy(fig, 340); fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Cases")
        render(fig)

c3, c4 = st.columns(2, gap="medium")
with c3:
    with st.container(border=True):
        title("Year-over-year change", "Provincial change in reported cases (%)")
        changes = T.sort_values(["Disease", "Year"]).copy()
        changes["YoY (%)"] = changes.groupby("Disease")["Cases"].pct_change(fill_method=None) * 100
        changes["YoY (%)"] = changes["YoY (%)"].replace([np.inf, -np.inf], np.nan)
        valid = changes.dropna(subset=["YoY (%)"])
        if valid.empty:
            st.info("At least two years of valid case counts are required.")
        else:
            fig = px.line(valid, x="Year", y="YoY (%)", color="Disease",
                          markers=True, color_discrete_map=color_by_disease)
            tidy(fig, 330); fig.update_layout(legend_title_text="")
            render(fig)
with c4:
    with st.container(border=True):
        title("Geographic case burden", "Cases by PHU and disease across selected years")
        geo_cases = P.groupby(["Public health unit", "Disease"], as_index=False)["Cases"].sum()
        if geo_cases.empty:
            st.info("No geographic case counts available.")
        else:
            top_regions = (geo_cases.groupby("Public health unit")["Cases"].sum()
                           .nlargest(10).index)
            geo_cases = geo_cases[geo_cases["Public health unit"].isin(top_regions)].copy()
            geo_cases["PHU"] = geo_cases["Public health unit"].map(short_phu)
            fig = px.bar(geo_cases, y="PHU", x="Cases", color="Disease", orientation="h",
                         barmode="group", color_discrete_map=color_by_disease)
            tidy(fig, 330); fig.update_layout(yaxis_title=None, legend_title_text="")
            fig.update_yaxes(automargin=True)
            render(fig)

# Demographic and outcome records may be incomplete or use differing age bands.
st.markdown('<div class="section">05 / Demographic and outcomes profile</div>', unsafe_allow_html=True)
d1, d2 = st.columns(2, gap="medium")
with d1:
    with st.container(border=True):
        title("Age distribution", "Reported cases by disease and source age band")
        if A.empty:
            st.info("No age breakdown available for this selection.")
        else:
            ages = A.groupby(["Disease", "Age group"], as_index=False)["Number of cases"].sum()
            fig = px.bar(ages, x="Age group", y="Number of cases", color="Disease",
                         barmode="group", color_discrete_map=color_by_disease)
            tidy(fig, 340); fig.update_layout(xaxis_title=None, yaxis_title="Cases", legend_title_text="")
            render(fig)
            st.caption("Age bands can differ across diseases. Missing age groups are not zeros.")
with d2:
    with st.container(border=True):
        title("Reported cases by sex", "As recorded in the supplied dataset")
        if A.empty:
            st.info("No demographic records available.")
        else:
            sex = A.groupby(["Disease", "Sex"], as_index=False)["Number of cases"].sum()
            fig = px.bar(sex, x="Sex", y="Number of cases", color="Disease",
                         barmode="group", color_discrete_map=color_by_disease)
            tidy(fig, 340); fig.update_layout(xaxis_title=None, yaxis_title="Cases", legend_title_text="")
            render(fig)

with st.container(border=True):
    title("Disease outcomes", "Not all diseases have outcome records")
    if O.empty:
        st.info("Outcome records are unavailable for the selected disease(s).")
    else:
        outcomes = O.groupby(["Disease", "Outcome"], as_index=False)["Cases with outcome"].sum()
        fig = px.bar(outcomes, x="Outcome", y="Cases with outcome", color="Disease",
                     barmode="group", color_discrete_map=color_by_disease)
        tidy(fig, 330); fig.update_layout(xaxis_title=None, yaxis_title="Cases", legend_title_text="")
        render(fig)

# Export the filtered provincial records without altering the underlying source.
st.markdown('<div class="section">06 / Explore and export</div>', unsafe_allow_html=True)
with st.container(border=True):
    title("Filtered provincial disease records", "Rates remain disease-specific; rates are never added together")
    cols = ["Disease", "Year", "Cases", "Population", "Rate per 100,000"]
    st.dataframe(T[cols].sort_values(["Disease", "Year"]), hide_index=True,
                 use_container_width=True, height=300)
    st.download_button("↓ Download filtered CSV", data=T.to_csv(index=False).encode("utf-8-sig"),
                       file_name="pho_filtered_trends.csv", mime="text/csv")
    st.caption("Source: aggregated Ontario surveillance data provided for the project. "
               "Map boundaries: Government of Ontario, when available. Historical and merged PHUs may not match "
               "current boundary vintages. Portfolio analysis, not clinical advice.")
