# Search pending cards by title

IDs: REQ-CARDS-SEARCH, ACC-CARDS-SEARCH, STATE-CARDS-EMPTY-SEARCH, ACT-CARDS-SEARCH.
Screen: SCR-CARDS-LIST. Destinations: STATE-CARDS-LIST or STATE-CARDS-EMPTY-SEARCH.
Source meaning: brief.md line 4, title search with an explicit empty result.

Filter only the pending cards supplied by the list rule. Match a literal substring of the title after trimming query whitespace, normalizing both strings to NFC, and lowercasing in the Korean locale. Never search answers or questions. An empty/whitespace query shows all pending cards. Preserve input order. Show the result count and a clear button for nonempty input. For zero matches, show “일치하는 카드가 없어요” and the user's query as text. Clearing restores the pending list and focuses the search input. A zero-match search is not daily completion.

Implementation: app/rules/search.js. Focused tests: tests/search.test.cjs.
Tests cover casing, whitespace, Korean Unicode equivalence, title-only filtering, literal punctuation, zero results, text-safe query display, count/clear presentation and restoration. DOM rendering uses in-memory doubles.
