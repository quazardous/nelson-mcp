#!/usr/bin/env python3
"""Generate help documentation from modules and tools.

Scans all modules for:
1. help.md files in module directories (manual help)
2. Tool classes with description/help/parameters (auto-generated)

Produces:
    build/help/index.md          — master index
    build/help/<module>.md       — per-module page (manual + auto tools)

Then converts to XHP via md2xhp if available.

Usage:
    python scripts/generate_help.py
    python scripts/generate_help.py --xhp   # also convert to XHP
"""

import argparse
import importlib
import inspect
import os
import sys
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(PROJECT_ROOT, "plugin", "modules")
HELP_DIR = os.path.join(PROJECT_ROOT, "build", "help")


def _discover_modules():
    """Discover all modules with module.yaml."""
    modules = []
    for entry in sorted(os.listdir(MODULES_DIR)):
        yaml_path = os.path.join(MODULES_DIR, entry, "module.yaml")
        if os.path.isfile(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {}
            manifest["_dir"] = entry
            manifest["_path"] = os.path.join(MODULES_DIR, entry)
            modules.append(manifest)
    return modules


def _discover_tools(module_path, module_name):
    """Discover ToolBase subclasses in a module's tools/ directory."""
    tools_dir = os.path.join(module_path, "tools")
    if not os.path.isdir(tools_dir):
        return []

    # Add project root to path for imports
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    tools = []
    package = "plugin.modules.%s.tools" % module_name.replace(".", "_")

    for fn in sorted(os.listdir(tools_dir)):
        if fn.startswith("_") or not fn.endswith(".py"):
            continue
        mod_name = fn[:-3]
        fqn = "%s.%s" % (package, mod_name)
        try:
            mod = importlib.import_module(fqn)
            for attr_name, obj in inspect.getmembers(mod, inspect.isclass):
                if (hasattr(obj, "name") and hasattr(obj, "execute")
                        and getattr(obj, "name", None)
                        and obj.__module__ == fqn):
                    try:
                        tools.append(obj())
                    except Exception:
                        pass
        except Exception:
            pass

    return tools


def _tool_to_markdown(tool):
    """Generate Markdown documentation for a single tool."""
    lines = []
    lines.append("### `%s`" % tool.name)
    lines.append("")

    if tool.description:
        lines.append(tool.description)
        lines.append("")

    if getattr(tool, "help", None):
        lines.append(tool.help)
        lines.append("")

    # Mutation / doc type info
    meta = []
    if tool.detects_mutation():
        meta.append("**Mutation:** yes")
    if tool.doc_types:
        meta.append("**Doc types:** %s" % ", ".join(tool.doc_types))
    if not tool.requires_doc:
        meta.append("**Requires document:** no")
    if meta:
        lines.append(" | ".join(meta))
        lines.append("")

    # Parameters
    schema = tool.parameters or {}
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    if props:
        lines.append("**Parameters:**")
        lines.append("")
        for pname, pschema in props.items():
            if pname == "_document":
                continue
            ptype = pschema.get("type", "")
            pdesc = pschema.get("description", "")
            req = " *(required)*" if pname in required else ""
            enum = pschema.get("enum")
            enum_str = ""
            if enum:
                enum_str = " — values: %s" % ", ".join(
                    "`%s`" % e for e in enum)
            lines.append("- `%s`%s — *%s*%s%s" % (
                pname, req, ptype, enum_str,
                " — %s" % pdesc if pdesc else ""))
        lines.append("")

    return "\n".join(lines)


def _generate_module_help(module, tools):
    """Generate Markdown help for a module."""
    name = module["name"]
    title = module.get("title", name)
    mod_path = module["_path"]
    lines = []

    lines.append("# %s" % title)
    lines.append("")

    # Include manual help.md if present
    help_md = os.path.join(mod_path, "help.md")
    if os.path.isfile(help_md):
        with open(help_md, "r", encoding="utf-8") as f:
            content = f.read().strip()
        # Strip the first heading if it matches the title
        content_lines = content.split("\n")
        if content_lines and content_lines[0].startswith("# "):
            content_lines = content_lines[1:]
        lines.append("\n".join(content_lines).strip())
        lines.append("")

    # Config info
    config = module.get("config", {})
    if config:
        config_keys = [k for k, v in config.items()
                       if isinstance(v, dict) and v.get("widget") != "button"]
        if config_keys:
            lines.append("## Configuration")
            lines.append("")
            for key in config_keys:
                schema = config[key]
                label = schema.get("label", key)
                helper = schema.get("helper", "")
                default = schema.get("default", "")
                lines.append("- **%s** (`%s.%s`)" % (label, name, key))
                if helper:
                    lines.append("  %s" % helper)
                if default and default != "[]":
                    lines.append("  Default: `%s`" % default)
            lines.append("")

    # Tools
    if tools:
        lines.append("## Tools")
        lines.append("")
        for tool in sorted(tools, key=lambda t: t.name):
            lines.append(_tool_to_markdown(tool))

    return "\n".join(lines)


def _generate_index(modules_with_tools):
    """Generate the index.md."""
    lines = []
    lines.append("# Nelson MCP — Help Index")
    lines.append("")
    lines.append("## Modules")
    lines.append("")

    for mod, tools in modules_with_tools:
        name = mod["name"]
        title = mod.get("title", name)
        tool_count = len(tools)
        lines.append("- [%s](%s.md) — %s (%d tools)" % (
            title, name.replace(".", "_"), title, tool_count))

    lines.append("")
    lines.append("## Quick Reference")
    lines.append("")
    lines.append("### All Tools")
    lines.append("")

    all_tools = []
    for mod, tools in modules_with_tools:
        for t in tools:
            all_tools.append((t.name, mod["name"], t.description or ""))
    all_tools.sort()

    for tname, mname, desc in all_tools:
        short_desc = desc[:60] + "..." if len(desc) > 60 else desc
        lines.append("- `%s` — %s" % (tname, short_desc))

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate help documentation from modules and tools")
    parser.add_argument("--xhp", action="store_true",
                        help="Also convert to XHP format")
    args = parser.parse_args()

    os.makedirs(HELP_DIR, exist_ok=True)

    print("Scanning modules...")
    modules = _discover_modules()

    modules_with_tools = []

    for mod in modules:
        name = mod["name"]
        mod_dir = mod["_dir"]
        mod_path = mod["_path"]

        tools = _discover_tools(mod_path, name)

        # Skip modules with no help.md and no tools
        help_md = os.path.join(mod_path, "help.md")
        if not tools and not os.path.isfile(help_md):
            continue

        # Generate module help page
        md_content = _generate_module_help(mod, tools)
        out_name = name.replace(".", "_") + ".md"
        out_path = os.path.join(HELP_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        modules_with_tools.append((mod, tools))
        print("  %s — %d tools" % (name, len(tools)))

    # Generate index
    index_content = _generate_index(modules_with_tools)
    index_path = os.path.join(HELP_DIR, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_content)

    total_tools = sum(len(t) for _, t in modules_with_tools)
    print("Generated %d help pages (%d tools) in %s" % (
        len(modules_with_tools) + 1, total_tools, HELP_DIR))

    # Convert to XHP if requested
    if args.xhp:
        md2xhp_path = os.path.join(PROJECT_ROOT, "tools", "md2xhp", "md2xhp.py")
        if os.path.isfile(md2xhp_path):
            sys.path.insert(0, os.path.dirname(md2xhp_path))
            from md2xhp import convert_dir
            xhp_dir = os.path.join(HELP_DIR, "xhp")
            print("Converting to XHP...")
            convert_dir(HELP_DIR, xhp_dir)
        else:
            print("WARNING: md2xhp.py not found, skipping XHP conversion")


if __name__ == "__main__":
    main()
