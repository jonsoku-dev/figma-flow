# Open a question and return

IDs: REQ-CARDS-QUESTION, ACC-CARDS-QUESTION, STATE-CARDS-QUESTION, ACT-CARDS-OPEN.
Screens: SCR-CARDS-LIST, SCR-CARDS-REVIEW.
Source meaning: brief.md line 2, choosing a card shows its question and a reveal button.

Only an existing pending card may be opened. Opening sets review to {cardId, phase: "question"}; it preserves progress, order and the search query. An unknown or already completed ID leaves the session unchanged. Render the selected title, question and category as text. The answer rule controls the initially hidden answer and visible reveal button.

The review screen's “카드 목록” button returns to the same filtered list without completing the card. Reopening always begins at the question. Main-controller focus moves to the question screen heading on open and to the originating card on return, falling back to the list heading if needed.

Implementation: app/rules/question.js. Focused tests: tests/question.test.cjs.
Tests cover selection, invalid/completed IDs, immutable transitions, query/progress preservation, return/reopen, and question DOM text using an in-memory double. Actual browser focus is not established by these tests.
