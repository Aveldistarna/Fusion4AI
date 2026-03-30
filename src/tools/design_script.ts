import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

export function register(server: McpServer, client: FusionClient): void {
  server.tool(
    "execute_design",
    `Execute a complete CSG design from a YAML/JSON script.

The script defines a base body and a sequence of features (union, subtract, fillet, chamfer).
Position references like 'top', 'bottom' are resolved automatically from the body's bounding box.
Patterns like 'corners(47.14)' expand into multiple operations.

Example YAML:
  name: bracket
  body:
    shape: box
    size: [40, 20, 10]
  features:
    - subtract:
        shape: cylinder
        size: [5, through]
        pattern: corners(30)
    - fillet:
        radius: 1
        edges: vertical`,
    {
      yaml: z.string().describe("Design script in YAML or JSON format"),
      resume_from: z.number().int().min(0).optional()
        .describe("Step index to resume from after a checkpoint/select pause"),
      body_name: z.string().optional()
        .describe("Body name to operate on (required when resuming)"),
    },
    async ({ yaml, resume_from, body_name }) => {
      try {
        const result = await client.request("design_script", "execute_design", {
          yaml, resume_from, body_name,
        });
        return {
          content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );
}
