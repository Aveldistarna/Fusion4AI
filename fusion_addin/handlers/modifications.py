"""
Modification handlers — boolean operations, move/copy, fillet, chamfer, hole.
"""

import adsk.core
import adsk.fusion
import math
from ..utils.naming import find_body, body_info
from ..utils.geometry import resolve_face, resolve_edges


def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active Fusion design.")
    return design


def _mm2cm(mm: float) -> float:
    return mm / 10.0


# ── Boolean operations ──

def boolean_op(params: dict) -> dict:
    """Perform boolean union/subtract/intersect between two bodies."""
    design = _get_design()
    root = design.rootComponent

    op_map = {
        "union": adsk.fusion.BooleanTypes.UnionBooleanType,
        "subtract": adsk.fusion.BooleanTypes.DifferenceBooleanType,
        "intersect": adsk.fusion.BooleanTypes.IntersectionBooleanType,
    }

    operation = params["operation"].lower()
    if operation not in op_map:
        raise ValueError(f"Unknown operation: {operation}. Use union/subtract/intersect.")

    target = find_body(design, params["target_body"])
    if not target:
        raise ValueError(f"Target body not found: {params['target_body']}")

    tool = find_body(design, params["tool_body"])
    if not tool:
        raise ValueError(f"Tool body not found: {params['tool_body']}")

    combine_feats = root.features.combineFeatures
    combine_input = combine_feats.createInput(target, adsk.core.ObjectCollection.create())
    combine_input.toolBodies.add(tool)
    combine_input.operation = op_map[operation]
    combine_input.isKeepToolBodies = params.get("keep_tool", False)

    combine = combine_feats.add(combine_input)
    result_body = combine.bodies.item(0)

    return body_info(result_body)


# ── Move / Copy ──

def move_body(params: dict) -> dict:
    """Move a body by a translation vector [x, y, z] in mm."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    dx = _mm2cm(params.get("x", 0))
    dy = _mm2cm(params.get("y", 0))
    dz = _mm2cm(params.get("z", 0))

    bodies_col = adsk.core.ObjectCollection.create()
    bodies_col.add(body)

    transform = adsk.core.Matrix3D.create()
    transform.translation = adsk.core.Vector3D.create(dx, dy, dz)

    move_feats = root.features.moveFeatures
    move_input = move_feats.createInput(bodies_col, transform)
    move_feats.add(move_input)

    return body_info(body)


def copy_body(params: dict) -> dict:
    """Copy a body with an offset [x, y, z] in mm."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    dx = _mm2cm(params.get("x", 0))
    dy = _mm2cm(params.get("y", 0))
    dz = _mm2cm(params.get("z", 0))

    # Copy via move with copy option
    bodies_col = adsk.core.ObjectCollection.create()
    bodies_col.add(body)

    transform = adsk.core.Matrix3D.create()
    transform.translation = adsk.core.Vector3D.create(dx, dy, dz)

    move_feats = root.features.moveFeatures
    move_input = move_feats.createInput(bodies_col, transform)
    move_input.isCopy = True
    move_feats.add(move_input)

    # The new body is the last one added
    new_body = root.bRepBodies.item(root.bRepBodies.count - 1)
    if params.get("new_name"):
        new_body.name = params["new_name"]

    return body_info(new_body)


# ── Fillet ──

def add_fillet(params: dict) -> dict:
    """Add fillet to edges of a body."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    radius = _mm2cm(params["radius"])
    edges = resolve_edges(body, params.get("edges", "all"))

    if not edges:
        raise ValueError(f"No edges found for: {params.get('edges', 'all')}")

    edge_col = adsk.core.ObjectCollection.create()
    for e in edges:
        edge_col.add(e)

    fillets = root.features.filletFeatures
    fillet_input = fillets.createInput()
    fillet_input.addConstantRadiusEdgeSet(
        edge_col, adsk.core.ValueInput.createByReal(radius), True
    )
    fillets.add(fillet_input)

    return body_info(body)


# ── Chamfer ──

def add_chamfer(params: dict) -> dict:
    """Add chamfer to edges of a body."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    distance = _mm2cm(params["distance"])
    edges = resolve_edges(body, params.get("edges", "all"))

    if not edges:
        raise ValueError(f"No edges found for: {params.get('edges', 'all')}")

    edge_col = adsk.core.ObjectCollection.create()
    for e in edges:
        edge_col.add(e)

    chamfers = root.features.chamferFeatures
    chamfer_input = chamfers.createInput2()
    chamfer_input.chamferType = adsk.fusion.ChamferTypes.EqualDistanceChamferType
    chamfer_input.addToEdgeSets(
        edge_col,
        adsk.core.ValueInput.createByReal(distance),
        False,  # not tangent chain
    )
    chamfers.add(chamfer_input)

    return body_info(body)


# ── Hole on face ──

def add_hole(params: dict) -> dict:
    """Add a hole on a face of a body. Face can be 'top', 'front', etc. or a face ID."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    face = resolve_face(body, params["face"])
    if not face:
        raise ValueError(f"Face not found: {params['face']}")

    diameter = _mm2cm(params["diameter"])
    radius = diameter / 2
    depth = params.get("depth", "through")

    # Get face center for hole position
    from ..utils.geometry import face_center
    cx, cy, cz = face_center(face)

    # Offset position if provided
    offset_x = _mm2cm(params.get("offset_x", 0))
    offset_y = _mm2cm(params.get("offset_y", 0))

    # Create sketch on the face
    sketch = root.sketches.add(face)

    # Draw circle at center (in sketch local coords = 0,0 is face origin)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(offset_x, offset_y, 0), radius
    )

    # Select the correct profile: the one closest to the expected circle area (π*r²)
    expected_area = math.pi * radius * radius
    best_profile = None
    best_diff = float("inf")
    for i in range(sketch.profiles.count):
        p = sketch.profiles.item(i)
        diff = abs(p.areaProperties().area - expected_area)
        if diff < best_diff:
            best_diff = diff
            best_profile = p
    profile = best_profile

    # Extrude cut
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(
        profile, adsk.fusion.FeatureOperations.CutFeatureOperation
    )

    if depth == "through":
        ext_input.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
    else:
        d = _mm2cm(float(depth))
        ext_input.setDistanceExtent(
            False, adsk.core.ValueInput.createByReal(d)
        )
        ext_input.extent.isFlipped = True

    ext_input.participantBodies = [body]
    extrudes.add(ext_input)

    return body_info(body)


def add_holes(params: dict) -> dict:
    """Add multiple holes on a face in a single sketch (avoids coordinate drift)."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    face = resolve_face(body, params["face"])
    if not face:
        raise ValueError(f"Face not found: {params['face']}")

    holes = params["holes"]  # list of {x, y, diameter} in mm
    if not holes:
        raise ValueError("No holes specified.")

    depth = params.get("depth", "through")

    # Single sketch on the face
    sketch = root.sketches.add(face)

    # Draw all circles
    total_expected_area = 0
    for h in holes:
        r = _mm2cm(h["diameter"]) / 2
        ox = _mm2cm(h.get("x", 0))
        oy = _mm2cm(h.get("y", 0))
        sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(ox, oy, 0), r
        )
        total_expected_area += math.pi * r * r

    # Collect the circle profiles (those whose area ≈ π*r² for one of the holes)
    hole_areas = set()
    for h in holes:
        r = _mm2cm(h["diameter"]) / 2
        hole_areas.add(math.pi * r * r)

    profiles_to_cut = adsk.core.ObjectCollection.create()
    for i in range(sketch.profiles.count):
        p = sketch.profiles.item(i)
        area = p.areaProperties().area
        # Check if this profile matches any hole area (within 5% tolerance)
        for ha in hole_areas:
            if ha > 0 and abs(area - ha) / ha < 0.05:
                profiles_to_cut.add(p)
                break

    if profiles_to_cut.count == 0:
        raise RuntimeError("Could not identify hole profiles in sketch.")

    # Extrude cut all at once
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(
        profiles_to_cut, adsk.fusion.FeatureOperations.CutFeatureOperation
    )

    if depth == "through":
        ext_input.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
    else:
        d = _mm2cm(float(depth))
        ext_input.setDistanceExtent(
            False, adsk.core.ValueInput.createByReal(d)
        )
        ext_input.extent.isFlipped = True

    ext_input.participantBodies = [body]
    extrudes.add(ext_input)

    return body_info(body)


ACTIONS = {
    "boolean_op": boolean_op,
    "move_body": move_body,
    "copy_body": copy_body,
    "add_fillet": add_fillet,
    "add_chamfer": add_chamfer,
    "add_hole": add_hole,
    "add_holes": add_holes,
}
