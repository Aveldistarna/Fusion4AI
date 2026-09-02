import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

export function register(server: McpServer, client: FusionClient): void {
  // ── boolean_op ──
  server.tool(
    "boolean_op",
    "Perform a boolean operation between two bodies. 'subtract' cuts the tool from the target. 'union' merges them. 'intersect' keeps only the overlap.",
    {
      operation: z.enum(["union", "subtract", "intersect"]).describe("Boolean operation type"),
      target_body: z.string().describe("Target body name (the one that remains)"),
      tool_body: z.string().describe("Tool body name (used to cut/merge/intersect)"),
      keep_tool: z.boolean().optional().describe("Keep the tool body after operation (default: false)"),
    },
    async ({ operation, target_body, tool_body, keep_tool }) => {
      try {
        const result = await client.request("modifications", "boolean_op", {
          operation, target_body, tool_body, keep_tool,
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

  // ── move_body ──
  server.tool(
    "move_body",
    "Move a body by a translation in mm.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      x: z.number().optional().describe("X offset in mm (default: 0)"),
      y: z.number().optional().describe("Y offset in mm (default: 0)"),
      z: z.number().optional().describe("Z offset in mm (default: 0)"),
    },
    async ({ body_name, x, y, z: dz }) => {
      try {
        const result = await client.request("modifications", "move_body", {
          body_name, x, y, z: dz,
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

  // ── copy_body ──
  server.tool(
    "copy_body",
    "Copy a body with an offset in mm.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      x: z.number().optional().describe("X offset in mm (default: 0)"),
      y: z.number().optional().describe("Y offset in mm (default: 0)"),
      z: z.number().optional().describe("Z offset in mm (default: 0)"),
      new_name: z.string().optional().describe("Name for the copied body"),
    },
    async ({ body_name, x, y, z: dz, new_name }) => {
      try {
        const result = await client.request("modifications", "copy_body", {
          body_name, x, y, z: dz, new_name,
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

  // ── add_fillet ──
  server.tool(
    "add_fillet",
    "Add fillet (rounded edges) to a body. Edges can be 'all', 'top', 'bottom', 'front', 'back', 'left', 'right', or comma-separated edge IDs.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      radius: z.number().positive().describe("Fillet radius in mm"),
      edges: z.string().optional().describe("Edge selection: 'all', 'vertical', 'horizontal', 'perp_to_selection' (edges perpendicular to user-selected face), 'top', 'bottom', 'front', 'back', 'left', 'right', 'between:face1,face2', or comma-separated edge IDs (default: 'all')"),
    },
    async ({ body_name, radius, edges }) => {
      try {
        const result = await client.request("modifications", "add_fillet", {
          body_name, radius, edges,
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

  // ── add_chamfer ──
  server.tool(
    "add_chamfer",
    "Add chamfer (beveled edges) to a body.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      distance: z.number().positive().describe("Chamfer distance in mm"),
      edges: z.string().optional().describe("Edge selection: 'all', 'vertical', 'horizontal', 'top', 'bottom', 'front', 'back', 'left', 'right', 'between:face1,face2', or comma-separated edge IDs (default: 'all')"),
    },
    async ({ body_name, distance, edges }) => {
      try {
        const result = await client.request("modifications", "add_chamfer", {
          body_name, distance, edges,
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

  // ── add_hole ──
  server.tool(
    "add_hole",
    "Add a hole on a face of a body. Face can be 'top', 'front', etc. or a face ID. Depth can be a number (mm) or 'through'.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      face: z.string().describe("Face reference: 'top', 'bottom', 'front', 'back', 'left', 'right', or face ID"),
      diameter: z.number().positive().describe("Hole diameter in mm"),
      depth: z.union([z.number().positive(), z.literal("through")]).optional()
        .describe("Hole depth in mm or 'through' (default: 'through')"),
      offset_x: z.number().optional().describe("X offset from face center in mm (default: 0)"),
      offset_y: z.number().optional().describe("Y offset from face center in mm (default: 0)"),
    },
    async ({ body_name, face, diameter, depth, offset_x, offset_y }) => {
      try {
        const result = await client.request("modifications", "add_hole", {
          body_name, face, diameter, depth, offset_x, offset_y,
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

  // ── add_holes (multiple holes in one sketch) ──
  server.tool(
    "add_holes",
    "Add multiple holes on a face in a single operation. All holes are cut at once, avoiding coordinate drift. Each hole is specified as {x, y, diameter} where x/y are offsets from the face center in mm.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      face: z.string().describe("Face reference: 'top', 'bottom', 'front', 'back', 'left', 'right', or face ID"),
      holes: z.array(z.object({
        x: z.number().describe("X offset from face center in mm"),
        y: z.number().describe("Y offset from face center in mm"),
        diameter: z.number().positive().describe("Hole diameter in mm"),
      })).describe("Array of holes to create"),
      depth: z.union([z.number().positive(), z.literal("through")]).optional()
        .describe("Hole depth in mm or 'through' (default: 'through')"),
      intent: z.string().optional()
        .describe("WHY these holes exist. Lands on the body's provenance, not on why the body itself exists"),
      shape: z.string().optional()
        .describe("WHAT the body IS now these holes are in it - re-describe the machined result"),
    },
    async ({ body_name, face, holes, depth, intent, shape }) => {
      try {
        const result = await client.request("modifications", "add_holes", {
          body_name, face, holes, depth, intent, shape,
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

  // ── cut_by_plane ──
  server.tool(
    "cut_by_plane",
    "Cut a body with an infinite plane defined by a point and normal vector. Removes material on the normal side of the plane.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      point: z.tuple([z.number(), z.number(), z.number()])
        .describe("A point on the cutting plane [x, y, z] in mm"),
      normal: z.tuple([z.number(), z.number(), z.number()])
        .describe("Normal vector of the plane [nx, ny, nz] — material on this side is removed"),
    },
    async ({ body_name, point, normal }) => {
      try {
        const result = await client.request("modifications", "cut_by_plane", {
          body_name, point, normal,
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

  // ── rotate_body ──
  server.tool(
    "rotate_body",
    "Rotate a body around an axis defined by a point and direction vector.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      angle: z.number().describe("Rotation angle in degrees"),
      axis_point: z.tuple([z.number(), z.number(), z.number()]).optional()
        .describe("A point on the rotation axis [x, y, z] in mm (default: origin)"),
      axis_direction: z.tuple([z.number(), z.number(), z.number()]).optional()
        .describe("Direction of rotation axis [dx, dy, dz] (default: [0,0,1] = Z axis)"),
    },
    async ({ body_name, angle, axis_point, axis_direction }) => {
      try {
        const result = await client.request("modifications", "rotate_body", {
          body_name, angle, axis_point, axis_direction,
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

  // ── delete_body ──
  server.tool(
    "delete_body",
    "Delete a body permanently (this is NOT undoable via the timeline — the source feature is removed). " +
      "If other objects recorded a dependency on it, deletion is refused with the list of dependents " +
      "unless force=true. Check get_intent/find_dependents before forcing.",
    {
      body_name: z.string().describe("Body name or entityToken"),
      force: z.boolean().optional()
        .describe("Delete even if other objects depend on this body (default: false)"),
    },
    async ({ body_name, force }) => {
      try {
        const result = await client.request("modifications", "delete_body", {
          body_name, force,
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
