#!/usr/bin/env python3
"""Compile a bounded local design system into CSS and inspectable previews."""
import argparse
import copy
from decimal import Decimal, ROUND_HALF_UP
import html
import json
import math
import re
import sys
import textwrap
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from figma_bridge import (
    CANONICAL_COMPONENT_FAMILIES,
    dimension_px,
    reject_secret_like_text,
    validate,
    validate_component_properties,
    variable_value,
)

NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
ALIAS = re.compile(r"^\{([a-zA-Z0-9_.-]+)\}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
DIMENSION = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]+)?)(?:px|rem)$")
FONT = re.compile(r"^[a-zA-Z][a-zA-Z0-9 -]*$")
PROPERTIES = {"background", "color", "border-color", "padding", "padding-inline", "padding-block", "gap", "border-radius", "font-family", "font-size"}
PROPERTY_TYPES = {"background": "color", "color": "color", "border-color": "color", "padding": "dimension", "padding-inline": "dimension", "padding-block": "dimension", "gap": "dimension", "border-radius": "dimension", "font-family": "fontFamily", "font-size": "dimension"}
PREVIEW_NODE_LIMIT = 512
PREVIEW_DEPTH_LIMIT = 32
DOM_SOURCE_STRING_KEYS = {
    "selector", "control_selector", "tag", "input_type", "button_type",
    "name", "placeholder", "label_for", "help_id", "error_id",
    "aria_describedby", "fieldset_legend", "table_caption", "th_scope",
}
DOM_SOURCE_BOOL_KEYS = {"required", "disabled", "checked", "readonly"}


def _validate_dom_source(dom_source, context):
    if not isinstance(dom_source, dict) or not dom_source:
        raise ValueError(f"dom_source must be a nonempty object in {context}")
    unknown = set(dom_source) - DOM_SOURCE_STRING_KEYS - DOM_SOURCE_BOOL_KEYS
    if unknown:
        raise ValueError(f"unsupported dom_source fields in {context}: {', '.join(sorted(unknown))}")
    for key in DOM_SOURCE_STRING_KEYS & set(dom_source):
        val = dom_source[key]
        if not isinstance(val, str) or not val.strip() or len(val) > 512:
            raise ValueError(f"invalid dom_source.{key} in {context}")
        if re.search(r"https?://", val, re.IGNORECASE):
            raise ValueError(f"external URL forbidden in {context}.dom_source.{key}")
        reject_secret_like_text(val, f"{context}.dom_source.{key}")
    for key in DOM_SOURCE_BOOL_KEYS & set(dom_source):
        if not isinstance(dom_source[key], bool):
            raise ValueError(f"dom_source.{key} must be boolean in {context}")


def _compile_component_families(raw_families, components, screens):
    if not isinstance(raw_families, list) or not 1 <= len(raw_families) <= 32:
        raise ValueError("componentFamilies must be a nonempty list of at most 32 declarations")
    seen_ids = set()
    seen_components = {}
    normalized_families = []
    allowed_family_keys = {"id", "version", "component", "layout", "axes", "properties", "usage"}
    allowed_prop_keys = {"id", "name", "type", "target", "targetKey", "default_value", "allowedFamilyIds", "preferred_values"}

    for entry in raw_families:
        if not isinstance(entry, dict) or set(entry) - allowed_family_keys:
            raise ValueError("invalid componentFamilies entry")
        fid = entry.get("id")
        if not isinstance(fid, str) or fid not in CANONICAL_COMPONENT_FAMILIES:
            raise ValueError(f"unsupported component family: {fid!r}")
        if fid in seen_ids:
            raise ValueError(f"duplicate component family: {fid}")
        if entry.get("version") != 1:
            raise ValueError(f"component family version must be 1: {fid}")
        spec = CANONICAL_COMPONENT_FAMILIES[fid]
        comp_name = entry.get("component", fid)
        if not isinstance(comp_name, str) or not NAME.fullmatch(comp_name):
            raise ValueError(f"invalid component name for family {fid}: {comp_name!r}")
        if comp_name in seen_components:
            raise ValueError(f"multiple component families cannot target the same component: {comp_name}")
        seen_ids.add(fid)
        seen_components[comp_name] = fid
        layout_mode = entry.get("layout", spec["layout"])
        if layout_mode not in ("VERTICAL", "HORIZONTAL"):
            raise ValueError(f"invalid layout for family {fid}: {layout_mode!r}")
        if spec["required_layout"] and layout_mode != spec["required_layout"]:
            raise ValueError(f"component family {fid} requires {spec['required_layout']} layout")
        axes = entry.get("axes")
        if not isinstance(axes, dict) or not axes:
            raise ValueError(f"component family axes required: {fid}")
        cleaned_axes = {}
        seen_axis_values = set()
        for axis_name, values in axes.items():
            if (not isinstance(axis_name, str) or not NAME.fullmatch(axis_name)
                    or not isinstance(values, list) or not values or len(values) != len(set(values))):
                raise ValueError(f"invalid family axis: {fid}.{axis_name}")
            for val in values:
                if not isinstance(val, str) or not NAME.fullmatch(val) or val in seen_axis_values:
                    raise ValueError(f"invalid or duplicate family axis value: {fid}.{axis_name}.{val}")
                if axis_name == "state" and val not in spec["canonical_states"]:
                    raise ValueError(f"undeclared state value for family {fid}: {val}")
                seen_axis_values.add(val)
            cleaned_axes[axis_name] = list(values)
        raw_props = entry.get("properties", [])
        if not isinstance(raw_props, list) or len(raw_props) > 32:
            raise ValueError(f"component family properties must be a list of at most 32 items: {fid}")
        seen_prop_ids = set()
        norm_props = []
        for prop in raw_props:
            if not isinstance(prop, dict) or set(prop) - allowed_prop_keys:
                raise ValueError(f"invalid property declaration in family {fid}")
            pid = prop.get("id")
            ptype = prop.get("type")
            if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", pid) or pid == "문구":
                raise ValueError(f"invalid property id in family {fid}: {pid!r}")
            if pid in seen_prop_ids:
                raise ValueError(f"duplicate property id in family {fid}: {pid}")
            seen_prop_ids.add(pid)
            if ptype not in ("TEXT", "BOOLEAN", "INSTANCE_SWAP"):
                raise ValueError(f"unsupported property type in family {fid}.{pid}: {ptype!r}")
            t_key = prop.get("targetKey", prop.get("target"))
            if ("targetKey" in prop and "target" in prop and prop["targetKey"] != prop["target"]) or not isinstance(t_key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", t_key):
                raise ValueError(f"invalid targetKey in family {fid}.{pid}")
            pname = prop.get("name", pid)
            if not isinstance(pname, str) or not pname.strip() or "#" in pname or pname == "문구":
                raise ValueError(f"invalid property display name in family {fid}.{pid}")
            if pid in (set(cleaned_axes) | {"Variant"}) or pname in (set(cleaned_axes) | {"Variant"}):
                raise ValueError(f"property name collides with variant axis in family {fid}.{pid}")
            norm_prop = {"id": pid, "name": pname, "type": ptype, "targetKey": t_key}
            if ptype == "TEXT":
                if "default_value" in prop:
                    if not isinstance(prop["default_value"], str):
                        raise ValueError(f"TEXT default_value must be string in {fid}.{pid}")
                    reject_secret_like_text(prop["default_value"], f"{fid}.{pid}.default_value")
                    norm_prop["default_value"] = prop["default_value"]
            elif ptype == "BOOLEAN":
                if "default_value" in prop:
                    if not isinstance(prop["default_value"], bool):
                        raise ValueError(f"BOOLEAN default_value must be boolean in {fid}.{pid}")
                    norm_prop["default_value"] = prop["default_value"]
            else:
                if t_key == "label":
                    raise ValueError(f"INSTANCE_SWAP targetKey cannot be label in {fid}.{pid}")
                allowed_fams = prop.get("allowedFamilyIds")
                if allowed_fams is None and fid == "table-row":
                    allowed_fams = ["table-cell"]
                if allowed_fams is not None:
                    if (not isinstance(allowed_fams, list) or not allowed_fams or len(allowed_fams) > 16
                            or any(not isinstance(af, str) or af not in CANONICAL_COMPONENT_FAMILIES for af in allowed_fams)):
                        raise ValueError(f"allowedFamilyIds must reference canonical families in {fid}.{pid}")
                    if fid == "table-row" and set(allowed_fams) != {"table-cell"}:
                        raise ValueError("table-row swap slots can only target table-cell")
                    norm_prop["allowedFamilyIds"] = list(dict.fromkeys(allowed_fams))
                if "default_value" in prop:
                    norm_prop["default_value"] = copy.deepcopy(prop["default_value"])
                if "preferred_values" in prop:
                    norm_prop["preferred_values"] = copy.deepcopy(prop["preferred_values"])
            norm_props.append(norm_prop)
        norm_entry = {
            "id": fid,
            "version": 1,
            "component": comp_name,
            "layout": layout_mode,
            "axes": cleaned_axes,
            "properties": norm_props,
        }
        if "usage" in entry:
            if not isinstance(entry["usage"], str) or not entry["usage"].strip():
                raise ValueError(f"usage must be nonempty text in family {fid}")
            norm_entry["usage"] = entry["usage"]
        normalized_families.append(norm_entry)

    family_to_comp = {item["id"]: item["component"] for item in normalized_families}
    preview = []
    for item in normalized_families:
        fid = item["id"]
        comp_name = item["component"]
        if comp_name not in components:
            preview.append({
                "id": fid,
                "component": comp_name,
                "status": "unmapped",
                "layout": item["layout"],
                "main_count": 0,
                "instance_count": 0,
                "swap_targets": [],
                "preserved_overrides": [],
            })
            continue
        comp = components[comp_name]
        declared_values = [val for vals in item["axes"].values() for val in vals]
        if set(comp["variants"]) != set(declared_values):
            raise ValueError(f"undeclared or missing variant combinations on {comp_name}: expected {declared_values}, got {list(comp['variants'])}")
        attach_declared_axes(components, {comp_name: item["axes"]})
        comp["family"] = fid
        comp["layout"] = item["layout"]
        if "usage" in item and "usage" not in comp:
            comp["usage"] = item["usage"]
        comp_props = dict(comp.get("properties", {}))
        swap_targets_union = list(comp.get("swap_targets", []))
        for prop in item["properties"]:
            pid = prop["id"]
            ptype = prop["type"]
            target = prop["targetKey"]
            compiled_prop = {"type": ptype, "target": target}
            if prop["name"] != pid:
                compiled_prop["name"] = prop["name"]
            if ptype == "TEXT":
                compiled_prop["default_value"] = prop.get("default_value", comp_name if target == "label" else "")
            elif ptype == "BOOLEAN":
                compiled_prop["default_value"] = prop.get("default_value", True)
            else:
                allowed_fams = prop.get("allowedFamilyIds", [])
                allowed_comps = []
                for af in allowed_fams:
                    mapped_comp = family_to_comp.get(af, af)
                    if mapped_comp not in components:
                        raise ValueError(f"swap target family {af} for {fid}.{pid} is unmapped")
                    if mapped_comp not in allowed_comps:
                        allowed_comps.append(mapped_comp)
                    if mapped_comp not in swap_targets_union:
                        swap_targets_union.append(mapped_comp)
                if allowed_comps:
                    compiled_prop["allowed_components"] = allowed_comps
                if "default_value" in prop:
                    compiled_prop["default_value"] = copy.deepcopy(prop["default_value"])
                elif allowed_comps:
                    first_c = allowed_comps[0]
                    first_v = next(iter(components[first_c]["variants"]))
                    compiled_prop["default_value"] = {"component": first_c, "variant": first_v}
                else:
                    raise ValueError(f"INSTANCE_SWAP property {fid}.{pid} requires default_value or mapped allowedFamilyIds")
                if "preferred_values" in prop:
                    compiled_prop["preferred_values"] = copy.deepcopy(prop["preferred_values"])
                elif allowed_comps:
                    compiled_prop["preferred_values"] = [
                        {"component": ac, "variant": av}
                        for ac in allowed_comps
                        for av in components[ac]["variants"]
                    ]
            if pid in comp_props and comp_props[pid] != compiled_prop:
                raise ValueError(f"conflicting component property definition for {comp_name}.{pid}")
            comp_props[pid] = compiled_prop
        if comp_props:
            comp["properties"] = comp_props
        if swap_targets_union:
            comp["swap_targets"] = swap_targets_union
        direct_instances = [
            el for screen in screens for el in screen.get("elements", [])
            if el.get("kind") == "component" and el.get("component") == comp_name
        ]
        preserved = sorted({
            f"{el.get('id', comp_name)}.{pk}"
            for el in direct_instances
            for pk in (el.get("property_values") or {})
        })
        preview.append({
            "id": fid,
            "component": comp_name,
            "status": "mapped",
            "layout": item["layout"],
            "main_count": len(comp["variants"]),
            "instance_count": len(direct_instances),
            "swap_targets": list(swap_targets_union),
            "preserved_overrides": preserved,
        })

    if any(row["status"] == "unmapped" for row in preview):
        overall_status = "unmapped"
    elif sum(row["instance_count"] for row in preview) > 0:
        overall_status = "ready"
        for row in preview:
            row["status"] = "ready"
    else:
        overall_status = "mapped"
    return normalized_families, overall_status, preview


def compile_design(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("design version must be 1")
    raw = {}

    def collect(group, prefix=(), inherited=None):
        if not isinstance(group, dict) or not group:
            raise ValueError("token groups must be nonempty objects")
        allowed_type = {"color", "dimension", "number", "fontFamily"}
        group_type = group.get("$type", inherited)
        if group_type is not None and group_type not in allowed_type:
            raise ValueError(f"invalid group type: {'.'.join(prefix)}")
        if "$description" in group and not isinstance(group["$description"], str):
            raise ValueError("description must be text")
        for key, item in sorted(group.items()):
            if key in {"$type", "$description"}:
                continue
            if not isinstance(key, str) or not NAME.fullmatch(key):
                raise ValueError(f"invalid token name: {key}")
            path = prefix + (key,)
            if isinstance(item, dict) and "$value" in item:
                kind = item.get("$type", group_type)
                if set(item) - {"$type", "$value", "$description"} or kind not in allowed_type or ("$description" in item and not isinstance(item["$description"], str)):
                    raise ValueError(f"invalid token: {'.'.join(path)}")
                raw[".".join(path)] = {"$type": kind, "$value": item["$value"]}
            else:
                collect(item, path, group_type)
    collect(data.get("tokens"))
    if not raw:
        raise ValueError("at least one token is required")
    resolved = {}
    visiting = set()
    css_names = set()
    for path in raw:
        name = "--" + path.replace(".", "-")
        if name in css_names:
            raise ValueError(f"CSS name collision: {name}")
        css_names.add(name)

    def resolve(path):
        if path in resolved:
            return resolved[path]
        if path in visiting:
            raise ValueError(f"cyclic alias: {path}")
        if path not in raw:
            raise ValueError(f"unknown token: {path}")
        visiting.add(path)
        token = raw[path]
        value = token["$value"]
        match = ALIAS.fullmatch(value) if isinstance(value, str) else None
        alias = match.group(1) if match else None
        if alias:
            target = resolve(alias)
            if target["type"] != token["$type"]:
                raise ValueError(f"alias type mismatch: {path} -> {alias}")
            value = target["value"]
        kind = token["$type"]
        if isinstance(value, dict) and kind == "color":
            if set(value) - {"colorSpace", "components", "alpha", "hex"} or value.get("colorSpace") != "srgb" or not isinstance(value.get("components"), list) or len(value["components"]) != 3:
                raise ValueError(f"unsupported color value: {path}")
            if "hex" in value and (not isinstance(value["hex"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value["hex"])):
                raise ValueError(f"invalid color fallback: {path}")
            channels = value["components"] + [value.get("alpha", 1)]
            if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and 0 <= x <= 1 for x in channels):
                raise ValueError(f"invalid color components: {path}")
            # The bridge stores 8-bit hex; round each channel to the nearest byte.
            encoded = [int((Decimal(str(x)) * 255).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) for x in channels]
            value = "#" + "".join(f"{x:02x}" for x in (encoded if encoded[3] != 255 else encoded[:3]))
        elif isinstance(value, dict) and kind == "dimension":
            number = value.get("value")
            if set(value) != {"value", "unit"} or value.get("unit") not in {"px", "rem"} or not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number) or number < 0:
                raise ValueError(f"invalid dimension value: {path}")
            value = format(Decimal(str(number)), "f") + value["unit"]
        valid = ((kind == "color" and isinstance(value, str) and COLOR.fullmatch(value)) or
                 (kind == "dimension" and isinstance(value, str) and DIMENSION.fullmatch(value)) or
                 (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)) or
                 (kind == "fontFamily" and isinstance(value, str) and FONT.fullmatch(value)))
        if not valid:
            raise ValueError(f"invalid {kind} value: {path}")
        visiting.remove(path)
        resolved[path] = {"type": kind, "value": value, "css_name": "--" + path.replace(".", "-"), "alias": alias}
        return resolved[path]
    for path in sorted(raw):
        resolve(path)
    resolved = dict(sorted(resolved.items()))
    raw_components = data.get("components")
    raw_screens = data.get("screens")
    if not isinstance(raw_components, dict) or not raw_components or not isinstance(raw_screens, list) or not raw_screens:
        raise ValueError("components and screens are required")
    components = copy.deepcopy(raw_components)
    screens = copy.deepcopy(raw_screens)
    classes = set()
    allowed_component_keys = {"usage", "properties", "family", "layout", "swap_targets", "slots", "variant_axes"}
    for name, component in components.items():
        if not NAME.fullmatch(name) or not isinstance(component, dict) or set(component) - allowed_component_keys != {"variants"} or not isinstance(component.get("variants"), dict) or not component["variants"]:
            raise ValueError(f"invalid component: {name}")
        if "usage" in component and (not isinstance(component["usage"], str) or not component["usage"].strip()):
            raise ValueError(f"usage description must be source text: {name}")
        for variant, styles in component["variants"].items():
            if not NAME.fullmatch(variant) or not isinstance(styles, dict) or not styles:
                raise ValueError(f"invalid variant: {name}.{variant}")
            class_name = f"{name}--{variant}"
            if class_name in classes:
                raise ValueError(f"component class collision: {class_name}")
            classes.add(class_name)
            for prop, token in styles.items():
                if prop not in PROPERTIES or not isinstance(token, str) or token not in resolved:
                    raise ValueError(f"unknown property or token: {name}.{variant}.{prop}")
                if resolved[token]["type"] != PROPERTY_TYPES[prop]:
                    raise ValueError(f"property type mismatch: {name}.{variant}.{prop}")
        if "variant_axes" in component:
            attach_declared_axes(components, {name: component["variant_axes"]})
    seen = set()
    screen_ids = {screen.get("id") for screen in screens if isinstance(screen, dict) and isinstance(screen.get("id"), str)}
    element_ids = set()
    for screen in screens:
        if not isinstance(screen, dict) or not {"id", "title", "trace", "elements"} <= set(screen) or set(screen) - {"id", "title", "trace", "elements", "annotation"} or ("annotation" in screen and not isinstance(screen["annotation"], str)) or not isinstance(screen["id"], str) or not NAME.fullmatch(screen["id"]) or screen["id"] in seen or not isinstance(screen["title"], str) or not isinstance(screen["trace"], list) or not screen["trace"] or not all(isinstance(x, str) and x for x in screen["trace"]) or not isinstance(screen["elements"], list) or not screen["elements"]:
            raise ValueError("invalid screen")
        seen.add(screen["id"])
        for element in screen["elements"]:
            if not isinstance(element, dict) or element.get("kind") not in {"heading", "text", "component"} or not isinstance(element.get("text"), str):
                raise ValueError(f"invalid element in {screen['id']}")
            if any(key in element and (not isinstance(element[key], str) or not element[key]) for key in ("id", "target_screen", "annotation", "action_id")):
                raise ValueError(f"invalid element metadata in {screen['id']}")
            if "id" in element:
                if element["id"] in element_ids:
                    raise ValueError(f"duplicate element id: {element['id']}")
                element_ids.add(element["id"])
            if "target_screen" in element and element["target_screen"] not in screen_ids:
                raise ValueError(f"unknown target screen: {element['target_screen']}")
            if "dom_source" in element:
                _validate_dom_source(element["dom_source"], f"{screen['id']}.{element.get('id', 'element')}")
            metadata = {"id", "target_screen", "annotation", "action_id", "dom_source"}
            if element["kind"] == "component":
                metadata.add("property_values")
                name, variant = element.get("component"), element.get("variant")
                if set(element) - metadata != {"kind", "text", "component", "variant"} or name not in components or variant not in components[name]["variants"]:
                    raise ValueError(f"unknown component variant in {screen['id']}")
            elif set(element) - metadata != {"kind", "text"}:
                raise ValueError(f"invalid element in {screen['id']}")
    if "variant_axes" in data:
        attach_declared_axes(components, data["variant_axes"])
    families_out = None
    if "componentFamilies" in data:
        families_out = _compile_component_families(data["componentFamilies"], components, screens)
    validate_component_properties(components, screens)
    result = {"version": 1, "tokens": resolved, "components": components, "screens": screens}
    if families_out is not None:
        norm_families, status, family_preview = families_out
        result["componentFamilies"] = norm_families
        result["status"] = status
        result["family_preview"] = family_preview
    return result


def attach_declared_axes(components, axes):
    """Record declared independent axes without creating missing combinations."""
    if not isinstance(axes, dict):
        raise ValueError("variant axes must be declared")
    for name, declared in axes.items():
        component = components.get(name)
        if not isinstance(component, dict) or not isinstance(component.get("variants"), dict):
            raise ValueError(f"variant axes require an existing component: {name}")
        if not isinstance(declared, dict) or not declared:
            raise ValueError(f"variant axes require declared values: {name}")
        seen = {}
        cleaned = {}
        for axis, values in declared.items():
            if not isinstance(axis, str) or not NAME.fullmatch(axis) or not isinstance(values, list) or not values or len(values) != len(set(values)):
                raise ValueError(f"invalid variant axis: {name}.{axis}")
            for value in values:
                if not isinstance(value, str) or value not in component["variants"] or value in seen:
                    raise ValueError(f"variant axis value must be one existing definition: {name}.{axis}.{value}")
                seen[value] = axis
            cleaned[axis] = list(values)
        component["variant_axes"] = cleaned
    return components


def components_css(design):
    component_css = []
    for name, component in design["components"].items():
        for variant, styles in component["variants"].items():
            ordered = sorted(styles)
            padding_fields = {"padding", "padding-inline", "padding-block"}
            if "padding" in styles and any(prop in styles for prop in padding_fields - {"padding"}):
                padding_order = iter(prop for prop in styles if prop in padding_fields)
                ordered = [next(padding_order) if prop in padding_fields else prop for prop in ordered]
            declarations = "; ".join(f"{prop}: var({design['tokens'][styles[prop]]['css_name']})" for prop in ordered)
            component_css.append(f".{name}--{variant} {{ {declarations}; }}")
    return "\n".join(component_css) + "\n"


def component_preview(design, name, variant, label, overrides=None, budget=None, depth=0):
    """Resolve a bounded visible component tree from native property defaults and instance overrides."""
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > PREVIEW_NODE_LIMIT or depth >= PREVIEW_DEPTH_LIMIT:
        raise ValueError("component preview expansion exceeds its bound")
    definition = design["components"][name]
    properties = definition.get("properties", {})
    overrides = overrides or {}
    resolved_label = label
    label_visible = True
    slot_visibility = {}
    text_slots = []
    swaps = []
    for prop_id, prop in properties.items():
        has_override = prop_id in overrides
        value = overrides[prop_id] if has_override else prop["default_value"]
        if prop["type"] == "TEXT":
            if prop["target"] == "label":
                if has_override:
                    resolved_label = value
            else:
                text_slots.append((prop["target"], value))
        elif prop["type"] == "BOOLEAN":
            if prop["target"] == "label":
                label_visible = value
            else:
                slot_visibility[prop["target"]] = value
        else:
            swaps.append((prop["target"], value))
    visible_texts = [
        {"slot": slot, "text": text_val}
        for slot, text_val in text_slots
        if slot_visibility.get(slot, True)
    ]
    children = []
    for slot, reference in swaps:
        if not slot_visibility.get(slot, True):
            continue
        child_name, child_variant = reference["component"], reference["variant"]
        children.append({"slot": slot, "node": component_preview(
            design, child_name, child_variant, child_name, budget=budget, depth=depth + 1)})
    result = {
        "component": name,
        "variant": variant,
        "styles": definition["variants"][variant],
        "label": resolved_label if label_visible else None,
        "children": children,
    }
    if visible_texts:
        result["text_slots"] = visible_texts
    return result


def _preview_html(node, root=False):
    esc = html.escape
    identity = esc(node["component"] + "--" + node["variant"], quote=True)
    label = f'<span class="component-label">{esc(node["label"])}</span>' if node["label"] is not None else ""
    texts = "".join(
        f'<span class="component-text-slot" data-text-slot="{esc(item["slot"], quote=True)}">{esc(item["text"])}</span>'
        for item in node.get("text_slots", [])
    )
    children = "".join(f'<div class="component-slot" data-slot="{esc(child["slot"], quote=True)}">{_preview_html(child["node"])}</div>' for child in node["children"])
    return f'<div class="component-property-node {identity}"' + (' data-component-root="true"' if root else '') + f'>{label}{texts}{children}</div>'


def render(design, styled):
    esc = html.escape
    css = [":root {"] + [f"  {v['css_name']}: " + (f"var({design['tokens'][v['alias']]['css_name']})" if v['alias'] else str(v['value'])) + ";" for v in design["tokens"].values()] + ["}"]
    pages = []
    for screen in design["screens"]:
        elements = []
        preview_budget = [0]
        for item in screen["elements"]:
            content = esc(item["text"])
            if item["kind"] == "heading":
                elements.append(f"<h2>{content}</h2>")
            elif item["kind"] == "text":
                elements.append(f"<p>{content}</p>")
            else:
                cls = esc(item["component"] + "--" + item["variant"], quote=True)
                definition = design["components"][item["component"]]
                if definition.get("properties"):
                    tree = component_preview(design, item["component"], item["variant"], item["text"],
                                             item.get("property_values"), preview_budget)
                    body = _preview_html(tree, root=True)
                    if item.get('target_screen'):
                        target = esc(item['target_screen'], quote=True)
                        elements.append(f'<a href="#{target}" class="component-property-link">{body}</a>')
                    else:
                        elements.append(body)
                    continue
                if item.get('target_screen'):
                    target = esc(item['target_screen'], quote=True)
                    elements.append(f'<a href="#{target}" class="component {cls}">{content}</a>')
                else:
                    elements.append(f'<div class="component {cls}">{content}</div>')
        pages.append(f'<section id="{esc(screen["id"], quote=True)}" aria-label="{esc(screen["title"], quote=True)}"><small>{esc(screen["id"])}</small>{"".join(elements)}</section>')
    base = "body{margin:0;padding:16px;background:#eef0f2;color:#20242a;font-family:system-ui,sans-serif}main{display:flex;flex-wrap:wrap;gap:24px}section{box-sizing:border-box;width:min(360px,100%);min-height:480px;background:white;padding:24px;border:1px solid #cdd2d8}small{color:#59616b;overflow-wrap:anywhere}h2{margin:20px 0 12px}p{line-height:1.5}.component{overflow-wrap:anywhere;display:block;box-sizing:border-box;width:100%;margin:12px 0;border:1px solid #999;font:inherit;text-align:left}a.component{text-decoration:none}a.component:hover{text-decoration:underline}a.component:focus-visible{outline:3px solid #1849a5}"
    preview_css = ".component-property-node{display:block;box-sizing:border-box;width:100%;margin:12px 0;padding:16px;border:1px solid #999;border-radius:0;background:#fff;color:#222;font:inherit;text-align:left}.component-slot{margin:8px 0 0 12px}.component-slot .component-property-node{width:auto;margin:0}.component-property-link{text-decoration:none}.component-property-link:hover{text-decoration:underline}.component-property-link:focus-visible{outline:3px solid #1849a5}"
    has_property_previews = any(design["components"][item["component"]].get("properties")
                                for screen in design["screens"] for item in screen["elements"] if item["kind"] == "component")
    extra_styles = ([preview_css] if has_property_previews else [])
    style = "\n".join(css + [base] + extra_styles + ([components_css(design)] if styled else [".component{padding:16px;background:#fff;color:#222;border-radius:0}"]))
    return "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><link rel=\"icon\" href=\"data:,\"><title>디자인 미리보기</title><style>" + style + "</style></head><body><h1>" + ("스타일 시안" if styled else "와이어프레임") + "</h1><main>" + "".join(pages) + "</main></body></html>\n", "\n".join(css) + "\n"


def render_svg(design, screen, styled):
    esc = html.escape
    max_svg_bottom = 2390 if "componentFamilies" in design else 630
    body_parts = []
    y = 32
    budget = [0]
    for item in screen["elements"]:
        if item["kind"] == "component" and design["components"][item["component"]].get("properties"):
            tree = component_preview(design, item["component"], item["variant"], item["text"],
                                     item.get("property_values"), budget)
            component_markup, y = _render_component_svg(design, tree, y, styled, max_svg_bottom=max_svg_bottom)
            body_parts.extend(component_markup)
            continue
        styles = {}
        if styled and item["kind"] == "component":
            styles = design["components"][item["component"]]["variants"][item["variant"]]
        def get(prop, fallback):
            return design["tokens"][styles[prop]]["value"] if prop in styles else fallback
        def dimension(prop, fallback):
            return dimension_px(get(prop, fallback))
        padding = dimension("padding", "16px") if item["kind"] == "component" else 0
        padding_x = padding_y = padding
        for prop in styles:
            if prop == "padding": padding_x = padding_y = dimension(prop, "16px")
            elif prop == "padding-inline": padding_x = dimension(prop, "16px")
            elif prop == "padding-block": padding_y = dimension(prop, "16px")
        radius = dimension("border-radius", "0px")
        size = dimension("font-size", "22px" if item["kind"] == "heading" else "16px")
        font = get("font-family", "Inter")
        if size <= 0 or size > 96 or max(padding_x, padding_y) > 100 or radius > 180:
            raise ValueError(f"SVG style out of bounds: {screen['id']}")
        width = 312 - padding_x * 2
        if width < size:
            raise ValueError(f"SVG content too narrow: {screen['id']}")
        lines = textwrap.wrap(item["text"], width=max(1, int(width / size)), break_long_words=True) or [""]
        line_height = size * 1.5
        height = max(44, line_height * len(lines) + padding_y * 2)
        if y + height > max_svg_bottom:
            raise ValueError(f"screen exceeds SVG bounds: {screen['id']}")
        color = get("color", "#20242a")
        if item["kind"] == "component":
            fill, border = get("background", "#ffffff"), get("border-color", "#999999")
            body_parts.append(f'<rect x="24" y="{y:g}" width="312" height="{height:g}" rx="{radius:g}" fill="{esc(str(fill), quote=True)}" stroke="{esc(str(border), quote=True)}"/>')
        for i, line in enumerate(lines):
            body_parts.append(f'<text x="{24 + padding_x:g}" y="{y + padding_y + size + i * line_height:g}" fill="{esc(str(color), quote=True)}" font-family="{esc(str(font), quote=True)}" font-size="{size:g}">{esc(line)}</text>')
        y += height + 8
    svg_height = max(640, math.ceil(y + 10)) if "componentFamilies" in design else 640
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="{svg_height:g}" viewBox="0 0 360 {svg_height:g}" role="img">',
        f'<rect width="360" height="{svg_height:g}" fill="#ffffff"/>',
    ] + body_parts
    return "".join(parts) + "</svg>\n"


def _render_component_svg(design, root, y, styled, *, max_svg_bottom=630):
    esc = html.escape
    parts = []

    def style_value(node, prop, fallback):
        token = node["styles"].get(prop) if styled else None
        return design["tokens"][token]["value"] if token else fallback

    def dimensions(node):
        styles = node["styles"] if styled else {}
        padding = dimension_px(style_value(node, "padding", "16px"))
        px = py = padding
        for prop in styles:
            if prop == "padding": px = py = dimension_px(style_value(node, prop, "16px"))
            elif prop == "padding-inline": px = dimension_px(style_value(node, prop, "16px"))
            elif prop == "padding-block": py = dimension_px(style_value(node, prop, "16px"))
        size = dimension_px(style_value(node, "font-size", "16px"))
        radius = dimension_px(style_value(node, "border-radius", "0px"))
        if size <= 0 or size > 96 or max(px, py) > 100 or radius > 180:
            raise ValueError("SVG style out of bounds: component preview")
        return px, py, size, radius

    def measure(node, width):
        px, py, size, _radius = dimensions(node)
        content_width = width - 2 * px
        if content_width < size:
            raise ValueError("SVG component content too narrow")
        lines = textwrap.wrap(node["label"] or "", width=max(1, int(content_width / size)), break_long_words=True) if node["label"] is not None else []
        for slot_item in node.get("text_slots", []):
            lines.extend(textwrap.wrap(slot_item["text"] or "", width=max(1, int(content_width / size)), break_long_words=True) or [""])
        own_height = size * 1.5 * len(lines)
        child_heights = []
        for child in node["children"]:
            child_heights.append(measure(child["node"], width - 16))
        gap = 8 if child_heights and lines else 0
        return max(44, py * 2 + own_height + gap + sum(child_heights) + max(0, len(child_heights) - 1) * 8)

    def draw(node, x, top, width):
        px, py, size, radius = dimensions(node)
        height = measure(node, width)
        fill = style_value(node, "background", "#ffffff")
        border = style_value(node, "border-color", "#999999")
        color = style_value(node, "color", "#20242a")
        font = style_value(node, "font-family", "Inter")
        parts.append(f'<rect x="{x:g}" y="{top:g}" width="{width:g}" height="{height:g}" rx="{radius:g}" fill="{esc(str(fill), quote=True)}" stroke="{esc(str(border), quote=True)}"/>')
        cursor = top + py
        has_own_copy = node["label"] is not None or bool(node.get("text_slots"))
        if node["label"] is not None:
            lines = textwrap.wrap(node["label"], width=max(1, int((width - 2 * px) / size)), break_long_words=True) or [""]
            for line in lines:
                parts.append(f'<text x="{x + px:g}" y="{cursor + size:g}" fill="{esc(str(color), quote=True)}" font-family="{esc(str(font), quote=True)}" font-size="{size:g}">{esc(line)}</text>')
                cursor += size * 1.5
        for slot_item in node.get("text_slots", []):
            lines = textwrap.wrap(slot_item["text"] or "", width=max(1, int((width - 2 * px) / size)), break_long_words=True) or [""]
            for line in lines:
                parts.append(f'<text x="{x + px:g}" y="{cursor + size:g}" fill="{esc(str(color), quote=True)}" font-family="{esc(str(font), quote=True)}" font-size="{size:g}">{esc(line)}</text>')
                cursor += size * 1.5
        if node["children"] and has_own_copy:
            cursor += 8
        child_width = width - 16
        child_x = x + 8
        for index, child in enumerate(node["children"]):
            if index:
                cursor += 8
            child_height = draw(child["node"], child_x, cursor, child_width)
            cursor += child_height
        return height

    width, x = 312, 24
    height = measure(root, width)
    if y + height > max_svg_bottom:
        raise ValueError("screen exceeds SVG bounds")
    draw(root, x, y, width)
    return parts, y + height + 8


def compile_graph_component_families(
    source,
    *,
    owner_key="nf01.component-families",
    workbench_name="NF-01 · Component families workbench",
    position=None,
):
    """Compile a design or canonical graph with componentFamilies into a SemanticFamilyContract."""
    if not isinstance(source, dict):
        raise ValueError("source must be a design or graph object")
    if not isinstance(owner_key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]{0,119}", owner_key):
        raise ValueError("owner_key must be a bounded identifier")
    if not isinstance(workbench_name, str) or not workbench_name.strip() or len(workbench_name) > 120:
        raise ValueError("workbench_name must be bounded text")
    reject_secret_like_text(workbench_name, "workbench_name")
    pos = {"x": 1680, "y": 0} if position is None else dict(position)
    if (set(pos) != {"x", "y"}
            or any(not isinstance(pos[k], (int, float)) or isinstance(pos[k], bool) or not math.isfinite(pos[k]) for k in ("x", "y"))):
        raise ValueError("position must be finite {x, y}")

    if "nodes" in source and "edges" in source and "screens" not in source:
        nested_design = source.get("component_families_design") or source.get("design_system", {}).get("family_design")
        if isinstance(nested_design, dict):
            design_input = copy.deepcopy(nested_design)
        else:
            raw_families = source.get("componentFamilies") or source.get("design_system", {}).get("componentFamilies")
            if not raw_families:
                raise ValueError("graph requires componentFamilies declaration")
            design_input = _graph_to_family_design(source, raw_families)
    else:
        design_input = copy.deepcopy(source)

    if "componentFamilies" not in design_input:
        raise ValueError("componentFamilies declaration required")
    first_token = next(iter(design_input.get("tokens", {}).values()), None)
    if isinstance(first_token, dict) and "css_name" in first_token and "value" in first_token:
        validate(design_input)
        compiled = copy.deepcopy(design_input)
        if "family_preview" not in compiled or "status" not in compiled:
            norm_fams, st, prev = _compile_component_families(
                compiled["componentFamilies"], compiled["components"], compiled["screens"]
            )
            compiled["componentFamilies"] = norm_fams
            compiled["status"] = st
            compiled["family_preview"] = prev
    else:
        compiled = compile_design(design_input)

    if compiled.get("status") == "unmapped":
        raise ValueError("All declared componentFamilies must map to concrete components before native provisioning")

    tokens = compiled["tokens"]
    components = compiled["components"]
    families = compiled["componentFamilies"]
    comp_to_family = {item["component"]: item for item in families}
    comp_to_set_id = {item["component"]: f"{owner_key}/set:{item['id']}" for item in families}

    def variant_key_for(comp_name, variant_name):
        fid = comp_to_family[comp_name]["id"]
        return f"{owner_key}/variant:{fid}/{variant_name}"

    def resolve_style(styles_map):
        out = {
            "background": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0},
            "color": {"r": 0.1255, "g": 0.1412, "b": 0.1647, "a": 1.0},
            "borderColor": {"r": 0.7804, "g": 0.8039, "b": 0.8314, "a": 1.0},
            "paddingTop": 8.0,
            "paddingRight": 12.0,
            "paddingBottom": 8.0,
            "paddingLeft": 12.0,
            "itemSpacing": 8.0,
            "cornerRadius": 0.0,
            "fontFamily": "Inter",
            "fontSize": 14.0,
        }
        for prop, token_path in styles_map.items():
            tok = tokens[token_path]
            if prop == "background":
                out["background"] = variable_value(tok)[1]
            elif prop == "color":
                out["color"] = variable_value(tok)[1]
            elif prop == "border-color":
                out["borderColor"] = variable_value(tok)[1]
            elif prop == "padding":
                px = dimension_px(tok["value"])
                out["paddingTop"] = out["paddingRight"] = out["paddingBottom"] = out["paddingLeft"] = px
            elif prop == "padding-inline":
                px = dimension_px(tok["value"])
                out["paddingLeft"] = out["paddingRight"] = px
            elif prop == "padding-block":
                px = dimension_px(tok["value"])
                out["paddingTop"] = out["paddingBottom"] = px
            elif prop == "gap":
                out["itemSpacing"] = dimension_px(tok["value"])
            elif prop == "border-radius":
                out["cornerRadius"] = dimension_px(tok["value"])
            elif prop == "font-family":
                out["fontFamily"] = tok["value"]
            elif prop == "font-size":
                out["fontSize"] = dimension_px(tok["value"])
        return out

    deps = {item["component"]: set() for item in families}
    for item in families:
        cname = item["component"]
        for prop in components[cname].get("properties", {}).values():
            if prop["type"] == "INSTANCE_SWAP":
                for ac in prop.get("allowed_components", [prop["default_value"]["component"]]):
                    if ac not in comp_to_family:
                        raise ValueError(f"Swap target {ac} must be a declared component family for workbench provisioning")
                    deps[cname].add(ac)

    ordered_families = []
    visited = set()
    def order_visit(cname):
        if cname in visited:
            return
        visited.add(cname)
        for dep in deps[cname]:
            order_visit(dep)
        ordered_families.append(comp_to_family[cname])
    for item in families:
        order_visit(item["component"])

    default_font_family = "Inter"
    for tok in tokens.values():
        if tok.get("type") == "fontFamily":
            default_font_family = tok["value"]
            break

    component_sets = []
    for item in ordered_families:
        fid = item["id"]
        cname = item["component"]
        comp = components[cname]
        spec = CANONICAL_COMPONENT_FAMILIES[fid]
        axis_for_val = {
            val: axis_name
            for axis_name, vals in item["axes"].items()
            for val in vals
        }
        variants_out = []
        primary_label_default = CANONICAL_COMPONENT_FAMILIES[fid]["name"]
        for pid, cprop in comp.get("properties", {}).items():
            if cprop["type"] == "TEXT" and cprop["target"] == "label":
                primary_label_default = cprop["default_value"]
                break
        for vname, vstyles in comp["variants"].items():
            axis_name = axis_for_val[vname]
            variants_out.append({
                "key": variant_key_for(cname, vname),
                "variant": vname,
                "props": {axis_name: vname},
                "style": resolve_style(vstyles),
                "defaultLabel": primary_label_default,
            })
        props_out = []
        for pid, cprop in comp.get("properties", {}).items():
            p_entry = {
                "id": pid,
                "name": cprop.get("name", pid),
                "type": cprop["type"],
                "targetKey": cprop["target"],
            }
            if cprop["type"] in ("TEXT", "BOOLEAN"):
                p_entry["defaultValue"] = cprop["default_value"]
            else:
                def_ref = cprop["default_value"]
                allowed_comps = cprop.get("allowed_components", [def_ref["component"]])
                p_entry["allowedSetIds"] = [comp_to_set_id[ac] for ac in allowed_comps]
                p_entry["defaultValue"] = {
                    "setId": comp_to_set_id[def_ref["component"]],
                    "variantKey": variant_key_for(def_ref["component"], def_ref["variant"]),
                }
                p_entry["preferredValues"] = [
                    {
                        "setId": comp_to_set_id[pref["component"]],
                        "variantKey": variant_key_for(pref["component"], pref["variant"]),
                    }
                    for pref in cprop.get("preferred_values", [def_ref])
                ]
            props_out.append(p_entry)
        swap_set_ids = [comp_to_set_id[sc] for sc in comp.get("swap_targets", []) if sc in comp_to_set_id]
        component_sets.append({
            "id": comp_to_set_id[cname],
            "family": fid,
            "component": cname,
            "name": spec["name"],
            "layout": comp.get("layout", spec["layout"]),
            "axes": copy.deepcopy(item["axes"]),
            "swapTargets": swap_set_ids,
            "variants": variants_out,
            "properties": props_out,
        })

    instances_out = []
    for screen in compiled["screens"]:
        for idx, element in enumerate(screen["elements"]):
            if element["kind"] != "component" or element["component"] not in comp_to_family:
                continue
            cname = element["component"]
            comp_props = components[cname].get("properties", {})
            el_id = element.get("id", f"{screen['id']}-el-{idx}")
            prop_vals = {}
            for pid, raw_val in (element.get("property_values") or {}).items():
                cprop = comp_props[pid]
                if cprop["type"] in ("TEXT", "BOOLEAN"):
                    prop_vals[pid] = raw_val
                else:
                    prop_vals[pid] = {
                        "setId": comp_to_set_id[raw_val["component"]],
                        "variantKey": variant_key_for(raw_val["component"], raw_val["variant"]),
                    }
            inst_entry = {
                "key": f"{owner_key}/instance:{el_id}",
                "elementId": el_id,
                "setId": comp_to_set_id[cname],
                "variantKey": variant_key_for(cname, element["variant"]),
                "name": element["text"][:80] or cname,
                "text": element["text"],
                "propertyValues": prop_vals,
            }
            if "dom_source" in element:
                inst_entry["domSource"] = copy.deepcopy(element["dom_source"])
            instances_out.append(inst_entry)

    return {
        "schema": "figma-flow-semantic-family-contract-v1",
        "version": 1,
        "mode": "additive-family-workbench",
        "ownerKey": owner_key,
        "workbench": {
            "frameKey": f"{owner_key}/workbench",
            "libraryKey": f"{owner_key}/library",
            "instancesFrameKey": f"{owner_key}/instances",
            "name": workbench_name,
            "position": pos,
            "font": {"family": default_font_family, "style": "Regular"},
        },
        "componentSets": component_sets,
        "instances": instances_out,
    }


def _graph_to_family_design(graph, raw_families):
    """Synthesize a validated design dict from a canonical graph carrying componentFamilies."""
    tokens = {
        "color": {
            "ink": {"$type": "color", "$value": "#1f242b"},
            "muted": {"$type": "color", "$value": "#59616b"},
            "surface": {"$type": "color", "$value": "#ffffff"},
            "border": {"$type": "color", "$value": "#c7cdd4"},
            "accent": {"$type": "color", "$value": "#1849a5"},
            "danger": {"$type": "color", "$value": "#b42318"},
        },
        "space": {
            "xs": {"$type": "dimension", "$value": "4px"},
            "sm": {"$type": "dimension", "$value": "8px"},
            "md": {"$type": "dimension", "$value": "12px"},
        },
        "radius": {"sm": {"$type": "dimension", "$value": "4px"}},
        "font": {
            "body": {"$type": "fontFamily", "$value": "Inter"},
            "size": {"$type": "dimension", "$value": "14px"},
        },
    }
    for role in graph.get("design_foundations", {}).get("roles", []):
        if role.get("kind") == "typography" and (role.get("native") or {}).get("type") == "STRING":
            val = role.get("value", "")
            if isinstance(val, str) and FONT.fullmatch(val):
                tokens["font"]["body"]["$value"] = val
                break
    components = {}
    for entry in raw_families:
        if not isinstance(entry, dict) or "id" not in entry or "axes" not in entry:
            raise ValueError("invalid componentFamilies entry in graph")
        cname = entry.get("component", entry["id"])
        variants = {}
        for vals in entry["axes"].values():
            if not isinstance(vals, list):
                raise ValueError("invalid axis values in graph componentFamilies")
            for vname in vals:
                ink_tok = "color.danger" if vname == "error" else ("color.muted" if vname in ("disabled", "muted") else ("color.accent" if vname in ("checked", "selected") else "color.ink"))
                border_tok = "color.danger" if vname == "error" else ("color.accent" if vname in ("focus", "checked", "selected") else "color.border")
                variants[vname] = {
                    "color": ink_tok,
                    "background": "color.surface",
                    "border-color": border_tok,
                    "padding": "space.sm",
                    "gap": "space.sm",
                    "border-radius": "radius.sm",
                    "font-family": "font.body",
                    "font-size": "font.size",
                }
        components[cname] = {"variants": variants}
    raw_instances = graph.get("family_instances") or graph.get("design_system", {}).get("family_instances") or []
    elements = []
    if raw_instances:
        for idx, inst in enumerate(raw_instances):
            if not isinstance(inst, dict):
                raise ValueError("invalid family_instances entry")
            el = {
                "id": inst.get("id", f"family-instance-{idx}"),
                "kind": "component",
                "component": inst["component"],
                "variant": inst["variant"],
                "text": inst.get("text", inst["component"]),
            }
            if "property_values" in inst:
                el["property_values"] = copy.deepcopy(inst["property_values"])
            if "dom_source" in inst:
                el["dom_source"] = copy.deepcopy(inst["dom_source"])
            elements.append(el)
    else:
        for entry in raw_families:
            cname = entry.get("component", entry["id"])
            first_v = next(iter(components[cname]["variants"]))
            elements.append({
                "id": f"default-{cname}",
                "kind": "component",
                "component": cname,
                "variant": first_v,
                "text": CANONICAL_COMPONENT_FAMILIES.get(entry["id"], {}).get("name", cname),
            })
    return {
        "version": 1,
        "tokens": tokens,
        "componentFamilies": copy.deepcopy(raw_families),
        "components": components,
        "screens": [{
            "id": "graph-family-workbench",
            "title": "Graph component families",
            "trace": ["NF-01"],
            "elements": elements,
        }],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="new output directory")
    args = parser.parse_args()
    try:
        if not args.input.is_file():
            raise ValueError("input must be a regular file")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        design = compile_design(data)
        styled, css = render(design, True)
        wireframe, _ = render(design, False)
        outputs = {"resolved.json": json.dumps(design, ensure_ascii=False, indent=2) + "\n", "tokens.css": css, "components.css": components_css(design), "styled.html": styled, "wireframe.html": wireframe}
        for screen in design["screens"]:
            outputs[f"{screen['id']}-styled.svg"] = render_svg(design, screen, True)
            outputs[f"{screen['id']}-wireframe.svg"] = render_svg(design, screen, False)
        args.out.mkdir()  # A pre-existing directory is never overwritten.
        for name, content in outputs.items():
            with (args.out / name).open("x", encoding="utf-8") as output:
                output.write(content)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"design-system: {exc}\n")


if __name__ == "__main__":
    main()
