"""
Constraint grammar — the half of a recorded reason a machine can re-check.

Prose decays as the design moves; a parsed rule does not. "keep 3mm to Cover"
written as prose is a promise nobody verifies: the next move makes it a lie
and nothing notices. Written in this grammar it is re-measured after every
move, and a violation has a number attached to it.

The grammar is deliberately small. Anything outside it is STORED and reported
back as `unchecked` — never silently dropped — so that "no violations" can
never quietly mean "nothing was looked at".

  clearance >= 3mm to Cover      minimum gap between two bodies
  clearance <= 5mm to Cover      (>, < also accepted)
  inside Housing                 this body must stay within another
  flush Base top                 a face stays level with the same face of another
  aligned Bracket x              centres share a coordinate on that axis
  symmetric_to Leg_L about YZ    mirrored across a principal plane
  concentric_with Shaft z        centres agree on the axes across from z

Everything here is mm. Fusion's internal unit is cm, so every measurement
crosses that boundary exactly once, at the point it is read.
"""

import adsk.core
import adsk.fusion
import re
from typing import Any, Dict, List, Optional, Tuple

from ..utils.naming import find_body

# Geometry rounds; a rule that fires on floating-point dust is noise, not a
# finding. 0.01mm is well below anything a design decision turns on.
TOLERANCE_MM = 0.01

AXES = {"x": 0, "y": 1, "z": 2}

# Which bbox extreme a face label stands for: (axis index, "max" or "min").
# Mirrors FACE_DIRECTIONS in utils.geometry so the two vocabularies agree.
FACE_EXTREME = {
    "top": (2, "max"), "bottom": (2, "min"),
    "back": (1, "max"), "front": (1, "min"),
    "right": (0, "max"), "left": (0, "min"),
}

# A principal plane is named by the two axes it contains; the constraint is
# about the third one, which is the axis the mirror flips.
PLANE_NORMAL = {"XY": 2, "YZ": 0, "ZX": 1, "XZ": 1}

_CLEARANCE = re.compile(
    r"^clearance\s*(>=|<=|>|<)\s*([0-9.]+)\s*mm\s+to\s+(.+?)\s*$", re.I)
_INSIDE = re.compile(r"^inside\s+(.+?)\s*$", re.I)
_FLUSH = re.compile(r"^flush\s+(\S+)\s+(top|bottom|left|right|front|back)\s*$", re.I)
_ALIGNED = re.compile(r"^aligned\s+(\S+)\s+([xyz])\s*$", re.I)
_SYMMETRIC = re.compile(r"^symmetric_to\s+(\S+)\s+about\s+(XY|YZ|ZX|XZ)\s*$", re.I)
_CONCENTRIC = re.compile(r"^concentric_with\s+(\S+)(?:\s+([xyz]))?\s*$", re.I)


def parse(text: str) -> Optional[dict]:
    """Parse one constraint. Returns None if it is outside the grammar."""
    s = (text or "").strip()

    m = _CLEARANCE.match(s)
    if m:
        return {"kind": "clearance", "op": m.group(1),
                "value": float(m.group(2)), "other": m.group(3)}
    m = _INSIDE.match(s)
    if m:
        return {"kind": "inside", "other": m.group(1)}
    m = _FLUSH.match(s)
    if m:
        return {"kind": "flush", "other": m.group(1), "face": m.group(2).lower()}
    m = _ALIGNED.match(s)
    if m:
        return {"kind": "aligned", "other": m.group(1), "axis": m.group(2).lower()}
    m = _SYMMETRIC.match(s)
    if m:
        return {"kind": "symmetric_to", "other": m.group(1),
                "plane": m.group(2).upper()}
    m = _CONCENTRIC.match(s)
    if m:
        return {"kind": "concentric_with", "other": m.group(1),
                "axis": (m.group(2) or "z").lower()}
    return None


def references(text: str) -> Optional[str]:
    """Which other body a constraint talks about, if any."""
    rule = parse(text)
    return rule.get("other") if rule else None


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _bbox_mm(body: adsk.fusion.BRepBody) -> Tuple[List[float], List[float]]:
    bb = body.boundingBox
    return ([bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10],
            [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10])


def _centre_mm(body: adsk.fusion.BRepBody) -> List[float]:
    lo, hi = _bbox_mm(body)
    return [(lo[i] + hi[i]) / 2.0 for i in range(3)]


def _gap_mm(a: adsk.fusion.BRepBody, b: adsk.fusion.BRepBody) -> Tuple[float, str]:
    """Minimum distance between two bodies, in mm.

    measureMinimumDistance is exact but not available in every context, so a
    bounding-box gap stands in. The caller is told which was used: a bbox gap
    understates the clearance of anything that is not a block, and a rule that
    passed on an approximation has not really been checked.
    """
    try:
        app = adsk.core.Application.get()
        result = app.measureManager.measureMinimumDistance(a, b)
        if result:
            return result.value * 10, "exact"
    except Exception:
        pass

    alo, ahi = _bbox_mm(a)
    blo, bhi = _bbox_mm(b)
    per_axis = []
    for i in range(3):
        per_axis.append(max(blo[i] - ahi[i], alo[i] - bhi[i], 0.0))
    return (sum(v * v for v in per_axis) ** 0.5), "bbox"


def _compare(measured: float, op: str, target: float) -> bool:
    if op == ">=":
        return measured >= target - TOLERANCE_MM
    if op == ">":
        return measured > target - TOLERANCE_MM
    if op == "<=":
        return measured <= target + TOLERANCE_MM
    if op == "<":
        return measured < target + TOLERANCE_MM
    return False


def _round(v: float) -> float:
    return round(v, 3)


# ---------------------------------------------------------------------------
# Evaluation — one rule at a time
# ---------------------------------------------------------------------------

def _eval_rule(design, body, rule: dict) -> dict:
    other = find_body(design, rule["other"])
    if not other:
        return {"status": "error",
                "detail": "referenced body not found: %s" % rule["other"]}

    kind = rule["kind"]

    if kind == "clearance":
        gap, method = _gap_mm(body, other)
        ok = _compare(gap, rule["op"], rule["value"])
        record = {"status": "ok" if ok else "violated",
                  "measured_mm": _round(gap), "method": method}
        if not ok:
            record["detail"] = "gap is %.3fmm, rule wants %s%gmm" % (
                gap, rule["op"], rule["value"])
        elif method == "bbox":
            record["detail"] = "measured on bounding boxes — exact distance unavailable"
        return record

    if kind == "inside":
        lo, hi = _bbox_mm(body)
        olo, ohi = _bbox_mm(other)
        outside = []
        for axis, i in AXES.items():
            if lo[i] < olo[i] - TOLERANCE_MM:
                outside.append("%s- by %.3fmm" % (axis, olo[i] - lo[i]))
            if hi[i] > ohi[i] + TOLERANCE_MM:
                outside.append("%s+ by %.3fmm" % (axis, hi[i] - ohi[i]))
        if outside:
            return {"status": "violated", "method": "bbox",
                    "detail": "protrudes past %s: %s" % (rule["other"], ", ".join(outside))}
        return {"status": "ok", "method": "bbox",
                "detail": "bounding box is contained — not a true solid containment test"}

    if kind == "flush":
        i, side = FACE_EXTREME[rule["face"]]
        lo, hi = _bbox_mm(body)
        olo, ohi = _bbox_mm(other)
        mine = hi[i] if side == "max" else lo[i]
        theirs = ohi[i] if side == "max" else olo[i]
        delta = mine - theirs
        if abs(delta) <= TOLERANCE_MM:
            return {"status": "ok", "measured_mm": _round(delta)}
        return {"status": "violated", "measured_mm": _round(delta),
                "detail": "%s face is %.3fmm off %s's" % (
                    rule["face"], delta, rule["other"])}

    if kind == "aligned":
        i = AXES[rule["axis"]]
        delta = _centre_mm(body)[i] - _centre_mm(other)[i]
        if abs(delta) <= TOLERANCE_MM:
            return {"status": "ok", "measured_mm": _round(delta)}
        return {"status": "violated", "measured_mm": _round(delta),
                "detail": "centres differ by %.3fmm on %s" % (delta, rule["axis"])}

    if kind == "symmetric_to":
        i = PLANE_NORMAL[rule["plane"]]
        mine = _centre_mm(body)
        theirs = _centre_mm(other)
        # Mirrored across the plane: the flipped axis sums to zero, the others match.
        offenders = []
        total = mine[i] + theirs[i]
        if abs(total) > TOLERANCE_MM:
            offenders.append("mirror axis off by %.3fmm" % total)
        for axis, j in AXES.items():
            if j == i:
                continue
            d = mine[j] - theirs[j]
            if abs(d) > TOLERANCE_MM:
                offenders.append("%s differs by %.3fmm" % (axis, d))
        if offenders:
            return {"status": "violated", "detail": "; ".join(offenders)}
        return {"status": "ok"}

    if kind == "concentric_with":
        i = AXES[rule["axis"]]
        mine = _centre_mm(body)
        theirs = _centre_mm(other)
        offenders = []
        for axis, j in AXES.items():
            if j == i:
                continue
            d = mine[j] - theirs[j]
            if abs(d) > TOLERANCE_MM:
                offenders.append("%s off by %.3fmm" % (axis, d))
        if offenders:
            return {"status": "violated",
                    "detail": "axes across %s: %s" % (rule["axis"], "; ".join(offenders))}
        return {"status": "ok"}

    return {"status": "unchecked", "detail": "unknown rule kind"}


def evaluate(design, body, constraint_text: str) -> dict:
    """Check one recorded constraint against the geometry as it stands now."""
    record: Dict[str, Any] = {"constraint": constraint_text}
    rule = parse(constraint_text)
    if not rule:
        record["status"] = "unchecked"
        record["detail"] = "outside the grammar — recorded, but no machine checks it"
        return record
    try:
        record.update(_eval_rule(design, body, rule))
    except Exception as e:
        record["status"] = "error"
        record["detail"] = str(e)
    return record


def evaluate_all(design, body, constraints: List[str]) -> List[dict]:
    return [evaluate(design, body, c) for c in (constraints or [])]


def summarize(checks: List[dict]) -> dict:
    """Counts that let a caller see at a glance what was NOT checked."""
    counts = {"ok": 0, "violated": 0, "unchecked": 0, "error": 0}
    for c in checks:
        counts[c.get("status", "error")] = counts.get(c.get("status", "error"), 0) + 1
    return counts
