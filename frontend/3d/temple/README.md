# Temple study

The landing page's opening scene: a Thanjavur-style temple courtyard, made in Blender from code. Nothing in it is a photograph (D-142), and nothing reads as the BJP's (D-143).

**Status:** a study, not a finished asset. Adhi has seen renders from 28 to 29 October 2026 and asked for it to be far better. The weaknesses still known are listed at the end.

## What it is built from

The anatomy follows `docs/research/FRONTEND_RESEARCH_2026.md` (B5) and `docs/research/TAMIL_DESIGN_ROOTS.md` (section 12):

- **The base:** a moulded base (upapitha and adhishthana) with a rounded kumuda moulding and bead bands. It carries a carved Tamil inscription, as the real temple's base carries Rajaraja's records: Kural 120 and the old Tamil ledger signs for day, month, year, credit and rupee (`docs/research/LANDING_CULTURE_FIT.md`, Part D).
- **The walls:** two storeys built as Dravidian walls are, with a recessed core, projecting bays and real recessed niches. Each niche holds a carved kolam panel (never a lotus, never a deity). Kumbha-panjara pilasters stand between the niches, and kudu arches crown the openings.
- **The tower:** thirteen receding tiers, each ringed by detailed pavilions (kuta and shala). Each pavilion is modelled once and repeated about 360 times, so the detail costs little memory.
- **The crown:** an octagonal neck and an octagonal domed crown, with the four great arches and the finial.
- **The courtyard:**
  - a pillared hall with Chola-style pillars, whose blocks carry carved kolam knots;
  - the long hall in front of the tower;
  - a lamp pillar, rows of small oil lamps, and a rice-flour kolam on the paving;
  - coconut palms and banana plants.
- **Materials:** CC0 scans from Poly Haven, with real displacement near the camera, weathering (lichen on upward faces, drip streaks, worn edges) and a CC0 sky used for lighting only. The sky the camera sees is made.
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
- the camera: `wide`, `hall`, `low`, `base`, `close` or `aerial`;
- the light, as `grade=`: `morning`, `gold`, `blue` (blue hour, lamps lit) or `noon`;
- `quality=final`, for 4K maps and finer displacement.

On a 4 GB GTX 1650 a 1600 x 900 frame takes about 5 to 8 minutes. The script uses CUDA when it finds an NVIDIA card. On a Mac, Blender's own Metal GPU rendering is set in its preferences.

## Known weaknesses (29 October 2026)

- **No world beyond the walls.** The aerial view shows bare ground and a cloister on only three sides.
- **No people**, and the palms and banana plants are still simpler than real ones.
- **Proportions are approximate** until a primary architectural source is found (`TAMIL_DESIGN_ROOTS.md` section 13, item 8).
- **Every pavilion is identical.** Real temples vary every carving.
