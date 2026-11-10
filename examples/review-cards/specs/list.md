# Daily pending cards

IDs: REQ-CARDS-LIST, ACC-CARDS-LIST, STATE-CARDS-LIST.
Screen: SCR-CARDS-LIST.
Source meaning: brief.md line 2, today's cards are listed.

The supplied daily deck is copied into a new in-memory session. Four Korean learning cards are illustrative content, not user data. Display pending cards in deck order, excluding completed IDs. Each card is a native button with its title and category. Clicking it passes its exact ID to the question rule. Titles are written as text, never parsed as HTML. The list can be empty. Completing a card does not delete its source content.

Implementation: app/rules/list.js. Focused tests: tests/list.test.cjs.
Tests cover initial order, independent session data, exclusion of completed cards, an empty deck, text-safe DOM rendering, accessible button labels, exact selection, and replacement of obsolete list entries with in-memory DOM doubles.

Policy assumption: this is one session's daily deck. Reloading creates a new session; scheduling, editing, accounts and persistence are outside the draft.
