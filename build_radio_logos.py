#!/usr/bin/env python3
"""
(2026-11-09, his ask: WWJ, WJR, KTRH and AT40 show only letters - "can we get them all?") Builds radio_logos.tsv.gz, Premierium's table of US radio station
logos: call sign + band + frequency -> logo picture address. The box (RadioLogos.kt) looks for a newer one about once a day and fills a station's logo from it.
(2026-11-15, his pick: a public repo) Moved from the app's repo to Wyred4Fun/premierium-radio-logos (public), which runs it daily and publishes the table
there; clean_job.py then cleans the logos (see there).

For each US AM and FM station in the FCC list (fcc_calls.tsv.gz, a copy of the app's app/src/main/assets/fcc_calls.tsv.gz: call, band, frequency, city,
state), the ones Radio Browser lists first (the ones the app shows), then the rest:
  1. Wikipedia: the station's article ("CALL (AM)", "CALL-FM", "CALL (FM)" or "CALL") - only when the article's opening text names the station's frequency or
     city of license - and its LOGO only: (2026-11-10, his find: KMXK/KXSS/WJON had a photo of their studios) the infobox's "logo" field, else the logo
     (P154) of the article's Wikidata item; the file is drawn by Wikipedia as a 256 px picture (an SVG logo comes as a PNG that keeps its see-through
     background). Never the page's own lead picture (prop=pageimages): that gives only free pictures - a photo of a building, never the (non-free) logo.
  2. TuneIn (opml.radiotime.com Search.ashx) when Wikipedia has none, or only a picture that is not a PNG: a result naming the call sign (as written, and
     no other place on the dial) with its frequency, city or state - or, named by its call sign alone, one whose TuneIn details (Describe.ashx) say so -
     or giving the frequency and the city or state; its "image" (2026-11-15, his find: WSM 650 had "Riddim WSM Radio" of Ottawa).
  3. Otherwise none (the box keeps Radio Browser's own logo, if it has one).
A see-through PNG is preferred over other pictures.
(2026-11-10) Asked first: his own first presets (PRIORITY), then the stations Radio Browser lists (the ones the app shows), most played first, then the rest.
An answer made the old way (a Wikipedia page picture, or none found) is asked again (LOGO_WAY).

Polite: a plain User-Agent naming the app, a pause between requests, and a cache (radio_logos_cache.json.gz, kept beside the table in the release) so a
run asks only about new or changed stations and ones not found in a while. A run stops asking after MAX_MINUTES and keeps the rest for next time.
(2026-11-09, review) A station whose question failed (Wikipedia or TuneIn not reached) keeps its last answer and is asked again next run: an outage never
erases a logo. A cache that is there but cannot be read stops the run, and a table much smaller than the last published one (under MIN_SHARE of its logos)
is not published, unless ALLOW_SMALLER=1 (set by hand when the cache really was lost).

Usage: build_radio_logos.py <fcc_calls.tsv.gz> <cache in (may be missing)> <out folder> [last published table (may be missing)]
Writes <out>/radio_logos.tsv.gz and <out>/radio_logos_cache.json.gz.
Test the reading and matching without the network: python3 -m unittest test_build_radio_logos (in this folder).
"""
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AGENT = "PremieriumRadioLogos/1.0 (Android TV radio app; logo table; https://github.com/Wyred4Fun/premierium-radio-logos)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
TUNEIN = "https://opml.radiotime.com/Search.ashx"
TUNEIN_DESCRIBE = "https://opml.radiotime.com/Describe.ashx"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
# (2026-11-10) Radio Browser's servers, as the app asks them (RadioDir.HOSTS): "all" first, then the named ones - one being down no longer puts the stations
# in the FCC's alphabetical order (W calls - WWJ, WIP - last, and past the time limit).
RADIO_BROWSER_HOSTS = ["all", "de1", "de2"]
RADIO_BROWSER_PATH = "/json/stations/search?countrycode=US&hidebroken=true&limit=20000"
PAUSE = float(os.environ.get("PAUSE", "1.0"))
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "200"))
# How long an answer is kept before it is asked again: a logo found, half a year; none found, three months.
FOUND_DAYS = 180
MISSED_DAYS = 90
WIKI_BATCH = 20  # prop=extracts gives at most 20 opening texts per request
DAY = 86400
# (2026-11-09, review) The least share of the last published table's logos a new table must have to be published.
MIN_SHARE = 0.8
# (2026-11-09, review) This many stations in a row not reached: the sites are down - the run stops asking (the rest wait for the next run).
MAX_FAILED_IN_A_ROW = 30

# (2026-11-10) How cached answers are made now: 2 = the Wikipedia logo (infobox / Wikidata). An answer of an older way that came from Wikipedia (its page
# picture: maybe a photo) or found nothing is asked again; a TuneIn logo is kept.
LOGO_WAY = 3
# (2026-11-15, his find: WSM 650's "Riddim WSM Radio") 3 = TuneIn's match made stricter: a TuneIn logo of an older way is asked again.
TUNEIN_PICTURE = re.compile(r"(tunein|radiotime)\.com/")
WIKI_PICTURE = re.compile(r"(upload|thumb)\.wikimedia\.org/|utm_campaign=api")
# (2026-11-10) His first presets and the stations he named (RadioDir.SEEDS): always asked first.
PRIORITY = ["WWJ", "WIP", "WJR", "KTRH"]
LOGO_WIDTH = "256"
PICTURE = re.compile(r"\.(svg|png|jpe?g|gif|webp)$", re.I)

# Names the box has that are not FCC call signs (his first presets): the table key, Wikipedia titles to try, a TuneIn search and the station's whole names.
# (2026-11-13, his report: The Blaze showed Evah Blaze Radio's logo) A TuneIn result is taken only when its name IS one of [names] (case, "The" and
# punctuation aside), never when it merely has one of their words: "blaze" alone picked an unrelated station. None matching: no logo (letters on the box).
# Wikipedia only from a named station's own titles, none here: "American Top 40"'s article logo is the show's (Ryan Seacrest's), not Casey Kasem's station.
EXTRAS = [
    {"call": "AT40", "titles": [], "query": "Classic American Top 40", "names": ["Classic American Top 40", "American Top 40 with Casey Kasem"]},
    {"call": "BLAZE", "titles": [], "query": "The Blaze Radio Network", "names": ["The Blaze Radio Network", "Blaze Radio Network"]},
]

# Short forms for the common picture hosts (the box writes them out again): keeps the table small.
PREFIXES = [("W:", "https://upload.wikimedia.org/wikipedia/"), ("T:", "https://cdn-profiles.tunein.com/"), ("R:", "https://cdn-radiotime-logos.tunein.com/")]


def shorten(url):
    for k, p in PREFIXES:
        if url.startswith(p):
            return k + url[len(p):]
    return url


# ---- reading ----

def read_fcc(path):
    """The FCC's stations: [{call, band, freq, city, state}]."""
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) != 5 or not p[0]:
                continue
            out.append({"call": base_call(p[0]), "band": p[1].upper(), "freq": p[2], "city": p[3], "state": p[4].upper()})
    return out


def base_call(call):
    """(2026-11-10) "WIP-FM", "wwj-am", "WKUF-LP" -> WIP, WWJ, WKUF: the app looks a station up by its letters alone (RadioLogos.lookup), with the band apart."""
    return (call or "").strip().upper().split("-")[0]


def key(st):
    return "%s|%s|%s" % (st["call"], st.get("band", ""), st.get("freq", ""))


def stamp(st):
    """What makes a cached answer still good: the station's place on the dial and its city (a move or a new frequency is asked again).
    (2026-11-13) A named station (EXTRAS) also by how it is looked for: a changed search or names asks it again at once (not after 180 days)."""
    s = "%s|%s|%s|%s" % (st.get("band", ""), st.get("freq", ""), st.get("city", "").upper(), st.get("state", ""))
    if st.get("extra"):
        s += "|q:%s|n:%s|t:%s" % (st.get("query", ""), ";".join(st.get("names") or []), ";".join(st.get("titles") or []))
    return s


def plain_name(text):
    """A station name for comparing: lower case, punctuation as spaces, a leading "the" dropped, spaces single."""
    t = re.sub(r"[^0-9a-z]+", " ", (text or "").lower()).strip()
    if t.startswith("the "):
        t = t[4:]
    return t


CALL_IN_NAME = re.compile(r"(?<![A-Z0-9])([KW][A-Z]{2,3})(?![A-Z])")


def radio_browser_calls(raw_json):
    """The call signs written in Radio Browser's US station names (asked first: they are the stations the app shows), each with its most clicks:
    {call: clicks}. (2026-11-10) "94.1 WIP-FM": the letters as the app reads them (capitals, as written; a -FM / -AM suffix left off - "Kiss FM" is not KISS)."""
    calls = {}
    for o in raw_json:
        if not isinstance(o, dict):
            continue
        try:
            n = int(o.get("clickcount") or 0)
        except (TypeError, ValueError):
            n = 0
        for m in CALL_IN_NAME.finditer(o.get("name") or ""):
            c = m.group(1)
            calls[c] = max(n, calls.get(c, 0))
    return calls


def ask_order(stations, shown):
    """(2026-11-10) PRIORITY first, then the stations Radio Browser shows (most played first), then the rest by call sign."""
    def rank(s):
        c = s["call"]
        if c in PRIORITY:
            return (0, PRIORITY.index(c), 0, c)
        if c in shown:
            return (1, 0, -shown[c], c)
        return (2, 0, 0, c)
    return sorted(stations, key=rank)


def titles_for(st):
    c, b = st["call"], st["band"]
    if b == "AM":
        return [c + " (AM)", c]
    if b == "FM":
        return [c + "-FM", c + " (FM)", c]
    return [c]


def wiki_titles(st):
    """The Wikipedia titles to try for a station. (2026-11-13, review of The Blaze) A named station (EXTRAS) only its own [titles] - none means Wikipedia is
    not asked: its article is taken without the frequency/city check, so a guessed title ("BLAZE") could bring any page's picture."""
    if st.get("extra"):
        return list(st.get("titles") or [])
    return st.get("titles") or titles_for(st)


def freq_words(st):
    """How an article or a listing writes the frequency: "950", "94.1"."""
    f = st.get("freq", "")
    if not f:
        return []
    return [f]


def mentions(text, word):
    return re.search(r"(?<![0-9A-Za-z.])" + re.escape(word) + r"(?![0-9A-Za-z])", text, re.I) is not None


def wiki_ok(st, extract):
    """An article is the station's when its opening names its frequency or its city of license."""
    if not extract:
        return False
    if any(mentions(extract, f) for f in freq_words(st)):
        return True
    city = st.get("city", "")
    return bool(city) and mentions(extract, city)


INFOBOX_LOGO = re.compile(r"^\s*\|\s*logo\s*=(.*)$", re.M | re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)


def infobox_logo(wikitext):
    """(2026-11-10) The file named in the article's infobox "logo" field ("File:WWJ logo.svg"), or "": "[[File:X.svg|250px]]", "X.svg", "Image:X.png"; not
    logo_size / logo_caption, a template, or a name that is not a picture."""
    text = COMMENT.sub("", wikitext or "")
    for m in INFOBOX_LOGO.finditer(text):
        v = m.group(1).strip()
        if not v or v.startswith("{{"):
            continue
        if v.startswith("[["):
            v = v[2:].split("]]")[0]
        v = v.split("|")[0].strip()
        v = re.sub(r"^(file|image)\s*:\s*", "", v, flags=re.I).replace("_", " ").strip()
        if v and PICTURE.search(v):
            return "File:" + v[0].upper() + v[1:]
    return ""


def page_text(p):
    """The wikitext of a page of the answer (formatversion 1 or 2), or ""."""
    revs = p.get("revisions") or []
    if not revs:
        return ""
    r = revs[0]
    main = (r.get("slots") or {}).get("main") or r
    return main.get("content") or main.get("*") or ""


def wiki_pages(answer):
    """MediaWiki's answer to a query: {title: (opening text, infobox logo file, Wikidata item)}, and the normalized titles and redirects to follow."""
    q = answer.get("query", {})
    follow = {}
    for n in q.get("normalized", []) or []:
        follow[n.get("from")] = n.get("to")
    redir = {}
    for r in q.get("redirects", []) or []:
        redir[r.get("from")] = r.get("to")
    by_title = {}
    pages = q.get("pages", {})
    for p in (pages.values() if isinstance(pages, dict) else pages):
        if "missing" in p or "invalid" in p:
            continue
        qid = (p.get("pageprops") or {}).get("wikibase_item", "") or ""
        by_title[p.get("title")] = (p.get("extract", "") or "", infobox_logo(page_text(p)), qid)
    return by_title, follow, redir


def wikidata_logo(entity):
    """(2026-11-10) The logo file (P154) of a Wikidata item's answer, or "": the preferred one, else a current one (no end date), else the first; never a
    deprecated one."""
    claims = [c for c in ((entity or {}).get("claims") or {}).get("P154", []) if c.get("rank") != "deprecated"]
    def name(c):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        return v if isinstance(v, str) and PICTURE.search(v) else ""
    claims = [c for c in claims if name(c)]
    if not claims:
        return ""
    best = [c for c in claims if c.get("rank") == "preferred"] or [c for c in claims if "P582" not in (c.get("qualifiers") or {})] or claims
    v = name(best[0]).replace("_", " ")
    return "File:" + v[0].upper() + v[1:]


def file_urls(answer):
    """(2026-11-10) imageinfo's answer: {"File:X.svg": the 256 px picture (a PNG for an SVG)}, the asked names' spellings followed. A file kept on Commons
    comes back "missing" (not a local page) but with its imageinfo: taken."""
    q = (answer or {}).get("query", {})
    follow = {n.get("from"): n.get("to") for n in (q.get("normalized") or [])}
    out = {}
    pages = q.get("pages", {})
    for p in (pages.values() if isinstance(pages, dict) else pages):
        info = (p.get("imageinfo") or [{}])[0]
        u = info.get("thumburl") or info.get("url") or ""
        if u:
            out[p.get("title")] = https(u)
    for a, b in follow.items():
        if b in out:
            out[a] = out[b]
    return out


def resolve(title, follow, redir):
    t = follow.get(title, title)
    seen = 0
    while t in redir and seen < 5:
        t = redir[t]
        seen += 1
    return t


def is_png(url):
    return url.lower().split("?")[0].endswith(".png")


def mentions_cs(text, word):
    """(2026-11-15) The call sign as written, capitals and all: "Katy Perry Radio" is not KATY, "Kora" is not KORA."""
    return re.search(r"(?<![0-9A-Za-z.])" + re.escape(word) + r"(?![0-9A-Za-z])", text) is not None


DIAL = re.compile(r"(?<![0-9.])(\d{2,4}(?:\.\d)?)(?![0-9])")


def dial_numbers(text):
    """The numbers in a TuneIn name that read like a place on the dial: 87.5 to 108 (FM, "94.1", "Hot 97") or 530 to 1710 (AM)."""
    out = []
    for m in DIAL.finditer(text or ""):
        v = float(m.group(1))
        if 87.5 <= v <= 108.0 or (530 <= v <= 1710 and "." not in m.group(1)):
            out.append(m.group(1))
    return out


def other_dial(st, text):
    """(2026-11-15, his find: KALV 101.5 had "Stereo 1430 KALV", KAYO 100.9 a Washington "96.9 KAYO") True when the name gives a place on the dial and none of
    them is this station's ("Hot 103" is 103.3's; an AM/FM pair naming both is fine)."""
    nums = dial_numbers(text)
    f = st.get("freq", "")
    if not nums or not f:
        return False
    try:
        fv = float(f)
    except ValueError:
        return False
    for n in nums:
        v = float(n)
        if v == fv or ("." not in n and 87.5 <= fv <= 108.0 and int(fv) == int(v)):
            return False
        # (review) An FM frequency written without its dot: "Channel 933" is 93.3's, "Mix 1065" 106.5's.
        if "." not in n and 87.5 <= fv <= 108.0 and n == f.replace(".", ""):
            return False
    return True


def describe_ok(st, d):
    """(2026-11-15, his find: WSM 650 had "Riddim WSM Radio" of Ottawa, KIKS a Slovak station) TuneIn's details of a result ([d]: its Describe answer's
    station) are this station's: its call sign's letters, and its frequency or its city or state."""
    if not isinstance(d, dict):
        return False
    # ("WWJ-AM"; "WNIA Gospel Radio": its first word; "Riddim WSM Radio" is not WSM)
    if base_call((d.get("call_sign", "") or "").split(" ")[0]) != st.get("call", ""):
        return False
    f = st.get("freq", "")
    try:
        if f and float(d.get("frequency") or 0) == float(f):
            return True
    except ValueError:
        pass
    loc = d.get("location", "") or ""
    state_name = STATE_NAMES.get(st.get("state", ""), "")
    return bool((st.get("city") and mentions(loc, st["city"])) or (state_name and mentions(loc, state_name)) or (st.get("state") and mentions_cs(loc, st["state"])))


def tunein_pick(st, answer, names=None, describe=None):
    """The picture of TuneIn's result that is this station; "" when none; None when TuneIn's details of a likely result could not be read (asked again).
    With [names] (a named station): only a result whose whole name is one of them.
    (2026-11-15) A station's: its call sign written as it is (capitals) and no other place on the dial in its name, with its frequency, city or state named;
    named only by its call sign, TuneIn's details of it ([describe]: guide id -> its Describe station, None when not reached) must say so too."""
    body = answer.get("body", []) if isinstance(answer, dict) else []
    call = st.get("call", "")
    state_name = STATE_NAMES.get(st.get("state", ""), "")
    failed = False
    for o in body:
        if not isinstance(o, dict):
            continue
        img = o.get("image") or ""
        if not img.startswith("http"):
            continue
        text = o.get("text", "") or ""
        allt = " ".join(str(o.get(k, "") or "") for k in ("text", "subtext", "location", "formats", "genre_id"))
        if names is not None:
            if plain_name(text) in {plain_name(n) for n in names}:
                return https(img)
            continue
        if other_dial(st, text):
            continue
        f = st.get("freq", "")
        placed = (st.get("city") and mentions(allt, st["city"])) or (state_name and mentions(allt, state_name)) or (st.get("state") and mentions_cs(allt, st["state"]))
        # (an AM station is not its FM sister: "WWJ" is not "WWJ-FM")
        if call and mentions_cs(text, call) and not (st.get("band") == "AM" and mentions_cs(text, call + "-FM")):
            if (f and mentions(allt, f)) or placed:
                return https(img)
            gid = o.get("guide_id") or ""
            if describe is None or not gid:
                continue
            d = describe(gid)
            if d is None:
                failed = True
                continue
            if describe_ok(st, d):
                return https(img)
            continue
        if f and mentions(allt, f) and placed:
            return https(img)
    return None if failed else ""


def https(url):
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}


# (2026-11-11, his pick: a rejection rule; WNIC had a photo of a building) A picture whose file name says it is a photo of a place, not a logo, is never used:
# a name with "logo" or "wordmark" in it is always kept.
PHOTO_NAME = re.compile(r"building|studios?(?![a-z])|office|headquarters|transmitter|towers?(?![a-z])|antenna|mast(?![a-z])|(?<!out)doors?(?![a-z])|(?<![a-z])(img|dsc|dscn|p)[_ -]?\d{3,}", re.I)


def looks_like_photo(url):
    """Whether a picture's file name says it is a photo (a building, studio, tower, a camera's number), not a station logo."""
    if not url:
        return False
    name = urllib.parse.unquote(url.split("?")[0].rstrip("/").rsplit("/", 1)[-1])
    if re.search(r"logo|wordmark", name, re.I):
        return False
    return bool(PHOTO_NAME.search(name))


def choose(wiki_url, tunein_url):
    """A see-through PNG first, then whatever there is (Wikipedia's before TuneIn's); a picture named like a photo of a place is left out."""
    wiki_url = "" if looks_like_photo(wiki_url) else wiki_url
    tunein_url = "" if looks_like_photo(tunein_url) else tunein_url
    for u in (wiki_url, tunein_url):
        if u and is_png(u):
            return u
    return wiki_url or tunein_url or ""


def due(entry, st, now):
    """Whether a station is to be asked about (again)."""
    if not entry or entry.get("s") != stamp(st):
        return True
    # (2026-11-10) Made the old way and from Wikipedia's page picture (maybe a photo of the studios), or nothing found then: asked again now.
    # (2026-11-11) Wikipedia's page picture came as a thumb.wikimedia.org address (utm_campaign=api): 810 stations kept one for 180 days because only
    # upload.wikimedia.org was looked for.
    if entry.get("v", 1) < 2 and (not entry.get("u") or WIKI_PICTURE.search(entry.get("u", ""))):
        return True
    if entry.get("v", 1) < 3 and TUNEIN_PICTURE.search(entry.get("u", "")):
        return True
    age = now - entry.get("t", 0)
    return age > (FOUND_DAYS if entry.get("u") else MISSED_DAYS) * DAY


def table_count(path):
    """How many logos a published table has (its lines that are not the heading); None when there is no table."""
    if not path or not os.path.exists(path):
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        # (2026-11-15) Not the "=" lines of the clean copies (clean_job.py): logos only.
        return sum(1 for line in fh if line.strip() and not line.startswith("#") and not line.startswith("="))


def too_small(n, last, share=MIN_SHARE):
    """Whether a new table of [n] logos is much smaller than the last published one of [last] (None: there is none)."""
    return last is not None and last > 0 and n < last * share


def write_table(stations, cache, out_path, made):
    lines = ["#radio_logos|" + made + "|call|band|freq|logo"]
    n = 0
    for st in stations:
        e = cache.get(key(st))
        if e and e.get("u"):
            lines.append("|".join([st["call"], st.get("band", ""), st.get("freq", ""), shorten(e["u"])]))
            n += 1
    with gzip.open(out_path, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write("\n".join(lines) + "\n")
    return n


# ---- asking (network) ----

# (2026-11-11, his report: the logos are still not fixed - the last run's log held 158 Wikipedia and 42 Wikidata "429 Too Many Requests", then gave up) Told to
# slow down, a request now waits as long as the site says (Retry-After, 10 to 90 seconds) and every request after it waits a second longer (at most 8 more),
# for the rest of the run; six tries, not three.
_EXTRA = [0.0]


def get_json(url):
    last = None
    for attempt in range(6):
        try:
            if _EXTRA[0]:
                time.sleep(_EXTRA[0])
            req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                try:
                    wait = float(e.headers.get("Retry-After") or 0)
                except Exception:
                    wait = 0.0
                _EXTRA[0] = min(_EXTRA[0] + 1.0, 8.0)
                time.sleep(min(max(wait, 10.0), 90.0))
            else:
                time.sleep(3 + attempt * 5)
        except Exception as e:  # a busy moment: wait and try again
            last = e
            time.sleep(3 + attempt * 5)
    print("gave up on %s: %s" % (url.split("?")[0], last))
    return None


def wiki_batch(titles):
    """MediaWiki's answer; None when it was not reached."""
    # (2026-11-10) The opening text, the Wikidata item and the opening section's wikitext (its infobox) - no page picture.
    params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1", "prop": "extracts|pageprops|revisions", "ppprop": "wikibase_item",
              "rvprop": "content", "rvslots": "main", "rvsection": "0", "exintro": "1", "explaintext": "1", "exlimit": "20", "exchars": "1200",
              "titles": "|".join(titles)}
    time.sleep(PAUSE)
    a = get_json(WIKI_API + "?" + urllib.parse.urlencode(params))
    # Should Wikipedia ever refuse the opening section for several pages at once: the whole text instead.
    if isinstance(a, dict) and "error" in a and "section" in json.dumps(a["error"]).lower():
        params.pop("rvsection")
        time.sleep(PAUSE)
        a = get_json(WIKI_API + "?" + urllib.parse.urlencode(params))
    return None if not isinstance(a, dict) or "error" in a else a


def wikidata_items(qids):
    """(2026-11-10) Wikidata's answer for the items' claims {qid: entity}; None when it was not reached."""
    time.sleep(PAUSE)
    a = get_json(WIKIDATA_API + "?" + urllib.parse.urlencode({"action": "wbgetentities", "format": "json", "props": "claims", "ids": "|".join(qids)}))
    if not isinstance(a, dict) or "error" in a:
        return None
    return a.get("entities") or {}


def wiki_files(files):
    """(2026-11-10) Wikipedia's 256 px pictures of the logo files {"File:X": address} (a file on Commons too); None when it was not reached."""
    time.sleep(PAUSE)
    a = get_json(WIKI_API + "?" + urllib.parse.urlencode({"action": "query", "format": "json", "formatversion": "2", "prop": "imageinfo", "iiprop": "url",
                                                           "iiurlwidth": LOGO_WIDTH, "titles": "|".join(files)}))
    if not isinstance(a, dict) or "error" in a:
        return None
    return file_urls(a)


def tunein_search(query):
    """TuneIn's answer; None when it was not reached."""
    time.sleep(PAUSE)
    return get_json(TUNEIN + "?" + urllib.parse.urlencode({"query": query, "types": "station", "render": "json"}))


def tunein_describe(gid):
    """(2026-11-15) TuneIn's details of a station (call sign, frequency, place): its Describe answer's station; None when TuneIn was not reached."""
    time.sleep(PAUSE)
    a = get_json(TUNEIN_DESCRIBE + "?" + urllib.parse.urlencode({"id": gid, "render": "json"}))
    if not isinstance(a, dict):
        return None
    body = a.get("body") or []
    return body[0] if body and isinstance(body[0], dict) else {}


def ask_wikipedia(batch):
    """Each station of [batch] -> its Wikipedia logo ("" when none; None when a request it needed failed). (2026-11-10) The article's infobox logo, else its
    Wikidata item's logo (P154), drawn at 256 px - never the page's own picture."""
    asked = []
    for st in batch:
        asked.extend(wiki_titles(st))
    pages, follow, redir = {}, {}, {}
    failed = set()
    for i in range(0, len(asked), WIKI_BATCH):
        a = wiki_batch(asked[i:i + WIKI_BATCH])
        if a is None:
            failed.update(asked[i:i + WIKI_BATCH])
            continue
        p, f, r = wiki_pages(a)
        pages.update(p); follow.update(f); redir.update(r)
    # The station's article: the first of its titles whose opening names its frequency or city (a page with no logo still gives its Wikidata item).
    picked = {}
    for st in batch:
        titles = wiki_titles(st)
        logo, qid = "", ""
        for t in titles:
            got = pages.get(resolve(t, follow, redir))
            if not got or not (st.get("extra") or wiki_ok(st, got[0])):
                continue
            if got[1]:
                logo = got[1]
                break
            qid = qid or got[2]
        picked[key(st)] = (logo, qid, any(t in failed for t in titles))
    # Wikidata's logo for the ones whose infobox has none.
    qids = sorted(set(q for (lg, q, _) in picked.values() if not lg and q))
    items, items_failed = {}, False
    for i in range(0, len(qids), 50):
        got = wikidata_items(qids[i:i + 50])
        if got is None:
            items_failed = True
            continue
        items.update(got)
    files = {}
    for k, (lg, q, bad) in picked.items():
        f = lg or (wikidata_logo(items.get(q)) if q else "")
        files[k] = f
    # The files drawn as pictures.
    names = sorted(set(f for f in files.values() if f))
    urls, urls_failed = {}, set()
    for i in range(0, len(names), 50):
        got = wiki_files(names[i:i + 50])
        if got is None:
            urls_failed.update(names[i:i + 50])
            continue
        urls.update(got)
    found = {}
    for st in batch:
        k = key(st)
        lg, q, bad = picked[k]
        f = files[k]
        url = urls.get(f, "") if f else ""
        if url:
            found[k] = url
        elif (f and f in urls_failed) or (not lg and q and items_failed and q not in items) or (bad and not f):
            found[k] = None
        else:
            found[k] = ""
    return found


def kept_tunein(old, got, t):
    """(2026-11-15) A TuneIn logo found the older way, asked again: when TuneIn's answer this time does not list that picture at all (its search answers vary),
    it is kept - only one the stricter match has looked at and turned down is let go."""
    if t or not old or not TUNEIN_PICTURE.search(old):
        return t
    body = got.get("body", []) if isinstance(got, dict) else []
    listed = any(isinstance(o, dict) and https(o.get("image") or "") == old for o in body)
    return t if listed else old


def answer_for(st, w, search=None, describe=None, old=""):
    """A station's new cache answer's logo from its Wikipedia logo [w] (and TuneIn when that is not a PNG); None when a question failed (keep the old answer).
    ([search] and [describe] stand in for TuneIn in tests; with a stand-in search and no describe, TuneIn's details are not asked.)"""
    ask = describe if describe is not None else (tunein_describe if search is None else None)
    if w is None:
        # (2026-11-11, his report: the logos are still not fixed) Wikipedia would not answer (429): TuneIn alone gives the logo when it has one; with none found
        # the station is asked again next run (not recorded as "no logo").
        q = st.get("query") or (st["call"] + " " + st["freq"]).strip()
        got = (search or tunein_search)(q)
        if got is None:
            return None
        t = kept_tunein(old, got, tunein_pick(st, got, st.get("names"), ask))
        return t if t else None
    t = ""
    if not is_png(w):
        q = st.get("query") or (st["call"] + " " + st["freq"]).strip()
        got = (search or tunein_search)(q)
        if got is None:
            return None
        t = tunein_pick(st, got, st.get("names"), ask)
        if t is None:
            return None
        t = kept_tunein(old, got, t)
    return choose(w, t)


def main(fcc_path, cache_path, out_dir, last_table=None):
    started = time.time()
    now = int(started)
    os.makedirs(out_dir, exist_ok=True)
    stations = read_fcc(fcc_path)
    if len(stations) < 5000:
        sys.exit("too few FCC stations (%d): not as expected - nothing written" % len(stations))
    extras = [{"call": x["call"], "band": "", "freq": "", "city": "", "state": "", "titles": x["titles"], "query": x["query"], "names": x["names"], "extra": True} for x in EXTRAS]
    cache = {}
    if cache_path and os.path.exists(cache_path):
        # (2026-11-09, review) A cache that is there but cannot be read is not "no cache": starting afresh would publish a much smaller table.
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as fh:
                cache = json.load(fh)
        except Exception as e:
            sys.exit("cache not readable (%s): stopped - nothing written" % e)
    last = table_count(last_table)
    # His first presets, then Radio Browser's stations (the ones the app shows, most played first), the rest after.
    shown = {}
    for host in RADIO_BROWSER_HOSTS:
        try:
            time.sleep(PAUSE)
            req = urllib.request.Request("https://%s.api.radio-browser.info%s" % (host, RADIO_BROWSER_PATH), headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                shown = radio_browser_calls(json.loads(r.read().decode("utf-8")))
            if shown:
                break
        except Exception as e:
            print("Radio Browser (%s) not reached (%s)" % (host, type(e).__name__))
    if not shown:
        print("Radio Browser not reached: his presets first, then the FCC's order")
    order = extras + ask_order(stations, shown)
    todo = [s for s in order if due(cache.get(key(s)), s, now)]
    print("%d stations, %d to ask about (%d of them in Radio Browser)" % (len(order), len(todo), sum(1 for s in todo if s["call"] in shown)))
    done = 0
    failed = 0
    in_a_row = 0
    step = 10
    for i in range(0, len(todo), step):
        if time.time() - started > MAX_MINUTES * 60:
            print("time is up: %d left for the next run" % (len(todo) - i))
            break
        if in_a_row >= MAX_FAILED_IN_A_ROW:
            print("%d stations in a row not reached: stopped asking, %d left for the next run" % (in_a_row, len(todo) - i))
            break
        batch = todo[i:i + step]
        wiki = ask_wikipedia(batch)
        for st in batch:
            u = answer_for(st, wiki.get(key(st), ""), old=(cache.get(key(st)) or {}).get("u", ""))
            # (2026-11-09, review) Not reached: the old answer (if any) is kept as it was, and the station is asked again next run.
            if u is None:
                failed += 1
                in_a_row += 1
                continue
            in_a_row = 0
            cache[key(st)] = {"u": u, "s": stamp(st), "t": now, "v": LOGO_WAY}
            done += 1
        if done % 500 < step:
            print("asked about %d (%.0f min)" % (done, (time.time() - started) / 60))
    # Stations the FCC no longer lists are let go.
    live = set(key(s) for s in order)
    cache = {k: v for k, v in cache.items() if k in live}
    made = time.strftime("%Y-%m-%d", time.gmtime())
    n = write_table(extras + stations, cache, os.path.join(out_dir, "radio_logos.tsv.gz"), made)
    with gzip.open(os.path.join(out_dir, "radio_logos_cache.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump(cache, fh, separators=(",", ":"))
    print("%d logos in the table; %d stations asked about this run; %d not reached (kept for the next run)" % (n, done, failed))
    if n == 0:
        sys.exit("no logos at all: something is wrong - not published")
    # (2026-11-09, review) Months of answers are never replaced by a much smaller table.
    if too_small(n, last) and os.environ.get("ALLOW_SMALLER") != "1":
        sys.exit("only %d logos, the last published table has %d: not published (ALLOW_SMALLER=1 to publish it anyway)" % (n, last))


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) == 5 else None)
