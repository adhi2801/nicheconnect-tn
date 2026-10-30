"""The deal's seal, cast in bronze, made in Blender from code (D-142).

Colyv's signature in place of a kolam (Adhi, 30 October 2026): the deal's own
fingerprint drawn as a guilloche, the engraving banknotes carry because it is
hard to forge, in raised gold on a cast bronze disc. Its waves come from the
fingerprint's bytes by the same rule as the website's seal
(`frontend/prototypes/fold/fold-screens.js`, `sealParams`), so the object and the
screen always agree. Raised gold appears only on what cannot change
(TAMIL_DESIGN_ROOTS 5, 12.5); the bronze is Swamimalai's material (12.6).

The rim carries the date the way Tamil accountants wrote it (LANDING_CULTURE_FIT,
Part D): the old signs for day, month and year (U+0BF3 to U+0BF5) before Tamil
numerals in their traditional, non-positional form, then the fingerprint. The
font is Noto Sans Tamil Bold, under the SIL Open Font License (fonts/OFL.txt).

Run:
  blender -b --factory-startup --python seal.py -- out.png 1600 1600 128 [fp=a3f977c1]
"""

import itertools
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
OUT = argv[0] if argv else "//seal.png"
W = int(argv[1]) if len(argv) > 1 else 1600
H = int(argv[2]) if len(argv) > 2 else 1600
SAMPLES = int(argv[3]) if len(argv) > 3 else 128
FP = next((a.split("=", 1)[1] for a in argv if a.startswith("fp=")), "a3f977c1")
HERE = os.path.dirname(os.path.abspath(__file__))

# 30 October 2026, in traditional Tamil numerals: day 3 x 10, month 10,
# year 2 x 1000 + 2 x 10 + 6, each after its ledger sign.
DATE = "௳ ௩௰   ௴ ௰   ௵ ௨௲௨௰௬"

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene

# ---------- the fingerprint's waves (the website's rule, sealParams) ----------
b = [int(FP[i : i + 2], 16) for i in (0, 2, 4, 6)]
M = 5 + b[0] % 5
NW = 13 + b[1] % 8
PH = b[2] / 255 * math.pi * 2
LINES = 7
FIELD_R = 0.74  # the field's radius, inside the rim
TOP = 0.165  # the field's height


def rho(t, j, band):
    d = j / LINES * math.pi * 2
    if band == 0:
        return FIELD_R * (
            0.74 + 0.15 * math.sin(M * t + d) + 0.05 * math.sin(NW * t + PH + d)
        )
    return FIELD_R * (0.38 + 0.06 * math.sin((M + 3) * t + d + PH))


# ---------- the disc: a revolved profile ----------
PROFILE = [
    (0.0, 0.150),
    (0.40, 0.155),
    (0.78, 0.165),
    (0.80, 0.168),
    (0.815, 0.195),  # the inner lip of the rim
    (0.84, 0.205),
    (0.975, 0.205),  # the rim's flat, where the inscription runs
    (0.995, 0.19),
    (1.0, 0.165),
    (1.0, 0.04),  # the cast edge
    (0.99, 0.012),
    (0.97, 0.0),
    (0.0, 0.0),
]


def revolve(profile, segs=256):
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
            continue
        rings.append(
            [
                bm.verts.new(
                    (
                        r * math.cos(2 * math.pi * i / segs),
                        r * math.sin(2 * math.pi * i / segs),
                        z,
                    )
                )
                for i in range(segs)
            ]
        )
    for a, c in itertools.pairwise(rings):
        if len(a) == 1 and len(c) == 1:
            continue
        for i in range(segs):
            j = (i + 1) % segs
            if len(a) == 1:
                bm.faces.new((a[0], c[j], c[i]))
            elif len(c) == 1:
                bm.faces.new((a[i], a[j], c[0]))
            else:
                bm.faces.new((a[i], a[j], c[j], c[i]))
    me = bpy.data.meshes.new("disc")
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("disc", me)
    sc.collection.objects.link(ob)
    return ob


disc = revolve(PROFILE)
mod = disc.modifiers.new("subd", "SUBSURF")
mod.levels = mod.render_levels = 1


# ---------- the engraving: raised gold wire ----------
def wire(points, radius, name):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for p, (x, y, z) in zip(sp.points, points, strict=True):
        p.co = (x, y, z, 1)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(ob)
    return ob


GOLD_PARTS = []
STEPS = 1440
for j in range(LINES):
    pts = []
    for i in range(STEPS):
        t = 2 * math.pi * i / STEPS
        r = rho(t, j, 0)
        pts.append(
            (r * math.cos(t), r * math.sin(t), TOP + 0.004 + 0.003 * (r / FIELD_R))
        )
    GOLD_PARTS.append(wire(pts, 0.0042, f"band{j}"))
for j in range(4):
    pts = []
    for i in range(STEPS):
        t = 2 * math.pi * i / STEPS
        r = rho(t, j, 1)
        pts.append(
            (r * math.cos(t), r * math.sin(t), TOP - 0.004 + 0.003 * (r / FIELD_R))
        )
    GOLD_PARTS.append(wire(pts, 0.0036, f"inner{j}"))
for f in (0.995, 1.04):
    pts = [
        (
            FIELD_R * f * math.cos(2 * math.pi * i / STEPS),
            FIELD_R * f * math.sin(2 * math.pi * i / STEPS),
            TOP + 0.006,
        )
        for i in range(STEPS)
    ]
    GOLD_PARTS.append(wire(pts, 0.0035, f"border{f}"))

# ---------- the inscription on the rim ----------
font = bpy.data.fonts.load(os.path.join(HERE, "fonts", "NotoSansTamil.ttf"))
circle = bpy.data.curves.new("rimpath", "CURVE")
circle.dimensions = "2D"
sp = circle.splines.new("POLY")
RIM_R = 0.905
n = 256
sp.points.add(n - 1)
for i, p in enumerate(sp.points):
    a = (
        -2 * math.pi * i / n + math.pi / 2
    )  # clockwise from the top, so it reads left to right
    p.co = (RIM_R * math.cos(a), RIM_R * math.sin(a), 0, 1)
sp.use_cyclic_u = True
path = bpy.data.objects.new("rimpath", circle)
path.location.z = 0.205
sc.collection.objects.link(path)

txt = bpy.data.curves.new("rimtext", "FONT")
txt.font = font
fp_spaced = f"{FP[:4]} {FP[4:]}"
txt.body = f"{DATE}     ·     {fp_spaced}     ·     " * 2
txt.size = 0.062
txt.extrude = 0.004
txt.align_x = "LEFT"
txt.space_character = 1.12
text = bpy.data.objects.new("rimtext", txt)
text.location = (0, -0.022, 0.205)  # the text's baseline centred on the rim's flat
sc.collection.objects.link(text)
cm = text.modifiers.new("onrim", "CURVE")
cm.object = path
cm.deform_axis = "POS_X"
text.parent = path
text.location = (0, -0.022, 0)


# ---------- materials ----------
def bronze():
    m = bpy.data.materials.new("bronze")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 1.0
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0
    noise.inputs["Detail"].default_value = 8.0
    rough = N.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.28
    rough.inputs["To Max"].default_value = 0.52
    L.new(noise.outputs["Fac"], rough.inputs["Value"])
    L.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    # the cast colour, a little uneven
    base = N.new("ShaderNodeValToRGB")
    base.color_ramp.elements[0].color = (0.42, 0.25, 0.12, 1)
    base.color_ramp.elements[1].color = (0.62, 0.40, 0.21, 1)
    L.new(noise.outputs["Fac"], base.inputs["Fac"])
    # patina in the hollows: dark, faintly green, where hands never reach
    ao = N.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.05
    ao.samples = 8
    pat = N.new("ShaderNodeMix")
    pat.data_type = "RGBA"
    pat.inputs["B"].default_value = (0.06, 0.07, 0.05, 1)
    inv = N.new("ShaderNodeMapRange")
    inv.inputs["From Min"].default_value = 0.55
    inv.inputs["From Max"].default_value = 1.0
    inv.inputs["To Min"].default_value = 0.85
    inv.inputs["To Max"].default_value = 0.0
    L.new(ao.outputs["AO"], inv.inputs["Value"])
    L.new(inv.outputs["Result"], pat.inputs["Factor"])
    L.new(base.outputs["Color"], pat.inputs["A"])
    L.new(pat.outputs["Result"], bsdf.inputs["Base Color"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    L.new(noise.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def gold():
    m = bpy.data.materials.new("gold")
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Base Color"].default_value = (1.0, 0.74, 0.32, 1)
    bsdf.inputs["Roughness"].default_value = 0.2
    # a faintly hammered surface, as gold leaf pressed by hand
    vor = N.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 260.0
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    L.new(vor.outputs["Distance"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


BRONZE, GOLD = bronze(), gold()
disc.data.materials.append(BRONZE)
for g in GOLD_PARTS:
    g.data.materials.append(GOLD)
txt.materials.append(BRONZE)

# ---------- stage, light, camera ----------
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
floor = bpy.context.object
fm = bpy.data.materials.new("floor")
fb = fm.node_tree.nodes["Principled BSDF"]
fb.inputs["Base Color"].default_value = (0.01, 0.009, 0.008, 1)
fb.inputs["Roughness"].default_value = 0.35
floor.data.materials.append(fm)

world = bpy.data.worlds.new("dark")
sc.world = world
world.node_tree.nodes["Background"].inputs["Color"].default_value = (
    0.004,
    0.004,
    0.005,
    1,
)


def area(name, loc, size, energy, color):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    lo.rotation_mode = "QUATERNION"
    lo.rotation_quaternion = (Vector((0, 0, 0.1)) - Vector(loc)).to_track_quat("-Z", "Y")
    sc.collection.objects.link(lo)


area("key", (-2.2, -1.6, 2.6), 1.6, 420, (1.0, 0.86, 0.68))  # a warm lamp, high left
area("rim", (2.4, 2.2, 0.9), 0.8, 260, (0.72, 0.82, 1.0))  # a cool edge from behind
area("fill", (1.8, -2.4, 0.6), 2.4, 40, (1.0, 0.95, 0.9))

cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 85
cam_d.dof.use_dof = True
cam_d.dof.aperture_fstop = 4.0
cam = bpy.data.objects.new("cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = (0.0, -4.1, 3.0)
cam.rotation_mode = "QUATERNION"
cam.rotation_quaternion = (Vector((0, 0.05, 0.12)) - cam.location).to_track_quat(
    "-Z", "Y"
)
cam_d.dof.focus_distance = (Vector((0, 0, 0.18)) - cam.location).length

sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
try:
    prefs.compute_device_type = "CUDA"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "CUDA"
    sc.cycles.device = "GPU" if any(d.use for d in prefs.devices) else "CPU"
except Exception as e:
    print("NOGPU", e)
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.view_settings.view_transform = "AgX"
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("DONE", OUT)
