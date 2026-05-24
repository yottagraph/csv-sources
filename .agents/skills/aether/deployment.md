### App (Nuxt UI + server routes)

Vercel auto-deploys on every push to `main`. Preview deployments are created for
other branches. The app is available at `{slug}.yottagraph.app`.

### Agents (`agents/`)

Each subdirectory in `agents/` is a self-contained Python ADK agent. Deploy via
the Portal UI or `/deploy_agent` in Cursor.

### MCP Servers (`mcp-servers/`)

Each subdirectory in `mcp-servers/` is a Python FastMCP server. Deploy via
the Portal UI or `/deploy_mcp` in Cursor.
