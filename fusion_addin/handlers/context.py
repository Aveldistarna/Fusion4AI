"""
Context handlers — embed design intent and operation provenance into entities.

The design document itself is the world model: intent metadata lives in Fusion
Attributes (group "fusion4ai") attached directly to bodies/sketches/features,
so it travels with the geometry and survives copy/save/exchange.

Attributes:
  fusion4ai/context    — JSON: {intent, role, depends_on[], constraints[], updated_at}
  fusion4ai/provenance — JSON: [{op, params, at}, ...]  (operation history, capped)
"""

import adsk.core
import adsk.fusion
import json
import traceback
from datetime import datetime
from typing import Any, List, Optional, Tuple

from ..utils.naming import find_body

ATTR_GROUP = "fusion4ai"
ATTR_CONTEXT = "context"
ATTR_PROVENANCE = "provenance"
MAX_PROVENANCE_ENTRIES = 20

# Param keys that are consumed by context embedding, not part of the geometry op
CONTEXT_PARAM_KEYS = ("intent", "role", "depends_on", "constraints")


def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active Fusion design.")
    return design


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Entity resolution (bodies, sketches, timeline features, raw tokens)
# ---------------------------------------------------------------------------

def resolve_entity(design: adsk.fusion.Design, ref: str) -> Tuple[Optional[Any], str]:
    """Resolve a reference (name or entityToken) to an entity.
    Returns (entity, kind) where kind is body/sketch/feature/entity, or (None, "")."""
    body = find_body(design, ref)
    if body:
        return body, "body"

    for i in range(design.allComponents.count):
        comp = design.allComponents.item(i)
        for j in range(comp.sketches.count):
            sketch = comp.sketches.item(j)
            if sketch.name == ref or sketch.entityToken == ref:
                return sketch, "sketch"

    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        timeline = design.timeline
        for i in range(timeline.count):
            item = timeline.item(i)
            try:
                if item.name == ref and item.entity:
                    return item.entity, "feature"
                entity = item.entity
                if entity and getattr(entity, "name", None) == ref:
                    return entity, "feature"
            except Exception:
                continue

    try:
        entities = design.findEntityByToken(ref)
        if entities:
            return entities[0], "entity"
    except Exception:
        pass

    return None, ""


def entity_brief(entity: Any, kind: str = "") -> dict:
    """Standardized lightweight descriptor of an entity."""
    info: dict = {"type": kind or type(entity).__name__}
    name = getattr(entity, "name", None)
    if name:
        info["name"] = name
    token = getattr(entity, "entityToken", None)
    if token:
        info["id"] = token
    return info


# ---------------------------------------------------------------------------
# Attribute JSON helpers
# ---------------------------------------------------------------------------

def _read_json_attr(entity: Any, attr_name: str) -> Any:
    attrs = getattr(entity, "attributes", None)
    if not attrs:
        return None
    attr = attrs.itemByName(ATTR_GROUP, attr_name)
    if not attr or not attr.value:
        return None
    try:
        return json.loads(attr.value)
    except json.JSONDecodeError:
        return None


def _write_json_attr(entity: Any, attr_name: str, data: Any) -> None:
    attrs = getattr(entity, "attributes", None)
    if attrs is None:
        raise RuntimeError(f"Entity does not support attributes: {type(entity).__name__}")
    value = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    existing = attrs.itemByName(ATTR_GROUP, attr_name)
    if existing:
        existing.value = value
    else:
        attrs.add(ATTR_GROUP, attr_name, value)


# ---------------------------------------------------------------------------
# Core embedding logic (also used from primitives/modifications handlers)
# ---------------------------------------------------------------------------

def _resolve_dependency(design: adsk.fusion.Design, ref: str) -> Tuple[dict, Optional[str]]:
    """Resolve a depends_on reference. Returns (record, warning_or_None)."""
    entity, kind = resolve_entity(design, ref)
    if entity:
        record = {"ref": ref, "kind": kind}
        token = getattr(entity, "entityToken", None)
        if token:
            record["token"] = token
        name = getattr(entity, "name", None)
        if name and name != ref:
            record["name"] = name
        return record, None
    return {"ref": ref}, f"depends_on reference not found: {ref}"


def merge_context(
    entity: Any,
    intent: Optional[str] = None,
    role: Optional[str] = None,
    depends_on: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
) -> Tuple[dict, List[str]]:
    """Merge new context fields into the entity's context attribute.
    Returns (stored_context, warnings)."""
    design = _get_design()
    context = _read_json_attr(entity, ATTR_CONTEXT) or {}
    warnings: List[str] = []

    if intent is not None:
        context["intent"] = intent
    if role is not None:
        context["role"] = role
    if constraints is not None:
        context["constraints"] = constraints
    if depends_on is not None:
        resolved = []
        for ref in depends_on:
            record, warning = _resolve_dependency(design, ref)
            resolved.append(record)
            if warning:
                warnings.append(warning)
        context["depends_on"] = resolved

    context["updated_at"] = _now()
    _write_json_attr(entity, ATTR_CONTEXT, context)
    return context, warnings


def record_provenance(entity: Any, op: str, params: dict) -> None:
    """Append an operation record to the entity's provenance attribute."""
    clean_params = {
        k: v
        for k, v in params.items()
        if v is not None and not k.startswith("_") and k not in CONTEXT_PARAM_KEYS
    }
    history = _read_json_attr(entity, ATTR_PROVENANCE) or []
    history.append({"op": op, "params": clean_params, "at": _now()})
    if len(history) > MAX_PROVENANCE_ENTRIES:
        history = history[-MAX_PROVENANCE_ENTRIES:]
    _write_json_attr(entity, ATTR_PROVENANCE, history)


def try_embed(entity: Any, op: str, params: dict) -> None:
    """Best-effort embedding of provenance + inline context params.
    Never raises — context embedding must not break a modeling operation."""
    try:
        record_provenance(entity, op, params)
        if any(params.get(k) is not None for k in CONTEXT_PARAM_KEYS):
            merge_context(
                entity,
                intent=params.get("intent"),
                role=params.get("role"),
                depends_on=params.get("depends_on"),
                constraints=params.get("constraints"),
            )
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------

def _all_context_entries(design: adsk.fusion.Design) -> List[Tuple[Any, dict]]:
    """All (entity, context) pairs in the design."""
    entries = []
    try:
        attrs = design.findAttributes(ATTR_GROUP, ATTR_CONTEXT)
    except Exception:
        attrs = []
    for attr in attrs:
        try:
            entity = attr.parent
            if not entity:
                continue
            context = json.loads(attr.value) if attr.value else None
            if context is not None:
                entries.append((entity, context))
        except Exception:
            continue
    return entries


def _matches_target(dep: dict, target_token: Optional[str], target_name: Optional[str]) -> bool:
    if target_token and dep.get("token") == target_token:
        return True
    if target_name and (dep.get("ref") == target_name or dep.get("name") == target_name):
        return True
    return False


def _find_dependents_of(
    design: adsk.fusion.Design, target_token: Optional[str], target_name: Optional[str]
) -> List[dict]:
    dependents = []
    for entity, context in _all_context_entries(design):
        deps = context.get("depends_on") or []
        matched = [d for d in deps if _matches_target(d, target_token, target_name)]
        if matched:
            info = entity_brief(entity)
            info["intent"] = context.get("intent")
            info["via"] = [d.get("ref") for d in matched]
            dependents.append(info)
    return dependents


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def set_context(params: dict) -> dict:
    """Attach or update design intent on a body/sketch/feature."""
    design = _get_design()
    entity, kind = resolve_entity(design, params["target"])
    if not entity:
        raise ValueError(f"Target not found: {params['target']}")

    context, warnings = merge_context(
        entity,
        intent=params.get("intent"),
        role=params.get("role"),
        depends_on=params.get("depends_on"),
        constraints=params.get("constraints"),
    )
    result = {"target": entity_brief(entity, kind), "context": context}
    if warnings:
        result["warnings"] = warnings
    return result


def get_context(params: dict) -> dict:
    """Read intent, provenance, and dependents of an entity — 'why is this here?'"""
    design = _get_design()
    entity, kind = resolve_entity(design, params["target"])
    if not entity:
        raise ValueError(f"Target not found: {params['target']}")

    token = getattr(entity, "entityToken", None)
    name = getattr(entity, "name", None)
    return {
        "target": entity_brief(entity, kind),
        "context": _read_json_attr(entity, ATTR_CONTEXT),
        "provenance": _read_json_attr(entity, ATTR_PROVENANCE),
        "dependents": _find_dependents_of(design, token, name),
    }


def list_contexts(params: dict) -> dict:
    """Semantic map of the design: all annotated entities + unannotated bodies."""
    design = _get_design()

    annotated = []
    annotated_tokens = set()
    annotated_names = set()
    for entity, context in _all_context_entries(design):
        info = entity_brief(entity)
        info["context"] = context
        annotated.append(info)
        token = getattr(entity, "entityToken", None)
        if token:
            annotated_tokens.add(token)
        name = getattr(entity, "name", None)
        if name:
            annotated_names.add(name)

    # entityToken strings are not guaranteed stable across sessions, so match
    # by token OR name when deciding whether a body is annotated.
    unannotated_bodies = []
    for i in range(design.allComponents.count):
        comp = design.allComponents.item(i)
        for j in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(j)
            if body.entityToken not in annotated_tokens and body.name not in annotated_names:
                unannotated_bodies.append(body.name)

    return {
        "annotated": annotated,
        "annotated_count": len(annotated),
        "unannotated_bodies": unannotated_bodies,
    }


def find_dependents(params: dict) -> dict:
    """Impact analysis: what depends on this entity (breaks if removed/changed)?"""
    design = _get_design()
    entity, kind = resolve_entity(design, params["target"])
    if not entity:
        raise ValueError(f"Target not found: {params['target']}")

    token = getattr(entity, "entityToken", None)
    name = getattr(entity, "name", None)
    dependents = _find_dependents_of(design, token, name)
    own_context = _read_json_attr(entity, ATTR_CONTEXT) or {}

    return {
        "target": entity_brief(entity, kind),
        "dependents": dependents,
        "dependents_count": len(dependents),
        "own_depends_on": own_context.get("depends_on", []),
        "safe_to_modify": len(dependents) == 0,
    }


def check_integrity(params: dict) -> dict:
    """Reconciliation: find dangling depends_on references and unannotated bodies."""
    design = _get_design()

    dangling = []
    for entity, context in _all_context_entries(design):
        for dep in context.get("depends_on") or []:
            resolved = None
            token = dep.get("token")
            if token:
                try:
                    found = design.findEntityByToken(token)
                    resolved = found[0] if found else None
                except Exception:
                    resolved = None
            if not resolved and dep.get("ref"):
                resolved, _ = resolve_entity(design, dep["ref"])
            if not resolved:
                record = entity_brief(entity)
                record["missing_dependency"] = dep.get("ref") or dep.get("name") or token
                record["intent"] = context.get("intent")
                dangling.append(record)

    scan = list_contexts({})
    return {
        "dangling_references": dangling,
        "dangling_count": len(dangling),
        "unannotated_bodies": scan["unannotated_bodies"],
        "annotated_count": scan["annotated_count"],
        "ok": len(dangling) == 0,
    }


ACTIONS = {
    "set_context": set_context,
    "get_context": get_context,
    "list_contexts": list_contexts,
    "find_dependents": find_dependents,
    "check_integrity": check_integrity,
}
