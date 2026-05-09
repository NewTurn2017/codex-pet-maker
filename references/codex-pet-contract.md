# Codex Pet Contract (immutable)

These values are dictated by the Codex desktop app. Do not change them.

## Atlas

| Property | Value |
|---|---|
| Format | PNG (working) → WebP (final) |
| Dimensions | exactly **1536 × 1872** pixels |
| Color | RGBA, transparent-capable |
| Grid | **8 columns × 9 rows** |
| Cell | exactly **192 × 208** pixels |
| Background | fully transparent |
| Unused cells | fully transparent (alpha == 0) |
| Forbidden | labels, gutters, borders, drawn grid lines, shadows outside cells, extra frames |

## WebP encoding

```python
image.convert("RGBA").save(target, format="WEBP", lossless=True, quality=100, method=6)
```

## `pet.json` (exact key set, no extras)

```json
{
  "id": "pet-name",
  "displayName": "Pet Name",
  "description": "One short sentence.",
  "spritesheetPath": "spritesheet.webp"
}
```

## ID slug

```python
def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")
```

## Output package location

```
${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/
├── pet.json
└── spritesheet.webp
```
