"""Tests of clean_logos.py (made-up pictures, and his 7 real logos in test_logos/ when they are there) and clean_job.py (no network).
Run: python3 -m unittest test_clean_logos"""
import gzip
import io
import os
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import clean_job as job
import clean_logos as c

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.join(HERE, "test_logos")
NAVY = (31, 65, 92)   # the Radio page's card (RadioPage.CARD)


def png(im, fmt="PNG", **kw):
    b = io.BytesIO()
    im.save(b, fmt, **kw)
    return b.getvalue()


def disc_on(ground, color=(200, 20, 30), size=120, mode="RGB"):
    """A colored disc on a plain ground, drawn 4x and made smaller: a real soft (blended) edge."""
    big = Image.new(mode, (size * 4, size * 4), ground)
    ImageDraw.Draw(big).ellipse([size * 0.6, size * 0.6, size * 3.4, size * 3.4], fill=color)
    return big.resize((size, size), Image.LANCZOS)


def arr(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGBA")).astype(int)


def light_fringe(a, ground=(255, 255, 255)):
    """Shown points next to a clear one whose color is still near the old ground (a white fringe on a dark screen)."""
    clear = a[:, :, 3] < 10
    touch = ndimage.binary_dilation(clear, np.ones((3, 3), bool)) & ~clear
    near = np.abs(a[:, :, :3] - np.array(ground)).max(axis=2) <= 40
    return int((touch & (a[:, :, 3] >= 64) & near).sum())


class Made(unittest.TestCase):
    def test_white_ground_goes_without_fringe(self):
        r = c.clean(png(disc_on((255, 255, 255))))
        self.assertEqual(r.verdict, "cleaned")
        a = arr(r.png)
        self.assertEqual(a[0, 0, 3], 0)
        self.assertEqual(light_fringe(a), 0)
        # the soft edge un-blended: every shown point is the disc's red, not pink
        shown = a[:, :, 3] > 0
        self.assertLessEqual(a[:, :, 1][shown].max(), 40)
        # trimmed to the disc
        self.assertLess(a.shape[0], 100)

    def test_off_white_and_jpeg_noise(self):
        r = c.clean(png(disc_on((246, 248, 243)), "JPEG", quality=70))
        self.assertEqual(r.verdict, "cleaned")
        a = arr(r.png)
        self.assertEqual(light_fringe(a, (246, 248, 243)), 0)
        self.assertTrue(r.png.startswith(b"\x89PNG"))

    def test_interior_white_stays(self):
        # a red badge with a small white middle: the middle is the artwork's own (not joined to the edge, the badge far bigger than it)
        im = Image.new("RGB", (120, 120), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([10, 10, 110, 110], fill=(200, 20, 30))
        d.ellipse([47, 47, 73, 73], fill="white")
        a = arr(c.clean(png(im)).png)
        h, w = a.shape[:2]
        self.assertEqual(a[h // 2, w // 2, 3], 255)
        self.assertEqual(tuple(a[h // 2, w // 2, :3]), (255, 255, 255))

    def test_white_inside_dark_letters_goes(self):
        # (KFEQ) a dark red "O" and a dark "Q"-like ring on white: their middles are the ground seen through the letters
        im = Image.new("RGB", (240, 120), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([10, 10, 110, 110], outline=(130, 30, 35), width=12)
        d.ellipse([130, 10, 230, 110], outline=(30, 30, 30), width=10)
        a = arr(c.clean(png(im)).png)
        h, w = a.shape[:2]
        self.assertEqual(a[h // 2, w // 4, 3], 0)
        self.assertEqual(a[h // 2, 3 * w // 4, 3], 0)
        # a light-blue "O" (WOVU's letters) keeps its white middle
        im = Image.new("RGB", (120, 120), "white")
        ImageDraw.Draw(im).ellipse([10, 10, 110, 110], outline=(90, 190, 235), width=12)
        a = arr(c.clean(png(im)).png)
        self.assertEqual(a[a.shape[0] // 2, a.shape[1] // 2, 3], 255)

    def test_white_inside_a_framed_badge_stays(self):
        # (review) a thin black ring round a white roundel with a red square in it, beside a dark word; and a thin frame round a white box with words in it
        im = Image.new("RGB", (400, 120), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([10, 10, 110, 110], outline="black", width=4)
        d.rectangle([45, 45, 75, 75], fill=(200, 20, 30))
        d.rectangle([140, 40, 380, 80], fill=(20, 20, 20))
        a = arr(c.clean(png(im)).png)
        self.assertEqual(a[30, 30, 3], 255)
        im = Image.new("RGB", (400, 150), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([10, 10, 200, 140], outline=(10, 20, 60), width=3)
        d.rectangle([40, 60, 170, 90], fill=(10, 20, 60))
        d.rectangle([230, 50, 390, 100], fill=(10, 20, 60))
        a = arr(c.clean(png(im)).png)
        self.assertEqual(a[30, 30, 3], 255)
        # a thin ring with nothing in it: its white stays too (the ring is far smaller than its middle)
        im = Image.new("RGB", (400, 120), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([10, 10, 110, 110], outline="black", width=3)
        d.rectangle([140, 40, 380, 80], fill=(20, 20, 20))
        a = arr(c.clean(png(im)).png)
        self.assertEqual(a[a.shape[0] // 2, 50, 3], 255)

    def test_white_letters_in_a_dark_banner_stay(self):
        # (WJR) white letters cut into one dark red banner: many patches in one piece - all kept
        im = Image.new("RGB", (300, 120), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([10, 20, 290, 100], fill=(150, 25, 35))
        for x in range(25, 280, 50):
            d.rectangle([x, 40, x + 25, 80], fill="white")
        a = arr(c.clean(png(im)).png)
        whites = (a[:, :, 3] == 255) & (a[:, :, :3].min(axis=2) >= 240)
        self.assertGreaterEqual(int(whites.sum()), 5 * 26 * 41)

    def test_tiny_holes_of_thin_lettering_go_white_dot_on_badge_stays(self):
        im = Image.new("RGB", (300, 120), "white")
        d = ImageDraw.Draw(im)
        # thin dark "o"s: a 2-point ring round a 3x3 white hole
        for x in range(20, 120, 20):
            d.rectangle([x, 20, x + 6, 26], outline=(30, 30, 30), width=2)
        # a blue badge with a small white dot in it
        d.rectangle([150, 10, 290, 110], fill=(20, 60, 200))
        d.rectangle([215, 55, 218, 58], fill="white")
        r = c.clean(png(im))
        a = np.array(Image.open(io.BytesIO(r.png)).convert("RGBA")).astype(int)
        # the cleaned picture is trimmed: find the badge's dot by its color instead
        whites = (a[:, :, 3] == 255) & (a[:, :, :3].min(axis=2) >= 250)
        self.assertEqual(int(whites.sum()), 16)   # only the badge's 4x4 dot is still white

    def test_see_through_kept(self):
        im = disc_on((0, 0, 0, 0), mode="RGBA")
        self.assertEqual(c.clean(png(im)).verdict, "transparent")
        # a see-through margin round a white plate: the plate goes (as the app does)
        im = Image.new("RGBA", (140, 100), (0, 0, 0, 0))
        im.paste(disc_on((255, 255, 255), size=80).convert("RGBA"), (30, 10))
        self.assertEqual(c.clean(png(im)).verdict, "cleaned")

    def test_colored_ground_kept(self):
        self.assertEqual(c.clean(png(disc_on((10, 10, 10), (240, 240, 240)))).verdict, "colored")
        self.assertEqual(c.clean(png(disc_on((0, 90, 200), (255, 255, 255)))).verdict, "colored")

    def test_shaded_light_ground_kept(self):
        # (KRMO) light blue sweeping to white: not a plain ground - left as it is, never half taken off
        g = np.zeros((100, 200, 3), np.uint8)
        for x in range(200):
            g[:, x] = (int(190 + 65 * x / 199), int(225 + 30 * x / 199), 255)
        im = Image.fromarray(g)
        ImageDraw.Draw(im).ellipse([70, 20, 130, 80], fill=(0, 120, 0))
        r = c.clean(png(im))
        self.assertEqual(r.verdict, "colored")

    def test_small_blank_bad(self):
        self.assertEqual(c.clean(png(Image.new("RGB", (10, 10), "white"))).verdict, "small")
        self.assertEqual(c.clean(png(Image.new("RGB", (100, 100), "white"))).verdict, "blank")
        self.assertEqual(c.clean(b"<!DOCTYPE html><html>Wikimedia Error</html>").verdict, "bad")
        self.assertEqual(c.clean(b"").verdict, "bad")
        self.assertEqual(c.clean(b"x" * (c.MAX_BYTES + 1)).verdict, "bad")

    def test_other_picture_kinds(self):
        base = disc_on((255, 255, 255))
        grey16 = Image.fromarray(np.array(base.convert("L")).astype(np.uint16) * 257, "I;16")
        for name, im, fmt in (("CMYK jpeg", base.convert("CMYK"), "JPEG"), ("16-bit grey", grey16, "PNG"), ("palette", base.convert("P", palette=Image.ADAPTIVE), "PNG"),
                              ("grey + alpha", base.convert("LA"), "PNG"), ("icon", base, "ICO")):
            self.assertEqual(c.clean(png(im, fmt)).verdict, "cleaned", name)

    def test_large_made_smaller(self):
        r = c.clean(png(disc_on((255, 255, 255), size=1600)))
        self.assertEqual(r.verdict, "cleaned")
        self.assertLessEqual(max(r.size), c.MAX_SIDE)

    def test_gif_and_webp(self):
        self.assertEqual(c.clean(png(disc_on((255, 255, 255)), "GIF")).verdict, "cleaned")
        self.assertEqual(c.clean(png(disc_on((255, 255, 255)), "WEBP")).verdict, "cleaned")


@unittest.skipUnless(os.path.isdir(REAL), "his 7 logos are not here")
class HisSeven(unittest.TestCase):
    """(2026-11-15, his test set) WWJ and WWDK untouched; WJR, WOVU, WSM's jpg, WUMB, WVOW see-through with no white fringe."""

    def load(self, name):
        with open(os.path.join(REAL, name), "rb") as fh:
            return fh.read()

    def test_untouched(self):
        for n in ("WWJ.png", "WWDK.png"):
            self.assertEqual(c.clean(self.load(n)).verdict, "transparent", n)

    def test_cleaned_without_fringe(self):
        for n in ("WJR_760.png", "WOVU.png", "WSM_650.jpg", "WUMB.png", "WVOW.png"):
            r = c.clean(self.load(n))
            self.assertEqual(r.verdict, "cleaned", n)
            a = arr(r.png)
            self.assertEqual(light_fringe(a), 0, n)
            self.assertEqual(a[0, 0, 3] if a[0, 0, 3] == 0 else 0, 0)

    def test_wjr_white_letters_stay(self):
        a = arr(c.clean(self.load("WJR_760.png")).png)
        # WJR's white letters on red: thousands of white points stay
        whites = (a[:, :, 3] == 255) & (a[:, :, :3].min(axis=2) >= 240)
        self.assertGreater(int(whites.sum()), 10000)


class Job(unittest.TestCase):
    def test_name_and_path(self):
        self.assertEqual(job.name_for("https://x/a.png"), "50173ad31f77371c")
        self.assertEqual(job.path_for("logos", "50173ad31f77371c"), os.path.join("logos", "50", "50173ad31f77371c.png"))

    def test_fetch_address(self):
        self.assertEqual(job.fetch_address("https://upload.wikimedia.org/wikipedia/commons/0/01/WJR_logo_2024.png?utm_source=x"),
                         "https://thumb.wikimedia.org/wikipedia/commons/thumb/0/01/WJR_logo_2024.png/330px-WJR_logo_2024.png")
        self.assertEqual(job.fetch_address("https://upload.wikimedia.org/wikipedia/en/a/ab/X_logo.svg"),
                         "https://thumb.wikimedia.org/wikipedia/en/thumb/a/ab/X_logo.svg/330px-X_logo.svg.png")
        self.assertEqual(job.fetch_address("https://thumb.wikimedia.org/wikipedia/en/thumb/8/8d/WVOW.PNG/330px-WVOW.PNG?utm=1"),
                         "https://thumb.wikimedia.org/wikipedia/en/thumb/8/8d/WVOW.PNG/330px-WVOW.PNG")
        self.assertEqual(job.fetch_address("https://upload.wikimedia.org/wikipedia/commons/thumb/7/75/W.png/256px-W.png"),
                         "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/75/W.png/330px-W.png")
        self.assertEqual(job.fetch_address("https://cdn-profiles.tunein.com/s1/images/logoq.jpg?t=1"), "https://cdn-profiles.tunein.com/s1/images/logoq.jpg?t=1")

    def test_due(self):
        now = 10 ** 9
        # (2026-11-19) looked at before every logo got a copy: fetched again for its copy; one with its copy, or "bad", not
        self.assertTrue(job.due({"r": "transparent", "t": now, "k": job.CLEAN_WAY, "h": ""}, now))
        self.assertTrue(job.due({"r": "colored", "t": now, "k": job.CLEAN_WAY}, now))
        self.assertFalse(job.due({"r": "colored", "t": now, "k": job.CLEAN_WAY, "h": "0123456789abcdef"}, now))
        self.assertFalse(job.due({"r": "bad", "t": now, "k": job.CLEAN_WAY, "h": ""}, now))
        self.assertTrue(job.due(None, now))
        self.assertFalse(job.due({"r": "cleaned", "t": now, "k": job.CLEAN_WAY}, now))
        self.assertTrue(job.due({"r": "cleaned", "t": now, "k": job.CLEAN_WAY - 1}, now))
        self.assertTrue(job.due({"r": "bad", "t": now - 31 * job.DAY, "k": job.CLEAN_WAY}, now))
        self.assertFalse(job.due({"r": "bad", "t": now - 5 * job.DAY, "k": job.CLEAN_WAY}, now))
        self.assertTrue(job.due({"r": "transparent", "t": now - 181 * job.DAY, "k": job.CLEAN_WAY, "h": "0123456789abcdef"}, now))

    def make_table(self, d, rows):
        p = os.path.join(d, "t.tsv.gz")
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            fh.write("\n".join(["#radio_logos|2026-11-15|call|band|freq|logo"] + rows + ["=oldoldoldoldold1"]) + "\n")
        return p

    def test_run_cleans_writes_lines_and_keeps_on_outage(self):
        white = png(disc_on((255, 255, 255)))
        clear = png(disc_on((0, 0, 0, 0), mode="RGBA"))
        pics = {"https://x/white.png": white, "https://x/clear.png": clear, "https://rb/fav.png": white}
        with tempfile.TemporaryDirectory() as d:
            t = self.make_table(d, ["WJR|AM|760|https://x/white.png", "WWJ|AM|950|https://x/clear.png", "WOVU|FM|95.9|https://x/gone.png"])
            folder = os.path.join(d, "logos")
            out = os.path.join(d, "c.json.gz")

            def get(u):
                if u not in pics:
                    return None
                return pics[u]
            names = job.run(t, None, out, folder, 1e18, rb=["https://rb/fav.png"], get=get, pause=False)
            # (2026-11-19) every picture gets a copy: the cleaned ones and the see-through one as it is; the one not there (404) none
            self.assertEqual(names, {job.name_for("https://x/white.png"), job.name_for("https://rb/fav.png"), job.name_for("https://x/clear.png")})
            kept = arr(open(job.path_for(folder, job.name_for("https://x/clear.png")), "rb").read())
            self.assertEqual(kept[0, 0, 3], 0)   # kept see-through, not trimmed or changed
            for n in names:
                self.assertTrue(os.path.exists(job.path_for(folder, n)))
            with gzip.open(t, "rt") as fh:
                lines = fh.read().split("\n")
            self.assertIn("WJR|AM|760|https://x/white.png", lines)
            self.assertNotIn("=oldoldoldoldold1", lines)
            self.assertEqual(sorted(l.split(".")[0] for l in lines if l.startswith("=")), sorted("=" + n for n in names))
            self.assertTrue(all(len(l) == 26 for l in lines if l.startswith("=")))
            # next run: every site refuses - nothing is lost, nothing looked at again before its time
            def down(u):
                raise job.Refused("503")
            with gzip.open(out, "rt") as fh:
                import json
                cache = json.load(fh)
            for e in cache.values():
                e["k"] = 0   # pretend the cleaning changed: all due again
            with gzip.open(out, "wt") as fh:
                json.dump(cache, fh)
            names2 = job.run(t, out, out, folder, 1e18, rb=["https://rb/fav.png"], get=down, pause=False)
            self.assertEqual(names2, names)
            # the old table's own logo addresses are still read after "=" lines are in it
            self.assertEqual(len(job.read_table(t)[2]), 3)

    def test_radio_browser_down_keeps_its_copies_listed(self):
        white = png(disc_on((255, 255, 255)))
        with tempfile.TemporaryDirectory() as d:
            t = self.make_table(d, ["WJR|AM|760|https://x/white.png"])
            folder, out = os.path.join(d, "logos"), os.path.join(d, "c.json.gz")
            first = job.run(t, None, out, folder, 1e18, rb=["https://rb/fav.png"], get=lambda u: white, pause=False)
            self.assertEqual(len(first), 2)
            t2 = self.make_table(d, ["WJR|AM|760|https://x/white.png"])
            again = job.run(t2, out, out, folder, 1e18, rb=[], get=lambda u: white, pause=False)
            self.assertEqual(again, first)
            with gzip.open(t2, "rt") as fh:
                self.assertEqual(sum(1 for l in fh if l.startswith("=")), 2)

    def test_lost_cache_never_empties_logos(self):
        white = png(disc_on((255, 255, 255)))
        with tempfile.TemporaryDirectory() as d:
            t = self.make_table(d, ["WJR|AM|760|https://x/white.png", "WVOW|AM|1290|https://x/w2.png"])
            folder, out = os.path.join(d, "logos"), os.path.join(d, "c.json.gz")
            names = job.run(t, None, out, folder, 1e18, rb=[], get=lambda u: white, pause=False)
            self.assertEqual(len(names), 2)
            # the cache lost, and no time to look at anything: both copies taken back, listed, nothing removed
            t2 = self.make_table(d, ["WJR|AM|760|https://x/white.png", "WVOW|AM|1290|https://x/w2.png"])
            back = job.run(t2, os.path.join(d, "missing.gz"), out, folder, 0, rb=[], get=lambda u: white, pause=False)
            self.assertEqual(back, names)
            for n in names:
                self.assertTrue(os.path.exists(job.path_for(folder, n)))

    def test_a_picture_that_breaks_the_tools_is_bad(self):
        real = c.clean
        try:
            c.clean = lambda data: 1 / 0
            e = job.look("https://x/a.png", 5, None, tempfile.mkdtemp(), lambda u: b"x")
        finally:
            c.clean = real
        self.assertEqual(e["r"], "bad")

    def test_unused_copies_let_go_after_grace(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "logos")
            n = job.name_for("https://x/a.png")
            os.makedirs(os.path.join(folder, n[:2]))
            open(job.path_for(folder, n), "wb").write(b"x")
            now = 10 ** 9
            cache = {"https://x/a.png": {"r": "cleaned", "h": n, "t": now, "k": 1, "s": now - 10 * job.DAY}}
            self.assertEqual(job.let_go(cache, folder, now, {n}), 0)
            cache["https://x/a.png"]["s"] = now - 91 * job.DAY
            # a copy the last cache did not name (a lost cache) is never removed
            self.assertEqual(job.let_go(dict(cache), folder, now, set()), 0)
            self.assertEqual(job.let_go(cache, folder, now, {n}), 1)
            self.assertFalse(os.path.exists(job.path_for(folder, n)))
            self.assertEqual(cache, {})

    def test_deadline_leaves_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make_table(d, ["WJR|AM|760|https://x/white.png"])
            names = job.run(t, None, os.path.join(d, "c.json.gz"), os.path.join(d, "logos"), 0, rb=[], get=lambda u: 1 / 0, pause=False)
            self.assertEqual(names, set())


if __name__ == "__main__":
    unittest.main()
