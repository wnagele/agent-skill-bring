#!/usr/bin/env python3
"""Bring Shopping List skill — works with both OpenClaw (CLI) and OpenFang (JSON protocol)."""

import asyncio
import os
import uuid

import aiohttp
from bring_api import Bring, BringItemOperation
from skill_handler import Skill


skill = Skill("bring", "Manage Bring! shopping lists")


def load_config():
    from dotenv import load_dotenv
    load_dotenv()
    email = os.environ.get("BRING_EMAIL")
    password = os.environ.get("BRING_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Missing BRING_EMAIL and/or BRING_PASSWORD. "
            "Set them as environment variables or in a .env file."
        )
    return {"email": email, "password": password}


def _with_client(fn):
    def wrapper(input):
        config = load_config()

        async def run():
            async with aiohttp.ClientSession() as session:
                bring = Bring(session, config["email"], config["password"])
                await bring.login()
                return await fn(input, bring)

        return asyncio.run(run())

    return wrapper


async def _resolve_list_uuid(bring, name):
    if not name:
        raise RuntimeError("List name required")
    lists_response = await bring.load_lists()
    matches = [
        lst for lst in lists_response.lists
        if name.lower() in lst.name.lower()
    ]
    if not matches:
        raise RuntimeError(f'No lists found matching "{name}"')
    if len(matches) > 1:
        names = ", ".join(f'"{m.name}"' for m in matches)
        raise RuntimeError(f'Multiple lists match "{name}": {names}. Be more specific.')
    return matches[0].listUuid


async def _resolve_item(bring, list_uuid, item_name, specification=None):
    response = await bring.get_list(list_uuid)
    all_items = list(response.items.purchase) + list(response.items.recently)
    input_lower = item_name.lower()
    matches = [i for i in all_items if i.itemId.lower() == input_lower]

    if not matches:
        raise RuntimeError(f'Item "{item_name}" not found on list')

    if len(matches) == 1:
        return matches[0].itemId, matches[0].specification, matches[0].uuid

    if specification is not None:
        spec_matches = [
            i for i in matches if i.specification.lower() == specification.lower()
        ]
        if len(spec_matches) == 1:
            return spec_matches[0].itemId, spec_matches[0].specification, spec_matches[0].uuid
        if not spec_matches:
            specs = ", ".join(f'"{m.specification}"' for m in matches)
            raise RuntimeError(
                f'Item "{item_name}" with specification "{specification}" not found. '
                f"Available specifications: {specs}"
            )

    specs = ", ".join(
        f'"{m.specification}"' if m.specification else '""' for m in matches
    )
    raise RuntimeError(
        f'Multiple "{item_name}" items on list. Specify which one with the note argument. '
        f'Use "" for the entry without a note. '
        f"Available: {specs}"
    )


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@skill.tool("lists",
    description="Show all shopping lists",
    params={})
@_with_client
async def lists(input, bring):
    lists_response = await bring.load_lists()
    names = [lst.name for lst in lists_response.lists]
    return ", ".join(names) if names else "No lists found."


@skill.tool("catalog",
    description="List all available catalog items",
    params={})
@_with_client
async def catalog(input, bring):
    locale = bring.user_locale
    url = f"https://web.getbring.com/locale/catalog.{locale}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            catalog_data = await resp.json(content_type=None)
    sections = catalog_data.get("catalog", {}).get("sections", [])
    names = []
    for section in sections:
        for item in section.get("items", []):
            names.append(item.get("name", ""))
    names.sort()
    return "\n".join(f"- {name}" for name in names)


@skill.tool("items",
    description="Show items in a list",
    params={
        "list": {"type": "string", "description": "List name",
                 "required": True, "cli_positional": True},
    })
@_with_client
async def items(input, bring):
    list_uuid = await _resolve_list_uuid(bring, input["list"])
    response = await bring.get_list(list_uuid)

    def format_item(p):
        parts = [p.itemId]
        if p.specification:
            parts[0] += f" ({p.specification})"
        tags = []
        for attr in p.attributes:
            if attr.type == "PURCHASE_CONDITIONS":
                if attr.content.urgent:
                    tags.append("urgent")
                if attr.content.convenient:
                    tags.append("if convenient")
                if attr.content.discounted:
                    tags.append("if discounted")
        if tags:
            parts.append(f"[{', '.join(tags)}]")
        return " ".join(parts)

    lines = []
    purchase = [format_item(p) for p in response.items.purchase]
    recently = [format_item(p) for p in response.items.recently]

    if purchase:
        lines.append("To buy:")
        for item in purchase:
            lines.append(f"  - {item}")
    else:
        lines.append("Nothing to buy.")

    if recently:
        lines.append("Recently purchased:")
        for item in recently:
            lines.append(f"  - {item}")

    return "\n".join(lines)


@skill.tool("add",
    description="Add item to list",
    params={
        "list": {"type": "string", "description": "List name",
                 "required": True, "cli_positional": True},
        "item": {"type": "string", "description": "Item name",
                 "required": True, "cli_positional": True},
        "note": {"type": "string", "description": "Specification (quantity, variety, etc.)",
                 "cli_positional": True},
        "urgent": {"type": "boolean", "description": "Mark as urgent"},
        "convenient": {"type": "boolean", "description": "Mark as buy if convenient"},
        "discounted": {"type": "boolean", "description": "Mark as buy if discounted"},
    })
@_with_client
async def add(input, bring):
    list_uuid = await _resolve_list_uuid(bring, input["list"])
    item_name = input["item"]
    note = input.get("note", "")

    response = await bring.get_list(list_uuid)
    existing = None
    for p in response.items.purchase:
        if p.itemId.lower() == item_name.lower() and p.specification.lower() == note.lower():
            existing = p
            break

    if existing:
        item_uuid = existing.uuid
    else:
        item_uuid = str(uuid.uuid4())
        await bring.batch_update_list(
            list_uuid,
            {"itemId": item_name, "spec": note, "uuid": item_uuid},
            BringItemOperation.ADD,
        )

    if input.get("urgent") or input.get("convenient") or input.get("discounted"):
        await bring.batch_update_list(
            list_uuid,
            {
                "itemId": item_name,
                "spec": note,
                "uuid": item_uuid,
                "operation": "ATTRIBUTE_UPDATE",
                "attribute": {
                    "type": "PURCHASE_CONDITIONS",
                    "content": {
                        "urgent": bool(input.get("urgent")),
                        "convenient": bool(input.get("convenient")),
                        "discounted": bool(input.get("discounted")),
                    },
                },
            },
        )

    if existing:
        return f'Updated "{item_name}" on list'
    return f'Added "{item_name}" to list'


@skill.tool("purchased",
    description="Mark item as purchased",
    params={
        "list": {"type": "string", "description": "List name",
                 "required": True, "cli_positional": True},
        "item": {"type": "string", "description": "Item name",
                 "required": True, "cli_positional": True},
        "note": {"type": "string", "description": "Specification to disambiguate",
                 "cli_positional": True},
    })
@_with_client
async def purchased(input, bring):
    list_uuid = await _resolve_list_uuid(bring, input["list"])
    api_name, item_spec, item_uuid = await _resolve_item(
        bring, list_uuid, input["item"], input.get("note"),
    )
    await bring.batch_update_list(
        list_uuid,
        {"itemId": api_name, "spec": item_spec, "uuid": item_uuid},
        BringItemOperation.COMPLETE,
    )
    return f'Marked "{input["item"]}" as purchased'


@skill.tool("remove",
    description="Permanently remove item from list",
    params={
        "list": {"type": "string", "description": "List name",
                 "required": True, "cli_positional": True},
        "item": {"type": "string", "description": "Item name",
                 "required": True, "cli_positional": True},
        "note": {"type": "string", "description": "Specification to disambiguate",
                 "cli_positional": True},
    })
@_with_client
async def remove(input, bring):
    list_uuid = await _resolve_list_uuid(bring, input["list"])
    api_name, _, item_uuid = await _resolve_item(
        bring, list_uuid, input["item"], input.get("note"),
    )
    await bring.batch_update_list(
        list_uuid,
        {"itemId": api_name, "spec": "", "uuid": item_uuid},
        BringItemOperation.REMOVE,
    )
    return f'Removed "{input["item"]}" from list'


if __name__ == "__main__":
    skill.run()
