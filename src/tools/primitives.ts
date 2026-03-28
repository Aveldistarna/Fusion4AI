import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

export function register(server: McpServer, client: FusionClient): void {
  // ── create_box ──
  server.tool(
    "create_box",
    "Create a rectangular box. Returns body name, volume, and bounding box.",
    {
      width: z.number().positive().describe("Width in mm (X axis)"),
      height: z.number().positive().describe("Height in mm (Z axis)"),
      depth: z.number().positive().describe("Depth in mm (Y axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center position [x, y, z] in mm (default: origin)"),
    },
    async ({ width, height, depth, name, position }) => {
      try {
        const result = await client.request("primitives", "create_box", {
          width, height, depth, name, position,
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

  // ── create_cylinder ──
  server.tool(
    "create_cylinder",
    "Create a cylinder. Returns body name, volume, and bounding box.",
    {
      diameter: z.number().positive().describe("Diameter in mm"),
      height: z.number().positive().describe("Height in mm (Z axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center of base position [x, y, z] in mm (default: origin)"),
    },
    async ({ diameter, height, name, position }) => {
      try {
        const result = await client.request("primitives", "create_cylinder", {
          diameter, height, name, position,
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

  // ── create_sphere ──
  server.tool(
    "create_sphere",
    "Create a sphere. Returns body name, volume, and bounding box.",
    {
      diameter: z.number().positive().describe("Diameter in mm"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center position [x, y, z] in mm (default: origin)"),
    },
    async ({ diameter, name, position }) => {
      try {
        const result = await client.request("primitives", "create_sphere", {
          diameter, name, position,
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

  // ── create_cone ──
  server.tool(
    "create_cone",
    "Create a cone or frustum. Set top_diameter=0 for a pointed cone. Returns body name, volume, and bounding box.",
    {
      base_diameter: z.number().positive().describe("Base diameter in mm"),
      top_diameter: z.number().min(0).describe("Top diameter in mm (0 for pointed cone)"),
      height: z.number().positive().describe("Height in mm (Z axis)"),
      name: z.string().optional().describe("Name for the body"),
      position: z
        .tuple([z.number(), z.number(), z.number()])
        .optional()
        .describe("Center of base position [x, y, z] in mm (default: origin)"),
    },
    async ({ base_diameter, top_diameter, height, name, position }) => {
      try {
        const result = await client.request("primitives", "create_cone", {
          base_diameter, top_diameter, height, name, position,
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
