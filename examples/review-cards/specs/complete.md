# Complete one reviewed card

IDs: REQ-CARDS-COMPLETE, ACC-CARDS-COMPLETE, ACT-CARDS-COMPLETE.
Screens: SCR-CARDS-REVIEW to SCR-CARDS-LIST.
Destinations: STATE-CARDS-LIST or STATE-CARDS-DONE.
Source meaning: brief.md line 3 offers “복습 완료”; the draft proposes returning to the list.

Only an existing card in the answer phase can be completed. Add its ID once to completedIds, clear review, and retain deck contents and the search query. No source card is deleted. Repeated calls from the returned list are inert. A stale duplicate completion cannot increase the count. Before reveal, outside review, or with an unknown card ID, return the unchanged session.

List rendering excludes this ID. The independent finish rule decides whether the full deck is complete. The main controller focuses the list heading, or the completion heading after the final card. If a retained query matches no remaining card while others remain, show an empty search result rather than a daily success message.

Implementation: app/rules/complete.js. Focused tests: tests/complete.test.cjs.
Tests cover exact completion, input immutability, query/deck preservation, return to list, duplicate handling, and invalid/early calls.
