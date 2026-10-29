"""Procedural Thanjavur-style vimana for Colyv (study 1).

Built from the Dravidian vimana anatomy: upapitha and adhishthana (moulded
base), pada (pilastered wall with niches), prastara (cornice with a curved
kapota), a hara of miniature shrines (kuta at the corners, shala in the
middle, panjara between), then receding talas, the griva, the shikhara and
the kalasa. Proportions are approximate until a primary source is found
(docs/research/FRONTEND_RESEARCH_2026.md, B5).

Run: blender -b --factory-startup --python vimana.py -- <out.png> [width height samples]
"""
import math
import os
import sys

import addon_utils
import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
QUALITY = next((a.split('=', 1)[1] for a in argv if a.startswith('quality=')), 'preview')
GRADE = next((a.split('=', 1)[1] for a in argv if a.startswith('grade=')), 'morning')
OUT = argv[0] if argv else '//vimana.png'
W = int(argv[1]) if len(argv) > 1 else 1600
H = int(argv[2]) if len(argv) > 2 else 900
SAMPLES = int(argv[3]) if len(argv) > 3 else 96

addon_utils.enable('cycles', default_set=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

MESHES = {k: bmesh.new() for k in ('stone', 'gold', 'niche', 'floor', 'wall', 'carve')}


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


def loft(key, cx, cy, profile, e=40, n=64, cap_top=True, cap_bottom=False, aspect=1.0, phase=0.0):
    """Revolve a moulding profile [(half, z), ...] around a superellipse."""
    bm = MESHES[key]
    rings = [[bm.verts.new(p) for p in ring(cx, cy, h, h * aspect, z, e, n, phase)] for h, z in profile]
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap_top:
        bm.faces.new(list(reversed(rings[-1])) if False else rings[-1])
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))


def box(key, cx, cy, z0, hx, hy, h):
    bm = MESHES[key]
    v = [bm.verts.new((cx + sx * hx, cy + sy * hy, z0 + sz * h))
         for sz in (0, 1) for sy in (-1, 1) for sx in (-1, 1)]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
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
            p = (cx + s * half_len, cy + u, z0 + w) if along_x else (cx + u, cy + s * half_len, z0 + w)
            row.append(bm.verts.new(p))
        ends.append(row)
    a, b = ends
    for i in range(n):
        bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))


# ---------- architectural parts ----------
INSTANCES = []          # (unit, (x, y, z), scale, rotation about z)


def kuta(cx, cy, z0, s):
    """Corner pavilion, placed as an instance of the detailed unit built once (build_units)."""
    INSTANCES.append(('kuta', (cx, cy, z0), s, 0.0))


def shala(cx, cy, z0, s, along_x, side=None):
    """Middle pavilion (barrel-vaulted), placed as an instance; its great arch faces outward."""
    rot = {0: 0.0, 2: math.pi, 1: math.pi / 2, 3: -math.pi / 2}.get(side, 0.0 if along_x else math.pi / 2)
    INSTANCES.append(('shala', (cx, cy, z0), s, rot))


def _unit_kuta():
    """A kuta at unit size: moulded plinth, pilastered cell with a framed arch on each face,
    curved cornice, neck, a square dome carrying four small arches, and a finial."""
    loft('stone', 0, 0, [(0.5, 0.0), (0.5, 0.05), (0.46, 0.07), (0.46, 0.1), (0.48, 0.12)], e=40, n=32)
    box('stone', 0, 0, 0.12, 0.4, 0.4, 0.43)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box('stone', sx * 0.38, sy * 0.38, 0.12, 0.05, 0.05, 0.43)
            box('stone', sx * 0.38, sy * 0.38, 0.5, 0.07, 0.07, 0.04)
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]; tan = (-nrm[1], nrm[0])
        for d in (-1, 1):
            box('stone', tan[0] * d * 0.17 + nrm[0] * 0.41, tan[1] * d * 0.17 + nrm[1] * 0.41, 0.16, 0.03 + abs(nrm[0]) * 0.0, 0.03, 0.3)
        box('niche', nrm[0] * 0.405, nrm[1] * 0.405, 0.18, abs(tan[0]) * 0.12 + 0.01, abs(tan[1]) * 0.12 + 0.01, 0.24)
        nasika(nrm[0] * 0.42, nrm[1] * 0.42, 0.44, 0.15, 0.1, side, thick=0.03, out=0.04)
    loft('stone', 0, 0, [(0.44, 0.55), (0.5, 0.58), (0.54, 0.62), (0.52, 0.65), (0.44, 0.67), (0.36, 0.68)], e=40, n=32)
    loft('stone', 0, 0, [(0.3, 0.68), (0.3, 0.75), (0.34, 0.77)], e=40, n=32)
    dome = [(0.38 * math.cos(t) + 0.001, 0.77 + 0.4 * math.sin(t)) for t in [i * math.pi / 2 / 9 for i in range(10)]]
    loft('stone', 0, 0, dome, e=3.2, n=40)
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        nasika(nrm[0] * 0.34, nrm[1] * 0.34, 0.8, 0.11, 0.12, side, thick=0.02, out=0.05)
    loft('stone', 0, 0, [(0.07, 1.16), (0.09, 1.2), (0.05, 1.25), (0.07, 1.3), (0.01, 1.4)], e=2, n=14)


def _unit_shala():
    """A shala at unit size, long along x, outer face toward -y: plinth, pilastered body, cornice,
    a barrel vault with arched gable ends, a great kudu arch on the outer face, three finials."""
    hl, hw = 0.9, 0.42
    box('stone', 0, 0, 0.0, hl + 0.06, hw + 0.06, 0.12)
    box('stone', 0, 0, 0.12, hl, hw, 0.43)
    for i in range(7):
        u = -hl + 0.04 + i * (2 * hl - 0.08) / 6
        for sy in (-1, 1):
            box('stone', u, sy * (hw + 0.02), 0.12, 0.035, 0.03, 0.43)
    box('niche', 0, -(hw + 0.01), 0.18, 0.22, 0.01, 0.26)
    box('stone', 0, 0, 0.55, hl * 1.08, hw * 1.12, 0.07)
    box('stone', 0, 0, 0.62, hl * 1.02, hw * 1.04, 0.04)
    barrel('stone', 0, 0, 0.66, hl * 0.98, hw * 0.95, True)
    for sx, sd in ((-1, 3), (1, 1)):
        nasika(sx * hl * 0.99, 0, 0.66, hw * 0.75, hw * 0.95, sd, thick=0.03, out=0.06)
    for sd in (0, 2):
        nasika(0, (-1 if sd == 0 else 1) * hw * 0.72, 0.5, 0.36, 0.55, sd, thick=0.04, out=0.1)
    for k in (-0.6, 0, 0.6):
        loft('stone', k * hl, 0, [(0.05, 0.66 + hw * 1.15), (0.065, 0.66 + hw * 1.22), (0.04, 0.66 + hw * 1.28), (0.01, 0.66 + hw * 1.38)], e=2, n=10)


def build_units():
    """Build each pavilion once, in detail, as its own mesh."""
    units = {}
    for name, fn in (('kuta', _unit_kuta), ('shala', _unit_shala)):
        saved = (MESHES['stone'], MESHES['niche'])
        MESHES['stone'], MESHES['niche'] = bmesh.new(), bmesh.new()
        fn()
        meshes = []
        for key in ('stone', 'niche'):
            bm = MESHES[key]
            me = bpy.data.meshes.new(f'{name}_{key}')
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me); bm.free()
            for pg in me.polygons:
                pg.use_smooth = True
            meshes.append((key, me))
        MESHES['stone'], MESHES['niche'] = saved
        units[name] = meshes
    return units


def place_instances(units):
    col = bpy.data.collections.new('pavilions'); bpy.context.scene.collection.children.link(col)
    for (unit, (x, y, z), sc_, rot) in INSTANCES:
        for key, me in units[unit]:
            ob = bpy.data.objects.new(f'{unit}_{key}', me)
            ob.location = (x, y, z); ob.scale = (sc_, sc_, sc_); ob.rotation_euler = (0, 0, rot)
            col.objects.link(ob)


def pilasters(cx, cy, z0, half, h, step, depth=0.22, width=0.32):
    n = max(2, int(2 * half / step))
    for side in range(4):
        for i in range(n + 1):
            u = -half + 2 * half * i / n
            if side == 0: x, y = u, -half
            elif side == 1: x, y = half, u
            elif side == 2: x, y = u, half
            else: x, y = -half, u
            hx, hy = (width / 2, depth) if side in (0, 2) else (depth, width / 2)
            box('stone', cx + x, cy + y, z0, hx, hy, h)


def nasika(cx, cy, z0, w, h, side, thick=0.28, out=0.32):
    """A horseshoe arch (kudu) with a finial: the frame over a niche."""
    bm = MESHES['stone']
    nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
    tan = (-nrm[1], nrm[0])
    pts = []
    for i in range(23):
        th = -0.25 + (math.pi + 0.5) * i / 22   # a little past a half circle: the horseshoe
        pts.append((math.cos(th), math.sin(th)))
    def vert(u, wz, r, depth):
        return bm.verts.new((cx + tan[0] * u * w * r + nrm[0] * depth, cy + tan[1] * u * w * r + nrm[1] * depth, z0 + wz * h * r))
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
    loft('stone', fx, fy, [(w * 0.16, z0 + h * 0.92), (w * 0.2, z0 + h * 1.05), (w * 0.12, z0 + h * 1.22), (0.01, z0 + h * 1.32)], e=2.5, n=16)


def niches(cx, cy, z0, half, h, count):
    for side in range(4):
        for i in range(count):
            u = -half * 0.72 + 1.44 * half * (i / (count - 1) if count > 1 else 0.5)
            wn = min(1.4, half * 0.12)
            if side == 0: x, y, hx, hy = u, -half - 0.05, wn, 0.12
            elif side == 1: x, y, hx, hy = half + 0.05, u, 0.12, wn
            elif side == 2: x, y, hx, hy = u, half + 0.05, wn, 0.12
            else: x, y, hx, hy = -half - 0.05, u, 0.12, wn
            box('niche', cx + x, cy + y, z0 + h * 0.12, hx, hy, h * 0.62)
            nasika(cx + x, cy + y, z0 + h * 0.84, wn + 0.25, h * 0.26, side)
            # the frame: two jambs and a lintel with a small arch above
            if side in (0, 2):
                for d in (-1, 1):
                    box('stone', cx + x + d * (wn + 0.2), cy + y, z0 + h * 0.1, 0.2, 0.3, h * 0.66)
                box('stone', cx + x, cy + y, z0 + h * 0.76, wn + 0.45, 0.32, h * 0.07)
            else:
                for d in (-1, 1):
                    box('stone', cx + x, cy + y + d * (wn + 0.2), z0 + h * 0.1, 0.3, 0.2, h * 0.66)
                box('stone', cx + x, cy + y, z0 + h * 0.76, 0.32, wn + 0.45, h * 0.07)


def prastara(cx, cy, z0, half, k=1.0):
    """Beam, curved kapota cornice and the course above it (k scales it)."""
    p = [(0.1, 0), (0.1, 0.35), (0.35, 0.42), (0.9, 0.62), (1.15, 0.9), (1.1, 1.1), (0.85, 1.2), (0.2, 1.25),
         (0.2, 1.55), (0.35, 1.6), (0.35, 1.85)]
    loft('stone', cx, cy, [(half + d * k, z0 + z * k) for d, z in p], e=60, n=64)
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
                for (x, y) in ((d * u, -edge), (d * u, edge), (-edge, d * u), (edge, d * u)):
                    kuta(cx + x, cy + y, z0, s * 0.7)


def adhishthana(half, z0):
    p = [(half + 1.6, z0), (half + 1.6, z0 + 0.5), (half + 1.35, z0 + 0.55), (half + 1.35, z0 + 1.4),
         (half + 1.55, z0 + 1.5), (half + 1.55, z0 + 1.8), (half + 1.2, z0 + 1.9),
         # kumuda: the rounded torus moulding
         (half + 1.3, z0 + 2.05), (half + 1.45, z0 + 2.3), (half + 1.5, z0 + 2.6), (half + 1.45, z0 + 2.9), (half + 1.3, z0 + 3.12), (half + 1.1, z0 + 3.2),
         # kantha: the recessed neck
         (half + 0.85, z0 + 3.25), (half + 0.85, z0 + 3.8), (half + 1.25, z0 + 3.85),
         # pattika and the course above
         (half + 1.25, z0 + 4.4), (half + 0.95, z0 + 4.45), (half + 0.95, z0 + 4.85), (half + 0.4, z0 + 4.9), (half + 0.4, z0 + 5.4)]
    loft('stone', 0, 0, p, e=80, n=64)
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
            x, y = tan[0] * u + nrm[0] * (half_out + r * 0.4), tan[1] * u + nrm[1] * (half_out + r * 0.4)
            loft('stone', x, y, [(0.005, z - r), (r * 0.75, z - r * 0.6), (r, z), (r * 0.75, z + r * 0.6), (0.005, z + r)], e=2, n=10)


MESHES['inscr'] = bmesh.new()


def inscription_band(half_out, z_lo, z_hi):
    bm = MESHES['inscr']
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
            q = [(tan[0] * a + nrm[0] * (half_out + 0.008), tan[1] * a + nrm[1] * (half_out + 0.008), zz) for a, zz in ((a0, z_lo), (a1, z_lo), (a1, z_hi), (a0, z_hi))]
            f = bm.faces.new([bm.verts.new(v) for v in q])
            us = [(u_acc + (a0 + L / 2)) / (h * 32), (u_acc + (a1 + L / 2)) / (h * 32)]
            for loop, (uu, vv) in zip(f.loops, ((us[0], 0), (us[1], 0), (us[1], 1), (us[0], 1))):
                loop[uvl].uv = (uu, vv)
        u_acc += L


def base_ornament(half, z0):
    inscription_band(half + 1.25, z0 + 3.9, z0 + 4.35)
    inscription_band(half + 0.85, z0 + 3.28, z0 + 3.77)
    # inverted lotus petals on the slope below the kumuda, upright ones above the kantha
    petal_row(half + 1.22, z0 + 1.98, 0.32, 0.36, 0.42, tip_up=False)
    petal_row(half + 1.27, z0 + 3.95, 0.4, 0.4, 0.46, tip_up=True)
    # little blocks (dentils) in the recessed neck
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])
        n = int(2 * (half + 0.6) / 0.75)
        for i in range(n + 1):
            u = -(half + 0.6) + i * 2 * (half + 0.6) / n
            x, y = tan[0] * u + nrm[0] * (half + 0.95), tan[1] * u + nrm[1] * (half + 0.95)
            pass


def lotus_relief(cx, cy, z, R, side, depth=0.12, petals=None):
    """(Kept name for call sites.) A carved kolam panel: a raised ring holding a 3 x 3 grid of
    pulli dots, set in a square frame. Geometric, not floral (rule 6: no lotus)."""
    bm = MESHES['carve']
    nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
    tan = (-nrm[1], nrm[0])

    def P(u, w, d):
        return (cx + tan[0] * u + nrm[0] * d, cy + tan[1] * u + nrm[1] * d, z + w)

    def ring(r_out, r_in, d0, d1, n=64):
        o0 = [bm.verts.new(P(r_out * math.cos(2 * math.pi * i / n), r_out * math.sin(2 * math.pi * i / n), d0)) for i in range(n)]
        o1 = [bm.verts.new(P(r_out * math.cos(2 * math.pi * i / n), r_out * math.sin(2 * math.pi * i / n), d1)) for i in range(n)]
        i1 = [bm.verts.new(P(r_in * math.cos(2 * math.pi * i / n), r_in * math.sin(2 * math.pi * i / n), d1)) for i in range(n)]
        i0 = [bm.verts.new(P(r_in * math.cos(2 * math.pi * i / n), r_in * math.sin(2 * math.pi * i / n), d0)) for i in range(n)]
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((o0[i], o0[j], o1[j], o1[i])); bm.faces.new((o1[i], o1[j], i1[j], i1[i])); bm.faces.new((i1[i], i1[j], i0[j], i0[i]))

    def dome(u, w, r, d0, h, n=16):
        base = [bm.verts.new(P(u + r * math.cos(2 * math.pi * i / n), w + r * math.sin(2 * math.pi * i / n), d0)) for i in range(n)]
        mid = [bm.verts.new(P(u + r * 0.7 * math.cos(2 * math.pi * i / n), w + r * 0.7 * math.sin(2 * math.pi * i / n), d0 + h * 0.75)) for i in range(n)]
        tip = bm.verts.new(P(u, w, d0 + h))
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((base[i], base[j], mid[j], mid[i])); bm.faces.new((mid[i], mid[j], tip))

    # square frame
    f = R * 1.05
    for (u0, w0, u1, w1) in ((-f, f * 0.86, f, f), (-f, -f, f, -f * 0.86), (-f, -f, -f * 0.86, f), (f * 0.86, -f, f, f)):
        q = [bm.verts.new(P(u, w, d)) for d in (0.0, depth) for (u, w) in ((u0, w0), (u1, w0), (u1, w1), (u0, w1))]
        for fc in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            bm.faces.new([q[k] for k in fc])
    variants = [(3, 2, 0.5), (2, 3, 0.25), (3, 4, 0.3), (4, 3, 0.15), (1, 2, 0.5), (5, 4, 0.2), (2, 1, 0.25), (3, 1, 0.5)]
    vk = int(abs(cx * 7.3 + cy * 3.1 + z * 11.7)) % len(variants)
    a, b, ph = variants[vk]
    pts = []
    for i in range(361):
        t = 2 * math.pi * i / 360
        pts.append(P(R * 0.74 * math.sin(a * t + ph * math.pi), R * 0.74 * math.sin(b * t), depth * 0.9))
    tube('carve', pts, [R * 0.045] * len(pts), n=6)
    # the pulli dots the line loops around, where it allows: a grid matched to the knot
    for gu in range(-(a - 1), a, 2) if a > 1 else [0]:
        for gw in range(-(b - 1), b, 2) if b > 1 else [0]:
            dome(gu * R * 0.74 / a, gw * R * 0.74 / b, R * 0.06, 0.0, depth * 1.3)
    if vk % 3 == 0:
        ring(R * 0.92, R * 0.84, 0.0, depth * 0.8)


def storey(half, z0, h, niche_count, pil_step):
    """A wall built as Dravidian walls are: a recessed core, projecting bays, and deep niches cut into the bays."""
    core = half - 0.75
    box('stone', 0, 0, z0, core, core, h)
    wn = min(1.25, half * 0.1)          # niche half-width
    jw = 0.38                           # jamb half-width
    for side in range(4):
        nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
        tan = (-nrm[1], nrm[0])

        def place(u, d, hu, hd, z, hh):
            """A block centred u along the face and d out from the core, hu wide, hd deep."""
            x = tan[0] * u + nrm[0] * (core + d)
            y = tan[1] * u + nrm[1] * (core + d)
            hx = abs(tan[0]) * hu + abs(nrm[0]) * hd
            hy = abs(tan[1]) * hu + abs(nrm[1]) * hd
            box('stone', x, y, z, hx, hy, hh)
        # corner bays (karna): solid, the full depth
        for s in (-1, 1):
            place(s * (core - 0.9), 0.375, 1.0, 0.375, z0, h)
        for i in range(niche_count):
            u = -core * 0.68 + 1.36 * core * (i / (niche_count - 1) if niche_count > 1 else 0.5)
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
            # the carved lotus at the back of the recess, and the kudu arch over the opening
            px, py = tan[0] * u + nrm[0] * core, tan[1] * u + nrm[1] * core
            lotus_relief(px, py, z0 + h * 0.43, wn * 0.62, side)
            nasika(tan[0] * u + nrm[0] * (core + 0.75), tan[1] * u + nrm[1] * (core + 0.75), z0 + h * 0.8, wn + 0.3, h * 0.2, side, out=0.2)
            # slim pilasters on the recessed wall between bays
            if i < niche_count - 1:
                u2 = -core * 0.68 + 1.36 * core * ((i + 0.5) / (niche_count - 1))
                for k in (-1, 1):
                    place(u2 + k * 0.9, 0.12, 0.13, 0.12, z0 + h * 0.06, h * 0.86)
                kx, ky = tan[0] * u2 + nrm[0] * (core + 0.22), tan[1] * u2 + nrm[1] * (core + 0.22)
                zb = z0 + h * 0.1
                loft('stone', kx, ky, [(0.12, zb), (0.28, zb + 0.12), (0.34, zb + 0.32), (0.28, zb + 0.5), (0.14, zb + 0.58), (0.2, zb + 0.66), (0.1, zb + 0.7)], e=2.4, n=20)
                place(u2, 0.22, 0.11, 0.1, zb + 0.7, h * 0.48)
                place(u2, 0.26, 0.2, 0.12, zb + 0.7 + h * 0.48, 0.14)
                nasika(tan[0] * u2 + nrm[0] * (core + 0.3), tan[1] * u2 + nrm[1] * (core + 0.3), zb + 0.86 + h * 0.48, 0.42, h * 0.14, side, out=0.12)
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
        box('stone', 0, 0, z, half_t - 0.3, half_t - 0.3, h_t)
        pilasters(0, 0, z, half_t - 0.2, h_t, 1.1 + f * 0.3, depth=0.14, width=0.2)
        z = prastara(0, 0, z + h_t, half_t - 0.9, k)
        hara(0, 0, z - 0.15, half_t - 0.1, 2.0 - f * 0.75)
        z += 0.25
    # griva, shikhara with four great nasika arches, and the kalasa
    gh = 3.1
    loft('stone', 0, 0, [(4.55, z), (4.55, z + gh)], e=2, n=8, phase=math.pi / 8)
    for k in range(8):
        a = 2 * math.pi * k / 8
        loft('stone', 4.25 * math.cos(a), 4.25 * math.sin(a), [(0.22, z + 0.2), (0.22, z + gh - 0.2)], e=40, n=8)
    z += gh
    loft('stone', 0, 0, [(5.2, z), (5.5, z + 0.3), (5.4, z + 0.6)], e=2, n=8, phase=math.pi / 8)
    z += 0.6
    dome = [(5.0 * math.cos(a) * (1 + 0.08 * math.sin(a)) + 0.01, z + 5.2 * math.sin(a)) for a in [i * math.pi / 2 / 14 for i in range(15)]]
    loft('stone', 0, 0, [(r * 1.08, zz) for r, zz in dome], e=2, n=8, phase=math.pi / 8)
    for ang in range(4):
        a = ang * math.pi / 2
        dx, dy = math.cos(a), math.sin(a)
        arch = []
        # a horseshoe arch standing out from the dome face
        for i in range(17):
            th = math.pi * i / 16
            arch.append((2.3 * math.cos(th), 2.7 * math.sin(th)))
        bm = MESHES['stone']
        outer, inner = [], []
        for (u, w) in arch:
            for r, lst in ((1.0, outer), (0.72, inner)):
                p = Vector((-dy * u * r, dx * u * r, z + 0.6 + w * r)) + Vector((dx, dy, 0)) * (4.55 - 0.15 * w)
                lst.append(bm.verts.new(p))
        for i in range(16):
            bm.faces.new((outer[i], outer[i + 1], inner[i + 1], inner[i]))
    z += 5.2
    k = [(1.2, z - 0.2), (1.25, z + 0.1), (0.9, z + 0.25), (1.05, z + 0.5), (1.2, z + 0.9), (1.05, z + 1.35), (0.55, z + 1.6),
         (0.6, z + 1.8), (0.32, z + 2.0), (0.42, z + 2.4), (0.3, z + 2.8), (0.12, z + 3.2), (0.18, z + 3.4), (0.01, z + 3.9)]
    loft('gold', 0, 0, k, e=2, n=48)
    return z + 3.9


def courtyard():
    box('floor', 0, 0, -0.3, 260, 260, 0.3)
    # a cloister on three sides: a low wall with a colonnade in front
    for (cx, cy, hx, hy) in ((0, 95, 120, 1.2), (-120, 0, 1.2, 95), (120, 0, 1.2, 95)):
        box('wall', cx, cy, 0, hx, hy, 6.5)
        box('wall', cx, cy, 6.5, hx + (2.6 if hx < 5 else 0), hy + (2.6 if hy < 5 else 0), 0.7)
    for i in range(-36, 37):
        u = i * 3.2
        for (x, y) in ((u, 92), (-117, u * 0.8), (117, u * 0.8)):
            if abs(x) <= 118 and abs(y) <= 93:
                box('wall', x, y, 0, 0.45, 0.45, 6.5)


MESHES['grass'] = bmesh.new()
MESHES['path'] = bmesh.new()
MESHES['flame'] = bmesh.new()


def mandapa(x0, x1, hy):
    """The pillared hall in front of the tower: moulded base, pilastered walls, cornice, a hara of pavilions."""
    cx, hx = (x0 + x1) / 2, abs(x1 - x0) / 2
    z = 0.0
    for (d, h) in ((1.4, 0.6), (1.15, 0.9), (1.3, 0.7), (0.9, 0.5), (1.15, 0.6), (0.6, 0.6)):
        box('stone', cx, 0, z, hx + d, hy + d, h); z += h
    wall_h = 7.0
    box('stone', cx, 0, z, hx, hy, wall_h)
    for i in range(int(2 * hx / 2.0) + 1):
        u = x0 + i * 2.0 if x0 < x1 else x1 + i * 2.0
        for sy in (-1, 1):
            box('stone', u, sy * (hy + 0.12), z, 0.18, 0.22, wall_h)
    for i in range(int(2 * hy / 2.0) + 1):
        v = -hy + i * 2.0
        box('stone', min(x0, x1) - 0.12, v, z, 0.22, 0.18, wall_h)
    for i in range(int(2 * hx / 5.0)):
        u = min(x0, x1) + 2.5 + i * 5.0
        for sy, side in ((-1, 0), (1, 2)):
            # a framed panel: jamb pilasters with capitals, a carved lotus, a kudu arch above
            for d in (-1, 1):
                box('stone', u + d * 1.25, sy * (hy + 0.3), z + 0.5, 0.22, 0.3, 4.6)
                box('stone', u + d * 1.25, sy * (hy + 0.35), z + 5.1, 0.36, 0.36, 0.25)
            box('stone', u, sy * (hy + 0.3), z + 0.3, 1.5, 0.32, 0.25)
            box('stone', u, sy * (hy + 0.32), z + 5.35, 1.6, 0.34, 0.3)
            lotus_relief(u, sy * hy, z + 2.9, 0.75, side)
            nasika(u, sy * (hy + 0.35), z + 5.7, 1.1, 1.3, side, out=0.2)
    z += wall_h
    for (d, h) in ((0.3, 0.3), (0.8, 0.35), (1.2, 0.35), (1.0, 0.25), (0.4, 0.4)):
        box('stone', cx, 0, z, hx + d, hy + d, h); z += h
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
    loft('stone', x, y, [(1.3, 0), (1.3, 0.6), (1.0, 0.7), (1.0, 1.4), (0.75, 1.5)], e=40, n=32)
    loft('stone', x, y, [(0.42, 1.5), (0.36, h * 0.92), (0.5, h * 0.95), (0.5, h), (0.2, h + 0.4), (0.25, h + 0.7), (0.02, h + 1.1)], e=7, n=32)
    rings = 9
    for r in range(rings):
        z = 2.4 + (h - 3.0) * r / (rings - 1)
        rad = 0.85 - 0.25 * r / rings
        loft('stone', x, y, [(0.4, z - 0.08), (rad, z), (rad, z + 0.06), (0.4, z + 0.1)], e=8, n=32)
        for k in range(8):
            a = 2 * math.pi * k / 8 + r * 0.2
            px, py = x + rad * 0.9 * math.cos(a), y + rad * 0.9 * math.sin(a)
            loft('gold', px, py, [(0.02, z + 0.06), (0.07, z + 0.1), (0.06, z + 0.14)], e=2, n=8)
            loft('flame', px, py, [(0.005, z + 0.13), (0.035, z + 0.18), (0.02, z + 0.25), (0.002, z + 0.33)], e=2, n=8)


MESHES['blade'] = bmesh.new()


def grass_blades(cam_xy, fwd_angle, count=220000, seed=3, spread=0.75, reach=80, keep_out=()):
    """Real blades near the camera: curved, tapered, leaning, in tufts; the lawn shader covers the distance."""
    import random
    rnd = random.Random(seed)
    bm = MESHES['blade']
    cx, cy = cam_xy
    for i in range(count):
        dist = 1.5 + reach * (rnd.random() ** 2.0)
        ang = fwd_angle + rnd.uniform(-spread, spread)
        x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
        if -46 < x < -34 and y > -140:   # keep the paved path clear
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
        for s, (u, ww) in enumerate(((0, 1.0), (0.45, 0.8), (0.8, 0.45), (1.0, 0.0))):
            off = lean * h * u * u
            pts.append(((x + dx * off - px * ww, y + dy * off - py * ww, h * u),
                        (x + dx * off + px * ww, y + dy * off + py * ww, h * u)))
        vs = [(bm.verts.new(l), bm.verts.new(r)) for l, r in pts]
        for (l0, r0), (l1, r1) in zip(vs, vs[1:]):
            bm.faces.new((l0, r0, r1, l1))


def grounds():
    # a paved processional path toward the hall, lawns on either side
    box('path', -40, -70, 0.0, 6.5, 70, 0.04)
    box('path', -40, -6, 0.0, 30, 28, 0.03)
    box('path', 0, -64, 0.0, 34, 50, 0.05)
    box('path', 0, -130, 0.0, 40, 20, 0.05)
    for (cx, cy, hx, hy) in ((-90, -70, 40, 70), (10, -80, 36, 60), (60, -20, 50, 60)):
        box('grass', cx, cy, 0.0, hx, hy, 0.02)


MESHES['trunk'] = bmesh.new()
MESHES['leaf'] = bmesh.new()


def tube(key, path, radii, n=10):
    bm = MESHES[key]
    rings = []
    for i, (p, r) in enumerate(zip(path, radii)):
        p = Vector(p)
        t = (Vector(path[min(i + 1, len(path) - 1)]) - Vector(path[max(i - 1, 0)])).normalized()
        a = t.orthogonal().normalized(); b = t.cross(a)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / n) * a + math.sin(2 * math.pi * k / n) * b)) for k in range(n)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((r0[k], r0[(k + 1) % n], r1[(k + 1) % n], r1[k]))


MESHES['deadleaf'] = bmesh.new()
MESHES['banana'] = bmesh.new()
MESHES['fruit'] = bmesh.new()
MESHES['heart'] = bmesh.new()
MESHES['bstem'] = bmesh.new()
MESHES['midrib'] = bmesh.new()


def leaflet(bm, base, direction, side, length, width, droop, fold):
    """One pinna: a narrow blade that arches out and down, folded along its midrib."""
    pts = []
    for k in range(5):
        u = k / 4
        c = base + direction * (length * u) + Vector((0, 0, -droop * length * u * u))
        w = width * math.sin(math.pi * min(0.999, 0.15 + 0.85 * u)) * (1 - 0.7 * u)
        pts.append((c - side * w + Vector((0, 0, -fold * w)), c + Vector((0, 0, fold * w * 0.6)), c + side * w + Vector((0, 0, -fold * w))))
    vs = [[bm.verts.new(q) for q in row] for row in pts]
    for a, b in zip(vs, vs[1:]):
        bm.faces.new((a[0], a[1], b[1], b[0]))
        bm.faces.new((a[1], a[2], b[2], b[1]))


def palm(x, y, height, lean, heading, seed, detail=1.0):
    """A coconut palm: a swollen base, a leaning ringed trunk, a crown of arching fronds
    whose leaflets hang more toward the tip, a few dead fronds, and a cluster of nuts."""
    import random
    rnd = random.Random(seed)
    path, radii = [], []
    for i in range(32):
        f = i / 31
        bend = lean * height * (f ** 1.7)
        wob = 0.12 * math.sin(f * 7 + seed)
        path.append((x + bend * math.cos(heading) + wob * math.sin(heading), y + bend * math.sin(heading) - wob * math.cos(heading), height * f))
        radii.append(0.27 - 0.09 * f + 0.16 * max(0.0, 0.12 - f) / 0.12)
    tube('trunk', path, radii, n=14)
    crown = Vector(path[-1])
    loft('trunk', crown.x, crown.y, [(0.2, crown.z - 0.6), (0.34, crown.z - 0.2), (0.28, crown.z + 0.15), (0.05, crown.z + 0.4)], e=2, n=14)
    nf = int(30 * detail) + 4
    for k in range(nf):
        az = 2 * math.pi * k * 0.618 + rnd.uniform(-0.12, 0.12)
        age = k / (nf - 1)
        dead = age > 0.9
        bm = MESHES['deadleaf' if dead else 'leaf']
        rise = 1.15 - 1.7 * age + rnd.uniform(-0.15, 0.15)
        length = rnd.uniform(4.8, 6.4) * (0.7 if age < 0.12 else 1.0)
        d = Vector((math.cos(az), math.sin(az), 0))
        side = Vector((-d.y, d.x, 0))
        segs = int(34 * detail) + 6
        spine = []
        for t in range(segs + 1):
            u = t / segs
            hang = 1.6 if dead else 0.55
            spine.append(crown + d * length * u * (1 - 0.3 * max(0, -rise) * u) + Vector((0, 0, length * (rise * 0.6 * u - hang * u * u))))
        tube('deadleaf' if dead else 'trunk', spine[:int(segs * 0.6)], [0.045 - 0.03 * i / max(1, int(segs * 0.6) - 1) for i in range(int(segs * 0.6))], n=5)
        for t in range(2, segs):
            u = t / segs
            base = spine[t]
            fwd = (spine[t + 1] - spine[t - 1]).normalized()
            for sd in (-1, 1):
                ll = (1.55 * math.sin(math.pi * min(1, u * 1.04)) ** 0.6) * (1 - 0.35 * u) + 0.12
                out = (side * sd * 0.92 + fwd * 0.38).normalized()
                leaflet(bm, base, out, fwd * 0.5, ll, 0.045, 0.35 + 0.55 * u + rnd.uniform(-0.1, 0.1), 0.6)
    for c in range(int(rnd.uniform(5, 11))):
        a = 2 * math.pi * c / 8 + rnd.uniform(-0.2, 0.2)
        q = crown + Vector((0.4 * math.cos(a), 0.4 * math.sin(a), -0.45 + rnd.uniform(-0.15, 0.1)))
        loft('fruit', q.x, q.y, [(0.01, q.z - 0.2), (0.15, q.z - 0.1), (0.17, q.z + 0.04), (0.12, q.z + 0.14), (0.01, q.z + 0.21)], e=2, n=12)


def banana(x, y, height, heading, seed, fruit=True):
    """A banana plant (vazhai): a mottled, sheathed pseudostem, broad cupped leaves on arching
    petioles, torn along their veins, a rolled young leaf at the top, and on some a bunch with its heart."""
    import random
    rnd = random.Random(seed)
    stem = [(x, y, 0)] + [(x + 0.04 * math.sin(i), y, height * i / 10) for i in range(1, 11)]
    tube('bstem', stem, [0.34 - 0.17 * i / 10 for i in range(11)], n=20)
    top = Vector(stem[-1])
    # the rolled cigar leaf at the crown
    tube('banana', [top, top + Vector((0.02, 0, 0.7)), top + Vector((0.06, 0.02, 1.25))], [0.07, 0.05, 0.015], n=8)
    nleaves = 11
    for k in range(nleaves):
        az = heading + 2 * math.pi * k * 0.382 + rnd.uniform(-0.2, 0.2)
        age = k / (nleaves - 1)
        d = Vector((math.cos(az), math.sin(az), 0)); side = Vector((-d.y, d.x, 0))
        # a petiole that rises, then the blade that arches out and droops with age
        pet_len = 0.7 + 0.3 * rnd.random()
        rise0 = 1.25 - 1.1 * age
        p0 = top + Vector((0, 0, -0.25 * age))
        p1 = p0 + d * pet_len * 0.6 + Vector((0, 0, pet_len * rise0 * 0.7))
        tube('bstem', [p0, p0.lerp(p1, 0.5) + Vector((0, 0, 0.05)), p1], [0.05, 0.04, 0.03], n=8)
        length = rnd.uniform(2.4, 3.1) * (0.65 if k < 2 else 1)
        segs = 30
        spine = []
        for t in range(segs + 1):
            u = t / segs
            spine.append(p1 + d * length * u + Vector((0, 0, length * (0.55 * rise0 * u - (0.55 + 0.6 * age) * u * u))))
        tube('midrib', spine, [0.025 - 0.02 * t / segs for t in range(segs + 1)], n=6)
        old = age > 0.8
        bm = MESHES['deadleaf' if old and rnd.random() < 0.6 else 'banana']
        torn_from = rnd.uniform(0.35, 0.8)
        for t in range(segs):
            u = t / segs
            w = 0.58 * math.sin(math.pi * min(0.999, 0.03 + 0.97 * u)) ** 0.45
            for sd in (-1, 1):
                tear = (u > torn_from and rnd.random() < 0.22 + 0.3 * age)
                if tear:
                    continue
                a0, a1 = spine[t], spine[t + 1]
                # the blade cups: rises a little from the midrib, then falls to the edge
                m0 = a0 + side * sd * w * 0.5 + Vector((0, 0, 0.05 * w)); m1 = a1 + side * sd * w * 0.5 + Vector((0, 0, 0.05 * w))
                e0 = a0 + side * sd * w + Vector((0, 0, -0.16 * w)); e1 = a1 + side * sd * w + Vector((0, 0, -0.16 * w))
                v = [bm.verts.new(q) for q in (a0, a1, m1, m0, e0, e1)]
                bm.faces.new((v[0], v[1], v[2], v[3]))
                bm.faces.new((v[3], v[2], v[5], v[4]))
    if fruit:
        stalk = [top, top + Vector((0.35, 0.1, -0.2)), top + Vector((0.5, 0.15, -0.9))]
        tube('banana', stalk, [0.04, 0.035, 0.03], n=6)
        c = stalk[-1]
        for h in range(6):
            for f in range(10):
                a = 2 * math.pi * f / 10
                bz = c.z + 0.32 - h * 0.13
                b0 = Vector((c.x + 0.09 * math.cos(a), c.y + 0.09 * math.sin(a), bz))
                b1 = b0 + Vector((0.16 * math.cos(a), 0.16 * math.sin(a), 0.12))
                tube('fruit', [b0, b0.lerp(b1, 0.5) + Vector((0, 0, -0.02)), b1], [0.02, 0.026, 0.012], n=6)
        loft('heart', c.x, c.y, [(0.01, c.z - 0.75), (0.09, c.z - 0.55), (0.11, c.z - 0.4), (0.06, c.z - 0.25), (0.02, c.z - 0.15)], e=2, n=14)


def grove():
    import random
    rnd = random.Random(7)
    spots = [(-34, -118, 15.5), (-22, -128, 12.5)]  # foreground, framing the left of the shot
    for i in range(70):  # a skyline of palms beyond the cloister
        spots.append((rnd.uniform(-230, 240), rnd.uniform(102, 190), rnd.uniform(15, 26)))
    for i in range(24):
        spots.append((rnd.uniform(126, 200), rnd.uniform(-120, 100), rnd.uniform(14, 24)))
    for i, (x, y, h) in enumerate(spots):
        palm(x, y, h, rnd.uniform(0.04, 0.16), rnd.uniform(0, 2 * math.pi), i, detail=1.0 if i < 2 else 0.45)
    # banana plants flanking the path, as at a festive entrance
    for j, (bx, by) in enumerate(((-62, -114), (-41, -127), (-49, -96), (-31, -92))):
        banana(bx, by, rnd.uniform(3.6, 4.6), rnd.uniform(0, 6.28), 100 + j, fruit=(j < 3))


MESHES['bird'] = bmesh.new()


def birds(n=26, seed=11):
    import random
    rnd = random.Random(seed)
    bm = MESHES['bird']
    cx, cy, cz = 40.0, 120.0, 95.0
    for i in range(n):
        x, y, z = cx + rnd.gauss(0, 45), cy + rnd.gauss(0, 30), cz + rnd.gauss(0, 14)
        span = rnd.uniform(0.9, 1.6); flap = rnd.uniform(-0.35, 0.45); yaw = rnd.uniform(-0.4, 0.4) + 0.3
        dx, dy = math.cos(yaw), math.sin(yaw)
        body = [Vector((x - dx * 0.35, y - dy * 0.35, z)), Vector((x + dx * 0.4, y + dy * 0.4, z + 0.02))]
        tube('bird', body, [0.07, 0.04], n=6)
        for sd in (-1, 1):
            sx, sy = -dy * sd, dx * sd
            root0 = Vector((x - dx * 0.12, y - dy * 0.12, z)); root1 = Vector((x + dx * 0.15, y + dy * 0.15, z))
            elbow = Vector((x + sx * span * 0.5, y + sy * span * 0.5, z + flap * span * 0.5))
            tip = Vector((x + sx * span - dx * 0.25, y + sy * span - dy * 0.25, z + flap * span * 0.6 - 0.1))
            v = [bm.verts.new(q) for q in (root0, root1, elbow, tip)]
            bm.faces.new((v[0], v[1], v[2])); bm.faces.new((v[0], v[2], v[3]))


def pillar(x, y, h=4.6):
    """A Chola-style pillar: moulded base, square blocks (saduram) alternating with octagonal
    sections (kattu), a vase-shaped capital, a square abacus and a bracket (potika) with rolled ends."""
    loft('stone', x, y, [(0.62, 0), (0.62, 0.25), (0.55, 0.3), (0.55, 0.55), (0.5, 0.6)], e=60, n=24)
    z = 0.6
    kz = h / 4.6
    for k, (kind, hh) in enumerate((('sq', 0.75), ('oct', 0.55), ('sq', 0.7), ('oct', 0.55), ('sq', 0.6))):
        hh *= kz
        if kind == 'sq':
            box('stone', x, y, z, 0.4, 0.4, hh)
            # a kolam knot carved on each face of the middle block
            if k == 2:
                for side in range(4):
                    nrm = [(0, -1), (1, 0), (0, 1), (-1, 0)][side]
                    lotus_relief(x + nrm[0] * 0.4, y + nrm[1] * 0.4, z + hh / 2, 0.24, side, depth=0.03)
        else:
            loft('stone', x, y, [(0.4, z), (0.33, z + 0.06), (0.33, z + hh - 0.06), (0.4, z + hh)], e=2, n=8)
        z += hh
    # capital: neck, the vase (kalasa), the dish, the abacus (palagai)
    loft('stone', x, y, [(0.3, z), (0.26, z + 0.12), (0.36, z + 0.3), (0.42, z + 0.42), (0.3, z + 0.5), (0.48, z + 0.62)], e=2.2, n=24)
    z += 0.62
    box('stone', x, y, z, 0.55, 0.55, 0.12); z += 0.12
    # the bracket: arms in both directions, stepped, with a rolled (bevelled) end
    for (ax, ay) in ((1, 0), (0, 1)):
        box('stone', x, y, z, 0.95 if ax else 0.22, 0.22 if ax else 0.95, 0.22)
        for sgn in (-1, 1):
            box('stone', x + ax * sgn * 0.85, y + ay * sgn * 0.85, z - 0.16, 0.12 if ax else 0.2, 0.2 if ax else 0.12, 0.16)
    return z + 0.22


def pavilion(cx, cy, nx=4, ny=4, sp=3.3):
    """An open pillared pavilion (mandapa) on a moulded platform, roofed with stone slabs and beams."""
    hx, hy = (nx - 1) * sp / 2, (ny - 1) * sp / 2
    for (d, hh) in ((2.2, 0.35), (1.9, 0.35), (1.6, 0.3)):
        box('stone', cx, cy, -0.3 + 0.0, hx + d, hy + d, hh + 0.3)
    box('path', cx, cy, 0.35, hx + 1.4, hy + 1.4, 0.04)
    top_z = 0
    for i in range(nx):
        for j in range(ny):
            px, py = cx - hx + i * sp, cy - hy + j * sp
            ztop = pillar(px, py + 0.0, 6.6)
            top_z = ztop
    # pillars sit on the platform: lift them by moving the whole pavilion origin up is avoided; the
    # platform top is at about 1.0 m, so the pillars stand from the ground inside the platform rim
    for i in range(nx):
        box('stone', cx - hx + i * sp, cy, top_z, 0.3, hy + 0.6, 0.45)
    for j in range(ny):
        box('stone', cx, cy - hy + j * sp, top_z + 0.45, hx + 0.6, 0.3, 0.4)
    box('stone', cx, cy, top_z + 0.85, hx + 1.3, hy + 1.3, 0.35)
    loft('stone', cx, cy, [(hx + 1.3, top_z + 1.2), (hx + 1.75, top_z + 1.45), (hx + 1.8, top_z + 1.65), (hx + 1.5, top_z + 1.75), (hx + 0.9, top_z + 1.8)], e=40, n=64, aspect=(hy + 1.3) / (hx + 1.3))
    return top_z


top = build()
birds()
HALL_TOP = pavilion(0.0, -115.0)
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
        loft('gold', x, y, [(0.02, z), (0.07, z + 0.01), (0.09, z + 0.05), (0.06, z + 0.07), (0.075, z + 0.09)], e=2, n=12)
        loft('flame', x, y, [(0.004, z + 0.085), (0.025, z + 0.12), (0.015, z + 0.17), (0.002, z + 0.23)], e=2, n=8)
        LAMP_SPOTS.append((x, y, z + 0.16))


MESHES['rice'] = bmesh.new()


def ground_kolam(cx, cy, z, size, a=5, b=4, ph=0.5):
    pts = [(cx + size * math.sin(a * t + ph * math.pi), cy + size * math.sin(b * t), z) for t in [2 * math.pi * i / 900 for i in range(901)]]
    tube('rice', pts, [0.011] * len(pts), n=5)
    for i in range(-(a - 1), a, 2):
        for j in range(-(b - 1), b, 2):
            loft('rice', cx + i * size / a, cy + j * size / b, [(0.035, z - 0.005), (0.03, z + 0.008)], e=2, n=10)


ground_kolam(0.0, -101.6, 0.075, 2.3, a=3, b=2, ph=0.5)
ground_kolam(0.0, -21.5, 0.075, 1.8, a=4, b=3, ph=0.25)
lamp_row(-6.0, 6.0, -105.2, 0.4, 1.0)          # the front step of the hall
lamp_row(-13.0, 13.0, -18.4, 0.35, 1.3)         # along the temple's base
grounds()
grass_blades((-72.0, -138.0), math.atan2(138.0, 102.0), keep_out=((-35, -115, 35, 15), (-41, -151, 41, -109), (-71, -35, -9, 23)))
if len(argv) > 4 and argv[4] == 'close':
    grass_blades((-34.0, -44.0), math.atan2(29.0, 32.0), count=90000, seed=5, spread=0.9, reach=30, keep_out=((-71, -35, -9, 23), (-30, -35, 20, -16)))


# ---------- materials ----------
def mat_stone(name, base_a, base_b, rough=0.82):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N['Principled BSDF']
    pos = N.new('ShaderNodeNewGeometry')
    noise = N.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 0.9; noise.inputs['Detail'].default_value = 9
    noise.inputs['Roughness'].default_value = 0.62
    L.new(pos.outputs['Position'], noise.inputs['Vector'])
    # weathering: large dark patches where water and lichen sit
    lich = N.new('ShaderNodeTexNoise'); lich.inputs['Scale'].default_value = 0.22; lich.inputs['Detail'].default_value = 6
    L.new(pos.outputs['Position'], lich.inputs['Vector'])
    lr = N.new('ShaderNodeMapRange'); lr.inputs['From Min'].default_value = 0.5; lr.inputs['From Max'].default_value = 0.68
    lr.inputs['To Min'].default_value = 1.0; lr.inputs['To Max'].default_value = 0.55
    L.new(lich.outputs['Fac'], lr.inputs['Value'])
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*base_b, 1); ramp.color_ramp.elements[1].color = (*base_a, 1)
    L.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    # rain streaks: noise stretched downwards
    mapn = N.new('ShaderNodeMapping'); mapn.inputs['Scale'].default_value = (3.0, 3.0, 0.15)
    L.new(pos.outputs['Position'], mapn.inputs['Vector'])
    streak = N.new('ShaderNodeTexNoise'); streak.inputs['Scale'].default_value = 2.0; streak.inputs['Detail'].default_value = 3
    L.new(mapn.outputs['Vector'], streak.inputs['Vector'])
    sramp = N.new('ShaderNodeMapRange'); sramp.inputs['From Min'].default_value = 0.45; sramp.inputs['From Max'].default_value = 0.7
    sramp.inputs['To Min'].default_value = 1.0; sramp.inputs['To Max'].default_value = 0.72
    L.new(streak.outputs['Fac'], sramp.inputs['Value'])
    # crevices darken: ambient occlusion
    ao = N.new('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = 1.2; ao.samples = 8
    aor = N.new('ShaderNodeMapRange'); aor.inputs['From Min'].default_value = 0.0; aor.inputs['From Max'].default_value = 1.0
    aor.inputs['To Min'].default_value = 0.28; aor.inputs['To Max'].default_value = 1.0
    L.new(ao.outputs['AO'], aor.inputs['Value'])
    m1 = N.new('ShaderNodeMix'); m1.data_type = 'RGBA'; m1.blend_type = 'MULTIPLY'; m1.inputs['Factor'].default_value = 1.0
    L.new(ramp.outputs['Color'], m1.inputs['A'])
    comb = N.new('ShaderNodeMath'); comb.operation = 'MULTIPLY'
    L.new(sramp.outputs['Result'], comb.inputs[0]); L.new(aor.outputs['Result'], comb.inputs[1])
    comb2 = N.new('ShaderNodeMath'); comb2.operation = 'MULTIPLY'
    L.new(comb.outputs['Value'], comb2.inputs[0]); L.new(lr.outputs['Result'], comb2.inputs[1])
    # granite blocks: courses about 0.6 m high, joints staggered, as the temple was laid dry
    sep = N.new('ShaderNodeSeparateXYZ'); L.new(pos.outputs['Position'], sep.inputs['Vector'])
    hsum = N.new('ShaderNodeMath'); hsum.operation = 'ADD'
    L.new(sep.outputs['X'], hsum.inputs[0]); L.new(sep.outputs['Y'], hsum.inputs[1])
    bv = N.new('ShaderNodeCombineXYZ'); L.new(hsum.outputs['Value'], bv.inputs['X']); L.new(sep.outputs['Z'], bv.inputs['Y'])
    brick = N.new('ShaderNodeTexBrick'); brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Brick Width'].default_value = 1.45; brick.inputs['Row Height'].default_value = 0.62
    brick.inputs['Mortar Size'].default_value = 0.012; brick.inputs['Mortar Smooth'].default_value = 0.3
    brick.inputs['Color1'].default_value = (1, 1, 1, 1); brick.inputs['Color2'].default_value = (0.82, 0.82, 0.82, 1)
    brick.inputs['Bias'].default_value = 0.0
    L.new(bv.outputs['Vector'], brick.inputs['Vector'])
    joint = N.new('ShaderNodeMapRange'); joint.inputs['To Min'].default_value = 1.0; joint.inputs['To Max'].default_value = 0.6
    L.new(brick.outputs['Fac'], joint.inputs['Value'])
    perblock = N.new('ShaderNodeMix'); perblock.data_type = 'RGBA'; perblock.blend_type = 'MULTIPLY'; perblock.inputs['Factor'].default_value = 1.0
    L.new(comb2.outputs['Value'], perblock.inputs['A']); L.new(brick.outputs['Color'], perblock.inputs['B'])
    blk = N.new('ShaderNodeMath'); blk.operation = 'MULTIPLY'
    sepc = N.new('ShaderNodeSeparateColor'); L.new(perblock.outputs['Result'], sepc.inputs['Color'])
    L.new(sepc.outputs['Red'], blk.inputs[0]); L.new(joint.outputs['Result'], blk.inputs[1])
    L.new(blk.outputs['Value'], m1.inputs['B'])
    L.new(m1.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = rough
    # surface: fine grain and chipped edges, and the block joints pressed in
    bn = N.new('ShaderNodeTexNoise'); bn.inputs['Scale'].default_value = 28; bn.inputs['Detail'].default_value = 10
    vor = N.new('ShaderNodeTexVoronoi'); vor.inputs['Scale'].default_value = 6
    L.new(pos.outputs['Position'], bn.inputs['Vector']); L.new(pos.outputs['Position'], vor.inputs['Vector'])
    add0 = N.new('ShaderNodeMath'); add0.operation = 'ADD'
    L.new(bn.outputs['Fac'], add0.inputs[0]); L.new(vor.outputs['Distance'], add0.inputs[1])
    add = N.new('ShaderNodeMath'); add.operation = 'MULTIPLY_ADD'
    L.new(brick.outputs['Fac'], add.inputs[0]); add.inputs[1].default_value = -1.2; L.new(add0.outputs['Value'], add.inputs[2])
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.35; bump.inputs['Distance'].default_value = 0.04
    L.new(add.outputs['Value'], bump.inputs['Height']); L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def mat_simple(name, color, rough, metal=0.0):
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    return m


def mat_floor():
    m = bpy.data.materials.new('floor')
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    br = N.new('ShaderNodeTexBrick')
    br.inputs['Scale'].default_value = 0.6
    br.inputs['Color1'].default_value = (0.42, 0.2, 0.11, 1)
    br.inputs['Color2'].default_value = (0.5, 0.28, 0.15, 1)
    br.inputs['Mortar'].default_value = (0.22, 0.12, 0.07, 1)
    br.inputs['Mortar Size'].default_value = 0.01
    br.offset = 0.0; br.squash = 1.0
    br.inputs['Brick Width'].default_value = 1.0; br.inputs['Row Height'].default_value = 1.0
    pos = N.new('ShaderNodeNewGeometry')
    L.new(pos.outputs['Position'], br.inputs['Vector'])
    L.new(br.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.58
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.2
    L.new(br.outputs['Fac'], bump.inputs['Height']); L.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def mat_foliage(name, c0, c1, trans, trans_amount):
    m = bpy.data.materials.new(name)
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    pos = N.new('ShaderNodeNewGeometry')
    nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 1.6; nz.inputs['Detail'].default_value = 5
    L.new(pos.outputs['Position'], nz.inputs['Vector'])
    cr = N.new('ShaderNodeValToRGB')
    cr.color_ramp.elements[0].color = (*c0, 1); cr.color_ramp.elements[1].color = (*c1, 1)
    L.new(nz.outputs['Fac'], cr.inputs['Fac']); L.new(cr.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.5
    tr = N.new('ShaderNodeBsdfTranslucent'); tr.inputs['Color'].default_value = (*trans, 1)
    mix = N.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = trans_amount
    L.new(b.outputs['BSDF'], mix.inputs[1]); L.new(tr.outputs['BSDF'], mix.inputs[2]); L.new(mix.outputs['Shader'], N['Material Output'].inputs['Surface'])
    return m


def mat_leaf():
    m = bpy.data.materials.new('leaf')
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    pos = N.new('ShaderNodeNewGeometry')
    nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 0.7
    L.new(pos.outputs['Position'], nz.inputs['Vector'])
    cr = N.new('ShaderNodeValToRGB')
    cr.color_ramp.elements[0].color = (0.05, 0.1, 0.02, 1); cr.color_ramp.elements[1].color = (0.2, 0.26, 0.06, 1)
    L.new(nz.outputs['Fac'], cr.inputs['Fac']); L.new(cr.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.55
    tr = N.new('ShaderNodeBsdfTranslucent'); tr.inputs['Color'].default_value = (0.35, 0.42, 0.08, 1)
    mix = N.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = 0.35
    out = N['Material Output']
    L.new(b.outputs['BSDF'], mix.inputs[1]); L.new(tr.outputs['BSDF'], mix.inputs[2]); L.new(mix.outputs['Shader'], out.inputs['Surface'])
    return m


def mat_trunk():
    m = bpy.data.materials.new('trunk')
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    pos = N.new('ShaderNodeNewGeometry')
    wave = N.new('ShaderNodeTexWave'); wave.wave_type = 'BANDS'; wave.bands_direction = 'Z'
    wave.inputs['Scale'].default_value = 0.35; wave.inputs['Distortion'].default_value = 1.5
    L.new(pos.outputs['Position'], wave.inputs['Vector'])
    cr = N.new('ShaderNodeValToRGB')
    cr.color_ramp.elements[0].color = (0.12, 0.1, 0.08, 1); cr.color_ramp.elements[1].color = (0.32, 0.27, 0.21, 1)
    L.new(wave.outputs['Fac'], cr.inputs['Fac']); L.new(cr.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.9
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.6
    L.new(wave.outputs['Fac'], bump.inputs['Height']); L.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def mat_grass():
    m = bpy.data.materials.new("grass"); nt = m.node_tree; N, L = nt.nodes, nt.links; b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.25; nz.inputs["Detail"].default_value = 10
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB"); cr.color_ramp.elements[0].color = (0.05, 0.09, 0.015, 1); cr.color_ramp.elements[1].color = (0.15, 0.18, 0.045, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"]); L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    fine = N.new("ShaderNodeTexNoise"); fine.inputs["Scale"].default_value = 60; L.new(pos.outputs["Position"], fine.inputs["Vector"])
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6
    L.new(fine.outputs["Fac"], bump.inputs["Height"]); L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_blade():
    m = bpy.data.materials.new("blade"); nt = m.node_tree; N, L = nt.nodes, nt.links; b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.6; nz.inputs["Detail"].default_value = 4
    L.new(pos.outputs["Position"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB"); cr.color_ramp.elements[0].color = (0.04, 0.09, 0.012, 1); cr.color_ramp.elements[1].color = (0.2, 0.24, 0.05, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"]); L.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.6
    b.inputs["Subsurface Weight"].default_value = 0.2
    return m


def mat_path():
    m = bpy.data.materials.new("path"); nt = m.node_tree; N, L = nt.nodes, nt.links; b = N["Principled BSDF"]
    pos = N.new("ShaderNodeNewGeometry")
    br = N.new("ShaderNodeTexBrick"); br.inputs["Scale"].default_value = 0.35
    br.inputs["Color1"].default_value = (0.36, 0.3, 0.24, 1); br.inputs["Color2"].default_value = (0.26, 0.21, 0.17, 1)
    br.inputs["Mortar"].default_value = (0.1, 0.08, 0.06, 1); br.inputs["Mortar Size"].default_value = 0.012; br.inputs["Bias"].default_value = 0.0
    L.new(pos.outputs["Position"], br.inputs["Vector"]); L.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.7
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.3
    L.new(br.outputs["Fac"], bump.inputs["Height"]); L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_flame():
    m = bpy.data.materials.new("flame"); nt = m.node_tree; N, L = nt.nodes, nt.links
    em = N.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (1.0, 0.78, 0.45, 1); em.inputs["Strength"].default_value = 22 if GRADE != 'blue' else 6
    L.new(em.outputs["Emission"], N["Material Output"].inputs["Surface"])
    return m


TEX = __import__('os').path.join(__import__('os').path.dirname(__file__), 'tex')


def mat_scan(name, folder, size_m, tint=(1, 1, 1), weather=True, normal_strength=1.0, blend=0.25, displace=0.0):
    """A scanned PBR material (CC0, Poly Haven), box-projected in world space at its real size,
    with ambient-occlusion grime, rain streaks and lichen laid over it when weather=True."""
    import os
    m = bpy.data.materials.new(name)
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    tc = N.new('ShaderNodeTexCoord')
    mp = N.new('ShaderNodeMapping'); s = 1.0 / size_m; mp.inputs['Scale'].default_value = (s, s, s)
    oi = N.new('ShaderNodeObjectInfo')
    rnd = N.new('ShaderNodeVectorMath'); rnd.operation = 'SCALE'; L.new(oi.outputs['Random'], rnd.inputs['Vector']); rnd.inputs['Scale'].default_value = 53.0
    addv = N.new('ShaderNodeVectorMath'); addv.operation = 'ADD'
    L.new(tc.outputs['Object'], addv.inputs[0]); L.new(rnd.outputs['Vector'], addv.inputs[1])
    L.new(addv.outputs['Vector'], mp.inputs['Vector'])

    def img(file, non_color):
        t = N.new('ShaderNodeTexImage'); t.projection = 'BOX'; t.projection_blend = blend
        hi = os.path.join(TEX, folder, '4k', file)
        t.image = bpy.data.images.load(hi if (os.path.exists(hi) and QUALITY == 'final') else os.path.join(TEX, folder, file))
        if non_color:
            t.image.colorspace_settings.name = 'Non-Color'
        L.new(mp.outputs['Vector'], t.inputs['Vector'])
        return t

    dif, nor, rgh = img('Diffuse.jpg', False), img('nor_gl.jpg', True), img('Rough.jpg', True)
    col = N.new('ShaderNodeMix'); col.data_type = 'RGBA'; col.blend_type = 'MULTIPLY'; col.inputs['Factor'].default_value = 1.0
    bc = N.new('ShaderNodeBrightContrast'); bc.inputs['Bright'].default_value = 0.04; bc.inputs['Contrast'].default_value = -0.28
    L.new(dif.outputs['Color'], bc.inputs['Color'])
    L.new(bc.outputs['Color'], col.inputs['A']); col.inputs['B'].default_value = (*tint, 1)
    last = col.outputs['Result']
    if weather:
        pos = N.new('ShaderNodeNewGeometry')
        ao = N.new('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = 1.0; ao.samples = 8
        aor = N.new('ShaderNodeMapRange'); aor.inputs['To Min'].default_value = 0.3
        L.new(ao.outputs['AO'], aor.inputs['Value'])
        mapn = N.new('ShaderNodeMapping'); mapn.inputs['Scale'].default_value = (3.0, 3.0, 0.12)
        L.new(pos.outputs['Position'], mapn.inputs['Vector'])
        st = N.new('ShaderNodeTexNoise'); st.inputs['Scale'].default_value = 2.2; st.inputs['Detail'].default_value = 4
        L.new(mapn.outputs['Vector'], st.inputs['Vector'])
        sr = N.new('ShaderNodeMapRange'); sr.inputs['From Min'].default_value = 0.48; sr.inputs['From Max'].default_value = 0.72
        sr.inputs['To Min'].default_value = 1.0; sr.inputs['To Max'].default_value = 0.6
        L.new(st.outputs['Fac'], sr.inputs['Value'])
        li = N.new('ShaderNodeTexNoise'); li.inputs['Scale'].default_value = 0.25; li.inputs['Detail'].default_value = 6
        L.new(pos.outputs['Position'], li.inputs['Vector'])
        lr = N.new('ShaderNodeMapRange'); lr.inputs['From Min'].default_value = 0.52; lr.inputs['From Max'].default_value = 0.7
        lr.inputs['To Min'].default_value = 1.0; lr.inputs['To Max'].default_value = 0.62
        L.new(li.outputs['Fac'], lr.inputs['Value'])
        f1 = N.new('ShaderNodeMath'); f1.operation = 'MULTIPLY'; L.new(aor.outputs['Result'], f1.inputs[0]); L.new(sr.outputs['Result'], f1.inputs[1])
        f2a = N.new('ShaderNodeMath'); f2a.operation = 'MULTIPLY'; L.new(f1.outputs['Value'], f2a.inputs[0]); L.new(lr.outputs['Result'], f2a.inputs[1])
        # faces that look at the sky hold water: dark lichen in patches
        sepn = N.new('ShaderNodeSeparateXYZ'); L.new(pos.outputs['Normal'], sepn.inputs['Vector'])
        up = N.new('ShaderNodeMapRange'); up.inputs['From Min'].default_value = 0.45; up.inputs['From Max'].default_value = 0.95
        L.new(sepn.outputs['Z'], up.inputs['Value'])
        pn = N.new('ShaderNodeTexNoise'); pn.inputs['Scale'].default_value = 1.8; pn.inputs['Detail'].default_value = 8; pn.inputs['Roughness'].default_value = 0.7
        L.new(pos.outputs['Position'], pn.inputs['Vector'])
        pr = N.new('ShaderNodeMapRange'); pr.inputs['From Min'].default_value = 0.42; pr.inputs['From Max'].default_value = 0.62
        L.new(pn.outputs['Fac'], pr.inputs['Value'])
        upm = N.new('ShaderNodeMath'); upm.operation = 'MULTIPLY'; L.new(up.outputs['Result'], upm.inputs[0]); L.new(pr.outputs['Result'], upm.inputs[1])
        upd = N.new('ShaderNodeMapRange'); upd.inputs['To Min'].default_value = 1.0; upd.inputs['To Max'].default_value = 0.6
        L.new(upm.outputs['Value'], upd.inputs['Value'])
        # long monsoon drip streaks: thin vertical noise, strongest a little below each course
        mapd = N.new('ShaderNodeMapping'); mapd.inputs['Scale'].default_value = (9.0, 9.0, 0.35)
        L.new(pos.outputs['Position'], mapd.inputs['Vector'])
        dn = N.new('ShaderNodeTexNoise'); dn.inputs['Scale'].default_value = 3.0; dn.inputs['Detail'].default_value = 2
        L.new(mapd.outputs['Vector'], dn.inputs['Vector'])
        dr = N.new('ShaderNodeMapRange'); dr.inputs['From Min'].default_value = 0.55; dr.inputs['From Max'].default_value = 0.75
        dr.inputs['To Min'].default_value = 1.0; dr.inputs['To Max'].default_value = 0.76
        L.new(dn.outputs['Fac'], dr.inputs['Value'])
        f2b = N.new('ShaderNodeMath'); f2b.operation = 'MULTIPLY'; L.new(f2a.outputs['Value'], f2b.inputs[0]); L.new(upd.outputs['Result'], f2b.inputs[1])
        f2 = N.new('ShaderNodeMath'); f2.operation = 'MULTIPLY'; L.new(f2b.outputs['Value'], f2.inputs[0]); L.new(dr.outputs['Result'], f2.inputs[1])
        g = N.new('ShaderNodeMix'); g.data_type = 'RGBA'; g.blend_type = 'MULTIPLY'; g.inputs['Factor'].default_value = 1.0
        L.new(last, g.inputs['A']); L.new(f2.outputs['Value'], g.inputs['B'])
        last = g.outputs['Result']
    if weather:
        bev = N.new('ShaderNodeBevel'); bev.samples = 6; bev.inputs['Radius'].default_value = 0.035
        geo2 = N.new('ShaderNodeNewGeometry')
        dot = N.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
        L.new(bev.outputs['Normal'], dot.inputs[0]); L.new(geo2.outputs['Normal'], dot.inputs[1])
        edge = N.new('ShaderNodeMapRange'); edge.inputs['From Min'].default_value = 0.995; edge.inputs['From Max'].default_value = 0.93
        L.new(dot.outputs['Value'], edge.inputs['Value'])
        wear = N.new('ShaderNodeMix'); wear.data_type = 'RGBA'; wear.blend_type = 'SCREEN'
        L.new(edge.outputs['Result'], wear.inputs['Factor']); L.new(last, wear.inputs['A']); wear.inputs['B'].default_value = (0.22, 0.2, 0.17, 1)
        last = wear.outputs['Result']
    L.new(last, b.inputs['Base Color'])
    L.new(rgh.outputs['Color'], b.inputs['Roughness'])
    nm = N.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = normal_strength
    L.new(nor.outputs['Color'], nm.inputs['Color']); L.new(nm.outputs['Normal'], b.inputs['Normal'])
    if displace > 0:
        hgt = img('Displacement.png', True)
        dn = N.new('ShaderNodeDisplacement'); dn.inputs['Midlevel'].default_value = 0.5; dn.inputs['Scale'].default_value = displace
        L.new(hgt.outputs['Color'], dn.inputs['Height']); L.new(dn.outputs['Displacement'], N['Material Output'].inputs['Displacement'])
        m.displacement_method = 'BOTH'; m.max_vertex_displacement = displace * 1.2
    return m


def mat_inscription():
    import os
    m = mat_scan('inscr', 'large_sandstone_blocks', 3.4, displace=0.07, tint=((1.45, 1.14, 0.8) if GRADE == 'gold' else (1.34, 1.12, 0.86)), normal_strength=1.15)
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    uv = N.new('ShaderNodeUVMap')
    t = N.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(os.path.join(TEX, 'inscription.png')); t.image.colorspace_settings.name = 'Non-Color'
    t.extension = 'REPEAT'
    L.new(uv.outputs['UV'], t.inputs['Vector'])
    # carved letters: darker inside the groove, pressed into the stone
    base_col = b.inputs['Base Color'].links[0].from_socket
    dark = N.new('ShaderNodeMix'); dark.data_type = 'RGBA'; dark.blend_type = 'MULTIPLY'
    L.new(t.outputs['Color'], dark.inputs['Factor']); L.new(base_col, dark.inputs['A']); dark.inputs['B'].default_value = (0.45, 0.4, 0.36, 1)
    L.new(dark.outputs['Result'], b.inputs['Base Color'])
    nrm_src = b.inputs['Normal'].links[0].from_socket
    bump = N.new('ShaderNodeBump'); bump.invert = True; bump.inputs['Strength'].default_value = 0.9; bump.inputs['Distance'].default_value = 0.01
    L.new(t.outputs['Color'], bump.inputs['Height']); L.new(nrm_src, bump.inputs['Normal'])
    L.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


MATS = {
    'carve': mat_scan('carve', 'large_sandstone_blocks', 3.4, tint=((1.45, 1.14, 0.8) if GRADE == 'gold' else (1.34, 1.12, 0.86)), normal_strength=0.6),
    'inscr': mat_inscription(),
    'rice': mat_simple('rice', (0.86, 0.84, 0.8), 0.95),
    'bird': mat_simple('bird', (0.05, 0.045, 0.04), 0.8),
    'leaf': mat_leaf(),
    'deadleaf': mat_foliage('deadleaf', (0.18, 0.12, 0.05), (0.42, 0.3, 0.14), (0.5, 0.32, 0.1), 0.25),
    'banana': mat_foliage('banana', (0.07, 0.15, 0.025), (0.2, 0.3, 0.06), (0.4, 0.55, 0.1), 0.4),
    'bstem': mat_foliage('bstem', (0.08, 0.07, 0.03), (0.17, 0.19, 0.07), (0.25, 0.25, 0.08), 0.05),
    'midrib': mat_foliage('midrib', (0.28, 0.32, 0.12), (0.42, 0.45, 0.2), (0.4, 0.45, 0.2), 0.1),
    'fruit': mat_foliage('fruit', (0.16, 0.3, 0.04), (0.36, 0.42, 0.08), (0.4, 0.5, 0.1), 0.1),
    'heart': mat_foliage('heart', (0.12, 0.02, 0.05), (0.25, 0.05, 0.1), (0.3, 0.05, 0.08), 0.05),
    'trunk': mat_scan('trunk', 'palm_tree_bark', 1.3, tint=(0.75, 0.66, 0.55), weather=False),
    'stone': mat_scan('stone', 'large_sandstone_blocks', 3.4, displace=0.07, tint=((1.45, 1.14, 0.8) if GRADE == 'gold' else (1.34, 1.12, 0.86)), normal_strength=1.15),
    'wall': mat_scan('wall', 'large_sandstone_blocks', 3.4, displace=0.06, tint=((1.4, 1.1, 0.8) if GRADE == 'gold' else (1.3, 1.1, 0.86)), normal_strength=1.0),
    'gold': mat_simple('gold', (1.0, 0.7, 0.3), 0.22, 1.0),
    'niche': mat_simple('niche', (0.05, 0.035, 0.03), 0.9),
    'floor': mat_scan('floor', 'red_sandstone_pavement', 2.15, tint=(1.0, 0.85, 0.72), weather=False),
    'grass': mat_scan('grass', 'grass_path_2', 1.0, tint=(0.8, 0.85, 0.6), weather=False),
    'blade': mat_blade(),
    'path': mat_scan('path', 'red_sandstone_pavement', 2.15, displace=0.03, tint=(1.05, 0.9, 0.78), weather=False),
    'flame': mat_flame(),
}

UNITS = build_units()
for unit_meshes in UNITS.values():
    for key, me in unit_meshes:
        me.materials.append(MATS['carve'] if key == 'stone' else MATS['niche'])
place_instances(UNITS)
print('INSTANCES', len(INSTANCES))

for key, bm in MESHES.items():
    me = bpy.data.meshes.new(key)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(key, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(MATS[key])
    for p in me.polygons:
        p.use_smooth = True
    if key in ('stone', 'wall'):
        bv = ob.modifiers.new('bevel', 'BEVEL'); bv.width = 0.035; bv.segments = 2; bv.limit_method = 'ANGLE'
        bv.angle_limit = math.radians(40); bv.harden_normals = True
    ws = ob.modifiers.new('wn', 'WEIGHTED_NORMAL'); ws.keep_sharp = True
    if key in ('stone', 'wall', 'path', 'inscr'):
        sd = ob.modifiers.new('detail', 'SUBSURF'); sd.subdivision_type = 'SIMPLE'
        sd.use_adaptive_subdivision = True; sd.adaptive_pixel_size = 2.0 if QUALITY == 'final' else 4.0

# ---------- light, sky, camera ----------
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
for dev_type in ('CUDA',):
    try:
        prefs.compute_device_type = dev_type; prefs.get_devices()
        if any(d.type == dev_type for d in prefs.devices):
            break
    except Exception as e:
        print('NOGPU', dev_type, e)
for d in prefs.devices:
    d.use = d.type == prefs.compute_device_type
    print('DEVICE', d.type, d.name, d.use)
sc.cycles.device = 'GPU' if any(d.use for d in prefs.devices) else 'CPU'
print('RENDER_DEVICE', sc.cycles.device, prefs.compute_device_type)
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.view_settings.view_transform = 'AgX'
try:
    sc.view_settings.look = 'AgX - Punchy'
except Exception:
    pass
sc.view_settings.exposure = {'gold': 0.2, 'blue': 1.9, 'noon': -0.3}.get(GRADE, 0.1)

world = bpy.data.worlds.new('sky'); sc.world = world
wn = world.node_tree.nodes; wl = world.node_tree.links
sky = wn.new('ShaderNodeTexSky'); sky.sky_type = 'MULTIPLE_SCATTERING'
SUN_EL, SUN_ROT = (math.radians(12), math.radians(252)) if (len(argv) > 4 and argv[4] == 'hall') else (math.radians(16), math.radians(307))
if GRADE == 'gold':
    SUN_EL = math.radians(7)
elif GRADE == 'blue':
    SUN_EL = math.radians(-3.5)
elif GRADE == 'noon':
    SUN_EL = math.radians(52)
sky.sun_elevation = SUN_EL; sky.sun_rotation = SUN_ROT
sky.aerosol_density = 1.4; sky.air_density = 1.0


def world_clouds():
    """A painted cloud layer in the world shader: a noise field projected on a high plane."""
    tc = wn.new('ShaderNodeTexCoord')
    sep = wn.new('ShaderNodeSeparateXYZ'); wl.new(tc.outputs['Generated'], sep.inputs['Vector'])
    zden = wn.new('ShaderNodeMath'); zden.operation = 'ADD'; zden.inputs[1].default_value = 0.06
    wl.new(sep.outputs['Z'], zden.inputs[0])
    ux = wn.new('ShaderNodeMath'); ux.operation = 'DIVIDE'; wl.new(sep.outputs['X'], ux.inputs[0]); wl.new(zden.outputs['Value'], ux.inputs[1])
    uy = wn.new('ShaderNodeMath'); uy.operation = 'DIVIDE'; wl.new(sep.outputs['Y'], uy.inputs[0]); wl.new(zden.outputs['Value'], uy.inputs[1])
    comb = wn.new('ShaderNodeCombineXYZ'); wl.new(ux.outputs['Value'], comb.inputs['X']); wl.new(uy.outputs['Value'], comb.inputs['Y'])
    mp = wn.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (0.9, 2.2, 1.0)
    wl.new(comb.outputs['Vector'], mp.inputs['Vector'])
    cn = wn.new('ShaderNodeTexNoise'); cn.inputs['Scale'].default_value = 1.4; cn.inputs['Detail'].default_value = 12
    cn.inputs['Roughness'].default_value = 0.62; cn.inputs['Distortion'].default_value = 0.35
    wl.new(mp.outputs['Vector'], cn.inputs['Vector'])
    cover = wn.new('ShaderNodeMapRange'); cover.inputs['From Min'].default_value = 0.5; cover.inputs['From Max'].default_value = 0.72
    wl.new(cn.outputs['Fac'], cover.inputs['Value'])
    # only above the horizon, thinning near it
    hz = wn.new('ShaderNodeMapRange'); hz.inputs['From Min'].default_value = 0.01; hz.inputs['From Max'].default_value = 0.12
    wl.new(sep.outputs['Z'], hz.inputs['Value'])
    mask = wn.new('ShaderNodeMath'); mask.operation = 'MULTIPLY'
    wl.new(cover.outputs['Result'], mask.inputs[0]); wl.new(hz.outputs['Result'], mask.inputs[1])
    # lit undersides warm, shadowed parts a dusky violet
    shade = wn.new('ShaderNodeTexNoise'); shade.inputs['Scale'].default_value = 2.6; shade.inputs['Detail'].default_value = 6
    wl.new(mp.outputs['Vector'], shade.inputs['Vector'])
    cr = wn.new('ShaderNodeValToRGB')
    cr.color_ramp.elements[0].color = (0.46, 0.47, 0.55, 1); cr.color_ramp.elements[1].color = (1.55, 1.48, 1.38, 1)
    wl.new(shade.outputs['Fac'], cr.inputs['Fac'])
    # sunrise: a band of saffron and orange low on the horizon, fading into the blue above
    glow = wn.new('ShaderNodeMapRange'); glow.inputs['From Min'].default_value = 0.0; glow.inputs['From Max'].default_value = 0.42
    glow.inputs['To Min'].default_value = 0.45; glow.inputs['To Max'].default_value = 0.0
    wl.new(sep.outputs['Z'], glow.inputs['Value'])
    gramp = wn.new('ShaderNodeValToRGB')
    gramp.color_ramp.elements[0].color = (0.62, 0.7, 0.82, 1); gramp.color_ramp.elements[1].color = (1.05, 0.98, 0.86, 1)
    wl.new(glow.outputs['Result'], gramp.inputs['Fac'])
    warm = wn.new('ShaderNodeMix'); warm.data_type = 'RGBA'
    wl.new(glow.outputs['Result'], warm.inputs['Factor']); wl.new(sky.outputs['Color'], warm.inputs['A']); wl.new(gramp.outputs['Color'], warm.inputs['B'])
    mix = wn.new('ShaderNodeMix'); mix.data_type = 'RGBA'
    wl.new(mask.outputs['Value'], mix.inputs['Factor']); wl.new(warm.outputs['Result'], mix.inputs['A']); wl.new(cr.outputs['Color'], mix.inputs['B'])
    return mix.outputs['Result']


wl.new(world_clouds(), wn['Background'].inputs['Color'])
env = wn.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(os.path.join(TEX, 'hdri', 'sky_2k.hdr'))
bg_light = wn.new('ShaderNodeBackground'); wl.new(env.outputs['Color'], bg_light.inputs['Color'])
bg_light.inputs['Strength'].default_value = {'blue': 0.05, 'noon': 0.6}.get(GRADE, 0.45)
lp = wn.new('ShaderNodeLightPath'); mixw = wn.new('ShaderNodeMixShader')
wl.new(lp.outputs['Is Camera Ray'], mixw.inputs['Fac']); wl.new(bg_light.outputs['Background'], mixw.inputs[1]); wl.new(wn['Background'].outputs['Background'], mixw.inputs[2])
wl.new(mixw.outputs['Shader'], wn['World Output'].inputs['Surface'])


def volume_clouds():
    """Real 3D clouds: a thin slab of noise-shaped volume high above, lit by the low sun."""
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 1400, 700))
    dom = bpy.context.object; dom.name = 'clouds'; dom.scale = (3200, 1800, 120)
    m = bpy.data.materials.new('clouds'); nt = m.node_tree; N, L = nt.nodes, nt.links
    N.remove(N['Principled BSDF'])
    pos = N.new('ShaderNodeNewGeometry')
    mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (0.0028, 0.005, 0.012)
    L.new(pos.outputs['Position'], mp.inputs['Vector'])
    nz = N.new('ShaderNodeTexNoise'); nz.noise_dimensions = '3D'; nz.inputs['Scale'].default_value = 1.0
    nz.inputs['Detail'].default_value = 9; nz.inputs['Roughness'].default_value = 0.6; nz.inputs['Distortion'].default_value = 0.2
    L.new(mp.outputs['Vector'], nz.inputs['Vector'])
    dens = N.new('ShaderNodeMapRange'); dens.inputs['From Min'].default_value = 0.56; dens.inputs['From Max'].default_value = 0.78
    dens.inputs['To Min'].default_value = 0.0; dens.inputs['To Max'].default_value = 0.06
    L.new(nz.outputs['Fac'], dens.inputs['Value'])
    tc = N.new('ShaderNodeTexCoord'); sep = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs['Vector'])
    prof = N.new('ShaderNodeMath'); prof.operation = 'ABSOLUTE'; L.new(sep.outputs['Z'], prof.inputs[0])
    fall = N.new('ShaderNodeMapRange'); fall.inputs['From Min'].default_value = 0.2; fall.inputs['From Max'].default_value = 1.0
    fall.inputs['To Min'].default_value = 1.0; fall.inputs['To Max'].default_value = 0.0
    L.new(prof.outputs['Value'], fall.inputs['Value'])
    mul = N.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; L.new(dens.outputs['Result'], mul.inputs[0]); L.new(fall.outputs['Result'], mul.inputs[1])
    vol = N.new('ShaderNodeVolumePrincipled')
    vol.inputs['Color'].default_value = (1.0, 0.92, 0.86, 1); vol.inputs['Anisotropy'].default_value = 0.55
    L.new(mul.outputs['Value'], vol.inputs['Density'])
    L.new(vol.outputs['Volume'], N['Material Output'].inputs['Volume'])
    m.cycles.volume_step_rate = 0.5
    dom.data.materials.append(m)


if '--volclouds' in argv:
    volume_clouds()
    # the real clouds replace the painted ones
    for nd in wn:
        if nd.bl_idname == 'ShaderNodeMix' and nd.inputs['Factor'].is_linked and nd.outputs['Result'].links and nd.outputs['Result'].links[0].to_node == wn['Background']:
            wl.remove(nd.inputs['Factor'].links[0]); nd.inputs['Factor'].default_value = 0.0

wn['Background'].inputs['Strength'].default_value = {'blue': 0.5, 'noon': 0.12}.get(GRADE, 0.16)

sun_data = bpy.data.lights.new('sun', 'SUN'); sun_data.energy = 7.5; sun_data.color = (1.0, 0.84, 0.6); sun_data.angle = math.radians(1.2)
if GRADE == 'gold':
    sun_data.energy = 9.0; sun_data.color = (1.0, 0.8, 0.52)
elif GRADE == 'blue':
    sun_data.energy = 0.0
elif GRADE == 'noon':
    sun_data.energy = 6.0; sun_data.color = (1.0, 0.97, 0.92)
sun = bpy.data.objects.new('sun', sun_data); sc.collection.objects.link(sun)
d = Vector((math.cos(SUN_EL) * math.sin(SUN_ROT), -math.cos(SUN_EL) * math.cos(SUN_ROT), math.sin(SUN_EL)))
sun.rotation_mode = 'QUATERNION'
sun.rotation_quaternion = (-d).to_track_quat('-Z', 'Y')

# haze: a thin volume over the courtyard
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 60))
fog = bpy.context.object; fog.scale = (520, 520, 120); fog.name = 'haze'
fm = bpy.data.materials.new('haze'); fnt = fm.node_tree
fnt.nodes.remove(fnt.nodes['Principled BSDF'])
vs = fnt.nodes.new('ShaderNodeVolumePrincipled'); vs.inputs['Density'].default_value = 0.00045
vs.inputs['Color'].default_value = (0.92, 0.93, 0.96, 1); vs.inputs['Anisotropy'].default_value = 0.55
fnt.links.new(vs.outputs['Volume'], fnt.nodes['Material Output'].inputs['Volume'])
fog.data.materials.append(fm)
sc.cycles.volume_step_rate = 4.0

cam_data = bpy.data.cameras.new('cam'); cam_data.lens = 35
cam = bpy.data.objects.new('cam', cam_data); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (-72.0, -138.0, 1.75)
target = Vector((30.0, 0.0, top * 0.4))
cam.rotation_mode = 'QUATERNION'
if len(argv) > 4 and argv[4] == "hall":
    cam.location = (0.0, -118.3, 1.7); target = Vector((0.0, 0.0, 24.0)); cam_data.lens = 30
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, -115, 5))
    dust = bpy.context.object; dust.scale = (6.5, 6.5, 5)
    dm = bpy.data.materials.new('dust'); dn = dm.node_tree
    dn.nodes.remove(dn.nodes['Principled BSDF'])
    dv = dn.nodes.new('ShaderNodeVolumePrincipled'); dv.inputs['Density'].default_value = 0.01
    dv.inputs['Color'].default_value = (1.0, 0.95, 0.88, 1); dv.inputs['Anisotropy'].default_value = 0.6
    dn.links.new(dv.outputs['Volume'], dn.nodes['Material Output'].inputs['Volume'])
    dust.data.materials.append(dm)
if len(argv) > 4 and argv[4] == "low":
    cam.location = (-21.0, -36.0, 1.6); target = Vector((0.0, 0.0, 52.0)); cam_data.lens = 18
if len(argv) > 4 and argv[4] == "aerial":
    cam.location = (-125.0, -175.0, 92.0); target = Vector((-5.0, -25.0, 14.0)); cam_data.lens = 32
if len(argv) > 4 and argv[4] == "base":
    cam.location = (-7.5, -23.5, 2.6); target = Vector((-3.0, -15.9, 3.7)); cam_data.lens = 40
if len(argv) > 4 and argv[4] == "close":
    cam.location = (-34.0, -44.0, 1.6); target = Vector((-2.0, -15.0, 9.0)); cam_data.lens = 28
cam.rotation_quaternion = (target - cam.location).to_track_quat("-Z", "Y")
cam_data.dof.use_dof = True; cam_data.dof.focus_distance = (target - cam.location).length; cam_data.dof.aperture_fstop = 2.8

if GRADE == 'blue':
    for (x, y, z) in LAMP_SPOTS:
        ld = bpy.data.lights.new('lamp', 'POINT'); ld.energy = 14; ld.color = (1.0, 0.72, 0.42); ld.shadow_soft_size = 0.05
        lo = bpy.data.objects.new('lamp', ld); lo.location = (x, y, z); sc.collection.objects.link(lo)
sc.cycles.offscreen_dicing_scale = 40.0
sc.cycles.max_subdivisions = 5


def finishing():
    ng = bpy.data.node_groups.new('finish', 'CompositorNodeTree')
    sc.compositing_node_group = ng
    N, L = ng.nodes, ng.links
    rl = N.new('CompositorNodeRLayers')
    gl = N.new('CompositorNodeGlare')
    try:
        gl.inputs['Type'].default_value = 'Bloom'
    except Exception as e:
        print('GLARE TYPE', e)
    gl.inputs['Threshold'].default_value = 0.85; gl.inputs['Strength'].default_value = 0.22; gl.inputs['Size'].default_value = 0.6 if gl.inputs['Size'].type == 'VALUE' else gl.inputs['Size'].default_value
    L.new(rl.outputs['Image'], gl.inputs['Image'])
    cb = N.new('CompositorNodeColorBalance')
    try:
        cb.inputs['Type'].default_value = 'Offset/Power/Slope (ASC-CDL)'
    except Exception:
        pass
    L.new(gl.outputs['Image'], cb.inputs['Image'])
    ld = N.new('CompositorNodeLensdist'); ld.inputs['Distortion'].default_value = -0.012; ld.inputs['Dispersion'].default_value = 0.004
    L.new(cb.outputs['Image'], ld.inputs['Image'])
    last = ld.outputs['Image']
    try:
        em = N.new('CompositorNodeEllipseMask'); em.inputs['Size'].default_value = (0.98, 0.95)
        bl = N.new('CompositorNodeBlur'); bl.inputs['Size'].default_value = (220, 220) if bl.inputs['Size'].type == 'VECTOR' else 220
        L.new(em.outputs['Mask'], bl.inputs['Image'])
        mx = N.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs['Factor'].default_value = 0.35
        inv = N.new('ShaderNodeMapRange'); inv.inputs['To Min'].default_value = 0.55; inv.inputs['To Max'].default_value = 1.0
        L.new(bl.outputs['Image'], inv.inputs['Value'])
        L.new(last, mx.inputs['A']); L.new(inv.outputs['Result'], mx.inputs['B'])
        last = mx.outputs['Result']
    except Exception as e:
        print('VIGNETTE', e)
    out = N.new('NodeGroupOutput')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    L.new(last, out.inputs[0])


finishing()
sc.render.filepath = OUT
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('DONE', OUT, 'height', round(top, 1), 'faces', sum(len(o.data.polygons) for o in sc.objects if o.type == 'MESH'))
