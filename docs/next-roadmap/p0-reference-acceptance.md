# P0 Reference Safety & Owned Baseline Acceptance Receipt

- **Canonical Graph Node:** [`p0-reference-safety`](backlog.graph.json) (canonical status, `evidence_status`, dependencies, and `next-ready` computation live in [backlog.graph.json](backlog.graph.json))
- **Review Contract:** [capability-review.md#p0-reference-safety](capability-review.md#p0-reference-safety)
- **Roadmap Entry Point:** [README.md](README.md)

## Integration References & Guard Surfaces

- **Baseline Fixture (`main` `d988600`):** [examples/owned-design-baseline/README.md](../../examples/owned-design-baseline/README.md) · [manifest.json](../../examples/owned-design-baseline/manifest.json) · [graph.json](../../examples/owned-design-baseline/graph.json) · [tests/test_owned_design_baseline.py](../../tests/test_owned_design_baseline.py)
- **Distribution Guard & Regression Tests (`main` `976a966`, branch fix `b949523`):** [tools/reference_distribution_guard.py](../../tools/reference_distribution_guard.py) · [tests/test_reference_distribution_guard.py](../../tests/test_reference_distribution_guard.py)
- **CI Workflow & Operator Guides:** [.github/workflows/reference-guard.yml](../../.github/workflows/reference-guard.yml) · [CONTRIBUTING.md](../../CONTRIBUTING.md) · [docs/guide.md#private-distribution](../guide.md#private-distribution)

## Observed Acceptance Evidence

1. **Protected Reference Archive Integrity & Guard Scope**
   - SHA-256 parity verified across 4 external ZIP inputs and 4 locally preserved archive copies.
   - Protected registry and licensed-dependency guard checks passed clean.
   - **CI vs. Release Full Check Boundary:** CI ([.github/workflows/reference-guard.yml](../../.github/workflows/reference-guard.yml)) executes `paths-only` repository scans, `git archive` target-zip checks, and synthetic guard behavior tests without private inputs. Full release distribution verification runs locally against 4 private source archives and 67 guard rules (`tools/reference_distribution_guard.py --reference-zip ... --reference-literals ...`).

2. **Owned Baseline Browser Capture Parity (`examples/owned-design-baseline/`)**
   - Independent browser verification (Carbon and independent Chromium `1440x900`) exercised 7 clicks, 3 disclosure states, and 6 directed transitions.
   - All 10 captured state/click PNG artifacts were byte-identical across runs.

3. **Installed Own Plugin Figma Desktop Native Verification**
   - **Environment & Revision Hygiene:** Run on Codex host with installed own plugin; official MCP was not used, and cloud sync is not guaranteed as an acceptance condition. An earlier draft capture (`86/104/104`) was superseded after capture correction, retired under its exact revision rather than substituted, and re-executed cleanly on a fresh task with final captures.
   - **Apply / Repeat / Read:** Actual `apply`, repeat `apply`, and `read` checks all verified `current`, reporting editable node counts `85/103/103` across the 3 states while preserving the same 3 frame IDs.
   - **Interactive Navigation:** Native prototype wiring recorded 6 `ON_CLICK` destinations, and Figma Present traversal passed 6/6 direct clicks.

4. **Automated Repository Verification**
   - Owned baseline provenance, manifest, and disclosure tests: 4 passed (`python3 -B -m unittest tests.test_owned_design_baseline`).
   - Design editor specialization scope tests: 2 passed (`python3 -B -m unittest tests.test_design_specialization`).
   - Strict local interaction graph validation: passed (`python3 -B skills/figma-flow/scripts/graph.py validate examples/owned-design-baseline/graph.json --strict-local`).
   - Guard synthetic behavior tests & `paths-only` repo scan: 12 guard unit tests passed (`tests.test_reference_distribution_guard`) and `reference_distribution_guard.py --ref HEAD` clean; CI guard workflow green.

## Public Disclosure Boundaries

- Original protected template labels, pre-rewrite historical SHAs, personal filesystem paths, Figma file/page/node IDs, and private/device raw outputs remain excluded from public documentation and Git history.
