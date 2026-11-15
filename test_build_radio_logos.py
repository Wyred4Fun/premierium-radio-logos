"""Tests of build_radio_logos.py's reading and matching, with small made-up answers (no network). Run: python3 -m unittest test_build_radio_logos"""
import gzip
import json
import os
import tempfile
import unittest

import build_radio_logos as b

WWJ = {"call": "WWJ", "band": "AM", "freq": "950", "city": "Detroit", "state": "MI"}
WIP = {"call": "WIP", "band": "FM", "freq": "94.1", "city": "Philadelphia", "state": "PA"}


class Wikipedia(unittest.TestCase):
    # (2026-11-10) The article's answer as asked now (formatversion 2): opening text, Wikidata item, the opening section's wikitext (its infobox).
    ANSWER = {"query": {
        "normalized": [{"from": "wip-FM", "to": "WIP-FM"}],
        "redirects": [{"from": "WWJ (AM)", "to": "WWJ (AM radio)"}, {"from": "WIP-FM", "to": "WIP-FM (radio)"}],
        "pages": [
            {"title": "WWJ (AM radio)", "extract": "WWJ (950 AM) is a commercial news radio station licensed to Detroit, Michigan.",
             "pageprops": {"wikibase_item": "Q1"},
             "revisions": [{"slots": {"main": {"content": "{{Infobox radio station\n| name = WWJ\n| image = WWJ studios.jpg\n"
                                                           "| logo = [[File:WWJ_Newsradio_950_logo.svg|250px]]<!-- the logo -->\n| logo_size = 250px\n}}"}}}]},
            {"title": "WIP-FM (radio)", "extract": "WIP-FM is a sports station in Philly on 94.1 megahertz.",
             "pageprops": {"wikibase_item": "Q2"},
             "revisions": [{"slots": {"main": {"content": "{{Infobox radio station\n| logo =\n| image = WIP studio.jpg\n}}"}}}]},
            {"title": "KMXK", "extract": "KMXK (94.9 FM) is a radio station licensed to Cold Spring, Minnesota.",
             "pageprops": {"wikibase_item": "Q3"},
             "revisions": [{"slots": {"main": {"content": "{{Infobox radio station\n| image = WWJO_KLZZ_KMXK_KZRV_KXSS_WJON_studios.jpg\n}}"}}}]},
            {"title": "WWJ", "missing": True},
        ]}}
    WIKIDATA = {
        "Q2": {"claims": {"P154": [
            {"rank": "normal", "mainsnak": {"datavalue": {"value": "WIP old logo.png"}}, "qualifiers": {"P582": [{}]}},
            {"rank": "normal", "mainsnak": {"datavalue": {"value": "WIP-FM 94.1 logo.svg"}}},
            {"rank": "deprecated", "mainsnak": {"datavalue": {"value": "WIP wrong.svg"}}}]}},
        "Q3": {"claims": {}},
    }
    FILES = {"File:WWJ Newsradio 950 logo.svg": "https://upload.wikimedia.org/wikipedia/en/thumb/a/ab/WWJ_Newsradio_950_logo.svg/256px-WWJ_Newsradio_950_logo.svg.png",
             "File:WIP-FM 94.1 logo.svg": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/WIP-FM_94.1_logo.svg/256px-WIP-FM_94.1_logo.svg.png"}

    def test_pages_follow_redirects(self):
        pages, follow, redir = b.wiki_pages(self.ANSWER)
        self.assertEqual(b.resolve("WWJ (AM)", follow, redir), "WWJ (AM radio)")
        self.assertEqual(b.resolve("wip-FM", follow, redir), "WIP-FM (radio)")
        self.assertNotIn("WWJ", pages)
        self.assertEqual(pages["WWJ (AM radio)"][1], "File:WWJ Newsradio 950 logo.svg")
        self.assertEqual(pages["WIP-FM (radio)"], ("WIP-FM is a sports station in Philly on 94.1 megahertz.", "", "Q2"))

    def test_infobox_logo_only(self):
        self.assertEqual(b.infobox_logo("| logo = WWJ logo.png\n| logo_size = 200px"), "File:WWJ logo.png")
        self.assertEqual(b.infobox_logo("|logo=[[Image:wip_logo.svg|frameless]]"), "File:Wip logo.svg")
        self.assertEqual(b.infobox_logo("| image = Studios.jpg\n| logo_caption = A logo.png"), "")
        self.assertEqual(b.infobox_logo("| logo = {{Some template}}"), "")
        self.assertEqual(b.infobox_logo("| logo = <!-- none yet -->"), "")
        self.assertEqual(b.infobox_logo("| logo = Not a file"), "")
        self.assertEqual(b.infobox_logo(None), "")

    def test_wikidata_logo(self):
        self.assertEqual(b.wikidata_logo(self.WIKIDATA["Q2"]), "File:WIP-FM 94.1 logo.svg")
        pref = {"claims": {"P154": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "a.svg"}}},
                                    {"rank": "preferred", "mainsnak": {"datavalue": {"value": "b.png"}}}]}}
        self.assertEqual(b.wikidata_logo(pref), "File:B.png")
        self.assertEqual(b.wikidata_logo(self.WIKIDATA["Q3"]), "")
        self.assertEqual(b.wikidata_logo(None), "")

    def test_file_urls_commons_file_kept(self):
        a = {"query": {"normalized": [{"from": "File:WWJ_logo.svg", "to": "File:WWJ logo.svg"}], "pages": [
            {"title": "File:WWJ logo.svg", "missing": True, "known": True, "imagerepository": "shared",
             "imageinfo": [{"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/WWJ_logo.svg",
                            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/WWJ_logo.svg/256px-WWJ_logo.svg.png"}]}]}}
        got = b.file_urls(a)
        self.assertTrue(got["File:WWJ logo.svg"].endswith("256px-WWJ_logo.svg.png"))
        self.assertEqual(got["File:WWJ_logo.svg"], got["File:WWJ logo.svg"])

    def test_accept_only_with_frequency_or_city(self):
        self.assertTrue(b.wiki_ok(WWJ, "WWJ (950 AM) is a station"))
        self.assertTrue(b.wiki_ok(WWJ, "WWJ is a station in Detroit."))
        self.assertFalse(b.wiki_ok(WWJ, "WWJ-TV is a CBS television station on channel 62 in Southfield"))
        self.assertFalse(b.wiki_ok(WWJ, "a station on 1950 kHz"))
        self.assertTrue(b.wiki_ok(WIP, "on 94.1 FM"))
        self.assertFalse(b.wiki_ok(WIP, "on 94.15 FM or 194.1"))
        self.assertFalse(b.wiki_ok(WIP, ""))

    def test_titles(self):
        # "WWJ (AM)" is the AM station's article's own title, asked first.
        self.assertEqual(b.titles_for(WWJ), ["WWJ (AM)", "WWJ"])
        self.assertEqual(b.titles_for(WIP), ["WIP-FM", "WIP (FM)", "WIP"])

    def test_wip_fm_style_call_sign(self):
        # (2026-11-10) A call sign written with its band ("WIP-FM") is kept as the app looks it up (WIP, band apart): its titles are not "WIP-FM-FM".
        self.assertEqual(b.base_call("WIP-FM"), "WIP")
        self.assertEqual(b.base_call(" wwj-am "), "WWJ")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.tsv.gz")
            with gzip.open(p, "wt") as f:
                f.write("WIP-FM\tFM\t94.1\tPhiladelphia\tPA\n")
            st = b.read_fcc(p)[0]
        self.assertEqual(b.key(st), "WIP|FM|94.1")
        self.assertEqual(b.titles_for(st), ["WIP-FM", "WIP (FM)", "WIP"])
        self.assertEqual(b.radio_browser_calls([{"name": "94.1 WIP-FM Sports", "clickcount": 7}, {"name": "WWJ Newsradio 950", "clickcount": 3}, {"name": "Kiss FM", "clickcount": 9}]), {"WIP": 7, "WWJ": 3})


class TuneIn(unittest.TestCase):
    def answer(self, *items):
        return {"head": {"status": "200"}, "body": list(items)}

    def test_call_sign_in_name(self):
        a = self.answer({"text": "WWJ-FM 97.1", "image": "http://cdn-profiles.tunein.com/s1/x.png"},
                        {"text": "WWJ Newsradio 950", "image": "http://cdn-profiles.tunein.com/s32500/images/logoq.png"})
        self.assertEqual(b.tunein_pick(WWJ, a), "https://cdn-profiles.tunein.com/s32500/images/logoq.png")

    def test_frequency_needs_place(self):
        a = self.answer({"text": "Sports Radio 94.1", "subtext": "Boston, MA", "image": "http://a/b.png"})
        self.assertEqual(b.tunein_pick(WIP, a), "")
        a = self.answer({"text": "Sports Radio 94.1", "subtext": "Philadelphia, PA", "image": "http://a/c.png"})
        self.assertEqual(b.tunein_pick(WIP, a), "https://a/c.png")

    # (2026-11-15, his find: WSM 650 AM had "Riddim WSM Radio" of Ottawa; real TuneIn answers of 2026-11-15)
    WSM = {"call": "WSM", "band": "AM", "freq": "650", "city": "Nashville", "state": "TN"}

    def test_call_alone_needs_tunein_details(self):
        a = self.answer({"text": "Riddim WSM Radio", "subtext": "World Sound Music", "guide_id": "s350700", "image": "http://cdn-profiles.tunein.com/s350700/images/logoq.jpg?t=1"},
                        {"text": "95.5 WSM-FM", "subtext": "Nashville's 95.5 WSM FM", "guide_id": "s25262", "image": "http://x/fm.jpg"})
        riddim = {"name": "Riddim WSM Radio", "call_sign": "Riddim WSM Radio", "frequency": "0", "band": "Stream", "location": "Ottawa, Canada"}
        self.assertEqual(b.tunein_pick(self.WSM, a, None, lambda g: riddim), "")
        # not asked (no details reader): not taken on its letters alone
        self.assertEqual(b.tunein_pick(self.WSM, a), "")
        # the details not reached: asked again next run
        self.assertIsNone(b.tunein_pick(self.WSM, a, None, lambda g: None))
        # a real one named only by its letters: its details say so
        w = self.answer({"text": "WXPN", "subtext": "XPN Music Mix", "guide_id": "s1", "image": "http://x/xpn.png"})
        xpn = {"call_sign": "WXPN-FM", "frequency": "88.5", "band": "FM", "location": "Philadelphia, PA"}
        st = {"call": "WXPN", "band": "FM", "freq": "88.5", "city": "Philadelphia", "state": "PA"}
        self.assertEqual(b.tunein_pick(st, w, None, lambda g: xpn), "https://x/xpn.png")
        self.assertEqual(b.tunein_pick(st, w, None, lambda g: dict(xpn, call_sign="WXPZ")), "")

    def test_letters_as_written(self):
        # "Katy Perry Radio" is not KATY, "Kass FM" not KASS, "Fun Kids" not KIDS
        katy = {"call": "KATY", "band": "FM", "freq": "101.3", "city": "Idyllwild", "state": "CA"}
        a = self.answer({"text": "Katy Perry Radio", "subtext": "x", "guide_id": "s9", "image": "http://x/k.png"})
        self.assertEqual(b.tunein_pick(katy, a, None, lambda g: {"call_sign": "KATY", "frequency": "101.3"}), "")

    def test_another_place_on_the_dial(self):
        kalv = {"call": "KALV", "band": "FM", "freq": "101.5", "city": "Phoenix", "state": "AZ"}
        a = self.answer({"text": "Stereo 1430 KALV", "subtext": "Phoenix", "image": "http://x/a.png"})
        self.assertEqual(b.tunein_pick(kalv, a), "")
        kayo = {"call": "KAYO", "band": "FM", "freq": "100.9", "city": "Wasilla", "state": "AK"}
        self.assertEqual(b.tunein_pick(kayo, self.answer({"text": "South Sound Country 96.9 KAYO", "subtext": "Alaska", "image": "http://x/b.png"})), "")
        # its own number, or the whole number of its FM frequency, or an AM/FM pair naming its own: fine
        kprs = {"call": "KPRS", "band": "FM", "freq": "103.3", "city": "Kansas City", "state": "MO"}
        self.assertEqual(b.tunein_pick(kprs, self.answer({"text": "Hot 103 Jamz KPRS", "subtext": "Kansas City", "image": "http://x/c.png"})), "https://x/c.png")
        khts = {"call": "KHTS", "band": "FM", "freq": "93.3", "city": "Canyon Country", "state": "CA"}
        self.assertFalse(b.other_dial(khts, "Channel 933 KHTS"))
        self.assertFalse(b.other_dial({"freq": "106.5"}, "Mix 1065"))
        self.assertTrue(b.other_dial({"freq": "106.5"}, "Mix 1055"))
        wcbl = {"call": "WCBL", "band": "AM", "freq": "1290", "city": "Benton", "state": "KY"}
        self.assertEqual(b.tunein_pick(wcbl, self.answer({"text": "WCBL AM 1290 FM 99.1", "subtext": "Kentucky", "image": "http://x/d.png"})), "https://x/d.png")

    def test_old_tunein_logo_kept_unless_turned_down(self):
        # (2026-11-15) Asked again for the stricter match: a picture TuneIn no longer lists is kept; one it lists and the match turns down goes.
        old = "https://cdn-profiles.tunein.com/s350700/images/logoq.jpg?t=1"
        riddim = {"body": [{"text": "Riddim WSM Radio", "guide_id": "s350700", "image": old.replace("https", "http")}]}
        self.assertEqual(b.answer_for(self.WSM, "", lambda q: riddim, lambda g: {"call_sign": "Riddim WSM Radio"}, old=old), "")
        other = {"body": [{"text": "Something else", "image": "http://x/y.png"}]}
        self.assertEqual(b.answer_for(self.WSM, "", lambda q: other, lambda g: {}, old=old), old)
        # a Wikipedia logo found now replaces it either way; a Wikipedia logo kept before is not TuneIn's: not kept this way
        self.assertEqual(b.answer_for(self.WSM, "https://w/a.png", lambda q: other, lambda g: {}, old=old), "https://w/a.png")
        self.assertEqual(b.answer_for(self.WSM, "", lambda q: other, lambda g: {}, old="https://upload.wikimedia.org/a.png"), "")

    def test_details_first_word(self):
        st = {"call": "WNIA", "band": "FM", "freq": "89.1", "city": "Tarboro", "state": "NC"}
        self.assertTrue(b.describe_ok(st, {"call_sign": "WNIA Gospel Radio", "frequency": "0", "location": "Winston Salem, NC"}))
        self.assertFalse(b.describe_ok(st, {"call_sign": "WNIA Gospel Radio", "frequency": "0", "location": " US"}))
        self.assertFalse(b.describe_ok(self.WSM, {"call_sign": "Riddim WSM Radio", "location": "Nashville, TN"}))

    def test_dial_numbers(self):
        self.assertEqual(b.dial_numbers("Hot 97 and 1520 AM, est. 1960, 93.9"), ["97", "1520", "93.9"])
        self.assertEqual(b.dial_numbers("Top 40, since 1922"), [])

    def test_no_image_or_junk(self):
        self.assertEqual(b.tunein_pick(WWJ, self.answer({"text": "WWJ", "image": ""})), "")
        self.assertEqual(b.tunein_pick(WWJ, {"body": "oops"}), "")
        self.assertEqual(b.tunein_pick(WWJ, []), "")

    def test_extra_by_whole_name(self):
        st = {"call": "AT40", "band": "", "freq": ""}
        a = self.answer({"text": "Top 40 Hits", "image": "http://x/1.png"}, {"text": "Classic American Top 40", "image": "http://x/2.png"})
        self.assertEqual(b.tunein_pick(st, a, ["Classic American Top 40"]), "https://x/2.png")
        # (2026-11-13) TuneIn's own answer for "The Blaze Radio Network": none of it is the station - a word in common is not enough
        blaze = {"call": "BLAZE", "band": "", "freq": ""}
        a = self.answer({"text": "Evah Blaze Radio", "image": "http://x/e.png"}, {"text": "104-1 The Blaze", "image": "http://x/b.png"},
                        {"text": "WDQS BLAZE RADIO", "image": "http://x/w.png"})
        self.assertEqual(b.tunein_pick(blaze, a, ["The Blaze Radio Network", "Blaze Radio Network"]), "")
        a = self.answer({"text": "Evah Blaze Radio", "image": "http://x/e.png"}, {"text": "Blaze Radio Network", "image": "http://x/r.png"})
        self.assertEqual(b.tunein_pick(blaze, a, ["The Blaze Radio Network"]), "https://x/r.png")

    def test_extra_wikipedia_only_its_own_titles(self):
        self.assertEqual(b.wiki_titles({"call": "BLAZE", "band": "", "freq": "", "titles": [], "extra": True}), [])
        self.assertEqual(b.wiki_titles({"call": "X", "band": "", "freq": "", "titles": ["X radio"], "extra": True}), ["X radio"])
        self.assertEqual(b.wiki_titles(WWJ), b.titles_for(WWJ))

    def test_extra_asked_again_when_its_search_changes(self):
        now = 10 ** 9
        old = {"call": "BLAZE", "band": "", "freq": "", "city": "", "state": "", "query": "The Blaze Radio Network", "words": ["blaze"], "extra": True}
        new = dict(old, names=["The Blaze Radio Network"])
        new.pop("words")
        kept = {"u": "https://x/e.png", "s": b.stamp(old), "t": now}
        self.assertTrue(b.due(kept, new, now))
        self.assertFalse(b.due({"u": "https://x/r.png", "s": b.stamp(new), "t": now}, new, now))
        # an FCC station's stamp is as before (no station asked again for this change)
        self.assertEqual(b.stamp(WWJ), "%s|%s|%s|%s" % (WWJ.get("band", ""), WWJ.get("freq", ""), WWJ.get("city", "").upper(), WWJ.get("state", "")))


class Table(unittest.TestCase):
    def test_choose_prefers_png(self):
        self.assertEqual(b.choose("https://w/a.jpg", "https://t/b.png"), "https://t/b.png")
        self.assertEqual(b.choose("https://w/a.png", "https://t/b.png"), "https://w/a.png")
        self.assertEqual(b.choose("https://w/a.jpg", ""), "https://w/a.jpg")
        self.assertEqual(b.choose("", ""), "")

    def test_due(self):
        now = 1000 * b.DAY
        self.assertTrue(b.due(None, WWJ, now))
        e = {"u": "x", "s": b.stamp(WWJ), "t": now - 10 * b.DAY}
        self.assertFalse(b.due(e, WWJ, now))
        moved = dict(WWJ, freq="960")
        self.assertTrue(b.due(e, moved, now))
        self.assertTrue(b.due({"u": "", "s": b.stamp(WWJ), "t": now - 100 * b.DAY}, WWJ, now))

    def test_write_and_shorten(self):
        cache = {b.key(WWJ): {"u": "https://upload.wikimedia.org/wikipedia/en/a.png"}, b.key(WIP): {"u": ""}}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.tsv.gz")
            self.assertEqual(b.write_table([WWJ, WIP], cache, p, "2026-11-09"), 1)
            with gzip.open(p, "rt") as f:
                lines = f.read().splitlines()
        self.assertEqual(lines[0], "#radio_logos|2026-11-09|call|band|freq|logo")
        self.assertEqual(lines[1], "WWJ|AM|950|W:en/a.png")

    def test_read_fcc_and_radio_browser(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.tsv.gz")
            with gzip.open(p, "wt") as f:
                f.write("WWJ\tAM\t950\tDetroit\tMI\nbad line\nWIP\tFM\t94.1\tPhiladelphia\tPA\n")
            self.assertEqual([s["call"] for s in b.read_fcc(p)], ["WWJ", "WIP"])
        self.assertEqual(set(b.radio_browser_calls([{"name": "WWJ Newsradio 950"}, {"name": "94.1 WIP"}, {"name": "Kiss FM"}, {"name": None}])), {"WWJ", "WIP"})


class Batch(unittest.TestCase):
    def fake(self, wiki=None, items=None, files=None):
        saved = (b.wiki_batch, b.wikidata_items, b.wiki_files)
        b.wiki_batch = wiki or (lambda titles: Wikipedia.ANSWER)
        b.wikidata_items = items or (lambda q: {k: v for k, v in Wikipedia.WIKIDATA.items() if k in q})
        b.wiki_files = files or (lambda f: {k: v for k, v in Wikipedia.FILES.items() if k in f})
        return saved

    def restore(self, saved):
        b.wiki_batch, b.wikidata_items, b.wiki_files = saved

    def test_logo_not_photo(self):
        # (2026-11-10, his find) The infobox logo, else Wikidata's; a page whose only picture is its studios gives none (TuneIn is asked then).
        kmxk = {"call": "KMXK", "band": "FM", "freq": "94.9", "city": "Cold Spring", "state": "MN"}
        saved = self.fake()
        try:
            got = b.ask_wikipedia([WWJ, WIP, kmxk])
        finally:
            self.restore(saved)
        self.assertTrue(got[b.key(WWJ)].endswith("256px-WWJ_Newsradio_950_logo.svg.png"))
        self.assertTrue(got[b.key(WIP)].endswith("256px-WIP-FM_94.1_logo.svg.png"))
        self.assertEqual(got[b.key(kmxk)], "")
        self.assertNotIn("studios", json.dumps(got))

    def test_page_not_the_station(self):
        saved = self.fake()
        try:
            got = b.ask_wikipedia([dict(WWJ, city="Nowhere", freq="1500")])
        finally:
            self.restore(saved)
        self.assertEqual(got[b.key(dict(WWJ, freq="1500"))], "")

    def test_files_or_wikidata_not_reached(self):
        saved = self.fake(files=lambda f: None)
        try:
            self.assertIsNone(b.ask_wikipedia([WWJ])[b.key(WWJ)])
        finally:
            self.restore(saved)
        saved = self.fake(items=lambda q: None)
        try:
            got = b.ask_wikipedia([WWJ, WIP])
        finally:
            self.restore(saved)
        self.assertTrue(got[b.key(WWJ)])
        self.assertIsNone(got[b.key(WIP)])

    def test_order_presets_then_shown(self):
        sts = [{"call": c, "band": "FM", "freq": "1"} for c in ("KAAA", "WZZZ", "WIP", "WWJ", "KBBB")]
        order = [s["call"] for s in b.ask_order(sts, {"KBBB": 5, "WZZZ": 900})]
        self.assertEqual(order, ["WWJ", "WIP", "WZZZ", "KBBB", "KAAA"])

    def test_old_page_pictures_asked_again(self):
        now = 1000 * b.DAY
        old_photo = {"u": "https://upload.wikimedia.org/wikipedia/commons/thumb/x/WWJO_KLZZ_KMXK_KZRV_KXSS_WJON_studios.jpg/256px-a.jpg", "s": b.stamp(WWJ), "t": now}
        self.assertTrue(b.due(old_photo, WWJ, now))
        self.assertTrue(b.due({"u": "", "s": b.stamp(WWJ), "t": now}, WWJ, now))
        # (2026-11-15) A TuneIn logo of a way before the stricter match (3) is asked again; one made the way it is now is kept.
        self.assertTrue(b.due({"u": "https://cdn-profiles.tunein.com/a.png", "s": b.stamp(WWJ), "t": now, "v": 2}, WWJ, now))
        self.assertFalse(b.due({"u": "https://cdn-profiles.tunein.com/a.png", "s": b.stamp(WWJ), "t": now, "v": 3}, WWJ, now))
        self.assertFalse(b.due(dict(old_photo, v=b.LOGO_WAY), WWJ, now))

    def test_page_thumbnail_pictures_asked_again(self):
        now = 1000 * b.DAY
        wnic = {"u": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7b/Clear_Channel_Building_Farmington_Hills_Michigan.JPG/330px-Clear_Channel_Building_Farmington_Hills_Michigan.JPG?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "s": b.stamp(WWJ), "t": now}
        self.assertTrue(b.due(wnic, WWJ, now))
        self.assertFalse(b.due(dict(wnic, v=b.LOGO_WAY), WWJ, now))

    def test_photo_names_rejected(self):
        u = "https://upload.wikimedia.org/wikipedia/commons/7/7b/%s"
        for bad in ("Clear_Channel_Building_Farmington_Hills_Michigan.JPG", "KANNtowers.jpg", "KCLU_Sendemast.jpg", "KDHX_station_building_external.jpg",
                    "KAZZ_radio_tower.jpg", "KBUP_Studio.jpg", "IMG_2503.JPG", "KALLdoor.jpg", "Falcon_Heights_transmitter.jpg"):
            self.assertTrue(b.looks_like_photo(u % bad), bad)
        for good in ("WWJ_logo.svg", "KALW_Radio_Logo.jpg", "KAAN_95.5FM_logo.jpg", "WJR_760.png", "Mix_94.7.jpg", "Studio_Logo.png", "WCJK.jpg", "Tower_Logo.png"):
            self.assertFalse(b.looks_like_photo(u % good), good)
        self.assertEqual(b.choose("https://x/Clear_Channel_Building.JPG", ""), "")
        self.assertEqual(b.choose("https://x/Clear_Channel_Building.JPG", "https://t/a.png"), "https://t/a.png")
        self.assertEqual(b.choose("https://x/WNIC_logo.jpg", "https://t/a.png"), "https://t/a.png")


class Failures(unittest.TestCase):
    """(2026-11-09, review) A site not reached never erases a logo, and a much smaller table is never published."""

    def test_wikipedia_not_reached(self):
        real = b.wiki_batch
        b.wiki_batch = lambda titles: None
        try:
            got = b.ask_wikipedia([WWJ])
        finally:
            b.wiki_batch = real
        self.assertIsNone(got[b.key(WWJ)])

    def test_answer_for(self):
        # (2026-11-11) Wikipedia not reached: TuneIn alone gives the logo; none found there, or TuneIn not reached too: asked again next run (None).
        t = {"body": [{"text": "WWJ Newsradio 950", "image": "http://t/b.png"}]}
        self.assertEqual(b.answer_for(WWJ, None, lambda q: t), "https://t/b.png")
        self.assertIsNone(b.answer_for(WWJ, None, lambda q: {}))
        self.assertIsNone(b.answer_for(WWJ, None, lambda q: None))
        self.assertIsNone(b.answer_for(WWJ, "https://w/a.jpg", lambda q: None))
        self.assertEqual(b.answer_for(WWJ, "https://w/a.png", lambda q: None), "https://w/a.png")
        a = {"body": [{"text": "WWJ Newsradio 950", "image": "http://t/b.png"}]}
        self.assertEqual(b.answer_for(WWJ, "https://w/a.jpg", lambda q: a), "https://t/b.png")
        self.assertEqual(b.answer_for(WWJ, "", lambda q: {}), "")

    def test_table_count_leaves_out_clean_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.gz")
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                fh.write("#radio_logos|x|call|band|freq|logo\nWWJ|AM|950|https://a\nWJR|AM|760|https://b\n=0123456789abcdef\n")
            self.assertEqual(b.table_count(p), 2)

    def test_too_small(self):
        self.assertFalse(b.too_small(10, None))
        self.assertFalse(b.too_small(80, 100))
        self.assertTrue(b.too_small(79, 100))
        self.assertFalse(b.too_small(5, 0))

    def run_main(self, d, cache, last=None, allow=None):
        fcc = os.path.join(d, "fcc.tsv.gz")
        with gzip.open(fcc, "wt") as f:
            f.write("WWJ\tAM\t950\tDetroit\tMI\n")
            for i in range(5000):
                f.write("W%s\tFM\t%d.1\tTown\tMI\n" % (chr(65 + i % 26) + chr(65 + i // 26 % 26) + chr(65 + i // 676 % 26), 88 + i % 20))
        cpath = os.path.join(d, "cache.json.gz")
        if cache is not None:
            with gzip.open(cpath, "wt") as f:
                f.write(cache)
        saved = (b.wiki_batch, b.wikidata_items, b.wiki_files, b.tunein_search, b.urllib.request.urlopen, b.PAUSE)
        def down(*a, **k):
            raise OSError("down")
        b.wiki_batch = lambda titles: None
        b.wikidata_items = lambda q: None
        b.wiki_files = lambda f: None
        b.tunein_search = lambda q: None
        b.urllib.request.urlopen = down
        b.PAUSE = 0
        old = os.environ.get("ALLOW_SMALLER")
        if allow:
            os.environ["ALLOW_SMALLER"] = allow
        try:
            b.main(fcc, cpath, os.path.join(d, "out"), last)
        finally:
            b.wiki_batch, b.wikidata_items, b.wiki_files, b.tunein_search, b.urllib.request.urlopen, b.PAUSE = saved
            if allow:
                if old is None:
                    del os.environ["ALLOW_SMALLER"]
                else:
                    os.environ["ALLOW_SMALLER"] = old
        with gzip.open(os.path.join(d, "out", "radio_logos_cache.json.gz"), "rt") as f:
            return json.load(f)

    def test_outage_keeps_old_logo(self):
        old = {b.key(WWJ): {"u": "https://w/wwj.png", "s": b.stamp(WWJ), "t": 0}}
        with tempfile.TemporaryDirectory() as d:
            got = self.run_main(d, json.dumps(old))
        self.assertEqual(got[b.key(WWJ)]["u"], "https://w/wwj.png")
        self.assertEqual(got[b.key(WWJ)]["t"], 0)

    def test_unreadable_cache_stops(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                self.run_main(d, "not json")

    def test_much_smaller_table_refused(self):
        old = {b.key(WWJ): {"u": "https://w/wwj.png", "s": b.stamp(WWJ), "t": 0}}
        with tempfile.TemporaryDirectory() as d:
            last = os.path.join(d, "last.tsv.gz")
            with gzip.open(last, "wt") as f:
                f.write("#radio_logos|2026-10-12|call|band|freq|logo\nWWJ|AM|950|W:a.png\nWJR|AM|760|W:b.png\n")
            self.assertEqual(b.table_count(last), 2)
            with self.assertRaises(SystemExit):
                self.run_main(d, json.dumps(old), last)
            self.run_main(d, json.dumps(old), last, allow="1")
        self.assertIsNone(b.table_count(None))


if __name__ == "__main__":
    unittest.main()
