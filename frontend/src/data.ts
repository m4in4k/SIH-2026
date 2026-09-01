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
        `Server unavailable (${response.status}). Check that FastAPI is running.`,
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
