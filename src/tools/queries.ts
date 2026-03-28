import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

export function register(server: McpServer, client: FusionClient): void {
  // ── get_bodies ──
  server.tool(
    "get_bodies",
    "List all bodies in the current design with name, volume, and bounding box.",
    {},
    async () => {
      try {
        const result = await client.request("queries", "get_bodies", {});
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

  // ── get_faces ──
  server.tool(
    "get_faces",
    "List all faces of a body with type (planar/cylindrical/...), center, normal, area, and semantic label (top/bottom/front/back/left/right) where applicable.",
    {
      body_name: z.string().describe("Body name or entityToken"),
    },
    async ({ body_name }) => {
      try {
        const result = await client.request("queries", "get_faces", { body_name });
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

  // ── screenshot ──
  server.tool(
    "screenshot",
    "Capture the current Fusion viewport as an image file.",
    {
      output_path: z.string().describe("File path to save the image (e.g. C:/temp/view.png)"),
      width: z.number().int().positive().optional().describe("Image width in pixels (default: 1920)"),
      height: z.number().int().positive().optional().describe("Image height in pixels (default: 1080)"),
    },
    async ({ output_path, width, height }) => {
      try {
        const result = await client.request("queries", "screenshot", {
          output_path, width, height,
        });
        return {
          content: [{ type: "text" as const, text: `Screenshot saved: ${result.path} (${result.width}x${result.height})` }],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── get_selection ──
  server.tool(
    "get_selection",
    "Get the user's current selection in Fusion UI. Returns details about selected faces, edges, bodies, or components. Use this to see what the user is pointing at.",
    {},
    async () => {
      try {
        const result = await client.request("queries", "get_selection", {});
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
