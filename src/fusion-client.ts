import * as http from "http";
import { FusionConnection, FusionResponse } from "./types.js";

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 7432;
const REQUEST_TIMEOUT = 120_000; // 120s for multi-step design scripts

export class FusionClient {
  private host: string = DEFAULT_HOST;
  private port: number = DEFAULT_PORT;
  private connected: boolean = false;
  private fusionVersion?: string;
  private documentName?: string;

  /** Connect to the Fusion Add-in HTTP server. */
  async connect(port?: number): Promise<{ version: string; document: string }> {
    if (port !== undefined) this.port = port;

    const res = await this.request("session", "ping", {});
    this.connected = true;
    this.fusionVersion = res.version as string;
    this.documentName = res.document as string;

    return {
      version: this.fusionVersion ?? "unknown",
      document: this.documentName ?? "unknown",
    };
  }

  /** Reset connection state. */
  disconnect(): void {
    this.connected = false;
    this.fusionVersion = undefined;
    this.documentName = undefined;
  }

  /** Check if currently connected. */
  isConnected(): boolean {
    return this.connected;
  }

  /** Get current connection info. */
  getStatus(): FusionConnection {
    return {
      host: this.host,
      port: this.port,
      connected: this.connected,
      fusionVersion: this.fusionVersion,
      documentName: this.documentName,
    };
  }

  /** Send a request to the Fusion Add-in and return the result. */
  async request(
    handler: string,
    action: string,
    params: Record<string, unknown> = {}
  ): Promise<Record<string, unknown>> {
    const body = JSON.stringify({ params });

    return new Promise<Record<string, unknown>>((resolve, reject) => {
      const req = http.request(
        {
          hostname: this.host,
          port: this.port,
          path: `/api/${handler}/${action}`,
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body),
          },
          timeout: REQUEST_TIMEOUT,
        },
        (res) => {
          let data = "";
          res.on("data", (chunk: Buffer) => {
            data += chunk.toString();
          });
          res.on("end", () => {
            try {
              const parsed: FusionResponse = JSON.parse(data);
              if (!parsed.success) {
                reject(new Error(parsed.error ?? "Unknown error from Fusion Add-in"));
              } else {
                resolve(parsed.result ?? {});
              }
            } catch {
              reject(new Error(`Invalid JSON from Fusion Add-in: ${data.slice(0, 200)}`));
            }
          });
        }
      );

      req.on("error", (e: Error) => {
        this.connected = false;
        reject(
          new Error(
            `Cannot reach Fusion Add-in at ${this.host}:${this.port} — ${e.message}. ` +
              `Is Fusion 360 running with the Fusion4AI add-in loaded?`
          )
        );
      });

      req.on("timeout", () => {
        req.destroy();
        reject(new Error(`Request to Fusion Add-in timed out after ${REQUEST_TIMEOUT}ms`));
      });

      req.write(body);
      req.end();
    });
  }
}
