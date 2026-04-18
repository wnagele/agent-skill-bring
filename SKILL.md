---
name: bring
description: Manage Bring! shopping lists - view, add, and remove grocery items from shared shopping lists. Use when the user wants to interact with their Bring! shopping list app, add groceries, check what's on the list, or remove items after shopping.
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env:
        - BRING_EMAIL
        - BRING_PASSWORD
    primaryEnv: BRING_PASSWORD
    install:
      - kind: pip
        package: bring-api
      - kind: pip
        package: python-dotenv
      - kind: pip
        package: agent-skill-handler
        source: git+https://github.com/wnagele/agent-skill-handler.git
  openfang:
    requires:
      bins:
        - python3
    install:
      - kind: pip
        package: bring-api
      - kind: pip
        package: python-dotenv
      - kind: pip
        package: agent-skill-handler
        source: git+https://github.com/wnagele/agent-skill-handler.git
    env:
      - name: BRING_EMAIL
        description: Bring! account email address
      - name: BRING_PASSWORD
        description: Bring! account password
        secret: true
---

# Bring Shopping List Integration

Manage Bring! shopping lists — view, add, and remove items.

## Setup

Provide `BRING_EMAIL` and `BRING_PASSWORD` via environment variables or a `.env` file:

```
BRING_EMAIL=you@example.com
BRING_PASSWORD=yourpassword
```

The skill checks environment variables first, then falls back to a `.env` file (searched from the current directory upward).

## Commands

All commands that take `<list>` accept a list name, matched case-insensitively.

### List all shopping lists

```bash
python3 scripts/bring.py lists
```

### List all catalog items

```bash
python3 scripts/bring.py catalog
```

Returns a list of all available item names. Use this to look up the correct item name when unsure what to pass to the `add` command.

### View items on a list

```bash
python3 scripts/bring.py items <list>
```

### Add an item

```bash
python3 scripts/bring.py add <list> <item> [note] [--urgent] [--convenient] [--discounted]
```

`<item>` is the broad category (e.g. "Milk", "Cheese"). Use `[note]` to specify quantity or variety (e.g. "2 liters", "Grated Mozzarella").

Optional flags:
- `--urgent` — mark as urgent
- `--convenient` — mark as "buy if convenient"
- `--discounted` — mark as "buy if discounted"

**Important:** Always run `catalog` first and match the user's request to a catalog item name. Using catalog names ensures items get the correct icon and category in the Bring app. Only use a free-text name if no catalog entry matches.

You can add multiple items with the same base name (e.g. "Cheese" with "Cheddar" and "Cheese" with "Mozzarella") without them overwriting each other.

### Mark an item as purchased

Moves the item to the recently purchased list:

```bash
python3 scripts/bring.py purchased <list> <item> [note]
```

### Remove an item

Permanently removes an item from the list:

```bash
python3 scripts/bring.py remove <list> <item> [note]
```

For `purchased` and `remove`, `[note]` is used to disambiguate when multiple items share the same name. If only one item matches, the note is not needed. If multiple items match (e.g. two "Batteries" entries), the CLI will error and list the available specifications to choose from.

## Examples

| User says | Command |
|---|---|
| "Add milk to the Home list" | `python3 scripts/bring.py add "Home" "Milk"` |
| "Add 2 liters of milk to Groceries" | `python3 scripts/bring.py add "Groceries" "Milk" "2 liters"` |
| "Add grated mozzarella" | `python3 scripts/bring.py add "Groceries" "Cheese" "Grated Mozzarella"` |
| "Add shampoo if it's on sale" | `python3 scripts/bring.py add "Groceries" "Shampoo" --discounted` |
| "We urgently need batteries" | `python3 scripts/bring.py add "Groceries" "Batteries" --urgent` |
| "What's on my shopping list?" | `python3 scripts/bring.py items "Groceries"` |
| "I bought the milk" | `python3 scripts/bring.py purchased "Groceries" "Milk"` |
| "I bought the AA batteries" | `python3 scripts/bring.py purchased "Groceries" "Batteries" "AA"` |
| "Remove milk from the list" | `python3 scripts/bring.py remove "Groceries" "Milk"` |
| "What lists do I have?" | `python3 scripts/bring.py lists` |

## Notes

- The locale is auto-detected from the user's Bring account. Item names are automatically translated to the user's language.
- `purchased` moves items to the "recently purchased" list. `remove` permanently deletes them.
- Multiple items with the same base name but different specifications are supported.
- If `python3` cannot find the required packages (e.g. `ModuleNotFoundError`), check for a `.venv` directory in the skill root and use its interpreter instead (e.g. `.venv/bin/python3`).
