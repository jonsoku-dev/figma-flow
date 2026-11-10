# Finish the full daily deck

IDs: REQ-CARDS-FINISH, ACC-CARDS-FINISH, STATE-CARDS-DONE.
Screen: SCR-CARDS-LIST.
Source meaning: brief.md line 3, show a completion notice after today's cards are finished.

Count completed cards against the full daily deck, independent of the current search or selected card. Foreign and duplicate completion IDs do not increase the count. Show “오늘 복습, 완료!” only when every daily card is completed; an initially empty deck also has no remaining work. Update the native progress element and its text label. On completion hide the list/search area and show the completion panel within SCR-CARDS-LIST, never a third screen. Do not offer an unrequested new-day or reset action.

Implementation: app/rules/finish.js. Focused tests: tests/finish.test.cjs.
Tests cover partial and full progress, independence from filtered results, empty decks, duplicate/foreign IDs, and completion/progress DOM presentation using an in-memory double.
