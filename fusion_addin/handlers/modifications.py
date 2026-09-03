"""
Modification handlers — boolean operations, move/copy, fillet, chamfer, hole.
"""

import adsk.core
import adsk.fusion
import math
from ..utils.naming import find_body, body_info
from ..utils.geometry import resolve_face, resolve_edges
from . import context


def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active Fusion design.")
    return design


def _mm2cm(mm: float) -> float:
    return mm / 10.0


# ── Boolean operations ──

def _with_review(design, body, info: dict) -> dict:
    """Attach the constraint re-check to an edit's response.

    A move that quietly breaks a recorded promise is the failure mode this
    whole layer exists to prevent, so the answer to "I moved it" carries
    whether anything it was measured against still holds.
    """
    report = context.review_related(design, body)
    if report:
        info["constraint_review"] = report
    return info


def boolean_op(params: dict) -> dict:
    """Perform boolean union/subtract/intersect between two bodies."""
    design = _get_design()
    root = design.rootComponent

    op_map = {
        "union": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "subtract": adsk.fusion.FeatureOperations.CutFeatureOperation,
        "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
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

    # Capture volume before operation
    vol_before = target.volume
    # Read the tool's name and reason before the combine can consume it.
    tool_name = tool.name
    tool_reason = context.absorbed_reason(tool, params)

    combine_feats = root.features.combineFeatures
    tool_bodies = adsk.core.ObjectCollection.create()
    tool_bodies.add(tool)
    combine_input = combine_feats.createInput(target, tool_bodies)
    combine_input.operation = op_map[operation]
    combine_input.isKeepToolBodies = params.get("keep_tool", False)

    # Debug: verify inputs
    debug = {
        "target_name": target.name,
        "target_volume": target.volume,
        "tool_name": tool.name,
        "tool_volume": tool.volume,
        "tool_bodies_count": tool_bodies.count,
        "operation": operation,
    }

    combine = combine_feats.add(combine_input)

    if not combine:
        raise RuntimeError(f"combineFeatures.add returned None. Debug: {debug}")

    # Check if combine produced any bodies
    if combine.bodies.count == 0:
        raise RuntimeError(f"Combine produced 0 bodies. Debug: {debug}")

    result_body = combine.bodies.item(0)

    absorbed = dict(params)
    if not params.get("keep_tool"):
        absorbed["_consumed"] = tool_name
        absorbed["intent"] = tool_reason
    context.try_embed(result_body, "boolean_op", absorbed)

    # Get info after operation
    result = body_info(result_body)
    result["volume_before_cm3"] = vol_before
    result["volume_delta_cm3"] = round(result["volume_cm3"] - vol_before, 6)
    result["_debug"] = debug
    return result


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

    context.try_embed(body, "move_body", params)

    return _with_review(design, body, body_info(body))


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

    context.try_embed(new_body, "copy_body", params)

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

    context.try_embed(body, "add_fillet", params)

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

    context.try_embed(body, "add_chamfer", params)

    return body_info(body)


# ── Hole on face ──

def _sketch_origin_offset(sketch, face):
    """Where the face's CENTRE sits in the sketch's own 2D coordinates.

    root.sketches.add(face) puts the sketch on the face's plane, but its
    origin is wherever Fusion decides — the world origin projected onto that
    plane, typically, not the middle of the face. Offsets are documented as
    being from the face centre, so they have to be measured from here or a
    hole lands at an absolute coordinate the caller never asked for.
    """
    bb = face.boundingBox
    centre = adsk.core.Point3D.create(
        (bb.minPoint.x + bb.maxPoint.x) / 2.0,
        (bb.minPoint.y + bb.maxPoint.y) / 2.0,
        (bb.minPoint.z + bb.maxPoint.z) / 2.0,
    )
    local = sketch.modelToSketchSpace(centre)
    return local.x, local.y


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
    cx, cy = _sketch_origin_offset(sketch, face)

    # Draw circle at center (in sketch local coords = 0,0 is face origin)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(cx + offset_x, cy + offset_y, 0), radius
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

    context.try_embed(body, "add_hole", params)

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
    cx, cy = _sketch_origin_offset(sketch, face)

    # Draw all circles
    total_expected_area = 0
    for h in holes:
        r = _mm2cm(h["diameter"]) / 2
        ox = _mm2cm(h.get("x", 0))
        oy = _mm2cm(h.get("y", 0))
        sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(cx + ox, cy + oy, 0), r
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

    context.try_embed(body, "add_holes", params)

    return body_info(body)


# ── Cut by plane ──

def cut_by_plane(params: dict) -> dict:
    """Cut a body with an infinite plane defined by a point and normal vector.
    Keeps the side opposite to the normal direction (i.e., removes material
    in the normal direction from the point)."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    # Point and normal in mm → cm
    pt = params["point"]  # [x, y, z] in mm
    nm = params["normal"]  # [nx, ny, nz] unit vector

    point = adsk.core.Point3D.create(_mm2cm(pt[0]), _mm2cm(pt[1]), _mm2cm(pt[2]))
    normal = adsk.core.Vector3D.create(nm[0], nm[1], nm[2])
    normal.normalize()

    # Create slab via sketch+extrude, orient with normal, then subtract from target.

    slab_size = 50.0  # 500mm in cm
    slab_thick = 50.0  # 500mm thick

    z_axis = adsk.core.Vector3D.create(0, 0, 1)

    # Create slab at origin on XY plane
    xy_plane = root.xYConstructionPlane
    sketch = root.sketches.add(xy_plane)
    half = slab_size / 2
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(-half, -half, 0),
        adsk.core.Point3D.create(half, half, 0),
    )
    profile = sketch.profiles.item(0)

    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(
        profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(slab_thick))
    ext = extrudes.add(ext_input)
    slab_body = ext.bodies.item(0)

    # Rotate slab to align with target normal
    move_feats = root.features.moveFeatures
    dot_val = z_axis.x * normal.x + z_axis.y * normal.y + z_axis.z * normal.z
    if dot_val < 0.9999:
        if dot_val > -0.9999:
            rot_axis = z_axis.crossProduct(normal)
            rot_axis.normalize()
            rot_angle = math.acos(max(-1, min(1, dot_val)))
        else:
            rot_axis = adsk.core.Vector3D.create(1, 0, 0)
            rot_angle = math.pi

        slab_col = adsk.core.ObjectCollection.create()
        slab_col.add(slab_body)
        rot_transform = adsk.core.Matrix3D.create()
        rot_transform.setToRotation(rot_angle, rot_axis, adsk.core.Point3D.create(0, 0, 0))
        move_feats.add(move_feats.createInput(slab_col, rot_transform))

    # Move slab to the plane point
    slab_col2 = adsk.core.ObjectCollection.create()
    slab_col2.add(slab_body)
    translate = adsk.core.Matrix3D.create()
    translate.translation = adsk.core.Vector3D.create(point.x, point.y, point.z)
    move_feats.add(move_feats.createInput(slab_col2, translate))

    # Subtract slab from target body
    vol_before = body.volume
    face_count_before = body.faces.count
    combine_feats = root.features.combineFeatures
    tool_bodies = adsk.core.ObjectCollection.create()
    tool_bodies.add(slab_body)
    combine_input = combine_feats.createInput(body, tool_bodies)
    combine_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    combine_input.isKeepToolBodies = False
    combine_feats.add(combine_input)

    context.try_embed(body, "cut_by_plane", params)

    # Note: intermediate features (sketch, extrude, moves) remain in timeline
    # because CombineFeature depends on them. They cannot be safely deleted.
    # The slab body itself is consumed by the combine (isKeepToolBodies=False).

    result = body_info(body)
    result["volume_before_cm3"] = vol_before
    result["volume_delta_cm3"] = round(result["volume_cm3"] - vol_before, 6)
    result["face_count_before"] = face_count_before
    result["face_count_after"] = body.faces.count

    # Validation warnings
    warnings = []
    if abs(result["volume_delta_cm3"]) < 1e-6:
        warnings.append("WARNING: volume unchanged — cut may not have intersected the body. Check slab size or plane position.")
    if body.faces.count <= face_count_before:
        warnings.append("WARNING: face count did not increase — cut may be incomplete.")
    if warnings:
        result["warnings"] = warnings

    return result


# ── Rotate body ──

def rotate_body(params: dict) -> dict:
    """Rotate a body around an axis defined by a point and direction vector."""
    design = _get_design()
    root = design.rootComponent

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    angle_deg = params["angle"]
    axis_pt = params.get("axis_point", [0, 0, 0])  # mm
    axis_dir = params.get("axis_direction", [0, 0, 1])  # unit vector

    origin = adsk.core.Point3D.create(
        _mm2cm(axis_pt[0]), _mm2cm(axis_pt[1]), _mm2cm(axis_pt[2])
    )
    direction = adsk.core.Vector3D.create(axis_dir[0], axis_dir[1], axis_dir[2])
    direction.normalize()

    angle_rad = math.radians(angle_deg)

    bodies_col = adsk.core.ObjectCollection.create()
    bodies_col.add(body)

    transform = adsk.core.Matrix3D.create()
    transform.setToRotation(angle_rad, direction, origin)

    move_feats = root.features.moveFeatures
    move_input = move_feats.createInput(bodies_col, transform)
    move_feats.add(move_input)

    context.try_embed(body, "rotate_body", params)

    return _with_review(design, body, body_info(body))


# ── Delete body ──

def delete_body(params: dict) -> dict:
    """Delete a body. Reports objects that recorded a dependency on it."""
    design = _get_design()

    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    name = body.name
    token = body.entityToken
    dependents = context._find_dependents_of(design, body, token, name)

    if dependents and not params.get("force"):
        return {
            "deleted": False,
            "reason": "Other objects depend on this body. Pass force=true to delete anyway.",
            "dependents": dependents,
        }

    if not body.deleteMe():
        raise RuntimeError(f"deleteMe() returned False for body: {name}")

    result: dict = {"deleted": True, "name": name}
    if dependents:
        result["warning"] = "Deleted despite dependents — run check_integrity and update their context."
        result["dependents"] = dependents
    return result


ACTIONS = {
    "boolean_op": boolean_op,
    "move_body": move_body,
    "copy_body": copy_body,
    "add_fillet": add_fillet,
    "add_chamfer": add_chamfer,
    "add_hole": add_hole,
    "add_holes": add_holes,
    "cut_by_plane": cut_by_plane,
    "rotate_body": rotate_body,
    "delete_body": delete_body,
}
