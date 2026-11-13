# Official Plugin API inventory

This is an offline declaration catalog, not an executor or a runtime support claim.
The MIT-licensed official source is pinned in `source.json` by upstream commit,
package version and SHA256. `upstream-package.json` is the original package metadata.
`index.json` is generated from that source using TypeScript 5.9.3 AST and type checker.
All source files and their license are preserved. No network request is made by the CLI.

From the repository root:

```sh
python3 tools/figma_api_inventory.py summary
python3 tools/figma_api_inventory.py search 'createVariable' --limit 10
python3 tools/figma_api_inventory.py search --owner RectangleNode --limit 0
python3 tools/figma_api_inventory.py nodes
python3 tools/figma_api_inventory.py route figma.currentUser --editor figma --permission currentuser
```

Search includes declarations, method overloads, properties, original JSDoc and source
links. `--owner` resolves inherited mixins with the TypeScript type checker, including
utility inheritance such as `Omit`. `nodes` lists concrete node interfaces and aliases,
including the `BaseNode`, `SceneNode` and `NodeType` declarations. Namespace paths are
references to official API objects, never bridge operation names or callable RPCs.

A route returns known blockers for documented editor restrictions, missing manifest
permissions and private/partner APIs. Absence of a blocker still requires reviewing
original documentation for editor, mode, capabilities, document access, version and
other conditions. Extracted restrictions are hints, not a complete policy engine.
Private declarations are included for completeness and explicitly blocked for public
routing. No Figma context is opened, code dispatched, or implementation certified.

Regenerate deterministically using the development-only compiler dependency:

```sh
npm install --prefix library/figma-api --ignore-scripts --package-lock=false
python3 tools/figma_api_inventory.py generate
python3 tools/figma_api_inventory.py verify
FIGMA_API_TYPESCRIPT="$PWD/library/figma-api/node_modules/typescript/lib/typescript.js" python3 -m unittest discover -s tests -p test_figma_api_inventory.py -v
```

An existing exact compiler can be supplied with `--typescript /path/to/typescript.js`.
Offline search and source-hash checks require only Python. The parser-version check
rejects other compiler versions. Tests skip compiler regeneration unless
`FIGMA_API_TYPESCRIPT` is provided; all other catalog/CLI tests remain offline.

Updating the pin is a deliberate maintenance change. Fetch the official declaration,
license and package metadata at one full upstream commit, update every source hash
and version in `source.json`, regenerate, inspect the diff and run the checks above.
Declaration presence and coverage never count as actual product acceptance.

## Static implementation-gap evidence

```sh
python3 tools/figma_api_inventory.py coverage > api-static-coverage.json
python3 tools/figma_api_inventory.py coverage --check-baseline
```

These commands use the exact development compiler above. Supply `--typescript` when
using an existing external TypeScript 5.9.3 installation. The checked baseline records
source hashes and one status for every declaration member. After intentional bridge
or recipe changes, inspect the full report, then refresh it with
`coverage --write-baseline` and review `coverage-baseline.json` in the same diff.
`coverage --check-baseline` is the reproducible CI command; changes to either source
hashes or per-member status fail it. The baseline is static evidence, never a passing
runtime gate.

The scanner parses top-level bridge JavaScript, the shipped compiled Design recipe
entries, and the generated recipe dispatcher. It excludes comments and string-only
examples. It recognizes dot access, optional chaining and static string bracket access.
Every member has one of these statuses:

- `qualified-static-reference` means a syntactic `figma.*` path matches its declared
  namespace path. This includes guards, reads and call expressions. Receiver binding,
  control-flow reachability and overload selection are unresolved.
- `unresolved-receiver-name-reference` means only a member name appears on another
  receiver. For example, `object.resize()` cannot establish `LayoutMixin.resize`
  implementation. Node references rooted at `figma.currentPage` also remain unresolved.
- `no-static-reference` means neither form appeared in the scanned scope. Dynamic
  access, aliases or other delivery paths could still supply behavior.

Every row retains `implementation: unverified` and `runtime_acceptance: unverified`.
Ambiguous names can match several interfaces. Overload declarations count separately.
Source occurrences therefore cannot be interpreted as a percentage of implemented
APIs, functioning capabilities or accepted product requirements.
