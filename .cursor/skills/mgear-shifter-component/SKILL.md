---
name: mgear-shifter-component
description: Builds and iterates on custom mGear Shifter components in tools/maya/shifter_components, porting In-Between behaviour cards into tween_* Shifter guides. Use when creating a new Shifter component, turning a card in Cards/ into a guide, editing a guide.py / settingsUI.py / Component class, or debugging a Shifter guide draw or rig build.
---

# Authoring In-Between Shifter components

Reference implementation: `tools/maya/shifter_components/tween_bounded_bow_01`. Copy its shape.
API facts and the running mistakes log live in `.cursor/rules/mgear-shifter-components.mdc` —
read it before starting and append to it when something surprises you.

mGear source (read-only, never edit):
`C:\Users\andre\Documents\GitHub\mgear\release\scripts\mgear`.
Nearest stock template: `shifter_classic_components/hydraulic_01`.

## Workflow

```
- [ ] 1. Read the card, extract the spec
- [ ] 2. Decide drive + guide shape
- [ ] 3. Write the maths module and its test
- [ ] 4. Write guide.py, settingsUI.py, __init__.py
- [ ] 5. Add a smoke_build.py case and make it pass
- [ ] 6. Append any lesson to the rule
```

**1. Read the card.** `Cards/<Name>.html` is the spec. The `Pseudocode` block and the
`Full formula breakdown` block are authoritative; the SVG is a 2D projection and often contains
artifacts that must not be ported (see the `cos(bendAngle)` entry in the lessons log).

**2. Decide drive and guide shape.** Every card so far reduces to: measure something between two
points, remap it to 0..1, drive a shape. Offer both distance and angle drive via a `driveMode`
param unless the card only makes sense one way. Keep the guide minimal — root, tip, and a blade
when a direction must be authored.

**3. Maths first, in a Maya-free module.** Expand the card's formula algebraically so each joint
needs constant coefficients and a couple of utility nodes rather than a live curve. Put it in
`bow_math.py`-style module with a `test_*.py` beside it asserting against a naive direct
implementation of the card formula. Run it in a second:

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" test_<name>.py
```

**4. Write the component.** Four files in `tools/maya/shifter_components/tween_<card>_01/`:
`__init__.py` (the `Component`), `guide.py` (`Guide` + `componentSettings`), `settingsUI.py`
(hand-written Qt, no Designer round trip), and the maths module. `TYPE` must equal the folder name.

**5. Build it for real.** Never hand a component over untested:

```powershell
$env:MAYA_MODULE_PATH="C:\Users\andre\Documents\GitHub\mgear\release"
cd tools\maya\shifter_components
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" smoke_build.py
```

Shifter draws guides and builds rigs under `maya.standalone`, so this is a full draw-build-assert
loop in about 20 seconds. Assert rig *behaviour* (joint positions after driving the controls), not
just that the build did not throw.

**6. Append the lesson.** Every surprise gets a dated line in the rule's Lessons section, in the
same change as the fix.

## Conventions

- Name components `tween_<card>_01`, `NAME` is the camelCase short name (`boundedBow`).
- Build the deformation in a chord-aligned space: **+X down the chord, +Y the shaped direction**,
  with a child transform whose `rotateX` rolls that direction around the chord.
- Settings that describe proportions are **ratios of the guide length**, so a rescaled guide keeps
  sane defaults. Absolute values go on anim attrs, seeded from `ratio * guide length`.
- Use one `remapValue` for input-remap plus easing plus clamping. Its ramp encodes the easing enum
  and stays hand-tunable after the build. Do not build easing out of arithmetic nodes.
- Measure distances in component-root local space so the rig global scale stays out of the drive.
- Thresholds a TD may want to retune go on `addSetupParam`, not hard-coded into the DG.
- Orient chains by aiming each point at its neighbour (`applyop.aimCns`, `-xy` for the last one).
- For any list-of-scene-objects setting, copy the stock IK Reference Array layout from
  `arm_2jnt_01/settingsUI.py`.

## Debugging a build

1. Reproduce headlessly in a throwaway script before changing any component code.
2. **Run the same scenario on the nearest stock component.** Much of what looks like a component
   bug is Shifter behaving as designed; this settles it in one run.
3. Only then edit, and add the scenario to `smoke_build.py` so it stays fixed.

In an interactive Maya session, `register.register()` re-registers the component path, flushes our
modules and clears Shifter's caches, so no restart is needed between iterations.
