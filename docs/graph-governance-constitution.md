# Graph SSoT and Code Quality Constitution

Version: 1.0.0
Issued: 2026-11-23
Applicability: Repositories that adopt this constitution. Adoption and technical enforcement are separate states and MUST be reported separately.

## 1. Purpose, authority, and scope

This constitution governs how developers and agents maintain Graph SSoT consistency, code quality, dependency boundaries, generated artifacts, and evidence of completion. Its objective is a reproducible development process in which relevant violations are detected and blocked without expanding every task into repository-wide cleanup.

MUST and MUST NOT establish mandatory requirements within the declared scope. SHOULD establishes a default whose exceptions require a recorded reason. MAY permits a choice without requiring it.

1. Work MUST be limited to the requested outcome, its necessary dependencies, and applicable mandatory repository checks. Optional improvements MUST NOT become implicit requirements.
2. Existing user changes MUST be preserved. This constitution does not authorize deployment, external communication, destructive data operations, or changes outside the authorized repository scope.
3. Before modifying tooling, an agent MUST inspect the actual repository instructions, versions, configuration, entry points, generation workflow, and CI behavior relevant to the task. A remembered or recommended configuration is not evidence of installation.
4. Repository-wide detection MUST NOT imply repository-wide remediation within every task. Unrelated existing defects MUST be reported separately unless they block the authorized outcome.
5. This constitution governs repository work within the user's authorization. It does not override platform permissions or grant authority to bypass existing controls.

## 2. Tool responsibilities and ownership

The initial preferred toolchain is Biome, Oxlint, and Knip because it is already in use. These names are defaults, not permanent requirements. Responsibilities and required coverage are normative; implementations MAY change under Section 10.

| Responsibility | Default owner | Required boundary |
| --- | --- | --- |
| Formatting and import organization | Biome | One designated formatter or fixer per behavior and file scope |
| General JavaScript, TypeScript, and framework lint | Oxlint | Enable relevant supported rules; avoid duplicate primary ownership |
| Supported type-aware lint | Oxlint when compatible | Verify backend and project compatibility; do not confuse built-in and custom rule support |
| Necessary lint for supported non-JavaScript files | Biome | Retain useful CSS, JSON, YAML, Markdown, and other applicable coverage |
| Unused files, exports, and package dependencies | Knip | Analyze appropriate entry points and consumer boundaries |
| Circular dependency checks | One designated existing analyzer | Select according to the repository's policy and actual capabilities |
| Project type correctness | The repository's verified type-check command | Type-aware lint does not automatically replace this responsibility |
| Graph, contract, document, and generation consistency | The existing Graph system or an independent verifier | Use deterministic evidence appropriate to each assertion |


1. A repository MUST maintain an understandable mapping from required checks to their responsible tools. Existing configuration and documentation SHOULD express this mapping without creating a duplicate manual registry.
2. Formatting, import sorting, unused-import fixes, and other automatic modifications MUST have a designated owner for each applicable scope. Conflicting fixers MUST NOT run against the same behavior.
3. Overlapping rules MUST be assessed by semantics, file coverage, and options, not by similar names alone. Removing duplication MUST preserve required detection.
4. A second analyzer MAY cover a documented gap or provide a distinct diagnostic benefit. Running multiple complete recommended rule sets without a defined purpose is not an acceptable default.
5. Version-sensitive capabilities, plugin stability, and language support MUST be verified against the installed versions. Such implementation details SHOULD reside in versioned tool configuration rather than being frozen into this constitution.

## 3. Biome policy

1. Biome SHOULD own formatting and import organization for file types it supports adequately in the adopted version.
2. Necessary lint for configuration, stylesheets, documentation syntax, and other supported non-JavaScript files SHOULD remain enabled where it provides useful coverage.
3. JavaScript and TypeScript rules duplicated by the primary linter SHOULD be disabled or assigned a distinct documented scope. Biome-only checks MUST NOT be removed before their relevance and replacement coverage are assessed.
4. Local formatting MAY apply approved fixes. CI MUST verify the submitted artifact rather than silently accepting an altered workspace as the original submission.
5. Formatting and document syntax checks MUST NOT be reported as validation of Graph semantics, API contracts, policy values, or prose accuracy.
6. If generated outputs are formatted, the formatter version and relevant configuration MUST be included in the generation inputs, and expected outputs MUST use the same formatting process.

## 4. Oxlint policy

1. Oxlint SHOULD own general JavaScript and TypeScript correctness checks and relevant framework rules. Plugin availability MUST NOT be confused with activation.
2. The rule set SHOULD prioritize concrete correctness and project needs, including applicable asynchronous behavior, framework conventions, accessibility, and import restrictions. Enabling every rule is not a quality objective.
3. Type-aware lint MAY be enabled only after verifying compatibility with the actual TypeScript features, configuration, package resolution, and backend. Enabling it MUST NOT silently initiate an unrelated TypeScript migration or remove an existing type-check gate.
4. Support for built-in type-aware rules MUST NOT be treated as proof that custom plugins can access equivalent type and symbol information.
5. Explicit import restrictions SHOULD enforce simple module boundaries where sufficient. More complex boundary plugins MAY be used when a documented policy requires them and their resolution coverage is verified.
6. Rules against hardcoding MUST identify specific Graph-owned definitions or prohibited access paths. Blanket bans on all numbers or strings MUST NOT substitute for domain policy enforcement.
7. Importing a generated module MUST NOT, by itself, establish that the implementation consumes the required contract or policy. Checks requiring symbol, type, data-flow, or behavioral evidence MUST use an appropriate verifier.
8. Existing suppressions SHOULD be reviewed within the affected scope. New suppressions MUST identify a concrete reason and MUST NOT merely hide an unresolved required violation.

## 5. Knip and unused-code policy

1. Knip SHOULD own project-level unused-file, unused-export, and package-dependency analysis. Local unused-variable lint and project-level unused-code analysis MUST be treated as different responsibilities.
2. Entry points MUST represent actual runtime, build, tooling, framework, package, and supported integration boundaries. Routes, workers, CLIs, generated entries, and dynamic registration MUST be considered where applicable.
3. Graph registration or documentation references MUST NOT automatically make code an execution entry point or establish runtime usage.
4. Applications and externally consumed packages MUST be distinguished. Public exports MUST NOT be deleted solely because this repository contains no consumer.
5. Default and production analysis MUST have explicit purposes. Production analysis does not universally replace default analysis, and development artifacts MUST NOT be classified as production dead code merely because they are outside the production scope.
6. Analysis MUST retain the dependency and consumer context needed for its conclusions. Passing only changed files is not a valid optimization when it destroys that context.
7. Circular dependency analysis MAY be assigned to Knip if the adopted version and policy support it. The selected issue types and severities MUST match the intended gate; reported warnings MUST NOT be assumed to block a merge.
8. Unused findings are candidates until consumer boundaries and relevant analysis limitations are accounted for. A candidate within the governed change scope MUST receive a disposition: remove or consolidate, retain with evidence, or explicitly defer under an authorized exception.
9. Unmapped or unresolved elements MUST NOT be classified as unused solely because evidence is missing. Mutual references, incomplete entries, dynamic loading, and external consumers MUST be considered in interpreting results.
10. Static code references alone MUST NOT authorize deletion of database structures, production data, published interfaces, or externally consumed assets.

## 6. Graph authority and traceability

1. The authoritative Graph MUST represent declared intent: governed requirements, contracts, policies, schemas, states, boundaries, and artifact responsibilities.
2. The observed Graph MUST represent facts extracted from the actual source snapshot. It is a derived observation, not a second manually maintained SSoT.
3. Declared, extracted, and inferred relationships MUST be distinguishable. Evidence MUST identify relevant source locations, source identity, and the extraction or verification method.
4. Observed implementation MUST NOT silently redefine authoritative intent. Reconciliation MUST distinguish correcting an implementation from explicitly changing an approved contract.
5. Domain identifiers MUST remain independent of incidental file names and line numbers. Locations and symbols are evidence and bindings; ambiguous rename or move matches MUST remain unresolved until supported.
6. Business contracts and meaningful boundaries MUST be explicit. Internal helpers, files, and calls SHOULD be extracted automatically rather than requiring manual domain registration for every function.
7. Relationship types and directions MUST be defined. Import, call, generation, implementation, documentation, and data-access relationships MUST have appropriate and distinct traversal policies.
8. Graph binding, observed usage, and contract compliance MUST be separate assertions. None establishes the others automatically.
9. Structural comparison MUST distinguish agreement, missing required relationships, prohibited relationships, unbound governed elements, and analysis uncertainty. Optional or planned relationships MUST NOT be treated as missing active implementation without a policy requiring them.
10. A refactor that preserves the contract MAY update observations and bindings without changing authoritative intent. A contract-changing implementation MUST include the corresponding authorized source change.

## 7. Generation and contract compliance

1. Each governed definition MUST have one authoritative owner. Graph-owned API definitions, enums, policy values, and boundary policies MUST NOT acquire independently editable copies in generated code or tool settings.
2. Structured artifacts SHOULD be generated or interpreted from the authoritative definition where the model is sufficiently expressive. Examples include API contracts, types, policy constants, state tables, configuration, and structured documentation.
3. Tool-specific boundary and policy configuration SHOULD be derived from the same authoritative policy when practical. Multiple analyzers MUST NOT require independent manual copies of the same architectural truth.
4. Generation verification MUST recreate expected artifacts in a clean location and compare both the managed file set and contents. It MUST detect modified, missing, unexpected, and obsolete managed outputs.
5. Generation inputs MUST include the relevant Graph content, generator, templates, options, tool versions, and other output-affecting configuration. Hidden environmental inputs and volatile metadata MUST NOT silently invalidate reproducibility.
6. Generated files MUST NOT be edited as a workaround for an incorrect generator or source definition. The correction MUST be made at the owning source or generator and propagated through generation.
7. Generated status MUST NOT grant a blanket exemption from validation. Applicable type, correctness, contract, and reproducibility checks MUST remain. Any style-only exception MUST be narrowly scoped and justified.
8. Handwritten business logic and UI behavior MUST consume the appropriate governed contracts and undergo the relevant static or behavioral verification. A code link, type assertion, or import alone is insufficient evidence.
9. Behavioral checks MUST exercise meaningful requirements, examples, or boundary cases. Comparing outputs from the same faulty transformation against themselves MUST NOT be presented as independent correctness evidence.
10. Free-form documents MUST identify the governed definitions they describe and the input version last reviewed. A relevant source change MUST result in an update, a reasoned no-change review, or an outstanding review state. Updating a timestamp or hash alone does not validate prose.
11. LLM-authored implementation and prose MUST NOT be treated as deterministic compiler output. Automatic synchronization guarantees MUST be limited to the modeled and verified scope.

## 8. Change impact and efficient execution

1. Impact analysis MUST use typed dependency traversal. For a relationship meaning that A depends on B, a change to B requires considering A and applicable downstream dependents.
2. Additions, modifications, deletions, and moves MUST be considered. Relevant relationships from both the previous and current Graph MUST be used so that removed nodes or edges do not erase their own impact.
3. Stable identifiers and structural analysis SHOULD be used where text diff cannot reliably identify changes. AST diff MUST NOT be described as proof of semantic equivalence.
4. Root reachability MAY identify unused candidates. SCC analysis MAY identify cycles, and topological ordering MAY schedule acyclic generation dependencies. Cycles in a general knowledge graph MUST NOT automatically be treated as build failures; collapsing a cycle does not resolve a forbidden generation dependency.
5. Affected targets MUST be assigned the required action: regenerate, modify, verify, review documentation, investigate usage, or supply missing evidence. A verified no-change outcome is valid; touching every affected file is not a completion requirement.
6. Caches and indexes MUST be tied to the actual inspected snapshot and relevant inputs, including applicable extractor, resolver, entry-point, generator, and policy configuration. A matching HEAD alone is insufficient when uncommitted changes exist.
7. Existing task runners SHOULD execute the necessary affected work using correct input and output declarations. Ordering dependencies alone MUST NOT be assumed to propagate every change. Generation changes MUST be reflected in the final task selection.
8. Expensive whole-project analysis MUST NOT run on every keystroke without a demonstrated need. Local feedback SHOULD use the smallest valid scope; integration checks MUST retain the context needed for valid conclusions.
9. Broader scans MUST be justified by a concrete risk, changed analysis input, incomplete evidence, or an existing mandatory gate. Completed checks MUST NOT be repeated without a relevant new change or failure.

## 9. CI enforcement and evidence

1. Required checks MUST cover applicable Graph integrity, generation consistency, structural policy, contract behavior, affected-artifact disposition, unused-candidate disposition, and evidence completeness.
2. A required result MUST identify the inspected source and Graph versions. Stale indexes or missing required evidence MUST NOT yield a successful compliance claim.
3. Results MUST distinguish pass, fail, needs review, and unknown. An explicitly out-of-scope item MAY be marked not applicable with a reason; it MUST NOT be counted as verified. Unknown evidence required for a governed change MUST block the compliance claim unless a specific authorized exception applies.
4. Each actionable finding MUST provide the rule or requirement, affected target, source evidence, applicable impact path, required action, and verification status. Human-readable and machine-readable results SHOULD share the same underlying findings.
5. The final required gate MUST fail when a mandatory sub-check is absent, unexpectedly skipped, or unsuccessful. A missing report or a natural-language agent completion message MUST NOT substitute for execution evidence.
6. CI SHOULD verify the submitted snapshot without applying automatic fixes. The configured required-check and repository protection settings MUST correspond to the intended merge policy.
7. Changes to verification code, generators, workflows, core contracts, suppressions, and baselines MUST receive review appropriate to their control impact. Implementation agents MUST NOT weaken checks or expand exceptions merely to obtain a passing result.
8. Repository controls MUST prevent ordinary implementation automation from bypassing required checks. Writing a workflow file MUST NOT be reported as activating a remote merge restriction.
9. Completion reports MUST distinguish proposed design, implemented code, local verification, observed CI execution, and activated merge enforcement. Missing permissions or unavailable environments MUST be reported accurately after all authorized preparatory work is completed.

## 10. Optimization and tool replacement

1. Existing Biome, Oxlint, and Knip configuration SHOULD be optimized before replacement. Priority SHOULD be: remove duplication, enable necessary compatible capabilities, correct analysis boundaries, and improve scheduling.
2. A tool or plugin MAY be added or replaced when a documented capability gap, compatibility issue, maintenance benefit, or measured performance improvement justifies it and required coverage is preserved.
3. Evaluation MUST begin with the actual required checks and file types. A tool MUST NOT be selected solely because it is newer, has more rules, shares a vendor, or advertises a faster benchmark.
4. Performance comparisons MUST use comparable source, environment, scope, and cache conditions. A speed gain caused by missing consumers, weaker checks, or measurement noise is not an improvement.
5. Correctness, false positives, diagnostic usefulness, configuration complexity, dependency cost, and migration impact MUST be considered alongside runtime. A modest runtime increase MAY be justified by meaningful required coverage.
6. Alternatives MUST be narrowed to the concrete unresolved need. Examples include a supported custom type-aware rule engine, a boundary plugin, a module graph extractor, or a formatter with required language support. These examples do not mandate additional tools.
7. New tool adoption MUST NOT silently install global skills, hooks, agent instruction files, or external services. Plugin side effects and applicable use conditions MUST be checked before adoption.
8. A project-wide language or framework migration MUST NOT be introduced solely to enable an optional lint feature without explicit scope justification.

## 11. Baselines, exceptions, and amendments

1. Initial adoption MAY record confirmed pre-existing violations in a scoped baseline. A baseline records debt; it does not make the implementation correct or expand the approved design.
2. New verified violations MUST be blocked within the governed scope. Existing violations SHOULD be repaired when they intersect the authorized change, unless an applicable exception explains the disposition.
3. Exceptions MUST identify the rule, target, reason, approving authority, and a review condition or expiry appropriate to the risk. Broad directory ignores MUST NOT conceal unrelated future violations.
4. Baselines and exceptions MUST NOT be regenerated automatically to absorb newly introduced failures. Their amendments MUST be explicit and reviewable.
5. Fixes to a defective rule or analyzer MAY change the check, but MUST explain the defect and preserve the intended protection. Silencing a real violation is not a rule fix.
6. Amendments to this constitution MUST record the changed obligation, rationale, affected controls, and version. An implementation change MUST NOT implicitly amend the constitution.
7. Adoption MUST demonstrate both a valid change passing and representative governed violations failing, using bounded fixtures or relevant repository examples. Unknown cases and unsupported scope MUST remain visible.
8. Once the authorized outcome and required checks are complete, work MUST stop. Additional cleanup or optimization requires a separate scoped task unless it is necessary for current acceptance.

## Non-normative reference material

These references describe tools and techniques. The adopted versions and repository configuration determine actual capability. Reading every reference or installing every referenced tool is not required.
- Biome language support and configuration.
- Oxlint, type-aware linting, and JS plugins.
- How Knip works, production mode, and issue types.
- Software Reflexion Model.
- Bazel Skyframe.
- dependency-cruiser rules.
- Boundaries integration with Oxlint.
- typescript-eslint custom rules and supported dependency versions.
- GitHub protected branches.
