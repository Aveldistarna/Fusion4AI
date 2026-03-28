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
}
