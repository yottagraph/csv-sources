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

- [x] **`fetch-support` location & dialect stability (answered by PR
      #9935).** `fetch-support` is implemented in
      [Lovelace-AI/lovelace#9935](https://github.com/Lovelace-AI/lovelace/pull/9935)
      ("Isolated-fetch prototype", branch `will/isolated-fetch-design`,
      open, +2554 lines, mergeable but `behind main`). It lives at
      `moongoose/cmd/fetch-support/` in that branch and is **local-only
      in P0** — the PR explicitly does **not** deploy it. The v0
      dialect is documented in `moongoose/cmd/fetch-support/api/README.md`
      and codified in `api/types.go`; the prototype's
      `internal/erc20/json.go` is a faithful mirror, so the dialect we
      already documented is correct and current. **See "Lovelace-side
      dependency: the `fetch-support` service" below.**

- [ ] **`fetch-support` deployment plan** — to go to production we
      need a reachable, authenticated `fetch-support` endpoint. The
      P1 plan in PR #9935's
      `experimental/will/isolated_fetch/project-plan.md` calls for:
      - promoting `fetch-support` from local-only to a deployed
        service on **gcp-newgate** (Helm chart, ArgoCD app, TF
        callsite, behind caddy-mcp),
      - adding **Auth0 `client_credentials`** enforcement via the
        existing M2M minter with a new `audience=fetch-services`,
      - switching the publish backend from local FS to GCS with a
        per-environment publish bucket.
      Options for us, in order of preference:
      1. **Land PR #9935, then do P1 deploy, then build CSV Sources
         on top.** Cleanest. Aligns with the upstream plan.
      2. **Land PR #9935, then run our own private `fetch-support`
         Cloud Run instance in the broadchurch project** (build the
         binary, push the image, deploy alone). Faster to unblock us
         but creates a parallel deploy of a service that should be
         centralized.
      3. **Don't merge PR #9935; just run `fetch-support` locally**
         during CSV Sources dev. Fine for design + dev. Can't ship.
      **Pending decision from you** — see "Lovelace-side dependency"
      below for the trade-offs.

- [x] **Schema registration (answered by PR #9935).** `fetch-support`
      loads schemas from a `--schemas-dir` at startup — every
      `*.yaml` is parsed as `dataschema.DatasetSchema` and keyed by
      the `name` field. **P0 mechanism is to mirror our
      `schema.yaml` into `fetch-support`'s `--schemas-dir`** (a
      filesystem deploy concern, not a runtime API). P1 plan
      (project-plan.md) discusses either a `POST /fetch/schemas/{source}`
      upload endpoint or a `schema_yaml` field on each
      `PublishRequest`; both are designed but not yet implemented.

- [ ] **Schema sync workflow** — even given P0 mirroring, we still
      need an operational answer: where does the canonical
      `csv-sources/schema.yaml` live, how do we get it into the
      deployed `fetch-support`'s schemas dir, and how do schema
      changes propagate (PR to the lovelace repo? a CI job? a manual
      copy?). Tied to the deployment-plan decision above.

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
**Last updated:** 2026-05-26 (added `fetch-support` service findings from PR #9935 and landing-order strategies)

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

### Lovelace-side dependency: the `fetch-support` service

> **Source:** [`Lovelace-AI/lovelace#9935`](https://github.com/Lovelace-AI/lovelace/pull/9935)
> ("Isolated-fetch prototype", branch `will/isolated-fetch-design`,
> open since 2026-05-06, +2554 lines, mergeable but `behind main`).
> Read in this design: `docs/designs/isolated-fetch.md` (590 lines —
> the umbrella architecture doc),
> `experimental/will/isolated_fetch/project-plan.md` (236 lines — the
> roadmap), and the entire `moongoose/cmd/fetch-support/` directory
> (`README.md`, `api/README.md`, `api/types.go`, `main.go`,
> `handler.go`, `schemastore.go`, `translator.go`, `testdata/`).

This PR is the **umbrella architecture** behind the
`lovelace-fetch-erc20` prototype. It introduces:

1. A formal **"Isolated Fetch" design** (`docs/designs/isolated-fetch.md`)
   that frames customer-side data sources as "zero access or visibility
   to the core Lovelace codebase". Codifies ten Decision points
   (D1–D10) including: customer code runs in the customer's GCP
   project (D1); Auth0 `client_credentials` for HTTP M2M auth (D2);
   wire format stays `FetchMessage` `.binpb.zst` (D4); customer-side
   language is open / any-language (D6); P0 omits all deploy infra
   (D8).
2. The **`moongoose/cmd/fetch-support` HTTP service** itself —
   ~320 lines of translator + ~136 lines of handler + ~82 lines of
   schema store + main, plus golden tests. **`api/README.md` and
   `api/types.go` are the canonical v0 dialect spec**, and they
   match the prototype's mirror exactly (i.e. our documented dialect
   is correct).
3. A **project plan** with explicit P1 work for deploying
   `fetch-support` and the supporting Auth0 / GCS infra.

#### What `fetch-support` is

A Go HTTP service that exposes two endpoints:

| Endpoint | Behavior |
|----------|----------|
| `POST /fetch/publish` | Accepts a v0 dialect `PublishRequest`, looks up the schema by `source`, runs `Translate` (dialect → `FetchMessage` proto, typing props/attrs per schema, building flavor / property / relationship / attribute metadata maps), runs `dataschema.Validator.ValidateFetchMessage` (with the system schema merged in), writes a `.binpb.zst` to `{extract-store}/{pipeline-or-source}/{YYYY-MM-DD}/{key}.binpb.zst`. Returns `{uri, records}` on success, 400 on validation failure, 500 on storage error. |
| `GET /healthz` | Returns 200 `ok`. |

Configuration (via CLI flags on the binary):

```
fetch-support
  --listen=:8080                                    # HTTP listen address
  --extract-store=gs://...   OR  file:///abs/path   # where .binpb.zst lands
  --schemas-dir=/path/to/schemas                    # *.yaml schema files loaded at startup
```

The translator is the heart of the service — it owns every piece of
proto-level complexity our customer code would otherwise have to
solve: setting `Record.Source`, building `ProtoEntity` subjects with
the right `Flavor` / `Name` / `StrongIds` / `Aliases`, applying
schema-derived mergeability (`MERGEABLE` for real-world flavors,
`NOT_MERGEABLE` for passive ones), creating one `Atom` per property
and one per link target, copying `Citation` / `SourceDownloadTimestamp`
through to the `FetchMessage`, and building the four metadata maps
the validator requires.

#### Status (per the PR and project plan)

- **PR state:** open since 2026-05-06, `behind main`, mergeable.
  Author is `will-at-lovelace` (you). 17 files changed, +2554 -0
  (one file modified is `moongoose/fetch/fetchlib/BUILD` for
  visibility; everything else is new).
- **P0 (in this PR) is "build & run locally; no deploy"** — the
  service binary builds today, has golden tests, and is intended to
  be run by a developer on their laptop alongside a local customer
  app. No Helm chart, no ArgoCD config, no Auth0 middleware (the
  flags are wired conceptually but enforcement is P1), no production
  GCS bucket assignment.
- **P1 (planned in `project-plan.md`, not yet in flight)** brings
  the deploy:
  - Promote `fetch-support` to a deployed service on **gcp-newgate**
    (Helm chart in `prod/apps/`, ArgoCD app, TF callsite, behind
    caddy-mcp).
  - Add Auth0 `client_credentials` Bearer auth using existing
    `mcplib` middleware, with a new `audience=fetch-services` in the
    M2M minter config.
  - Switch the publish backend to a per-environment GCS bucket.
  - Optionally wrap `recordeval` for hosted validation diagnostics
    returned inline on the publish response.
  - Public Bearer-auth front-end on
    `POST /ingest/addGlobRequest` so glob registration doesn't need
    an FDE in the loop.
- **Open questions blocking promotion** (also in `project-plan.md`):
  bucket ownership for outputs (customer-owned vs Lovelace-owned),
  deploy target choice, public auth on glob registration, source
  registry catalog, customer secret store choice, schema sync model
  (`--schemas-dir` mirror vs upload endpoint vs `schema_yaml` on
  request).

#### Why this matters for CSV Sources

`fetch-support` is the **only** Lovelace-side service our app has to
talk to in steady-state. **It is the dependency.** Without it
running somewhere reachable and authenticated, our extract Cloud Run
service has nothing to POST to and no data lands in the KG.

This drives the **landing order** for the whole project:

1. **PR #9935 merges into `lovelace` `main`.** Currently `behind
   main`; needs a rebase. Pure additions in new files (apart from
   one `+1 -0` BUILD visibility line), so the rebase should be
   clean.
2. **`fetch-support` P1 deploy work happens** (gcp-newgate Helm /
   ArgoCD / TF, Auth0 audience, M2M client wiring, production GCS
   bucket). Most of this is documented in
   `experimental/will/isolated_fetch/project-plan.md § Next — P1`.
3. **Broadchurch / CSV Sources picks up the deployed URL + Auth0
   client_credentials** and we go end-to-end.

Three viable strategies for us, in increasing order of "ship it
fast at the cost of doing it twice":

| Strategy | Pros | Cons |
|----------|------|------|
| **A. Land the upstream P1 first.** Get PR #9935 merged, do the gcp-newgate deploy, then build CSV Sources on top. | Single source of truth. Reuses the planned audience / minter / bucket. No duplicated service. | Couples our timeline to upstream P1 work; could be weeks of unrelated infra. |
| **B. Run a private `fetch-support` in the broadchurch project.** Land PR #9935, then build the binary, push to broadchurch's Artifact Registry, deploy as a Cloud Run service alongside our extract service. Use a private Auth0 client, or no auth on a VPC-internal ingress. | Unblocks us today. Same code as upstream, just hosted differently. | Two deployed `fetch-support`'s long-term unless we migrate. Extra IAM / DNS / monitoring to babysit. Schema sync goes through us, not the central deploy. |
| **C. Run `fetch-support` locally only.** Build and run on a developer laptop during CSV Sources dev. Use `file://` for the extract store; no IngestNG. | Zero deploy friction; perfect for design + dev iteration. | Can't ship to production. Can't validate the full KG round-trip. |

**Strong default:** Strategy A if the upstream P1 work is on a
reasonable timeline (weeks not months), otherwise Strategy B with an
explicit plan to migrate to the central deploy when it lands.
Strategy C is what we'll use during dev regardless.

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
