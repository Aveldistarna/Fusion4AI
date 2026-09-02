import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FusionClient } from "../fusion-client.js";

export function register(server: McpServer, client: FusionClient): void {
  // ── fusion_connect ──
  server.tool(
    "fusion_connect",
    "Connect to the Fusion 360 add-in. Verifies reachability and returns Fusion version and active document name.",
    {
      port: z
        .number()
        .int()
        .positive()
        .optional()
        .describe("Port of the Fusion add-in HTTP server (default: 7432)"),
    },
    async ({ port }) => {
      try {
        const info = await client.connect(port);
        return {
          content: [
            {
              type: "text" as const,
              text:
                `Connected to Fusion 360.\n` +
                `  Version : ${info.version}\n` +
                `  Document: ${info.document}`,
            },
          ],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── fusion_disconnect ──
  server.tool(
    "fusion_disconnect",
    "Disconnect from the Fusion 360 add-in.",
    {},
    async () => {
      client.disconnect();
      return {
        content: [{ type: "text" as const, text: "Disconnected from Fusion 360." }],
      };
    }
  );

  // ── fusion_status ──
  server.tool(
    "fusion_status",
    "Get current connection status, Fusion version, active document, and design summary.",
    {},
    async () => {
      const status = client.getStatus();
      if (!status.connected) {
        return {
          content: [
            {
              type: "text" as const,
              text: "Not connected. Use fusion_connect first.",
            },
          ],
        };
      }

      try {
        const info = await client.request("session", "status", {});
        const lines = [
          `Connected: ${status.host}:${status.port}`,
          `Fusion   : ${status.fusionVersion}`,
          `Document : ${info.document ?? status.documentName}`,
          `Bodies   : ${info.body_count ?? "?"}`,
          `Components: ${info.component_count ?? "?"}`,
        ];
        return {
          content: [{ type: "text" as const, text: lines.join("\n") }],
        };
      } catch (e: any) {
        client.disconnect();
        return {
          content: [
            {
              type: "text" as const,
              text: `Connection lost: ${e.message}`,
            },
          ],
          isError: true,
        };
      }
    }
  );

  // ── fusion_reload ──
  server.tool(
    "fusion_reload",
    "Hot-reload all Python handler modules in the Fusion add-in. Use this after editing Python code — no need to manually restart the add-in.",
    {},
    async () => {
      try {
        const result = await client.request("system", "reload", {});
        return {
          content: [
            {
              type: "text" as const,
              text: `Reloaded: ${JSON.stringify(result)}`,
            },
          ],
        };
      } catch (e: any) {
        return {
          content: [{ type: "text" as const, text: e.message }],
          isError: true,
        };
      }
    }
  );

  // ── fusion_undo ──
  server.tool(
    "fusion_undo",
    "Undo the last operation(s) in the Fusion design timeline.",
    {
      count: z.number().int().positive().optional()
        .describe("Number of operations to undo (default: 1)"),
    },
    async ({ count }) => {
      try {
        const result = await client.request("session", "undo", { count });
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

  // ── fusion_redo ──
  server.tool(
    "fusion_redo",
    "Redo previously undone operation(s).",
    {
      count: z.number().int().positive().optional()
        .describe("Number of operations to redo (default: 1)"),
    },
    async ({ count }) => {
      try {
        const result = await client.request("session", "redo", { count });
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

  // ── get_timeline ──
  server.tool(
    "get_timeline",
    "List all items in the Fusion design timeline (features, sketches, construction planes, etc.) with index, type, name, and status.",
    {},
    async () => {
      try {
        const result = await client.request("session", "get_timeline", {});
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

  // ── delete_feature ──
  server.tool(
    "delete_feature",
    "Delete a feature or sketch from the design by timeline index or name.",
    {
      index: z.number().int().min(0).optional()
        .describe("Timeline index of the item to delete"),
      name: z.string().optional()
        .describe("Name of the feature/sketch to delete"),
    },
    async ({ index, name }) => {
      try {
        const result = await client.request("session", "delete_feature", { index, name });
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

  // ── new_design ──
  server.tool(
    "new_design",
    "Create a new empty Fusion design document.",
    {},
    async () => {
      try {
        const result = await client.request("session", "new_design", {});
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

  // ── set_checkpoint ──
  server.tool(
    "set_checkpoint",
    "Record a named checkpoint at the current end of the timeline. " +
      "Call this BEFORE starting each new part/section, so a failed attempt can be " +
      "undone with rollback_to_checkpoint instead of abandoning the design.",
    {
      label: z.string().describe("Checkpoint name (e.g. 'before Leg_R', 'bracket done')"),
    },
    async ({ label }) => {
      try {
        const result = await client.request("session", "set_checkpoint", { label });
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

  // ── list_checkpoints ──
  server.tool(
    "list_checkpoints",
    "List the recorded timeline checkpoints for the current design.",
    {},
    async () => {
      try {
        const result = await client.request("session", "list_checkpoints", {});
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

  // ── rollback_to_checkpoint ──
  server.tool(
    "rollback_to_checkpoint",
    "PERMANENTLY delete all timeline items created after a checkpoint — undo one failed part " +
      "while keeping everything built before it. This is destructive (not a timeline marker move); " +
      "confirm with the user if the work being discarded was not created in this session.",
    {
      label: z.string().optional().describe("Checkpoint name to roll back to"),
      position: z.number().int().min(0).optional()
        .describe("Timeline position to roll back to (alternative to label)"),
    },
    async ({ label, position }) => {
      try {
        const result = await client.request("session", "rollback_to_checkpoint", {
          label, position,
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
