// ── Fusion Add-in HTTP response ──

export interface FusionResponse {
  success: boolean;
  result?: Record<string, unknown>;
  error?: string;
}

// ── Connection state ──

export interface FusionConnection {
  host: string;
  port: number;
  connected: boolean;
  fusionVersion?: string;
  documentName?: string;
}

// ── Body information returned by creation tools ──

export interface BodyInfo {
  name: string;
  id: string; // Fusion entityToken
  volume_cm3: number;
  bounding_box: {
    min: [number, number, number];
    max: [number, number, number];
  };
}

// ── Face information for spatial queries ──

export interface FaceInfo {
  id: string;
  type: "planar" | "cylindrical" | "spherical" | "conical" | "other";
  center: [number, number, number];
  normal?: [number, number, number];
  area_cm2: number;
}

// ── Edge information ──

export interface EdgeInfo {
  id: string;
  type: "line" | "arc" | "circle" | "other";
  start: [number, number, number];
  end: [number, number, number];
  length_mm: number;
}

// ── Measurement result ──

export interface MeasureResult {
  distance_mm?: number;
  angle_deg?: number;
  area_cm2?: number;
  volume_cm3?: number;
}
