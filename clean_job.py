#!/usr/bin/env python3
"""
(2026-11-15, his ask: every radio logo a clean see-through PNG, stored on GitHub) The cleaning step of the logo job, after the table is built
(build_radio_logos.py). Every logo the app may show - each picture in the table, and (his pick) every Radio Browser US station's own logo - is downloaded
once and looked at (clean_logos.py): a plain white or near-white ground is taken off and the clean PNG kept in logos/<2>/<name>.png. (2026-11-19, his ask,
after Wikipedia answered his Onn's own requests with 429) Every other picture - see-through ones, ones with a ground of their own - is kept there too, as it
is (made smaller, as a PNG), so the app loads every logo from this repo and never asks Wikipedia or a station's site itself. The PNG's name is the first 16 letters of the SHA-1 of the logo's address as the app has it,
so the app finds the clean copy of any logo from its address alone; the table gets one line "=<name>.<version>" for each clean copy (<version>: the first
8 letters of the SHA-1 of the file, so a copy made again is fetched again; a line the app's reader of older builds skips: it wants four fields).

Polite and resumable like the table: Wikimedia's pictures are fetched as its 330 px thumbnails (its full-size host refuses a run like this), a pause
between requests to the same site, a cache (radio_logos_clean.json.gz) so a picture is looked at once (again after LOOK_DAYS, or when the cleaning
changes: CLEAN_WAY), and the run stops at its deadline, leaving the rest for the next.
An outage never removes a clean copy: a picture not reached keeps its last answer, a copy is let go only after no logo has used it for UNUSED_DAYS, a
copy in logos/ with no cache entry (the cache lost) is taken back, and only a copy the last run's cache named can be removed.

Usage: clean_job.py <table.tsv.gz (rewritten with the "=" lines)> <clean cache in (may be missing)> <clean cache out> <logos folder>
Tests: python3 -m unittest test_clean_logos (in this folder).
"""
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import build_radio_logos as table
import clean_logos

AGENT = "PremieriumRadioLogos/1.0 (https://github.com/Wyred4Fun/premierium-radio-logos; Android TV radio app logo cleaning)"
# (2026-11-15) Raised when the cleaning changes: every picture is looked at again.
CLEAN_WAY = 1
LOOK_DAYS = 180         # a picture looked at is looked at again after this long (a site may change the file behind the same address)
BAD_DAYS = 30           # not a picture / gone (404): asked again after this long
UNUSED_DAYS = 90        # a clean copy no logo has used for this long is let go
DAY = 86400
TIMEOUT = 20
WHOLE_SECONDS = 40   # a picture that takes longer than this to arrive is left for the next run
PAUSE_SAME_SITE = float(os.environ.get("PAUSE_SAME_SITE", "1.0"))
PAUSE_OTHER = 0.15
MAX_IN_A_ROW_REFUSED = 25   # this many "too many requests" from one site in a row: that site waits for the next run
NAME_LEN = 16
THUMB_WIDTH = 330


def name_for(url):
    """The clean copy's name for a logo address: the first 16 letters of its SHA-1 (as the app works it out: RadioLogos.cleanFor)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:NAME_LEN]


def path_for(folder, name):
    return os.path.join(folder, name[:2], name + ".png")


WIKI_ORIGINAL = re.compile(r"^https://upload\.wikimedia\.org/wikipedia/([^/]+)/([0-9a-f])/([0-9a-f]{2})/([^?/]+)(?:\?.*)?$")
WIKI_THUMB = re.compile(r"^https://(?:upload|thumb)\.wikimedia\.org/wikipedia/([^/]+)/thumb/([0-9a-f])/([0-9a-f]{2})/([^/]+)/(\d+)px-[^?]*(?:\?.*)?$")


def fetch_address(url):
    """Where a logo is fetched from for cleaning: a Wikimedia picture as its 330 px thumbnail on thumb.wikimedia.org (an SVG as its PNG), else the address."""
    m = WIKI_ORIGINAL.match(url)
    if m and "/thumb/" not in url:
        proj, a, ab, f = m.groups()
        tail = f + (".png" if f.lower().endswith(".svg") else "")
        return "https://thumb.wikimedia.org/wikipedia/%s/thumb/%s/%s/%s/%dpx-%s" % (proj, a, ab, f, THUMB_WIDTH, tail)
    m = WIKI_THUMB.match(url)
    if m:
        proj, a, ab, f, _ = m.groups()
        tail = f + (".png" if f.lower().endswith(".svg") else "")
        return "https://thumb.wikimedia.org/wikipedia/%s/thumb/%s/%s/%s/%dpx-%s" % (proj, a, ab, f, THUMB_WIDTH, tail)
    return url


def site(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def expand(short):
    for k, p in table.PREFIXES:
        if short.startswith(k):
            return p + short[len(k):]
    return short


def read_table(path):
    """The table's lines: (heading, [rows as written], [logo addresses as the app has them]); old "=" lines left out."""
    head, rows, urls = "", [], []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("#"):
                head = head or line
                continue
            if line.startswith("="):
                continue
            rows.append(line)
            p = line.split("|")
            if len(p) == 4 and p[3]:
                urls.append(expand(p[3]))
    return head, rows, urls


def write_table(path, head, rows, names):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("\n".join([head] + rows + ["=" + n for n in sorted(names)]) + "\n")


def radio_browser_logos():
    """Radio Browser's US stations' own logos (the app shows one when the table has none), most played first; [] when it was not reached."""
    for host in table.RADIO_BROWSER_HOSTS:
        try:
            req = urllib.request.Request("https://%s.api.radio-browser.info%s" % (host, table.RADIO_BROWSER_PATH), headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            out = []
            for o in sorted((o for o in data if isinstance(o, dict)), key=lambda o: -int(o.get("clickcount") or 0)):
                f = o.get("favicon") or ""
                if f.startswith("http"):
                    out.append(f)
            if out:
                return out
        except Exception as e:
            print("Radio Browser (%s) not reached (%s)" % (host, type(e).__name__))
    return []


# (2026-11-19) The verdicts whose picture is kept as it is (every picture but "bad": not one, or gone).
KEPT_AS_IS = ("transparent", "colored", "small", "blank")


def due(entry, now):
    """Whether a logo address is to be looked at (again)."""
    if not entry or entry.get("k", 0) < CLEAN_WAY:
        return True
    # (2026-11-19) A picture looked at before copies of every logo were kept: fetched again for its copy.
    if entry.get("r") in KEPT_AS_IS and not entry.get("h"):
        return True
    age = now - entry.get("t", 0)
    if entry.get("r") == "bad":
        return age > BAD_DAYS * DAY
    return age > LOOK_DAYS * DAY


class Refused(Exception):
    """The site said "too many requests" or is down for now: asked again next run."""


def download(url):
    """The picture's bytes; None when it is not there (404, not a picture: recorded as "bad"); Refused when the site was busy or not reached."""
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "image/*,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            # (dry run 2026-11-15: one site trickled for nine minutes) Read in pieces, at most WHOLE_SECONDS in all.
            end = time.time() + WHOLE_SECONDS
            parts, n = [], 0
            while True:
                if time.time() > end:
                    raise Refused("too slow")
                b = r.read(65536)
                if not b:
                    break
                parts.append(b)
                n += len(b)
                if n > clean_logos.MAX_BYTES:
                    return None
            return b"".join(parts)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504):
            raise Refused(str(e.code))
        return None
    except Exception as e:
        raise Refused(type(e).__name__)


def look(url, now, entry, folder, get=download):
    """Looks at one logo: a new cache entry (a clean copy written when there is one), or None when it was not reached (the old entry stays)."""
    try:
        data = get(fetch_address(url))
    except Refused:
        return None
    if data is None:
        return {"r": "bad", "t": now, "k": CLEAN_WAY, "h": (entry or {}).get("h", "")}
    try:
        res = clean_logos.clean(data)
    except Exception as x:   # (review) a picture the tools choke on is "bad", never the end of the run
        print("could not look at %s: %s" % (url[:100], type(x).__name__))
        res = clean_logos.Result("bad", note="error")
    e = {"r": res.verdict, "t": now, "k": CLEAN_WAY, "h": ""}
    png = res.png
    if png is None and res.verdict in KEPT_AS_IS:
        try:
            png = clean_logos.as_png(data)
        except Exception as x:
            print("could not copy %s: %s" % (url[:100], type(x).__name__))
    if png:
        name = name_for(url)
        p = path_for(folder, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        old = None
        if os.path.exists(p):
            with open(p, "rb") as fh:
                old = fh.read()
        if old != png:
            with open(p + ".part", "wb") as fh:
                fh.write(png)
            os.replace(p + ".part", p)
        e["h"] = name
    elif res.verdict == "bad" and entry and entry.get("h"):
        # A picture that came back broken this once keeps its clean copy until it is looked at again.
        e["h"] = entry["h"]
    return e


def let_go(cache, folder, now, known):
    """Entries no logo has used for UNUSED_DAYS are let go; then a clean copy is removed only when the last run's cache named it ([known]) and no entry
    names it now (review: a lost cache, or one missing some entries, never empties logos/; a file no cache ever named is left alone). How many files went."""
    for u in [u for u, e in cache.items() if now - e.get("s", e.get("t", 0)) > UNUSED_DAYS * DAY]:
        cache.pop(u, None)
    keep = set(e["h"] for e in cache.values() if e.get("h"))
    gone = 0
    if os.path.isdir(folder):
        for d in os.listdir(folder):
            sub = os.path.join(folder, d)
            if not os.path.isdir(sub):
                continue
            for f in os.listdir(sub):
                if f.endswith(".png") and f[:-4] in known and f[:-4] not in keep:
                    os.remove(os.path.join(sub, f))
                    gone += 1
    return gone


def version_of(path):
    """The first 8 letters of the SHA-1 of a clean copy's bytes: the app asks for <name>.png?v=<this>, so a copy made again is fetched again."""
    with open(path, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:8]


def run(table_path, cache_in, cache_out, folder, deadline, rb=None, get=download, pause=True):
    now = int(time.time())
    cache = {}
    if cache_in and os.path.exists(cache_in):
        try:
            with gzip.open(cache_in, "rt", encoding="utf-8") as fh:
                cache = json.load(fh)
        except Exception as e:
            sys.exit("clean cache not readable (%s): stopped - nothing written" % e)
    # The clean copies the last run's cache named: the only ones that may be removed.
    known = set(e.get("h") for e in cache.values() if e.get("h"))
    head, rows, table_urls = read_table(table_path)
    rb_urls = radio_browser_logos() if rb is None else rb
    # Radio Browser's logos first (most played first: the ones the app shows most), then the table's; each address once.
    order, seen = [], set()
    for u in rb_urls + table_urls:
        if u not in seen:
            seen.add(u)
            order.append(u)
    # Still in use: the time is noted (a copy is let go only after UNUSED_DAYS unused). (review) A clean copy already in logos/ with no cache entry (the
    # cache lost) is taken back as it is, listed, and looked at again in its turn.
    adopted = 0
    for u in order:
        if u in cache:
            cache[u]["s"] = now
        elif os.path.exists(path_for(folder, name_for(u))):
            cache[u] = {"r": "cleaned", "h": name_for(u), "t": 0, "k": CLEAN_WAY, "s": now}
            adopted += 1
    if adopted:
        print("%d clean copies taken back from logos/ (no cache entry)" % adopted)
    todo = [u for u in order if due(cache.get(u), now)]
    print("%d logo addresses (%d from Radio Browser), %d to look at" % (len(order), len(set(rb_urls)), len(todo)))
    last_at = {}
    refused = {}
    looked = cleaned = copied = missed = 0
    for u in todo:
        if time.time() > deadline:
            print("time is up: %d left for the next run" % (len(todo) - looked - missed))
            break
        s = site(fetch_address(u))
        if refused.get(s, 0) >= MAX_IN_A_ROW_REFUSED:
            missed += 1
            continue
        if pause:
            wait = (PAUSE_SAME_SITE if s in last_at else 0.0) - (time.time() - last_at.get(s, 0.0))
            time.sleep(max(PAUSE_OTHER, wait))
        if os.environ.get("SHOW_EACH"):
            print("  ", u[:110], flush=True)
        e = look(u, now, cache.get(u), folder, get)
        last_at[s] = time.time()
        if e is None:
            refused[s] = refused.get(s, 0) + 1
            missed += 1
            continue
        refused[s] = 0
        e["s"] = now
        cache[u] = e
        looked += 1
        cleaned += 1 if e.get("h") and e["r"] == "cleaned" else 0
        copied += 1 if e.get("h") and e["r"] != "cleaned" else 0
        if looked % 500 == 0:
            print("looked at %d" % looked)
    gone = let_go(cache, folder, now, known)
    # (review) Every copy still in use is listed, not only those of this run's lists: Radio Browser not reached keeps its logos' clean copies.
    names = set(e["h"] for e in cache.values() if e.get("h") and os.path.exists(path_for(folder, e["h"])))
    write_table(table_path, head, rows, ["%s.%s" % (n, version_of(path_for(folder, n))) for n in names])
    with gzip.open(cache_out, "wt", encoding="utf-8") as fh:
        json.dump(cache, fh, separators=(",", ":"))
    kinds = {}
    for u in seen:
        r = cache.get(u, {}).get("r")
        if r:
            kinds[r] = kinds.get(r, 0) + 1
    print("looked at %d this run (%d cleaned, %d kept as they are), %d not reached; %d copies in use, %d let go; all so far: %s" % (looked, cleaned, copied, missed, len(names), gone, kinds))
    return names


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    # (2026-11-19) CLEAN_UNTIL (the workflow's: its start + what the run may use) gives the cleaning all the time the table left; else CLEAN_MINUTES.
    until = os.environ.get("CLEAN_UNTIL", "")
    deadline = float(until) if until else time.time() + float(os.environ.get("CLEAN_MINUTES", "120")) * 60
    run(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], deadline)
