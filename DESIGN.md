# CSV Sources - Design Document

> **Status:** Early design. Product vision is being captured collaboratively
> before any feature work begins. This document is the source of truth and
> should be updated continuously as decisions are made. It is intended to be
> detailed enough that an autonomous coding agent could pick up most of the
> implementation work directly from this file.

## Planning TODOs

Open items we need to dig into before (or alongside) implementation. Check
items off as they're resolved and move the resulting decisions into the
appropriate section below.

### Foundational research

- [ ] **Review fetch source design** — read the canonical Lovelace docs /
      skill material on what a "fetch source" is, how sources register with
      the platform, what the ingestion contract looks like (schemas,
      flavors, properties, relationships, provenance, primary keys,
      resolver behavior), and how a source's data flows into the
      Elemental Knowledge Graph. Capture the relevant findings under
      "Fetch Source Background" below.
- [ ] **Review Broadchurch fetch source prototype** — locate the existing
      prototype implementation in the Broadchurch ecosystem (likely a
      separate repo or a `fetch_source`-style module). Document what it
      does, what shape its inputs/outputs are, what infrastructure it
      uses (GCS, Cloud Run Jobs, Workflows, query server, etc.), and
      which pieces we should reuse vs. re-do for this app. Capture
      findings under "Fetch Source Background" below.

### Product definition (still to discuss)

- [ ] **Target users & primary use cases** — who is uploading CSVs, what
      data are they bringing in, and what do they want to do with it once
      it's in the graph?
- [ ] **Scope of CSV inputs** — single canonical schema, a fixed set of
      supported schemas, fully open-ended, or user-defined templates per
      "source"?
- [ ] **Column-to-ontology mapping UX** — how does a user say "this column
      is the entity name, that column is the ticker, this one is a
      relationship to an issuer entity, etc."? Manual UI, saved templates,
      AI-assisted suggestions, or some mix?
- [ ] **Source identity & re-upload semantics** — is each upload its own
      source? Do uploads stack into a named "source"? What happens on
      re-upload (replace, append, upsert by primary key)?
- [ ] **Validation & preview flow** — what does the user see before they
      commit an upload (sample rows, parsed entity preview, per-row
      errors, dry-run extraction)?
- [ ] **Ontology integration** — do we constrain users to existing
      flavors/properties, allow new ones, or both? How do we surface the
      Lovelace ontology to the user during mapping?
- [ ] **Provenance & lineage** — how do ingested entities/properties
      track back to the originating CSV file, row, column, and user?
- [ ] **File constraints** — max size, encoding (UTF-8 only?), delimiter
      detection, header handling, quoted fields, common dialect quirks
      (Excel-exported CSVs, BOMs, etc.).
- [ ] **Auth & tenant isolation** — confirm Auth0 + per-tenant Firestore /
      Postgres / GCS scoping. Who can see / re-run / delete a source?

### Technical plan (depends on items above)

- [ ] **Ingestion architecture** — sync upload → immediate parse, async
      Cloud Run Job, or hybrid? How does the parsed data reach the
      Elemental Knowledge Graph (direct gateway call, intermediate
      staging table in Postgres/BigQuery, or the standard fetch source
      pipeline)?
- [ ] **Storage decisions** — where do raw CSV files live (GCS bucket via
      portal?), where does per-source config / mapping live (Firestore
      via `useAppPrefs` / `useAppFeaturePrefs`?), where do staging /
      intermediate rows live?
- [ ] **Server endpoints** — enumerate `server/api/**` routes needed
      (upload, list sources, list uploads under a source, run/re-run
      ingest, fetch preview, delete).
- [ ] **Pages / UX surfaces** — enumerate pages (sources list, source
      detail, new upload wizard, mapping editor, run history, etc.).
- [ ] **Agents / MCP servers** — decide whether any of this needs an ADK
      agent (e.g. for AI-assisted column mapping) or an MCP server
      (e.g. exposing CSV sources to other agents). Default: none until
      we identify a concrete need.
- [ ] **Deployment plan** — web app to Vercel on push to `main`. Any
      Cloud Run Jobs / Workflows needed for ingest? If so, register
      under `jobs:` / `workflows:` in `broadchurch.yaml`.

---

## Project Overview

**CSV Sources** is an Aether app that lets end users upload CSV files
whose contents should be pulled into the **Elemental Knowledge Graph**
as a **fetch source**. In other words: it gives non-engineers a
self-service path for getting tabular data into the Lovelace platform
without needing a bespoke pipeline written for each new dataset.

The CSV upload tool itself behaves as a fetch source (in the same family
as EDGAR, FRED, FDIC, GLEIF, etc.) — but instead of pulling from a fixed
external API, its inputs come from user-uploaded files. Each upload
should result in entities, properties, and relationships appearing in
the graph with proper provenance back to the originating file and user.

> Detailed product scope (target users, supported CSV shapes, mapping
> UX, etc.) is still to be defined — see "Planning TODOs" above.

**Created:** 2026-05-24
**App ID:** csv-sources
**Description:** Aether app: CSV Sources — user-uploaded CSVs as a fetch source for the Elemental Knowledge Graph.
**Last updated:** 2026-05-24

## Configuration

| Setting        | Value                                |
| -------------- | ------------------------------------ |
| Authentication | Auth0                                |
| Query Server   | https://query.pip.prod.g.lovelace.ai |
| Tenant org     | org_k9Uy5G5qFE6YilKi                 |
| GCP project    | broadchurch                          |
| Data mode      | api-mcp                              |

## Fetch Source Background

_To be filled in after completing the two "Foundational research" TODOs
above._

### What is a fetch source?

_(notes from reviewing fetch source design)_

### Existing Broadchurch fetch source prototype

_(notes from reviewing the prototype: location, behavior, infra,
reuse vs. rebuild)_

## Cross-Cutting Concepts

_To be defined — likely candidates once we've discussed more:_

- CSV parsing & dialect handling
- Column → ontology mapping model (shared between UI, server, and any
  ingest job)
- Source / upload / run identity model
- Provenance tagging applied to every emitted entity / property

## Pages

_To be defined — likely candidates once we've discussed more:_

- Sources list
- Source detail (uploads, runs, schema mapping)
- New upload wizard (upload → preview → mapping → confirm → run)
- Run history / error inspector

### Page Template

Name:
Route:
Description:
Implementation status:
Details:
