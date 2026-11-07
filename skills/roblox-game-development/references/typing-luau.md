# Typed Luau: getting to zero `luau-lsp` errors without lying to the checker

Written after taking a 72-file game from **4,815 blocking diagnostics to 0** with the pinned
`luau-lsp` (1.70.1) and Roblox `globalTypes.d.luau`. Everything below was reproduced on that
toolchain. Two sections matter most: what Luau actually does with table types, and what a "zero"
claim is allowed to mean.

## Part 1 - table types: sealed, unsealed, and optional reads

This is the part most agents get wrong, including the first version of this file. Verify before
believing; these four cases were run through the real analyzer.

```lua
--!strict
-- 1. An ANNOTATED local is sealed: it cannot grow new fields.
local a: { x: number } = { x = 1 }
a.y = 2            --> TypeError: Cannot add property 'y' to table '{ x: number }'

-- 2. An UNANNOTATED literal is unsealed and grows freely.
local g = {}
g.one = 1          --> ok
g.two = 2          --> ok

-- 3. A literal widens into an annotated parameter, extra fields included.
local function f(p: { x: number }) end
f({ x = 1, extra = true })   --> ok

-- 4. A literal widens into an annotated dictionary index too.
local budget: { [string]: { t: number, n: number } } = {}
budget["k"] = { n = 0, t = 1 }   --> ok
```

The practical rule:

- **Table literals are unsealed by default**; they grow until something constrains them.
- **A type annotation seals the variable it annotates.** Extra fields are then an error, which is the
  point of the annotation - keep it and stop adding fields.
- **Widening into an annotated destination is allowed**, so `{x = 1, extra = true}` is fine where
  `{x: number}` is expected.

So "remove the annotation to silence diagnostics" is bad advice: the annotation is the contract, and
the diagnostic says a field does not belong. Prefer an explicit record type
(`type Budget = { t: number, n: number }`) when the shape is reused, and plain inference for a scratch
table you only grow locally. A dictionary type (`{ [K]: V }`) is the right tool when keys are data; a
record type when fields are named and fixed.

### The optional-read trap that this file originally misdiagnosed

A dictionary read is not automatically optional, but a dictionary keyed by an **instance type** is:

```lua
--!strict
local budget: { [Player]: { t: number, n: number } } = {}

local function apply(player: Player): boolean
    local b = budget[player]          -- type: { n: number, t: number }?
    if not b then
        b = { t = os.clock(), n = 0 }
        budget[player] = b            --> TypeError: Expected '{ n: number, t: number }',
                                      --             got '{ n: number, t: number }?'
    end
    return true
end
```

Assigning a fresh table into `b` does **not** change `b`'s type: the local was inferred as optional
and keeps that type for the rest of the scope. Writing it back into a non-optional slot then fails.
Build the value in a fresh local (or annotate the assignment) instead:

```lua
local fresh: { t: number, n: number } = { t = os.clock(), n = 0 }
budget[player] = fresh
b = fresh
```

Same family as the `nil`-reassignment trap below: a *narrowing* issue, not a sealed-table issue. If a
diagnostic mentions an optional type, find where the optional originated before touching annotations.

## Part 2 - what "zero errors" is allowed to mean

Never decide a typecheck passed by counting a word in the output. `grep -c Error` is wrong three ways:
`0 errors` contains the word, a crashed analyzer prints nothing at all, and lint findings share the
stream. RobloxForge already implements the correct contract in `check.py`; use it.

```bash
rbforge check .                # offline gate: stylua, selene, luau-lsp, structure
rbforge check . --scope static # just the format/lint/typecheck rung
```

The contract, and the only thing to report:

| Result | Meaning |
|---|---|
| `pass` | analyzer exited 0 with no blocking diagnostics |
| `fail` | `TypeError` / `SyntaxError` present (exit 1 is the documented "findings" status) |
| `fail` | analyzer exited with anything other than 0/1 (crash, missing binary, bad flag) |
| `fail` | non-zero exit with **no** readable diagnostics - never a pass |
| `skip` | definitions or luau-lsp unavailable - this is not a pass either |

On failure the detail carries a map instead of a wall of text:

```
4815 type error(s): src/server/Systems/HarrowInterior.luau(...) TypeError: ...
  4815 blocking diagnostic(s) in 9 file(s); analyzer exit 1; definitions ok; sourcemap ok
  worst files: HarrowInterior.luau 2961, HarrowBuilder.luau 776, WorldBuilder.luau 763, ...
  worst kinds: Unknown type used in - operation 834, Expected this to be 416, ...
```

Fix the files at the top of that list first. Three files held 96 % of the diagnostics in the case
study; each had one root cause.

## Part 3 - the root causes, and which are general

**General language rules** (hold in any Luau project - verified on 1.70.1):

- **No default parameter values.** `function f(a: string, b: number? = nil)` is a syntax error
  (`Expected ')' ... got '='`), and one bad signature can cascade into hundreds of bogus diagnostics.
  Spell it `b: number?` and pass `nil` at every call site that omits it.
- **`nil` reassignment kills narrowing.**
  ```lua
  local gun = char:FindFirstChild("Weapon")
  if gun and not gun:IsA("Model") then gun = nil end   -- stays Instance? forever
  ```
  Keep the raw instance and a narrowed view in separate locals.
- **A nullable type is not an optional argument.** `material: Enum.Material?` still needs an argument.
- **`tostring(Enum.Material.Grass)`** is `"Enum.Material.Grass"`; payloads should send `.Name`.
- **A line that starts with `(`** continues the previous expression: `local x = 1` then
  `(tbl).field()` is "Ambiguous syntax: this looks like an argument list".

**Case study, not a rule** (true in this project - check before assuming it elsewhere):

- *Untyped parameters produce caller-side type errors.* The mechanism is general: an unannotated
  parameter is a generic, Luau unifies it across call sites, and failures surface at the callers as
  `Expected this to be 'Player', but got '{- Character: ...}'`. What is case-specific is the audit
  fix - sweeping one module's public functions removed dozens at once only because they were
  unannotated in the first place.
- *Procedural builders cannot be strict.* Three config-driven geometry files produced 4,500
  diagnostics because every field of a part table was inferred from data. That does **not** license
  `--!nonstrict` as a default - see the escape-hatch policy below.
- *`DataStore:UpdateAsync` rejects a structural twin.* The analyzer reported
  `Expected this to be exactly '{...}'` twice in one message for two textually identical types. The
  fix that keeps validation intact is a typed adapter at the boundary (a function taking your profile
  type and returning what the store expects), not `any` on the store handle. `any` is acceptable only
  when an adapter would itself be a lie about the runtime shape, and then it needs a comment naming
  the invariant it relies on.

## Part 4 - escape hatches have a policy

`--!nonstrict` and `any` are allowed, narrowly, under these conditions:

1. Prefer, in order: explicit types for config structures; validation at untrusted boundaries (remote
   payloads, DataStore reads, attributes); typed intermediate variables; a narrow cast where the
   analyzer cannot express a proven invariant.
2. A module may be `--!nonstrict` only with concrete evidence in the header comment: what makes full
   typing impractical, and which module *owns* the logic strict mode would have protected. "It
   reported too many errors" is not evidence - that is the thing being fixed.
3. Every `any` in a signature or a cast gets one line saying what it stands for and who guarantees it.
4. The escape hatch does not remove tests: behaviour stays covered by the project's suites, and a
   strict-mode gap is not an excuse to skip a playtest.

## Part 5 - verify, then verify the verification

1. `stylua src/` first; formatting churn hides real diagnostics.
2. `rbforge check . --scope static` and read the summary, not the tail.
3. Re-run after each batch. Annotating one function can surface callers that previously inferred their
   way out of trouble - the count going up after a fix is normal and is the checker telling the truth.
4. Claim zero only from a `pass` on the full tree, and state which rungs were skipped.
5. A clean static pass proves types and formatting. It proves nothing about multiplayer correctness,
   network ownership, or frame time - those need a played session and, for performance, a measurement.
