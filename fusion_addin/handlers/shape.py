"""
Shape — what a thing actually IS, in a form that can be read instead of seen.

A screenshot is not perception. Asked what a body looks like, image
recognition guesses; it cannot tell R15 from R14, or notice that a fillet
swallowed a face entirely. So this reads the geometry itself and writes down
what it found, in the modality the reader can actually reason in.

Two halves, and both are needed:

  MEASURED   describe() computes a summary from the B-Rep as it stands now —
             extents, how much of its bounding box it fills, the face
             inventory, openings, symmetry. Facts, recomputed every call.

  DECLARED   context["shape"] is the sentence written when the thing was
             built: what its author understood it to be. Prose, and prose
             about geometry goes stale the moment someone edits the model.

Which is why writing a declared shape also stamps a FINGERPRINT of the
measured one. Later, a fingerprint that no longer matches says the sentence
describes a body that no longer exists — the one failure mode that makes a
recorded shape worse than none at all.
"""

import adsk.core
import adsk.fusion
from typing import Any, Dict, List, Optional

from ..utils.geometry import face_normal, FACE_DIRECTIONS
from ..utils.naming import find_body

# Symmetry is decided by matching mirrored faces; real models carry rounding,
# and a plane that only fails by a micron is a plane of symmetry.
SYMMETRY_TOL_MM = 0.05
MIRROR_PLANES = {"YZ": 0, "ZX": 1, "XY": 2}


def _bbox_mm(body) -> Dict[str, List[float]]:
    bb = body.boundingBox
    lo = [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10]
    hi = [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10]
    return {"min": [round(v, 3) for v in lo],
            "max": [round(v, 3) for v in hi],
            "size": [round(hi[i] - lo[i], 3) for i in range(3)]}


def _face_kind(face) -> str:
    geom = face.geometry
    if isinstance(geom, adsk.core.Plane):
        return "planar"
    if isinstance(geom, adsk.core.Cylinder):
        return "cylindrical"
    if isinstance(geom, adsk.core.Sphere):
        return "spherical"
    if isinstance(geom, adsk.core.Cone):
        return "conical"
    if isinstance(geom, adsk.core.Torus):
        return "toroidal"
    return "freeform"


def _face_centre_mm(face) -> Optional[List[float]]:
    """Centre of a face's bounding box, in mm.

    Deliberately not face_center(): that returns pointOnFace — an arbitrary
    point ON the surface, in cm — which is neither a centroid nor comparable
    with anything measured in mm. A face's box centre is stable and mirrors
    the way the face does, which is all this needs.
    """
    try:
        bb = face.boundingBox
        return [(bb.minPoint.x + bb.maxPoint.x) * 5.0,
                (bb.minPoint.y + bb.maxPoint.y) * 5.0,
                (bb.minPoint.z + bb.maxPoint.z) * 5.0]
    except Exception:
        return None


def _symmetry(body, centre: List[float]) -> List[str]:
    """Which principal planes through the centre the faces mirror across."""
    faces = []
    for face in body.faces:
        c = _face_centre_mm(face)
        if not c:
            return []
        faces.append((c, face.area))

    planes = []
    for name, axis in MIRROR_PLANES.items():
        matched = True
        for point, area in faces:
            mirrored = list(point)
            mirrored[axis] = 2 * centre[axis] - point[axis]
            hit = False
            for other, other_area in faces:
                if abs(area - other_area) > max(area, other_area) * 0.001 + 1e-6:
                    continue
                if all(abs(mirrored[i] - other[i]) <= SYMMETRY_TOL_MM for i in range(3)):
                    hit = True
                    break
            if not hit:
                matched = False
                break
        if matched:
            planes.append(name)
    return planes


def _proportions(size: List[float]) -> str:
    """How the extents relate — the one word a reader wants before the numbers.

    A statement about the bounding box only. It says a shape is plate-like, not
    that it IS a plate: an L-bracket and a slab share these proportions, and
    only the declared shape can tell them apart.
    """
    ordered = sorted(v for v in size if v > 0)
    if len(ordered) < 3 or ordered[0] <= 0:
        return "degenerate"
    smallest, mid, largest = ordered
    if smallest * 3 <= mid:
        return "plate-like" if mid * 3 > largest else "bar-like"
    if largest >= smallest * 3:
        return "bar-like"
    return "blocky"


def describe_body(body) -> dict:
    """Everything about one body that can be stated without seeing it."""
    bbox = _bbox_mm(body)
    size = bbox["size"]
    box_volume_cm3 = (size[0] * size[1] * size[2]) / 1000.0

    kinds: Dict[str, int] = {}
    labelled: Dict[str, int] = {}
    inner_loops = 0
    largest = None

    for face in body.faces:
        kind = _face_kind(face)
        kinds[kind] = kinds.get(kind, 0) + 1
        try:
            for loop in face.loops:
                if not loop.isOuter:
                    inner_loops += 1
        except Exception:
            pass
        if kind == "planar":
            n = face_normal(face)
            if n:
                for label, d in FACE_DIRECTIONS.items():
                    if n[0] * d[0] + n[1] * d[1] + n[2] * d[2] > 0.8:
                        labelled[label] = labelled.get(label, 0) + 1
                        break
        if largest is None or face.area > largest[1]:
            largest = (kind, face.area)

    centre = [(bbox["min"][i] + bbox["max"][i]) / 2.0 for i in range(3)]
    proportions = _proportions(size)
    info = {
        "body": body.name,
        "bbox_mm": bbox,
        "centre_mm": [round(v, 3) for v in centre],
        "volume_cm3": round(body.volume, 4),
        "surface_area_cm2": round(body.area, 4),
        "bbox_fill": round(body.volume / box_volume_cm3, 4) if box_volume_cm3 else None,
        "faces": dict(sorted(kinds.items())),
        "face_count": body.faces.count,
        "edge_count": body.edges.count,
        "planar_faces_by_direction": dict(sorted(labelled.items())),
        "inner_loops": inner_loops,
        "proportions": proportions,
        "symmetry_planes": _symmetry(body, centre),
    }
    if largest:
        info["largest_face"] = {"kind": largest[0], "area_cm2": round(largest[1], 4)}
    if inner_loops:
        info["note_inner_loops"] = (
            "an opening shows up once per face it breaks through — a through "
            "hole in a plate counts 2")
    return info


def fingerprint(body) -> dict:
    """The few numbers that change when a body's shape changes.

    Stamped alongside a declared shape so a later check can say whether the
    sentence still describes this body. Deliberately coarse: position is not
    included, because moving a part does not make a description of its shape
    wrong.
    """
    d = describe_body(body)
    return {
        "volume_cm3": d["volume_cm3"],
        "size_mm": d["bbox_mm"]["size"],
        "face_count": d["face_count"],
        "edge_count": d["edge_count"],
        "inner_loops": d["inner_loops"],
    }


def fingerprint_drift(recorded: dict, current: dict) -> List[str]:
    """How a stamped fingerprint differs from the geometry now. Empty = intact."""
    drift = []
    if not recorded:
        return drift
    v0, v1 = recorded.get("volume_cm3"), current.get("volume_cm3")
    if v0 is not None and v1 is not None and abs(v1 - v0) > max(abs(v0), 1e-9) * 0.001:
        drift.append("volume %.4f -> %.4f cm3" % (v0, v1))
    s0, s1 = recorded.get("size_mm"), current.get("size_mm")
    if s0 and s1 and any(abs(s1[i] - s0[i]) > 0.01 for i in range(3)):
        drift.append("size %s -> %s mm" % (s0, s1))
    for key, label in (("face_count", "faces"), ("edge_count", "edges"),
                       ("inner_loops", "inner loops")):
        a, b = recorded.get(key), current.get(key)
        if a is not None and b is not None and a != b:
            drift.append("%s %d -> %d" % (label, a, b))
    return drift


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _get_design():
    from . import context as ctx
    return ctx._get_design()


def describe(params: dict) -> dict:
    """Read what a body or a whole part IS, without looking at a picture."""
    from . import context as ctx

    design = _get_design()
    target = params.get("target")
    module_name = params.get("module")

    if module_name:
        from . import modules as mods
        entry = mods._read_modules(design).get(module_name)
        if entry is None:
            raise ValueError(f"Module not found: {module_name}")
        members, missing = [], []
        for ref in entry.get("bodies") or []:
            body = find_body(design, ref)
            (members if body else missing).append(body if body else ref)
        if not members:
            raise ValueError(f"Module '{module_name}' has no existing bodies")
        return describe_module(module_name, entry, members, missing)

    if not target:
        raise ValueError("give a target body or a module")
    body = find_body(design, target)
    if not body:
        raise ValueError(f"Body not found: {target}")

    info = describe_body(body)
    context = ctx._read_json_attr(body, ctx.ATTR_CONTEXT) or {}
    declared = context.get("shape")
    if declared:
        info["declared_shape"] = declared
        drift = fingerprint_drift(context.get("shape_fingerprint"), fingerprint(body))
        if drift:
            info["shape_drift"] = drift
            info["warning"] = ("the recorded shape description was written for a "
                               "different body than this one is now")
    return info


def describe_module(name: str, entry: dict, bodies: List[Any],
                    missing: List[str]) -> dict:
    """What a whole part IS: its combined extent and how its bodies sit."""
    los, his, total_volume = [], [], 0.0
    parts = []
    for body in bodies:
        b = _bbox_mm(body)
        los.append(b["min"])
        his.append(b["max"])
        total_volume += body.volume
        parts.append({"body": body.name, "size_mm": b["size"],
                      "volume_cm3": round(body.volume, 4)})

    lo = [round(min(p[i] for p in los), 3) for i in range(3)]
    hi = [round(max(p[i] for p in his), 3) for i in range(3)]
    size = [round(hi[i] - lo[i], 3) for i in range(3)]
    box_cm3 = (size[0] * size[1] * size[2]) / 1000.0

    info = {
        "module": name,
        "intent": entry.get("intent"),
        "declared_shape": entry.get("shape"),
        "bodies": parts,
        "body_count": len(parts),
        "combined_bbox_mm": {"min": lo, "max": hi, "size": size},
        "combined_volume_cm3": round(total_volume, 4),
        "bbox_fill": round(total_volume / box_cm3, 4) if box_cm3 else None,
    }
    if entry.get("area"):
        info["district_mm"] = entry["area"]
    if missing:
        info["missing_bodies"] = missing
    return info


def _questions(context: dict, measured: dict) -> List[str]:
    """The questions a reader has to answer, with the numbers already in them.

    Templates, deliberately. The point is not to be clever about the prose —
    it is that the recorded sentence and the measured fact end up in the same
    line, where a mismatch is visible. Half of these read as obviously true;
    that is fine, because the one that does not is the whole reason to look.
    """
    q = []
    size = measured.get("bbox_mm", {}).get("size")
    if context.get("intent"):
        q.append("intent: %r — does the measured shape actually do this?"
                 % context["intent"])
    if context.get("placement"):
        q.append("placement: %r — is it there? measured centre %s"
                 % (context["placement"], measured.get("centre_mm")))
    if context.get("dimensions"):
        q.append("dimensions: %r — do the measured extents %s follow from that "
                 "arithmetic?" % (context["dimensions"], size))
    if context.get("shape"):
        q.append("shape: %r — measured %d faces (%s), %d openings, fill %s, "
                 "symmetry %s. The same object?"
                 % (context["shape"], measured.get("face_count", 0),
                    measured.get("faces"), measured.get("inner_loops", 0),
                    measured.get("bbox_fill"), measured.get("symmetry_planes")))
    else:
        q.append("no shape is recorded — nothing says what this IS, so nothing "
                 "can be compared against the measurement")
    if not context.get("constraints"):
        q.append("no constraint is recorded: nothing about this body is "
                 "re-checked when anything moves")
    return q


def review(params: dict) -> dict:
    """Put what was RECORDED and what was MEASURED side by side.

    Nothing here judges. "clearance hole for the M3 that fixes the lid" cannot
    be checked by machine, and a checker that tried would report a success it
    had not earned — the failure this whole layer exists to prevent.

    What a machine can do is stop the two halves living in separate tools.
    get_intent and describe_shape each answer half the question, so half is
    what gets read. Together, "intent says a through hole" next to
    "inner_loops: 0" is a contradiction anyone can see.

    You are the reader. Answer the questions, then record the answer with
    verify_intent so the next reader can tell a checked part from an unchecked
    one.
    """
    from . import context as ctx

    design = _get_design()
    target = params.get("target")
    if not target:
        raise ValueError("target is required")
    body = find_body(design, target)
    if not body:
        raise ValueError(f"Body not found: {target}")

    context = ctx._read_json_attr(body, ctx.ATTR_CONTEXT) or {}
    measured = describe_body(body)

    verification = context.get("verification")
    if not verification:
        state = {"status": "never verified"}
    else:
        drift = fingerprint_drift(verification.get("fingerprint"),
                                  fingerprint(body))
        state = dict(verification)
        state["status"] = "stale" if drift else (
            "verified" if verification.get("matches") else "mismatch recorded")
        if drift:
            state["drift_since_verified"] = drift

    return {
        "target": ctx.entity_brief(body, "body"),
        "recorded": {k: context.get(k) for k in
                     ("intent", "placement", "dimensions", "shape",
                      "role", "constraints", "depends_on")},
        "measured": measured,
        "provenance": ctx._read_json_attr(body, ctx.ATTR_PROVENANCE) or [],
        "verification": state,
        "questions": _questions(context, measured),
    }


def verify(params: dict) -> dict:
    """Record that the recorded reasons were read against the measured shape.

    `note` is required on purpose. "verified: true" on its own is a claim, not
    a check, and it is indistinguishable from never having looked. Writing
    what was compared — "intent says a through hole for M6; measured 2
    openings and one 6.0 cylindrical face" — is what makes it evidence.

    The measured fingerprint is stamped alongside, so machining the body later
    takes the verification back to stale rather than leaving a stale pass.
    """
    from . import context as ctx

    design = _get_design()
    target = params.get("target")
    if not target:
        raise ValueError("target is required")
    body = find_body(design, target)
    if not body:
        raise ValueError(f"Body not found: {target}")

    note = (params.get("note") or "").strip()
    if not note:
        raise ValueError(
            "note is required: say what you compared. Without it, 'verified' "
            "cannot be told apart from never having looked.")

    record = {
        "matches": bool(params.get("matches", True)),
        "note": note,
        "at": ctx._now(),
        "fingerprint": fingerprint(body),
    }
    context = ctx._read_json_attr(body, ctx.ATTR_CONTEXT) or {}
    context["verification"] = record
    ctx._write_json_attr(body, ctx.ATTR_CONTEXT, context)
    return {"target": ctx.entity_brief(body, "body"), "verification": record}


ACTIONS = {
    "describe": describe,
    "review": review,
    "verify": verify,
}
