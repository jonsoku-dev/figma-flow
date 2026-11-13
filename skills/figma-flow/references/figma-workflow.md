# Figma workflow and evidence

일반 사용자는 Figma **Design 모드**의 로컬 플러그인만 사용한다. Figma Dev Mode·Computer Use·후크·원격 MCP는 필수가 아니다. Figma가 요청된 탐색 단계는 실제 네이티브 화면/주석과 Design 캔버스의 읽을 수 있는 대상 링크 주석 보드·팔레트·토큰·프로토타입 왕복 연결을 검증해야 사용자 선택 대기로 진행한다. 로컬 HTML만 읽고 네이티브 검증 완료라고 하지 않는다. 승인 전 본제작과 승인 전 명시적 탐색용 Figma 리뷰를 구분한다. 개발 검수의 CU는 별도 사용자 허용 시에만 가능하며 일반 실행 경로에는 의존하지 않는다.

0.15에서는 [정상 방향 선택 계약](direction-selection.md)의 실제 시안·사용자 선택이 모든 새 제작보다 먼저다. 후크·Computer Use·Stagehand·브라우저 드라이버·GUI 자동화 없이 동작한다. 선택 전에는 탐색 시안과 읽기/감사만 수행하며, 과거의 네이티브 검사 통과를 새 제작 승인으로 사용하지 않는다.

Figma가 포함된 작업에서 이 문서를 읽는다. `python3 tools/figma_feature.py route FEATURE`로 [기능별 실행 경로](figma-feature-routes.md)를 찾고 현재 등록 Flow의 작업·schema·실행 revision을 확인한다. 추가 기능은 검토한 별도 로컬 SDK를 사용하고, 파일 외 작업은 해당 REST 또는 제품 UI로 진행한다. Figma MCP 연결 확인이나 호출을 시작·대체 경로로 사용하지 않는다.

## Required native handoff for every Figma destination

Apply the [native capture, contract, bindings declaration and commands](local-design-audit.md#필수-네이티브-전달-검사-0130) to registered Flow imports and reviewed local SDK writes. Read back the selected actual file/page after writing, then run native_handoff.py and the project check_project.py entry. Missing native annotations, real local component-set instances, important variable bindings or expected action/state coverage block acceptance. Pin both capture and expected contract under bindings.native_handoff. Deliver the generated native screen specification and receipt; metadata or a screenshot cannot pass this gate.

## Choose the right surface

- 등록 Flow에서 지원되는 기능은 기존 workspace task 또는 명시적 예제 메뉴로 실행한다. 닫힌 플러그인은 사용자가 대상 파일에서 다시 열어야 한다. 현재 task/revision과 실제 file/page 범위를 확인한다.
- Flow 범위 밖의 Plugin API는 [SDK 프로젝트](../../../docs/figma-sdk-project.md)에서 편집기·모드에 맞게 별도 구현한다. 소스 검토 → check/build → 대상 편집기에서 수동 등록·실행 → 실제 getter와 렌더 검증 순서를 따른다. SDK는 등록 Flow controller의 임의 JS 실행 통로가 아니다.
- Plugin API 밖의 발행·발표·브랜치·계정 작업은 [기능별 실행 경로](figma-feature-routes.md)의 제품 UI/REST와 현재 사용자 권한을 따른다. 사용할 수 없는 기능만 pending/blocked로 남기고 독립 작업을 계속한다. 로컬 빌드 성공은 플랜·좌석·편집권을 보증하지 않는다.

## Source planning and native Specs

Preserve the original brief and its source/version. Link each requirement and acceptance criterion to its source and distinguish specified, inferred, and unresolved. The native screen specification generated from observed nodes is mandatory for Figma-backed handoff. The separate Figma Specs product is used only if the user requests it or it is the selected source: its availability and target plan must be checked. For the separate Specs product, use its product UI with the requested file and preserve content and comment anchors before and after edits; this Flow integration does not claim a Specs authoring API. A screenshot is not proof that the Spec's text was read. If Figma Specs is unavailable, retain and label the required external native-readback screen specification; this does not waive native annotations, component instances, variables or the handoff gate. Do not call ordinary text or comments a Figma Spec.

Pin evidence to the exact selection: file key, node IDs, observed version if exposed, read time and saved response/rendering path. If the host exposes no Figma version, record `unknown` plus the captured response hash; a response hash identifies that observation, not the current remote file. Re-read affected selections before relying on them after changes. Compare each fact against its selected authority from the run record; preserve disagreements rather than replacing brief intent with visual inference.

## From brief to editable screens

Inspect existing pages, local/published libraries, tokens, and relevant Code Connect links. Reuse suitable components and variables; create local components for genuinely repeated UI when appropriate. Give semantic names, retain editable text and hierarchy, use auto layout for related items, and keep stable requirement IDs distinct from Figma node IDs.

Create wireframes and final designs as separately identifiable artifacts linked to the same screen IDs. Ground visual hierarchy and styling in the product purpose, audience and real content; honor the brief, including restrained designs, and avoid unexplained placeholder content. Save the IDs and version evidence returned by writes. Verify the actual hierarchy, text, chosen component instances and variables, and inspect a real rendering for overlap, clipping, states and viewport behavior. Include a lightweight design accessibility pass for contrast, meaning conveyed by more than color, visible focus and interactions that do not depend only on hover; consider reduced motion when motion is present. Check these again in the actual application where applicable. A screenshot alone is not evidence of editability or functional completeness. Generated images and font availability follow the selected local plugin API, font loading and product permissions; do not misreport placeholders as final assets.

## Planning information and reactions

Write native `annotations` on supported screen/control nodes and read them back with action/state coverage. If native annotation support is blocked, keep the Figma handoff pending/blocked and report the affected node IDs; an external mapping can preserve work but cannot satisfy the native gate. User-editable source documents remain the authoritative home for detailed behavior and decisions.

Create actual prototype reactions for requested interactions, not just arrows. Where the host supports it, the Plugin API uses `setReactionsAsync` and exposes `reactions` for readback. Check the trigger and every action's type and required fields; check destination existence only for actions that have destinations. An action can use BACK, URL, a variable, or other behaviors without a destination node. Prototype playback and real application behavior are separate checks. If a step fails, record the error and affected screen IDs; do not invent a transition or infer playback from a write receipt.

## Figma to code and round trip

Use actual Flow native readback, the generated screen specification and an export/rendering of the selected nodes. If extra fields are needed, use a reviewed local SDK getter/export or a scoped REST read. Read large documents by relevant page/children instead of treating a partial response as the whole file. Compare screenshot, hierarchy, node text, states, variables, components, assets and reactions with the brief. Discover and reuse existing Code Connect mappings and actual repository components when applicable. Creating a new mapping is a separate operation with its own tool and permission rules; do not present an existing mapping as newly published.

A locally authored import must be inspected for editable layers, design-system component links and parity; an HTML/SVG/source input alone proves none of them. A code layer or Make import is a different artifact again. Clearly label which conversion occurred and whether it was actually inspected. Implement only from current, reconciled evidence; a parallel code draft made while Figma is unavailable is a useful partial result, not a verified Figma-to-code round trip.

## Evidence for each phase

| Phase | Minimum evidence before calling that phase verified |
| --- | --- |
| Brief | Source snapshot/version plus requirement, screen, state, action and acceptance coverage, with unknowns listed. |
| Wireframe | Actual Figma node IDs, editable hierarchy and reviewed layout for the requested screens/states. |
| Design | Actual updated node IDs, relevant component/token usage and reviewed rendering; note visual defects. |
| Native handoff | Actual screen/control annotations, component-set instances and bound-variable modes/aliases validated against the expected contract; pinned receipt and generated screen specification. |
| Prototype | Actual reactions read back; playback separately recorded. |
| Extraction | Required node/content/reaction sources reread, reconciled with brief; unavailable sources and gaps listed. |
| Frontend | Actual diff and relevant checks; run affected flows in a browser when practical. For persistent data, check read/write errors and relevant stale or concurrent writers. |

If quota is exhausted, stop Figma retries. Preserve the last successful results and unresolved operations in the run record, work independently where permitted, and resume only after access is restored and current target state is inspected. Recheck changed descendants rather than silently reusing stale evidence.

If a required Figma operation is unavailable, explicitly set the affected phase and dependent extraction/parity phase to `blocked`, with the error and resume condition. A placeholder URL, local screenshot, code-generated mock or local freshness manifest cannot satisfy actual Figma node, reaction, editability or playback evidence. Use the [live example workflow](live-example.md) to keep independent work actionable while preserving this boundary.
