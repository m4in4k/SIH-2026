import training from "./demo-transactions.json";
export type Detection = {
  code: string;
  stage: string;
  detector: string;
  title: string;
  feature: string;
  observed: number;
  operator: string;
  threshold: number;
  baseline: number | null;
  unit: string;
  detected_at: string;
  reason: string;
};
export type StageEvent = {
  id: string;
  stage: string;
  status: string;
  at: string;
  detail: Record<string, unknown>;
};
export type Tx = {
  txid: string;
  observed_at: string | null;
  block_time?: string | null;
  confirmed?: boolean | null;
  confirmations?: number | null;
  block_height?: number | null;
  block_hash?: string | null;
  size_bytes?: number | null;
  weight?: number | null;
  version?: number | null;
  locktime?: number | null;
  inputs: { prev_txid: string; prev_vout: number }[];
  outputs: {
    index: number;
    value_sats: number;
    address?: string | null;
    script_type?: string | null;
    script_hex?: string | null;
  }[];
  fee_sats: number | null;
  vsize: number | null;
  dataset_id?: string;
  source_record?: number;
};
export type Alert = {
  id: string;
  txid: string;
  title: string;
  severity: string;
  priority?: string;
  risk_score?: number;
  score: number;
  reasons: string[];
  alternative: string;
  detected_at?: string;
  reviewed_at?: string;
  first_detected_stage?: string;
  detection_stages?: string[];
  transaction_observed_at?: string | null;
  transaction_block_time?: string | null;
  detections?: Detection[];
  status: string;
  created_at: string;
  model_version?: string;
  dataset_id?: string;
  feature_contributions?: FeatureContribution[];
};
export type Dataset = {
  id: string;
  name: string;
  status: string;
  count: number;
  created_at: string;
  sha256?: string;
  error?: string;
  warnings?: string[];
  progress?: number;
  stage_events?: StageEvent[];
  current_stage?: string;
  synthetic?: boolean;
};
export type Case = {
  id: string;
  name: string;
  description: string;
  member_role: string;
  synthetic?: boolean;
};
export type User = { id: string; name: string; email: string; role: string };
export type Summary = {
  transactions: number;
  total_output_sats: number;
  alerts_count: number;
  high_priority: number;
  chart: { label: string; count: number }[];
  alerts: Alert[];
  datasets: Dataset[];
};
export type FeatureContribution = {
  feature: string;
  contribution: number;
  description: string;
  value: number;
};
export type Cluster = {
  id: string;
  cluster_id: string;
  type: 'wallet' | 'ip';
  size: number;
  addresses?: string[];
  ips?: string[];
  txid_count: number;
  txids: string[];
  high_alert_hits?: number;
  medium_alert_hits?: number;
  flagged_alert_hits?: number;
  risk_score: number;
  risk_level: 'high' | 'medium' | 'low';
  heuristic: string;
  countries?: string[];
  has_tor?: boolean;
  has_vpn?: boolean;
};
export type GeoCountry = {
  country: string;
  count: number;
  tor_count: number;
  vpn_count: number;
  asns: string[];
};
export type GeoSummary = {
  countries: GeoCountry[];
  total_observations: number;
  tor_observations: number;
  vpn_observations: number;
};
export type MLExplanation = {
  alert_id: string;
  txid: string;
  score: number;
  model_version: string;
  feature_contributions: FeatureContribution[];
  disclaimer: string;
};
export const short = (s: string, n = 7) =>
  s.length > n * 2 ? `${s.slice(0, n)}…${s.slice(-n)}` : s;
export const btc = (n: number) =>
  (n / 1e8).toLocaleString("en-US", { maximumFractionDigits: 5 });
export const demoTx: Tx[] = training.transactions.map((t, i) => ({
  ...t,
  dataset_id: "demo-dataset",
  source_record: i + 1,
}));
export const demoAlerts: Alert[] = [140, 100, 60, 20, 179, 178, 177].map(
  (i, k) => ({
    id: `alert-${i}`,
    txid: demoTx[i].txid,
    title: k < 4 ? "Unusual output fan-out" : "Elevated output count",
    severity: k < 4 ? "high" : "medium",
    score: 97 - k * 4,
    reasons: [
      `${demoTx[i].outputs.length} outputs created in one transaction.`,
      `Output count exceeds the configured review threshold.`,
      `Synthetic scenario supplied to illustrate investigation workflow.`,
    ],
    alternative:
      "Payment batching or wallet maintenance may explain this pattern. Ownership and intent are unknown.",
    status: k === 5 ? "reviewed" : "open",
    created_at: demoTx[i].observed_at!,
    model_version: "illustrative-demo-v1",
    dataset_id: "demo-dataset",
  }),
);
demoAlerts.forEach((a, index) => {
  const stage = index < 4 ? "rule_detection" : "model_scoring";
  const detected = new Date(
    Date.UTC(2026, 8, 1, 0, 0, stage === "rule_detection" ? 3 : 5),
  ).toISOString();
  a.transaction_observed_at = a.created_at;
  a.detected_at = detected;
  a.created_at = "2026-09-01T00:00:06Z";
  a.first_detected_stage = stage;
  a.detection_stages = [stage];
  if (index >= 4) {
    a.score = 98.8 - (index - 4) * 0.5;
    a.title = "Multivariate transaction anomaly";
  }
  const observed =
    index < 4 ? demoTx.find((t) => t.txid === a.txid)!.outputs.length : a.score;
  const threshold = index < 4 ? 10 : 97;
  const reason =
    index < 4
      ? `${observed} outputs meet the fan-out threshold of ${threshold}; demo baseline is 2.`
      : `Illustrative anomaly percentile ${observed} meets the review threshold of ${threshold}.`;
  a.detections = [
    {
      code: index < 4 ? "fan_out" : "isolation_forest",
      stage,
      detector:
        index < 4 ? "Count threshold rule" : "Isolation Forest (illustrative)",
      title: a.title,
      feature: index < 4 ? "output_count" : "anomaly_percentile",
      observed,
      operator: ">=",
      threshold,
      baseline: index < 4 ? 2 : null,
      unit: index < 4 ? "count" : "percentile",
      detected_at: detected,
      reason,
    },
  ];
  a.reasons = [
    reason,
    "Synthetic demonstration only; this is not a measured model result.",
  ];
});
export const demoCase: Case = {
  id: "demo",
  name: "Operation Northstar",
  description: "Synthetic Bitcoin activity · training investigation",
  member_role: "viewer",
  synthetic: true,
};
export const demoDataset: Dataset = {
  id: "demo-dataset",
  name: "northstar_training.json",
  status: "completed",
  count: demoTx.length,
  created_at: "2026-09-01T00:00:00Z",
  warnings: ["Synthetic data. Not live Bitcoin activity."],
  synthetic: true,
  stage_events: [
    "validation",
    "feature_engineering",
    "rule_detection",
    "model_scoring",
    "alert_generation",
  ].map((stage, i) => ({
    id: `demo-stage-${i}`,
    stage,
    status: "completed",
    at: new Date(Date.UTC(2026, 8, 1, 0, 0, [1, 2, 3, 5, 6][i])).toISOString(),
    detail: { note: "Illustrative synthetic stage event" },
  })),
};
export function demoSummary(): Summary {
  return {
    transactions: demoTx.length,
    total_output_sats: demoTx.reduce(
      (s, t) => s + t.outputs.reduce((v, o) => v + o.value_sats, 0),
      0,
    ),
    alerts_count: demoAlerts.length,
    high_priority: 4,
    chart: Array.from({ length: 24 }, (_, h) => ({
      label: `${h.toString().padStart(2, "0")}:00`,
      count: demoTx.filter((t) => new Date(t.observed_at!).getUTCHours() === h)
        .length,
    })),
    alerts: demoAlerts,
    datasets: [demoDataset],
  };
}
export function demoGraph(txid: string) {
  const center = demoTx.findIndex((t) => t.txid === txid);
  if (center < 0)
    throw new Error(
      "Transaction not found in the synthetic demo. Choose a transaction from the transaction list.",
    );
  const chosen = demoTx.slice(
    Math.max(0, center - 2),
    Math.min(demoTx.length, center + 3),
  );
  return {
    nodes: chosen.flatMap((t) => [
      {
        data: {
          id: t.txid,
          label: short(t.txid, 4),
          kind: "transaction",
          focus: t.txid === txid,
        },
      },
      ...t.outputs.slice(0, 5).map((o) => ({
        data: {
          id: `${t.txid}:${o.index}`,
          label: `${btc(o.value_sats)} BTC`,
          kind: "output",
          focus: false,
        },
      })),
    ]),
    edges: chosen.flatMap((t) => [
      ...t.outputs.slice(0, 5).map((o) => ({
        data: {
          id: `create:${t.txid}:${o.index}`,
          source: t.txid,
          target: `${t.txid}:${o.index}`,
          label: "creates",
        },
      })),
      ...t.inputs
        .filter((i) => chosen.some((p) => p.txid === i.prev_txid))
        .map((i) => ({
          data: {
            id: `spend:${t.txid}`,
            source: `${i.prev_txid}:${i.prev_vout}`,
            target: t.txid,
            label: "spent by",
          },
        })),
    ]),
    truncated: true,
  };
}
export async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-Sentinel-Request": "1",
      ...options.headers,
    },
  });
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(
        `Service temporarily unavailable (${response.status}). Please retry in a moment.`,
      );
    }
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Invalid request. Check the supplied fields.",
    );
  }
  return response.status === 204 ? null : response.json();
}
export function download(data: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const demoClusters: Cluster[] = [
  {
    id: "wc-demo-001",
    cluster_id: "wc-a1b2c3d4e5f6",
    type: "wallet",
    size: 8,
    addresses: [
      "synthetic-address-20-0","synthetic-address-20-1","synthetic-address-21-0",
      "synthetic-address-22-0","synthetic-address-60-0","synthetic-address-60-1",
      "synthetic-address-61-0","synthetic-address-62-0",
    ],
    txid_count: 6,
    txids: [demoTx[20]?.txid, demoTx[60]?.txid, demoTx[100]?.txid].filter(Boolean) as string[],
    high_alert_hits: 2,
    medium_alert_hits: 1,
    risk_score: 78.5,
    risk_level: "high",
    heuristic: "common_input_ownership+address_reuse",
  },
  {
    id: "wc-demo-002",
    cluster_id: "wc-b2c3d4e5f6a1",
    type: "wallet",
    size: 4,
    addresses: [
      "synthetic-address-100-0","synthetic-address-101-0",
      "synthetic-address-102-0","synthetic-address-140-0",
    ],
    txid_count: 4,
    txids: [demoTx[100]?.txid, demoTx[140]?.txid].filter(Boolean) as string[],
    high_alert_hits: 1,
    medium_alert_hits: 0,
    risk_score: 42.0,
    risk_level: "medium",
    heuristic: "common_input_ownership+address_reuse",
  },
  {
    id: "ic-demo-001",
    cluster_id: "ic-c3d4e5f6a1b2",
    type: "ip",
    size: 3,
    ips: ["185.220.101.1", "185.220.102.4", "185.220.101.15"],
    txid_count: 4,
    txids: [demoTx[20]?.txid, demoTx[60]?.txid].filter(Boolean) as string[],
    flagged_alert_hits: 2,
    risk_score: 80.0,
    risk_level: "high",
    heuristic: "ip_txid_cooccurrence",
    countries: ["XX"],
    has_tor: true,
    has_vpn: false,
  },
  {
    id: "ic-demo-002",
    cluster_id: "ic-d4e5f6a1b2c3",
    type: "ip",
    size: 2,
    ips: ["46.148.1.10", "81.19.3.30"],
    txid_count: 3,
    txids: [demoTx[100]?.txid].filter(Boolean) as string[],
    flagged_alert_hits: 1,
    risk_score: 35.0,
    risk_level: "medium",
    heuristic: "ip_txid_cooccurrence",
    countries: ["RU"],
    has_tor: false,
    has_vpn: false,
  },
];

export const demoGeoSummary: GeoSummary = {
  countries: [
    { country: "RU", count: 18, tor_count: 0, vpn_count: 3, asns: ["AS12389"] },
    { country: "NL", count: 14, tor_count: 0, vpn_count: 12, asns: ["AS60068", "AS9009"] },
    { country: "US", count: 22, tor_count: 0, vpn_count: 2, asns: ["AS16509", "AS15169"] },
    { country: "CN", count: 11, tor_count: 0, vpn_count: 0, asns: ["AS4134", "AS4837"] },
    { country: "DE", count: 8, tor_count: 0, vpn_count: 0, asns: ["AS3320"] },
    { country: "XX", count: 6, tor_count: 6, vpn_count: 0, asns: ["AS9009"] },
  ],
  total_observations: 79,
  tor_observations: 6,
  vpn_observations: 17,
};

export const demoMLExplain = (alert: Alert): MLExplanation => ({
  alert_id: alert.id,
  txid: alert.txid,
  score: alert.score,
  model_version: alert.model_version || "illustrative-demo-v1",
  feature_contributions: [
    { feature: "output_count", contribution: 0.42, description: "Number of outputs (high = fan-out/mixing)", value: alert.detections?.[0]?.observed ?? 16 },
    { feature: "output_value_entropy", contribution: 0.21, description: "Shannon entropy of output values", value: 3.84 },
    { feature: "largest_output_share", contribution: -0.11, description: "Fraction of value in largest output", value: 0.18 },
    { feature: "log_output_total", contribution: 0.08, description: "Log of total output value in satoshis", value: 12.4 },
    { feature: "fee_rate_missing", contribution: 0.05, description: "Binary: fee data absent from record", value: 0 },
    { feature: "round_output_fraction", contribution: 0.04, description: "Fraction of outputs with round BTC values", value: 0.06 },
    { feature: "input_count", contribution: -0.03, description: "Number of inputs", value: 1 },
    { feature: "is_off_hours", contribution: 0.02, description: "Binary: observed between 00:00–05:00 UTC", value: 0 },
  ],
  disclaimer: "DEMO — illustrative contributions only. Not measured model output.",
});

