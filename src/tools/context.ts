import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

function formatResult(result: Record<string, unknown>): string {
  return JSON.stringify(result, null, 2);
}

export function register(server: McpServer, client: FusionClient): void {
  // ── set_intent ──
  server.tool(
    "set_intent",
    "Embed design reasoning into a body/sketch/feature as persistent attributes in the Fusion document. " +
      "Records WHY it exists (intent), WHY it sits there (placement), WHY it is this size (dimensions), " +
      "what it depends on, and the constraints a machine re-checks. " +
      "This context survives session restarts and travels with the geometry.",
    {
      target: z.string().describe("Body/sketch/feature name or entityToken"),
      intent: z.string().optional()
        .describe("WHY this object exists (e.g. 'clearance hole for M3 screw fixing the lid')"),
      placement: z.string().optional()
        .describe("WHY it sits at this position/orientation. Name the relation and what breaks if it moves " +
          "(e.g. 'centered on the servo horn axis so the arm clears the frame at full sweep'). " +
          "Test: if this were moved, would your sentence reveal that something broke?"),
      dimensions: z.string().optional()
        .describe("WHY it is this size — the arithmetic behind the numbers " +
          "(e.g. 'depth 49 = 54 frame width - 5 wall clearance')"),
      role: z.string().optional().describe("Functional role (e.g. 'mounting', 'structural', 'clearance', 'cosmetic')"),
      depends_on: z.array(z.string()).optional()
        .describe("Names/tokens of entities this object's position or size depends on"),
      constraints: z.array(z.string()).optional()
        .describe("Rules re-measured after every move. Grammar: 'clearance >= 3mm to Cover', " +
          "'inside Housing', 'flush Base top', 'aligned Bracket x', 'symmetric_to Leg_L about YZ', " +
          "'concentric_with Shaft z'. Anything else is stored but reported as unchecked."),
    },
    async ({ target, intent, placement, dimensions, role, depends_on, constraints }) => {
      try {
        const result = await client.request("context", "set_context", {
          target, intent, placement, dimensions, role, depends_on, constraints,
        });
        return {
          content: [{ type: "text" as const, text: formatResult(result) }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── get_intent ──
  server.tool(
    "get_intent",
    "Read WHY an object is there: its embedded design intent, constraints, dependencies, " +
      "operation history (provenance), and what other objects depend on it. " +
      "ALWAYS check this before modifying or deleting an object you did not create in this session.",
    {
      target: z.string().describe("Body/sketch/feature name or entityToken"),
    },
    async ({ target }) => {
      try {
        const result = await client.request("context", "get_context", { target });
        return {
          content: [{ type: "text" as const, text: formatResult(result) }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── get_design_context ──
  server.tool(
    "get_design_context",
    "Get the semantic map of the whole design: every annotated entity with its intent and dependencies, " +
      "plus bodies that have no intent recorded yet. " +
      "Call this first when resuming work on an existing design to recover past intent.",
    {},
    async () => {
      try {
        const result = await client.request("context", "list_contexts", {});
        return {
          content: [{ type: "text" as const, text: formatResult(result) }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── find_dependents ──
  server.tool(
    "find_dependents",
    "Impact analysis: list all objects whose recorded dependencies point at this entity — " +
      "i.e. what may break if it is moved, resized, or deleted. Returns safe_to_modify flag.",
    {
      target: z.string().describe("Body/sketch/feature name or entityToken"),
    },
    async ({ target }) => {
      try {
        const result = await client.request("context", "find_dependents", { target });
        return {
          content: [{ type: "text" as const, text: formatResult(result) }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── review_geometry ──
  server.tool(
    "review_geometry",
    "Re-measure every recorded constraint against the geometry as it stands now. " +
      "Fusion checks that a model is valid, never that it still keeps the promises its designer made: " +
      "nothing else notices a bracket drifting off the 3mm gap it was placed for. " +
      "Run after manual edits, after a batch of moves, and before calling a part done. " +
      "Reports 'unchecked' as prominently as violations — a constraint outside the grammar was stored, not verified.",
    {
      target: z.string().optional()
        .describe("Review one body only. Omit to review the whole design."),
    },
    async ({ target }) => {
      try {
        const result = await client.request("context", "review_geometry", { target });
        return {
          content: [{ type: "text" as const, text: formatResult(result) }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── check_context_integrity ──
  server.tool(
    "check_context_integrity",
    "Reconciliation check: find dangling depends_on references (target was deleted/renamed), " +
      "orphaned intent (the body/face it described was consumed by a fillet or deleted), " +
      "and bodies without recorded intent. Run this after manual edits in the Fusion UI " +
      "or when resuming work, then repair with set_intent.",
    {
      purge_orphans: z.boolean().optional()
        .describe("Delete intent whose geometry no longer exists. Destructive and " +
          "unrecoverable — read the orphans first and re-attach anything still meaningful."),
    },
    async ({ purge_orphans }) => {
      try {
        const result = await client.request("context", "check_integrity", { purge_orphans });
        return {
          content: [{ type: "text" as const, text: formatResult(result) }],
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
