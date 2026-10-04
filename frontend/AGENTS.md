<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Project Learnings
- Sleep Consistency trend updates must retain the supplied reference's vertical bars and breakdown layout while changing only the requested data and ranges.
- Sleep Stress has only a high-stress detector; its chart must not label other valid windows as medium or low stress.
- Every navigable sleep breakdown row needs the same trailing chevron so its percentage aligns with the other rows.
- Sleep chart value labels must clear neighboring plots and render after them; place labels on opposite sides when the asleep and needed lines cross.
