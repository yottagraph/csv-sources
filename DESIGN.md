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
- [x] **Review Broadchurch fetch source prototype** — read
      [`Lovelace-AI/lovelace-fetch-erc20`](https://github.com/Lovelace-AI/lovelace-fetch-erc20)
      end-to-end (README, all source under `cmd/`, `internal/erc20/`,
      `schema.yaml`, `tf/main.tf`, `cloudbuild.yaml`). Findings captured
      in "Prototype: lovelace-fetch-erc20" and the deltas with the
      canonical design captured in "Adapting the prototype to CSV
      Sources" below. **This dramatically simplifies our problem** —
      see those sections for why (short version: customer code never
      touches FetchMessage protos; it POSTs JSON to a server-side
      `fetch-support` service that handles the proto/validation/
      ingest-bucket side).

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

> **Major update after reviewing the prototype:** several earlier
> questions are now answered — the prototype establishes a clear
> contract (POST v0 dialect JSON to a `fetch-support` service) and a
> clear architecture (Cloud Run Job for download + Cloud Run Service
> for extract, both Go, both isolated from the lovelace monorepo). The
> revised plan below reflects that.

- [ ] **Repo structure for the data source backend** — the prototype is
      a separate repo with its own `go.mod`, stock Go toolchain, no
      Bazel, and a clean isolation from the lovelace monorepo. The
      three viable options for us are:

      1. **Monorepo, separate package.** Add `fetch-source/` (or
         similar) as a top-level directory in this repo with its own
         `go.mod`, mirroring the prototype's layout 1:1
         (`cmd/{download,extract,devrun}`, `internal/csv/`,
         `schema.yaml`, `Dockerfile.*`, `cloudbuild.yaml`, `tf/`).
         Aether app stays at repo root. **Recommended starting point**
         — keeps related design + code together, avoids a second repo
         to clone/PR against, and the toolchains are naturally
         separated by directory.
      2. **Separate repo** (e.g. `lovelace-fetch-csv-sources` under
         `Lovelace-AI`). Exactly mirrors the prototype's convention,
         clean toolchain separation, but adds friction (two repos to
         keep in lock-step).
      3. **Inside `jobs/` and a new `services/` subdirectory.** Aether
         already has `jobs/` (conventionally Python ADK) and
         `mcp-servers/`. Adding Go here would be inconsistent with the
         template's conventions.

      **Pending decision.** See "Adapting the prototype to CSV Sources
      § Repo structure" below for the trade-off discussion.

- [x] **Ingestion architecture (answered by the prototype).** The
      pattern is: persist raw to a `-raw` GCS bucket → Eventarc fires
      on `object.finalized` → Cloud Run extract service translates raw
      → v0 dialect JSON → POSTs to `fetch-support` `/fetch/publish` →
      `fetch-support` writes the `.binpb.zst` to the ingest-watched
      extract bucket and `ingestng` picks it up. **We adopt this
      end-to-end.** Our only customization: the "download" step is a
      user CSV upload from the Aether app, not a polled external API.

- [x] **FetchMessage production (answered by the prototype).**
      **Customer code does NOT touch FetchMessage protos.** Our
      service POSTs v0 dialect JSON (`PublishRequest{records: [...]}`)
      with simple `Record`/`Link` shapes — `fetch-support` server-side
      translates dialect → protos, applies mergeability rules,
      validates against `schema.yaml`, builds the metadata maps, and
      writes the `.binpb.zst` file. Our work is just "produce correct
      dialect JSON".

- [x] **Ingest hookup (answered by the prototype).** We do not write
      into the ingest extract bucket directly. We POST to
      `fetch-support`, and it owns writing into the extract bucket
      and registering the ingest glob.

- [ ] **`fetch-support` deployment & endpoint** — the prototype README
      links to `moongoose/cmd/fetch-support/api/README.md` in the
      lovelace monorepo, but that path does not exist on `main` yet
      (as of this research). We need to confirm with you:
      (a) where `fetch-support` lives today (branch / repo / deployed
      URL), (b) whether the v0 dialect is stable enough to commit
      against, and (c) whether the Broadchurch tenant has Auth0 (or
      other) credentials wired to call it.

- [ ] **Schema registration** — the prototype ships a `schema.yaml`
      that has to match what `fetch-support` knows. **Open question:**
      how do we register our `schema.yaml` with `fetch-support`? Does
      it pull schemas from a known location, or do we hand it the
      file at deploy time?

- [ ] **Storage layout (CSV-specific)** — where exactly do raw CSVs
      live in GCS? Options:
      - **Per-app-instance bucket** (e.g. `{project}-csv-sources-raw`)
        — mirrors the prototype, single bucket for everything.
      - **Per-tenant prefix in a shared bucket** — easier multi-tenant
        story for Broadchurch if the app is reused across tenants.
      - **Per-tenant bucket provisioned by the Broadchurch portal** —
        cleanest isolation, but heavier provisioning.
      Pending the broader product discussion. For P0 the prototype's
      single-bucket pattern is fine.

- [ ] **Download stage role in our world** — in the prototype,
      `cmd/download` actively polls an external API. For CSV uploads
      our "download" is the user upload. Two reasonable shapes:
      (a) **No Cloud Run Job at all.** The Aether server-side upload
      handler writes the CSV directly to the raw bucket; Eventarc
      takes it from there. Simplest.
      (b) **Cloud Run Job for `From URL` uploads.** Keep a
      `cmd/download` that can fetch a CSV from an arbitrary HTTPS
      URL (or a GCS URL) and write it to the raw bucket, so power
      users can pull from existing data publishers without uploading
      bytes through the browser. Optional, P1.

- [ ] **Extract as Service vs. Job** — prototype uses a Cloud Run
      Service (because Eventarc → HTTP). For large CSVs (10s of MBs +)
      we may want the Service to enqueue a Cloud Run Job and return
      immediately, so we don't hit request timeouts. P0 can use the
      Service directly; revisit when we know our file-size envelope.

- [ ] **Dataset schema strategy** — same question as before, but now
      narrower: do we ship a single `schema.yaml` defining a fixed
      vocabulary the CSV mapping UI exposes, or generate a per-source
      `schema.yaml` from each user mapping and register it with
      `fetch-support` at upload time? P0 default: **one shipped
      schema** with a useful starter vocabulary; per-source dynamic
      schemas are a clear P1.

- [ ] **Source identity model** — open. Easiest: one `source: "csv"`
      with a `pipeline` per user-defined source (the dialect already
      carries `pipeline`). Alternative: each user-defined source is a
      separately-registered "source" inside `fetch-support`. P0
      default: single `source` constant, per-source `pipeline` value.

- [ ] **Quality gates (per-upload validation)** — the prototype relies
      on `fetch-support` returning errors when records fail schema
      validation. We should surface those errors in the upload UI
      (show: "row N column X failed — reason"). We do not need to run
      `recordeval` ourselves at upload time; we trust the server-side
      validation. `schemacheck` runs against our shipping schema at
      development time.

- [ ] **Server endpoints** — enumerate `server/api/**` routes (upload
      CSV, list sources, get mapping, update mapping, trigger
      publish, fetch run history, delete source).

- [ ] **Pages / UX surfaces** — enumerate pages (sources list, source
      detail, new upload wizard, mapping editor, run history /
      validation error inspector).

- [ ] **Agents / MCP servers** — decide whether any of this needs an
      ADK agent (e.g. for AI-assisted column mapping) or an MCP server
      (e.g. exposing CSV sources to other agents). Default: none until
      we identify a concrete need.

- [ ] **Deployment plan** — Aether web app to Vercel on push to
      `main`. Go data source backend built by Cloud Build (per
      prototype's `cloudbuild.yaml` pattern), images pushed to
      Artifact Registry, deployed via Terraform under `tf/`. Cross-
      project IAM (broadchurch project → lovelace fetch-support) is
      P1 per the prototype's stub. Register Cloud Run resources under
      `broadchurch.yaml` if the portal needs to know about them
      (TBD).

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
**Last updated:** 2026-05-26 (added Broadchurch prototype findings + Adapting the prototype to CSV Sources)

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

> **Source:** [`Lovelace-AI/lovelace-fetch-erc20`](https://github.com/Lovelace-AI/lovelace-fetch-erc20)
> on `main`. Self-described in the README as "the P0 worked example
> for the Isolated Fetch design". The Isolated Fetch design doc and
> the `fetch-support` API README it cross-links to are not yet on
> `lovelace`'s `main` branch — that machinery appears to be ahead of
> docs. We're treating the prototype's own code as the canonical
> reference for now.

#### One-paragraph summary

The prototype is a **customer-side**, **monorepo-isolated** data
source for ERC-20 token transfers. It runs entirely on the customer's
GCP project as two Cloud Run components plus a GCS raw bucket; it
talks to the lovelace platform exclusively through a single HTTP
endpoint (`POST /fetch/publish` on a server-side `fetch-support`
service) using a small JSON dialect. **It does not import any code
from the lovelace monorepo, does not use Bazel, does not produce
FetchMessage protobufs, and does not write to the ingest extract
bucket directly.** All of that complexity is server-side, behind the
`fetch-support` HTTP boundary.

#### Components

| Component | Type | Trigger | Role |
|-----------|------|---------|------|
| `cmd/download` | Cloud Run **Job** | Cloud Scheduler (`0 * * * *`) | Polls an external API (ETH JSON-RPC for the prototype), writes one raw JSON file per chunk to a `-raw` GCS bucket. Maintains a checkpoint object in the same bucket. Exits when the chunk range is done. |
| `cmd/extract` | Cloud Run **Service** | Eventarc on GCS `object.finalized` on the raw bucket | Reads the raw JSON, parses it, optionally enriches addresses, builds a v0 dialect `PublishRequest`, POSTs to `fetch-support` `/fetch/publish`. Stateless per request. |
| `cmd/devrun` | Local CLI | Manual | Wraps both phases in-process against a `file://` raw store + a local `fetch-support` server, for end-to-end developer testing. |
| `internal/erc20/` | Library | — | Source-specific code: external API client (`rpc.go`, `download.go`), parsers (`extract.go`), the v0 dialect builder (`json.go`), the `Store` interface (`storage.go`, supports both `gs://` and `file://`), the publish HTTP client (`publish.go`), and enrichment (`enrich.go`). |
| `schema.yaml` | Static asset | — | Standard fetch-source dataset schema (flavors / properties / relationships / attributes / mergeability / strong_id_properties), identical in shape to the canonical lovelace `schema.yaml` files. |
| `tf/main.tf` | Terraform | `terraform apply` | GCS bucket, two Cloud Run components, two service accounts, Eventarc trigger, Cloud Scheduler job. P0 stub: missing Workload Identity, cross-project IAM, and Auth0 wiring. |
| `cloudbuild.yaml` + `Dockerfile.{download,extract}` | Cloud Build pipeline | `gcloud builds submit` | Builds the two Docker images via standard Go `distroless` build pattern, pushes to Artifact Registry. Does not deploy. |

#### The v0 publish dialect

This is the most important thing the prototype establishes — it's the
contract everything customer-side has to honor.

```jsonc
{
  "dialect_version": "v0",
  "source":         "erc20",                     // matches schema.yaml name
  "pipeline":       "erc20",                     // optional sub-namespace
  "key":            "12345000-12345010",         // unique batch key, used in extract filename
  "citation":       "https://etherscan.io/block/12345700",  // source pointer for provenance
  "downloaded_at":  "2026-05-12T17:00:00Z",      // RFC3339
  "records": [
    {
      "type":       "eth_address",               // flavor name from schema.yaml
      "key":        "0xfff0000000000000000000000000000000000001",
      "name":       "Treasury (USDC)",           // optional display name
      "aliases":    ["usdc-treasury"],           // optional
      "strong_id_property": "eth_address_id",    // optional
      "props":      { "eth_is_contract": 1.0 },  // property name → value (typed per schema)
      "links": {                                 // relationship name → list of targets
        "erc20_transfer": [
          {
            "type": "eth_address",               // target flavor
            "key":  "0x1110000000000000000000000000000000000002",
            "name": "Bob",                       // optional
            "attrs": {                           // attribute name → value (on the relationship)
              "txid":           "0xtxhash000000aaaa",
              "log_index":      "0",
              "block_number":   "12345700",
              "token_value":    200,
              "token_symbol":   "USDC",
              "token_contract": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
            }
          }
        ]
      },
      "timestamp": "2024-07-31T04:26:40Z"
    },
    // ...
  ]
}
```

The server returns `{ "uri": "<gs:// path to .binpb.zst>", "records": <count> }`
on success, non-200 on failure. The dialect is a thin, language-
agnostic projection of the canonical FetchMessage proto shape:
`source` / `pipeline` / `key` map to publish-file identity, `records`
collapses `Record.Subject` + atoms + relationships into a simpler
`{type, key, props, links, timestamp}` shape, and the server-side
`fetch-support` handles the proto translation, mergeability flags,
citation propagation, and schema-metadata-map generation. **None of
those proto-level details have to be solved customer-side.**

#### Data flow

```
external API ──HTTP──▶ cmd/download (Cloud Run Job, scheduled)
                              │
                              ▼ writes JSON
                       gs://{project}-erc20-raw/
                       erc20/download/{date}/erc20-{from}-{to}.json
                              │
                              ▼ object.finalized
                       Eventarc trigger
                              │
                              ▼ HTTP POST
                       cmd/extract (Cloud Run Service)
                              │
                              ▼ POST /fetch/publish (v0 JSON)
                       lovelace fetch-support service
                              │
                              ▼ writes .binpb.zst
                       gs://{...}-fetch-{source}/{pipeline}/{date}/{key}.binpb.zst
                              │
                              ▼ Pub/Sub notification
                       ingestng → knowledge graph
```

#### What is intentionally omitted in P0 (per the README)

- Workload Identity binding to `fetch-support`.
- Cross-project IAM grant from the customer project to the ingest
  extract bucket (we never need it directly — `fetch-support` writes
  there, but the trust path between the customer project SA and
  `fetch-support` still has to be set up).
- Auth0 `client_credentials` for Bearer auth at `--publish-url`
  (the flag exists, enforcement is P1).
- Retry/backoff for rate-limited downloads.
- Per-chunk metrics / tracing.

### Adapting the prototype to CSV Sources

This is the section that synthesizes the two preceding ones. Our
product is **the prototype's pipeline** + **an Aether web app** that
gives users a UI to feed CSVs into it.

#### Mapping the prototype's components to ours

| Prototype component | CSV Sources equivalent | Notes |
|---------------------|------------------------|-------|
| `cmd/download` (Cloud Scheduler-triggered Job polling an external API) | **The Aether app's CSV upload endpoint.** Server-side route in `server/api/uploads.post.ts` (or similar) takes the user's CSV and writes it straight to the raw bucket at `csv/uploads/{date}/{source}/{upload-id}.csv` (or analogous path). | Our "download" event _is_ the user upload. The Cloud Run Job role mostly disappears for P0. We might keep an _optional_ `cmd/download` later for "fetch a CSV from an HTTPS URL" (see TODO above). |
| GCS `-raw` bucket | **Same role, our naming.** E.g. `{project}-csv-sources-raw`. Storage layout: `csv/uploads/{date}/{source}/{upload-id}.csv` plus a sibling `mapping.json` so the extract service has everything it needs. | Per-tenant prefixing / bucket split is an open question (see TODO). |
| Eventarc on `object.finalized` | **Same role.** Triggers `cmd/extract` when a new upload lands. | Identical to the prototype. |
| `cmd/extract` (Cloud Run Service) | **Cloud Run Service that reads the uploaded CSV + its mapping, builds a v0 dialect `PublishRequest`, POSTs to `fetch-support`.** | Our `internal/csv/` library replaces `internal/erc20/`. The high-level structure (read raw → parse → dialect translator → POST) is identical. |
| `cmd/devrun` | **Same role.** A local CLI that orchestrates the upload + extract phases against a `file://` store and a locally-running `fetch-support`. | Useful for development without GCP credentials. |
| `internal/erc20/` package | **`internal/csv/` package.** CSV dialect detection, header handling, row parsing, mapping-driven dialect builder, `Store` interface (carbon copy of prototype's `storage.go`), publish HTTP client (carbon copy of prototype's `publish.go`). | The dialect builder is the only meaningful new code; the rest is straight from the prototype. |
| `schema.yaml` | **`schema.yaml`** for CSV Sources — defines the flavors / properties / relationships users can target through the mapping UI. | TBD whether one shipped schema or per-source dynamic schemas. |
| `tf/main.tf` | **`tf/main.tf` + extra** for: the raw bucket, both Cloud Run components, Eventarc, service accounts, IAM. Plus anything the Aether app needs that isn't on Vercel (probably nothing). | Cross-project IAM to `fetch-support` is the new piece relative to the prototype's stub. |
| `cloudbuild.yaml` | **`cloudbuild.yaml`** for the Go data source backend. | Mirrors the prototype 1:1. |

#### What the Aether app adds on top of the prototype

The prototype is a bare backend pipeline. CSV Sources adds:

1. **User identity & tenant isolation** via the Aether template's
   Auth0 + per-tenant Firestore wiring. User uploads carry the user
   identity and the tenant org id; per-source metadata (display name,
   mapping, run history) lives in tenant Firestore via `useAppPrefs`
   / `useAppFeaturePrefs`.
2. **The upload flow UI** — a wizard for picking a file, previewing
   parsed rows, mapping columns to schema vocabulary, seeing
   validation errors, and submitting.
3. **The "source" abstraction surface** — a sources list, source
   detail, per-source upload history, run/validation reports. These
   are pure Aether pages backed by per-tenant Firestore for metadata
   and the raw bucket for file blobs.
4. **The server-side upload endpoint** — a Nitro route in
   `server/api/**` that accepts the multipart upload, writes the
   bytes to the raw bucket, writes the mapping JSON alongside, and
   returns the upload id. Eventarc handles everything from there.
5. **Surfacing publish results** — the extract service writes its
   per-run outcome (records published, validation errors, upstream
   `fetch-support` response) somewhere readable by the Aether app
   (per-source GCS log file? Firestore document? both?) so the UI
   can show users what happened.

#### Repo structure

The prototype is a separate repo. Our app is more than a fetch
source, so a separate repo isn't a perfect fit. **Recommended P0:**
keep everything in this repo, with the Go data source backend in a
top-level `fetch-source/` directory that is **structurally identical
to the prototype**:

```
csv-sources/                           ← this repo
├── (Aether app at the root: nuxt.config.ts, pages/, components/, …)
├── package.json
├── server/                            ← Nitro server routes for the app
│   └── api/
│       ├── uploads.post.ts            ← multipart CSV upload → raw bucket
│       ├── sources.get.ts             ← list user's sources
│       └── ...
│
└── fetch-source/                      ← Self-contained Go subproject
    ├── go.mod                         ← independent Go module
    ├── go.sum
    ├── README.md
    ├── schema.yaml                    ← CSV Sources dataset schema
    ├── cmd/
    │   ├── download/                  ← (optional, P1) "from URL" puller
    │   ├── extract/                   ← Cloud Run Service: raw CSV → v0 JSON → fetch-support
    │   └── devrun/                    ← local orchestrator
    ├── internal/
    │   └── csv/
    │       ├── storage.go             ← gs:// + file:// Store (copy of prototype)
    │       ├── parse.go               ← CSV dialect detection, row iteration
    │       ├── mapping.go             ← mapping model + apply
    │       ├── publish.go             ← fetch-support HTTP client (copy of prototype)
    │       └── ...
    ├── Dockerfile.extract
    ├── Dockerfile.download            ← (only if we keep a download command)
    ├── cloudbuild.yaml
    └── tf/
        └── main.tf
```

Trade-offs:

- **+ Single source of truth for design** (`DESIGN.md` covers both
  sides; no jumping repos).
- **+ The Aether app and the data source backend evolve together** —
  changes to the dialect schema, mapping shape, or upload-payload
  contract can be a single PR.
- **+ Toolchains stay clean** — the Go subproject has its own
  `go.mod`, its own CI (separate GH Action / Cloud Build trigger),
  and is invisible to the Aether Vercel build because it's under a
  separate directory.
- **− Slight CI complexity** — we need a Go-only CI job for the
  `fetch-source/` directory and a separate Cloud Build trigger
  scoped to changes under that path.
- **− Vercel build needs to be told to ignore `fetch-source/`** so it
  doesn't try to install / build anything there. Trivial via
  `.vercelignore`.

The alternative (separate repo, like the prototype) is the cleaner
purist answer but adds a constant cross-repo coordination cost that
seems unnecessary while this is a single product. **Open question for
you:** do you want monorepo (Option 1) or two repos (Option 2)?

#### What carries over directly from the prototype

These pieces we should **copy almost verbatim** from
`Lovelace-AI/lovelace-fetch-erc20` and adapt only at the edges:

- `internal/erc20/storage.go` → `internal/csv/storage.go` — the
  `Store` interface and the `gs://` + `file://` implementations.
- `internal/erc20/publish.go` → `internal/csv/publish.go` — the
  `PublishClient` and its v0 dialect POST logic.
- `cmd/extract/main.go` — the Eventarc-triggered HTTP service shell
  (CloudEvents decoding, `/healthz`, `--once` mode for devrun).
- `cmd/devrun/main.go` — the local orchestrator structure.
- `Dockerfile.extract` / `Dockerfile.download` — distroless Go build.
- `cloudbuild.yaml` — build & push image pattern.
- `tf/main.tf` — Cloud Run + Eventarc + GCS bucket wiring (we add
  cross-project IAM to `fetch-support` and remove the
  `cmd/download` + Cloud Scheduler resources if we drop the
  download stage).

#### What's genuinely new for CSV Sources

The pieces that aren't in the prototype and we have to design:

1. **The Aether upload flow** — pages, components, server routes,
   per-tenant Firestore data model.
2. **The CSV parser + mapping engine** — `internal/csv/parse.go`,
   `internal/csv/mapping.go`. Has to handle realistic CSV dialect
   variation (Excel exports, BOMs, quoted commas, dates in mixed
   formats, etc.).
3. **The dialect builder driven by user mapping** — translates `(CSV
   row, mapping)` into a list of v0 dialect `Record`s. The
   prototype's equivalent (`internal/erc20/json.go`
   `BuildPublishRequest`) is fully _domain-specific_; ours has to
   be _generic_, driven by the mapping configuration.
4. **The mapping configuration model** — the JSON / YAML schema for
   "this column is the entity name; that column is a property of
   type X; this column is a relationship target keyed by Y", plus a
   UI to author it.
5. **Validation error surfacing** — fetch-support returns
   validation errors; we need to capture them, persist them, and
   show them in the Aether UI.
6. **Per-tenant identity flowing through to provenance** — the
   `citation` field in the dialect should point back to "user X,
   tenant Y, upload Z, row N".

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
