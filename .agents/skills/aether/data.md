# Data — Elemental API (platform data source)

**This app is built on the Lovelace platform.** The Query Server is the
primary data source — use it first for any data needs (entities, news,
filings, sentiment, relationships, events). Do NOT call external APIs
(e.g. sec.gov, Wikipedia) for data that the platform already provides.

Tenant-owned analytical data (event streams, derived tables, time-series
features that Cloud Run Jobs write into the tenant project) lives in
BigQuery, not the Elemental API. For that see [`bigquery.md`](bigquery.md)
— and importantly, do NOT add `@google-cloud/bigquery` or any GCP
credentials to this app. Queries go through the portal gateway.

The Elemental API provides access to the Lovelace Knowledge Graph through
the Query Server. Use it to search for entities, retrieve properties,
explore relationships, and analyze sentiment. New data sources are added
regularly — use the discovery-first pattern to find what's available.

## Skill Documentation

For endpoint reference, response shapes, and edge cases, **read the
elemental-api skill** in `.agents/skills/elemental-api/` (start with `SKILL.md` and
follow the skill’s own structure). Files are copied from
`@yottagraph-app/aether-instructions` (installed during project init). If
the directory is missing, run `/update_instructions` to install it.

## Data model skill

For Lovelace **entity types, properties, relationships, and per-source schemas** (EDGAR, FRED, FDIC, etc.), read the **data-model skill** in `.agents/skills/data-model/`. Start with `SKILL.md`, then `overview.md` and the source-specific folders. Both skills are distributed via `@yottagraph-app/aether-instructions` and installed during project init.

## Test Before You Build

**ALWAYS test data access before writing application code.** The Elemental
API has response shapes that differ from what the TypeScript types suggest,
and assumptions about nesting, property formats, and field names will be
wrong without testing.

### Step 1: MCP tools (interactive exploration)

**If MCP tools appear in your tool list, start here.** MCP handles entity
resolution, PID lookups, and NEID formatting automatically — use it to
verify what data exists and how it's structured.

```
elemental_get_schema()                          → list all entity types
elemental_get_schema(flavor="article")          → properties for a type
elemental_get_entity(entity="Apple")            → resolve + fetch entity
elemental_get_related(entity="Apple",
    related_flavor="person")                    → follow relationships
```

MCP tells you the correct flavor IDs, property IDs, and data shapes. Use
these to inform your REST implementation.

**Verify MCP is working with known-good queries:**

```
elemental_get_schema()                          → should return flavors + properties
elemental_get_entity(entity="Microsoft")        → should resolve to a company
elemental_get_entity(entity="Apple Inc")        → another known entity
elemental_health()                              → server health check
```

**Interpreting MCP errors — do NOT assume the server is broken:**

- `entity not found` or 404 in entity lookup → the entity doesn't exist
  in the knowledge graph, not a connectivity problem. Try a different entity.
- `failed to get property values: 404` → the entity was resolved but has
  no data for those properties. The MCP server is working correctly.
- Schema calls succeed but entity calls fail → data is sparse for that
  entity type. Try well-known entities (Microsoft, Apple Inc, JPMorgan).
- If `elemental_health()` fails → actual connectivity problem.

**Key insight:** A 404 from an MCP entity/property call means "not found,"
not "server broken." Always test with known entities before concluding
the server is down.

### Step 2: curl (verify exact request/response shapes)

MCP doesn't cover every REST endpoint (e.g. `/elemental/find` expressions).
Test those with curl before implementing them in code.

The gateway proxy authenticates on your behalf — no Auth0 tokens needed.
Read `broadchurch.yaml` for the three values you need:

| YAML path            | Purpose                              |
| -------------------- | ------------------------------------ |
| `gateway.url`        | Portal Gateway base URL              |
| `tenant.org_id`      | Your tenant ID (path segment)        |
| `gateway.qs_api_key` | API key (sent as `X-Api-Key` header) |

Build the request URL as `{gateway.url}/api/qs/{tenant.org_id}/{endpoint}`
and include the header `X-Api-Key: {gateway.qs_api_key}`.

```bash
# Variables — read these from broadchurch.yaml
GW="https://broadchurch-portal-194773164895.us-central1.run.app"
ORG="org_abc123"
KEY="qs_..."

# Search for an entity by name
curl -s "$GW/api/qs/$ORG/entities/search" \
  -X POST -H "Content-Type: application/json" \
  -H "X-Api-Key: $KEY" \
  -d '{"queries":[{"queryId":1,"query":"Microsoft"}],"maxResults":3}'

# Test a find expression
curl -s -X POST "$GW/api/qs/$ORG/elemental/find" \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'expression={"type":"is_type","is_type":{"fid":12}}' \
  --data-urlencode 'limit=5'

# Get entity properties (form-encoded)
curl -s -X POST "$GW/api/qs/$ORG/elemental/entities/properties" \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'eids=["00416400910670863867"]' \
  --data-urlencode 'pids=[8,313]' | jq .
```

`/elemental/find` and `/elemental/entities/properties` require
`application/x-www-form-urlencoded` with JSON-stringified parameter values.
All other endpoints accept `application/json`.

**Interpreting errors:** 400 = expression syntax is wrong. 500 = expression
is valid but the query failed (wrong PID, unsupported operator for that
property type). 200 + empty `eids` = query worked but no results match.
404 from entity/property endpoints = entity or data doesn't exist (not a
server error). Always test with known entities (e.g. search for "Microsoft")
before assuming the API is broken.

### Step 3: Implement with confidence

Now write your composable or server route, knowing the exact API shapes.

## Pre-Built Helpers

The template includes composables and utilities that handle common
Elemental API patterns. **Use these instead of writing from scratch:**

### `useElementalSchema()` — Schema Discovery with Caching

```typescript
const { flavors, properties, flavorByName, pidByName, refresh } = useElementalSchema();
await refresh(); // fetches once, then cached
const articleFid = flavorByName('article'); // → string | null
const namePid = pidByName('name'); // → string | null
```

Handles the dual response shapes (`res.schema.flavors` vs `res.flavors`)
and the `fid`/`findex` naming inconsistency automatically.

### `utils/elementalHelpers` — Gateway URL Helpers

```typescript
import {
    buildGatewayUrl,
    getApiKey,
    padNeid,
    searchEntities,
    getEntityName,
} from '~/utils/elementalHelpers';

const url = buildGatewayUrl('entities/search'); // full gateway URL
const key = getApiKey(); // from runtimeConfig
const neid = padNeid('4926132345040704022'); // → "04926132345040704022"

const results = await searchEntities('Microsoft'); // batch name search
const name = await getEntityName(neid); // display name lookup
```

## Client Usage

All API calls go through `useElementalClient()` from `@yottagraph-app/elemental-api/client`.
Auth tokens and base URL are configured automatically by the `elemental-client` plugin.

```typescript
import { useElementalClient } from '@yottagraph-app/elemental-api/client';

const client = useElementalClient();

const schema = await client.getSchema();
const entities = await client.findEntities({
    expression: JSON.stringify({
        type: 'comparison',
        comparison: { operator: 'string_like', pid: 8, value: 'Apple' },
    }),
    limit: 5,
});
```

### Client Method Quick Reference

All methods return data directly and throw on non-2xx responses.

**Entity search and lookup:**

| Method         | Signature                  | Purpose                                 |
| -------------- | -------------------------- | --------------------------------------- |
| `findEntities` | `(body: FindEntitiesBody)` | Expression-based search (see `find.md`) |

> **Entity search**: Use `findEntities()` with `string_like` on the name PID
> for name-based searches, or call `POST /entities/search` directly via
> `$fetch` for batch name resolution with scored ranking (this endpoint is
> not wrapped by the generated client).

> **Entity name lookup**: To get an entity's display name from its NEID,
> call `GET /entities/{neid}/name` directly via `$fetch` (not on the
> generated client). Returns `{"name": "..."}`. For all other entity
> data, use `getPropertyValues()`.

**Properties and schema:**

| Method              | Signature                                | Purpose                                                                              |
| ------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------ |
| `getSchema`         | `()`                                     | All entity types (flavors) and properties (PIDs)                                     |
| `getPropertyValues` | `(body: { eids: string, pids: string })` | Property values (eids: JSON array of NEID strings; pids: JSON array of numeric PIDs) |
| `summarizeProperty` | `(pid: number)`                          | Summary stats for a property                                                         |

**Relationships and graph:**

| Method         | Signature                        | Purpose                                                      |
| -------------- | -------------------------------- | ------------------------------------------------------------ |
| `findEntities` | `(body: { expression, limit? })` | Find linked entities via `linked` expression (see `find.md`) |

**Other:**

| Method       | Signature                | Purpose                        |
| ------------ | ------------------------ | ------------------------------ |
| `getHealth`  | `()`                     | Health check                   |
| `getStatus`  | `()`                     | Server status and capabilities |
| `adaMessage` | `(body: AdaMessageBody)` | Ada AI chat                    |

## Discovery-First Pattern

The knowledge graph contains many entity types and properties, and new datasets
are added regularly (e.g. Edgar filings, financial data). Do NOT hardcode entity
types or property names. Instead, discover them at runtime:

1. **Get the schema** — `client.getSchema()` returns all entity types (flavors)
   and properties (PIDs) available in the system. See `schema.md`.

    The schema response contains:
    - **Flavors** (entity types): Company, Person, GovernmentOrg, etc.
      Each flavor has a numeric ID and a human-readable name.
    - **PIDs** (properties): name, country, industry, lei_code, etc.
      Each PID has a type (`data_str`, `data_int`, `data_nindex`, etc.).
    - Properties with type `data_nindex` are references to other entities —
      resolve them with another `getPropertyValues` call.

    Use flavor names in `findEntities()` expressions and PID names in
    `getPropertyValues()`.

2. **Search with expressions** — `client.findEntities()` uses a JSON expression
   language to search by type, property value, or relationship. See `find.md`.
3. **Get property values** — `client.getPropertyValues()` fetches property data
   for specific entities.

This pattern lets agents work with any dataset without needing hardcoded
knowledge of what's in the graph.

## Semantics-First Data Handling

For reliable agent behavior, prefer typed semantics over string heuristics:

- **Use canonical endpoints/tools for each domain.** Example: fetch events
  from event APIs (`elemental_get_events` / event endpoints), not by scanning
  unrelated property names for words like "event" or "filing".
- **Treat reference-typed properties as links, not display text.** For
  relationship/reference values (`data_nindex` and similar), resolve linked
  entities before presenting user-facing output.
- **Interpret 404s as data absence first.** A 404 on entity/property lookups
  usually means "not found in current data," not transport failure. Validate
  connectivity separately (for example, with health endpoints).

## API Gotchas

### `getSchema()` response structure differs by endpoint

There are two schema endpoints with **different response shapes**:

| Endpoint                         | Flavors at                    | Flavor ID field | Detail level                         |
| -------------------------------- | ----------------------------- | --------------- | ------------------------------------ |
| `GET /schema`                    | top-level (`res.flavors`)     | `findex`        | Rich (display names, units, domains) |
| `GET /elemental/metadata/schema` | nested (`res.schema.flavors`) | `fid`           | Basic (name + type only)             |

The TypeScript client's `getSchema()` calls `/elemental/metadata/schema`,
so the response nests data under `.schema`. The generated types may suggest
top-level access, but it won't work at runtime.

```typescript
// WRONG — will crash (data is nested under .schema):
const res = await client.getSchema();
const props = res.properties; // undefined!

// CORRECT — always use fallback to handle both shapes:
const res = await client.getSchema();
const properties = res.schema?.properties ?? (res as any).properties ?? [];
const flavors = res.schema?.flavors ?? (res as any).flavors ?? [];
```

### Flavor ID field: `fid` vs `findex`

The flavor identifier has **different field names** depending on the endpoint:
`GET /schema` returns `findex`, `/elemental/metadata/schema` returns `fid`.
Same value, different key. Always use a fallback:

```typescript
const articleFlavor = flavors.find((f) => f.name === 'article');
// Always use String() — safe for small IDs (12) and required for large ones
const articleFid = String(articleFlavor?.fid ?? articleFlavor?.findex ?? '');

// When building a FID lookup map:
const fidMap = new Map(flavors.map((f) => [String(f.fid ?? f.findex), f.name]));
```

The `is_type` expression in `/elemental/find` always uses the `fid` key
regardless of which schema endpoint provided the value.

### Some FIDs and PIDs are 64-bit -- `JSON.parse` will silently corrupt them

FIDs and PIDs are stored as 64-bit signed integers. Many are small
(e.g. `12`), but others exceed JavaScript's `Number.MAX_SAFE_INTEGER`
(2^53 - 1) -- for example, `3466547124233281063`. `JSON.parse` silently
rounds these large values (that example becomes `3466547124233281000`). An `is_type` query with
the rounded FID returns empty results and no error, making it look like
the data doesn't exist.

**Always treat FIDs and PIDs as strings in TypeScript/JavaScript.**
Before `JSON.parse`, rewrite large numeric `fid`/`pid` fields to
quoted strings. Store them as `string`, not `number`. Build expressions
and `pids` arrays via string interpolation, not `JSON.stringify` of a
JS number. This is safe for small IDs too.

### Relationship property values need zero-padding to form valid NEIDs

Relationship properties (`data_nindex`) return linked entity IDs as raw
numbers (e.g. `4926132345040704022`). These must be **zero-padded to 20
characters** to form valid NEIDs. This is easy to miss and causes silent
failures — `getPropertyValues` returns empty results and
`/entities/{neid}/name` returns a 404.

```typescript
// WRONG — raw value is NOT a valid NEID:
const filingId = res.values[0].value; // "4926132345040704022" (19 chars)

// CORRECT — always pad to 20 characters:
const filingNeid = String(res.values[0].value).padStart(20, '0'); // "04926132345040704022"
```

> **WARNING -- `getPropertyValues()` takes JSON-stringified arrays**: The `eids`
> and `pids` parameters must be JSON-encoded strings, NOT native arrays. The
> TypeScript type is `string`, not `string[]`. Passing a raw array will silently
> return no data.

> **WARNING -- PIDs are numeric IDs, not string names.** Property IDs (PIDs)
> are integers, not human-readable names. `pids: JSON.stringify(['name'])`
> will fail — use `pids: JSON.stringify([8])` (where 8 is the PID for "name"
> from `getSchema()`). Always call `getSchema()` first to discover the
> numeric PID for each property.

```typescript
// WRONG — PIDs are numbers, not strings:
const values = await client.getPropertyValues({
    eids: JSON.stringify(['00416400910670863867']),
    pids: JSON.stringify(['name', 'country', 'industry']), // FAILS
});

// CORRECT — use numeric PIDs from getSchema():
const values = await client.getPropertyValues({
    eids: JSON.stringify(['00416400910670863867']),
    pids: JSON.stringify([8, 313]), // 8=name, 313=country (from schema)
});
```

### Traversing relationships: graph-layer vs property-layer entities

The knowledge graph has two layers:

- **Graph layer** — people, organizations, and locations are first-class
  nodes with edges between them. Use `findEntities()` with a `linked`
  expression to traverse these (see `find.md`).
- **Property layer** — documents, filings, articles, financial instruments,
  events, and all other types are attached as property values on graph
  nodes. Use `getPropertyValues()` with the relationship PID to traverse
  these.

If you need to find people linked to an organization, use `findEntities`
with a `linked` expression:

```typescript
const res = await client.findEntities({
    expression: JSON.stringify({
        type: 'linked',
        linked: {
            to_entity: orgNeid,
            distance: 1,
            pids: [isOfficerPid, isDirectorPid, worksAtPid],
            direction: 'incoming',
        },
    }),
    limit: 50,
});
const personNeids = (res as any).eids ?? [];
```

For non-graph-node types (filings, documents, etc.), use `getPropertyValues`
with the relationship PID. Relationship properties (`data_nindex`) return
linked entity IDs as values. Zero-pad the returned IDs to 20 characters
to form valid NEIDs.

```typescript
const pidMap = await getPropertyPidMap(client);
const filedPid = pidMap.get('filed')!;
const res = await client.getPropertyValues({
    eids: JSON.stringify([orgNeid]),
    pids: JSON.stringify([filedPid]),
});
const docNeids = (res.values ?? []).map((v) => String(v.value).padStart(20, '0'));
```

See [cookbook-data.md](cookbook-data.md) in this skill for a full "Get filings for a company" recipe.

### Expression language pitfalls

These mistakes come up repeatedly when building `/elemental/find` queries:

- **Entity type filtering**: Use `is_type` (not `comparison` with pid=0).
  `comparison` requires `pid != 0`.
- **`string_like` is name-only**: Only works on the name property (PID 8).
  Use `eq` for exact matches on other string properties.
- **Boolean combinators**: Use `{"type": "and", "and": [...]}` — not
  `conjunction` or any other name.
- **`lt`/`gt` are numeric-only**: Only work on `data_int` and `data_float`
  properties.
- **`regex` is not implemented**: Will return an error.

Read the "Common Mistakes" section in the **elemental-api skill** (`find.md`)
for examples of each.

### Entity Search

Use `client.findEntities()` (`POST /elemental/find`) for entity search.
It supports filtering by type, property value, and relationship via the
expression language (see `find.md`). For name-based lookups, use
`string_like` on the name property (PID 8).

For batch name resolution with scored ranking, call `POST /entities/search`
directly via `$fetch` (not on the generated client). See the
**elemental-api skill** (`entities.md`) for request/response shapes.

## Traversing Relationships

Relationships between entities are discoverable via the schema — use
`getSchema()` to find relationship properties (`data_nindex` type) and
their PIDs. Do NOT hardcode relationship names or PIDs; they can change
as the knowledge graph evolves. See the **data-model skill** for
source-specific schemas.

**Two traversal methods:**

- **Graph-layer entities** (person, organization, location): Use
  `findEntities()` with a `linked` expression. See `find.md`.
- **Property-layer entities** (documents, filings, articles, etc.): Use
  `getPropertyValues()` with the relationship PID. Values are entity IDs
  that must be zero-padded to 20 characters.

See [cookbook-data.md](cookbook-data.md) (news feed recipe) for a full example.

## Error Handling

```typescript
try {
    const data = await client.findEntities({
        expression: JSON.stringify({
            type: 'comparison',
            comparison: { operator: 'string_like', pid: 8, value: 'Apple' },
        }),
        limit: 5,
    });
} catch (error) {
    console.error('API Error:', error);
    showError('Failed to load data. Please try again.');
}
```

Methods on `useElementalClient()` return data directly and throw on non-2xx
responses. For full `{ data, status, headers }` access, import the raw
functions instead:

```typescript
import { getArticle } from '@yottagraph-app/elemental-api/client';

const response = await getArticle(artid);
if (response.status === 404) {
    /* handle not found */
}
```

## Lovelace MCP Servers

Four MCP servers may be configured in `.agents/mcp.json` for interactive
data exploration. **Check your tool list** — if tools like
`elemental_get_schema` appear, use them as your primary testing and
exploration interface before writing code. If they don't appear, the
servers aren't connected; use curl and the skill docs instead.

| Server                | What it provides                                                              |
| --------------------- | ----------------------------------------------------------------------------- |
| `lovelace-elemental`  | Knowledge Graph: entities, relationships, events, sentiment, schema discovery |
| `lovelace-stocks`     | Stock/financial market data                                                   |
| `lovelace-wiki`       | Wikipedia entity enrichment                                                   |
| `lovelace-polymarket` | Prediction market data                                                        |

### MCP Tool Quick Reference

| Tool                           | Purpose                                                        | Use to verify...                     |
| ------------------------------ | -------------------------------------------------------------- | ------------------------------------ |
| `elemental_get_schema`         | Discover entity types (flavors), properties, and relationships | Flavor IDs, property IDs, data types |
| `elemental_get_entity`         | Look up entity by name or NEID; returns properties             | Entity resolution, property shapes   |
| `elemental_get_related`        | Related entities with type/relationship filters                | Relationship types and traversal     |
| `elemental_get_relationships`  | Relationship types and counts between two entities             | Edge types between specific entities |
| `elemental_graph_neighborhood` | Most influential neighbors of an entity                        | Graph connectivity                   |
| `elemental_graph_sentiment`    | Sentiment analysis from news articles                          | Sentiment data availability          |
| `elemental_get_events`         | Events for an entity or by search query                        | Event categories and shapes          |
| `elemental_health`             | Health check                                                   | Server connectivity                  |

MCP tools handle entity resolution, PID lookups, and NEID formatting
automatically. Use them to discover IDs and verify data exists before
building REST-based features with `useElementalClient()`.

### Setup

`.agents/mcp.json` is auto-generated by `init-project.js`. If it's missing,
run `node init-project.js --local` to regenerate it. For provisioned projects,
the servers route through the Portal Gateway proxy (no credentials needed).
For local development without a gateway, the servers require an
`AUTH0_M2M_DEV_TOKEN` environment variable.
