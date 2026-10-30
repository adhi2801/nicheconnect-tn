"""Procedural Thanjavur-style vimana for Colyv (study 1).

Built from the Dravidian vimana anatomy: upapitha and adhishthana (moulded
base), pada (pilastered wall with niches), prastara (cornice with a curved
kapota), a hara of miniature shrines (kuta at the corners, shala in the
middle, panjara between), then receding talas, the griva, the shikhara and
the kalasa. Proportions are approximate until a primary source is found
(docs/research/FRONTEND_RESEARCH_2026.md, B5).

Run: blender -b --factory-startup --python vimana.py -- <out.png> [width height samples]
"""

import contextlib
import itertools
import math
import os
import random
import sys

import addon_utils
import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
QUALITY = next((a.split("=", 1)[1] for a in argv if a.startswith("quality=")), "preview")
GRADE = next((a.split("=", 1)[1] for a in argv if a.startswith("grade=")), "morning")
HERO = "--hero" in argv
ORBIT = float(next((a.split("=", 1)[1] for a in argv if a.startswith("orbit=")), "-38"))
OUT = argv[0] if argv else "//vimana.png"
WET = "--wet" in argv
W = int(argv[1]) if len(argv) > 1 else 1600
H = int(argv[2]) if len(argv) > 2 else 900
SAMPLES = int(argv[3]) if len(argv) > 3 else 96

addon_utils.enable("cycles", default_set=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

MESHES = {
    k: bmesh.new()
    for k in ("stone", "gold", "niche", "floor", "wall", "carve", "mono", "dome")
}


# ---------- geometry helpers ----------
def ring(cx, cy, hx, hy, z, e, n, phase=0.0):
    """A superellipse ring: e near 2 is round, large e is square."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n + phase
        c, s = math.cos(t), math.sin(t)
        x = hx * math.copysign(abs(c) ** (2 / e), c)
        y = hy * math.copysign(abs(s) ** (2 / e), s)
        pts.append((cx + x, cy + y, z))
    return pts


def loft(
    key,
    cx,
    cy,
    profile,
    e=40,
    n=64,
    cap_top=True,
    cap_bottom=False,
    aspect=1.0,
    phase=0.0,
):
    """Revolve a moulding profile [(half, z), ...] around a superellipse."""
    bm = MESHES[key]
    rings = [
        [bm.verts.new(p) for p in ring(cx, cy, h, h * aspect, z, e, n, phase)]
        for h, z in profile
    ]
    for a, b in itertools.pairwise(rings):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap_top:
        bm.faces.new(list(reversed(rings[-1])) if False else rings[-1])
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))


def box(key, cx, cy, z0, hx, hy, h):
    bm = MESHES[key]
    v = [
        bm.verts.new((cx + sx * hx, cy + sy * hy, z0 + sz * h))
        for sz in (0, 1)
        for sy in (-1, 1)
        for sx in (-1, 1)
    ]
    for f in (
        (0, 1, 3, 2),
        (4, 6, 7, 5),
        (0, 4, 5, 1),
        (2, 3, 7, 6),
        (0, 2, 6, 4),
        (1, 5, 7, 3),
    ):
        bm.faces.new([v[i] for i in f])


def barrel(key, cx, cy, z0, half_len, r, along_x, n=14):
    """A shala roof: a half cylinder, with closed gable ends."""
    bm = MESHES[key]
    ends = []
    for s in (-1, 1):
        row = []
        for i in range(n + 1):
            a = math.pi * i / n
            u, w = r * math.cos(a), r * math.sin(a) * 1.25
            p = (
                (cx + s * half_len, cy + u, z0 + w)
                if along_x
                else (cx + u, cy + s * half_len, z0 + w)
            )
            row.append(bm.verts.new(p))
        ends.append(row)
    a, b = ends
    for i in range(n):
        bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))


# ---------- architectural parts ----------
INSTANCES = []  # (unit, (x, y, z), scale, rotation about z)


def kuta(cx, cy, z0, s):
    """Corner pavilion, placed as an instance of the detailed unit built once (build_units)."""
    INSTANCES.append(("kuta", (cx, cy, z0), s, 0.0))


def shala(cx, cy, z0, s, along_x, side=None):
    """Middle pavilion (barrel-vaulted), placed as an instance; its great arch faces outward."""
    rot = {0: 0.0, 2: math.pi, 1: math.pi / 2, 3: -math.pi / 2}.get(
        side, 0.0 if along_x else math.pi / 2
    )
    INSTANCES.append(("shala", (cx, cy, z0), s, rot))


def _unit_kuta(v=0):
    """A kuta at unit size: moulded plinth, pilastered cell with a framed arch on each face,
    curved cornice, neck, a square dome carrying four small arches, and a finial."""
    loft(
        "stone",
        0,
        0,
        [(0.5, 0.0), (0.5, 0.05), (0.46, 0.07), (0.46, 0.1), (0.48, 0.12)],
        e=40,
        n=32,
    )
    box("stone", 0, 0, 0.12, 0.4, 0.4, 0.43)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("stone", sx * 0.38, sy * 0.38, 0.12, 0.05, 0.05, 0.43)
            box("stone", sx * 0.38, sy * 0.38, 0.5, 0.07, 0.07, 0.04)
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        for d in (-1, 1):
            box(
                "stone",
                tan[0] * d * 0.17 + nrm[0] * 0.41,
                tan[1] * d * 0.17 + nrm[1] * 0.41,
                0.16,
                0.03 + abs(nrm[0]) * 0.0,
                0.03,
                0.3,
            )
        box(
            "niche",
            nrm[0] * 0.405,
            nrm[1] * 0.405,
            0.18,
            abs(tan[0]) * 0.12 + 0.01,
            abs(tan[1]) * 0.12 + 0.01,
            0.24,
        )
        nasika(nrm[0] * 0.42, nrm[1] * 0.42, 0.44, 0.15, 0.1, side, thick=0.03, out=0.04)
    loft(
        "stone",
        0,
        0,
        [
            (0.44, 0.55),
            (0.5, 0.58),
            (0.54, 0.62),
            (0.52, 0.65),
            (0.44, 0.67),
            (0.36, 0.68),
        ],
        e=40,
        n=32,
    )
    loft("stone", 0, 0, [(0.3, 0.68), (0.3, 0.75), (0.34, 0.77)], e=40, n=32)
    # three designs: a squared dome, a round one with a taller crown, an
    # octagonal one; real towers alternate them tier by tier
    rise = (0.4, 0.48, 0.36)[v]
    dome = [
        (0.38 * math.cos(t) + 0.001, 0.77 + rise * math.sin(t))
        for t in [i * math.pi / 2 / 9 for i in range(10)]
    ]
    loft(
        "stone",
        0,
        0,
        dome,
        e=(3.2, 2.0, 2.0)[v],
        n=(40, 40, 8)[v],
        phase=(0.0, 0.0, math.pi / 8)[v],
    )
    if v == 1:
        # a ring of beads where the dome meets its neck
        for i in range(16):
            a16 = 2 * math.pi * i / 16
            loft(
                "stone",
                0.36 * math.cos(a16),
                0.36 * math.sin(a16),
                [(0.005, 0.765), (0.03, 0.78), (0.005, 0.8)],
                e=2,
                n=8,
            )
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        nasika(nrm[0] * 0.34, nrm[1] * 0.34, 0.8, 0.11, 0.12, side, thick=0.02, out=0.05)
    zt = 0.77 + rise
    finials = (
        [
            (0.07, zt - 0.01),
            (0.09, zt + 0.03),
            (0.05, zt + 0.08),
            (0.07, zt + 0.13),
            (0.01, zt + 0.23),
        ],
        [
            (0.06, zt - 0.01),
            (0.1, zt + 0.06),
            (0.04, zt + 0.12),
            (0.06, zt + 0.16),
            (0.03, zt + 0.22),
            (0.01, zt + 0.32),
        ],
        [(0.08, zt - 0.01), (0.08, zt + 0.04), (0.11, zt + 0.07), (0.01, zt + 0.17)],
    )[v]
    loft("stone", 0, 0, finials, e=2, n=14)


def _unit_shala(v=0):
    """A shala at unit size, long along x, outer face toward -y: plinth, pilastered body, cornice,
    a barrel vault with arched gable ends, a great kudu arch on the outer face, three finials."""
    hl, hw = 0.9, 0.42
    box("stone", 0, 0, 0.0, hl + 0.06, hw + 0.06, 0.12)
    box("stone", 0, 0, 0.12, hl, hw, 0.43)
    for i in range(7):
        u = -hl + 0.04 + i * (2 * hl - 0.08) / 6
        for sy in (-1, 1):
            box("stone", u, sy * (hw + 0.02), 0.12, 0.035, 0.03, 0.43)
    box("niche", 0, -(hw + 0.01), 0.18, 0.22, 0.01, 0.26)
    box("stone", 0, 0, 0.55, hl * 1.08, hw * 1.12, 0.07)
    box("stone", 0, 0, 0.62, hl * 1.02, hw * 1.04, 0.04)
    barrel("stone", 0, 0, 0.66, hl * 0.98, hw * (0.95, 1.08, 0.86)[v], True)
    for sx, sd in ((-1, 3), (1, 1)):
        nasika(sx * hl * 0.99, 0, 0.66, hw * 0.75, hw * 0.95, sd, thick=0.03, out=0.06)
    for sd in (0, 2):
        nasika(
            0,
            (-1 if sd == 0 else 1) * hw * 0.72,
            0.5,
            0.36,
            0.55,
            sd,
            thick=0.04,
            out=0.1,
        )
    for k in ((-0.6, 0, 0.6), (-0.66, -0.22, 0.22, 0.66), (0,))[v]:
        loft(
            "stone",
            k * hl,
            0,
            [
                (0.05, 0.66 + hw * 1.15),
                (0.065, 0.66 + hw * 1.22),
                (0.04, 0.66 + hw * 1.28),
                (0.01, 0.66 + hw * 1.38),
            ],
            e=2,
            n=10,
        )


def build_units():
    """Build each pavilion once, in detail, as its own mesh."""
    units = {}
    for name, fn, v in [(f"kuta{v}", _unit_kuta, v) for v in range(3)] + [
        (f"shala{v}", _unit_shala, v) for v in range(3)
    ]:
        saved = (MESHES["stone"], MESHES["niche"])
        MESHES["stone"], MESHES["niche"] = bmesh.new(), bmesh.new()
        fn(v)
        meshes = []
        for key in ("stone", "niche"):
            bm = MESHES[key]
            me = bpy.data.meshes.new(f"{name}_{key}")
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
            for pg in me.polygons:
                pg.use_smooth = True
            meshes.append((key, me))
        MESHES["stone"], MESHES["niche"] = saved
        units[name] = meshes
    return units


def place_instances(units):
    col = bpy.data.collections.new("pavilions")
    bpy.context.scene.collection.children.link(col)
    for unit, (x, y, z), sc_, rot in INSTANCES:
        # one design per tier, the same on all four sides, as on a real tower
        design = (
            f"{unit}{round(z * 4) % 3}" if PART is None else f"{unit}{round(x / 3.2) + 1}"
        )
        for key, me in units[design]:
            ob = bpy.data.objects.new(f"{unit}_{key}", me)
            ob.location = (x, y, z)
            ob.scale = (sc_, sc_, sc_)
            ob.rotation_euler = (0, 0, rot)
            col.objects.link(ob)


def pilasters(cx, cy, z0, half, h, step, depth=0.22, width=0.32):
    n = max(2, int(2 * half / step))
    for side in range(4):
        for i in range(n + 1):
            u = -half + 2 * half * i / n
            if side == 0:
                x, y = u, -half
            elif side == 1:
                x, y = half, u
            elif side == 2:
                x, y = u, half
            else:
                x, y = -half, u
            hx, hy = (width / 2, depth) if side in (0, 2) else (depth, width / 2)
            box("stone", cx + x, cy + y, z0, hx, hy, h)


def nasika(cx, cy, z0, w, h, side, thick=0.28, out=0.32):
    """A horseshoe arch (kudu) with a finial: the frame over a niche."""
    bm = MESHES["stone"]
    nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
    tan = (-nrm[1], nrm[0])
    pts = []
    for i in range(23):
        th = (
            -0.25 + (math.pi + 0.5) * i / 22
        )  # a little past a half circle: the horseshoe
        pts.append((math.cos(th), math.sin(th)))

    def vert(u, wz, r, depth):
        return bm.verts.new(
            (
                cx + tan[0] * u * w * r + nrm[0] * depth,
                cy + tan[1] * u * w * r + nrm[1] * depth,
                z0 + wz * h * r,
            )
        )

    for depth0, depth1 in ((0.0, out),):
        outer0 = [vert(c, s, 1.0, depth0) for c, s in pts]
        inner0 = [vert(c, s, 0.78, depth0) for c, s in pts]
        outer1 = [vert(c, s, 1.0, depth1) for c, s in pts]
        inner1 = [vert(c, s, 0.78, depth1) for c, s in pts]
        for i in range(22):
            bm.faces.new((outer1[i], outer1[i + 1], inner1[i + 1], inner1[i]))
            bm.faces.new((outer0[i + 1], outer0[i], outer1[i], outer1[i + 1]))
            bm.faces.new((inner0[i], inner0[i + 1], inner1[i + 1], inner1[i]))
    # the lion-face finial (simplified) at the crown of the arch
    fx, fy = cx + nrm[0] * out * 0.6, cy + nrm[1] * out * 0.6
    loft(
        "stone",
        fx,
        fy,
        [
            (w * 0.16, z0 + h * 0.92),
            (w * 0.2, z0 + h * 1.05),
            (w * 0.12, z0 + h * 1.22),
            (0.01, z0 + h * 1.32),
        ],
        e=2.5,
        n=16,
    )


def niches(cx, cy, z0, half, h, count):
    for side in range(4):
        for i in range(count):
            u = -half * 0.72 + 1.44 * half * (i / (count - 1) if count > 1 else 0.5)
            wn = min(1.4, half * 0.12)
            if side == 0:
                x, y, hx, hy = u, -half - 0.05, wn, 0.12
            elif side == 1:
                x, y, hx, hy = half + 0.05, u, 0.12, wn
            elif side == 2:
                x, y, hx, hy = u, half + 0.05, wn, 0.12
            else:
                x, y, hx, hy = -half - 0.05, u, 0.12, wn
            box("niche", cx + x, cy + y, z0 + h * 0.12, hx, hy, h * 0.62)
            nasika(cx + x, cy + y, z0 + h * 0.84, wn + 0.25, h * 0.26, side)
            # the frame: two jambs and a lintel with a small arch above
            if side in (0, 2):
                for d in (-1, 1):
                    box(
                        "stone",
                        cx + x + d * (wn + 0.2),
                        cy + y,
                        z0 + h * 0.1,
                        0.2,
                        0.3,
                        h * 0.66,
                    )
                box("stone", cx + x, cy + y, z0 + h * 0.76, wn + 0.45, 0.32, h * 0.07)
            else:
                for d in (-1, 1):
                    box(
                        "stone",
                        cx + x,
                        cy + y + d * (wn + 0.2),
                        z0 + h * 0.1,
                        0.3,
                        0.2,
                        h * 0.66,
                    )
                box("stone", cx + x, cy + y, z0 + h * 0.76, 0.32, wn + 0.45, h * 0.07)


def prastara(cx, cy, z0, half, k=1.0):
    """Beam, curved kapota cornice and the course above it (k scales it)."""
    p = [
        (0.1, 0),
        (0.1, 0.35),
        (0.35, 0.42),
        (0.9, 0.62),
        (1.15, 0.9),
        (1.1, 1.1),
        (0.85, 1.2),
        (0.2, 1.25),
        (0.2, 1.55),
        (0.35, 1.6),
        (0.35, 1.85),
    ]
    loft("stone", cx, cy, [(half + d * k, z0 + z * k) for d, z in p], e=60, n=64)
    return z0 + 1.85 * k


def hara(cx, cy, z0, half, s):
    """A ring of pavilions on the cornice: kutas at corners, a shala mid-side, panjaras between."""
    edge = half - s * 0.35
    for sx in (-1, 1):
        for sy in (-1, 1):
            kuta(cx + sx * edge, cy + sy * edge, z0, s)
    shala(cx, cy - edge, z0, s, True, 0)
    shala(cx, cy + edge, z0, s, True, 2)
    shala(cx - edge, cy, z0, s, False, 3)
    shala(cx + edge, cy, z0, s, False, 1)
    gap = edge - s * 1.35
    if gap > s * 1.2:
        m = int(gap / (s * 1.25))
        for k in range(m):
            u = s * 1.4 + (gap - s * 0.2) * (k + 0.5) / m
            for d in (-1, 1):
                for x, y in (
                    (d * u, -edge),
                    (d * u, edge),
                    (-edge, d * u),
                    (edge, d * u),
                ):
                    kuta(cx + x, cy + y, z0, s * 0.7)


def adhishthana(half, z0):
    p = [
        (half + 1.6, z0),
        (half + 1.6, z0 + 0.5),
        (half + 1.35, z0 + 0.55),
        (half + 1.35, z0 + 1.4),
        (half + 1.55, z0 + 1.5),
        (half + 1.55, z0 + 1.8),
        (half + 1.2, z0 + 1.9),
        # kumuda: the rounded torus moulding
        (half + 1.3, z0 + 2.05),
        (half + 1.45, z0 + 2.3),
        (half + 1.5, z0 + 2.6),
        (half + 1.45, z0 + 2.9),
        (half + 1.3, z0 + 3.12),
        (half + 1.1, z0 + 3.2),
        # kantha: the recessed neck
        (half + 0.85, z0 + 3.25),
        (half + 0.85, z0 + 3.8),
        (half + 1.25, z0 + 3.85),
        # pattika and the course above
        (half + 1.25, z0 + 4.4),
        (half + 0.95, z0 + 4.45),
        (half + 0.95, z0 + 4.85),
        (half + 0.4, z0 + 4.9),
        (half + 0.4, z0 + 5.4),
    ]
    loft("stone", 0, 0, p, e=80, n=64)
    base_ornament(half, z0)
    return z0 + 5.4


def petal_row(half_out, z, height, width, spacing, depth=0.09, tip_up=True):
    """(Kept name for call sites.) A band of round beads on a moulding: no petals (rule 6)."""
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        step = spacing * 0.55
        n = int(2 * (half_out - 0.3) / step)
        r = min(height, width) * 0.32
        for i in range(n + 1):
            u = -(half_out - 0.3) + i * (2 * (half_out - 0.3) / n)
            x, y = (
                tan[0] * u + nrm[0] * (half_out + r * 0.4),
                tan[1] * u + nrm[1] * (half_out + r * 0.4),
            )
            loft(
                "stone",
                x,
                y,
                [
                    (0.005, z - r),
                    (r * 0.75, z - r * 0.6),
                    (r, z),
                    (r * 0.75, z + r * 0.6),
                    (0.005, z + r),
                ],
                e=2,
                n=10,
            )


MESHES["inscr"] = bmesh.new()


def inscription_band(half_out, z_lo, z_hi):
    bm = MESHES["inscr"]
    uvl = bm.loops.layers.uv.verify()
    h = z_hi - z_lo
    u_acc = 0.0
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        L = 2 * half_out - 0.6
        segs = 40
        for i in range(segs):
            a0, a1 = -L / 2 + L * i / segs, -L / 2 + L * (i + 1) / segs
            q = [
                (
                    tan[0] * a + nrm[0] * (half_out + 0.008),
                    tan[1] * a + nrm[1] * (half_out + 0.008),
                    zz,
                )
                for a, zz in ((a0, z_lo), (a1, z_lo), (a1, z_hi), (a0, z_hi))
            ]
            f = bm.faces.new([bm.verts.new(v) for v in q])
            us = [(u_acc + (a0 + L / 2)) / (h * 32), (u_acc + (a1 + L / 2)) / (h * 32)]
            for loop, (uu, vv) in zip(
                f.loops, ((us[0], 0), (us[1], 0), (us[1], 1), (us[0], 1)), strict=False
            ):
                loop[uvl].uv = (uu, vv)
        u_acc += L


def base_ornament(half, z0):
    inscription_band(half + 1.25, z0 + 3.9, z0 + 4.35)
    inscription_band(half + 0.85, z0 + 3.28, z0 + 3.77)
    # a bead row below the kumuda, and one above the inscribed pattika
    petal_row(half + 1.22, z0 + 1.98, 0.32, 0.36, 0.42, tip_up=False)
    # beads on the course above the pattika, so the inscription reads clear
    petal_row(half + 0.95, z0 + 4.65, 0.36, 0.36, 0.42, tip_up=True)
    # little blocks (dentils) in the recessed neck
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        n = int(2 * (half + 0.6) / 0.75)
        for i in range(n + 1):
            u = -(half + 0.6) + i * 2 * (half + 0.6) / n
            _x, _y = (
                tan[0] * u + nrm[0] * (half + 0.95),
                tan[1] * u + nrm[1] * (half + 0.95),
            )
            pass


def panel_relief(cx, cy, z, R, side, depth=0.12, key="carve"):
    """A carved kudu medallion: a horseshoe arch (kudu), a second within it, and a water pot
    (kalasa) raised at its heart, the pot the pillar's own capital is shaped from. The kudu frames
    openings across the whole tower, so the panels speak its language. Never a lotus (rule 6),
    never a kolam, never a deity (rule 1)."""
    nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
    tan = (-nrm[1], nrm[0])

    def P(u, w, d):
        return (cx + tan[0] * u + nrm[0] * d, cy + tan[1] * u + nrm[1] * d, z + w)

    def horseshoe(r, d, thick):
        # a little past a half circle, standing on two short legs: the kudu's outline
        pts = [P(r * 0.92, -r * 0.55, d)]
        for i in range(29):
            th = -0.22 + (math.pi + 0.44) * i / 28
            pts.append(P(r * math.cos(th), r * 0.15 + r * 0.92 * math.sin(th), d))
        pts.append(P(-r * 0.92, -r * 0.55, d))
        tube(key, pts, [thick] * len(pts), n=8)

    horseshoe(R, depth * 0.55, R * 0.075)
    horseshoe(R * 0.74, depth * 0.45, R * 0.05)
    # the finial at the arch's crown, a small spade of stone
    tube(
        key,
        [
            P(0, R * 1.0, depth * 0.5),
            P(0, R * 1.16, depth * 0.55),
            P(0, R * 1.28, depth * 0.4),
        ],
        [R * 0.07, R * 0.05, R * 0.012],
        n=8,
    )
    # the pot: a vertical lathe, set half into the stone so only its front stands out
    vx, vy, _ = P(0, 0, depth * 0.05)
    k = R * 0.42
    loft(
        key,
        vx,
        vy,
        [
            (k * 0.30, z - k * 1.05),
            (k * 0.62, z - k * 0.85),
            (k * 0.80, z - k * 0.40),
            (k * 0.74, z + k * 0.05),
            (k * 0.36, z + k * 0.35),
            (k * 0.30, z + k * 0.48),
            (k * 0.48, z + k * 0.58),
            (k * 0.20, z + k * 0.62),
            (k * 0.08, z + k * 0.95),
            (0.004, z + k * 1.05),
        ],
        e=2,
        n=24,
    )


def storey(half, z0, h, niche_count, pil_step):
    """A wall built as Dravidian walls are: a recessed core, projecting bays, and deep niches cut into the bays."""
    core = half - 0.75
    box("stone", 0, 0, z0, core, core, h)
    wn = min(1.25, half * 0.1)  # niche half-width
    jw = 0.38  # jamb half-width
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])

        def place(u, d, hu, hd, z, hh, tan=tan, nrm=nrm):
            """A block centred u along the face and d out from the core, hu wide, hd deep."""
            x = tan[0] * u + nrm[0] * (core + d)
            y = tan[1] * u + nrm[1] * (core + d)
            hx = abs(tan[0]) * hu + abs(nrm[0]) * hd
            hy = abs(tan[1]) * hu + abs(nrm[1]) * hd
            box("stone", x, y, z, hx, hy, hh)

        # corner bays (karna): solid, the full depth
        for s in (-1, 1):
            place(s * (core - 0.9), 0.375, 1.0, 0.375, z0, h)
        for i in range(niche_count):
            u = -core * 0.68 + 1.36 * core * (
                i / (niche_count - 1) if niche_count > 1 else 0.5
            )
            # the bay around the niche: jambs, sill and lintel, leaving a real recess
            for s in (-1, 1):
                place(u + s * (wn + jw), 0.375, jw, 0.375, z0, h)
            place(u, 0.375, wn, 0.375, z0, h * 0.12)
            place(u, 0.375, wn, 0.375, z0 + h * 0.74, h * 0.26)
            # framing pilasters on the jambs, with bracket capitals
            for s in (-1, 1):
                place(u + s * (wn + jw), 0.8, 0.14, 0.06, z0 + h * 0.08, h * 0.62)
                place(u + s * (wn + jw), 0.82, 0.24, 0.1, z0 + h * 0.66, h * 0.05)
                place(u + s * (wn + jw), 0.84, 0.34, 0.12, z0 + h * 0.71, h * 0.03)
            # the carved kudu medallion at the back of the recess, and the kudu arch over the opening
            px, py = tan[0] * u + nrm[0] * core, tan[1] * u + nrm[1] * core
            panel_relief(px, py, z0 + h * 0.43, wn * 0.62, side)
            nasika(
                tan[0] * u + nrm[0] * (core + 0.75),
                tan[1] * u + nrm[1] * (core + 0.75),
                z0 + h * 0.8,
                wn + 0.3,
                h * 0.2,
                side,
                out=0.2,
            )
            # slim pilasters on the recessed wall between bays
            if i < niche_count - 1:
                u2 = -core * 0.68 + 1.36 * core * ((i + 0.5) / (niche_count - 1))
                for k in (-1, 1):
                    place(u2 + k * 0.9, 0.12, 0.13, 0.12, z0 + h * 0.06, h * 0.86)
                kx, ky = (
                    tan[0] * u2 + nrm[0] * (core + 0.22),
                    tan[1] * u2 + nrm[1] * (core + 0.22),
                )
                zb = z0 + h * 0.1
                loft(
                    "stone",
                    kx,
                    ky,
                    [
                        (0.12, zb),
                        (0.28, zb + 0.12),
                        (0.34, zb + 0.32),
                        (0.28, zb + 0.5),
                        (0.14, zb + 0.58),
                        (0.2, zb + 0.66),
                        (0.1, zb + 0.7),
                    ],
                    e=2.4,
                    n=20,
                )
                place(u2, 0.22, 0.11, 0.1, zb + 0.7, h * 0.48)
                place(u2, 0.26, 0.2, 0.12, zb + 0.7 + h * 0.48, 0.14)
                nasika(
                    tan[0] * u2 + nrm[0] * (core + 0.3),
                    tan[1] * u2 + nrm[1] * (core + 0.3),
                    zb + 0.86 + h * 0.48,
                    0.42,
                    h * 0.14,
                    side,
                    out=0.12,
                )
    return prastara(0, 0, z0 + h, half)


def build():
    z = 0.0
    half = 14.6
    z = adhishthana(half, z)
    for h, nc in ((7.6, 5), (6.8, 5)):
        z = storey(half, z, h, nc, 2.1)
        hara(0, 0, z, half + 0.4, 2.3)
        half -= 1.0
        z += 0.25
    # the receding talas
    tiers = 13
    for t in range(tiers):
        f = t / (tiers - 1)
        half_t = half - 1.4 - t * 0.62
        h_t = 1.35 - f * 0.35
        k = 0.62 - f * 0.22
        box("stone", 0, 0, z, half_t - 0.3, half_t - 0.3, h_t)
        pilasters(0, 0, z, half_t - 0.2, h_t, 1.1 + f * 0.3, depth=0.14, width=0.2)
        z = prastara(0, 0, z + h_t, half_t - 0.9, k)
        hara(0, 0, z - 0.15, half_t - 0.1, 2.0 - f * 0.75)
        z += 0.25
    # on the real tower the crown stands on a platform wider than the top tier
    return crown(z, (half - 1.4 - (tiers - 1) * 0.62) * 1.35)


def crown(z, T):
    """The crown on a top tier of half width T, standing at height z: platform, neck,
    brim, lattice dome, crests and kalasa, as on the real tower. Returns the top height."""
    # ---- the crown, as on the real tower (photographed references, 29 Oct 2026) ----
    # the platform, with a moulded edge
    box("stone", 0, 0, z, T + 0.1, T + 0.1, 0.45)
    loft(
        "stone",
        0,
        0,
        [
            (T + 0.1, z + 0.45),
            (T + 0.28, z + 0.55),
            (T + 0.2, z + 0.68),
            (T - 0.1, z + 0.72),
        ],
        e=40,
        n=64,
    )
    z += 0.72
    # plain blocks at the corners, where the real tower has seated bulls (rule 1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("stone", sx * (T - 0.55), sy * (T - 0.55), z, 0.42, 0.42, 0.75)
            loft(
                "stone",
                sx * (T - 0.55),
                sy * (T - 0.55),
                [(0.5, z + 0.75), (0.56, z + 0.85), (0.4, z + 0.95), (0.05, z + 1.25)],
                e=6,
                n=24,
            )
    # the neck: a short drum, rounded square, a niche between pilasters on each side
    r_neck = T * 0.8
    neck = 1.25
    loft(
        "stone",
        0,
        0,
        [
            (r_neck + 0.2, z),
            (r_neck, z + 0.2),
            (r_neck, z + neck - 0.12),
            (r_neck + 0.16, z + neck),
        ],
        e=6,
        n=64,
    )
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        box(
            "niche",
            nrm[0] * (r_neck - 0.04),
            nrm[1] * (r_neck - 0.04),
            z + 0.35,
            0.55 if nrm[1] else 0.08,
            0.55 if nrm[0] else 0.08,
            neck - 0.75,
        )
        for d in (-1, 1):
            box(
                "stone",
                tan[0] * d * 0.78 + nrm[0] * r_neck,
                tan[1] * d * 0.78 + nrm[1] * r_neck,
                z + 0.2,
                0.12 if nrm[1] else 0.09,
                0.12 if nrm[0] else 0.09,
                neck - 0.32,
            )
    z += neck
    # the brim: a broad flaring cornice, wider than the dome, its edge hanging down
    B = T * 1.12
    # thick, its edge curving down like a drip-moulding (kapota)
    loft(
        "stone",
        0,
        0,
        [
            (r_neck + 0.16, z - 0.35),
            (T * 0.98, z - 0.05),
            (B * 0.96, z + 0.3),
            (B, z + 0.55),
            (B * 1.01, z + 0.8),
            (B * 0.97, z + 0.98),
            (T * 1.02, z + 1.08),
            (T * 0.94, z + 1.14),
        ],
        e=5,
        n=72,
    )
    # the brim carved as on the real crown: round medallions all along its outer face,
    # a row of beads at its lip, and a second, finer row where it meets the dome
    for i in range(48):
        a48 = 2 * math.pi * (i + 0.5) / 48
        c48, s48 = math.cos(a48), math.sin(a48)
        # the brim is a rounded square (e=5): find its face along this direction
        rr = B * 1.0 / (abs(c48) ** 5 + abs(s48) ** 5) ** (1 / 5)
        mx, my = c48 * (rr + 0.04), s48 * (rr + 0.04)
        loft(
            "stone",
            mx,
            my,
            [
                (0.01, z + 0.5),
                (0.2, z + 0.56),
                (0.26, z + 0.7),
                (0.2, z + 0.84),
                (0.01, z + 0.9),
            ],
            e=2,
            n=14,
        )
    for i in range(96):
        a96 = 2 * math.pi * i / 96
        c96, s96 = math.cos(a96), math.sin(a96)
        rr = B * 0.97 / (abs(c96) ** 5 + abs(s96) ** 5) ** (1 / 5)
        loft(
            "stone",
            c96 * rr,
            s96 * rr,
            [(0.01, z + 0.93), (0.08, z + 0.97), (0.09, z + 1.02), (0.01, z + 1.07)],
            e=2,
            n=8,
        )
    for i in range(72):
        a72 = 2 * math.pi * i / 72
        rr = T * 0.97
        loft(
            "stone",
            math.cos(a72) * rr,
            math.sin(a72) * rr,
            [(0.01, z + 1.1), (0.1, z + 1.15), (0.11, z + 1.22), (0.01, z + 1.28)],
            e=2,
            n=8,
        )
    z += 1.14
    # the dome: rounded, a little squat, carved all over in a diamond lattice
    Rd = T * 0.98
    Hd = T * 1.0
    dome = [
        (Rd * math.cos(a) + 0.01, z + Hd * math.sin(a))
        for a in [i * math.pi / 2 / 18 for i in range(19)]
    ]
    loft("dome", 0, 0, dome, e=2, n=96)
    # round medallions set into the lattice, between the crests
    for i in range(8):
        a8 = math.pi / 8 + i * math.pi / 4
        el = 0.36
        cx_, cy_ = (
            Rd * math.cos(el) * math.cos(a8) * 1.0,
            Rd * math.cos(el) * math.sin(a8) * 1.0,
        )
        cz_ = z + Hd * math.sin(el)
        loft(
            "dome",
            cx_ * 1.03,
            cy_ * 1.03,
            [
                (0.01, cz_ - 0.36),
                (0.3, cz_ - 0.24),
                (0.36, cz_),
                (0.3, cz_ + 0.24),
                (0.01, cz_ + 0.36),
            ],
            e=2,
            n=20,
            aspect=1.0,
        )
    # the four great crests: fans standing on the brim at the cardinal points, their rims
    # finely scalloped like feathers, leaning back against the dome, a rounded crest on top
    Fr = T * 0.5
    lean = 0.42  # how far back the top leans, per metre of height

    def crest_layer(rad, scal, lobes, thick, fwd, key, dvec, pvec, base_z):
        """One layer of a crest: a fan outline extruded through its thickness, sheared back."""
        bm_ = MESHES[key]
        outline = [(-rad, 0.0)]
        for i in range(97):
            th = math.pi * i / 96
            rr = rad * (1 + scal * abs(math.cos(lobes * th / 2)) - scal)
            outline.append((-rr * math.cos(th), rr * math.sin(th) * 1.12))
        outline.append((rad, 0.0))
        rings_ = []
        for sgn in (-1, 1):
            rings_.append(
                [
                    bm_.verts.new(
                        dvec * (fwd - lean * h + sgn * thick / 2)
                        + pvec * s
                        + Vector((0, 0, base_z + h))
                    )
                    for s, h in outline
                ]
            )
        bm_.faces.new(rings_[0][::-1])
        bm_.faces.new(rings_[1])
        for i in range(len(outline)):
            j = (i + 1) % len(outline)
            bm_.faces.new((rings_[0][i], rings_[0][j], rings_[1][j], rings_[1][i]))

    for ang in range(4):
        a = ang * math.pi / 2
        dvec, pvec = (
            Vector((math.cos(a), math.sin(a), 0)),
            Vector((-math.sin(a), math.cos(a), 0)),
        )
        base_z = z - 0.2
        crest_layer(Fr, 0.06, 30, 0.3, Rd * 1.04, "stone", dvec, pvec, base_z)
        crest_layer(
            Fr * 0.8, 0.05, 24, 0.24, Rd * 1.04 + 0.24, "stone", dvec, pvec, base_z
        )
        crest_layer(
            Fr * 0.6, 0.04, 18, 0.18, Rd * 1.04 + 0.42, "stone", dvec, pvec, base_z
        )
        crest_layer(
            Fr * 0.36, 0.0, 2, 0.05, Rd * 1.04 + 0.53, "niche", dvec, pvec, base_z
        )
        # the rounded crest at the top, in place of the carved face
        h_top = Fr * 1.12
        c = dvec * (Rd * 1.04 - lean * h_top + 0.15) + Vector((0, 0, base_z + h_top))
        loft(
            "stone",
            c.x,
            c.y,
            [
                (0.01, c.z - 0.15),
                (0.34, c.z),
                (0.4, c.z + 0.25),
                (0.3, c.z + 0.5),
                (0.12, c.z + 0.68),
                (0.01, c.z + 0.75),
            ],
            e=2,
            n=20,
        )
    z += Hd
    # the kalasa, gold: a round pot, a neck ring, a flared disc, a pointed flame
    k = [
        (0.55, z - 0.05),
        (0.78, z + 0.05),
        (0.64, z + 0.18),
        (0.72, z + 0.3),
        (1.02, z + 0.62),
        (1.12, z + 0.95),
        (1.0, z + 1.3),
        (0.6, z + 1.55),
        (0.4, z + 1.64),
        (0.52, z + 1.74),
        (0.34, z + 1.86),
        (0.3, z + 1.98),
        (0.78, z + 2.08),
        (0.74, z + 2.16),
        (0.3, z + 2.2),
        (0.36, z + 2.34),
        (0.42, z + 2.68),
        (0.32, z + 3.05),
        (0.16, z + 3.42),
        (0.01, z + 3.8),
    ]
    loft("gold", 0, 0, k, e=2, n=64)
    return z + 3.8


def courtyard():
    box("floor", 0, 0, -0.3, 260, 260, 0.3)
    # a cloister on three sides: a low wall with a colonnade in front
    for cx, cy, hx, hy in ((0, 95, 120, 1.2), (-120, 0, 1.2, 95), (120, 0, 1.2, 95)):
        box("wall", cx, cy, 0, hx, hy, 6.5)
        box(
            "wall",
            cx,
            cy,
            6.5,
            hx + (2.6 if hx < 5 else 0),
            hy + (2.6 if hy < 5 else 0),
            0.7,
        )
    for i in range(-36, 37):
        u = i * 3.2
        for x, y in ((u, 92), (-117, u * 0.8), (117, u * 0.8)):
            if abs(x) <= 118 and abs(y) <= 93:
                box("wall", x, y, 0, 0.45, 0.45, 6.5)


MESHES["grass"] = bmesh.new()
MESHES["path"] = bmesh.new()
MESHES["flame"] = bmesh.new()


def mandapa(x0, x1, hy):
    """The pillared hall in front of the tower: moulded base, pilastered walls, cornice, a hara of pavilions."""
    cx, hx = (x0 + x1) / 2, abs(x1 - x0) / 2
    z = 0.0
    for d, h in (
        (1.4, 0.6),
        (1.15, 0.9),
        (1.3, 0.7),
        (0.9, 0.5),
        (1.15, 0.6),
        (0.6, 0.6),
    ):
        box("stone", cx, 0, z, hx + d, hy + d, h)
        z += h
    wall_h = 7.0
    box("stone", cx, 0, z, hx, hy, wall_h)
    for i in range(int(2 * hx / 2.0) + 1):
        u = x0 + i * 2.0 if x0 < x1 else x1 + i * 2.0
        for sy in (-1, 1):
            box("stone", u, sy * (hy + 0.12), z, 0.18, 0.22, wall_h)
    for i in range(int(2 * hy / 2.0) + 1):
        v = -hy + i * 2.0
        box("stone", min(x0, x1) - 0.12, v, z, 0.22, 0.18, wall_h)
    for i in range(int(2 * hx / 5.0)):
        u = min(x0, x1) + 2.5 + i * 5.0
        for sy, side in ((-1, 0), (1, 2)):
            # a framed panel: jamb pilasters with capitals, a kudu medallion, a kudu arch above
            for d in (-1, 1):
                box("stone", u + d * 1.25, sy * (hy + 0.3), z + 0.5, 0.22, 0.3, 4.6)
                box("stone", u + d * 1.25, sy * (hy + 0.35), z + 5.1, 0.36, 0.36, 0.25)
            box("stone", u, sy * (hy + 0.3), z + 0.3, 1.5, 0.32, 0.25)
            box("stone", u, sy * (hy + 0.32), z + 5.35, 1.6, 0.34, 0.3)
            panel_relief(u, sy * hy, z + 2.9, 0.75, side)
            nasika(u, sy * (hy + 0.35), z + 5.7, 1.1, 1.3, side, out=0.2)
    z += wall_h
    for d, h in ((0.3, 0.3), (0.8, 0.35), (1.2, 0.35), (1.0, 0.25), (0.4, 0.4)):
        box("stone", cx, 0, z, hx + d, hy + d, h)
        z += h
    s = 1.9
    for i in range(int(2 * hx / (s * 2.4))):
        u = min(x0, x1) + s * 1.3 + i * s * 2.4
        for sy, side in ((-1, 0), (1, 2)):
            if i % 3 == 1:
                shala(u, sy * (hy - 0.4), z, s, True, side)
            else:
                kuta(u, sy * (hy - 0.4), z, s * 0.85)


def lamp_pillar(x, y, h):
    """A deepa stambha: a slender octagonal pillar ringed with small oil lamps."""
    loft(
        "stone",
        x,
        y,
        [(1.3, 0), (1.3, 0.6), (1.0, 0.7), (1.0, 1.4), (0.75, 1.5)],
        e=40,
        n=32,
    )
    loft(
        "stone",
        x,
        y,
        [
            (0.42, 1.5),
            (0.36, h * 0.92),
            (0.5, h * 0.95),
            (0.5, h),
            (0.2, h + 0.4),
            (0.25, h + 0.7),
            (0.02, h + 1.1),
        ],
        e=7,
        n=32,
    )
    rings = 9
    for r in range(rings):
        z = 2.4 + (h - 3.0) * r / (rings - 1)
        rad = 0.85 - 0.25 * r / rings
        loft(
            "stone",
            x,
            y,
            [(0.4, z - 0.08), (rad, z), (rad, z + 0.06), (0.4, z + 0.1)],
            e=8,
            n=32,
        )
        for k in range(8):
            a = 2 * math.pi * k / 8 + r * 0.2
            px, py = x + rad * 0.9 * math.cos(a), y + rad * 0.9 * math.sin(a)
            loft(
                "gold",
                px,
                py,
                [(0.02, z + 0.06), (0.07, z + 0.1), (0.06, z + 0.14)],
                e=2,
                n=8,
            )
            loft(
                "flame",
                px,
                py,
                [
                    (0.005, z + 0.13),
                    (0.035, z + 0.18),
                    (0.02, z + 0.25),
                    (0.002, z + 0.33),
                ],
                e=2,
                n=8,
            )


MESHES["blade"] = bmesh.new()


def grass_blades(
    cam_xy, fwd_angle, count=220000, seed=3, spread=0.75, reach=80, keep_out=()
):
    """Real blades near the camera: curved, tapered, leaning, in tufts; the lawn shader covers the distance."""
    import random

    rnd = random.Random(seed)  # noqa: S311 - shape variation, not security
    bm = MESHES["blade"]
    cx, cy = cam_xy
    for _i in range(count):
        dist = 1.5 + reach * (rnd.random() ** 2.0)
        ang = fwd_angle + rnd.uniform(-spread, spread)
        x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
        if -46 < x < -34 and y > -140:  # keep the paved path clear
            continue
        if any(x0 < x < x1 and y0 < y < y1 for (x0, y0, x1, y1) in keep_out):
            continue
        h = rnd.uniform(0.07, 0.19) * (1.5 if rnd.random() < 0.06 else 1.0)
        w = rnd.uniform(0.006, 0.014)
        a = rnd.uniform(0, 2 * math.pi)
        lean = rnd.uniform(0.15, 0.6)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy * w, dx * w
        pts = []
        for _s, (u, ww) in enumerate(((0, 1.0), (0.45, 0.8), (0.8, 0.45), (1.0, 0.0))):
            off = lean * h * u * u
            pts.append(
                (
                    (x + dx * off - px * ww, y + dy * off - py * ww, h * u),
                    (x + dx * off + px * ww, y + dy * off + py * ww, h * u),
                )
            )
        vs = [(bm.verts.new(lft), bm.verts.new(rgt)) for lft, rgt in pts]
        for (l0, r0), (l1, r1) in itertools.pairwise(vs):
            bm.faces.new((l0, r0, r1, l1))


def grounds():
    # a paved processional path toward the hall, lawns on either side
    box("path", -40, -70, 0.0, 6.5, 70, 0.04)
    box("path", -40, -6, 0.0, 30, 28, 0.03)
    box("path", 0, -64, 0.0, 34, 50, 0.05)
    box("path", 0, -130, 0.0, 40, 20, 0.05)
    for cx, cy, hx, hy in ((-90, -70, 40, 70), (10, -80, 36, 60), (60, -20, 50, 60)):
        box("grass", cx, cy, 0.0, hx, hy, 0.02)


MESHES["trunk"] = bmesh.new()
MESHES["leaf"] = bmesh.new()


def tube(key, path, radii, n=10):
    bm = MESHES[key]
    rings = []
    for i, (p, r) in enumerate(zip(path, radii, strict=False)):
        p = Vector(p)
        t = (
            Vector(path[min(i + 1, len(path) - 1)]) - Vector(path[max(i - 1, 0)])
        ).normalized()
        a = t.orthogonal().normalized()
        b = t.cross(a)
        rings.append(
            [
                bm.verts.new(
                    p
                    + r
                    * (
                        math.cos(2 * math.pi * k / n) * a
                        + math.sin(2 * math.pi * k / n) * b
                    )
                )
                for k in range(n)
            ]
        )
    for r0, r1 in itertools.pairwise(rings):
        for k in range(n):
            bm.faces.new((r0[k], r0[(k + 1) % n], r1[(k + 1) % n], r1[k]))


MESHES["deadleaf"] = bmesh.new()
MESHES["banana"] = bmesh.new()
MESHES["fruit"] = bmesh.new()
MESHES["heart"] = bmesh.new()
MESHES["bstem"] = bmesh.new()
MESHES["midrib"] = bmesh.new()


def leaflet(bm, base, direction, side, length, width, droop, fold):
    """One pinna: a narrow blade that arches out and down, folded along its midrib."""
    pts = []
    for k in range(5):
        u = k / 4
        c = base + direction * (length * u) + Vector((0, 0, -droop * length * u * u))
        w = width * math.sin(math.pi * min(0.999, 0.15 + 0.85 * u)) * (1 - 0.7 * u)
        pts.append(
            (
                c - side * w + Vector((0, 0, -fold * w)),
                c + Vector((0, 0, fold * w * 0.6)),
                c + side * w + Vector((0, 0, -fold * w)),
            )
        )
    vs = [[bm.verts.new(q) for q in row] for row in pts]
    for a, b in itertools.pairwise(vs):
        bm.faces.new((a[0], a[1], b[1], b[0]))
        bm.faces.new((a[1], a[2], b[2], b[1]))


def palm(x, y, height, lean, heading, seed, detail=1.0):
    """A coconut palm: a swollen base, a leaning ringed trunk, a crown of arching fronds
    whose leaflets hang more toward the tip, a few dead fronds, and a cluster of nuts."""
    import random

    rnd = random.Random(seed)  # noqa: S311 - shape variation, not security
    path, radii = [], []
    for i in range(32):
        f = i / 31
        bend = lean * height * (f**1.7)
        wob = 0.12 * math.sin(f * 7 + seed)
        path.append(
            (
                x + bend * math.cos(heading) + wob * math.sin(heading),
                y + bend * math.sin(heading) - wob * math.cos(heading),
                height * f,
            )
        )
        radii.append(0.27 - 0.09 * f + 0.16 * max(0.0, 0.12 - f) / 0.12)
    tube("trunk", path, radii, n=14)
    crown = Vector(path[-1])
    loft(
        "trunk",
        crown.x,
        crown.y,
        [
            (0.2, crown.z - 0.6),
            (0.34, crown.z - 0.2),
            (0.28, crown.z + 0.15),
            (0.05, crown.z + 0.4),
        ],
        e=2,
        n=14,
    )
    nf = int(30 * detail) + 4
    for k in range(nf):
        az = 2 * math.pi * k * 0.618 + rnd.uniform(-0.12, 0.12)
        age = k / (nf - 1)
        dead = age > 0.9
        bm = MESHES["deadleaf" if dead else "leaf"]
        rise = 1.15 - 1.7 * age + rnd.uniform(-0.15, 0.15)
        length = rnd.uniform(4.8, 6.4) * (0.7 if age < 0.12 else 1.0)
        d = Vector((math.cos(az), math.sin(az), 0))
        side = Vector((-d.y, d.x, 0))
        segs = int(34 * detail) + 6
        spine = []
        for t in range(segs + 1):
            u = t / segs
            hang = 1.6 if dead else 0.55
            spine.append(
                crown
                + d * length * u * (1 - 0.3 * max(0, -rise) * u)
                + Vector((0, 0, length * (rise * 0.6 * u - hang * u * u)))
            )
        tube(
            "deadleaf" if dead else "trunk",
            spine[: int(segs * 0.6)],
            [
                0.045 - 0.03 * i / max(1, int(segs * 0.6) - 1)
                for i in range(int(segs * 0.6))
            ],
            n=5,
        )
        for t in range(2, segs):
            u = t / segs
            base = spine[t]
            fwd = (spine[t + 1] - spine[t - 1]).normalized()
            for sd in (-1, 1):
                ll = (1.55 * math.sin(math.pi * min(1, u * 1.04)) ** 0.6) * (
                    1 - 0.35 * u
                ) + 0.12
                out = (side * sd * 0.92 + fwd * 0.38).normalized()
                leaflet(
                    bm,
                    base,
                    out,
                    fwd * 0.5,
                    ll,
                    0.045,
                    0.35 + 0.55 * u + rnd.uniform(-0.1, 0.1),
                    0.6,
                )
    for c in range(int(rnd.uniform(5, 11))):
        a = 2 * math.pi * c / 8 + rnd.uniform(-0.2, 0.2)
        q = crown + Vector(
            (0.4 * math.cos(a), 0.4 * math.sin(a), -0.45 + rnd.uniform(-0.15, 0.1))
        )
        loft(
            "fruit",
            q.x,
            q.y,
            [
                (0.01, q.z - 0.2),
                (0.15, q.z - 0.1),
                (0.17, q.z + 0.04),
                (0.12, q.z + 0.14),
                (0.01, q.z + 0.21),
            ],
            e=2,
            n=12,
        )


def banana_blade(bm, spine, side, rnd, age):
    """One banana leaf blade on its midrib, as a continuous surface with UVs (u along the
    leaf, v from midrib to margin). Wind tears it along its parallel veins into strips:
    each strip is its own surface, drooping a little more at its free edge, so the leaf
    reads as torn, not as a comb with teeth missing."""
    uvl = bm.loops.layers.uv.verify()
    segs = len(spine) - 1

    def at(u):
        f = u * segs
        i = min(int(f), segs - 1)
        return spine[i].lerp(spine[i + 1], f - i)

    def width(u):
        return 0.6 * math.sin(math.pi * min(0.999, 0.02 + 0.98 * u)) ** 0.42

    for sd in (-1, 1):
        # tears: more and wider on older leaves, none near the base where it is tough
        n_tears = int(rnd.uniform(1, 4) + age * 9)
        cuts = sorted(rnd.uniform(0.18, 0.97) for _ in range(n_tears))
        bounds = [0.0, *cuts, 1.0]
        for k in range(len(bounds) - 1):
            ua, ub = bounds[k] + (0.004 if k else 0.0), bounds[k + 1]
            if ub - ua < 0.012:
                continue
            free = 0.0 if k == 0 else rnd.uniform(0.25, 1.0)
            nu = max(2, int((ub - ua) * 40))
            nv = 7
            depth_cut = 1.0 if k else 0.0
            grid = []
            for i in range(nu + 1):
                u = ua + (ub - ua) * i / nu
                row = []
                a = at(u)
                w = width(u)
                for j in range(nv + 1):
                    v = 0.03 + 0.97 * j / nv
                    # cupped across: rises from the midrib, then falls to the margin
                    lift = 0.08 * w * math.sin(math.pi * v * 0.8) - 0.22 * w * v * v
                    droop = -free * depth_cut * 0.25 * w * v**2.2
                    q = a + side * sd * w * v + Vector((0, 0, lift + droop))
                    row.append((bm.verts.new(q), (u, v)))
                grid.append(row)
            for i in range(nu):
                for j in range(nv):
                    quad = (
                        grid[i][j],
                        grid[i + 1][j],
                        grid[i + 1][j + 1],
                        grid[i][j + 1],
                    )
                    f = bm.faces.new([c[0] for c in (quad if sd > 0 else quad[::-1])])
                    for loop, c in zip(
                        f.loops, (quad if sd > 0 else quad[::-1]), strict=False
                    ):
                        loop[uvl].uv = c[1]


def banana(x, y, height, heading, seed, fruit=True):
    """A banana plant (vazhai): a mottled, sheathed pseudostem, broad cupped leaves on arching
    petioles, torn along their veins, a rolled young leaf at the top, and on some a bunch with its heart."""
    import random

    rnd = random.Random(seed)  # noqa: S311 - shape variation, not security
    stem = [(x, y, 0)] + [
        (x + 0.04 * math.sin(i), y, height * i / 10) for i in range(1, 11)
    ]
    tube("bstem", stem, [0.34 - 0.17 * i / 10 for i in range(11)], n=20)
    top = Vector(stem[-1])
    # the rolled cigar leaf at the crown
    tube(
        "banana",
        [top, top + Vector((0.02, 0, 0.7)), top + Vector((0.06, 0.02, 1.25))],
        [0.07, 0.05, 0.015],
        n=8,
    )
    nleaves = 15
    for k in range(nleaves):
        az = heading + 2 * math.pi * k * 0.382 + rnd.uniform(-0.2, 0.2)
        age = k / (nleaves - 1)
        d = Vector((math.cos(az), math.sin(az), 0))
        side = Vector((-d.y, d.x, 0))
        # a petiole that rises, then the blade that arches out and droops with age
        pet_len = 0.7 + 0.3 * rnd.random()
        rise0 = 1.25 - 1.1 * age
        p0 = top + Vector((0, 0, -0.25 * age))
        p1 = p0 + d * pet_len * 0.6 + Vector((0, 0, pet_len * rise0 * 0.7))
        tube(
            "bstem",
            [p0, p0.lerp(p1, 0.5) + Vector((0, 0, 0.05)), p1],
            [0.05, 0.04, 0.03],
            n=8,
        )
        length = rnd.uniform(2.4, 3.1) * (0.65 if k < 2 else 1)
        segs = 30
        spine = []
        for t in range(segs + 1):
            u = t / segs
            spine.append(
                p1
                + d * length * u
                + Vector((0, 0, length * (0.5 * rise0 * u - (0.75 + 0.9 * age) * u * u)))
            )
        tube("midrib", spine, [0.025 - 0.02 * t / segs for t in range(segs + 1)], n=6)
        old = age > 0.8
        bm = MESHES["deadleaf" if old and rnd.random() < 0.6 else "banana"]
        banana_blade(bm, spine, side, rnd, age)
    for k in range(rnd.randint(2, 4)):
        az = heading + rnd.uniform(0, 2 * math.pi)
        d = Vector((math.cos(az), math.sin(az), 0))
        side = Vector((-d.y, d.x, 0))
        z0 = top.z - 0.15 - 0.25 * k
        base = Vector((top.x, top.y, z0)) + d * 0.12
        hang = [
            base
            + d * (0.25 * math.sin(math.pi * 0.5 * u))
            + Vector((0, 0, -2.2 * u * rnd.uniform(0.7, 1.0)))
            for u in [i / 20 for i in range(21)]
        ]
        tube("deadleaf", hang, [0.02] * len(hang), n=5)
        banana_blade(MESHES["deadleaf"], hang, side * 0.35, rnd, 1.0)
    if fruit:
        stalk = [top, top + Vector((0.35, 0.1, -0.2)), top + Vector((0.5, 0.15, -0.9))]
        tube("banana", stalk, [0.04, 0.035, 0.03], n=6)
        c = stalk[-1]
        for h in range(6):
            for f in range(10):
                a = 2 * math.pi * f / 10
                bz = c.z + 0.32 - h * 0.13
                b0 = Vector((c.x + 0.09 * math.cos(a), c.y + 0.09 * math.sin(a), bz))
                b1 = b0 + Vector((0.16 * math.cos(a), 0.16 * math.sin(a), 0.12))
                tube(
                    "fruit",
                    [b0, b0.lerp(b1, 0.5) + Vector((0, 0, -0.02)), b1],
                    [0.02, 0.026, 0.012],
                    n=6,
                )
        loft(
            "heart",
            c.x,
            c.y,
            [
                (0.01, c.z - 0.75),
                (0.09, c.z - 0.55),
                (0.11, c.z - 0.4),
                (0.06, c.z - 0.25),
                (0.02, c.z - 0.15),
            ],
            e=2,
            n=14,
        )


def grove():
    import random

    rnd = random.Random(7)  # noqa: S311 - shape variation, not security
    spots = [
        (-34, -118, 15.5),
        (-22, -128, 12.5),
    ]  # foreground, framing the left of the shot
    for _ in range(70):  # a skyline of palms beyond the cloister
        spots.append((rnd.uniform(-230, 240), rnd.uniform(102, 190), rnd.uniform(15, 26)))
    for _ in range(24):
        spots.append((rnd.uniform(126, 200), rnd.uniform(-120, 100), rnd.uniform(14, 24)))
    for i, (x, y, h) in enumerate(spots):
        palm(
            x,
            y,
            h,
            rnd.uniform(0.04, 0.16),
            rnd.uniform(0, 2 * math.pi),
            i,
            detail=1.0 if i < 2 else 0.45,
        )
    # banana plants flanking the path, as at a festive entrance
    for j, (bx, by) in enumerate(((-62, -114), (-41, -127), (-49, -96), (-31, -92))):
        banana(
            bx, by, rnd.uniform(3.6, 4.6), rnd.uniform(0, 6.28), 100 + j, fruit=(j < 3)
        )


MESHES["bird"] = bmesh.new()


def birds(n=26, seed=11):
    import random

    rnd = random.Random(seed)  # noqa: S311 - shape variation, not security
    bm = MESHES["bird"]
    cx, cy, cz = 40.0, 120.0, 95.0
    for _i in range(n):
        x, y, z = cx + rnd.gauss(0, 45), cy + rnd.gauss(0, 30), cz + rnd.gauss(0, 14)
        span = rnd.uniform(0.9, 1.6)
        flap = rnd.uniform(-0.35, 0.45)
        yaw = rnd.uniform(-0.4, 0.4) + 0.3
        dx, dy = math.cos(yaw), math.sin(yaw)
        body = [
            Vector((x - dx * 0.35, y - dy * 0.35, z)),
            Vector((x + dx * 0.4, y + dy * 0.4, z + 0.02)),
        ]
        tube("bird", body, [0.07, 0.04], n=6)
        for sd in (-1, 1):
            sx, sy = -dy * sd, dx * sd
            root0 = Vector((x - dx * 0.12, y - dy * 0.12, z))
            root1 = Vector((x + dx * 0.15, y + dy * 0.15, z))
            elbow = Vector(
                (x + sx * span * 0.5, y + sy * span * 0.5, z + flap * span * 0.5)
            )
            tip = Vector(
                (
                    x + sx * span - dx * 0.25,
                    y + sy * span - dy * 0.25,
                    z + flap * span * 0.6 - 0.1,
                )
            )
            v = [bm.verts.new(q) for q in (root0, root1, elbow, tip)]
            bm.faces.new((v[0], v[1], v[2]))
            bm.faces.new((v[0], v[2], v[3]))


MESHES["pstone"] = bmesh.new()


def prism(key, origin, along, across, outline, half_w):
    """A 2D outline (s along the arm, z up) extruded across a width: brackets, beams, steps."""
    bm = MESHES[key]
    o, a, c = Vector(origin), Vector(along), Vector(across)
    sides = []
    for sgn in (-1, 1):
        sides.append(
            [
                bm.verts.new(o + a * s + Vector((0, 0, z)) + c * (sgn * half_w))
                for (s, z) in outline
            ]
        )
    n = len(outline)
    bm.faces.new(sides[0][::-1])
    bm.faces.new(sides[1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((sides[0][i], sides[0][j], sides[1][j], sides[1][i]))


def taranga_outline(L, depth_root, depth_tip, rolls=3):
    """The wave bracket (taranga potika) of Chola and Pandya halls: flat on top, its underside
    a run of rolls stepping down toward the pillar."""
    top = [(0.0, 0.0), (L, 0.0), (L, -depth_tip)]
    under = []
    steps = 36
    for i in range(steps + 1):
        s = L - (L - 0.28) * i / steps
        f = (L - s) / (L - 0.28)
        base = depth_tip + (depth_root - depth_tip) * f
        roll = 0.06 * abs(math.sin(math.pi * rolls * f))
        under.append((s, -(base + roll)))
    return top + under + [(0.0, -depth_root - 0.02)]


def bead(key, x, y, z, rad):
    """One small stone bead: the unit of the bead rows (malai) Chola carvers ran along mouldings."""
    loft(
        key,
        x,
        y,
        [
            (0.002, z - rad),
            (rad * 0.7, z - rad * 0.7),
            (rad, z),
            (rad * 0.7, z + rad * 0.7),
            (0.002, z + rad),
        ],
        e=2,
        n=8,
    )


def bead_square(key, cx, cy, half, z, rad, step):
    """A row of beads around a square course, corner to corner."""
    n = max(2, round(2 * half / step))
    for side in range(4):
        for i in range(n):
            u = -half + 2 * half * i / n
            x, y = ((u, -half), (half, u), (-u, half), (-half, -u))[side]
            bead(key, cx + x, cy + y, z, rad)


def bead_ring(key, cx, cy, r, z, rad, count):
    """A ring of beads around a round or octagonal section."""
    for i in range(count):
        a = 2 * math.pi * i / count
        bead(key, cx + r * math.cos(a), cy + r * math.sin(a), z, rad)


def pillar(x, y, h=4.6, seed=0, w=0.36):
    """A Chola granite pillar, after the hall pillars of Thanjavur and Darasuram, detailed part by
    part from the base up (pass 10, 30 October 2026):

    - a base (upapitha): a slab, a rounded moulding (kumuda), a recessed neck with a bead row
      (kantha) and a top band (pattika);
    - the shaft: square blocks (saduram) alternating with chamfered octagonal sections (kattu); each
      block a raised frame with a bead border around a kudu medallion, banded at both edges; each
      octagon stopped with triangles and ringed with beads at its waist;
    - the capital: a ribbed pot (kalasa), a neck (tadi), a dish (kumbha) ribbed with gadroons, never
      petals (no lotus, rule 6), and a thick abacus (palagai) with a bead row beneath;
    - the bracket (potika): the wave rolls (taranga) on four arms, each with its flat central
      band (patta), as the Cholas cut them.

    Every size follows the half-width `w`, so the proportion holds at any size."""
    K = "pstone"
    rnd = random.Random(seed)  # noqa: S311 - carving variation, not security
    # --- the base
    box(K, x, y, 0.0, w * 1.55, w * 1.55, 0.12)
    loft(
        K,
        x,
        y,
        [
            (w * 1.46, 0.12),
            (w * 1.46, 0.18),
            (w * 1.36, 0.21),
            (w * 1.44, 0.27),
            (w * 1.47, 0.32),
            (w * 1.42, 0.37),
            (w * 1.26, 0.40),
            (w * 1.26, 0.47),
            (w * 1.38, 0.50),
            (w * 1.38, 0.57),
            (w * 1.18, 0.60),
        ],
        e=40,
        n=48,
    )
    bead_square(K, x, y, w * 1.28, 0.435, 0.022, 0.085)
    z = 0.60
    capital_h, bracket_h = 1.25, 0.42
    shaft = h - z - capital_h - bracket_h
    plan = (("sq", 0.26), ("oct", 0.16), ("sq", 0.22), ("oct", 0.16), ("sq", 0.20))
    for k, (kind, share) in enumerate(plan):
        hh = shaft * share
        if kind == "sq":
            box(K, x, y, z, w, w, hh)
            # a thin projecting band, beaded, at both edges of the block
            for zb in (z, z + hh - 0.035):
                box(K, x, y, zb, w + 0.02, w + 0.02, 0.035)
            bead_square(K, x, y, w + 0.025, z + 0.06, 0.016, 0.07)
            bead_square(K, x, y, w + 0.025, z + hh - 0.06, 0.016, 0.07)
            for side in range(4):
                nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
                tan = (-nrm[1], nrm[0])
                fx, fy = x + nrm[0] * w, y + nrm[1] * w
                m, fw = w * 0.86, 0.035
                top, bot = z + hh - 0.12, z + 0.12
                # the raised frame around the sunk panel
                for u0, u1, w0, w1 in (
                    (-m, m, bot, bot + fw),
                    (-m, m, top - fw, top),
                    (-m, -m + fw, bot, top),
                    (m - fw, m, bot, top),
                ):
                    cu, hu = (u0 + u1) / 2, (u1 - u0) / 2
                    box(
                        K,
                        fx + tan[0] * cu + nrm[0] * 0.012,
                        fy + tan[1] * cu + nrm[1] * 0.012,
                        w0,
                        abs(tan[0]) * hu + abs(nrm[0]) * 0.014,
                        abs(tan[1]) * hu + abs(nrm[1]) * 0.014,
                        w1 - w0,
                    )
                # a bead border just inside the frame, top and bottom
                inner = m - fw - 0.03
                nb = max(4, round(2 * inner / 0.06))
                for i in range(nb + 1):
                    u = -inner + 2 * inner * i / nb
                    for zz in (bot + fw + 0.03, top - fw - 0.03):
                        bead(
                            K,
                            fx + tan[0] * u + nrm[0] * 0.012,
                            fy + tan[1] * u + nrm[1] * 0.012,
                            zz,
                            0.012,
                        )
                # the medallion, centred, larger on the middle block
                panel_relief(
                    fx,
                    fy,
                    z + hh / 2,
                    (0.62 if k == 2 else 0.54) * w,
                    side,
                    depth=0.05,
                    key=K,
                )
        else:
            # chamfered: the corners cut back from the square, stopped with triangles
            loft(
                K,
                x,
                y,
                [
                    (w, z),
                    (w * 0.95, z + 0.05),
                    (w * 0.84, z + 0.13),
                    (w * 0.84, z + hh - 0.13),
                    (w * 0.95, z + hh - 0.05),
                    (w, z + hh),
                ],
                e=2,
                n=8,
                phase=math.pi / 8,
            )
            # the waist: a fillet with a ring of beads
            loft(
                K,
                x,
                y,
                [
                    (w * 0.86, z + hh * 0.47),
                    (w * 0.9, z + hh * 0.5),
                    (w * 0.86, z + hh * 0.53),
                ],
                e=2,
                n=32,
            )
            bead_ring(K, x, y, w * 0.9, z + hh * 0.5, 0.014, 28 + rnd.randrange(0, 4))
        z += hh
    # --- the capital: the ribbed pot
    loft(
        K,
        x,
        y,
        [
            (w * 0.72, z),
            (w * 0.66, z + 0.10),
            (w * 0.66, z + 0.16),
            (w * 0.84, z + 0.30),
            (w * 0.98, z + 0.44),
            (w * 0.98, z + 0.52),
            (w * 0.74, z + 0.62),
        ],
        e=2,
        n=48,
    )
    for i in range(16):
        a = 2 * math.pi * i / 16
        c, sn = math.cos(a), math.sin(a)
        tube(
            K,
            [
                (x + c * w * 0.68, y + sn * w * 0.68, z + 0.16),
                (x + c * w * 0.88, y + sn * w * 0.88, z + 0.31),
                (x + c * w * 0.99, y + sn * w * 0.99, z + 0.46),
                (x + c * w * 0.76, y + sn * w * 0.76, z + 0.61),
            ],
            [0.012, 0.018, 0.018, 0.01],
            n=6,
        )
    z += 0.62
    # the neck
    loft(K, x, y, [(w * 0.58, z), (w * 0.56, z + 0.1), (w * 0.6, z + 0.14)], e=2, n=40)
    z += 0.14
    # the dish, ribbed with gadroons
    loft(
        K,
        x,
        y,
        [(w * 0.62, z), (w * 0.86, z + 0.1), (w * 1.12, z + 0.2), (w * 1.24, z + 0.26)],
        e=2,
        n=48,
    )
    for i in range(24):
        a = 2 * math.pi * i / 24
        c, sn = math.cos(a), math.sin(a)
        tube(
            K,
            [
                (x + c * w * 0.64, y + sn * w * 0.64, z + 0.01),
                (x + c * w * 0.92, y + sn * w * 0.92, z + 0.12),
                (x + c * w * 1.2, y + sn * w * 1.2, z + 0.24),
            ],
            [0.012, 0.016, 0.01],
            n=6,
        )
    z += 0.26
    # the abacus, with a bead row beneath
    bead_square(K, x, y, w * 1.42, z + 0.02, 0.018, 0.08)
    box(K, x, y, z + 0.03, w * 1.5, w * 1.5, 0.2)
    z += 0.23
    # --- the wave bracket, four arms, each with its flat central band
    arm = w * 2.8
    for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        prism(
            K,
            (x, y, z + bracket_h),
            (ax, ay, 0),
            (-ay, ax, 0),
            taranga_outline(arm, bracket_h, bracket_h * 0.38),
            w * 0.62,
        )
        for sgn in (-1, 1):
            box(
                K,
                x + ax * arm * 0.5 + (-ay) * sgn * (w * 0.62 + 0.008),
                y + ay * arm * 0.5 + ax * sgn * (w * 0.62 + 0.008),
                z + bracket_h * 0.42,
                abs(ax) * arm * 0.45 + abs(ay) * 0.012,
                abs(ay) * arm * 0.45 + abs(ax) * 0.012,
                bracket_h * 0.16,
            )
    return z + bracket_h


def pavilion(cx, cy, nx=4, ny=4, sp=3.3):
    """An open pillared pavilion (mandapa) on a moulded platform, roofed with stone slabs and beams."""
    K = "pstone"
    hx, hy = (nx - 1) * sp / 2, (ny - 1) * sp / 2
    for d, hh in ((2.2, 0.35), (1.9, 0.35), (1.6, 0.3)):
        box(K, cx, cy, -0.3 + 0.0, hx + d, hy + d, hh + 0.3)
    box("path", cx, cy, 0.35, hx + 1.4, hy + 1.4, 0.04)
    top_z = 0
    for i in range(nx):
        for j in range(ny):
            px, py = cx - hx + i * sp, cy - hy + j * sp
            top_z = pillar(px, py, 6.6, seed=i * ny + j)
    # beams (uttiram) carried on the brackets, each with a moulded lower edge
    for i in range(nx):
        prism(
            K,
            (cx - hx + i * sp, cy - hy - 0.6, top_z + 0.42),
            (0, 1, 0),
            (1, 0, 0),
            [(0, 0), (2 * hy + 1.2, 0), (2 * hy + 1.2, -0.42), (0, -0.42)],
            0.28,
        )
    for j in range(ny):
        prism(
            K,
            (cx - hx - 0.6, cy - hy + j * sp, top_z + 0.84),
            (1, 0, 0),
            (0, 1, 0),
            [(0, 0), (2 * hx + 1.2, 0), (2 * hx + 1.2, -0.4), (0, -0.4)],
            0.27,
        )
    # the roof slabs, then the curved dripstone eave (kapota) with its little end-scrolls
    box(K, cx, cy, top_z + 0.84, hx + 1.3, hy + 1.3, 0.3)
    loft(
        K,
        cx,
        cy,
        [
            (hx + 1.3, top_z + 1.14),
            (hx + 1.85, top_z + 1.32),
            (hx + 2.0, top_z + 1.5),
            (hx + 1.92, top_z + 1.62),
            (hx + 1.55, top_z + 1.7),
            (hx + 1.5, top_z + 1.84),
            (hx + 1.1, top_z + 1.9),
        ],
        e=40,
        n=96,
        aspect=(hy + 1.3) / (hx + 1.3),
    )
    # a parapet of small pavilions on the roof, as on the Thanjavur halls
    for i in range(nx + 1):
        u = -hx - 0.8 + i * (2 * hx + 1.6) / nx
        for x, y in ((cx + u, cy - hy - 1.0), (cx + u, cy + hy + 1.0)):
            kuta(x, y, top_z + 1.9, 0.55)
    return top_z


PART = next((a.split("=", 1)[1] for a in argv if a.startswith("part=")), None)
if PART is None:
    top = build()
elif PART == "crown":
    top = crown(0.0, 3.76)
elif PART in ("kuta", "shala"):
    for v in range(3):
        (kuta if PART == "kuta" else shala)(
            (v - 1) * 3.2, 0.0, 0.0, 1.6, *([] if PART == "kuta" else [True])
        )
    top = 2.4
elif PART == "pillar":
    top = pillar(0.0, 0.0, 6.6)
else:
    raise SystemExit(f"unknown part {PART}")
if PART is not None:
    HERO = True
if not HERO:
    birds()
    HALL_TOP = pavilion(0.0, -115.0)
HANGING = []


def hanging_lamp(x, y, top, drop):
    """A thoonga vilakku: a brass chain from the ceiling, a bowl of oil with five
    wicks, and a small finial below; its light is added at dusk."""
    z = top - drop
    for k in range(int(drop / 0.09)):
        zz = top - k * 0.09
        loft(
            "gold", x, y, [(0.012, zz - 0.07), (0.022, zz - 0.035), (0.012, zz)], e=2, n=6
        )
    loft(
        "gold",
        x,
        y,
        [
            (0.01, z - 0.2),
            (0.05, z - 0.16),
            (0.16, z - 0.06),
            (0.2, z),
            (0.17, z + 0.02),
            (0.02, z + 0.03),
        ],
        e=2,
        n=24,
    )
    loft("gold", x, y, [(0.005, z - 0.42), (0.03, z - 0.33), (0.02, z - 0.2)], e=2, n=10)
    for w in range(5):
        a = 2 * math.pi * w / 5
        loft(
            "flame",
            x + 0.15 * math.cos(a),
            y + 0.15 * math.sin(a),
            [(0.012, z + 0.02), (0.02, z + 0.06), (0.001, z + 0.12)],
            e=2,
            n=8,
        )
        HANGING.append((x + 0.15 * math.cos(a), y + 0.15 * math.sin(a), z + 0.08))


def kuthu_vilakku(x, y, z0, h=1.55):
    """A tall brass standing lamp: a stepped round foot, a stem of turned rings and
    bulbs, an oil bowl with five spouts each holding a flame, and a crowning finial."""
    s = h / 1.55
    prof = [
        (0.005, 0),
        (0.24, 0),
        (0.25, 0.02),
        (0.22, 0.05),
        (0.15, 0.08),
        (0.17, 0.11),
        (0.06, 0.16),
        (0.05, 0.3),
        (0.075, 0.34),
        (0.05, 0.38),
        (0.035, 0.6),
        (0.06, 0.66),
        (0.04, 0.72),
        (0.03, 0.95),
        (0.055, 1.0),
        (0.04, 1.06),
        (0.05, 1.12),
        (0.03, 1.16),
    ]
    loft("gold", x, y, [(r * s, z0 + zz * s) for (r, zz) in prof], e=2, n=40)
    zb = z0 + 1.16 * s
    loft(
        "gold",
        x,
        y,
        [
            (0.03 * s, zb),
            (0.12 * s, zb + 0.02 * s),
            (0.2 * s, zb + 0.06 * s),
            (0.21 * s, zb + 0.09 * s),
            (0.19 * s, zb + 0.09 * s),
            (0.02 * s, zb + 0.05 * s),
        ],
        e=2,
        n=40,
    )
    for w in range(5):
        a = 2 * math.pi * w / 5 + 0.3
        sx, sy = x + 0.23 * s * math.cos(a), y + 0.23 * s * math.sin(a)
        tube(
            "gold",
            [
                Vector(
                    (
                        x + 0.17 * s * math.cos(a),
                        y + 0.17 * s * math.sin(a),
                        zb + 0.07 * s,
                    )
                ),
                Vector((sx, sy, zb + 0.085 * s)),
            ],
            [0.02 * s, 0.012 * s],
            n=8,
        )
        loft(
            "flame",
            sx,
            sy,
            [
                (0.006, zb + 0.09 * s),
                (0.016, zb + 0.12 * s),
                (0.01, zb + 0.16 * s),
                (0.001, zb + 0.21 * s),
            ],
            e=2,
            n=8,
        )
        HANGING.append((sx, sy, zb + 0.14 * s))
    zf = zb + 0.09 * s
    loft(
        "gold",
        x,
        y,
        [
            (0.02 * s, zf),
            (0.03 * s, zf + 0.12 * s),
            (0.06 * s, zf + 0.18 * s),
            (0.035 * s, zf + 0.24 * s),
            (0.045 * s, zf + 0.3 * s),
            (0.001, zf + 0.42 * s),
        ],
        e=2,
        n=24,
    )


if not HERO:
    # in front of the pillar, where the hall camera sees it (pass 8 fault)
    kuthu_vilakku(-2.6, -106.8, 0.068)


if not HERO:
    for hx_ in (-3.3, 0.0, 3.3):
        for hy_ in (-116.65, -113.35):
            hanging_lamp(hx_, hy_, HALL_TOP + 0.42, 3.2 + 0.25 * abs(hx_) / 3.3)
    courtyard()
    grove()
    mandapa(-16.5, -78, 11)
    lamp_pillar(-30, -98, 11.5)
LAMP_SPOTS = []


def lamp_row(x0, x1, y, z, step):
    """Small brass oil lamps in a row along a step, each with its flame."""
    n = int((x1 - x0) / step) + 1
    for i in range(n):
        x = x0 + i * step
        loft(
            "gold",
            x,
            y,
            [
                (0.02, z),
                (0.07, z + 0.01),
                (0.09, z + 0.05),
                (0.06, z + 0.07),
                (0.075, z + 0.09),
            ],
            e=2,
            n=12,
        )
        loft(
            "flame",
            x,
            y,
            [(0.004, z + 0.085), (0.025, z + 0.12), (0.015, z + 0.17), (0.002, z + 0.23)],
            e=2,
            n=8,
        )
        LAMP_SPOTS.append((x, y, z + 0.16))


MESHES["rice"] = bmesh.new()


if not HERO:
    lamp_row(-6.0, 6.0, -105.2, 0.4, 1.0)  # the front step of the hall
    lamp_row(-13.0, 13.0, -18.4, 0.35, 1.3)  # along the temple's base
    grounds()
MESHES["pave"] = bmesh.new()


def paving(x0, x1, y0, y1, top, seed):
    """Dressed stone slabs laid in courses, each its own: a length and a course width
    from the quarry, a few millimetres high or low, a hair out of level, a chamfered
    edge, and its own tone. Water then lies in the joints and on the low slabs, and a
    reflection breaks at every edge, as it does on real paving."""
    import random

    rnd = random.Random(seed)  # noqa: S311 - shape variation, not security
    bm = MESHES["pave"]
    tone_layer = bm.loops.layers.float_color.new("slab")
    y = y0
    while y < y1:
        w = rnd.choice((0.6, 0.75, 0.9))
        x = x0 - rnd.uniform(0, 1.2)
        while x < x1:
            ln = rnd.uniform(0.9, 1.7)
            ax, bx = max(x, x0) + 0.004, min(x + ln, x1) - 0.004
            ay, by = y + 0.004, min(y + w, y1) - 0.004
            if bx - ax > 0.1 and by - ay > 0.1:
                h = top + rnd.uniform(-0.004, 0.003)
                tx, ty = rnd.uniform(-0.0025, 0.0025), rnd.uniform(-0.0025, 0.0025)
                c = 0.012

                def zt(
                    px, py, d=0.0, h=h, tx=tx, ty=ty, cx=(ax + bx) / 2, cy=(ay + by) / 2
                ):
                    return h - d + tx * (px - cx) + ty * (py - cy)

                bot = [
                    bm.verts.new((px, py, top - 0.08))
                    for (px, py) in ((ax, ay), (bx, ay), (bx, by), (ax, by))
                ]
                out = [
                    bm.verts.new((px, py, zt(px, py, 0.007)))
                    for (px, py) in ((ax, ay), (bx, ay), (bx, by), (ax, by))
                ]
                inn = [
                    bm.verts.new((px, py, zt(px, py)))
                    for (px, py) in (
                        (ax + c, ay + c),
                        (bx - c, ay + c),
                        (bx - c, by - c),
                        (ax + c, by - c),
                    )
                ]
                faces = [bm.faces.new(inn)]
                for i in range(4):
                    j = (i + 1) % 4
                    faces.append(bm.faces.new((out[i], out[j], inn[j], inn[i])))
                    faces.append(bm.faces.new((bot[i], bot[j], out[j], out[i])))
                tone = rnd.gauss(1.0, 0.07) * (0.86 if rnd.random() < 0.12 else 1.0)
                for f in faces:
                    for loop in f.loops:
                        loop[tone_layer] = (
                            tone,
                            tone * rnd.uniform(0.985, 1.015),
                            tone,
                            1.0,
                        )
            x += ln
        y += w


if not HERO:
    paving(-30.0, 30.0, -108.6, -20.0, 0.068, 31)  # the courtyard up to the tower
    paving(-6.3, 6.3, -121.3, -108.7, 0.402, 32)  # the hall's own floor
if not HERO:
    grass_blades(
        (-72.0, -138.0),
        math.atan2(138.0, 102.0),
        keep_out=((-35, -115, 35, 15), (-41, -151, 41, -109), (-71, -35, -9, 23)),
    )
if not HERO and len(argv) > 4 and argv[4] == "close":
    grass_blades(
        (-34.0, -44.0),
        math.atan2(29.0, 32.0),
        count=90000,
        seed=5,
        spread=0.9,
        reach=30,
        keep_out=((-71, -35, -9, 23), (-30, -35, 20, -16)),
    )


# ---------- materials ----------
def mat_stone(name, base_a, base_b, rough=0.82):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.9
    noise.inputs["Detail"].default_value = 9
    noise.inputs["Roughness"].default_value = 0.62
    L.new(pos.outputs["Position"], noise.inputs["Vector"])
    # weathering: large dark patches where water and lichen sit
    lich = N.new("ShaderNodeTexNoise")
    lich.inputs["Scale"].default_value = 0.22
    lich.inputs["Detail"].default_value = 6
    L.new(pos.outputs["Position"], lich.inputs["Vector"])
    lr = N.new("ShaderNodeMapRange")
    lr.inputs["From Min"].default_value = 0.5
    lr.inputs["From Max"].default_value = 0.68
    lr.inputs["To Min"].default_value = 1.0
    lr.inputs["To Max"].default_value = 0.55
    L.new(lich.outputs["Fac"], lr.inputs["Value"])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*base_b, 1)
    ramp.color_ramp.elements[1].color = (*base_a, 1)
    L.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # rain streaks: noise stretched downwards
    mapn = N.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (3.0, 3.0, 0.15)
    L.new(pos.outputs["Position"], mapn.inputs["Vector"])
    streak = N.new("ShaderNodeTexNoise")
    streak.inputs["Scale"].default_value = 2.0
    streak.inputs["Detail"].default_value = 3
    L.new(mapn.outputs["Vector"], streak.inputs["Vector"])
    sramp = N.new("ShaderNodeMapRange")
    sramp.inputs["From Min"].default_value = 0.45
    sramp.inputs["From Max"].default_value = 0.7
    sramp.inputs["To Min"].default_value = 1.0
    sramp.inputs["To Max"].default_value = 0.72
    L.new(streak.outputs["Fac"], sramp.inputs["Value"])
    # crevices darken: ambient occlusion
    ao = N.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 1.2
    ao.samples = 8
    aor = N.new("ShaderNodeMapRange")
    aor.inputs["From Min"].default_value = 0.0
    aor.inputs["From Max"].default_value = 1.0
    aor.inputs["To Min"].default_value = 0.28
    aor.inputs["To Max"].default_value = 1.0
    L.new(ao.outputs["AO"], aor.inputs["Value"])
    m1 = N.new("ShaderNodeMix")
    m1.data_type = "RGBA"
    m1.blend_type = "MULTIPLY"
    m1.inputs["Factor"].default_value = 1.0
    L.new(ramp.outputs["Color"], m1.inputs["A"])
    comb = N.new("ShaderNodeMath")
    comb.operation = "MULTIPLY"
    L.new(sramp.outputs["Result"], comb.inputs[0])
    L.new(aor.outputs["Result"], comb.inputs[1])
    comb2 = N.new("ShaderNodeMath")
    comb2.operation = "MULTIPLY"
    L.new(comb.outputs["Value"], comb2.inputs[0])
    L.new(lr.outputs["Result"], comb2.inputs[1])
    # granite blocks: courses about 0.6 m high, joints staggered, as the temple was laid dry
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(pos.outputs["Position"], sep.inputs["Vector"])
    hsum = N.new("ShaderNodeMath")
    hsum.operation = "ADD"
    L.new(sep.outputs["X"], hsum.inputs[0])
    L.new(sep.outputs["Y"], hsum.inputs[1])
    bv = N.new("ShaderNodeCombineXYZ")
    L.new(hsum.outputs["Value"], bv.inputs["X"])
    L.new(sep.outputs["Z"], bv.inputs["Y"])
    brick = N.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = 1.45
    brick.inputs["Row Height"].default_value = 0.62
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Mortar Smooth"].default_value = 0.3
    brick.inputs["Color1"].default_value = (1, 1, 1, 1)
    brick.inputs["Color2"].default_value = (0.82, 0.82, 0.82, 1)
    brick.inputs["Bias"].default_value = 0.0
    L.new(bv.outputs["Vector"], brick.inputs["Vector"])
    joint = N.new("ShaderNodeMapRange")
    joint.inputs["To Min"].default_value = 1.0
    joint.inputs["To Max"].default_value = 0.6
    L.new(brick.outputs["Fac"], joint.inputs["Value"])
    perblock = N.new("ShaderNodeMix")
    perblock.data_type = "RGBA"
    perblock.blend_type = "MULTIPLY"
    perblock.inputs["Factor"].default_value = 1.0
    L.new(comb2.outputs["Value"], perblock.inputs["A"])
    L.new(brick.outputs["Color"], perblock.inputs["B"])
    blk = N.new("ShaderNodeMath")
    blk.operation = "MULTIPLY"
    sepc = N.new("ShaderNodeSeparateColor")
    L.new(perblock.outputs["Result"], sepc.inputs["Color"])
    L.new(sepc.outputs["Red"], blk.inputs[0])
    L.new(joint.outputs["Result"], blk.inputs[1])
    L.new(blk.outputs["Value"], m1.inputs["B"])
    L.new(m1.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    # surface: fine grain and chipped edges, and the block joints pressed in
    bn = N.new("ShaderNodeTexNoise")
    bn.inputs["Scale"].default_value = 28
    bn.inputs["Detail"].default_value = 10
    vor = N.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 6
    L.new(pos.outputs["Position"], bn.inputs["Vector"])
    L.new(pos.outputs["Position"], vor.inputs["Vector"])
    add0 = N.new("ShaderNodeMath")
    add0.operation = "ADD"
    L.new(bn.outputs["Fac"], add0.inputs[0])
    L.new(vor.outputs["Distance"], add0.inputs[1])
    add = N.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    L.new(brick.outputs["Fac"], add.inputs[0])
    add.inputs[1].default_value = -1.2
    L.new(add0.outputs["Value"], add.inputs[2])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.04
    L.new(add.outputs["Value"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def mat_simple(name, color, rough, metal=0.0):
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def mat_floor():
    m = bpy.data.materials.new("floor")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    br = N.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 0.6
    br.inputs["Color1"].default_value = (0.42, 0.2, 0.11, 1)
    br.inputs["Color2"].default_value = (0.5, 0.28, 0.15, 1)
    br.inputs["Mortar"].default_value = (0.22, 0.12, 0.07, 1)
    br.inputs["Mortar Size"].default_value = 0.01
    br.offset = 0.0
    br.squash = 1.0
    br.inputs["Brick Width"].default_value = 1.0
    br.inputs["Row Height"].default_value = 1.0
    pos = N.new("ShaderNodeNewGeometry")
    L.new(pos.outputs["Position"], br.inputs["Vector"])
    L.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.58
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    L.new(br.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_foliage(name, c0, c1, trans, trans_amount):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.6
    nz.inputs["Detail"].default_value = 5
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (*c0, 1)
    cr.color_ramp.elements[1].color = (*c1, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"])
    L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.5
    tr = N.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (*trans, 1)
    mix = N.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = trans_amount
    L.new(b.outputs["BSDF"], mix.inputs[1])
    L.new(tr.outputs["BSDF"], mix.inputs[2])
    L.new(mix.outputs["Shader"], N["Material Output"].inputs["Surface"])
    return m


def mat_banana_leaf():
    m = bpy.data.materials.new("banana_leaf")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    uv = N.new("ShaderNodeUVMap")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(uv.outputs["UV"], sep.inputs["Vector"])
    # veins: lines of constant (u * 140 + v * 9), so they leave the midrib at a slant
    vu = N.new("ShaderNodeMath")
    vu.operation = "MULTIPLY_ADD"
    vu.inputs[1].default_value = 140.0
    vv = N.new("ShaderNodeMath")
    vv.operation = "MULTIPLY"
    vv.inputs[1].default_value = 9.0
    L.new(sep.outputs["Y"], vv.inputs[0])
    L.new(sep.outputs["X"], vu.inputs[0])
    L.new(vv.outputs["Value"], vu.inputs[2])
    sw = N.new("ShaderNodeMath")
    sw.operation = "SINE"
    L.new(vu.outputs["Value"], sw.inputs[0])
    vein = N.new("ShaderNodeMapRange")
    vein.inputs["From Min"].default_value = 0.6
    vein.inputs["From Max"].default_value = 1.0
    L.new(sw.outputs["Value"], vein.inputs["Value"])
    # colour across the blade: pale by the midrib, deep green, a dry margin
    across = N.new("ShaderNodeValToRGB")
    els = across.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.3, 0.38, 0.1, 1)
    els[1].position, els[1].color = 0.12, (0.09, 0.2, 0.03, 1)
    e = els.new(0.9)
    e.color = (0.11, 0.22, 0.035, 1)
    e = els.new(0.985)
    e.color = (0.34, 0.26, 0.08, 1)
    L.new(sep.outputs["Y"], across.inputs["Fac"])
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 2.5
    nz.inputs["Detail"].default_value = 6
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    mot = N.new("ShaderNodeMapRange")
    mot.inputs["To Min"].default_value = 0.75
    mot.inputs["To Max"].default_value = 1.15
    L.new(nz.outputs["Fac"], mot.inputs["Value"])
    c1 = N.new("ShaderNodeMix")
    c1.data_type = "RGBA"
    c1.blend_type = "MULTIPLY"
    c1.inputs["Factor"].default_value = 1.0
    L.new(across.outputs["Color"], c1.inputs["A"])
    L.new(mot.outputs["Result"], c1.inputs["B"])
    c2 = N.new("ShaderNodeMix")
    c2.data_type = "RGBA"
    c2.blend_type = "MULTIPLY"
    c2.inputs["B"].default_value = (0.78, 0.82, 0.7, 1)
    L.new(vein.outputs["Result"], c2.inputs["Factor"])
    L.new(c1.outputs["Result"], c2.inputs["A"])
    L.new(c2.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.42
    try:
        b.inputs["Coat Weight"].default_value = 0.25
        b.inputs["Coat Roughness"].default_value = 0.3
    except KeyError:
        pass
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.002
    L.new(vein.outputs["Result"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    tr = N.new("ShaderNodeBsdfTranslucent")
    tcol = N.new("ShaderNodeMix")
    tcol.data_type = "RGBA"
    tcol.blend_type = "MULTIPLY"
    tcol.inputs["Factor"].default_value = 1.0
    L.new(c2.outputs["Result"], tcol.inputs["A"])
    tcol.inputs["B"].default_value = (2.4, 2.6, 1.2, 1)
    L.new(tcol.outputs["Result"], tr.inputs["Color"])
    mix = N.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.42
    L.new(b.outputs["BSDF"], mix.inputs[1])
    L.new(tr.outputs["BSDF"], mix.inputs[2])
    L.new(mix.outputs["Shader"], N["Material Output"].inputs["Surface"])
    return m


def mat_pseudostem():
    m = bpy.data.materials.new("pseudostem")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    # sheath edges: long vertical bands that wrap round the stem
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (14.0, 14.0, 0.6)
    L.new(pos.outputs["Position"], mp.inputs["Vector"])
    wv = N.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "X"
    wv.inputs["Distortion"].default_value = 2.0
    L.new(mp.outputs["Vector"], wv.inputs["Vector"])
    blot = N.new("ShaderNodeTexNoise")
    blot.inputs["Scale"].default_value = 6.0
    blot.inputs["Detail"].default_value = 8
    L.new(pos.outputs["Position"], blot.inputs["Vector"])
    br = N.new("ShaderNodeValToRGB")
    e = br.color_ramp.elements
    e[0].position, e[0].color = 0.45, (0.2, 0.3, 0.08, 1)
    e[1].position, e[1].color = 0.62, (0.16, 0.07, 0.05, 1)
    L.new(blot.outputs["Fac"], br.inputs["Fac"])
    shade = N.new("ShaderNodeMix")
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["Factor"].default_value = 0.35
    L.new(br.outputs["Color"], shade.inputs["A"])
    L.new(wv.outputs["Color"], shade.inputs["B"])
    L.new(shade.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.45
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    L.new(wv.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_leaf():
    m = bpy.data.materials.new("leaf")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.7
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.05, 0.1, 0.02, 1)
    cr.color_ramp.elements[1].color = (0.2, 0.26, 0.06, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"])
    L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.55
    tr = N.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (0.35, 0.42, 0.08, 1)
    mix = N.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.35
    out = N["Material Output"]
    L.new(b.outputs["BSDF"], mix.inputs[1])
    L.new(tr.outputs["BSDF"], mix.inputs[2])
    L.new(mix.outputs["Shader"], out.inputs["Surface"])
    return m


def mat_trunk():
    m = bpy.data.materials.new("trunk")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    wave = N.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 0.35
    wave.inputs["Distortion"].default_value = 1.5
    L.new(pos.outputs["Position"], wave.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.12, 0.1, 0.08, 1)
    cr.color_ramp.elements[1].color = (0.32, 0.27, 0.21, 1)
    L.new(wave.outputs["Fac"], cr.inputs["Fac"])
    L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    L.new(wave.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_grass():
    m = bpy.data.materials.new("grass")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.25
    nz.inputs["Detail"].default_value = 10
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.05, 0.09, 0.015, 1)
    cr.color_ramp.elements[1].color = (0.15, 0.18, 0.045, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"])
    L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    fine = N.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 60
    L.new(pos.outputs["Position"], fine.inputs["Vector"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    L.new(fine.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_blade():
    m = bpy.data.materials.new("blade")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.6
    nz.inputs["Detail"].default_value = 4
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.04, 0.09, 0.012, 1)
    cr.color_ramp.elements[1].color = (0.2, 0.24, 0.05, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"])
    L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.6
    b.inputs["Subsurface Weight"].default_value = 0.2
    return m


def mat_path():
    m = bpy.data.materials.new("path")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    br = N.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 0.35
    br.inputs["Color1"].default_value = (0.36, 0.3, 0.24, 1)
    br.inputs["Color2"].default_value = (0.26, 0.21, 0.17, 1)
    br.inputs["Mortar"].default_value = (0.1, 0.08, 0.06, 1)
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Bias"].default_value = 0.0
    L.new(pos.outputs["Position"], br.inputs["Vector"])
    L.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.7
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.3
    L.new(br.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_flame():
    m = bpy.data.materials.new("flame")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.78, 0.45, 1)
    em.inputs["Strength"].default_value = 22 if GRADE != "blue" else 6
    L.new(em.outputs["Emission"], N["Material Output"].inputs["Surface"])
    return m


TEX = __import__("os").path.join(__import__("os").path.dirname(__file__), "tex")


WET_MASKS = {}


def mat_scan(
    name,
    folder,
    size_m,
    tint=(1, 1, 1),
    weather=True,
    normal_strength=1.0,
    blend=0.25,
    displace=0.0,
    wet=False,
):
    """A scanned PBR material (CC0, Poly Haven), box-projected in world space at its real size,
    with ambient-occlusion grime, rain streaks and lichen laid over it when weather=True."""
    import os

    m = bpy.data.materials.new(name)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    s = 1.0 / size_m
    mp.inputs["Scale"].default_value = (s, s, s)
    oi = N.new("ShaderNodeObjectInfo")
    rnd = N.new("ShaderNodeVectorMath")
    rnd.operation = "SCALE"
    L.new(oi.outputs["Random"], rnd.inputs["Vector"])
    rnd.inputs["Scale"].default_value = 53.0
    addv = N.new("ShaderNodeVectorMath")
    addv.operation = "ADD"
    L.new(tc.outputs["Object"], addv.inputs[0])
    L.new(rnd.outputs["Vector"], addv.inputs[1])
    L.new(addv.outputs["Vector"], mp.inputs["Vector"])

    def img(file, non_color):
        t = N.new("ShaderNodeTexImage")
        t.projection = "BOX"
        t.projection_blend = blend
        hi = os.path.join(TEX, folder, "4k", file)
        t.image = bpy.data.images.load(
            hi
            if (os.path.exists(hi) and QUALITY == "final")
            else os.path.join(TEX, folder, file)
        )
        if non_color:
            t.image.colorspace_settings.name = "Non-Color"
        L.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    dif, nor, rgh = (
        img("Diffuse.jpg", False),
        img("nor_gl.jpg", True),
        img("Rough.jpg", True),
    )
    # break the repeat: the same scan, scaled and turned, faded in by a soft mask
    mp2 = N.new("ShaderNodeMapping")
    mp2.inputs["Scale"].default_value = (s * 0.71, s * 0.71, s * 0.71)
    mp2.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(90))
    mp2.inputs["Location"].default_value = (0.37, 0.61, 0.13)
    L.new(addv.outputs["Vector"], mp2.inputs["Vector"])
    dif2 = N.new("ShaderNodeTexImage")
    dif2.projection = "BOX"
    dif2.projection_blend = blend
    dif2.image = dif.image
    L.new(mp2.outputs["Vector"], dif2.inputs["Vector"])
    tmask = N.new("ShaderNodeTexNoise")
    tmask.inputs["Scale"].default_value = 0.09
    tmask.inputs["Detail"].default_value = 2
    L.new(addv.outputs["Vector"], tmask.inputs["Vector"])
    tmr = N.new("ShaderNodeMapRange")
    tmr.inputs["From Min"].default_value = 0.42
    tmr.inputs["From Max"].default_value = 0.58
    L.new(tmask.outputs["Fac"], tmr.inputs["Value"])
    dmix = N.new("ShaderNodeMix")
    dmix.data_type = "RGBA"
    L.new(tmr.outputs["Result"], dmix.inputs["Factor"])
    L.new(dif.outputs["Color"], dmix.inputs["A"])
    L.new(dif2.outputs["Color"], dmix.inputs["B"])
    col = N.new("ShaderNodeMix")
    col.data_type = "RGBA"
    col.blend_type = "MULTIPLY"
    col.inputs["Factor"].default_value = 1.0
    bc = N.new("ShaderNodeBrightContrast")
    bc.inputs["Bright"].default_value = 0.04
    bc.inputs["Contrast"].default_value = -0.28
    L.new(dmix.outputs["Result"], bc.inputs["Color"])
    L.new(bc.outputs["Color"], col.inputs["A"])
    col.inputs["B"].default_value = (*tint, 1)
    last = col.outputs["Result"]
    if weather:
        pos = N.new("ShaderNodeNewGeometry")
        ao = N.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = 1.0
        ao.samples = 8
        aor = N.new("ShaderNodeMapRange")
        aor.inputs["To Min"].default_value = 0.3
        L.new(ao.outputs["AO"], aor.inputs["Value"])
        mapn = N.new("ShaderNodeMapping")
        mapn.inputs["Scale"].default_value = (3.0, 3.0, 0.12)
        L.new(pos.outputs["Position"], mapn.inputs["Vector"])
        st = N.new("ShaderNodeTexNoise")
        st.inputs["Scale"].default_value = 2.2
        st.inputs["Detail"].default_value = 4
        L.new(mapn.outputs["Vector"], st.inputs["Vector"])
        sr = N.new("ShaderNodeMapRange")
        sr.inputs["From Min"].default_value = 0.48
        sr.inputs["From Max"].default_value = 0.72
        sr.inputs["To Min"].default_value = 1.0
        sr.inputs["To Max"].default_value = 0.6
        L.new(st.outputs["Fac"], sr.inputs["Value"])
        li = N.new("ShaderNodeTexNoise")
        li.inputs["Scale"].default_value = 0.25
        li.inputs["Detail"].default_value = 6
        L.new(pos.outputs["Position"], li.inputs["Vector"])
        lr = N.new("ShaderNodeMapRange")
        lr.inputs["From Min"].default_value = 0.52
        lr.inputs["From Max"].default_value = 0.7
        lr.inputs["To Min"].default_value = 1.0
        lr.inputs["To Max"].default_value = 0.62
        L.new(li.outputs["Fac"], lr.inputs["Value"])
        f1 = N.new("ShaderNodeMath")
        f1.operation = "MULTIPLY"
        L.new(aor.outputs["Result"], f1.inputs[0])
        L.new(sr.outputs["Result"], f1.inputs[1])
        f2a = N.new("ShaderNodeMath")
        f2a.operation = "MULTIPLY"
        L.new(f1.outputs["Value"], f2a.inputs[0])
        L.new(lr.outputs["Result"], f2a.inputs[1])
        # faces that look at the sky hold water: dark lichen in patches
        sepn = N.new("ShaderNodeSeparateXYZ")
        L.new(pos.outputs["Normal"], sepn.inputs["Vector"])
        up = N.new("ShaderNodeMapRange")
        up.inputs["From Min"].default_value = 0.45
        up.inputs["From Max"].default_value = 0.95
        L.new(sepn.outputs["Z"], up.inputs["Value"])
        pn = N.new("ShaderNodeTexNoise")
        pn.inputs["Scale"].default_value = 1.8
        pn.inputs["Detail"].default_value = 8
        pn.inputs["Roughness"].default_value = 0.7
        L.new(pos.outputs["Position"], pn.inputs["Vector"])
        pr = N.new("ShaderNodeMapRange")
        pr.inputs["From Min"].default_value = 0.42
        pr.inputs["From Max"].default_value = 0.62
        L.new(pn.outputs["Fac"], pr.inputs["Value"])
        upm = N.new("ShaderNodeMath")
        upm.operation = "MULTIPLY"
        L.new(up.outputs["Result"], upm.inputs[0])
        L.new(pr.outputs["Result"], upm.inputs[1])
        upd = N.new("ShaderNodeMapRange")
        upd.inputs["To Min"].default_value = 1.0
        upd.inputs["To Max"].default_value = 0.6
        L.new(upm.outputs["Value"], upd.inputs["Value"])
        # long monsoon drip streaks: thin vertical noise, strongest a little below each course
        mapd = N.new("ShaderNodeMapping")
        mapd.inputs["Scale"].default_value = (9.0, 9.0, 0.35)
        L.new(pos.outputs["Position"], mapd.inputs["Vector"])
        dn = N.new("ShaderNodeTexNoise")
        dn.inputs["Scale"].default_value = 3.0
        dn.inputs["Detail"].default_value = 2
        L.new(mapd.outputs["Vector"], dn.inputs["Vector"])
        dr = N.new("ShaderNodeMapRange")
        dr.inputs["From Min"].default_value = 0.55
        dr.inputs["From Max"].default_value = 0.75
        dr.inputs["To Min"].default_value = 1.0
        dr.inputs["To Max"].default_value = 0.76
        L.new(dn.outputs["Fac"], dr.inputs["Value"])
        f2b = N.new("ShaderNodeMath")
        f2b.operation = "MULTIPLY"
        L.new(f2a.outputs["Value"], f2b.inputs[0])
        L.new(upd.outputs["Result"], f2b.inputs[1])
        f2 = N.new("ShaderNodeMath")
        f2.operation = "MULTIPLY"
        L.new(f2b.outputs["Value"], f2.inputs[0])
        L.new(dr.outputs["Result"], f2.inputs[1])
        g = N.new("ShaderNodeMix")
        g.data_type = "RGBA"
        g.blend_type = "MULTIPLY"
        g.inputs["Factor"].default_value = 1.0
        L.new(last, g.inputs["A"])
        L.new(f2.outputs["Value"], g.inputs["B"])
        last = g.outputs["Result"]
    if weather:
        bev = N.new("ShaderNodeBevel")
        bev.samples = 6
        bev.inputs["Radius"].default_value = 0.035
        geo2 = N.new("ShaderNodeNewGeometry")
        dot = N.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        L.new(bev.outputs["Normal"], dot.inputs[0])
        L.new(geo2.outputs["Normal"], dot.inputs[1])
        edge = N.new("ShaderNodeMapRange")
        edge.inputs["From Min"].default_value = 0.995
        edge.inputs["From Max"].default_value = 0.93
        L.new(dot.outputs["Value"], edge.inputs["Value"])
        wear = N.new("ShaderNodeMix")
        wear.data_type = "RGBA"
        wear.blend_type = "SCREEN"
        L.new(edge.outputs["Result"], wear.inputs["Factor"])
        L.new(last, wear.inputs["A"])
        wear.inputs["B"].default_value = (0.22, 0.2, 0.17, 1)
        last = wear.outputs["Result"]
    L.new(last, b.inputs["Base Color"])
    L.new(rgh.outputs["Color"], b.inputs["Roughness"])
    if wet:
        # After a monsoon shower: the paving darkens as it soaks, and water stands
        # in its low places, mirror-smooth, reflecting the tower and the lamps.
        gw = N.new("ShaderNodeNewGeometry")
        pz = N.new("ShaderNodeTexNoise")
        pz.inputs["Scale"].default_value = 0.22
        pz.inputs["Detail"].default_value = 7
        pz.inputs["Roughness"].default_value = 0.62
        L.new(gw.outputs["Position"], pz.inputs["Vector"])
        hgt_w = img("Displacement.png", True)
        sumw = N.new("ShaderNodeMath")
        sumw.operation = "MULTIPLY_ADD"
        sumw.inputs[1].default_value = -0.35
        L.new(hgt_w.outputs["Color"], sumw.inputs[0])
        L.new(pz.outputs["Fac"], sumw.inputs[2])
        pud = N.new("ShaderNodeMapRange")
        pud.inputs["From Min"].default_value = 0.31
        pud.inputs["From Max"].default_value = 0.35
        L.new(sumw.outputs["Value"], pud.inputs["Value"])
        damp = N.new("ShaderNodeMapRange")
        damp.inputs["From Min"].default_value = 0.2
        damp.inputs["From Max"].default_value = 0.42
        L.new(sumw.outputs["Value"], damp.inputs["Value"])
        dk = N.new("ShaderNodeMix")
        dk.data_type = "RGBA"
        dk.blend_type = "MULTIPLY"
        L.new(damp.outputs["Result"], dk.inputs["Factor"])
        L.new(b.inputs["Base Color"].links[0].from_socket, dk.inputs["A"])
        dk.inputs["B"].default_value = (0.62, 0.6, 0.58, 1)
        L.new(dk.outputs["Result"], b.inputs["Base Color"])
        rmix = N.new("ShaderNodeMix")
        rmix.data_type = "FLOAT"
        L.new(pud.outputs["Result"], rmix.inputs["Factor"])
        rdamp = N.new("ShaderNodeMath")
        rdamp.operation = "MULTIPLY"
        rdamp.inputs[1].default_value = 0.85
        L.new(rgh.outputs["Color"], rdamp.inputs[0])
        L.new(rdamp.outputs["Value"], rmix.inputs["A"])
        rmix.inputs["B"].default_value = 0.02
        L.new(rmix.outputs["Result"], b.inputs["Roughness"])
        WET_MASKS[name] = (N, L, pud)
    nm = N.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = normal_strength
    L.new(nor.outputs["Color"], nm.inputs["Color"])
    L.new(nm.outputs["Normal"], b.inputs["Normal"])
    if wet:
        # standing water is flat: the stone's relief vanishes under it
        flat = N.new("ShaderNodeNewGeometry")
        nmix = N.new("ShaderNodeMix")
        nmix.data_type = "VECTOR"
        L.new(WET_MASKS[name][2].outputs["Result"], nmix.inputs["Factor"])
        L.new(nm.outputs["Normal"], nmix.inputs[4])
        L.new(flat.outputs["Normal"], nmix.inputs[5])
        L.new(nmix.outputs[1], b.inputs["Normal"])
    if displace > 0:
        hgt = img("Displacement.png", True)
        dn = N.new("ShaderNodeDisplacement")
        dn.inputs["Midlevel"].default_value = 0.5
        dn.inputs["Scale"].default_value = displace
        L.new(hgt.outputs["Color"], dn.inputs["Height"])
        L.new(dn.outputs["Displacement"], N["Material Output"].inputs["Displacement"])
        m.displacement_method = "BOTH"
        m.max_vertex_displacement = displace * 1.2
    return m


def mat_granite(name, warm=1.0):
    """Tamil Nadu granite, made, not scanned: grains of biotite, feldspar and quartz in their
    proportions, iron staining, chisel tooling, grime in the hollows, and edges polished by hands."""
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    geo = N.new("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]

    def voronoi(scale, out="Color"):
        v = N.new("ShaderNodeTexVoronoi")
        v.voronoi_dimensions = "3D"
        v.inputs["Scale"].default_value = scale
        v.inputs["Randomness"].default_value = 1.0
        L.new(pos, v.inputs["Vector"])
        return v.outputs[out]

    def noise(scale, detail=4.0, rough=0.55):
        n = N.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        L.new(pos, n.inputs["Vector"])
        return n.outputs["Fac"]

    def ramp(src, stops, constant=False):
        r = N.new("ShaderNodeValToRGB")
        if constant:
            r.color_ramp.interpolation = "CONSTANT"
        els = r.color_ramp.elements
        els[0].position, els[0].color = stops[0][0], (*stops[0][1], 1)
        els[1].position, els[1].color = stops[1][0], (*stops[1][1], 1)
        for p_, c_ in stops[2:]:
            e = els.new(p_)
            e.color = (*c_, 1)
        L.new(src, r.inputs["Fac"])
        return r.outputs["Color"]

    def bw(src):
        g = N.new("ShaderNodeRGBToBW")
        L.new(src, g.inputs["Color"])
        return g.outputs["Val"]

    def mix(a, b_, fac, mode="MIX"):
        x = N.new("ShaderNodeMix")
        x.data_type = "RGBA"
        x.blend_type = mode
        if isinstance(fac, float):
            x.inputs["Factor"].default_value = fac
        else:
            L.new(fac, x.inputs["Factor"])
        for sock, v in (("A", a), ("B", b_)):
            if isinstance(v, tuple):
                x.inputs[sock].default_value = (*v, 1)
            else:
                L.new(v, x.inputs[sock])
        return x.outputs["Result"]

    w = warm

    def channel(src):
        # one channel of a cell's random colour is uniform over 0..1; a grey of all
        # three bunches near the middle and starves the black and white grains
        sp = N.new("ShaderNodeSeparateColor")
        L.new(src, sp.inputs["Color"])
        return sp.outputs["Red"]

    # salt and pepper: black biotite, grey quartz, off-white and faintly pink feldspar
    grains = ramp(
        channel(voronoi(320)),
        [
            (0.0, (0.022, 0.021, 0.02)),
            (0.24, (0.27, 0.265, 0.26)),
            (0.52, (0.55, 0.53, 0.5)),
            (0.78, (0.6 * w, 0.5, 0.47)),
            (0.9, (0.74, 0.73, 0.7)),
        ],
        constant=True,
    )
    fine = ramp(
        channel(voronoi(950)),
        [(0.0, (0.03, 0.03, 0.03)), (0.3, (0.36, 0.35, 0.34)), (0.65, (0.62, 0.6, 0.57))],
        constant=True,
    )
    col = mix(grains, fine, 0.4)
    # a thousand years of air, soot and hands: a warm grey patina over the grain
    pat = ramp(noise(1.1, 6, 0.6), [(0.35, (0.5, 0.47, 0.43)), (0.7, (0.78, 0.72, 0.64))])
    col = mix(col, pat, 1.0, "MULTIPLY")
    # the mass of the stone: broad warm and cool zones, and iron staining in clouds
    zone = ramp(noise(0.35, 3), [(0.3, (0.6, 0.58, 0.57)), (0.7, (0.8, 0.74, 0.66))])
    col = mix(col, zone, 1.0, "MULTIPLY")
    stain = ramp(noise(1.6, 6, 0.65), [(0.55, (0, 0, 0)), (0.72, (1, 1, 1))])
    col = mix(col, (0.36 * w, 0.24, 0.15), bw(stain), "MIX")
    # grime where the light and the rain cannot reach
    ao = N.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.6
    ao.samples = 8
    grime = ramp(ao.outputs["AO"], [(0.0, (0.35, 0.33, 0.3)), (0.85, (1, 1, 1))])
    col = mix(col, grime, 1.0, "MULTIPLY")
    # dark rain streaks under ledges
    sx = N.new("ShaderNodeMapping")
    sx.inputs["Scale"].default_value = (8.0, 8.0, 0.4)
    L.new(pos, sx.inputs["Vector"])
    sn = N.new("ShaderNodeTexNoise")
    sn.inputs["Scale"].default_value = 2.5
    L.new(sx.outputs["Vector"], sn.inputs["Vector"])
    streak = ramp(sn.outputs["Fac"], [(0.55, (1, 1, 1)), (0.75, (0.88, 0.87, 0.85))])
    col = mix(col, streak, 1.0, "MULTIPLY")
    # edges worn smooth and a little lighter by centuries of hands and feet
    bev = N.new("ShaderNodeBevel")
    bev.samples = 6
    bev.inputs["Radius"].default_value = 0.03
    dot = N.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L.new(bev.outputs["Normal"], dot.inputs[0])
    L.new(geo.outputs["Normal"], dot.inputs[1])
    edge = N.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.995
    edge.inputs["From Max"].default_value = 0.9
    L.new(dot.outputs["Value"], edge.inputs["Value"])
    col = mix(col, (0.2, 0.19, 0.17), edge.outputs["Result"], "SCREEN")
    L.new(col, b.inputs["Base Color"])
    rr = N.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.5
    rr.inputs["To Max"].default_value = 0.78
    L.new(noise(4.0, 5), rr.inputs["Value"])
    rsub = N.new("ShaderNodeMath")
    rsub.operation = "MULTIPLY_ADD"
    rsub.inputs[1].default_value = -0.22
    L.new(edge.outputs["Result"], rsub.inputs[0])
    L.new(rr.outputs["Result"], rsub.inputs[2])
    L.new(rsub.outputs["Value"], b.inputs["Roughness"])
    # relief: the grain, the chisel's tooling, and a gentle unevenness of the dressed face
    h1 = N.new("ShaderNodeMath")
    h1.operation = "MULTIPLY"
    h1.inputs[1].default_value = 0.25
    L.new(bw(voronoi(240)), h1.inputs[0])
    tool = N.new("ShaderNodeMapping")
    tool.inputs["Scale"].default_value = (22.0, 22.0, 70.0)
    L.new(pos, tool.inputs["Vector"])
    tw = N.new("ShaderNodeTexWave")
    tw.wave_type = "BANDS"
    tw.bands_direction = "Z"
    tw.inputs["Scale"].default_value = 1.0
    tw.inputs["Distortion"].default_value = 6.0
    tw.inputs["Detail"].default_value = 3.0
    L.new(tool.outputs["Vector"], tw.inputs["Vector"])
    h2 = N.new("ShaderNodeMath")
    h2.operation = "MULTIPLY_ADD"
    h2.inputs[1].default_value = 0.35
    L.new(tw.outputs["Fac"], h2.inputs[0])
    L.new(h1.outputs["Value"], h2.inputs[2])
    h3 = N.new("ShaderNodeMath")
    h3.operation = "ADD"
    L.new(h2.outputs["Value"], h3.inputs[0])
    L.new(noise(2.0, 6), h3.inputs[1])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.004
    L.new(h3.outputs["Value"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def toned(m, attr):
    """Multiply a material's colour by a per-slab tone stored on the mesh."""
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N["Principled BSDF"]
    src = b.inputs["Base Color"].links[0].from_socket
    at = N.new("ShaderNodeAttribute")
    at.attribute_name = attr
    mx = N.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.inputs["Factor"].default_value = 1.0
    L.new(src, mx.inputs["A"])
    L.new(at.outputs["Color"], mx.inputs["B"])
    L.new(mx.outputs["Result"], b.inputs["Base Color"])
    return m


def lattice(m):
    """Carve a diamond lattice into a dome's material: two families of grooves running
    diagonally across longitude and height, as on the real crown."""
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N["Principled BSDF"]
    geo = N.new("ShaderNodeNewGeometry")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sep.inputs["Vector"])
    lon = N.new("ShaderNodeMath")
    lon.operation = "ARCTAN2"
    L.new(sep.outputs["Y"], lon.inputs[0])
    L.new(sep.outputs["X"], lon.inputs[1])
    grooves = []
    for sgn in (1.0, -1.0):
        a_ = N.new("ShaderNodeMath")
        a_.operation = "MULTIPLY"
        a_.inputs[1].default_value = 36.0
        L.new(lon.outputs["Value"], a_.inputs[0])
        b_ = N.new("ShaderNodeMath")
        b_.operation = "MULTIPLY_ADD"
        b_.inputs[1].default_value = 3.1 * sgn
        L.new(sep.outputs["Z"], b_.inputs[0])
        L.new(a_.outputs["Value"], b_.inputs[2])
        s_ = N.new("ShaderNodeMath")
        s_.operation = "SINE"
        L.new(b_.outputs["Value"], s_.inputs[0])
        ab = N.new("ShaderNodeMath")
        ab.operation = "ABSOLUTE"
        L.new(s_.outputs["Value"], ab.inputs[0])
        grooves.append(ab)
    mn = N.new("ShaderNodeMath")
    mn.operation = "MINIMUM"
    L.new(grooves[0].outputs["Value"], mn.inputs[0])
    L.new(grooves[1].outputs["Value"], mn.inputs[1])
    edge = N.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.35
    L.new(mn.outputs["Value"], edge.inputs["Value"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.05
    L.new(edge.outputs["Result"], bump.inputs["Height"])
    if b.inputs["Normal"].is_linked:
        L.new(b.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    shade = N.new("ShaderNodeMapRange")
    shade.inputs["To Min"].default_value = 0.62
    shade.inputs["To Max"].default_value = 1.0
    L.new(edge.outputs["Result"], shade.inputs["Value"])
    mx = N.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.inputs["Factor"].default_value = 1.0
    L.new(b.inputs["Base Color"].links[0].from_socket, mx.inputs["A"])
    L.new(shade.outputs["Result"], mx.inputs["B"])
    L.new(mx.outputs["Result"], b.inputs["Base Color"])
    return m


def mat_inscription():
    import os

    m = mat_scan(
        "inscr",
        "large_sandstone_blocks",
        3.4,
        displace=0.07,
        tint=((1.45, 1.14, 0.8) if GRADE == "gold" else (1.34, 1.12, 0.86)),
        normal_strength=1.15,
    )
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    uv = N.new("ShaderNodeUVMap")
    t = N.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(os.path.join(TEX, "inscription.png"))
    t.image.colorspace_settings.name = "Non-Color"
    t.extension = "REPEAT"
    L.new(uv.outputs["UV"], t.inputs["Vector"])
    # carved letters: darker inside the groove, pressed into the stone
    base_col = b.inputs["Base Color"].links[0].from_socket
    dark = N.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    L.new(t.outputs["Color"], dark.inputs["Factor"])
    L.new(base_col, dark.inputs["A"])
    dark.inputs["B"].default_value = (0.45, 0.4, 0.36, 1)
    L.new(dark.outputs["Result"], b.inputs["Base Color"])
    nrm_src = b.inputs["Normal"].links[0].from_socket
    bump = N.new("ShaderNodeBump")
    bump.invert = True
    bump.inputs["Strength"].default_value = 0.9
    bump.inputs["Distance"].default_value = 0.01
    L.new(t.outputs["Color"], bump.inputs["Height"])
    L.new(nrm_src, bump.inputs["Normal"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


MATS = {
    "carve": mat_scan(
        "carve",
        "large_sandstone_blocks",
        3.4,
        tint=((1.45, 1.14, 0.8) if GRADE == "gold" else (1.34, 1.12, 0.86)),
        normal_strength=0.6,
    ),
    "inscr": mat_inscription(),
    "pstone": mat_granite("pstone"),
    "dome": lattice(
        mat_scan(
            "dome",
            "large_sandstone_blocks",
            26.0,
            tint=((1.45, 1.14, 0.8) if GRADE == "gold" else (1.34, 1.12, 0.86)),
            normal_strength=0.4,
        )
    ),
    "mono": mat_scan(
        "mono",
        "large_sandstone_blocks",
        26.0,
        tint=((1.45, 1.14, 0.8) if GRADE == "gold" else (1.34, 1.12, 0.86)),
        normal_strength=0.5,
    ),
    "rice": mat_simple("rice", (0.5, 0.48, 0.45), 0.98),
    "bird": mat_simple("bird", (0.05, 0.045, 0.04), 0.8),
    "leaf": mat_leaf(),
    "deadleaf": mat_foliage(
        "deadleaf", (0.18, 0.12, 0.05), (0.42, 0.3, 0.14), (0.5, 0.32, 0.1), 0.25
    ),
    "banana": mat_banana_leaf(),
    "bstem": mat_pseudostem(),
    "midrib": mat_foliage(
        "midrib", (0.28, 0.32, 0.12), (0.42, 0.45, 0.2), (0.4, 0.45, 0.2), 0.1
    ),
    "fruit": mat_foliage(
        "fruit", (0.16, 0.3, 0.04), (0.36, 0.42, 0.08), (0.4, 0.5, 0.1), 0.1
    ),
    "heart": mat_foliage(
        "heart", (0.12, 0.02, 0.05), (0.25, 0.05, 0.1), (0.3, 0.05, 0.08), 0.05
    ),
    "trunk": mat_scan(
        "trunk", "palm_tree_bark", 1.3, tint=(0.75, 0.66, 0.55), weather=False
    ),
    "stone": mat_scan(
        "stone",
        "large_sandstone_blocks",
        3.4,
        displace=0.07,
        tint=((1.45, 1.14, 0.8) if GRADE == "gold" else (1.34, 1.12, 0.86)),
        normal_strength=1.15,
    ),
    "wall": mat_scan(
        "wall",
        "large_sandstone_blocks",
        3.4,
        displace=0.06,
        tint=((1.4, 1.1, 0.8) if GRADE == "gold" else (1.3, 1.1, 0.86)),
        normal_strength=1.0,
    ),
    "gold": mat_simple("gold", (1.0, 0.7, 0.3), 0.22, 1.0),
    "niche": mat_simple("niche", (0.05, 0.035, 0.03), 0.9),
    "floor": mat_scan(
        "floor",
        "red_sandstone_pavement",
        2.15,
        tint=(1.0, 0.85, 0.72),
        weather=False,
        wet=WET,
    ),
    "grass": mat_scan("grass", "grass_path_2", 1.0, tint=(0.8, 0.85, 0.6), weather=False),
    "blade": mat_blade(),
    "path": mat_scan(
        "path",
        "red_sandstone_pavement",
        2.15,
        displace=0.03,
        tint=(1.05, 0.9, 0.78),
        weather=False,
        wet=WET,
    ),
    "pave": toned(
        mat_scan(
            "pave",
            "red_sandstone_pavement",
            2.15,
            tint=(1.0, 0.88, 0.78),
            weather=False,
            wet=WET,
        ),
        "slab",
    ),
    "flame": mat_flame(),
}

UNITS = build_units()
for unit_meshes in UNITS.values():
    for key, me in unit_meshes:
        me.materials.append(MATS["carve"] if key == "stone" else MATS["niche"])
place_instances(UNITS)
print("INSTANCES", len(INSTANCES))

for key, bm in MESHES.items():
    me = bpy.data.meshes.new(key)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(key, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(MATS[key])
    for p in me.polygons:
        p.use_smooth = key != "pave"
    if key in ("stone", "wall", "pstone", "mono"):
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = 0.035
        bv.segments = 2
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(40)
        bv.harden_normals = True
    ws = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    ws.keep_sharp = True
    if key in ("stone", "wall", "path", "inscr"):
        sd = ob.modifiers.new("detail", "SUBSURF")
        sd.subdivision_type = "SIMPLE"
        sd.use_adaptive_subdivision = True
        sd.adaptive_pixel_size = 2.0 if QUALITY == "final" else 4.0

# ---------- light, sky, camera ----------
sc = bpy.context.scene
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev_type in ("CUDA",):
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        if any(d.type == dev_type for d in prefs.devices):
            break
    except Exception as e:
        print("NOGPU", dev_type, e)
for d in prefs.devices:
    d.use = d.type == prefs.compute_device_type
    print("DEVICE", d.type, d.name, d.use)
sc.cycles.device = "GPU" if any(d.use for d in prefs.devices) else "CPU"
print("RENDER_DEVICE", sc.cycles.device, prefs.compute_device_type)
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.view_settings.view_transform = "AgX"
with contextlib.suppress(Exception):
    sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = {"gold": 0.2, "blue": 1.9, "noon": -0.3}.get(GRADE, 0.1)

world = bpy.data.worlds.new("sky")
sc.world = world
wn = world.node_tree.nodes
wl = world.node_tree.links
sky = wn.new("ShaderNodeTexSky")
sky.sky_type = "MULTIPLE_SCATTERING"
SUN_EL, SUN_ROT = (
    # low behind the camera, to its left: the tower's face and the pillars catch raking
    # dusk light (pass 10; at 252 degrees the sun stood behind the tower and the view went flat)
    (math.radians(12), math.radians(330))
    if (len(argv) > 4 and argv[4] == "hall")
    else (math.radians(16), math.radians(307))
)
if GRADE == "gold":
    SUN_EL = math.radians(7)
elif GRADE == "blue":
    SUN_EL = math.radians(-3.5)
elif GRADE == "noon":
    SUN_EL = math.radians(52)
sky.sun_elevation = SUN_EL
sky.sun_rotation = SUN_ROT
sky.aerosol_density = 1.4
sky.air_density = 1.0


def world_clouds():
    """A painted cloud layer in the world shader: a noise field projected on a high plane."""
    tc = wn.new("ShaderNodeTexCoord")
    sep = wn.new("ShaderNodeSeparateXYZ")
    wl.new(tc.outputs["Generated"], sep.inputs["Vector"])
    zden = wn.new("ShaderNodeMath")
    zden.operation = "ADD"
    zden.inputs[1].default_value = 0.06
    wl.new(sep.outputs["Z"], zden.inputs[0])
    ux = wn.new("ShaderNodeMath")
    ux.operation = "DIVIDE"
    wl.new(sep.outputs["X"], ux.inputs[0])
    wl.new(zden.outputs["Value"], ux.inputs[1])
    uy = wn.new("ShaderNodeMath")
    uy.operation = "DIVIDE"
    wl.new(sep.outputs["Y"], uy.inputs[0])
    wl.new(zden.outputs["Value"], uy.inputs[1])
    comb = wn.new("ShaderNodeCombineXYZ")
    wl.new(ux.outputs["Value"], comb.inputs["X"])
    wl.new(uy.outputs["Value"], comb.inputs["Y"])
    mp = wn.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.9, 2.2, 1.0)
    wl.new(comb.outputs["Vector"], mp.inputs["Vector"])
    cn = wn.new("ShaderNodeTexNoise")
    cn.inputs["Scale"].default_value = 1.4
    cn.inputs["Detail"].default_value = 12
    cn.inputs["Roughness"].default_value = 0.62
    cn.inputs["Distortion"].default_value = 0.35
    wl.new(mp.outputs["Vector"], cn.inputs["Vector"])
    cover = wn.new("ShaderNodeMapRange")
    cover.inputs["From Min"].default_value = 0.5
    cover.inputs["From Max"].default_value = 0.72
    wl.new(cn.outputs["Fac"], cover.inputs["Value"])
    # only above the horizon, thinning near it
    hz = wn.new("ShaderNodeMapRange")
    hz.inputs["From Min"].default_value = 0.01
    hz.inputs["From Max"].default_value = 0.12
    wl.new(sep.outputs["Z"], hz.inputs["Value"])
    mask = wn.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    wl.new(cover.outputs["Result"], mask.inputs[0])
    wl.new(hz.outputs["Result"], mask.inputs[1])
    # lit undersides warm, shadowed parts a dusky violet
    shade = wn.new("ShaderNodeTexNoise")
    shade.inputs["Scale"].default_value = 2.6
    shade.inputs["Detail"].default_value = 6
    wl.new(mp.outputs["Vector"], shade.inputs["Vector"])
    cr = wn.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.46, 0.47, 0.55, 1)
    cr.color_ramp.elements[1].color = (1.55, 1.48, 1.38, 1)
    wl.new(shade.outputs["Fac"], cr.inputs["Fac"])
    # a pale warm band of light low on the horizon, fading into the blue above
    glow = wn.new("ShaderNodeMapRange")
    glow.inputs["From Min"].default_value = 0.0
    glow.inputs["From Max"].default_value = 0.42
    glow.inputs["To Min"].default_value = 0.45
    glow.inputs["To Max"].default_value = 0.0
    wl.new(sep.outputs["Z"], glow.inputs["Value"])
    gramp = wn.new("ShaderNodeValToRGB")
    gramp.color_ramp.elements[0].color = (0.62, 0.7, 0.82, 1)
    gramp.color_ramp.elements[1].color = (1.05, 0.98, 0.86, 1)
    wl.new(glow.outputs["Result"], gramp.inputs["Fac"])
    warm = wn.new("ShaderNodeMix")
    warm.data_type = "RGBA"
    wl.new(glow.outputs["Result"], warm.inputs["Factor"])
    wl.new(sky.outputs["Color"], warm.inputs["A"])
    wl.new(gramp.outputs["Color"], warm.inputs["B"])
    mix = wn.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    wl.new(mask.outputs["Value"], mix.inputs["Factor"])
    wl.new(warm.outputs["Result"], mix.inputs["A"])
    wl.new(cr.outputs["Color"], mix.inputs["B"])
    return mix.outputs["Result"]


wl.new(world_clouds(), wn["Background"].inputs["Color"])
env = wn.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(os.path.join(TEX, "hdri", "sky_2k.hdr"))
bg_light = wn.new("ShaderNodeBackground")
wl.new(env.outputs["Color"], bg_light.inputs["Color"])
bg_light.inputs["Strength"].default_value = {"blue": 0.05, "noon": 0.6}.get(GRADE, 0.45)
lp = wn.new("ShaderNodeLightPath")
mixw = wn.new("ShaderNodeMixShader")
wl.new(lp.outputs["Is Camera Ray"], mixw.inputs["Fac"])
wl.new(bg_light.outputs["Background"], mixw.inputs[1])
wl.new(wn["Background"].outputs["Background"], mixw.inputs[2])
wl.new(mixw.outputs["Shader"], wn["World Output"].inputs["Surface"])


def volume_clouds():
    """Real 3D clouds: a thin slab of noise-shaped volume high above, lit by the low sun."""
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 1400, 700))
    dom = bpy.context.object
    dom.name = "clouds"
    dom.scale = (3200, 1800, 120)
    m = bpy.data.materials.new("clouds")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    N.remove(N["Principled BSDF"])
    pos = N.new("ShaderNodeNewGeometry")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.0028, 0.005, 0.012)
    L.new(pos.outputs["Position"], mp.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise")
    nz.noise_dimensions = "3D"
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 9
    nz.inputs["Roughness"].default_value = 0.6
    nz.inputs["Distortion"].default_value = 0.2
    L.new(mp.outputs["Vector"], nz.inputs["Vector"])
    dens = N.new("ShaderNodeMapRange")
    dens.inputs["From Min"].default_value = 0.56
    dens.inputs["From Max"].default_value = 0.78
    dens.inputs["To Min"].default_value = 0.0
    dens.inputs["To Max"].default_value = 0.06
    L.new(nz.outputs["Fac"], dens.inputs["Value"])
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs["Vector"])
    prof = N.new("ShaderNodeMath")
    prof.operation = "ABSOLUTE"
    L.new(sep.outputs["Z"], prof.inputs[0])
    fall = N.new("ShaderNodeMapRange")
    fall.inputs["From Min"].default_value = 0.2
    fall.inputs["From Max"].default_value = 1.0
    fall.inputs["To Min"].default_value = 1.0
    fall.inputs["To Max"].default_value = 0.0
    L.new(prof.outputs["Value"], fall.inputs["Value"])
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    L.new(dens.outputs["Result"], mul.inputs[0])
    L.new(fall.outputs["Result"], mul.inputs[1])
    vol = N.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (1.0, 0.92, 0.86, 1)
    vol.inputs["Anisotropy"].default_value = 0.55
    L.new(mul.outputs["Value"], vol.inputs["Density"])
    L.new(vol.outputs["Volume"], N["Material Output"].inputs["Volume"])
    m.cycles.volume_step_rate = 0.5
    dom.data.materials.append(m)


if "--volclouds" in argv:
    volume_clouds()
    # the real clouds replace the painted ones
    for nd in wn:
        if (
            nd.bl_idname == "ShaderNodeMix"
            and nd.inputs["Factor"].is_linked
            and nd.outputs["Result"].links
            and nd.outputs["Result"].links[0].to_node == wn["Background"]
        ):
            wl.remove(nd.inputs["Factor"].links[0])
            nd.inputs["Factor"].default_value = 0.0

wn["Background"].inputs["Strength"].default_value = {"blue": 0.5, "noon": 0.12}.get(
    GRADE, 0.16
)

sun_data = bpy.data.lights.new("sun", "SUN")
sun_data.energy = 7.5
sun_data.color = (1.0, 0.84, 0.6)
sun_data.angle = math.radians(1.2)
if GRADE == "gold":
    sun_data.energy = 9.0
    sun_data.color = (1.0, 0.8, 0.52)
elif GRADE == "blue":
    sun_data.energy = 0.0
elif GRADE == "noon":
    sun_data.energy = 6.0
    sun_data.color = (1.0, 0.97, 0.92)
sun = bpy.data.objects.new("sun", sun_data)
sc.collection.objects.link(sun)
d = Vector(
    (
        math.cos(SUN_EL) * math.sin(SUN_ROT),
        -math.cos(SUN_EL) * math.cos(SUN_ROT),
        math.sin(SUN_EL),
    )
)
sun.rotation_mode = "QUATERNION"
sun.rotation_quaternion = (-d).to_track_quat("-Z", "Y")

# haze: a thin volume over the courtyard
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 60))
fog = bpy.context.object
fog.scale = (520, 520, 120)
fog.name = "haze"
fm = bpy.data.materials.new("haze")
fnt = fm.node_tree
fnt.nodes.remove(fnt.nodes["Principled BSDF"])
vs = fnt.nodes.new("ShaderNodeVolumePrincipled")
vs.inputs["Density"].default_value = 0.00045
vs.inputs["Color"].default_value = (0.92, 0.93, 0.96, 1)
vs.inputs["Anisotropy"].default_value = 0.55
fnt.links.new(vs.outputs["Volume"], fnt.nodes["Material Output"].inputs["Volume"])
fog.data.materials.append(fm)
sc.cycles.volume_step_rate = 4.0
if GRADE == "blue":
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -55, 4.0))
    mist = bpy.context.object
    mist.scale = (110, 150, 8.0)
    mist.name = "mist"
    mm = bpy.data.materials.new("mist")
    mnt = mm.node_tree
    mnt.nodes.remove(mnt.nodes["Principled BSDF"])
    mg = mnt.nodes.new("ShaderNodeTexCoord")
    ms = mnt.nodes.new("ShaderNodeSeparateXYZ")
    mnt.links.new(mg.outputs["Generated"], ms.inputs["Vector"])
    mfall = mnt.nodes.new("ShaderNodeMapRange")
    mfall.inputs["To Min"].default_value = 0.009
    mfall.inputs["To Max"].default_value = 0.0
    mnt.links.new(ms.outputs["Z"], mfall.inputs["Value"])
    mv = mnt.nodes.new("ShaderNodeVolumePrincipled")
    mv.inputs["Color"].default_value = (0.9, 0.92, 1.0, 1)
    mv.inputs["Anisotropy"].default_value = 0.72
    mnt.links.new(mfall.outputs["Result"], mv.inputs["Density"])
    mnt.links.new(mv.outputs["Volume"], mnt.nodes["Material Output"].inputs["Volume"])
    mist.data.materials.append(mm)

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 35
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = (-72.0, -138.0, 1.75)
target = Vector((30.0, 0.0, top * 0.4))
cam.rotation_mode = "QUATERNION"
if len(argv) > 4 and argv[4] == "hall":
    cam.location = (0.0, -118.3, 1.7)
    target = Vector((0.0, 0.0, 24.0))
    cam_data.lens = 30
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, -115, 5))
    dust = bpy.context.object
    dust.scale = (6.5, 6.5, 5)
    dm = bpy.data.materials.new("dust")
    dn = dm.node_tree
    dn.nodes.remove(dn.nodes["Principled BSDF"])
    dv = dn.nodes.new("ShaderNodeVolumePrincipled")
    dv.inputs["Density"].default_value = 0.01
    dv.inputs["Color"].default_value = (1.0, 0.95, 0.88, 1)
    dv.inputs["Anisotropy"].default_value = 0.6
    dn.links.new(dv.outputs["Volume"], dn.nodes["Material Output"].inputs["Volume"])
    dust.data.materials.append(dm)
if len(argv) > 4 and argv[4] == "threshold":
    # Kneeling height at the hall's edge, the tower framed by two pillars and
    # mirrored in the wet paving, lamps along the step in the foreground.
    cam.location = (0.35, -112.2, 1.05)
    target = Vector((0.0, 0.0, 28.0))
    cam_data.lens = 22
if len(argv) > 4 and argv[4] == "approach":
    # Down the processional path at golden hour, the sun raking across the
    # tower's tiers so every pavilion throws a shadow.
    cam.location = (-52.0, -120.0, 1.7)
    target = Vector((-2.0, 0.0, 26.0))
    cam_data.lens = 35
if len(argv) > 4 and argv[4] == "pillarmacro":
    # One carved block of a hall pillar, close, the tower soft behind.
    cam.location = (-3.4, -117.45, 2.35)
    target = Vector((-4.95, -116.1, 2.2))
    cam_data.lens = 50
if len(argv) > 4 and argv[4] == "low":
    cam.location = (-21.0, -36.0, 1.6)
    target = Vector((0.0, 0.0, 52.0))
    cam_data.lens = 18
if len(argv) > 4 and argv[4] == "aerial":
    cam.location = (-125.0, -175.0, 92.0)
    target = Vector((-5.0, -25.0, 14.0))
    cam_data.lens = 32
if len(argv) > 4 and argv[4] == "base":
    cam.location = (-7.5, -23.5, 2.6)
    target = Vector((-3.0, -15.9, 3.7))
    cam_data.lens = 40
if len(argv) > 4 and argv[4] == "close":
    cam.location = (-34.0, -44.0, 1.6)
    target = Vector((-2.0, -15.0, 9.0))
    cam_data.lens = 28
cam.rotation_quaternion = (target - cam.location).to_track_quat("-Z", "Y")
cam_data.dof.use_dof = True
cam_data.dof.focus_distance = (target - cam.location).length
cam_data.dof.aperture_fstop = 2.8

if GRADE == "blue":
    # Warm floodlights in the paving at the tower's foot, aimed up its faces:
    # each grazes the tiers, so every pavilion throws a shadow upward.
    import random as _r

    rr = _r.Random(5)  # noqa: S311 - light variation, not security
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        for u in (-11.0, -4.0, 4.0, 11.0):
            fx = tan[0] * u + nrm[0] * 31.0
            fy = tan[1] * u + nrm[1] * 31.0
            if abs(u) > 5:
                # the lower storey: a broad soft wash, never a hard pool
                wl_ = bpy.data.lights.new("wash", "AREA")
                wl_.shape = "RECTANGLE"
                wl_.size, wl_.size_y = 9.0, 2.0
                wl_.energy = 4.5e3
                wl_.color = (1.0, 0.6, 0.32)
                wo = bpy.data.objects.new("wash", wl_)
                wo.location = (fx * 0.62, fy * 0.62, 0.4)
                aim_w = Vector((tan[0] * u * 0.6, tan[1] * u * 0.6, 9.0)) - Vector(
                    wo.location
                )
                wo.rotation_mode = "QUATERNION"
                wo.rotation_quaternion = aim_w.to_track_quat("-Z", "Y")
                wo.visible_glossy = False
                wo.visible_camera = False
                sc.collection.objects.link(wo)
                continue
            fl = bpy.data.lights.new("flood", "SPOT")
            fl.energy = 7e4 * rr.uniform(0.85, 1.1) * (2.2 if abs(u) < 5 else 1.0)
            fl.color = (1.0, 0.66, 0.36)
            fl.spot_size = math.radians(24 if abs(u) < 5 else 44)
            fl.spot_blend = 0.8
            fl.shadow_soft_size = 0.3
            fo = bpy.data.objects.new("flood", fl)
            fo.location = (fx, fy, 0.25)
            aim = Vector(
                (tan[0] * u * 0.3, tan[1] * u * 0.3, 52.0 if abs(u) < 5 else 16.0)
            ) - Vector((fx, fy, 0.25))
            fo.rotation_mode = "QUATERNION"
            fo.rotation_quaternion = aim.to_track_quat("-Z", "Y")
            sc.collection.objects.link(fo)
    for x, y, z in HANGING:
        hl = bpy.data.lights.new("hang", "POINT")
        # five flames a lamp: kept low so the granite keeps its grain (pass 8 fault)
        hl.energy = 2.0
        hl.color = (1.0, 0.68, 0.38)
        hl.shadow_soft_size = 0.03
        ho = bpy.data.objects.new("hang", hl)
        ho.location = (x, y, z)
        sc.collection.objects.link(ho)
    for x, y, z in LAMP_SPOTS:
        ld = bpy.data.lights.new("lamp", "POINT")
        ld.energy = 14
        ld.color = (1.0, 0.72, 0.42)
        ld.shadow_soft_size = 0.05
        lo = bpy.data.objects.new("lamp", ld)
        lo.location = (x, y, z)
        sc.collection.objects.link(lo)
sc.cycles.offscreen_dicing_scale = 40.0
sc.cycles.max_subdivisions = 5


def finishing():
    ng = bpy.data.node_groups.new("finish", "CompositorNodeTree")
    sc.compositing_node_group = ng
    N, L = ng.nodes, ng.links
    rl = N.new("CompositorNodeRLayers")
    gl = N.new("CompositorNodeGlare")
    try:
        gl.inputs["Type"].default_value = "Bloom"
    except Exception as e:
        print("GLARE TYPE", e)
    gl.inputs["Threshold"].default_value = 0.85
    gl.inputs["Strength"].default_value = 0.22
    gl.inputs["Size"].default_value = (
        0.6 if gl.inputs["Size"].type == "VALUE" else gl.inputs["Size"].default_value
    )
    L.new(rl.outputs["Image"], gl.inputs["Image"])
    cb = N.new("CompositorNodeColorBalance")
    with contextlib.suppress(Exception):
        cb.inputs["Type"].default_value = "Offset/Power/Slope (ASC-CDL)"
    L.new(gl.outputs["Image"], cb.inputs["Image"])
    ld = N.new("CompositorNodeLensdist")
    ld.inputs["Distortion"].default_value = -0.012
    ld.inputs["Dispersion"].default_value = 0.004
    L.new(cb.outputs["Image"], ld.inputs["Image"])
    last = ld.outputs["Image"]
    try:
        em = N.new("CompositorNodeEllipseMask")
        em.inputs["Size"].default_value = (0.98, 0.95)
        bl = N.new("CompositorNodeBlur")
        bl.inputs["Size"].default_value = (
            (220, 220) if bl.inputs["Size"].type == "VECTOR" else 220
        )
        L.new(em.outputs["Mask"], bl.inputs["Image"])
        mx = N.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        mx.inputs["Factor"].default_value = 0.35
        inv = N.new("ShaderNodeMapRange")
        inv.inputs["To Min"].default_value = 0.55
        inv.inputs["To Max"].default_value = 1.0
        L.new(bl.outputs["Image"], inv.inputs["Value"])
        L.new(last, mx.inputs["A"])
        L.new(inv.outputs["Result"], mx.inputs["B"])
        last = mx.outputs["Result"]
    except Exception as e:
        print("VIGNETTE", e)
    out = N.new("NodeGroupOutput")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    L.new(last, out.inputs[0])


def hero_stage():
    """The vimana alone, as a crafted object on a dark stage."""
    for ob in list(sc.objects):
        if ob.name.split(".")[0] in (
            "sun",
            "mist",
            "clouds",
            "flood",
            "wash",
            "lamp",
            "hang",
            "haze",
        ):
            bpy.data.objects.remove(ob, do_unlink=True)
    # the stone as it is at Thanjavur: a warm weathered granite, not pale sand
    for key in ("stone", "carve", "wall", "mono", "dome"):
        for nd in MATS[key].node_tree.nodes:
            if (
                nd.bl_idname == "ShaderNodeMix"
                and nd.data_type == "RGBA"
                and not nd.inputs["B"].is_linked
            ):
                v = nd.inputs["B"].default_value
                if v[0] > 1.0:
                    nd.inputs["B"].default_value = (0.98, 0.8, 0.62, 1)
    # a thousand monsoons: long dark streaks run down from every ledge, patina
    # gathers in broad clouds, and the stone is never one even tone
    for key in ("stone", "carve", "wall", "mono", "dome"):
        nt_ = MATS[key].node_tree
        N_, L_ = nt_.nodes, nt_.links
        b_ = N_["Principled BSDF"]
        src = b_.inputs["Base Color"].links[0].from_socket
        geo_ = N_.new("ShaderNodeNewGeometry")
        mp_ = N_.new("ShaderNodeMapping")
        mp_.inputs["Scale"].default_value = (0.9, 0.9, 0.035)
        L_.new(geo_.outputs["Position"], mp_.inputs["Vector"])
        st_ = N_.new("ShaderNodeTexNoise")
        st_.inputs["Scale"].default_value = 3.0
        st_.inputs["Detail"].default_value = 6
        L_.new(mp_.outputs["Vector"], st_.inputs["Vector"])
        sr_ = N_.new("ShaderNodeMapRange")
        sr_.inputs["From Min"].default_value = 0.42
        sr_.inputs["From Max"].default_value = 0.7
        sr_.inputs["To Min"].default_value = 1.0
        sr_.inputs["To Max"].default_value = 0.62
        L_.new(st_.outputs["Fac"], sr_.inputs["Value"])
        pc_ = N_.new("ShaderNodeTexNoise")
        pc_.inputs["Scale"].default_value = 0.06
        pc_.inputs["Detail"].default_value = 4
        L_.new(geo_.outputs["Position"], pc_.inputs["Vector"])
        pr_ = N_.new("ShaderNodeMapRange")
        pr_.inputs["To Min"].default_value = 0.8
        pr_.inputs["To Max"].default_value = 1.2
        L_.new(pc_.outputs["Fac"], pr_.inputs["Value"])
        both = N_.new("ShaderNodeMath")
        both.operation = "MULTIPLY"
        L_.new(sr_.outputs["Result"], both.inputs[0])
        L_.new(pr_.outputs["Result"], both.inputs[1])
        mx_ = N_.new("ShaderNodeMix")
        mx_.data_type = "RGBA"
        mx_.blend_type = "MULTIPLY"
        mx_.inputs["Factor"].default_value = 1.0
        L_.new(src, mx_.inputs["A"])
        L_.new(both.outputs["Value"], mx_.inputs["B"])
        L_.new(mx_.outputs["Result"], b_.inputs["Base Color"])
    # the backdrop: deep indigo above, a warm umber at the floor, seamless
    wnodes, wlinks = world.node_tree.nodes, world.node_tree.links
    for nd in list(wnodes):
        wnodes.remove(nd)
    out = wnodes.new("ShaderNodeOutputWorld")
    tc = wnodes.new("ShaderNodeTexCoord")
    sp = wnodes.new("ShaderNodeSeparateXYZ")
    wlinks.new(tc.outputs["Generated"], sp.inputs["Vector"])
    gr = wnodes.new("ShaderNodeValToRGB")
    e = gr.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.012, 0.009, 0.008, 1)
    e[1].position, e[1].color = 0.22, (0.004, 0.006, 0.018, 1)
    mid = e.new(0.05)
    mid.color = (0.02, 0.014, 0.012, 1)
    wlinks.new(sp.outputs["Z"], gr.inputs["Fac"])
    bg = wnodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    wlinks.new(gr.outputs["Color"], bg.inputs["Color"])
    wlinks.new(bg.outputs["Background"], out.inputs["Surface"])
    # a polished dark granite floor that holds a soft reflection
    bpy.ops.mesh.primitive_circle_add(
        vertices=128, radius=20000, fill_type="NGON", location=(0, 0, -0.02)
    )
    floor = bpy.context.object
    fm = bpy.data.materials.new("stage")
    fb = fm.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.018, 0.016, 0.015, 1)
    fz = fm.node_tree.nodes.new("ShaderNodeTexNoise")
    fz.inputs["Scale"].default_value = 0.08
    fr = fm.node_tree.nodes.new("ShaderNodeMapRange")
    fr.inputs["To Min"].default_value = 0.08
    fr.inputs["To Max"].default_value = 0.26
    fm.node_tree.links.new(fz.outputs["Fac"], fr.inputs["Value"])
    fm.node_tree.links.new(fr.outputs["Result"], fb.inputs["Roughness"])
    floor.data.materials.append(fm)
    # key: a warm low sun from the front left, rim: cool from behind right, fill: faint
    for name, energy, colour, el, az, angle in (
        ("key", 11.0, (1.0, 0.7, 0.42), 9, 252, 1.4),
        ("rim", 5.5, (0.55, 0.68, 1.0), 16, 40, 1.2),
        ("fill", 0.12, (0.75, 0.8, 1.0), 35, 300, 12.0),
    ):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.color = colour
        ld.angle = math.radians(angle)
        lo = bpy.data.objects.new(name, ld)
        e_, a_ = math.radians(el), math.radians(az)
        d_ = Vector(
            (math.cos(e_) * math.sin(a_), -math.cos(e_) * math.cos(a_), math.sin(e_))
        )
        lo.rotation_mode = "QUATERNION"
        lo.rotation_quaternion = (-d_).to_track_quat("-Z", "Y")
        sc.collection.objects.link(lo)
    # the camera circles the tower, low, on a long lens: it stands, it does not lean
    o = math.radians(ORBIT)
    dist = 430.0
    cam.location = (dist * math.sin(o), -dist * math.cos(o), 14.0)
    tgt = Vector((0.0, 0.0, top * 0.47))
    cam.rotation_quaternion = (tgt - cam.location).to_track_quat("-Z", "Y")
    cam_data.lens = 105
    if PART is not None:
        size = {"crown": 16.0, "kuta": 9.0, "shala": 9.0, "pillar": 9.0}[PART]
        dist_p = size * 2.3
        cam.location = (dist_p * math.sin(o), -dist_p * math.cos(o), top * 0.35)
        tgt = Vector((0.0, 0.0, top * 0.5))
        cam.rotation_quaternion = (tgt - cam.location).to_track_quat("-Z", "Y")
        cam_data.lens = 50
        cam_data.shift_y = 0.0
    if len(argv) > 4 and argv[4] == "crown":
        tgt = Vector((0.0, 0.0, top - 7.5))
        cam.rotation_quaternion = (tgt - cam.location).to_track_quat("-Z", "Y")
        cam_data.lens = 900
        cam_data.shift_y = 0.0
    cam_data.clip_end = 6000.0
    cam_data.shift_y = 0.04
    cam_data.dof.use_dof = False
    # a soft warm glow on the far backdrop, behind the tower: the silhouette
    # lifts off the dark, as a product does on a stage
    back = Vector((-math.sin(o), math.cos(o), 0.0))
    bpy.ops.mesh.primitive_plane_add(
        size=1, location=tuple(back * 900 + Vector((0, 0, 115)))
    )
    halo = bpy.context.object
    halo.scale = (900, 900, 1)
    halo.rotation_mode = "QUATERNION"
    halo.rotation_quaternion = (-back).to_track_quat("Z", "Y")
    hm = bpy.data.materials.new("halo")
    hn, hl_ = hm.node_tree.nodes, hm.node_tree.links
    hn.remove(hn["Principled BSDF"])
    hc = hn.new("ShaderNodeTexCoord")
    hg = hn.new("ShaderNodeTexGradient")
    hg.gradient_type = "SPHERICAL"
    hmp = hn.new("ShaderNodeMapping")
    hmp.inputs["Scale"].default_value = (5.0, 4.2, 1.0)
    hl_.new(hc.outputs["Object"], hmp.inputs["Vector"])
    hl_.new(hmp.outputs["Vector"], hg.inputs["Vector"])
    hr = hn.new("ShaderNodeValToRGB")
    hr.color_ramp.elements[0].color = (0, 0, 0, 1)
    hr.color_ramp.elements[1].position = 1.0
    hr.color_ramp.elements[1].color = (0.075, 0.048, 0.03, 1)
    hr.color_ramp.interpolation = "EASE"
    soft = hr.color_ramp.elements.new(0.55)
    soft.color = (0.012, 0.008, 0.005, 1)
    hl_.new(hg.outputs["Fac"], hr.inputs["Fac"])
    he = hn.new("ShaderNodeEmission")
    hl_.new(hr.outputs["Color"], he.inputs["Color"])
    hl_.new(he.outputs["Emission"], hn["Material Output"].inputs["Surface"])
    halo.data.materials.append(hm)
    halo.visible_shadow = False
    halo.visible_diffuse = False
    halo.visible_glossy = False
    sc.view_settings.exposure = -0.4
    with contextlib.suppress(TypeError):
        sc.view_settings.look = "AgX - Medium High Contrast"


if HERO:
    hero_stage()
finishing()
sc.render.filepath = OUT
sc.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
print(
    "DONE",
    OUT,
    "height",
    round(top, 1),
    "faces",
    sum(len(o.data.polygons) for o in sc.objects if o.type == "MESH"),
)
