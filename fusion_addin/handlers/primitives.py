"""
Primitive shape handlers — box, cylinder, sphere, cone.
All dimensions are received in mm, converted to cm for Fusion internal units.
"""

import adsk.core
import adsk.fusion
import math
from ..utils.naming import body_info, find_body


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
    combine_feats = root.features.combineFeatures
    tool_bodies = adsk.core.ObjectCollection.create()
    tool_bodies.add(new_body)
    combine_input = combine_feats.createInput(target, tool_bodies)
    combine_input.operation = op
    combine_input.isKeepToolBodies = False
    combine_feats.add(combine_input)

    result = body_info(target)
    result["volume_before_cm3"] = vol_before
    result["volume_delta_cm3"] = round(result["volume_cm3"] - vol_before, 6)
    result["boolean"] = boolean_op
    return result


def create_box(params: dict) -> dict:
    """Create a rectangular box centered at position."""
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


def create_sphere(params: dict) -> dict:
    """Create a sphere centered at position using revolve."""
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
    center = adsk.core.Point3D.create(cx, cz, 0)
    top = adsk.core.Point3D.create(cx, cz + radius, 0)
    bottom = adsk.core.Point3D.create(cx, cz - radius, 0)

    # Half-circle arc
    sketch.sketchCurves.sketchArcs.addByThreePoints(
        top,
        adsk.core.Point3D.create(cx + radius, cz, 0),
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
    p_br = adsk.core.Point3D.create(cx + base_r, cz, 0)
    p_tr = adsk.core.Point3D.create(cx + top_r, cz + h, 0)
    p_tl = adsk.core.Point3D.create(cx, cz + h, 0)
    p_bl = adsk.core.Point3D.create(cx, cz, 0)

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
