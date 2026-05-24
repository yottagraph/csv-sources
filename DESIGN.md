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

- [x] **Review fetch source design** — read the canonical Lovelace docs in
      `Lovelace-AI/lovelace` under `moongoose/fetch/onboarding/`
      (`README.md`, `GUIDE.md`, `reference/gcs-infrastructure.md`,
      `skills/implement-source/SKILL.md`) plus `moongoose/fetch/README.md`
      and `moongoose/cmd/ingestng/README.md`. Findings captured under
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
      Elemental Knowledge Graph: produce `FetchMessage` protos in the
      same format as the canonical pipeline (`.binpb.zst` files in an
      ingest-watched extract bucket), or use a different path entirely
      (e.g. direct gateway call, BigQuery staging)?
- [ ] **Storage decisions** — where do raw CSV files live (per-tenant
      GCS bucket via the Broadchurch portal? shared bucket with tenant
      prefix? something else?), where does per-source config / mapping
      live (Firestore via `useAppPrefs` / `useAppFeaturePrefs`?), where
      do produced `FetchMessage` files land for ingest pickup?
- [ ] **FetchMessage production** — what language / library writes
      `FetchMessage` protos for atomized records? Options: import the
      moongoose Go fetch lib as a dependency in a Go Cloud Run service;
      generate Python bindings from `fetchapi.proto` and use them in a
      Python Cloud Run service / job; or roll a thin TypeScript proto
      writer in the Nuxt server. Need a decision and a rationale.
- [ ] **Ingest hookup** — how do produced files get picked up by ingest?
      Options: write into an existing newgate-managed extract bucket and
      let the existing Pub/Sub notification flow + `ingestng` handle it
      automatically; create our own bucket and register an `ingestng`
      glob request pointing at it; or stand up something separate.
- [ ] **Dataset schema strategy** — every fetch source has a
      `schema.yaml` declaring flavors / properties / relationships /
      attributes. Do we (a) maintain a single fixed
      `csv-sources/schema.yaml` and constrain users to its vocabulary,
      (b) generate a per-source `schema.yaml` from each user mapping and
      register it dynamically, or (c) something hybrid (fixed base
      vocabulary + extension points)?
- [ ] **Source identity model** — every fetch source has a `Source`
      string constant (e.g. `edgar-source`) and is registered in
      `registry.go`. For us, do all user uploads share one umbrella
      source (e.g. `csv-uploads-source`) with per-upload metadata
      carried inside the records, or does each user-created "source"
      get its own constant / registration / extract bucket?
- [ ] **Quality gates** — the canonical workflow requires `recordeval`,
      `schemacheck`, Deep Research dictionary + extraction reviews, and
      a full eval-stack ingest test in `gcp-danger` before any source is
      "done". Decide which of these we can run on user-uploaded data
      (likely `recordeval` per upload, before publishing to the ingest
      bucket), which we can run at design time on the dataset schema we
      ship (`schemacheck`), and which are not applicable / get a
      lightweight substitute.
- [ ] **Server endpoints** — enumerate `server/api/**` routes needed
      (upload, list sources, list uploads under a source, run/re-run
      atomize, fetch preview, delete).
- [ ] **Pages / UX surfaces** — enumerate pages (sources list, source
      detail, new upload wizard, mapping editor, run history, etc.).
- [ ] **Agents / MCP servers** — decide whether any of this needs an ADK
      agent (e.g. for AI-assisted column mapping) or an MCP server
      (e.g. exposing CSV sources to other agents). Default: none until
      we identify a concrete need.
- [ ] **Deployment plan** — web app to Vercel on push to `main`. Cloud
      Run service / Job for the atomization worker (and any per-tenant
      bucket bootstrap). Register Cloud Run Jobs under `jobs:` in
      `broadchurch.yaml`. Cross-project IAM if our Cloud Run service
      needs to write into a `lovelace-infrastructure` or `gcp-newgate`
      ingest bucket.

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
**Last updated:** 2026-05-24 (added Fetch Source Background)

## Configuration

| Setting        | Value                                |
| -------------- | ------------------------------------ |
| Authentication | Auth0                                |
| Query Server   | https://query.pip.prod.g.lovelace.ai |
| Tenant org     | org_k9Uy5G5qFE6YilKi                 |
| GCP project    | broadchurch                          |
| Data mode      | api-mcp                              |

## Fetch Source Background

### What is a fetch source?

> **Source:** [`Lovelace-AI/lovelace`](https://github.com/Lovelace-AI/lovelace) — read primarily under
> `moongoose/fetch/onboarding/` (`README.md`, `GUIDE.md`,
> `reference/gcs-infrastructure.md`,
> `skills/implement-source/SKILL.md`) plus `moongoose/fetch/README.md`
> and `moongoose/cmd/ingestng/README.md`. The two-bucket flow and the
> three-stage pipeline described below are taken directly from those
> docs and are the contract we have to honor (or deliberately diverge
> from) to land data in the Elemental Knowledge Graph.

#### One-line summary

A **fetch source** is a Go streamer that runs continuously, pulls data
from some external place, persists raw bytes to GCS, atomizes them into
canonical `FetchMessage` protobufs, and publishes those protos to a
second GCS bucket where the **ingest service** notices them via Pub/Sub
and writes them into the knowledge graph.

#### The Download → Extract → Atomize pipeline

Every source implements the `Streamable` interface in
`moongoose/fetch/fetchtypes/streamable.go`, which is built around a
three-stage pipeline orchestrated by the source's `HandleStream`:

1. **`Download(ctx, start, end)`** — pull raw data from the external
   source and persist each unit to the **raw store** at
   `{rawStore}/{source}/download/{date}/{id}.json`. Returns the
   download URIs.

2. **`Extract(ctx, downloadURI)`** — optional LLM-driven extraction for
   freetext sources (news articles, PDFs, etc.). For structured sources
   like EDGAR, FRED, FDIC, GLEIF, and CSV/JSON APIs this is a **no-op
   that returns the download URI unchanged**. When non-trivial it
   writes to `{rawStore}/{source}/extract/{date}/{id}.json`.

3. **`Atomize(ctx, extractURI)`** — convert the extracted data into
   `FetchMessage` protobufs. Each `FetchMessage` carries `Record`s with
   a `Subject` (a `ProtoEntity` with `Flavor`, `Name`, `StrongIds`,
   `Aliases`, mergeability info, and citations) plus a list of `Atom`s
   (each carrying a `Property` name, a value (`str_val` / `float_val`
   / `target` for a relationship), citations, and timestamps).
   Records are validated against the source's `schema.yaml` and the
   resulting `.binpb.zst` files are written to the **extract store** at
   `{extractStore}/{pipeline}/{date}/{key}.binpb.zst`.

`HandleStream` is the long-running loop that drives this pipeline; for
timer-driven sources it uses `RunPollingLoop` (immediate first run,
poll ticker, heartbeats). Sources also write **checkpoints** so each
poll knows what's new, and emit pipeline-stage counters via
`GetPipelineStats()` for Grafana visibility.

#### The two-bucket model

Each source has a presence in two GCS buckets:

| Bucket | Purpose | Path convention |
|--------|---------|-----------------|
| **Raw store** (shared across sources) | Stores raw bytes downloaded from the external source. | `{rawStore}/{source}/download/{date}/{id}.json` |
| **Extract store** (per source) | Stores atomized `FetchMessage` protobufs ready for ingest. | `{extractStore}/{pipeline}/{date}/{key}.binpb.zst` |

In the canonical newgate deployment these are named
`{env_code}-{business_code}-fetch-raw-data` (shared) and
`{env_code}-{business_code}-fetch-{sourcename}` (per source). The
extract bucket has a GCS bucket-notification → Pub/Sub topic →
Cloud-Storage subscription that drops Avro notification files into a
shared `{...}-fetch-subscriptions` bucket. A daily Storage Insights
inventory report also lands in `{...}-fetch-inventoryreports`. All of
this — buckets, Pub/Sub, IAM, inventory — is provisioned by Terraform
under `gcp-newgate/tf/modules/base_k8s/k8s-newgate-fetch.tf` whenever
a source name is added to `local.fetch_sources`.

#### The ingest service (`ingestng`)

`moongoose/cmd/ingestng` consumes `FetchMessage` files and writes their
records into the knowledge graph database. Two API request types:

- **`ApiGlobRequest`** — register a glob URL (e.g.
  `gs://x-newgate-fetch-foo/*/*.binpb.zst`) with request type `ingest`
  or `delete`. Files matching the glob are actively ingested (and
  re-ingested when their mtime changes); `delete` globs remove
  previously-ingested quads.
- **`ApiEfidRequest`** — re-ingest a specific extraction file by id,
  primarily used by Rewrite jobs.

Storage backends are `file://...` and `gs://...`. File formats accepted
are `.pb`, `.binpb`, `.pb.json`, `.pb.txt`, each optionally `.zstd`.

#### Per-source artifacts

Every source maintains a directory at
`moongoose/fetch/fetchtypes/{sourcename}/`:

| Artifact | File |
|----------|------|
| Data dictionary | `DATA_DICTIONARY.md` |
| Guidance log | `GUIDANCE_LOG.md` |
| Workflow feedback | `WORKFLOW_FEEDBACK.md` |
| Dataset schema | `schema.yaml` (flavors, properties, relationships, attributes) |
| Go types/helpers | `models.go`, `helpers.go`, etc. |
| Streamer entry point | `moongoose/fetch/{sourcename}_streamer.go` |
| Registry entry | switch case in `moongoose/fetch/registry.go` |
| `Source` constant | `moongoose/fetch/fetchtypes/source.go` |
| Tests / fixtures | `*_test.go`, `testdata/*.pb.txt` |

#### Production deployment

Production fetch runs on **gcp-newgate** as a set of per-source
`gcp-fetch` Kubernetes Deployments (one `fetchInstance` per source),
configured via `charts/argocd-applications/values-{env}.yaml` and
deployed by ArgoCD. Each instance is a long-lived pod running the fetch
binary with a single `streams.yaml` stream entry pointing to the
source's raw and extract buckets.

#### Quality gates

The onboarding guide gates new sources behind:

- **`recordeval`** — validates `.binpb.zst` / `.pb.txt` output against
  the dataset schema and quality bar (zero schema errors, 100%
  citation coverage, zero empty records, etc.). Run early and often.
- **`schemacheck`** — flags inconsistencies (same name, different
  descriptions) between this source's `schema.yaml` and every other
  source's schema. Goal: a coherent cross-source vocabulary.
- **Deep Research reviews** — Gemini-driven reviews of the data
  dictionary and the extraction output. Up to two rounds each.
- **End-to-end eval stack** — ephemeral ingest + resolve + DB stack in
  `gcp-danger`, with `dbeval` over the result.

#### Three onboarding workflows

The guide distinguishes:

- **Workflow A — New Source.** External API → full lifecycle:
  explore, dictionary, GCS infra, code, validation, eval stack.
- **Workflow B — Modify Existing Source.** Code / schema changes plus
  validation; reuse the existing infrastructure.
- **Workflow C — Aggregation Config.** Source that reads from the
  existing KG and emits derived records back through the same ingest
  pipeline; no external API and no raw-data infrastructure.

### Implications for the CSV Sources product

Our product is a **fourth pattern** that the upstream onboarding guide
does not explicitly cover: an end-user-driven source whose input is
"whatever CSV you upload". The high-level contract — produce
`FetchMessage` records, land them somewhere the ingest service can
pick them up — has to be preserved. Everything underneath can (and per
your direction, will) diverge:

| Concern | Canonical fetch source | CSV Sources product |
|---------|------------------------|---------------------|
| Execution | Long-lived k8s Deployment on gcp-newgate, polling on a timer | **Cloud Run** (service for triggering, Job for atomization), running on demand per upload |
| Input | External HTTP API / TCP stream | **User CSV upload** through the Aether web app |
| `Download()` analogue | HTTP fetch, write JSON to shared raw bucket | Browser upload → web app server → write CSV to **our** GCS layout (TBD: per-tenant, shared with prefix, or per-source bucket) |
| `Extract()` analogue | No-op for structured sources | No-op (CSV is structured) — or a normalization pass (header detection, dialect sniff) |
| `Atomize()` analogue | Bespoke Go code per source emitting `FetchMessage` records | **Generic atomizer driven by user-defined column → flavor/property/relationship mapping** |
| Schema definition | Source-author-written `schema.yaml` checked into the lovelace repo | Per-source schema (TBD: fixed base vocabulary, per-source generated from mapping, or hybrid) |
| GCS infra | Terraform under gcp-newgate, fixed naming, shared raw bucket, per-source extract bucket | **Different model** — TBD; needs to fit the multi-tenant Broadchurch app pattern |
| Ingest hookup | GCS bucket notification → Pub/Sub → ingest service | TBD; cleanest path is to write into an ingest-watched bucket (existing or new) so the existing ingest service picks files up unchanged |
| Quality gates | `recordeval` + `schemacheck` + Deep Research + eval stack | Per-upload `recordeval` is the closest analogue; schema-level checks happen when we define our shipping vocabulary |

#### Hard constraints inherited from upstream

Regardless of how we implement the rest, our output has to satisfy the
canonical contract or ingest will reject it:

- Records use the **v2 proto fields only** (no deprecated `entity`,
  `flavor`, `int_val`, `bool_val`, `target_val`, etc.).
- `Record.Source` must be set; `Record.Subject` must be a populated
  `ProtoEntity` with `Flavor`, `Name`, and `FlavorResolverInformation`.
- `NamedEntityResolverInformation.Mergeability` must be `MERGEABLE` for
  real-world entities (organizations, people, locations, countries…)
  and `NOT_MERGEABLE` for passive source-specific entities.
- Every `Atom` needs a `Property` name, a non-zero `Timestamp`, a
  value, and `Citations` (verbatim source text — for us that means a
  reference back to the CSV row / column).
- All `FlavorResolverInformation`, `PropertyResolverInformation`, and
  `AttributeResolverInformation` mergeabilities are `NOT_MERGEABLE`.
- Every `FetchMessage` must carry the schema metadata maps
  (`flavor_metadata`, `property_metadata`, `relationship_metadata`,
  `attribute_metadata`) describing every element referenced in its
  records, or `recordeval` will treat missing entries as errors.

These constraints fall out of `fetchapi.proto` and the validator
behavior; they're non-negotiable and will shape both our atomizer and
our mapping UI.

### Existing Broadchurch fetch source prototype

_(notes from reviewing the prototype: location, behavior, infra,
reuse vs. rebuild — TODO)_

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
