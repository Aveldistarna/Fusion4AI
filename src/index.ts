#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { execSync } from "child_process";
import { FusionClient } from "./fusion-client.js";

// Tool registrars (one per category)
import { register as registerSession } from "./tools/session.js";
import { register as registerPrimitives } from "./tools/primitives.js";
import { register as registerQueries } from "./tools/queries.js";
import { register as registerModifications } from "./tools/modifications.js";
import { register as registerDesignScript } from "./tools/design_script.js";
import { register as registerContext } from "./tools/context.js";
import { register as registerModules } from "./tools/modules.js";

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------

const server = new McpServer({
  name: "fusion4ai",
  version: "1.0.0",
});

const fusionClient = new FusionClient();

// Register tool categories
registerSession(server, fusionClient);
registerPrimitives(server, fusionClient);
registerQueries(server, fusionClient);
registerModifications(server, fusionClient);
registerDesignScript(server, fusionClient);
registerContext(server, fusionClient);
registerModules(server, fusionClient);

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------

function cleanup() {
  fusionClient.disconnect();
}

async function main() {
  const transport = new StdioServerTransport();

  process.on("SIGINT", () => {
    cleanup();
    process.exit(0);
  });
  process.on("SIGTERM", () => {
    cleanup();
    process.exit(0);
  });
  process.on("exit", () => {
    cleanup();
  });

  await server.connect(transport);
  console.error("fusion4ai MCP server running on stdio");
}

// ---------------------------------------------------------------------------
// --setup: register as MCP server in Claude Code
// ---------------------------------------------------------------------------

if (process.argv.includes("--setup")) {
  const scope = process.argv.includes("--project") ? "project" : "user";
  try {
    const scopeFlag = scope === "project" ? " --scope project" : "";
    execSync(`claude mcp add${scopeFlag} fusion4ai -- fusion4ai`, {
      stdio: "inherit",
      env: { ...process.env, FORCE_COLOR: "1" },
    });
    console.log(`\nfusion4ai registered as MCP server (scope: ${scope}).`);
  } catch (e: any) {
    console.error("Failed to register:", e.message);
    process.exit(1);
  }
  process.exit(0);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
