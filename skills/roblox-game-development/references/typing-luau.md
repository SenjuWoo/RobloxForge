# Getting a Luau project to zero `luau-lsp` errors

Field notes from taking a 72-file game from **4,815 type errors to 0** without rewriting it. The
errors were not 4,815 separate mistakes: four root causes produced almost all of them.

## First: read the shape of the failure, not the first error

`rbforge check --scope static` prints the first diagnostics and a count. Before touching code, get the
distribution yourself, because the tail is noise and the head is the bug:

```bash
luau-lsp analyze --platform=roblox \
  --definitions "$LOCALAPPDATA/RobloxForge/types/globalTypes-<ver>.d.luau" \
  --sourcemap sourcemap.json --ignore='artifacts/**' --ignore='backups/**' \
  src tests tools > diagnostics.txt 2>&1
grep -c Error diagnostics.txt
grep Error diagnostics.txt | sed 's/.*Haven\\//' | cut -d'(' -f1 | sort | uniq -c | sort -rn
```

A file with 2,900 errors is not 2,900 problems. In the project above, three procedural builders held
96 % of them and each had one cause.

## Root cause 1: untyped parameters are generic, and generics unify across every call site

The signature `function Manager.TeleportPlayerToPlot(player, plotId)` gives `player` a *generic*
type. Luau then unifies that generic with every argument at every call site, and reports the failures
at the call sites with a message like:

```
TypeError: Expected this to be 'Player', but got '{- Character: {- FindFirstChild: (tp1) -> ...
```

That message does not mean a wrong value was passed. It means the parameter was never given a type.
Fixing the parameter removes dozens of errors at once:

```lua
function Manager.TeleportPlayerToPlot(player: Player, plotId: number?)
```

Sweep the module for every `function X.Y(player, ...)` and annotate. Same for helper `s`, `fx`,
`data`, `target`, `payload` parameters.

## Root cause 2: a `nil` reassignment kills narrowing

```lua
local gunModel = char:FindFirstChild("EquippedWeaponModel")
if gunModel and not gunModel:IsA("Model") then
    gunModel = nil                     -- now the type is Instance?, forever
end
if gunModel then
    local muzzle = gunModel:FindFirstChild("Muzzle", true)   -- still Instance?
end
```

Keep the object and a narrowed view separate:

```lua
local gunInstance = char:FindFirstChild("EquippedWeaponModel")
local gunModel: Model? = nil
if gunInstance and gunInstance:IsA("Model") then
    gunModel = gunInstance
end
```

Same trap for singletons: `local ghostPart: Part? = nil` then `ghostPart = Instance.new("Part")`
inside an `if not ghostPart` block still leaves the field nullable for later property writes. Build
into a fresh local (`local made = Instance.new("Part")`), configure it, then assign.

## Root cause 3: sealed table literals do not widen

```lua
local budget: { [Player]: { t: number, n: number } } = {}
...
budget[player] = { t = now, n = 0 }   -- ERROR: sealed literal cannot be assigned to an unsealed type
```

A table literal has an *exact* (sealed) type; the annotated index type is unsealed. Either drop the
annotation (inference is fine for a small counter table) or build through a variable typed the same
way. Do not add `:: any` casts to chase this - drop the annotation.

## Root cause 4: `--!strict` on procedural geometry is a lie

Config-driven builders - a 200-panel dome, a ship interior, a terrain skirt - assemble tables of
parts from data. Under `--!strict` every `cfg.color`, `cfg.size.X` and dynamic key is an error, and
the honest number is thousands. These modules are `--!nonstrict` **with the reason written in the
header comment**, and the logic modules (data, combat, economy) stay `--!strict` where the types
actually protect something.

Write the reason in the file, not just in the commit:

```lua
--!nonstrict
-- Procedural geometry: part tables are built dynamically from config, so strict inference produces
-- thousands of false positives here. Logic-critical modules stay --!strict.
```

## Syntax that does not exist, and reads like a type error

- **No default parameter values.** `function f(a: string, b: number? = nil)` is a *syntax* error
  (`Expected ')' ... got '='`), and it can cascade into 500+ bogus diagnostics in one file. Luau
  optional parameters are spelled `b: number?` and callers must pass `nil` explicitly:
  `f("x", nil)`. A helper with many optional args gets longer call sites, not defaults.
- **A line starting with `(`** continues the previous expression: `local x = 1` then `(hud :: any).y()`
  is "Ambiguous syntax: this looks like an argument list". Assign to a local first, or prefix `;`.
- **`tostring(Enum.Material.Grass)`** is `"Enum.Material.Grass"`; send `.Name` in payloads.

## Boundaries where a cast is honest

- `DataStore:UpdateAsync` rejects a *structural twin* of a table type even when the printed types are
  identical (`Expected this to be exactly '{...}'` twice in one message). Pass the store through an
  `any`-typed local, or the value through `any`, and keep the real validation in your sanitizer.
- `HudBuilder`-style tables that grow after construction lose their concrete field signatures across
  the module boundary. One `local hudAny: any = hud` at the call site beats annotating 40 callbacks.

Both are worth a one-line comment saying why the cast exists, or the next agent will "fix" it back.

## Verification loop

1. `stylua src/` then `luau-lsp analyze` - formatting churn hides real diagnostics otherwise.
2. Re-run the whole distribution after each batch; a fix that drops 40 errors in one file may surface
   10 in another (typed parameters expose call sites that inferred their way out before).
3. Only claim zero when `grep -c Error` is `0` on the **full** tree, not the file you edited.
