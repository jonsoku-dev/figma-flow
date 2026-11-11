# Screen and action specification — Pre-Figma Quality Review

This file is a human-readable projection of [graph.json](graph.json); graph relationships and stable IDs remain canonical there.

## `SCR-QUALITY-01` — Context-pinned design review

- **Requirements:** REQ-QUALITY-01, REQ-QUALITY-02, REQ-QUALITY-03, REQ-QUALITY-04, REQ-QUALITY-05
- **States:** Planned authoring/review surface; actual runtime states are not yet specified or verified.
- **Action:** `ACT-QUALITY-01` — Review pinned preview and admit direction
- **Accepted by:** AC-QUALITY-01, AC-QUALITY-02, AC-QUALITY-03, AC-QUALITY-04, AC-QUALITY-05, AC-QUALITY-06
- **Implementation:** `CODE-QUALITY-01`–`CODE-QUALITY-04` reference [design intent](../../tools/design_intent.py), [pinned critique](../../tools/design_critique.py), [direction handling](../../tools/design_directions.py), and [workflow routing](../../tools/route_design.py). All code nodes remain unverified.
- **Evidence:** `TEST-QUALITY-01`–`TEST-QUALITY-02` reference existing [direct design](../../tests/test_direct_design.py) and [routing](../../tests/test_route_design.py) test files. Their execution is not claimed. No visual candidates or native Figma/visual-quality certification are produced here. Structural/contrast checks and Pillow demo wiring are not proof of visual quality.

### Action meaning

The action is planned and has no represented destination in this packet. Its behavioral details are defined in the feature requirement/acceptance text. Add actual state or destination nodes only when supported by the implemented flow or observed target.

`TEST-QUALITY-03` links the [explicit-mode source pipeline](../../tests/test_explicit_mode_packets.py) to the same action and acceptance relationships. Its compiled artifacts remain synthetic local proof, with actual native and visual acceptance unverified.
