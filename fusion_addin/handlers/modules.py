"""
Modules — which bodies are one part, and what that part is for.

The timeline records WHEN things were made, and checkpoints roll work back by
time. Nothing recorded WHICH BODIES ARE ONE THING. "Leg_R" existed only as a
checkpoint label and as three separate bodies that no record connected, so
after the session that made them, the grouping was gone.

A module is the spatial grouping the timeline cannot express: the bodies that
belong to one part, the reason that part exists, and optionally the volume it
is allowed to occupy. The volume is the useful half — a part growing into its
neighbour's space becomes a finding at review time instead of a surprise at
assembly, and moving one rectangle is free while moving thirty bodies is not.

Stored on the Design object (group fusion4ai, attribute "modules"), because a
grouping belongs to no single body and has to outlive all of them.
"""

import adsk.core
import adsk.fusion
from typing import Any, Dict, List, Optional

from . import context as ctx
from ..utils.naming import find_body

ATTR_MODULES = "modules"

# Same tolerance as the constraint grammar: geometry rounds, and a finding
# that fires on floating-point dust is noise.
TOLERANCE_MM = 0.01


def _read_modules(design) -> Dict[str, dict]:
    return ctx._read_json_attr(design, ATTR_MODULES) or {}


def _write_modules(design, modules: Dict[str, dict]) -> None:
    ctx._write_json_attr(design, ATTR_MODULES, modules)


def _bbox_mm(body) -> tuple:
    bb = body.boundingBox
    return ([bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10],
            [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10])


def _normalize_area(area: Any) -> Optional[List[List[float]]]:
    """Accept [[x1,y1,z1],[x2,y2,z2]] in any corner order; return [lo, hi]."""
    if not area:
        return None
    try:
        a, b = area[0], area[1]
        lo = [min(float(a[i]), float(b[i])) for i in range(3)]
        hi = [max(float(a[i]), float(b[i])) for i in range(3)]
        return [lo, hi]
    except Exception:
        raise ValueError(
            "area must be [[x1,y1,z1],[x2,y2,z2]] — two opposite corners in mm")


def set_module(params: dict) -> dict:
    """Declare which bodies are one part, and why that part exists."""
    design = ctx._get_design()
    name = params.get("name")
    if not name:
        raise ValueError("name is required")

    modules = _read_modules(design)
    entry = modules.get(name, {})
    warnings = []

    if params.get("bodies") is not None:
        resolved, missing = [], []
        for ref in params["bodies"]:
            body = find_body(design, ref)
            if body:
                resolved.append(body.name)
            else:
                missing.append(ref)
        entry["bodies"] = resolved
        if missing:
            warnings.append("bodies not found: %s" % ", ".join(missing))

    if params.get("intent") is not None:
        entry["intent"] = params["intent"]
    if params.get("shape") is not None:
        # What the part IS, as a whole — the bodies each know their own shape,
        # nothing else knows what they add up to.
        entry["shape"] = params["shape"]
    if params.get("area") is not None:
        entry["area"] = _normalize_area(params["area"])

    entry["updated_at"] = ctx._now()
    modules[name] = entry
    _write_modules(design, modules)

    result = {"module": name, "record": entry}
    if warnings:
        result["warnings"] = warnings
    return result


def delete_module(params: dict) -> dict:
    """Forget a grouping. The bodies themselves are untouched."""
    design = ctx._get_design()
    name = params.get("name")
    modules = _read_modules(design)
    if name not in modules:
        raise ValueError(f"Module not found: {name}")
    removed = modules.pop(name)
    _write_modules(design, modules)
    return {"deleted": name, "was": removed}


def list_modules(params: dict) -> dict:
    """Every part, one line each, plus the bodies nobody classified."""
    design = ctx._get_design()
    modules = _read_modules(design)

    all_names = []
    for i in range(design.allComponents.count):
        comp = design.allComponents.item(i)
        for j in range(comp.bRepBodies.count):
            all_names.append(comp.bRepBodies.item(j).name)

    claimed = set()
    rows = []
    for name, entry in modules.items():
        members = entry.get("bodies") or []
        missing = [b for b in members if b not in all_names]
        claimed.update(b for b in members if b in all_names)
        row = {
            "module": name,
            "bodies": members,
            "body_count": len(members),
            "intent": entry.get("intent"),
            "shape": entry.get("shape"),
            "has_area": bool(entry.get("area")),
        }
        if missing:
            row["missing_bodies"] = missing
        rows.append(row)

    unassigned = [n for n in all_names if n not in claimed]
    return {
        "modules": rows,
        "module_count": len(rows),
        "unassigned_bodies": unassigned,
        "unassigned_count": len(unassigned),
    }


def review_modules(params: dict) -> dict:
    """Check each part against the volume it was given.

    A module without an area is reported as unbudgeted rather than passed:
    nothing was checked, and saying so is the whole point.
    """
    design = ctx._get_design()
    modules = _read_modules(design)
    target = params.get("name")

    overflows, unbudgeted, missing_bodies, empty = [], [], [], []
    checked = 0

    for name, entry in modules.items():
        if target and name != target:
            continue
        area = entry.get("area")
        members = entry.get("bodies") or []
        # A district with nobody in it checks nothing, and reporting that as a
        # pass is exactly the lie this tool exists to avoid.
        if not members:
            empty.append(name)
            continue
        if not area:
            unbudgeted.append(name)
            continue
        lo, hi = area[0], area[1]
        for ref in members:
            body = find_body(design, ref)
            if not body:
                missing_bodies.append({"module": name, "body": ref})
                continue
            checked += 1
            blo, bhi = _bbox_mm(body)
            out = []
            for axis, i in (("x", 0), ("y", 1), ("z", 2)):
                if blo[i] < lo[i] - TOLERANCE_MM:
                    out.append("%s- by %.3fmm" % (axis, lo[i] - blo[i]))
                if bhi[i] > hi[i] + TOLERANCE_MM:
                    out.append("%s+ by %.3fmm" % (axis, bhi[i] - hi[i]))
            if out:
                overflows.append({"module": name, "body": ref,
                                  "detail": "outside its district: " + ", ".join(out)})

    return {
        "overflows": overflows,
        "overflow_count": len(overflows),
        "unbudgeted_modules": unbudgeted,
        "empty_modules": empty,
        "missing_bodies": missing_bodies,
        "bodies_checked": checked,
        "ok": not overflows and not missing_bodies and not empty,
    }


def move_module(params: dict) -> dict:
    """Move every body of a part together, as one rigid thing.

    A part moved body-by-body is a part that arrives somewhere slightly wrong;
    this keeps the arrangement inside it intact. The district moves with it,
    since the volume was drawn for the part, not for the coordinates.
    """
    design = ctx._get_design()
    name = params.get("name")
    modules = _read_modules(design)
    entry = modules.get(name)
    if entry is None:
        raise ValueError(f"Module not found: {name}")

    dx = float(params.get("x") or 0)
    dy = float(params.get("y") or 0)
    dz = float(params.get("z") or 0)

    root = design.rootComponent
    bodies_col = adsk.core.ObjectCollection.create()
    moved, missing = [], []
    for ref in entry.get("bodies") or []:
        body = find_body(design, ref)
        if body:
            bodies_col.add(body)
            moved.append(ref)
        else:
            missing.append(ref)

    if bodies_col.count == 0:
        raise ValueError(f"Module '{name}' has no existing bodies to move")

    transform = adsk.core.Matrix3D.create()
    transform.translation = adsk.core.Vector3D.create(dx / 10.0, dy / 10.0, dz / 10.0)
    move_feats = root.features.moveFeatures
    move_feats.add(move_feats.createInput(bodies_col, transform))

    if entry.get("area"):
        lo, hi = entry["area"]
        delta = [dx, dy, dz]
        entry["area"] = [[lo[i] + delta[i] for i in range(3)],
                         [hi[i] + delta[i] for i in range(3)]]
        entry["updated_at"] = ctx._now()
        modules[name] = entry
        _write_modules(design, modules)

    result = {"module": name, "moved_bodies": moved,
              "translation_mm": [dx, dy, dz],
              "area_followed": bool(entry.get("area"))}
    if missing:
        result["missing_bodies"] = missing

    # Whatever this part was measured against still has to hold.
    review = ctx.review_related(design, find_body(design, moved[0]))
    if review:
        result["constraint_review"] = review
    return result


ACTIONS = {
    "set_module": set_module,
    "move_module": move_module,
    "delete_module": delete_module,
    "list_modules": list_modules,
    "review_modules": review_modules,
}
