# Translating

> **You don't need to do any of this yourself.** If you'd like the integration translated into your language, just [open an issue][issues] asking for it — Claude can do the translation. The notes below are for maintainers (and anyone who'd rather submit a PR directly).

[issues]: https://github.com/Sese-Schneider/ha-cover-time-based/issues/new

Cover Time Based has strings in two places, each with its own file layout. Both surfaces need updating when you add a new language or a new translatable string.

| Surface | Files | Used for |
|---|---|---|
| Home Assistant backend | [`strings.json`](custom_components/cover_time_based/strings.json) and [`translations/<lang>.json`](custom_components/cover_time_based/translations/) | Config-flow titles and fields, Repairs issues, service descriptions — anything Home Assistant's own UI renders for us. |
| Lovelace configuration card | [`frontend/translations.js`](custom_components/cover_time_based/frontend/translations.js) — the `EN` object at the top, and the `TRANSLATIONS = { en: EN, pt: {...}, pl: {...} }` block below it | Every string the card itself draws. |

Currently supported languages: English (`en`), Portuguese (`pt`), Polish (`pl`).

## Adding a new language

Say you want to add German (`de`).

### Backend

1. Copy `custom_components/cover_time_based/translations/en.json` to `custom_components/cover_time_based/translations/de.json`.
2. Translate every value in `de.json`. Keep the keys exactly the same — Home Assistant looks them up by name.

Don't touch `strings.json` — it stays in English and is the developer source of truth.

### Card

In [`custom_components/cover_time_based/frontend/translations.js`](custom_components/cover_time_based/frontend/translations.js):

1. Find the `TRANSLATIONS` object:

   ```js
   const TRANSLATIONS = {
     en: EN,
     pt: { ... },
     pl: { ... },
   };
   ```

2. Add a `de:` entry mirroring the existing `pt:` and `pl:` blocks. Use the `EN` object above it as the master list of keys: copy every key across and translate its value.

The card falls back to English for any key you miss, so a partial translation will work — but the [audit below](#verifying-translations-are-in-sync) will flag what's missing.

The card resolves a locale by trying the exact code first, then its base language, then English — so a `pt-BR` user reads the `pt` catalogue, and adding `de` also covers `de-AT` and `de-CH`. Add a region-specific key (`pt-BR`) only when that variant needs wording of its own.

The `language_request.*` keys are deliberately **English-only**. They are the "your language isn't translated yet" banner, which by construction is only ever shown to users whose language has no catalogue — a translated copy would be unreachable.

## Adding a new translatable string

When you add a new feature that introduces a new user-facing string:

### Backend

1. Add the key + English value to [`strings.json`](custom_components/cover_time_based/strings.json), under the appropriate top-level section (`config`, `issues`, or `services`).
2. Mirror the same addition into [`translations/en.json`](custom_components/cover_time_based/translations/en.json). The two files have the same shape; `strings.json` is what ships, `translations/en.json` is what Home Assistant actually reads.
3. Add the same key with a translated value to **every other** `translations/<lang>.json` file (`pt.json`, `pl.json`, …).

### Card

1. Add the key + English value to the `EN` object at the top of `translations.js`.
2. Add the same key with a translated value to **every other** language block inside the `TRANSLATIONS` object (`pt`, `pl`, …).
3. Render the string with `this._t("your.key")`. It reads `hass.language` and falls back to English if a key or language is missing.

For substitutions, use `{name}` placeholders and pass replacements as the second argument:

```js
this._t("hints.movement", { seconds: 3 });
// EN: "Click after about {seconds} seconds."
```

## Verifying translations are in sync

Run this from the repo root. It lists missing and extra keys for every non-English language across both surfaces:

```bash
python - <<'PY'
import json, re
from pathlib import Path
base = Path("custom_components/cover_time_based")

def all_keys(d, prefix=""):
    out = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict): out += all_keys(v, full)
        else: out.append(full)
    return set(out)

en = json.loads((base / "translations/en.json").read_text())
en_keys = all_keys(en)
for path in sorted((base / "translations").glob("*.json")):
    if path.stem == "en": continue
    other = all_keys(json.loads(path.read_text()))
    print(f"backend {path.stem}: missing={sorted(en_keys - other) or 'none'}  extra={sorted(other - en_keys) or 'none'}")

card = (base / "frontend/translations.js").read_text()
def block(text, start):
    m = re.search(start, text)
    if not m: return ""
    s, depth = m.end() - 1, 0
    for i in range(s, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0: return text[s:i+1]
    return ""
def keys_of(t): return set(re.findall(r'"([^"]+)":\s*"', t))

en_card = keys_of(block(card, r"const EN\s*=\s*\{"))
trans   = block(card, r"const TRANSLATIONS\s*=\s*\{")
# The translation-request banner is English-only by design — see above.
IGNORE = {k for k in en_card if k.startswith("language_request.")}
for lang in re.findall(r"^\s{2}(\w+):\s*\{", trans, re.M):
    if lang == "en": continue
    other = keys_of(block(trans, rf"{lang}:\s*\{{"))
    missing = sorted((en_card - IGNORE) - other)
    print(f"card    {lang}: missing={missing or 'none'}  extra={sorted(other - en_card) or 'none'}")
PY
```

Both surfaces should report `missing=none  extra=none` for every language.
