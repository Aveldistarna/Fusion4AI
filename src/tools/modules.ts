import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

function formatResult(result: Record<string, unknown>): string {
  return JSON.stringify(result, null, 2);
}

const areaParam = z
  .tuple([
    z.tuple([z.number(), z.number(), z.number()]),
    z.tuple([z.number(), z.number(), z.number()]),
  ])
  .optional()
  .describe(
    "The volume this part may occupy: two opposite corners [[x1,y1,z1],[x2,y2,z2]] in mm. " +
      "Draw the districts BEFORE building the parts — moving a box is free, moving thirty bodies is not."
  );

export function register(server: McpServer, client: FusionClient): void {
  // ── set_module ──
  server.tool(
    "set_module",
    "Declare which bodies are one part, and why that part exists. " +
      "The timeline records WHEN things were made; nothing else records WHICH BODIES ARE ONE THING — " +
      "after the session that built them, the grouping is otherwise gone. " +
      "Optionally give the part a district (the volume it may occupy) so a part growing into its " +
      "neighbour's space becomes a review finding instead of a surprise at assembly.",
    {
      name: z.string().describe("Part name (e.g. 'leg_right', 'housing')"),
      bodies: z.array(z.string()).optional()
        .describe("Body names that make up this part (replaces the current membership)"),
      intent: z.string().optional()
        .describe("What this part is for — the reason the group exists as a group"),
      shape: z.string().optional()
        .describe("WHAT the assembled part IS as a whole — each body knows its own shape, nothing else knows what they add up to"),
      area: areaParam,
    },
    async ({ name, bodies, intent, shape, area }) => {
      try {
        const result = await client.request("modules", "set_module", {
          name, bodies, intent, shape, area,
        });
        return { content: [{ type: "text" as const, text: formatResult(result) }] };
      } catch (e: any) {
        return { content: [{ type: "text" as const, text: e.message }], isError: true };
      }
    }
  );

  // ── list_modules ──
  server.tool(
    "list_modules",
    "Every part in the design, one line each, plus the bodies nobody classified. " +
      "Call when resuming work to recover how the design is divided up.",
    {},
    async () => {
      try {
        const result = await client.request("modules", "list_modules", {});
        return { content: [{ type: "text" as const, text: formatResult(result) }] };
      } catch (e: any) {
        return { content: [{ type: "text" as const, text: e.message }], isError: true };
      }
    }
  );

  // ── review_modules ──
  server.tool(
    "review_modules",
    "Check each part against the district it was given: which bodies have grown outside their volume. " +
      "A part with no district is reported as unbudgeted rather than passed — nothing was checked, " +
      "and saying so is the point.",
    {
      name: z.string().optional().describe("Review one part only. Omit for all."),
    },
    async ({ name }) => {
      try {
        const result = await client.request("modules", "review_modules", { name });
        return { content: [{ type: "text" as const, text: formatResult(result) }] };
      } catch (e: any) {
        return { content: [{ type: "text" as const, text: e.message }], isError: true };
      }
    }
  );

  // ── move_module ──
  server.tool(
    "move_module",
    "Move every body of a part together, as one rigid thing — the arrangement inside it stays intact. " +
      "The part's district moves with it. Returns the constraint re-check, since whatever this part " +
      "was measured against still has to hold.",
    {
      name: z.string().describe("Part name"),
      x: z.number().optional().describe("X offset in mm (default: 0)"),
      y: z.number().optional().describe("Y offset in mm (default: 0)"),
      z: z.number().optional().describe("Z offset in mm (default: 0)"),
    },
    async ({ name, x, y, z }) => {
      try {
        const result = await client.request("modules", "move_module", { name, x, y, z });
        return { content: [{ type: "text" as const, text: formatResult(result) }] };
      } catch (e: any) {
        return { content: [{ type: "text" as const, text: e.message }], isError: true };
      }
    }
  );

  // ── delete_module ──
  server.tool(
    "delete_module",
    "Forget a grouping. The bodies themselves are untouched.",
    {
      name: z.string().describe("Part name"),
    },
    async ({ name }) => {
      try {
        const result = await client.request("modules", "delete_module", { name });
        return { content: [{ type: "text" as const, text: formatResult(result) }] };
      } catch (e: any) {
        return { content: [{ type: "text" as const, text: e.message }], isError: true };
      }
    }
  );
}
