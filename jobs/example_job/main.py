"""
Example Compute Job — a minimal Cloud Run Job entrypoint.

This is a starting point. Customize the body to do whatever batch
work your project needs: ETL, enrichment, scoring, periodic
aggregations, exports, notifications, etc.

A "compute job" is just a containerized Python (or any-language)
entrypoint deployed as a Cloud Run Job. It can be triggered:
- On a cron schedule via Cloud Scheduler (see `job.yaml`)
- Ad-hoc via the Portal "Run now" button
- From your Vercel app via the Portal Jobs API
- From an Agent Engine tool call
- As a step in a Cloud Workflows DAG (see workflows/example_workflow/)

Auth follows the same pattern as agents and MCP servers:
- Reads broadchurch.yaml at startup to discover the gateway URL,
  query server URL, org_id, and tenant SA
- Uses the bundled broadchurch_auth helpers to call the Yottagraph
  Elemental API and the tenant Postgres database

Local testing:
    cd jobs/example_job
    pip install -r requirements.txt
    python main.py --shard 0 --total-shards 1

Deployment:
    Use the /deploy_job Cursor command, or trigger the deploy-job
    GitHub Actions workflow with input `job_name=example_job`.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("example_job")


def load_config() -> dict:
    """Load broadchurch.yaml from the working directory or job directory."""
    for candidate in [Path("broadchurch.yaml"), Path(__file__).parent / "broadchurch.yaml"]:
        if candidate.exists():
            return yaml.safe_load(candidate.read_text()) or {}
    log.warning("broadchurch.yaml not found — running with environment-only config")
    return {}


def parse_args() -> argparse.Namespace:
    """Cloud Run Jobs Execution API exposes per-task variables as env vars.

    For parallel/sharded jobs, CLOUD_RUN_TASK_INDEX and CLOUD_RUN_TASK_COUNT
    are injected at runtime. We mirror these as CLI flags so local testing
    works the same way as production execution.
    """
    parser = argparse.ArgumentParser(description="Example compute job")
    parser.add_argument(
        "--shard",
        type=int,
        default=int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0")),
        help="This task's shard index (0-based). Defaults to CLOUD_RUN_TASK_INDEX.",
    )
    parser.add_argument(
        "--total-shards",
        type=int,
        default=int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1")),
        help="Total number of parallel shards. Defaults to CLOUD_RUN_TASK_COUNT.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()

    org_id = config.get("tenant", {}).get("org_id", os.environ.get("ORG_ID", "<unknown>"))
    log.info(
        "Starting example_job (shard=%d/%d, org_id=%s)",
        args.shard,
        args.total_shards,
        org_id,
    )

    # --- Customize below this line ---
    #
    # The canonical BC 2.0 compute pattern: read from APIs / MCP /
    # Cloud SQL, do work, write results to BigQuery (analytical) and
    # optionally Cloud SQL (transactional).
    #
    # 1. ETL/enrichment loop over entities from the yottagraph:
    #
    #     from broadchurch_auth import elemental_client
    #     resp = elemental_client.post(
    #         "/elemental/find",
    #         data={"expression": '{"type":"is_type","is_type":{"fid":10}}', "limit": "10000"},
    #     )
    #     eids = resp.json().get("eids", [])
    #     rows = []
    #     for eid in eids[args.shard::args.total_shards]:
    #         rows.append(enrich(eid))
    #     write_to_bigquery("entity_enrichments", rows)
    #
    # 2. Periodic aggregation written to BigQuery (preferred for
    #    append-only result sets):
    #
    #     from google.cloud import bigquery
    #     bq = bigquery.Client()
    #     dataset = os.environ.get("BIGQUERY_DATASET")  # e.g. "bc-acme.bc_acme_analytics"
    #     if not dataset:
    #         raise RuntimeError("BIGQUERY_DATASET not set; ensure tenant is BC 2.0")
    #     table = f"{dataset}.daily_summary"
    #     rows = [{"date": today_iso(), "count": 42, "shard": args.shard}]
    #     errors = bq.insert_rows_json(table, rows)
    #     if errors:
    #         raise RuntimeError(f"BQ insert failed: {errors}")
    #
    # 3. State updates to tenant Postgres (use Cloud SQL when the UI
    #    needs to read-modify-write the same row):
    #
    #     import psycopg
    #     conn = psycopg.connect(os.environ["DATABASE_URL"])
    #     with conn.cursor() as cur:
    #         cur.execute(
    #             "INSERT INTO last_run (job, ts) VALUES (%s, NOW()) "
    #             "ON CONFLICT (job) DO UPDATE SET ts = excluded.ts",
    #             ("example_job",),
    #         )
    #     conn.commit()
    #
    # 4. Workflow step (called from workflows/<name>/workflow.yaml):
    #
    #     import json
    #     input_payload = json.loads(os.environ.get("WORKFLOW_INPUT", "{}"))
    #     result = do_work(input_payload)
    #     print(json.dumps(result))
    #
    # See docs/COMPUTE_JOBS.md "Cloud SQL vs BigQuery" for the
    # decision rubric on which write target to use.
    #
    log.info("This is the example job. Customize main.py for your workload.")
    log.info("Job complete (shard=%d/%d)", args.shard, args.total_shards)

    return 0


if __name__ == "__main__":
    sys.exit(main())
