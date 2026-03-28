"""
Query handlers — inspect bodies, faces, and capture screenshots.
"""

import adsk.core
import adsk.fusion
import os
from ..utils.naming import body_info, find_body
from ..utils.geometry import face_normal, face_center, FACE_DIRECTIONS


def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active Fusion design.")
    return design


def _label_for_normal(nx: float, ny: float, nz: float) -> str:
    """Find the best semantic label for a face normal, or return '' if no good match."""
    best_label = ""
    best_dot = 0.8  # threshold — must be reasonably aligned
    for label, (dx, dy, dz) in FACE_DIRECTIONS.items():
        dot = nx * dx + ny * dy + nz * dz
        if dot > best_dot:
            best_dot = dot
            best_label = label
    return best_label


def get_bodies(params: dict) -> dict:
    """List all bodies in the design."""
    design = _get_design()
    bodies = []
    all_components = design.allComponents
    for i in range(all_components.count):
        comp = all_components.item(i)
        for j in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(j)
            bodies.append(body_info(body))
    return {"bodies": bodies, "count": len(bodies)}


def get_faces(params: dict) -> dict:
    """List faces of a body with type, center, normal, and semantic label."""
    design = _get_design()
    body = find_body(design, params["body_name"])
    if not body:
        raise ValueError(f"Body not found: {params['body_name']}")

    faces = []
    for face in body.faces:
        n = face_normal(face)
        c = face_center(face)

        face_type = "other"
        geom = face.geometry
        if isinstance(geom, adsk.core.Plane):
            face_type = "planar"
        elif isinstance(geom, adsk.core.Cylinder):
            face_type = "cylindrical"
        elif isinstance(geom, adsk.core.Sphere):
            face_type = "spherical"
        elif isinstance(geom, adsk.core.Cone):
            face_type = "conical"

        label = ""
        if n and face_type == "planar":
            label = _label_for_normal(n[0], n[1], n[2])

        face_data = {
            "id": face.entityToken,
            "type": face_type,
            "center_mm": [c[0] * 10, c[1] * 10, c[2] * 10] if c else None,
            "area_cm2": face.area,
        }
        if n:
            face_data["normal"] = [round(n[0], 4), round(n[1], 4), round(n[2], 4)]
        if label:
            face_data["label"] = label

        faces.append(face_data)

    return {"body": body.name, "faces": faces, "count": len(faces)}


def screenshot(params: dict) -> dict:
    """Capture the current viewport to a file."""
    app = adsk.core.Application.get()
    viewport = app.activeViewport

    output_path = params["output_path"]

    # Ensure directory exists
    dir_path = os.path.dirname(output_path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

    width = params.get("width", 1920)
    height = params.get("height", 1080)

    viewport.saveAsImageFile(output_path, width, height)

    return {"path": output_path, "width": width, "height": height}


def get_selection(params: dict) -> dict:
    """Get the user's current selection in Fusion UI."""
    app = adsk.core.Application.get()
    ui = app.userInterface
    selections = ui.activeSelections

    if selections.count == 0:
        return {"items": [], "count": 0, "message": "Nothing selected in Fusion."}

    items = []
    for i in range(selections.count):
        sel = selections.item(i)
        entity = sel.entity
        item: dict = {
            "index": i,
            "type": type(entity).__name__,
        }

        # Entity token for future reference
        if hasattr(entity, "entityToken"):
            item["id"] = entity.entityToken

        # Face details
        if isinstance(entity, adsk.fusion.BRepFace):
            n = face_normal(entity)
            c = face_center(entity)
            geom = entity.geometry
            if isinstance(geom, adsk.core.Plane):
                item["face_type"] = "planar"
            elif isinstance(geom, adsk.core.Cylinder):
                item["face_type"] = "cylindrical"
            elif isinstance(geom, adsk.core.Sphere):
                item["face_type"] = "spherical"
            elif isinstance(geom, adsk.core.Cone):
                item["face_type"] = "conical"
            else:
                item["face_type"] = "other"
            if c:
                item["center_mm"] = [c[0] * 10, c[1] * 10, c[2] * 10]
            if n:
                item["normal"] = [round(n[0], 4), round(n[1], 4), round(n[2], 4)]
                label = _label_for_normal(n[0], n[1], n[2])
                if label:
                    item["label"] = label
            item["area_cm2"] = entity.area
            # Parent body
            if entity.body:
                item["body_name"] = entity.body.name

        # Edge details
        elif isinstance(entity, adsk.fusion.BRepEdge):
            item["length_mm"] = entity.length * 10
            if entity.body:
                item["body_name"] = entity.body.name

        # Body details
        elif isinstance(entity, adsk.fusion.BRepBody):
            item["name"] = entity.name
            item["volume_cm3"] = entity.volume

        # Component details
        elif isinstance(entity, adsk.fusion.Occurrence):
            item["name"] = entity.name
            item["component"] = entity.component.name

        items.append(item)

    return {"items": items, "count": len(items)}


ACTIONS = {
    "get_bodies": get_bodies,
    "get_faces": get_faces,
    "screenshot": screenshot,
    "get_selection": get_selection,
}
