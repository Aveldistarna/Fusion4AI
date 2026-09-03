"""
Primitive shape handlers — box, cylinder, sphere, cone.
All dimensions are received in mm, converted to cm for Fusion internal units.
"""

import adsk.core
import adsk.fusion
import math
from ..utils.naming import body_info, find_body
from . import context


def _mm2cm(mm: float) -> float:
    return mm / 10.0


def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active Fusion design. Please open or create a design.")
    return design


def _apply_boolean(params: dict, design: adsk.fusion.Design, new_body: adsk.fusion.BRepBody) -> dict:
    """If boolean and target params are set, apply boolean operation and return target body info.
    Otherwise return the new body info."""
    boolean_op = params.get("boolean")
    target_name = params.get("target")

    if not boolean_op or not target_name:
        context.try_embed(new_body, params.get("_op", "create"), params)
        return body_info(new_body)

    root = design.rootComponent
    target = find_body(design, target_name)
    if not target:
        raise ValueError(f"Target body not found: {target_name}")

    op_map = {
        "union": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "subtract": adsk.fusion.FeatureOperations.CutFeatureOperation,
        "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    op = op_map.get(boolean_op.lower())
    if op is None:
        raise ValueError(f"Unknown boolean operation: {boolean_op}. Use union/subtract/intersect.")

    vol_before = target.volume
    # Read the tool's name and reason BEFORE the combine consumes it.
    tool_name = new_body.name
    tool_reason = context.absorbed_reason(new_body, params)

    combine_feats = root.features.combineFeatures
    tool_bodies = adsk.core.ObjectCollection.create()
    tool_bodies.add(new_body)
    combine_input = combine_feats.createInput(target, tool_bodies)
    combine_input.operation = op
    combine_input.isKeepToolBodies = False
    combine = combine_feats.add(combine_input)
    if not combine:
        raise RuntimeError(
            "combineFeatures.add returned None (%s of '%s' into '%s')"
            % (boolean_op, tool_name, target_name))

    # Provenance goes on the target body (its operation history), but intent
    # belongs to the boolean feature itself — otherwise successive cuts would
    # overwrite the target body's own intent.
    op_name = params.get("_op", "create")
    absorbed = dict(params)
    absorbed["_consumed"] = tool_name
    absorbed["intent"] = tool_reason
    # Labelled as a modification of the target, so the reason lands in the
    # target's provenance instead of overwriting why the target exists.
    context.try_embed(target, "%s:%s" % (boolean_op.lower(), op_name), absorbed)
    if combine and any(params.get(k) is not None for k in context.CONTEXT_PARAM_KEYS):
        context.try_embed(combine, op_name, params)

    result = body_info(target)
    result["volume_before_cm3"] = vol_before
    result["volume_delta_cm3"] = round(result["volume_cm3"] - vol_before, 6)

    # Fusion reports success either way, so the geometry is the only evidence.
    # A Join between bodies that never touch leaves both of them standing and
    # moves no volume: silence here reads as "merged" and is the opposite.
    if result["volume_delta_cm3"] == 0:
        # Do not claim the tool was consumed: a Join that merged nothing leaves
        # the body in the design, and Fusion renames it after the target, so
        # the old name no longer finds it.
        result["warning"] = (
            "%s moved no volume. Fusion neither merges nor cuts bodies that do "
            "not touch, and reports success either way — check that the tool "
            "overlapped the target. If it did not, the tool body is still in "
            "the design under a name derived from '%s'." % (boolean_op, target_name))
    result["boolean"] = boolean_op
    return result


def create_box(params: dict) -> dict:
    """Create a rectangular box centered at position."""
    params.setdefault("_op", "create_box")
    design = _get_design()
    root = design.rootComponent

    w = _mm2cm(params["width"])
    h = _mm2cm(params["height"])
    d = _mm2cm(params["depth"])
    pos = params.get("position", [0, 0, 0])
    cx, cy, cz = _mm2cm(pos[0]), _mm2cm(pos[1]), _mm2cm(pos[2])

    # Sketch on XY plane (offset by Z if needed)
    sketches = root.sketches
    xy_plane = root.xYConstructionPlane

    # If Z offset, create an offset plane
    if abs(cz) > 1e-8:
        planes = root.constructionPlanes
        plane_input = planes.createInput()
        offset = adsk.core.ValueInput.createByReal(cz)
        plane_input.setByOffset(xy_plane, offset)
        sketch_plane = planes.add(plane_input)
    else:
        sketch_plane = xy_plane

    sketch = sketches.add(sketch_plane)

    # Draw rectangle centered at (cx, cy)
    x0, y0 = cx - w / 2, cy - d / 2
    x1, y1 = cx + w / 2, cy + d / 2
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(x0, y0, 0),
        adsk.core.Point3D.create(x1, y1, 0),
    )

    profile = sketch.profiles.item(0)

    # Extrude
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(
        profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(h))
    ext = extrudes.add(ext_input)

    body = ext.bodies.item(0)
    if params.get("name"):
        body.name = params["name"]

    return _apply_boolean(params, design, body)


def create_cylinder(params: dict) -> dict:
    """Create a cylinder with base center at position."""
    params.setdefault("_op", "create_cylinder")
    design = _get_design()
    root = design.rootComponent

    radius = _mm2cm(params["diameter"]) / 2
    h = _mm2cm(params["height"])
    pos = params.get("position", [0, 0, 0])
    cx, cy, cz = _mm2cm(pos[0]), _mm2cm(pos[1]), _mm2cm(pos[2])

    # Sketch plane
    xy_plane = root.xYConstructionPlane
    if abs(cz) > 1e-8:
        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(xy_plane, adsk.core.ValueInput.createByReal(cz))
        sketch_plane = planes.add(plane_input)
    else:
        sketch_plane = xy_plane

    sketch = root.sketches.add(sketch_plane)

    # Draw circle
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(cx, cy, 0), radius
    )

    profile = sketch.profiles.item(0)

    # Extrude
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(
        profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(h))
    ext = extrudes.add(ext_input)

    body = ext.bodies.item(0)
    if params.get("name"):
        body.name = params["name"]

    return _apply_boolean(params, design, body)


def _to_sketch_xy(sketch, x_cm: float, z_cm: float):
    """Put a world (x, z) point into a sketch's own 2D coordinates.

    A sketch on the XZ plane carries world Z on its local Y axis, but Fusion
    orients that axis the opposite way, so writing world coordinates straight
    into the sketch mirrors everything through the origin. On a shape with no
    handedness — a sphere — nothing looks wrong until it is measured, or
    printed. Ask the sketch where the point goes instead of assuming.
    """
    local = sketch.modelToSketchSpace(adsk.core.Point3D.create(x_cm, 0, z_cm))
    return local.x, local.y


def create_sphere(params: dict) -> dict:
    """Create a sphere centered at position using revolve."""
    params.setdefault("_op", "create_sphere")
    design = _get_design()
    root = design.rootComponent

    radius = _mm2cm(params["diameter"]) / 2
    pos = params.get("position", [0, 0, 0])
    cx, cy, cz = _mm2cm(pos[0]), _mm2cm(pos[1]), _mm2cm(pos[2])

    # Sketch on XZ plane passing through center
    xz_plane = root.xZConstructionPlane
    sketch = root.sketches.add(xz_plane)

    # Draw semicircle + axis line
    # In XZ sketch, local coords are (x_world, z_world)
    sx, sy = _to_sketch_xy(sketch, cx, cz)
    center = adsk.core.Point3D.create(sx, sy, 0)
    top = adsk.core.Point3D.create(sx, sy + radius, 0)
    bottom = adsk.core.Point3D.create(sx, sy - radius, 0)

    # Half-circle arc
    sketch.sketchCurves.sketchArcs.addByThreePoints(
        top,
        adsk.core.Point3D.create(sx + radius, sy, 0),
        bottom,
    )

    # Close with diameter line
    sketch.sketchCurves.sketchLines.addByTwoPoints(bottom, top)

    profile = sketch.profiles.item(0)

    # Revolve axis: the diameter line (Y axis in sketch = Z in world)
    axis_line = sketch.sketchCurves.sketchLines.item(0)

    revolves = root.features.revolveFeatures
    rev_input = revolves.createInput(
        profile, axis_line, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    rev_input.setAngleExtent(False, adsk.core.ValueInput.createByString("360 deg"))
    rev = revolves.add(rev_input)

    body = rev.bodies.item(0)
    if params.get("name"):
        body.name = params["name"]

    # Move to Y position if needed
    if abs(cy) > 1e-8:
        move_feats = root.features.moveFeatures
        bodies_collection = adsk.core.ObjectCollection.create()
        bodies_collection.add(body)
        transform = adsk.core.Matrix3D.create()
        transform.translation = adsk.core.Vector3D.create(0, cy, 0)
        move_input = move_feats.createInput(bodies_collection, transform)
        move_feats.add(move_input)

    return _apply_boolean(params, design, body)


def create_cone(params: dict) -> dict:
    """Create a cone or frustum using revolve."""
    params.setdefault("_op", "create_cone")
    design = _get_design()
    root = design.rootComponent

    base_r = _mm2cm(params["base_diameter"]) / 2
    top_r = _mm2cm(params["top_diameter"]) / 2
    h = _mm2cm(params["height"])
    pos = params.get("position", [0, 0, 0])
    cx, cy, cz = _mm2cm(pos[0]), _mm2cm(pos[1]), _mm2cm(pos[2])

    # Sketch on XZ plane
    xz_plane = root.xZConstructionPlane
    sketch = root.sketches.add(xz_plane)

    # Draw trapezoid profile (or triangle if top_r == 0)
    lines = sketch.sketchCurves.sketchLines

    # Points: bottom-right, top-right, top-left (axis), bottom-left (axis)
    bx, by = _to_sketch_xy(sketch, cx, cz)
    _, ty = _to_sketch_xy(sketch, cx, cz + h)
    p_br = adsk.core.Point3D.create(bx + base_r, by, 0)
    p_tr = adsk.core.Point3D.create(bx + top_r, ty, 0)
    p_tl = adsk.core.Point3D.create(bx, ty, 0)
    p_bl = adsk.core.Point3D.create(bx, by, 0)

    lines.addByTwoPoints(p_bl, p_br)  # bottom edge
    lines.addByTwoPoints(p_br, p_tr)  # right edge (slant)
    if top_r > 1e-8:
        lines.addByTwoPoints(p_tr, p_tl)  # top edge
    else:
        p_tl = p_tr  # pointed cone
    lines.addByTwoPoints(p_tl, p_bl)  # axis edge

    profile = sketch.profiles.item(0)

    # Revolve around the axis (the left edge)
    axis_line = lines.item(lines.count - 1)  # last line = axis

    revolves = root.features.revolveFeatures
    rev_input = revolves.createInput(
        profile, axis_line, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    rev_input.setAngleExtent(False, adsk.core.ValueInput.createByString("360 deg"))
    rev = revolves.add(rev_input)

    body = rev.bodies.item(0)
    if params.get("name"):
        body.name = params["name"]

    # Move to Y position if needed
    if abs(cy) > 1e-8:
        move_feats = root.features.moveFeatures
        bodies_collection = adsk.core.ObjectCollection.create()
        bodies_collection.add(body)
        transform = adsk.core.Matrix3D.create()
        transform.translation = adsk.core.Vector3D.create(0, cy, 0)
        move_input = move_feats.createInput(bodies_collection, transform)
        move_feats.add(move_input)

    return _apply_boolean(params, design, body)


def create_polygon(params: dict) -> dict:
    """Create an extruded polygon from a list of 2D points.
    Points define the cross-section on the XY plane, extruded along Z."""
    params.setdefault("_op", "create_polygon")
    design = _get_design()
    root = design.rootComponent

    points = params["points"]  # list of [x, y] in mm
    h = _mm2cm(params["height"])
    pos = params.get("position", [0, 0, 0])
    cx, cy, cz = _mm2cm(pos[0]), _mm2cm(pos[1]), _mm2cm(pos[2])

    if len(points) < 3:
        raise ValueError("Polygon requires at least 3 points.")

    # Sketch plane
    xy_plane = root.xYConstructionPlane
    if abs(cz) > 1e-8:
        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(xy_plane, adsk.core.ValueInput.createByReal(cz))
        sketch_plane = planes.add(plane_input)
    else:
        sketch_plane = xy_plane

    sketch = root.sketches.add(sketch_plane)
    lines = sketch.sketchCurves.sketchLines

    # Draw closed polygon
    pts = [adsk.core.Point3D.create(_mm2cm(p[0]) + cx, _mm2cm(p[1]) + cy, 0) for p in points]
    for i in range(len(pts)):
        lines.addByTwoPoints(pts[i], pts[(i + 1) % len(pts)])

    if sketch.profiles.count == 0:
        raise RuntimeError("Polygon sketch produced no profile. Check that points form a closed shape.")

    profile = sketch.profiles.item(0)

    # Extrude
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(
        profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(h))
    ext = extrudes.add(ext_input)

    body = ext.bodies.item(0)
    if params.get("name"):
        body.name = params["name"]

    return _apply_boolean(params, design, body)


ACTIONS = {
    "create_box": create_box,
    "create_cylinder": create_cylinder,
    "create_sphere": create_sphere,
    "create_cone": create_cone,
    "create_polygon": create_polygon,
}
