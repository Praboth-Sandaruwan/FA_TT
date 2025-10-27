# Diagrams & Media Guidelines

This directory stores shared visual assets that support project documentation. Keep diagrams and media files close to the written docs so they stay discoverable and version controlled.

## How to organise files

- Create a subdirectory per project or domain (e.g. `project-a/`, `shared/`).
- Include both the rendered output (`.png`, `.svg`, `.pdf`) **and** the editable source (`.drawio`, `.puml`, `.fig`, etc.) so updates can be made without recreating assets from scratch.
- Use descriptive, kebab-cased filenames that indicate the subject and version, for example: `checkout-flow-v2.drawio`.

## Recommended formats

| Purpose | Preferred Format | Notes |
| --- | --- | --- |
| Architecture & sequence diagrams | `.drawio`, `.puml`, `.svg` | Export a static image for easy viewing in Markdown.
| UI mocks & wireframes | `.fig`, `.png`, `.jpg` | Link to Figma or other design tools when source files exceed repository limits.
| Data models | `.puml`, `.png`, `.svg` | Keep ERDs and schema diagrams next to the code they describe.

## Referencing diagrams in docs

- Store diagrams in this folder and link to them using relative paths, e.g. `![Checkout flow](../diagrams/project-a/checkout-flow-v2.png)`.
- For larger collections, add a local `README.md` within the project-specific subdirectory that explains the assets.
- Update the main documentation checklist in [`docs/template.md`](../template.md) once diagrams are added.

## Version control tips

- Prefer vector formats (`.svg`) where possible for clearer diffs.
- If binaries must be committed, keep them small and compress when appropriate.
- Remove outdated diagrams instead of leaving them orphaned; rely on git history if you need to recover old versions.
