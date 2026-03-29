"""
Spatial awareness utilities — semantic face/edge resolution.

This module is the core differentiator of Fusion4AI:
it translates human-readable spatial references ("top", "front", etc.)
into concrete Fusion API geometry objects.
"""

import adsk.core
import adsk.fusion
import math
from typing import Optional, List, Tuple


# Direction vectors for semantic face names
FACE_DIRECTIONS = {
    "top":    ( 0.0,  0.0,  1.0),
    "bottom": ( 0.0,  0.0, -1.0),
    "front":  ( 0.0, -1.0,  0.0),
    "back":   ( 0.0,  1.0,  0.0),
    "left":   (-1.0,  0.0,  0.0),
    "right":  ( 1.0,  0.0,  0.0),
}


def resolve_face(
    body: adsk.fusion.BRepBody, face_ref: str
) -> Optional[adsk.fusion.BRepFace]:
    """
    Resolve a face reference to a BRepFace.

    face_ref can be:
      - A semantic name: "top", "bottom", "front", "back", "left", "right"
      - An entityToken string for exact match
    """
    # Try semantic name
    direction = FACE_DIRECTIONS.get(face_ref.lower())
    if direction:
        return _find_face_by_normal(body, direction)

    # Try entityToken
    for face in body.faces:
        if face.entityToken == face_ref:
            return face

    return None


def _edge_direction(edge: adsk.fusion.BRepEdge) -> Optional[Tuple[float, float, float]]:
    """Get the direction vector of a linear edge, or None if not linear."""
    geom = edge.geometry
    if isinstance(geom, adsk.core.Line3D):
        sp = edge.startVertex.geometry
        ep = edge.endVertex.geometry
        dx, dy, dz = ep.x - sp.x, ep.y - sp.y, ep.z - sp.z
        mag = math.sqrt(dx*dx + dy*dy + dz*dz)
        if mag > 1e-10:
            return (dx/mag, dy/mag, dz/mag)
    return None


def resolve_edges(
    body: adsk.fusion.BRepBody, edge_ref: str
) -> List[adsk.fusion.BRepEdge]:
    """
    Resolve an edge reference to a list of BRepEdges.

    edge_ref can be:
      - "all": all edges of the body
      - "top", "bottom", etc.: edges belonging to that face
      - "vertical": edges aligned with Z axis
      - "horizontal": edges perpendicular to Z axis
      - "between:face1,face2": edges shared by two faces (e.g. "between:front,right")
      - A comma-separated list of entityTokens
    """
    ref = edge_ref.strip().lower()

    if ref == "all":
        return list(body.edges)

    # Direction-based: vertical/horizontal
    if ref == "vertical":
        result = []
        for edge in body.edges:
            d = _edge_direction(edge)
            if d and abs(abs(d[2]) - 1.0) < 0.1:  # aligned with Z
                result.append(edge)
        return result

    if ref == "horizontal":
        result = []
        for edge in body.edges:
            d = _edge_direction(edge)
            if d and abs(d[2]) < 0.1:  # perpendicular to Z
                result.append(edge)
        return result

    # Between two faces: "between:front,right"
    if ref.startswith("between:"):
        face_names = ref[8:].split(",")
        if len(face_names) != 2:
            return []
        face1 = resolve_face(body, face_names[0].strip())
        face2 = resolve_face(body, face_names[1].strip())
        if not face1 or not face2:
            return []
        edges1 = set(e.entityToken for e in face1.edges)
        return [e for e in face2.edges if e.entityToken in edges1]

    # Semantic face name
    direction = FACE_DIRECTIONS.get(ref)
    if direction:
        face = _find_face_by_normal(body, direction)
        if face:
            return list(face.edges)
        return []

    # Try entityTokens (comma-separated)
    tokens = {t.strip() for t in edge_ref.split(",")}
    return [e for e in body.edges if e.entityToken in tokens]


def face_center(face: adsk.fusion.BRepFace) -> Tuple[float, float, float]:
    """Get the centroid of a face (in cm, Fusion internal units)."""
    # Use pointOnFace for a reliable point, then fall back to vertex average
    try:
        pt = face.pointOnFace
        return (pt.x, pt.y, pt.z)
    except Exception:
        pass

    # Fallback: average of vertices
    xs, ys, zs = [], [], []
    for vertex in face.vertices:
        p = vertex.geometry
        xs.append(p.x)
        ys.append(p.y)
        zs.append(p.z)
    if xs:
        return (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
    return (0.0, 0.0, 0.0)


def face_normal(face: adsk.fusion.BRepFace) -> Optional[Tuple[float, float, float]]:
    """Get the outward normal of a face at its center."""
    try:
        evaluator = face.evaluator
        # Get a point on the face and evaluate normal there
        pt = face.pointOnFace
        (ret, normal) = evaluator.getNormalAtPoint(pt)
        if ret:
            return (normal.x, normal.y, normal.z)
    except Exception:
        pass

    # Fallback for planar faces: use geometry directly
    try:
        geom = face.geometry
        if isinstance(geom, adsk.core.Plane):
            n = geom.normal
            return (n.x, n.y, n.z)
    except Exception:
        pass

    return None


def _find_face_by_normal(
    body: adsk.fusion.BRepBody, target_dir: Tuple[float, float, float]
) -> Optional[adsk.fusion.BRepFace]:
    """Find the planar face whose outward normal is closest to target_dir."""
    best_face = None
    best_dot = -2.0

    for face in body.faces:
        n = face_normal(face)
        if n is None:
            continue
        dot = n[0]*target_dir[0] + n[1]*target_dir[1] + n[2]*target_dir[2]
        if dot > best_dot:
            best_dot = dot
            best_face = face

    return best_face


def body_bounding_box_mm(body: adsk.fusion.BRepBody) -> dict:
    """Get bounding box in mm (converting from Fusion's internal cm)."""
    bb = body.boundingBox
    return {
        "min": [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10],
        "max": [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10],
    }
