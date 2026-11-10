---
name: graph-ssot
description: Use when a graph must own component design values, export them to Figma and web, import designer edits, or verify a native/web round trip.
---

# Graph-owned component design

Resolve tools relative to this installed plugin root. Read [the command, panel and schema guide](../../examples/graph-ssot/README.md) before pairing, importing or recovering. Use the installed 0.23.1 `figma_workspace.py` route by default. Reuse the registered stable manifest and ID; prepare `discover` / `sync` tasks with the originating thread UUID, then reopen the same Figma Flow. See the command guide for task revision/CAS updates and foreign-ID handling. The canonical values live in graph.design_system.tokens. Component properties contain token references, and generated web modules/stylesheets carry the graph hash.

Before creating or critiquing UI, follow the [bundled skill dependency contract](../figma-flow/references/skill-dependencies.md) and run the installed plugin's `tools/skill_dependencies.py --check`. Read verified bundled guidance within the graph-owned design constraints. Before browser proof, apply [target origin registration](../figma-flow/references/browser-access.md) through the current authorized host tools.

Default execution uses `figma_control.py enable` → workspace `refresh` → control `serve`, followed by the user's one manual plugin launch. Run prepared `discover/read` or `sync/read|apply` with exact file/page/current revision, then verify its returned readback and actual web proof. Manual panel buttons are fallback. A closed/stale plugin may require reopening; never promise hidden background startup or permanent hot reload. `uncertain` requires a current read before another write. Home history/next-action and language settings assist operation, not design acceptance.

## Establish the source

1. Read the selected graph and component native/web references. Inspect user changes. Preserve existing files and actual native getter evidence.
2. Discover the exact Figma file, source page and additional declared instance pages with `figma_workspace.py prepare --kind discover`. In **준비된 작업**, open that project task in the actual file. In **Figma 값 읽기**, click **Figma 값 읽고 저장** and save the downloaded actual getter JSON.
3. Use `prepare --kind sync -- --adopt` to migrate existing components to the graph's owned token namespace. Check actual old bindings/values and every instance of each declared main. Shared variables outside the declared graph scope must stay untouched. Each normal/disabled visual variant needs its own graph property scope.
4. Copy the exact returned web module to the app-owned module path, then import graphStylesheet or muiComponents. Preserve workspace generation files. MUI length values are explicit CSS pixels. Add the emitted graphSha256 as data-graph-sha on each matched element. Render actual web proof with exported web-probe.js through the current authorized browser.
5. Run the prepared sync task through local control with exact scope/current revision. The following UI sequence is the manual fallback: open the task from the same home. In **컴포넌트 동기화**, inspect **적용 범위 확인** before **확인한 범위에 적용**. **취소** closes confirmation without writing; it does not cancel a running apply. Save the automatically downloaded actual focused getter, and pair with native plan, exact generated module and actual browser proof. A generated file alone cannot complete pairing.

## Change and reconcile

- Graph edits: update token roots through graph_design_system.update_graph_values with the expected graph hash; prepare the sync task with graph+pairing and its current task revision; apply in Figma; reload/read the real web; pair the actual current native/web result.
- Native variable edits: click **Figma 값 읽고 저장**, preview graph_sync.py import, then --apply. Changes land in the graph first and regenerate the web module. Prepare the same sync task with the same actual native readback to reconcile the native baseline, then verify/pair.
- Designer direct main/instance edits: preview import --node-edit-scope component. Show affected mains, all connected instances and web selectors. Promote one unambiguous edit to that graph component only. Conflicting edits on a shared token stop the import. After --apply, prepare the same sync task with the accepted --import-report and exact actual readback; the repair plan restores canonical bindings and guards against further edits. Verify native and rendered web before pairing.
- Panel failures: **JSON 다시 저장** downloads the retained result without another write. Inspect **실행 기록과 복구 정보** and preserve rollback conflicts. Re-read current native state before regenerating a conflicted plan; older retained success JSON and rollback reports do not complete pairing.
- Interrupted graph/web publication: keep the recovery journal. Use recover only when its expected graph hash still matches; otherwise export the current graph again. A conflict never advances the baseline.

Return with **작업 목록** after task completion. Standalone manifests are a compatibility path, not the default for new work. Chat handoff targets the task's recorded thread; inspect selection/request content before copy or explicit queue, and do not infer the active desktop chat.

## Acceptance

Test font size/family, spacing and at least one visual property in both directions on the real component. Read main/instance values and bindings, CSS pixels/colors and actual graph hashes. Also inspect normal/error/loading/success and mobile, and verify a nonparticipating neighboring component stays unchanged. Preserve command exit codes and actual PNGs. Existing user-selection and design-acceptance gates retain their own meaning.

The current adapter handles declared typography/spacing, solid color/borders, radius/gap and supported dimensions. Fixed width/height require FIXED sizing. Mixed paints, external paint styles and changes requiring unmapped structure are conflicts. Component-scope import changes the declared logical component; an independent per-instance variant needs an explicit graph declaration and web selector.
