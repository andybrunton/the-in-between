---
name: mgear-shifter-component
description: Builds and iterates on custom mGear Shifter components in components/, porting In-Between behaviour cards into tween_* Shifter guides. Use when creating a new Shifter component, turning a card in Cards/ into a guide, editing a guide.py / settingsUI.py / Component class, or debugging a Shifter guide draw or rig build.
---

# Authoring In-Between Shifter components

Reference implementation: `components/tween_bounded_bow_01`. Copy its shape.
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

**4. Write the component.** Four files in `components/tween_<card>_01/`:
`__init__.py` (the `Component`), `guide.py` (`Guide` + `componentSettings`), `settingsUI.py`
(hand-written Qt, no Designer round trip), and the maths module. `TYPE` must equal the folder name.
Any new `addParam` after guides exist in the wild must also land in `_UPGRADE_PARAMS` and
`upgrade_root` (see **Upgrading live guides**).

**5. Build it for real.** Never hand a component over untested:

```powershell
$env:MAYA_MODULE_PATH="C:\Users\andre\Documents\GitHub\mgear\release"
cd components
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

## Guide parameters (`addParameters`)

Every setting the rigger authors lives on the **guide root** as a custom attr via `addParam` in
`Guide.addParameters`. The Component reads them as `self.settings["attrName"]` after
`setFromHierarchy` / `getMergedValues`.

**Naming.** `scriptName` on the guide root is the dict key — no prefix. Anim attrs built from
guide params (`addAnimParam`) are prefixed on the UI host (`boundedBow_bulge`).

**Types.** `long` for enums and counts, `double` for ratios and angles, `bool`, `string` for
comma-separated reference lists (`ikrefarray`).

### Bounded Bow (`tween_bounded_bow_01`) — reference param set

| Param | Type | Role |
|-------|------|------|
| `driveMode` | long 0–1 | `0` = distance (span compresses), `1` = angle (tip kinks) |
| `easing` | long 0–3 | Ramp shape on the single `remapValue` node |
| `div` | long | Joint count |
| `minLengthRatio` | double | Distance mode: guide-length fraction at full bulge |
| `maxBendAngle` | double | Angle mode: degrees at full bulge |
| `bulgeRatio` | double | Peak height as fraction of guide length (seeds anim `bulge`) |
| `tangentWeight` | double | Bezier handle span (peaky vs flat-topped) |
| `ikrefarray` | string | Comma-separated guide roots or locators for tip **space** |
| `ikrefJointDriver` | bool | Tip follows a **joint index** on each `ikrefarray` entry |
| `ikrefJointIndex` | long | 0-based index into each referenced component's `jointList` |
| `angleRef` | string | Guide name driving angle mode (control, locator, or component root) |
| `angleAxis` | long 0–2 | `rotateX` / `rotateY` / `rotateZ` on the angle driver |
| `angleReverse` | bool | Flip driver sign |
| `angleJointDriver` | bool | Read `angleJointIndex` from `angleRef` component instead of ctl/loc |
| `angleJointIndex` | long | 0-based index into `angleRef` component's `jointList` |
| `useIndex` | bool | Stock mGear parent-index override |
| `parentJointIndex` | long | Stock mGear parent joint index (`-1` = default) |

Post-build TD tuning uses `addSetupParam` on the rig (`restAngle`, etc.) — not guide params.

## Joint indices

When a guide param must follow or read a **built joint** on another component, store a **component
root** in the string ref (`neck_L0_root`, `arm_L0_root`) plus a **single index** applied to every
entry in a list (`ikrefarray`) or to the lone `angleRef`.

**Index rule:** 0-based into `comp.jointList` after that component's `jointStructure` pass.
`0` is the first joint the component emits, not the guide root transform.

**UI rule:** `<<` adds the selected object. In joint mode, require `isGearGuide` + `comp_type` on
the selection (component root), not a locator. Grey out the index spinbox when joint mode is off.

**Resolve helper** (copy from bounded bow):

```python
def _joint_from_component_ref(self, ref, index):
    comp = self.rig.findComponent(ref)
    if not comp:
        return None
    try:
        return comp.jointList[index]
    except (IndexError, TypeError):
        return None
```

**Wire timing** — `jointList` does not exist during `connect_standard`:

| Driver | When | How |
|--------|------|-----|
| Control / locator `ikrefarray` | `connect_standard` | `connectRef(..., ik_cns)` |
| Control / locator `angleRef` | `connect_standard` | channel → remap + `tip_npo` |
| Joint `angleRef` | `jointStructure` (after `super`) | same as above, joint rotate channel |
| Joint `ikrefarray` | `postScript` | `pointConstraint` onto `ik_cns` |

Use **point** constraint for joint tip refs, not parent: `ik_cns` already lives under the bow
hierarchy; parent would compound motion. When an external angle driver owns tip rotation,
`connectRef` skips rotate (`skipRotate` / `sr`) so translation and twist do not fight.

**Typical setups**

- **Arm bulge:** `driveMode` angle; `angleRef` = elbow ctl; axis = bend channel. `ikrefarray` =
  upstream arm component for tip **position** only — not the bow's own output (cycles).
- **Neck / head:** `angleJointDriver` on, `angleRef` = `neck_L0_root`, `angleJointIndex` = neck
  IK joint. `ikrefJointDriver` on, same root in `ikrefarray`, `ikrefJointIndex` = head joint.

## Upgrading live guides

New `addParam` attrs are **not** on guides drawn before the param existed. Opening settings or
building against a stale root raises `No 'attrName' attr found`.

**Pattern** (bounded bow `guide.py`):

1. Tuple `_UPGRADE_PARAMS` of `(scriptName, valueType, default, min, max)` for every param added
   after ship.
2. `upgrade_root(root)` — skip if `root.hasAttr`, else `attribute.ParamDef2(...).create(root)`.
3. Call from `setFromHierarchy` **before** `super()` (build path).
4. Call from `componentSettings.__init__` **before** `populate_componentControls` (settings path).

After a code change: `register.register()`, then reopen settings or rebuild. **No Maya restart,
no guide redraw** when upgrade is wired. Redraw only if you need fresh guide geometry, not new attrs.

One-liner to patch a selected root without opening settings:

```python
from tween_bounded_bow_01.guide import Guide
import mgear.pymaya as pm
Guide.upgrade_root(pm.PyNode("boundedBow_C0_root"))
```

## Debugging a build

1. Reproduce headlessly in a throwaway script before changing any component code.
2. **Run the same scenario on the nearest stock component.** Much of what looks like a component
   bug is Shifter behaving as designed; this settles it in one run.
3. Only then edit, and add the scenario to `smoke_build.py` so it stays fixed.

In an interactive Maya session, `register.register()` re-registers the component path, flushes our
modules and clears Shifter's caches, so no restart is needed between iterations. Delete **rig**
only and rebuild; redraw the guide only for geometry changes, not for new guide params when
`upgrade_root` is wired.
