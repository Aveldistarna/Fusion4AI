"""
Context handlers — embed design intent and operation provenance into entities.

The design document itself is the world model: intent metadata lives in Fusion
Attributes (group "fusion4ai") attached directly to bodies/sketches/features,
so it travels with the geometry and survives copy/save/exchange.

A reason is recorded in three parts, because they go missing separately and
answer different questions:
  intent      — WHY this exists at all
  placement   — WHY it sits at this position/orientation
  dimensions  — WHY it is this size (the arithmetic behind the numbers)
  shape       — WHAT it is, as its author understood it. Prose about geometry
                goes stale on the next edit, so writing it stamps a
                fingerprint of the measured shape; a later mismatch says the
                sentence now describes a body that no longer exists.
Prose in any of them decays as the design moves; constraints[] is the half a
machine re-checks (see constraints.py for the grammar).

Attributes:
  fusion4ai/context    — JSON: {intent, placement, dimensions, role,
                                depends_on[], constraints[], updated_at}
  fusion4ai/provenance — JSON: [{op, params, at}, ...]  (operation history, capped)
"""

import adsk.core
import adsk.fusion
import json
import traceback
from datetime import datetime
from typing import Any, List, Optional, Tuple

from ..utils.naming import find_body
from . import constraints as constraint_rules

ATTR_GROUP = "fusion4ai"
ATTR_CONTEXT = "context"
ATTR_PROVENANCE = "provenance"
MAX_PROVENANCE_ENTRIES = 20

# Which operations CREATE a body: their intent describes the body itself.
# Every other operation MODIFIES one, and its intent describes the operation —
# recording a fillet's reason as the body's reason overwrites why the body
# exists at all, leaving the fillet's reason as the only one left standing.
CREATION_OPS = {
    "create", "create_box", "create_cylinder", "create_sphere",
    "create_cone", "create_polygon", "copy_body",
}

# Param keys that are consumed by context embedding, not part of the geometry op
CONTEXT_PARAM_KEYS = ("intent", "placement", "dimensions", "shape", "role",
                      "depends_on", "constraints")


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
    placement: Optional[str] = None,
    dimensions: Optional[str] = None,
    shape: Optional[str] = None,
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
    if placement is not None:
        context["placement"] = placement
    if dimensions is not None:
        context["dimensions"] = dimensions
    if shape is not None:
        context["shape"] = shape
        # Stamp what the sentence was written about, so drift is detectable.
        try:
            if hasattr(entity, "faces"):
                from . import shape as shape_tools
                context["shape_fingerprint"] = shape_tools.fingerprint(entity)
        except Exception:
            warnings.append("shape recorded, but its fingerprint could not be taken")
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


def absorbed_reason(tool_entity: Any, params: dict) -> Optional[str]:
    """The reason to carry over when a body is consumed by another.

    A cut cylinder stops existing the moment it does its job. Whatever it was
    for has to move to the body that absorbed it, or "why is there a hole
    here" becomes unanswerable the instant it becomes a hole.
    """
    inline = params.get("intent")
    if inline:
        return inline
    try:
        existing = _read_json_attr(tool_entity, ATTR_CONTEXT) or {}
        return existing.get("intent")
    except Exception:
        return None


def _trim_provenance(history: List[dict]) -> List[dict]:
    """Cap the history, but never drop an entry that carries a reason.

    A fillet's radius can be re-derived from the geometry; why someone added
    it cannot. So the cap falls on the mechanical entries first, and a design
    with more recorded reasons than the cap keeps all of them.
    """
    if len(history) <= MAX_PROVENANCE_ENTRIES:
        return history
    with_reason = [h for h in history if h.get("intent")]
    plain = [h for h in history if not h.get("intent")]
    room = MAX_PROVENANCE_ENTRIES - len(with_reason)
    kept = with_reason + (plain[-room:] if room > 0 else [])
    kept.sort(key=lambda h: h.get("at") or "")
    return kept


def record_provenance(entity: Any, op: str, params: dict) -> None:
    """Append an operation record to the entity's provenance attribute.

    A modification's intent rides along here rather than on the body. It
    explains the operation, not the thing — and this is the only place it can
    live where the finished body can still be asked about it.
    """
    clean_params = {
        k: v
        for k, v in params.items()
        if v is not None and not k.startswith("_") and k not in CONTEXT_PARAM_KEYS
    }
    record = {"op": op, "params": clean_params, "at": _now()}
    if op not in CREATION_OPS:
        reason = params.get("intent")
        if reason:
            record["intent"] = reason
    if params.get("_consumed"):
        record["consumed"] = params["_consumed"]

    history = _read_json_attr(entity, ATTR_PROVENANCE) or []
    history.append(record)
    _write_json_attr(entity, ATTR_PROVENANCE, _trim_provenance(history))


def try_embed(entity: Any, op: str, params: dict) -> None:
    """Best-effort embedding of provenance + inline context params.
    Never raises — context embedding must not break a modeling operation."""
    try:
        record_provenance(entity, op, params)
        fields = {k: params.get(k) for k in CONTEXT_PARAM_KEYS}
        if op not in CREATION_OPS:
            # The operation's reason already went to provenance. Everything
            # else still describes the body — `shape` above all: re-describing
            # what a part BECAME after machining ("outer 20, 2mm wall tube")
            # is more use to the next reader than the cuts that got it there.
            fields["intent"] = None
        if any(v is not None for v in fields.values()):
            merge_context(entity, **fields)
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------

def _scan_contexts(
    design: adsk.fusion.Design,
) -> Tuple[List[Tuple[Any, dict]], List[Tuple[Any, dict]]]:
    """Scan every fusion4ai/context attribute. Returns (live, orphaned).

    An attribute on a B-Rep entity is never deleted automatically. If a later
    feature consumes the edge or face it was attached to (a fillet swallowing
    an edge, say), the attribute survives with a null parent. Those orphans are
    intent that no longer describes any geometry: they must be reported, not
    skipped, or the reasoning vanishes from the world model without a trace.

    Orphans are returned as (attribute, record) so the caller can purge them.
    """
    live: List[Tuple[Any, dict]] = []
    orphaned: List[Tuple[Any, dict]] = []
    try:
        attrs = design.findAttributes(ATTR_GROUP, ATTR_CONTEXT)
    except Exception:
        return live, orphaned

    for attr in attrs:
        try:
            context = json.loads(attr.value) if attr.value else None
        except Exception:
            continue
        if context is None:
            continue
        try:
            entity = attr.parent
        except Exception:
            entity = None
        if entity:
            live.append((entity, context))
        else:
            orphaned.append((attr, {
                "intent": context.get("intent"),
                "role": context.get("role"),
                "recorded_at": context.get("updated_at"),
                "context": context,
                "reason": "parent geometry no longer exists — consumed by a later "
                          "feature (fillet/chamfer/boolean) or deleted",
            }))
    return live, orphaned


def _all_context_entries(design: adsk.fusion.Design) -> List[Tuple[Any, dict]]:
    """All (entity, context) pairs whose entity still exists."""
    live, _ = _scan_contexts(design)
    return live


def _resolve_token(design: adsk.fusion.Design, token: str, cache: dict) -> Optional[Any]:
    """findEntityByToken, memoized for the duration of one lookup."""
    if token in cache:
        return cache[token]
    resolved = None
    try:
        found = design.findEntityByToken(token)
        resolved = found[0] if found else None
    except Exception:
        resolved = None
    cache[token] = resolved
    return resolved


def _same_entity(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    try:
        if a == b:
            return True
    except Exception:
        pass
    try:
        ta = getattr(a, "entityToken", None)
        return bool(ta) and ta == getattr(b, "entityToken", None)
    except Exception:
        return False


def _matches_target(
    design: adsk.fusion.Design,
    dep: dict,
    target: Optional[Any],
    target_token: Optional[str],
    target_name: Optional[str],
    cache: dict,
) -> bool:
    """Does this depends_on record point at the target entity?

    Token strings are not stable over time: the same entity can hand out
    different strings, so a string match proves identity but a mismatch proves
    nothing. Only findEntityByToken can settle it, so an unmatched token is
    resolved back to an entity before concluding it is a different one.
    """
    dep_token = dep.get("token")
    if target_token and dep_token == target_token:
        return True
    if target_name and (dep.get("ref") == target_name or dep.get("name") == target_name):
        return True
    if dep_token and target is not None:
        return _same_entity(_resolve_token(design, dep_token, cache), target)
    return False


def _find_dependents_of(
    design: adsk.fusion.Design,
    target: Optional[Any],
    target_token: Optional[str],
    target_name: Optional[str],
) -> List[dict]:
    dependents = []
    cache: dict = {}
    for entity, context in _all_context_entries(design):
        deps = context.get("depends_on") or []
        matched = [
            d for d in deps
            if _matches_target(design, d, target, target_token, target_name, cache)
        ]
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
        placement=params.get("placement"),
        dimensions=params.get("dimensions"),
        shape=params.get("shape"),
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
        "dependents": _find_dependents_of(design, entity, token, name),
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
    dependents = _find_dependents_of(design, entity, token, name)
    own_context = _read_json_attr(entity, ATTR_CONTEXT) or {}

    return {
        "target": entity_brief(entity, kind),
        "dependents": dependents,
        "dependents_count": len(dependents),
        "own_depends_on": own_context.get("depends_on", []),
        "safe_to_modify": len(dependents) == 0,
    }


def check_integrity(params: dict) -> dict:
    """Reconciliation: find dangling references, orphaned intent, unannotated bodies.

    Pass purge_orphans=True to delete intent whose geometry is gone. That is
    destructive and unrecoverable, so it is off by default: read the orphans
    first and re-attach anything still meaningful with set_intent.
    """
    design = _get_design()
    live, orphaned = _scan_contexts(design)

    purge = bool(params.get("purge_orphans"))
    orphan_records = []
    for attr, record in orphaned:
        if purge:
            try:
                attr.deleteMe()
                record["purged"] = True
            except Exception as e:
                record["purged"] = False
                record["purge_error"] = str(e)
        orphan_records.append(record)

    dangling = []
    for entity, context in live:
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

    # A shape description that no longer matches its body is worse than none:
    # it reads as current and is not. Only geometry can say which it is.
    stale_shapes = []
    try:
        from . import shape as shape_tools
        for entity, context in live:
            if not context.get("shape") or not hasattr(entity, "faces"):
                continue
            drift = shape_tools.fingerprint_drift(
                context.get("shape_fingerprint"), shape_tools.fingerprint(entity))
            if drift:
                stale_shapes.append({
                    "body": getattr(entity, "name", "?"),
                    "declared_shape": context.get("shape"),
                    "drift": drift,
                })
    except Exception:
        traceback.print_exc()

    # A verification stamped on a different shape is worse than none: it reads
    # as "someone checked this" about geometry nobody checked.
    stale_verifications = []
    try:
        from . import shape as shape_tools
        for entity, context in live:
            v = context.get("verification")
            if not v or not hasattr(entity, "faces"):
                continue
            drift = shape_tools.fingerprint_drift(
                v.get("fingerprint"), shape_tools.fingerprint(entity))
            if drift:
                stale_verifications.append({
                    "body": getattr(entity, "name", "?"),
                    "verified_at": v.get("at"),
                    "note": v.get("note"),
                    "drift": drift,
                })
            elif not v.get("matches"):
                stale_verifications.append({
                    "body": getattr(entity, "name", "?"),
                    "verified_at": v.get("at"),
                    "note": v.get("note"),
                    "mismatch": "recorded as NOT matching its intent",
                })
    except Exception:
        traceback.print_exc()

    scan = list_contexts({})
    remaining_orphans = [r for r in orphan_records if not r.get("purged")]
    result = {
        "dangling_references": dangling,
        "dangling_count": len(dangling),
        "orphaned_intent": orphan_records,
        "orphaned_count": len(orphan_records),
        "stale_shapes": stale_shapes,
        "stale_shape_count": len(stale_shapes),
        "stale_verifications": stale_verifications,
        "stale_verification_count": len(stale_verifications),
        "unannotated_bodies": scan["unannotated_bodies"],
        "annotated_count": scan["annotated_count"],
        "ok": (not dangling and not remaining_orphans and not stale_shapes
               and not stale_verifications),
    }
    if purge:
        result["purged_count"] = sum(1 for r in orphan_records if r.get("purged"))
    return result


def _body_constraint_rows(design) -> List[Tuple[Any, str, List[str]]]:
    """(body, name, constraints) for every body carrying constraints."""
    rows = []
    for entity, context in _all_context_entries(design):
        rules = context.get("constraints") or []
        if not rules:
            continue
        # Constraints are measured off bounding boxes, so only solid bodies
        # can carry them; a feature or sketch with rules is left to the review
        # to report as unchecked rather than silently measured wrong.
        if not hasattr(entity, "boundingBox"):
            continue
        rows.append((entity, getattr(entity, "name", "?"), rules))
    return rows


def review_geometry(params: dict) -> dict:
    """Re-measure recorded constraints against the geometry as it stands.

    The point of the exercise: Fusion checks that a model is valid, never that
    it still keeps the promises its designer made about it. Nothing else will
    notice a bracket drifting off the 3mm gap it was placed for.

    `unchecked` is reported as prominently as `violations` on purpose — a
    constraint outside the grammar was stored, not verified, and a review that
    hid that would let "no violations" mean "nothing was looked at".
    """
    design = _get_design()
    target = params.get("target")

    if target:
        entity, kind = resolve_entity(design, target)
        if not entity:
            raise ValueError(f"Target not found: {target}")
        context = _read_json_attr(entity, ATTR_CONTEXT) or {}
        rows = [(entity, getattr(entity, "name", target), context.get("constraints") or [])]
    else:
        rows = _body_constraint_rows(design)

    violations, unchecked, errors, satisfied = [], [], [], []
    for body, name, rules in rows:
        for check in constraint_rules.evaluate_all(design, body, rules):
            check["body"] = name
            status = check.get("status")
            if status == "violated":
                violations.append(check)
            elif status == "unchecked":
                unchecked.append(check)
            elif status == "error":
                errors.append(check)
            else:
                satisfied.append(check)

    checked = len(violations) + len(satisfied)
    result = {
        "violations": violations,
        "violation_count": len(violations),
        "unchecked": unchecked,
        "unchecked_count": len(unchecked),
        "errors": errors,
        "bodies_reviewed": len(rows),
        "constraints_checked": checked,
        "constraints_satisfied": len(satisfied),
        "ok": not violations and not errors,
    }
    if target:
        result["satisfied"] = satisfied
    return result


def review_related(design, body) -> Optional[dict]:
    """Constraints that this body's position could have broken — its own, and
    every rule elsewhere that names it. Cheap enough to run after each move."""
    try:
        name = getattr(body, "name", None)
        rows = []
        for other, other_name, rules in _body_constraint_rows(design):
            if other_name == name:
                rows.append((other, other_name, rules))
                continue
            relevant = [r for r in rules if constraint_rules.references(r) == name]
            if relevant:
                rows.append((other, other_name, relevant))
        if not rows:
            return None

        checks = []
        for target_body, target_name, rules in rows:
            for check in constraint_rules.evaluate_all(design, target_body, rules):
                check["body"] = target_name
                checks.append(check)

        counts = constraint_rules.summarize(checks)
        report = {"checked": len(checks), "summary": counts}
        breaks = [c for c in checks if c.get("status") in ("violated", "error")]
        if breaks:
            report["violations"] = breaks
        skipped = [c for c in checks if c.get("status") == "unchecked"]
        if skipped:
            report["unchecked"] = [c["constraint"] for c in skipped]
        return report
    except Exception:
        traceback.print_exc()
        return None


def _all_bodies(design) -> List[Any]:
    bodies = []
    for i in range(design.allComponents.count):
        comp = design.allComponents.item(i)
        for j in range(comp.bRepBodies.count):
            bodies.append(comp.bRepBodies.item(j))
    return bodies


def what_is_not_recorded(params: dict) -> dict:
    """WHICH BODIES HAVE NO RECORD — names only, nothing else.

    Every other door carries what it is filtering OUT: finding the three
    bodies nobody described means reading the whole map, and the map with the
    prose in it is the part that does not fit in an answer on a real design.
    This one carries only the absence, so it stays small at any size.

    Three questions per body, because a reason is recorded in three parts and
    they go missing separately: why it exists, why it sits there, why it is
    that size. Use it before a documenting pass, and again to see the pass
    finished.
    """
    design = _get_design()
    limit = int(params.get("limit") or 40)

    missing = {"intent": [], "placement": [], "dimensions": [], "shape": [],
               "constraints": [], "verification": []}
    total = 0
    complete = 0

    for body in _all_bodies(design):
        total += 1
        context = _read_json_attr(body, ATTR_CONTEXT) or {}
        name = body.name
        gaps = 0
        for field in ("intent", "placement", "dimensions", "shape"):
            if not context.get(field):
                missing[field].append(name)
                gaps += 1
        if not context.get("constraints"):
            missing["constraints"].append(name)
        # Never compared against its own geometry: not a failure, but not a
        # pass either — nobody has looked.
        if not context.get("verification"):
            missing["verification"].append(name)
        if gaps == 0:
            complete += 1

    result = {"bodies_total": total, "fully_described": complete}
    for field, names in missing.items():
        result["no_" + field] = names[:limit]
        result["no_%s_count" % field] = len(names)
    result["ok"] = not any(missing[f]
                           for f in ("intent", "placement", "dimensions",
                                     "shape", "verification"))
    return result


ACTIONS = {
    "set_context": set_context,
    "what_is_not_recorded": what_is_not_recorded,
    "review_geometry": review_geometry,
    "get_context": get_context,
    "list_contexts": list_contexts,
    "find_dependents": find_dependents,
    "check_integrity": check_integrity,
}
