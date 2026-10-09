
## UI look (2026-10-09)
- The user found the plain flat dark UI childish. Rule: give dashboards a finished look from the start — icons in the nav, a filled/glowing selected item, card shadows, round corners, gradient buttons, focus glow, and no big empty areas on wide screens. Compare with the user's own apps (MeetAI) before calling a UI done.
- Never put max-width on the scrolling element itself: the scrollbar then sits in the middle of a wide window. Limit the content inside (`main > *`) and let the scroll area fill to the window edge. Check a screen wider than 1920 px.
