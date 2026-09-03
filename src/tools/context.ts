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
      shape: z.string().optional()
        .describe("WHAT this IS, as you understand it right now — the shape you would have to " +
          "see to know (e.g. 'rounded-rectangle plate, 40x30x10, corners R15 so the sides are " +
          "fully arced, one 6mm hole through the centre'). Recording this stamps a fingerprint " +
          "of the actual geometry, so a later edit that makes the sentence wrong is detectable."),
      role: z.string().optional().describe("Functional role (e.g. 'mounting', 'structural', 'clearance', 'cosmetic')"),
      depends_on: z.array(z.string()).optional()
        .describe("Names/tokens of entities this object's position or size depends on"),
      constraints: z.array(z.string()).optional()
        .describe("Rules re-measured after every move. Grammar: 'clearance >= 3mm to Cover', " +
          "'inside Housing', 'flush Base top', 'aligned Bracket x', 'symmetric_to Leg_L about YZ', " +
          "'concentric_with Shaft z'. Anything else is stored but reported as unchecked."),
    },
    async ({ target, intent, placement, dimensions, shape, role, depends_on, constraints }) => {
      try {
        const result = await client.request("context", "set_context", {
          target, intent, placement, dimensions, shape, role, depends_on, constraints,
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

  // ── describe_shape ──
  server.tool(
    "describe_shape",
    "Read what a body or a whole part IS, computed from the geometry — extents, how much of its " +
      "bounding box it fills, the face inventory, openings, symmetry planes. " +
      "Use this INSTEAD of a screenshot when you need to know the actual shape: image recognition " +
      "cannot tell R15 from R14, or notice that a fillet swallowed a face entirely. " +
      "If a shape description was recorded, this also reports whether it still matches the body.",
    {
      target: z.string().optional().describe("Body name or entityToken"),
      module: z.string().optional()
        .describe("Describe a whole part instead: combined extent, its bodies, how much it fills"),
    },
    async ({ target, module }) => {
      try {
        const result = await client.request("shape", "describe", { target, module });
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

  // ── review_intent ──
  server.tool(
    "review_intent",
    "Put what was RECORDED against what is actually MEASURED, side by side, and ask the questions. " +
      "Nothing else does this: get_intent returns the reasons, describe_shape returns the geometry, " +
      "and reading one of them is how a hole ends up in the wrong place while every review passes. " +
      "This one judges nothing — 'clearance hole for the M3' cannot be machine-checked, and a checker " +
      "that claimed to would be reporting a success it never earned. YOU are the check. " +
      "Read the answers, then record them with verify_intent.",
    {
      target: z.string().describe("Body name or entityToken"),
    },
    async ({ target }) => {
      try {
        const result = await client.request("shape", "review", { target });
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

  // ── verify_intent ──
  server.tool(
    "verify_intent",
    "Record that you read the recorded reasons against the measured shape, and what you concluded. " +
      "Until this is called a body counts as UNVERIFIED — not failed, but nobody has looked, " +
      "and what_is_not_recorded says so. The fingerprint of the shape is stamped alongside, " +
      "so machining the body later returns it to unverified rather than leaving a stale pass.",
    {
      target: z.string().describe("Body name or entityToken"),
      matches: z.boolean().optional()
        .describe("Does the geometry actually do what the recorded reasons claim? " +
          "Default true. Record false when you found a contradiction you have not fixed yet."),
      note: z.string()
        .describe("REQUIRED: what you compared, concretely. 'intent says a through hole for M6; " +
          "measured 2 openings and one 6.0mm cylindrical face.' Without this, 'verified' is " +
          "indistinguishable from never having looked."),
    },
    async ({ target, matches, note }) => {
      try {
        const result = await client.request("shape", "verify", { target, matches, note });
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

  // ── what_is_not_recorded ──
  server.tool(
    "what_is_not_recorded",
    "WHICH BODIES HAVE NO RECORD — names only, nothing else. " +
      "Every other tool carries what it is filtering out, so finding the three bodies nobody described " +
      "means reading the whole map with all the prose in it. This one carries only the absence. " +
      "Asks three questions per body, because a reason is recorded in three parts that go missing separately: " +
      "why it exists, why it sits there, why it is that size. " +
      "Use before a documenting pass, and again to see the pass finished.",
    {
      limit: z.number().int().positive().optional()
        .describe("Names listed per question (default 40). Whatever is dropped is still counted."),
    },
    async ({ limit }) => {
      try {
        const result = await client.request("context", "what_is_not_recorded", { limit });
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
