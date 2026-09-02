import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

// Common optional params for inline boolean operation
const booleanParam = z.enum(["union", "subtract", "intersect"]).optional()
  .describe("If set, immediately perform this boolean operation with the target body instead of creating a separate body");
const targetParam = z.string().optional()
  .describe("Target body name for the boolean operation (required if boolean is set)");
const intentParam = z.string().optional()
  .describe("WHY this shape exists — design intent embedded into the model itself (e.g. 'M3 mounting holes for servo bracket'). Strongly recommended: this context persists in the document and survives session restarts.");
const dependsOnParam = z.array(z.string()).optional()
  .describe("Names of bodies/features whose position or size this shape depends on (dependency graph for impact analysis)");
const placementParam = z.string().optional()
  .describe("WHY it sits at this position/orientation — name the relation and what breaks if it moves (e.g. 'flush with the frame's top face so the lid seats flat')");
const dimensionsParam = z.string().optional()
  .describe("WHY it is this size — the arithmetic behind the numbers (e.g. 'depth 49 = 54 frame width - 5 wall clearance')");
const shapeParam = z.string().optional()
  .describe("WHAT this IS, as you understand it — the shape you would have to see to know (e.g. 'rounded-rectangle plate, corners R15'). Recording it stamps a fingerprint of the real geometry so a later edit that makes the sentence wrong is detectable.");
const constraintsParam = z.array(z.string()).optional()
  .describe("Rules re-measured after every move. Grammar: 'clearance >= 3mm to Cover', 'inside Housing', 'flush Base top', 'aligned Bracket x', 'symmetric_to Leg_L about YZ', 'concentric_with Shaft z'. Anything else is stored but reported as unchecked.");

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
      intent: intentParam,
      placement: placementParam,
      dimensions: dimensionsParam,
      shape: shapeParam,
      constraints: constraintsParam,
      depends_on: dependsOnParam,
    },
    async ({ width, height, depth, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on }) => {
      try {
        const result = await client.request("primitives", "create_box", {
          width, height, depth, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on,
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
      intent: intentParam,
      placement: placementParam,
      dimensions: dimensionsParam,
      shape: shapeParam,
      constraints: constraintsParam,
      depends_on: dependsOnParam,
    },
    async ({ diameter, height, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on }) => {
      try {
        const result = await client.request("primitives", "create_cylinder", {
          diameter, height, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on,
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
      intent: intentParam,
      placement: placementParam,
      dimensions: dimensionsParam,
      shape: shapeParam,
      constraints: constraintsParam,
      depends_on: dependsOnParam,
    },
    async ({ diameter, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on }) => {
      try {
        const result = await client.request("primitives", "create_sphere", {
          diameter, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on,
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
      intent: intentParam,
      placement: placementParam,
      dimensions: dimensionsParam,
      shape: shapeParam,
      constraints: constraintsParam,
      depends_on: dependsOnParam,
    },
    async ({ base_diameter, top_diameter, height, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on }) => {
      try {
        const result = await client.request("primitives", "create_cone", {
          base_diameter, top_diameter, height, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on,
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

  // ── create_polygon ──
  server.tool(
    "create_polygon",
    "Create an extruded polygon from a list of 2D points. Points define the cross-section, extruded along Z. Use this for arbitrary cross-sections like T-slots, channels, brackets, etc.",
    {
      points: z.array(z.tuple([z.number(), z.number()]))
        .describe("2D points [[x,y], ...] in mm defining the polygon outline (closed automatically)"),
      height: z.number().positive().describe("Extrusion height in mm (Z axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Position offset [x, y, z] in mm (default: origin)"),
      boolean: booleanParam,
      target: targetParam,
      intent: intentParam,
      placement: placementParam,
      dimensions: dimensionsParam,
      shape: shapeParam,
      constraints: constraintsParam,
      depends_on: dependsOnParam,
    },
    async ({ points, height, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on }) => {
      try {
        const result = await client.request("primitives", "create_polygon", {
          points, height, name, position, boolean: boolOp, target, intent, placement, dimensions, shape, constraints, depends_on,
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
