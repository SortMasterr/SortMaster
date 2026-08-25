# SortMaster project instructions

## Source of truth

- Before changing project behavior, read `CLAUDE.md` and the documents it routes to.
- For previous-record and dashboard work, read `Docs/API_SPEC.md` and `Docs/ERD.md` first.
- Treat explicit implementation-status notes in the documents as authoritative. Do not present planned schema fields as implemented.
- When documentation and code disagree, report the conflict before changing the API or schema.

## Current work scope

- Focus on the previous-record page (`/events`) and dashboard page (`/statistics`).
- Do not modify the monitoring page, camera streaming, or streaming pipeline unless the user explicitly requests it. The CTO owns that area.
- Preserve the existing page routes and API paths.

## Naming conventions

- Use camelCase for project-defined variable names, function and method names, configuration keys, internal JSON fields, manifest fields, and generated artifact names unless an external contract requires another form.
- Use PascalCase for class names.
- Preserve names required by Python special methods, standard-library APIs, third-party libraries, model class labels, database schemas, existing public APIs, protocols, and file formats. Examples include `__init__`, Ultralytics arguments such as `save_txt`, and existing YOLO class names such as `trash_normal`.
- Do not rename an established external API or database field solely to satisfy this convention. Follow the relevant specification and update its documentation when an authorized schema change is made.
- When changing a project-defined name, update all related code comments, configuration examples, manifests, and README documentation in the same change.

## API and data rules

- JSON fields use camelCase. WebSocket `eventType` values use UPPER_SNAKE_CASE.
- API or schema changes require CTO review and corresponding updates to `Docs/API_SPEC.md` and `.agentfiles/apiSpec.md`.
- Never assume that `detectionId`, `trackingId`, `binId`, `binType`, `modelVersion`, `BIN_STATES`, or camera-specific GridFS buckets are already implemented; `Docs/ERD.md` currently marks these as designed but not fully reflected in code.
- Keep development and production database configuration separate. Do not start a local MongoDB or write to the production database without explicit user direction.

## Verification

- Use Python 3.11 in `WebApps/backend/.venv`.
- Verify frontend changes against the current API contract and test without modifying production data.
