#!/usr/bin/env python3
"""Compile a bounded local design system into CSS and inspectable previews."""
import argparse
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
from figma_bridge import dimension_px, validate_component_properties

NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
ALIAS = re.compile(r"^\{([a-zA-Z0-9_.-]+)\}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
DIMENSION = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]+)?)(?:px|rem)$")
FONT = re.compile(r"^[a-zA-Z][a-zA-Z0-9 -]*$")
PROPERTIES = {"background", "color", "border-color", "padding", "padding-inline", "padding-block", "gap", "border-radius", "font-family", "font-size"}
PROPERTY_TYPES = {"background": "color", "color": "color", "border-color": "color", "padding": "dimension", "padding-inline": "dimension", "padding-block": "dimension", "gap": "dimension", "border-radius": "dimension", "font-family": "fontFamily", "font-size": "dimension"}
PREVIEW_NODE_LIMIT = 512
PREVIEW_DEPTH_LIMIT = 32


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
    components = data.get("components")
    screens = data.get("screens")
    if not isinstance(components, dict) or not components or not isinstance(screens, list) or not screens:
        raise ValueError("components and screens are required")
    classes = set()
    for name, component in components.items():
        if not NAME.fullmatch(name) or not isinstance(component, dict) or set(component) - {"usage", "properties"} != {"variants"} or not isinstance(component.get("variants"), dict) or not component["variants"]:
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
            metadata = {"id", "target_screen", "annotation", "action_id"}
            if element["kind"] == "component":
                metadata.add("property_values")
                name, variant = element.get("component"), element.get("variant")
                if set(element) - metadata != {"kind", "text", "component", "variant"} or name not in components or variant not in components[name]["variants"]:
                    raise ValueError(f"unknown component variant in {screen['id']}")
            elif set(element) - metadata != {"kind", "text"}:
                raise ValueError(f"invalid element in {screen['id']}")
    if "variant_axes" in data:
        attach_declared_axes(components, data["variant_axes"])
    validate_component_properties(components, screens)
    return {"version": 1, "tokens": resolved, "components": components, "screens": screens}


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
    label_visible = True
    slot_visibility = {}
    swaps = []
    for display, prop in properties.items():
        value = overrides.get(display, prop["default_value"])
        if prop["type"] == "BOOLEAN":
            if prop["target"] == "label":
                label_visible = value
            else:
                slot_visibility[prop["target"]] = value
        else:
            swaps.append((prop["target"], value))
    children = []
    for slot, reference in swaps:
        if not slot_visibility.get(slot, True):
            continue
        child_name, child_variant = reference["component"], reference["variant"]
        children.append({"slot": slot, "node": component_preview(
            design, child_name, child_variant, child_name, budget=budget, depth=depth + 1)})
    return {"component": name, "variant": variant, "styles": definition["variants"][variant],
            "label": label if label_visible else None, "children": children}


def _preview_html(node, root=False):
    esc = html.escape
    identity = esc(node["component"] + "--" + node["variant"], quote=True)
    label = f'<span class="component-label">{esc(node["label"])}</span>' if node["label"] is not None else ""
    children = "".join(f'<div class="component-slot" data-slot="{esc(child["slot"], quote=True)}">{_preview_html(child["node"])}</div>' for child in node["children"])
    return f'<div class="component-property-node {identity}"' + (' data-component-root="true"' if root else '') + f'>{label}{children}</div>'


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
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="360" height="640" viewBox="0 0 360 640" role="img">', '<rect width="360" height="640" fill="#ffffff"/>']
    y = 32
    budget = [0]
    for item in screen["elements"]:
        if item["kind"] == "component" and design["components"][item["component"]].get("properties"):
            tree = component_preview(design, item["component"], item["variant"], item["text"],
                                     item.get("property_values"), budget)
            component_markup, y = _render_component_svg(design, tree, y, styled)
            parts.extend(component_markup)
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
        if y + height > 630:
            raise ValueError(f"screen exceeds SVG bounds: {screen['id']}")
        color = get("color", "#20242a")
        if item["kind"] == "component":
            fill, border = get("background", "#ffffff"), get("border-color", "#999999")
            parts.append(f'<rect x="24" y="{y:g}" width="312" height="{height:g}" rx="{radius:g}" fill="{esc(str(fill), quote=True)}" stroke="{esc(str(border), quote=True)}"/>')
        for i, line in enumerate(lines):
            parts.append(f'<text x="{24 + padding_x:g}" y="{y + padding_y + size + i * line_height:g}" fill="{esc(str(color), quote=True)}" font-family="{esc(str(font), quote=True)}" font-size="{size:g}">{esc(line)}</text>')
        y += height + 8
    return "".join(parts) + "</svg>\n"


def _render_component_svg(design, root, y, styled):
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
        if node["label"] is not None:
            lines = textwrap.wrap(node["label"], width=max(1, int((width - 2 * px) / size)), break_long_words=True) or [""]
            for line in lines:
                parts.append(f'<text x="{x + px:g}" y="{cursor + size:g}" fill="{esc(str(color), quote=True)}" font-family="{esc(str(font), quote=True)}" font-size="{size:g}">{esc(line)}</text>')
                cursor += size * 1.5
        if node["children"] and node["label"] is not None:
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
    if y + height > 630:
        raise ValueError("screen exceeds SVG bounds")
    draw(root, x, y, width)
    return parts, y + height + 8


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
