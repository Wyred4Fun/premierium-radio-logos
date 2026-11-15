#!/usr/bin/env python3
"""
(2026-11-15, his ask: "every radio station logo ... a clean transparent PNG, with no white box around it") Cleans one logo picture, once, on GitHub - the same
idea as the box's RadioLogoArt (which only fixes the screen), done properly on the file:
  - already see-through at its edge (WWJ, WWDK)             -> "transparent": kept as it is (no new file);
  - a real ground of its own, not a plain light one (a colored slab, a black square) -> "colored": kept as it is;
  - a plain white or near-white ground (WJR, WUMB, WVOW, WOVU, WSM's jpg) -> "cleaned": the ground joined to the picture's edge goes see-through (a white
    part inside the artwork, not joined to the edge, stays), the artwork's soft edge is un-blended from the ground (its color worked back out and its
    see-through amount set, so no white fringe shows on a dark screen), the empty margin is trimmed, and it is saved as a PNG;
  - too small to judge, or a cleaning that would leave next to nothing -> kept as it is ("small", "blank");
  - not a picture at all (an error page) -> "bad".
A picture larger than MAX_SIDE is made smaller first (the box draws a logo at most about 200 px).
Needs Pillow, numpy and scipy. Tests: python3 -m unittest test_clean_logos (in this folder).
"""
import io

import numpy as np
from PIL import Image
from scipy import ndimage

MAX_SIDE = 400
MAX_POINTS = 25_000_000
MIN_SIDE = 16
# The most bytes a picture may have to be looked at (a 40 MB "logo" is not one).
MAX_BYTES = 8 * 1024 * 1024
# A see-through edge: this share of the edge's points (after a clear margin is trimmed) shows less than ALPHA_CLEAR.
ALPHA_CLEAR = 40
CLEAR_EDGE = 0.25
# A plain ground: this share of the edge's solid points is within GROUND_NEAR of its commonest color.
GROUND_SHARE = 0.6
GROUND_NEAR = 48
# A light ground (the only one that goes): bright and greyish.
LIGHT_MIN = 215
GREY_SPREAD = 30
# Within HARD of the ground (largest difference of red, green or blue): ground. Up to SOFT: the artwork's soft edge, un-blended.
HARD = 26
SOFT = 240
# The soft edge is looked at this many points deep from the ground that went.
BAND = 2
# A plain ground: what goes (within HARD) is at least this share of what a looser match (GROUND_NEAR) joined to the edge would take; less is a shaded ground.
PLAIN_SHARE = 0.85
# A tiny light patch inside thin lettering (see letter_holes): at most this share of the picture and this many points, with the ground that went on at least
# HOLE_AROUND of the ring HOLE_NEAR points round it.
HOLE_SHARE = 0.001
HOLE_MAX = 64
HOLE_NEAR = 4
HOLE_AROUND = 0.25
# The most a 256-color PNG may differ from the full-color picture, on average per color part of a shown point (out of 255).
PALETTE_ERROR = 6.0
# The ground seen through dark lettering (see counters): a patch of at least COUNTER_MIN points and at most COUNTER_SHARE of the picture, its lettering
# holding at most COUNTER_HOLES patches, at most COUNTER_AREA and at least COUNTER_MIN_AREA times the patch (a thin frame round a white box is not a letter's
# stroke), darker than COUNTER_DARK (brightness 0-255), and no artwork inside the patch.
COUNTER_MIN = 20
COUNTER_SHARE = 0.25
COUNTER_HOLES = 2
COUNTER_AREA = 3
COUNTER_MIN_AREA = 0.5
COUNTER_INNER = 4
COUNTER_DARK = 110
# Left with less than this share of the picture showing: "blank" (kept as it was).
MIN_LEFT = 0.005


class Result:
    def __init__(self, verdict, png=None, size=None, note=""):
        self.verdict = verdict      # transparent / colored / cleaned / small / blank / bad
        self.png = png              # the cleaned file's bytes ("cleaned" only)
        self.size = size            # (width, height) of what was looked at / made
        self.note = note

    def __repr__(self):
        return "Result(%s, %s, %s)" % (self.verdict, self.size, self.note)


def load(data):
    """The picture as RGBA numpy (h, w, 4) uint8, made smaller to MAX_SIDE; None when it is not a picture."""
    if not data or len(data) > MAX_BYTES:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        # (a "logo" of 10,000 x 10,000 points: not one, and slow to open) Looked at before the picture is read.
        if im.size[0] * im.size[1] > MAX_POINTS:
            return None
        im.load()
    except Exception:
        return None
    if getattr(im, "is_animated", False):
        im.seek(0)
    # A 16-bit grey picture: Pillow would clip it to white (its values run to 65535), so its top 8 bits are taken.
    if im.mode in ("I", "I;16", "I;16B", "I;16L"):
        im = Image.fromarray((np.clip(np.array(im, dtype=np.int64), 0, 65535) >> 8).astype(np.uint8), "L")
    im = im.convert("RGBA")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return np.array(im)


def shown_box(alpha, floor=ALPHA_CLEAR):
    """The box round the points that show (alpha at least [floor]): top, bottom, left, right (inclusive); None when nothing shows."""
    rows = np.where((alpha >= floor).any(axis=1))[0]
    cols = np.where((alpha >= floor).any(axis=0))[0]
    if len(rows) == 0:
        return None
    return rows[0], rows[-1], cols[0], cols[-1]


def edge_points(a):
    return np.concatenate([a[0], a[-1], a[1:-1, 0], a[1:-1, -1]])


def ground_of(px):
    """The plain ground round the picture (a float RGB array), or None: GROUND_SHARE of the edge's solid points near one color."""
    e = edge_points(px)
    solid = e[e[:, 3] >= 200][:, :3].astype(int)
    if len(solid) < len(e) * 0.6:
        return None
    q = (solid // 16) @ np.array([256, 16, 1])
    vals, counts = np.unique(q, return_counts=True)
    top = vals[np.argmax(counts)]
    g = solid[q == top].mean(axis=0)
    near = (np.abs(solid - g).max(axis=1) <= GROUND_NEAR).mean()
    if near < GROUND_SHARE:
        return None
    # The ground's own color, from the points near it (not only the commonest bin).
    return solid[np.abs(solid - g).max(axis=1) <= GROUND_NEAR // 2].mean(axis=0)


def is_light(g):
    return g is not None and (g @ np.array([0.3, 0.6, 0.1])) >= LIGHT_MIN and (g.max() - g.min()) <= GREY_SPREAD


def classify(px):
    """("transparent" | "colored" | "white", the trimmed picture, the ground or None)."""
    box = shown_box(px[:, :, 3])
    if box is None:
        return "blank", px, None
    t, b, l, r = box
    cut = px[t:b + 1, l:r + 1]
    if min(cut.shape[:2]) < 2:
        return "blank", px, None
    e = edge_points(cut)
    if (e[:, 3] < ALPHA_CLEAR).mean() >= CLEAR_EDGE:
        return "transparent", px, None
    g = ground_of(cut)
    if is_light(g):
        return "white", cut, g
    # A clear margin round artwork with its own edge (TuneIn's see-through squares): see-through, not a ground of its own.
    if (edge_points(px)[:, 3] < ALPHA_CLEAR).mean() >= CLEAR_EDGE:
        return "transparent", px, None
    return "colored", px, g


def letter_holes(labels, edge_labels, gone, h, w):
    """The ground seen through the tiny holes of thin lettering ("A", "e", "o" in a small tagline): on a dark screen they would show as white specks. A light
    patch not joined to the edge goes too only when it is tiny (at most HOLE_SHARE of the picture and HOLE_MAX points) and the ground that went is right
    round it (HOLE_NEAR points away, on at least HOLE_AROUND of that ring) - thin strokes, not a solid shape: a white dot or star on a colored badge stays,
    and so does every larger white part of the artwork (WJR's white letters on red)."""
    n = labels.max()
    if n == 0:
        return np.zeros((h, w), bool)
    sizes = ndimage.sum(np.ones((h, w)), labels, index=np.arange(1, n + 1))
    limit = min(HOLE_MAX, HOLE_SHARE * h * w)
    cand = [i + 1 for i, s in enumerate(sizes) if s <= limit and (i + 1) not in set(edge_labels.tolist())]
    out = np.zeros((h, w), bool)
    if not cand:
        return out
    objs = ndimage.find_objects(labels)
    for lab in cand:
        sl = objs[lab - 1]
        if sl is None:
            continue
        y0, y1 = max(0, sl[0].start - HOLE_NEAR - 1), min(h, sl[0].stop + HOLE_NEAR + 1)
        x0, x1 = max(0, sl[1].start - HOLE_NEAR - 1), min(w, sl[1].stop + HOLE_NEAR + 1)
        hole = labels[y0:y1, x0:x1] == lab
        ring = ndimage.binary_dilation(hole, structure=np.ones((3, 3), bool), iterations=HOLE_NEAR) & ~hole
        around = ring.sum()
        if around == 0:
            continue
        if (ring & gone[y0:y1, x0:x1]).sum() >= HOLE_AROUND * around:
            out[y0:y1, x0:x1] |= hole
    return out


def counters(labels, edge_labels, art, rgb, alpha, h, w):
    """(2026-11-15, his find: KFEQ kept white between the K and the F and inside the Q) The ground seen through dark lettering: a light patch not joined to
    the edge goes when the artwork right round it is one or two dark letters - pieces of artwork that hold at most COUNTER_HOLES such patches, are no more
    than COUNTER_AREA times the patch in size (and at least COUNTER_MIN_AREA times: strokes, not a thin frame), and are dark (median brightness under
    COUNTER_DARK), with no artwork inside the patch. White inside a colored banner (WJR's letters: one piece with many patches), inside light lettering
    (WOVU's), inside a framed box or ringed badge holding artwork, or bigger than COUNTER_SHARE of the picture stays."""
    n = labels.max()
    out = np.zeros((h, w), bool)
    if n == 0:
        return out
    sizes = ndimage.sum(np.ones((h, w)), labels, index=np.arange(n + 1))
    edge = set(edge_labels.tolist())
    alab, an = ndimage.label(art, structure=np.ones((3, 3), bool))
    asz = ndimage.sum(np.ones((h, w)), alab, index=np.arange(an + 1))
    objs = ndimage.find_objects(labels)
    owner = {}
    for i in range(1, n + 1):
        if i in edge or sizes[i] < COUNTER_MIN or sizes[i] > COUNTER_SHARE * h * w or objs[i - 1] is None:
            continue
        sl = objs[i - 1]
        y0, y1 = max(0, sl[0].start - 1), min(h, sl[0].stop + 1)
        x0, x1 = max(0, sl[1].start - 1), min(w, sl[1].stop + 1)
        m = labels[y0:y1, x0:x1] == i
        ring = ndimage.binary_dilation(m, structure=np.ones((3, 3), bool)) & ~m
        cs = np.unique(alab[y0:y1, x0:x1][ring])
        cs = cs[cs > 0]
        if len(cs):
            owner[i] = cs
    held = {}
    for cs in owner.values():
        for c in cs:
            held[c] = held.get(c, 0) + 1
    lum = rgb @ np.array([0.3, 0.6, 0.1])
    for i, cs in owner.items():
        area = sum(asz[c] for c in cs)
        if max(held[c] for c in cs) > COUNTER_HOLES or area > COUNTER_AREA * sizes[i] or area < COUNTER_MIN_AREA * sizes[i]:
            continue
        # (review) A patch with artwork of its own inside it (a speck of picture noise aside) (a framed box with words in it, a ringed badge with a picture) is the badge's white, not a
        # letter's middle: kept.
        sl = objs[i - 1]
        m = labels[sl] == i
        if (ndimage.binary_fill_holes(m) & ~m & art[sl]).sum() >= max(COUNTER_INNER, 0.01 * sizes[i]):
            continue
        m = np.isin(alab, cs) & (alpha > 0.8)
        if m.any() and float(np.median(lum[m])) < COUNTER_DARK:
            out |= labels == i
    return out


def unblend(px, ground):
    """The plain ground joined to the edge goes see-through; the artwork's soft edge next to it is un-blended (no fringe). Returns RGBA uint8."""
    h, w = px.shape[:2]
    rgb = px[:, :, :3].astype(np.float64)
    alpha = px[:, :, 3].astype(np.float64) / 255.0
    g = np.asarray(ground, dtype=np.float64)
    d = np.abs(rgb - g).max(axis=2)
    passable = (d <= HARD) | (alpha < ALPHA_CLEAR / 255.0)
    labels, _ = ndimage.label(passable)  # 4-connected
    edge_labels = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    edge_labels = edge_labels[edge_labels > 0]
    gone = np.isin(labels, edge_labels)
    # (KRMO's light-blue-to-white sweep) A ground that is not plain: what a looser match joined to the edge would take is much more than what went - a
    # shaded or textured backing, not a plain one. Kept as it is (None), never half taken off.
    loose = (d <= GROUND_NEAR) | (alpha < ALPHA_CLEAR / 255.0)
    ll, _ = ndimage.label(loose)
    le = np.unique(np.concatenate([ll[0], ll[-1], ll[:, 0], ll[:, -1]]))
    loose_gone = np.isin(ll, le[le > 0]).sum()
    if loose_gone > 0 and gone.sum() < PLAIN_SHARE * loose_gone:
        return None
    gone |= letter_holes(labels, edge_labels, gone, h, w)
    gone |= counters(labels, edge_labels, ~passable, rgb, alpha, h, w)
    # The soft edge: points next to what went (within BAND), not themselves gone.
    near = ndimage.binary_dilation(gone, structure=np.ones((3, 3), bool), iterations=BAND) & ~gone
    band = near & (d < SOFT)
    # The artwork's own color near each band point: the mean of the solid artwork within 2 (else 4) points (not the band, not the ground).
    core = ~gone & ~band & (alpha > 0.8)
    core_f = core.astype(np.float64)
    fg = np.zeros_like(rgb)
    have = np.zeros((h, w), bool)
    for rad in (2, 4):
        size = 2 * rad + 1
        cnt = ndimage.uniform_filter(core_f, size=size, mode="constant")
        sums = np.stack([ndimage.uniform_filter(rgb[:, :, c] * core_f, size=size, mode="constant") for c in range(3)], axis=2)
        ok = (cnt > 1e-6) & ~have
        fg[ok] = sums[ok] / cnt[ok][:, None]
        have |= ok
    out_rgb = rgb.copy()
    out_a = alpha.copy()
    out_a[gone] = 0.0
    ys, xs = np.nonzero(band)
    c = rgb[ys, xs]
    diff = c - g
    # How much artwork a band point has: along the line from the ground to the artwork's color near it (the projection); where that color is the ground's
    # own (no artwork near), the least alpha that can make the point's color over the ground ("color to alpha").
    f = fg[ys, xs]
    fd = f - g
    fn = (fd * fd).sum(axis=1)
    use_f = have[ys, xs] & (np.abs(fd).max(axis=1) > HARD)
    a_proj = np.where(use_f, (diff * fd).sum(axis=1) / np.maximum(fn, 1e-6), 0.0)
    lim = np.where(diff < 0, g, 255.0 - g)
    a_c2a = (np.abs(diff) / np.maximum(lim, 1e-6)).max(axis=1)
    a_new = np.clip(np.where(use_f, a_proj, a_c2a), 0.0, 1.0)
    # The point's own color with the ground taken out: c = a*F + (1-a)*g  ->  F = g + (c-g)/a.
    with np.errstate(divide="ignore", invalid="ignore"):
        col = g + diff / np.maximum(a_new, 1e-3)[:, None]
    col = np.clip(col, 0, 255)
    out_rgb[ys, xs] = col
    out_a[ys, xs] = alpha[ys, xs] * a_new
    out_a[out_a < 2 / 255.0] = 0.0
    out = np.dstack([np.round(out_rgb), np.round(out_a * 255.0)]).astype(np.uint8)
    out[out[:, :, 3] == 0, :3] = 0
    return out


def to_png(px):
    """The PNG: as 256 colors when that changes the picture by at most PALETTE_ERROR on average (about a quarter of the size), else in full color."""
    im = Image.fromarray(px, "RGBA")
    full = io.BytesIO()
    im.save(full, "PNG", optimize=True)
    try:
        q = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        small = io.BytesIO()
        q.save(small, "PNG", optimize=True)
        back = np.array(Image.open(io.BytesIO(small.getvalue())).convert("RGBA")).astype(int)
        shown = px[:, :, 3] > 0
        err = np.abs(back - px.astype(int))[shown].mean() if shown.any() else 0.0
        if err <= PALETTE_ERROR and small.tell() < full.tell():
            return small.getvalue()
    except Exception:
        pass
    return full.getvalue()


def clean(data):
    """A logo file's bytes -> Result."""
    px = load(data)
    if px is None:
        return Result("bad", note="not a picture")
    h, w = px.shape[:2]
    if min(h, w) < MIN_SIDE:
        return Result("small", size=(w, h))
    kind, cut, g = classify(px)
    if kind != "white":
        return Result(kind, size=(w, h), note=("ground %s" % np.round(g).astype(int).tolist()) if g is not None else "")
    out = unblend(cut, g)
    if out is None:
        return Result("colored", size=(w, h), note="shaded light ground %s" % np.round(g).astype(int).tolist())
    box = shown_box(out[:, :, 3], floor=9)
    if box is None:
        return Result("blank", size=(w, h), note="nothing left")
    t, b, l, r = box
    out = out[t:b + 1, l:r + 1]
    if (out[:, :, 3] >= ALPHA_CLEAR).mean() * (out.shape[0] * out.shape[1]) < MIN_LEFT * h * w:
        return Result("blank", size=(w, h), note="next to nothing left")
    return Result("cleaned", png=to_png(out), size=(out.shape[1], out.shape[0]), note="ground %s" % np.round(g).astype(int).tolist())


if __name__ == "__main__":
    import sys
    # clean_logos.py in.png [out.png]: says what it is, and writes the cleaned file when there is one.
    with open(sys.argv[1], "rb") as fh:
        res = clean(fh.read())
    print(sys.argv[1], res)
    if res.png and len(sys.argv) > 2:
        with open(sys.argv[2], "wb") as fh:
            fh.write(res.png)
