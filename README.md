# The In-Between

Math-driven curve and joint behaviours between your existing controls — live card demos plus **mGear Shifter components** for Maya.

Each behaviour is a recipe card (the spec) and a matching `tween_*` Shifter guide (the rig). Open a card to explore the maths; draw the guide in Maya to build it.

## Card gallery (local)

This site loads card HTML via `fetch()`, so use a local server (not `file://`):

- **VS Code:** Live Server on `index.html`
- **Python:** `python -m http.server 8080` then open `http://localhost:8080`

## mGear components (Maya)

Components live in `components/`. Each subfolder is one Shifter guide type (e.g. `tween_bounded_bow_01`).

### One-time setup

**Option A — environment variable (recommended)**

Add the `components` folder to `MGEAR_SHIFTER_COMPONENT_PATH` (the path must be the folder that *contains* the component subfolders, not a component folder itself). Restart Maya.

**Option B — register from the Script Editor**

```python
import sys
sys.path.append(r"C:\path\to\the-in-between\components")
import register
register.register()
```

Re-run `register.register()` after editing component code so Shifter picks up changes without restarting Maya.

### Draw and build

1. Open mGear → **Shifter Guide Component** manager.
2. Search for `tween_` (e.g. `tween_bounded_bow_01`).
3. Double-click to draw the guide. Place **root** at the start, **tip** at the end; aim the **blade** flag at the bulge direction where applicable.
4. Select the `guide` root and **Build**.

Anim attributes land on the rig UI host (e.g. `global_C0_ctl`), prefixed with the component name (`boundedBow_bulge`, etc.).

### Components

| Card | Shifter type | Status |
|------|----------------|--------|
| Bounded Bow | `tween_bounded_bow_01` | Available |
| Angle Push | `tween_angle_push_01` | Planned |
| Muscle Curve | `tween_muscle_curve_01` | Planned |
| Wave Billow | `tween_wave_billow_01` | Available |
| Skin Wrinkle | `tween_skin_wrinkle_01` | Planned |
| 3D Volume | `tween_volume_3d_01` | Planned |

### Developer checks

```powershell
$env:MAYA_MODULE_PATH="C:\path\to\mgear\release"
cd components
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" smoke_build.py
```

Pure maths modules have a `test_*.py` beside them (`mayapy test_bow_math.py`).

## Publish on GitHub Pages

1. Push this repo to GitHub (public).
2. **Settings → Pages** → deploy from branch `main`, folder `/ (root)`.
3. Site URL: `https://<username>.github.io/the-in-between/`
