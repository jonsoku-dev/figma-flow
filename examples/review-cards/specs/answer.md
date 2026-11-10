# Reveal an answer

IDs: REQ-CARDS-ANSWER, ACC-CARDS-ANSWER, STATE-CARDS-ANSWER, ACT-CARDS-REVEAL.
Screen: SCR-CARDS-REVIEW.
Source meaning: brief.md line 3, after seeing the answer the user can choose retry or completion.

Revealing is allowed only in the question phase and changes the selected review to phase "answer" without recording progress. In the question phase, answer text is cleared, its panel and the two choices are hidden, and both choice buttons are disabled. In the answer phase, display the answer as text, hide the reveal button, show and enable “다시 연습” and “복습 완료”. The reveal button maintains aria-controls and aria-expanded. The main controller focuses the answer panel after reveal.

Retry and completion transitions are independently owned by specs/retry.md and specs/complete.md. This rule owns answer visibility and availability of those controls, not their transition policies.

Implementation: app/rules/answer.js. Focused tests: tests/answer.test.cjs.
Tests cover phase transition, idempotent reveal, ignored list-state reveal, unchanged progress, text-safe rendering, all hidden/disabled/expanded attributes, and resetting presentation to the question phase. DOM assertions use in-memory doubles; browser focus and announcement remain unverified.
