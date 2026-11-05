# Temple study

The landing page's opening scene: a Thanjavur-style temple courtyard, made in Blender from code. Nothing in it is a photograph (D-142), and nothing reads as the BJP's (D-143).

**Status:** a study, not a finished asset. Adhi has seen renders from 28 to 29 October 2026 and asked for it to be far better. On 29 October he chose the **hero object** direction for the landing page: the vimana alone, as a crafted object on a dark stage, turning as the reader scrolls (`--hero`). The courtyard world stays for other shots. The weaknesses still known are listed at the end.

## What it is built from

The anatomy follows `docs/research/FRONTEND_RESEARCH_2026.md` (B5) and `docs/research/TAMIL_DESIGN_ROOTS.md` (section 12):

- **The base:** a moulded base (upapitha and adhishthana) with a rounded kumuda moulding and bead bands. It carries a carved Tamil inscription, as the real temple's base carries Rajaraja's records: Kural 120 and the old Tamil ledger signs for day, month, year, credit and rupee (`docs/research/LANDING_CULTURE_FIT.md`, Part D).
- **The walls:** two storeys built as Dravidian walls are, with a recessed core, projecting bays and real recessed niches. Each niche holds a carved kudu medallion: a horseshoe arch within an arch around a raised water pot (never a lotus, D-143; never a kolam, 30 October; never a deity). Kumbha-panjara pilasters stand between the niches, and kudu arches crown the openings.
- **The tower:** thirteen receding tiers, each ringed by detailed pavilions (kuta and shala). Each pavilion is modelled once and repeated about 360 times, so the detail costs little memory.
- **The crown:** an octagonal neck and an octagonal domed crown with ribs on its eight edges and a bead garland at its foot, the four great arches standing proud with shadowed niches and small finials, and the gold kalasa: the only gold on the tower.
- **The courtyard:**
  - a pillared hall with Chola-style granite pillars: square blocks in sunk frames each carrying a kudu medallion, chamfered octagonal sections, a vase capital and a wave bracket (taranga potika); brass lamps hang between them and a five-flame standing lamp (kuthu vilakku) stands at its edge;
  - the long hall in front of the tower;
  - a lamp pillar and rows of small oil lamps;
  - coconut palms, and banana plants whose leaves tear along their veins;
  - dressed stone paving laid in courses, each slab its own tone and level; after rain (`--wet`) water stands in the low places and reflects the floodlit tower.
- **Materials:** granite made, not scanned, for the pillars (grains of biotite, quartz and feldspar, patina, tooling, worn edges); CC0 scans from Poly Haven elsewhere, with real displacement near the camera, weathering (lichen on upward faces, drip streaks, worn edges) and a CC0 sky used for lighting only. The sky the camera sees is made.
- **Finishing:** bloom, a colour grade, slight lens dispersion and a vignette.

## How to run it

```powershell
python fetch_assets.py --4k
```

**Render the inscription strip** (Tamil needs a browser's text shaping). Open `inscription.html` in Chrome at 9000 x 256, screenshot the `#s` element, and resize it to 8192 x 256 in grey as `tex/inscription.png`. The study used Playwright for this.

**Then render, for example:**

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python vimana.py -- out.png 1600 900 160 hall grade=gold quality=final
```

**Arguments after `--`:**
- the output file;
- width, height and samples;
- the camera: `wide`, `hall`, `low`, `base`, `close`, `aerial`, `threshold` (from inside the hall at dusk), `approach` or `pillarmacro`; with `--hero`, any name, and `orbit=<degrees>` sets where the camera stands around the tower;
- the light, as `grade=`: `morning`, `gold`, `blue` (blue hour, lamps lit) or `noon`;
- `quality=final`, for 4K maps and finer displacement;
- `--wet` for paving after rain, and `--hero` for the vimana alone on its dark stage.

On a 4 GB GTX 1650 a 1600 x 900 frame takes about 5 to 8 minutes. The script uses CUDA when it finds an NVIDIA card. On a Mac, Blender's own Metal GPU rendering is set in its preferences.

## The bar: "no weakness" (Adhi, 30 October 2026)

A render ships to the page only when every line holds, judged at 4K and at the size it is shown, side by side with a reference of the real temple from the same angle:

1. **Proportions from a source:** about 66 m tall, a near-cubic two-storey base, thirteen stepped storeys in a straight pyramid; any other figure cites where it comes from.
2. **Nothing repeats where the eye can see it:** no pavilion, panel or texture tile visible twice in one frame unaltered.
3. **Every surface has age:** colour variation, darker weathering streaks where water runs, worn arrises, grime in recesses; no flat single-tone stone.
4. **Carving reads as hand-cut** at the closest camera: crisp undercuts and shadow, no blocky primitives.
5. **The light has a source:** a low dusk sun or lamps, never flat fill; shadows fall the way that source says.
6. **Scale is legible:** people, lamps and doorways at their real sizes.
7. **The rules hold:** no lotus, no saffron or orange (D-143); no kolam; no deity or ritual (rule 1); nothing a photograph (D-142).
8. **Founder's judgement:** Adhi (and Harish) judge it better than the reference set and the previous pass.

## Known weaknesses (30 October 2026)

- **The hall is far below the tower:** its light reads as flat grey day, its pillars fill the frame without enough carving to hold the eye, and the standing lamp is not visible from the hall camera. Pass 9 replaced every kolam panel with a kudu medallion and removed the paving kolams.
- **Textures:** the walls, paving, bark and grass use CC0 scans from Poly Haven, and the sky light is a CC0 capture. `frontend.md` 8a says "never stock"; whether CC0 material scans count is a founder decision. The pillars' granite is made, not scanned.

## Known weaknesses (29 October 2026)

- **The hero:** the stone still repeats its scanned block pattern on the walls; the tiers' pavilions are all one design; the scroll turn exists only as a 12-frame preview.

- **No world beyond the walls.** The aerial view shows bare ground and a cloister on only three sides.
- **No people**, and the palms and banana plants are still simpler than real ones.
- **Proportions are approximate** until a primary architectural source is found (`TAMIL_DESIGN_ROOTS.md` section 13, item 8).
- **Every pavilion is identical.** Real temples vary every carving.
