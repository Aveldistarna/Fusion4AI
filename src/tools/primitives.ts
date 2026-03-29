import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

// Common optional params for inline boolean operation
const booleanParam = z.enum(["union", "subtract", "intersect"]).optional()
  .describe("If set, immediately perform this boolean operation with the target body instead of creating a separate body");
const targetParam = z.string().optional()
  .describe("Target body name for the boolean operation (required if boolean is set)");

function formatResult(result: Record<string, unknown>): string {
  return JSON.stringify(result, null, 2);
}

export function register(server: McpServer, client: FusionClient): void {
  // ── create_box ──
  server.tool(
    "create_box",
    "Create a rectangular box. Optionally apply a boolean operation (union/subtract/intersect) with a target body in a single step.",
    {
      width: z.number().positive().describe("Width in mm (X axis)"),
      height: z.number().positive().describe("Height in mm (Z axis)"),
      depth: z.number().positive().describe("Depth in mm (Y axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center position [x, y, z] in mm (default: origin)"),
      boolean: booleanParam,
      target: targetParam,
    },
    async ({ width, height, depth, name, position, boolean: boolOp, target }) => {
      try {
        const result = await client.request("primitives", "create_box", {
          width, height, depth, name, position, boolean: boolOp, target,
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

  // ── create_cylinder ──
  server.tool(
    "create_cylinder",
    "Create a cylinder. Optionally apply a boolean operation with a target body in a single step. Common use: subtract from a target to create a hole.",
    {
      diameter: z.number().positive().describe("Diameter in mm"),
      height: z.number().positive().describe("Height in mm (Z axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center of base position [x, y, z] in mm (default: origin)"),
      boolean: booleanParam,
      target: targetParam,
    },
    async ({ diameter, height, name, position, boolean: boolOp, target }) => {
      try {
        const result = await client.request("primitives", "create_cylinder", {
          diameter, height, name, position, boolean: boolOp, target,
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

  // ── create_sphere ──
  server.tool(
    "create_sphere",
    "Create a sphere. Optionally apply a boolean operation with a target body in a single step.",
    {
      diameter: z.number().positive().describe("Diameter in mm"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center position [x, y, z] in mm (default: origin)"),
      boolean: booleanParam,
      target: targetParam,
    },
    async ({ diameter, name, position, boolean: boolOp, target }) => {
      try {
        const result = await client.request("primitives", "create_sphere", {
          diameter, name, position, boolean: boolOp, target,
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

  // ── create_cone ──
  server.tool(
    "create_cone",
    "Create a cone or frustum. Set top_diameter=0 for a pointed cone. Optionally apply a boolean operation with a target body.",
    {
      base_diameter: z.number().positive().describe("Base diameter in mm"),
      top_diameter: z.number().min(0).describe("Top diameter in mm (0 for pointed cone)"),
      height: z.number().positive().describe("Height in mm (Z axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center of base position [x, y, z] in mm (default: origin)"),
      boolean: booleanParam,
      target: targetParam,
    },
    async ({ base_diameter, top_diameter, height, name, position, boolean: boolOp, target }) => {
      try {
        const result = await client.request("primitives", "create_cone", {
          base_diameter, top_diameter, height, name, position, boolean: boolOp, target,
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
}
