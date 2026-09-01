import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronRight,
  Clock,
  Copy,
  Filter,
  Info,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  api,
  btc,
  demoTx,
  demoDataset,
  short,
  type Tx,
  type Alert,
  type Dataset,
  type Detection,
  type StageEvent,
} from "./data";
export const stageName = (stage?: string) =>
  ({
    validation: "Validation",
    feature_engineering: "Feature engineering",
    rule_detection: "Rule detection",
    model_scoring: "Model scoring",
    alert_generation: "Alert generation",
  })[stage || ""] || "Not recorded";
export const utc = (s?: string | null) =>
  s
    ? new Date(s).toISOString().replace("T", " ").replace("Z", " UTC")
    : "Not supplied";
const amount = (n?: number | null) =>
  n == null ? "Unknown" : `${n.toLocaleString("en-US")} sat`;
export function StagePill({ stage }: { stage?: string }) {
  return (
    <span className={`stage-pill ${stage || "unknown"}`}>
      {stageName(stage)}
    </span>
  );
}
export function DetectionEvidence({
  alert,
  dataset,
}: {
  alert: Alert;
  dataset?: Dataset;
}) {
  const signals = alert.detections || [];
  return (
    <section className="detection-evidence">
      <div className="section-label">DETECTION RECORD</div>
      <div className="detection-summary">
        <div>
          <small>First flagged during</small>
          <StagePill stage={alert.first_detected_stage} />
        </div>
        <div>
          <small>Detected at</small>
          <span>{utc(alert.detected_at)}</span>
        </div>
      </div>
      {!signals.length && (
        <div className="safeguard">
          <Info size={16} />
          <p>
            This legacy alert did not record its detection stage or processing
            timestamp. Existing reasons remain available; transaction time is
            not substituted for detection time.
          </p>
        </div>
      )}
      {signals.map((d, i) => (
        <article className="signal-card" key={`${d.code}-${i}`}>
          <div>
            <strong>{d.title}</strong>
            <StagePill stage={d.stage} />
          </div>
          <p>{d.reason}</p>
          <div className="evidence-values">
            <span>
              <small>Observed</small>
              <b>
                {d.observed} {d.unit}
              </b>
            </span>
            <span>
              <small>Threshold</small>
              <b>
                {d.operator} {d.threshold}
              </b>
            </span>
            <span>
              <small>Dataset median</small>
              <b>{d.baseline ?? "Not applicable"}</b>
            </span>
          </div>
          <small>
            {d.detector} · {utc(d.detected_at)}
          </small>
        </article>
      ))}
      <div className="pipeline-strip">
        {[
          "validation",
          "feature_engineering",
          "rule_detection",
          "model_scoring",
          "alert_generation",
        ].map((stage) => (
          <div
            key={stage}
            className={
              alert.detection_stages?.includes(stage) ? "triggered" : ""
            }
          >
            <i />
            <span>{stageName(stage)}</span>
            {alert.detection_stages?.includes(stage) && <b>Signal detected</b>}
          </div>
        ))}
      </div>
      <p className="micro-copy">
        Highlighted stages produced this alert. The stage order shows the
        pipeline, not proof that every stage ran.
      </p>
      {dataset?.stage_events?.length ? (
        <details className="stage-history">
          <summary>
            Recorded pipeline activity · {dataset.stage_events.length} events
          </summary>
          {dataset.stage_events.map((e) => (
            <div key={e.id}>
              <StagePill stage={e.stage} />
              <span>{e.status}</span>
              <time>{utc(e.at)}</time>
            </div>
          ))}
        </details>
      ) : null}
    </section>
  );
}
type Fields = Record<string, string>;
const initial: Fields = {
  time_basis: "observed_at",
  confirmation: "all",
  alert_state: "all",
  sort: "txid",
  severity: "all",
  status: "all",
  stage: "all",
};
function params(fields: Fields) {
  const p = new URLSearchParams();
  Object.entries(fields).forEach(([k, v]) => {
    if (v && v !== "all")
      p.set(
        k,
        k === "date_from" || k === "date_to"
          ? new Date(v + "Z").toISOString()
          : v,
      );
  });
  return p;
}
function validate(fields: Fields) {
  for (const [a, b] of [
    ["min_sats", "max_sats"],
    ["min_fee_rate", "max_fee_rate"],
    ["min_inputs", "max_inputs"],
    ["min_outputs", "max_outputs"],
  ])
    if (fields[a] && fields[b] && Number(fields[a]) > Number(fields[b]))
      throw new Error("Minimum values must not exceed maximum values.");
  if (fields.date_from && fields.date_to && fields.date_from > fields.date_to)
    throw new Error("Start time must precede end time.");
}
function matchesTx(t: Tx, f: Fields, alerts: Alert[]) {
  const total = t.outputs.reduce((s, o) => s + o.value_sats, 0),
    rate = t.fee_sats != null && t.vsize ? t.fee_sats / t.vsize : null;
  for (const [lo, hi, value] of [
    ["min_sats", "max_sats", total],
    ["min_fee_rate", "max_fee_rate", rate],
    ["min_inputs", "max_inputs", t.inputs.length],
    ["min_outputs", "max_outputs", t.outputs.length],
  ] as [string, string, number | null][]) {
    if ((f[lo] || f[hi]) && value == null) return false;
    if (f[lo] && value! < Number(f[lo])) return false;
    if (f[hi] && value! > Number(f[hi])) return false;
  }
  const when = f.time_basis === "block_time" ? t.block_time : t.observed_at;
  if ((f.date_from || f.date_to) && !when) return false;
  if (
    f.date_from &&
    new Date(when!).getTime() < new Date(f.date_from + "Z").getTime()
  )
    return false;
  if (
    f.date_to &&
    new Date(when!).getTime() > new Date(f.date_to + "Z").getTime()
  )
    return false;
  if (f.dataset_id && t.dataset_id !== f.dataset_id) return false;
  if (f.confirmation === "confirmed" && t.confirmed !== true) return false;
  if (f.confirmation === "unconfirmed" && t.confirmed !== false) return false;
  if (f.confirmation === "unknown" && t.confirmed != null) return false;
  if (f.script_type && !t.outputs.some((o) => o.script_type === f.script_type))
    return false;
  const flagged = alerts.some((a) => a.txid === t.txid);
  if (
    (f.alert_state === "flagged" && !flagged) ||
    (f.alert_state === "unflagged" && flagged)
  )
    return false;
  return true;
}
function FilterFields({
  fields,
  setFields,
  datasets,
  alerts,
}: {
  fields: Fields;
  setFields: (v: Fields) => void;
  datasets: Dataset[];
  alerts: boolean;
}) {
  const set = (key: string, v: string) => setFields({ ...fields, [key]: v });
  const input = (key: string, label: string, type = "number") => (
    <label key={key}>
      {label}
      <input
        type={type}
        min={type === "number" ? 0 : undefined}
        step={key.includes("fee") || key === "min_score" ? "any" : undefined}
        value={fields[key] || ""}
        onChange={(e) => set(key, e.target.value)}
      />
    </label>
  );
  const select = (key: string, label: string, options: [string, string][]) => (
    <label key={key}>
      {label}
      <select
        value={fields[key] || ""}
        onChange={(e) => set(key, e.target.value)}
      >
        {options.map(([v, l]) => (
          <option value={v} key={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <div className="advanced-fields">
      {select("dataset_id", "Dataset", [
        ["", "All datasets"],
        ...datasets.map((d) => [d.id, d.name] as [string, string]),
      ])}
      {select("time_basis", "Transaction time basis", [
        ["observed_at", "Observation time"],
        ["block_time", "Reported block time"],
      ])}
      {input("date_from", "From (UTC)", "datetime-local")}
      {input("date_to", "Through (UTC)", "datetime-local")}
      {input("min_sats", "Min output total (sat)")}
      {input("max_sats", "Max output total (sat)")}
      {input("min_fee_rate", "Min fee rate (sat/vB)")}
      {input("max_fee_rate", "Max fee rate (sat/vB)")}
      {input("min_inputs", "Min inputs")}
      {input("max_inputs", "Max inputs")}
      {input("min_outputs", "Min outputs")}
      {input("max_outputs", "Max outputs")}
      {select("confirmation", "Confirmation snapshot", [
        ["all", "All states"],
        ["confirmed", "Reported confirmed"],
        ["unconfirmed", "Reported unconfirmed"],
        ["unknown", "Not supplied"],
      ])}
      {select("script_type", "Output script type", [
        ["", "Any script"],
        ["p2wpkh", "P2WPKH"],
        ["p2pkh", "P2PKH"],
        ["p2sh", "P2SH"],
        ["p2tr", "P2TR"],
        ["p2wsh", "P2WSH"],
        ["op_return", "OP_RETURN"],
      ])}
      {!alerts &&
        select("alert_state", "Anomaly signals", [
          ["all", "All transactions"],
          ["flagged", "Has alerts"],
          ["unflagged", "No alerts"],
        ])}
      {!alerts &&
        select("sort", "Sort order", [
          ["txid", "Transaction ID"],
          ["time_desc", "Newest transaction time"],
          ["value_desc", "Largest output total"],
          ["fee_desc", "Highest fee rate"],
        ])}
      {alerts &&
        select("severity", "Priority", [
          ["all", "All priorities"],
          ["high", "High"],
          ["medium", "Medium"],
        ])}
      {alerts &&
        select("status", "Review status", [
          ["all", "All statuses"],
          ["open", "Needs review"],
          ["reviewed", "Reviewed"],
        ])}
      {alerts &&
        select("stage", "Detected during", [
          ["all", "Any stage"],
          ["rule_detection", "Rule detection"],
          ["model_scoring", "Model scoring"],
          ["unknown", "Stage not recorded"],
        ])}
      {alerts && input("min_score", "Minimum model percentile")}
    </div>
  );
}
export function RecordsView({
  mode,
  caseId,
  demo,
  datasets,
  alerts,
  onTx,
  onAlert,
}: {
  mode: "transactions" | "alerts";
  caseId: string;
  demo: boolean;
  datasets: Dataset[];
  alerts: Alert[];
  onTx: (t: Tx) => void;
  onAlert: (a: Alert) => void;
}) {
  const [fields, setFields] = useState<Fields>({ ...initial }),
    [q, setQ] = useState(""),
    [open, setOpen] = useState(false),
    [offset, setOffset] = useState(0),
    [items, setItems] = useState<(Tx | Alert)[]>([]),
    [total, setTotal] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const change = (f: Fields) => {
    setFields(f);
    setOffset(0);
  };
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError("");
    const timer = setTimeout(async () => {
      try {
        validate(fields);
        let result;
        if (demo) {
          let tx = demoTx.filter((t) => matchesTx(t, fields, alerts));
          let rows: (Tx | Alert)[];
          if (mode === "transactions") {
            tx = tx.filter((t) =>
              (t.txid + " " + t.outputs.map((o) => o.address).join(" "))
                .toLowerCase()
                .includes(q.toLowerCase()),
            );
            tx.sort((a, b) =>
              fields.sort === "value_desc"
                ? b.outputs.reduce((s, o) => s + o.value_sats, 0) -
                  a.outputs.reduce((s, o) => s + o.value_sats, 0)
                : fields.sort === "fee_desc"
                  ? (b.fee_sats != null && b.vsize
                      ? b.fee_sats / b.vsize
                      : -1) -
                    (a.fee_sats != null && a.vsize ? a.fee_sats / a.vsize : -1)
                  : fields.sort === "time_desc"
                    ? String(
                        fields.time_basis === "block_time"
                          ? b.block_time
                          : b.observed_at,
                      ).localeCompare(
                        String(
                          fields.time_basis === "block_time"
                            ? a.block_time
                            : a.observed_at,
                        ),
                      )
                    : a.txid.localeCompare(b.txid),
            );
            rows = tx;
          } else {
            const ids = new Set(tx.map((t) => t.txid));
            rows = alerts.filter(
              (a) =>
                ids.has(a.txid) &&
                (a.title + " " + a.txid + " " + a.reasons.join(" "))
                  .toLowerCase()
                  .includes(q.toLowerCase()) &&
                (fields.severity === "all" || fields.severity === a.severity) &&
                (fields.status === "all" || fields.status === a.status) &&
                (fields.stage === "all" ||
                  (fields.stage === "unknown" && !a.first_detected_stage) ||
                  a.detection_stages?.includes(fields.stage)) &&
                (!fields.min_score ||
                  (!a.model_version?.startsWith("rules-only") &&
                    a.score >= Number(fields.min_score))),
            );
          }
          result = {
            items: rows.slice(offset, offset + 25),
            total: rows.length,
          };
        } else if (!caseId) {
          result = { items: [], total: 0 };
        } else {
          const p = params({ ...fields, q, offset: String(offset) });
          if (mode === "transactions") {
            ["stage", "severity", "status", "min_score"].forEach((k) =>
              p.delete(k),
            );
          }
          result = await api(
            `/cases/${caseId}/${mode === "transactions" ? "transaction-search" : "alert-search"}?${p}`,
          );
        }
        if (active) {
          setItems(result.items);
          setTotal(result.total);
        }
      } catch (e) {
        if (active) {
          setError((e as Error).message);
          setItems([]);
          setTotal(0);
        }
      } finally {
        if (active) setBusy(false);
      }
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [fields, q, offset, caseId, demo, mode, alerts]);
  const count = Object.entries(fields).filter(
    ([k, v]) => v && v !== "all" && v !== initial[k],
  ).length;
  return (
    <section className="panel">
      <div className="toolbar">
        <label className="search wide">
          <Search size={17} />
          <input
            aria-label={`Search ${mode}`}
            placeholder={
              mode === "transactions"
                ? "Search TXID or output address…"
                : "Search anomaly, reason, or TXID…"
            }
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <button
          className={`button ${open ? "filter-active" : ""}`}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <Filter size={15} />
          Advanced filters{count > 0 && <b className="count-bubble">{count}</b>}
        </button>
      </div>
      {open && (
        <>
          <FilterFields
            fields={fields}
            setFields={change}
            datasets={datasets}
            alerts={mode === "alerts"}
          />
          <div className="filter-footnote">
            <span>
              Ranges are inclusive. Missing values do not match numeric/date
              filters. Output totals include change.
            </span>
            <button
              className="text-button"
              onClick={() => {
                change({ ...initial });
                setQ("");
              }}
            >
              Reset filters
            </button>
          </div>
        </>
      )}
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div
        className={`table-scroll ${busy ? "results-loading" : ""}`}
        aria-busy={busy}
      >
        <table>
          <thead>
            <tr>
              {mode === "transactions" ? (
                <>
                  <th>Transaction ID</th>
                  <th>Confirmation snapshot</th>
                  <th>Inputs → outputs</th>
                  <th>Output total</th>
                  <th>Fee rate</th>
                  <th />
                </>
              ) : (
                <>
                  <th>Anomaly / transaction</th>
                  <th>First detected during</th>
                  <th>Detected at (UTC)</th>
                  <th>Model score</th>
                  <th>Status</th>
                  <th />
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {items.map((row) =>
              mode === "transactions"
                ? (() => {
                    const t = row as Tx;
                    return (
                      <tr key={t.txid} onClick={() => onTx(t)}>
                        <td>
                          <button
                            className="text-button mono"
                            onClick={() => onTx(t)}
                          >
                            {short(t.txid)}
                          </button>
                          <span className="sub">
                            {t.dataset_id &&
                              datasets.find((d) => d.id === t.dataset_id)?.name}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`badge ${t.confirmed === true ? "completed" : ""}`}
                          >
                            {t.confirmed == null
                              ? "Not supplied"
                              : t.confirmed
                                ? "Confirmed"
                                : "Unconfirmed"}
                          </span>
                        </td>
                        <td>
                          {t.inputs.length} → {t.outputs.length}
                        </td>
                        <td>
                          {btc(t.outputs.reduce((s, o) => s + o.value_sats, 0))}{" "}
                          BTC
                        </td>
                        <td>
                          {t.fee_sats != null && t.vsize
                            ? `${(t.fee_sats / t.vsize).toFixed(2)} sat/vB`
                            : "Unknown"}
                        </td>
                        <td>
                          <ChevronRight size={15} />
                        </td>
                      </tr>
                    );
                  })()
                : (() => {
                    const a = row as Alert;
                    return (
                      <tr key={a.id} onClick={() => onAlert(a)}>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => onAlert(a)}
                          >
                            {a.title}
                          </button>
                          <span className="mono sub">{short(a.txid)}</span>
                          <span className={`badge ${a.severity}`}>
                            {a.severity}
                          </span>
                        </td>
                        <td>
                          <StagePill stage={a.first_detected_stage} />
                          {(a.detection_stages?.length || 0) > 1 && (
                            <span className="sub">Also flagged by model</span>
                          )}
                        </td>
                        <td className="mono">
                          {a.detected_at
                            ? utc(a.detected_at).replace(" UTC", "")
                            : "Not recorded"}
                        </td>
                        <td>
                          {a.model_version?.startsWith("rules-only")
                            ? "Not scored"
                            : `${a.score}/100`}
                        </td>
                        <td>
                          <span className={`status ${a.status}`}>
                            <i />
                            {a.status === "open" ? "Needs review" : "Reviewed"}
                          </span>
                        </td>
                        <td>
                          <ChevronRight size={15} />
                        </td>
                      </tr>
                    );
                  })(),
            )}
          </tbody>
        </table>
      </div>
      {!items.length && (
        <div className="empty">
          <Search />
          <h3>{busy ? "Searching…" : "No matching records"}</h3>
          <p>
            {busy
              ? "Applying your filters."
              : "Change the filters or import a dataset."}
          </p>
        </div>
      )}
      <div className="table-footer">
        <span>
          {total} matching {mode} ·{" "}
          {demo ? "Synthetic demo" : "Case-scoped records"}
        </span>
        <div className="pagination">
          <button
            className="button small"
            disabled={offset === 0 || busy}
            onClick={() => setOffset(Math.max(0, offset - 25))}
          >
            Previous
          </button>
          <span>
            {total ? offset + 1 : 0}–{Math.min(offset + 25, total)}
          </span>
          <button
            className="button small"
            disabled={offset + 25 >= total || busy}
            onClick={() => setOffset(offset + 25)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
type Detail = {
  transaction: Tx;
  dataset: Dataset;
  alerts: Alert[];
  inputs: (Tx["inputs"][number] & {
    resolved: boolean;
    previous_output: Tx["outputs"][number] | null;
  })[];
  outputs: (Tx["outputs"][number] & { spending_txids: string[] })[];
  metrics: {
    output_total_sats: number;
    resolved_input_count: number;
    input_total_sats: number | null;
    fee_rate_sat_vb: number | null;
  };
  observations: {
    sensor: string;
    peer_ip: string;
    peer_port: number;
    observed_at: string;
  }[];
  spenders_truncated: boolean;
};
export function TransactionDrawer({
  txid,
  caseId,
  demo,
  alerts,
  onClose,
  onTrace,
  onSelect,
  onAlert,
}: {
  txid: string;
  caseId: string;
  demo: boolean;
  alerts: Alert[];
  onClose: () => void;
  onTrace: (id: string) => void;
  onSelect: (id: string) => void;
  onAlert: (a: Alert) => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  useEffect(() => {
    let active = true;
    setDetail(null);
    setError("");
    setCopied(false);
    Promise.resolve()
      .then(() => {
        if (!demo) return api(`/cases/${caseId}/transaction-details/${txid}`);
        const t = demoTx.find((t) => t.txid === txid);
        if (!t)
          throw new Error("Transaction not available in this synthetic demo.");
        const inputs = t.inputs.map((i) => {
          const o = demoTx
            .find((x) => x.txid === i.prev_txid)
            ?.outputs.find((o) => o.index === i.prev_vout);
          return { ...i, resolved: !!o, previous_output: o || null };
        });
        return {
          transaction: t,
          dataset: demoDataset,
          alerts: alerts.filter((a) => a.txid === txid),
          inputs,
          outputs: t.outputs.map((o) => ({
            ...o,
            spending_txids: demoTx
              .filter((x) =>
                x.inputs.some(
                  (i) => i.prev_txid === txid && i.prev_vout === o.index,
                ),
              )
              .map((x) => x.txid),
          })),
          metrics: {
            output_total_sats: t.outputs.reduce((s, o) => s + o.value_sats, 0),
            resolved_input_count: inputs.filter((i) => i.resolved).length,
            input_total_sats:
              inputs.length && inputs.every((i) => i.resolved)
                ? inputs.reduce((s, i) => s + i.previous_output!.value_sats, 0)
                : null,
            fee_rate_sat_vb:
              t.fee_sats != null && t.vsize ? t.fee_sats / t.vsize : null,
          },
          observations: [],
          spenders_truncated: false,
        };
      })
      .then((d) => active && setDetail(d))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [txid, caseId, demo, alerts]);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, [onClose]);
  const t = detail?.transaction;
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside
        className="drawer rich-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="transaction-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-top">
          <span className="eyebrow">TRANSACTION EVIDENCE</span>
          <button
            className="icon-button"
            aria-label="Close transaction"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <h2 id="transaction-title">Inspect the complete record.</h2>
        <p className="mono break">{txid}</p>
        <button
          className="text-button copy-id"
          onClick={() =>
            navigator.clipboard
              .writeText(txid)
              .then(() => setCopied(true))
              .catch(() =>
                setError(
                  "Clipboard unavailable. Select and copy the transaction ID above.",
                ),
              )
          }
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}{" "}
          {copied ? "Copied" : "Copy transaction ID"}
        </button>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        {!detail && !error && (
          <div className="empty">Loading transaction evidence…</div>
        )}
        {detail && t && (
          <>
            <div className="transaction-metrics">
              <div>
                <small>Output total · includes change</small>
                <strong>{btc(detail.metrics.output_total_sats)} BTC</strong>
                <span>{amount(detail.metrics.output_total_sats)}</span>
              </div>
              <div>
                <small>Fee rate</small>
                <strong>
                  {detail.metrics.fee_rate_sat_vb == null
                    ? "Unknown"
                    : `${detail.metrics.fee_rate_sat_vb.toFixed(3)} sat/vB`}
                </strong>
                <span>Supplied fee: {amount(t.fee_sats)}</span>
              </div>
            </div>
            <h3>
              Chain metadata{" "}
              <small>Supplied snapshot, not live chain state</small>
            </h3>
            <dl className="rich-metadata">
              <dt>Confirmation status</dt>
              <dd>
                {t.confirmed == null
                  ? "Not supplied"
                  : t.confirmed
                    ? "Reported confirmed"
                    : "Reported unconfirmed"}
              </dd>
              <dt>Confirmations</dt>
              <dd>{t.confirmations ?? "Not supplied"}</dd>
              <dt>Block height</dt>
              <dd>{t.block_height ?? "Not supplied"}</dd>
              <dt>Block hash</dt>
              <dd className="mono">{t.block_hash ?? "Not supplied"}</dd>
              <dt>Observation time</dt>
              <dd>{utc(t.observed_at)}</dd>
              <dt>Reported block time</dt>
              <dd>{utc(t.block_time)}</dd>
              <dt>Size / virtual size</dt>
              <dd>
                {t.size_bytes ?? "Unknown"} bytes / {t.vsize ?? "Unknown"} vB
              </dd>
              <dt>Weight</dt>
              <dd>
                {t.weight ?? "Not supplied"}
                {t.weight != null ? " WU" : ""}
              </dd>
              <dt>Version / locktime</dt>
              <dd>
                {t.version ?? "Unknown"} / {t.locktime ?? "Unknown"}
              </dd>
            </dl>
            <h3>Detected anomalies · {detail.alerts.length}</h3>
            {detail.alerts.length ? (
              detail.alerts.map((a) => (
                <button
                  className="linked-alert"
                  key={a.id}
                  onClick={() => onAlert(a)}
                >
                  <span>
                    <strong>{a.title}</strong>
                    <small>{a.reasons[0]}</small>
                    <StagePill stage={a.first_detected_stage} />
                  </span>
                  <ChevronRight size={17} />
                </button>
              ))
            ) : (
              <p className="micro-copy">
                No alerts were generated for this transaction. This is not a
                finding of legitimacy.
              </p>
            )}
            <h3>Inputs · {detail.inputs.length}</h3>
            <p className="micro-copy">
              {detail.metrics.resolved_input_count} of {detail.inputs.length}{" "}
              input references resolved within this case. Input total:{" "}
              {amount(detail.metrics.input_total_sats)}.
            </p>
            {!detail.inputs.length && (
              <p className="micro-copy">
                No inputs supplied. This alone does not verify a coinbase
                transaction.
              </p>
            )}
            {detail.inputs.map((i, n) => (
              <div className="reference-card" key={n}>
                <div>
                  <small>
                    INPUT {n} ·{" "}
                    {i.resolved ? "RESOLVED" : "OUTSIDE AVAILABLE EVIDENCE"}
                  </small>
                  <button
                    disabled={!i.resolved}
                    className="text-button mono"
                    onClick={() => onSelect(i.prev_txid)}
                  >
                    {short(i.prev_txid, 12)}:{i.prev_vout}{" "}
                    <ArrowRight size={12} />
                  </button>
                </div>
                <strong>{amount(i.previous_output?.value_sats)}</strong>
                {i.previous_output?.address && (
                  <p className="mono break">{i.previous_output.address}</p>
                )}
              </div>
            ))}
            <h3>Outputs · {detail.outputs.length}</h3>
            {detail.outputs.map((o) => (
              <div className="reference-card" key={o.index}>
                <div>
                  <small>OUTPUT {o.index}</small>
                  <strong>{amount(o.value_sats)}</strong>
                </div>
                <p className="mono break">
                  {o.address || "No decoded address supplied"}
                </p>
                <span className="chip">
                  {o.script_type || "Script type not supplied"}
                </span>
                {o.script_hex && (
                  <details>
                    <summary>Script hex</summary>
                    <p className="mono break">{o.script_hex}</p>
                  </details>
                )}
                {o.spending_txids.map((id) => (
                  <button
                    key={id}
                    className="text-button mono spending-link"
                    onClick={() => onSelect(id)}
                  >
                    Observed spender: {short(id, 10)} <ArrowRight size={12} />
                  </button>
                ))}
                {!o.spending_txids.length && (
                  <small>
                    No spending transaction in the available case data; not
                    proof this output is unspent.
                  </small>
                )}
              </div>
            ))}
            {detail.spenders_truncated && (
              <p className="micro-copy">
                Spending references are limited to 1,000 candidate records.
              </p>
            )}
            <h3>Source and processing lineage</h3>
            <dl className="rich-metadata">
              <dt>Dataset</dt>
              <dd>{detail.dataset.name}</dd>
              <dt>Source record</dt>
              <dd>{t.source_record ?? "Not supplied"}</dd>
              <dt>SHA-256</dt>
              <dd className="mono">
                {detail.dataset.sha256 ||
                  "Synthetic browser demo — no imported file hash"}
              </dd>
              <dt>Imported at</dt>
              <dd>{utc(detail.dataset.created_at)}</dd>
            </dl>
            <details className="stage-history">
              <summary>
                Pipeline history · {detail.dataset.stage_events?.length || 0}{" "}
                records
              </summary>
              {detail.dataset.stage_events?.length ? (
                detail.dataset.stage_events.map((e) => (
                  <div key={e.id}>
                    <StagePill stage={e.stage} />
                    <span>{e.status}</span>
                    <time>{utc(e.at)}</time>
                  </div>
                ))
              ) : (
                <p>
                  No processing-stage timestamps were recorded for this legacy
                  dataset.
                </p>
              )}
            </details>
            {detail.observations.length > 0 && (
              <>
                <h3>Network observations</h3>
                <p className="micro-copy">
                  A relaying peer is not necessarily the originator or wallet
                  owner.
                </p>
                {detail.observations.map((o, i) => (
                  <div className="reference-card" key={i}>
                    <strong>
                      {o.peer_ip}:{o.peer_port}
                    </strong>
                    <small>
                      {o.sensor} · {utc(o.observed_at)}
                    </small>
                  </div>
                ))}
              </>
            )}
            <button
              className="button primary full"
              onClick={() => onTrace(txid)}
            >
              Trace transaction graph <ArrowRight size={15} />
            </button>
          </>
        )}
      </aside>
    </div>
  );
}
type Event = {
  id: string;
  type: string;
  title: string;
  at: string;
  stage?: string;
  txid?: string;
  alert_id?: string;
  dataset_id?: string;
  detail: Record<string, unknown>;
};
function demoEvents(alerts: Alert[]): Event[] {
  return [
    ...demoTx.flatMap((t) => [
      {
        id: t.txid + ":observation",
        type: "observation",
        title: "Transaction observed",
        at: t.observed_at!,
        txid: t.txid,
        dataset_id: t.dataset_id,
        detail: { source_record: t.source_record, time_basis: "observed_at" },
      },
      ...(t.block_time
        ? [
            {
              id: t.txid + ":block",
              type: "block",
              title: "Reported block time",
              at: t.block_time,
              txid: t.txid,
              dataset_id: t.dataset_id,
              detail: { time_basis: "block_time" },
            },
          ]
        : []),
    ]),
    ...(demoDataset.stage_events || []).map((e) => ({
      id: e.id,
      type: "pipeline",
      title: stageName(e.stage) + " · " + e.status,
      at: e.at,
      stage: e.stage,
      dataset_id: demoDataset.id,
      detail: { ...e.detail, status: e.status },
    })),
    ...alerts.flatMap((a) => [
      ...(a.detections || []).map((d, i) => ({
        id: a.id + ":" + i,
        type: "detection",
        title: d.title,
        at: d.detected_at,
        stage: d.stage,
        txid: a.txid,
        alert_id: a.id,
        dataset_id: a.dataset_id,
        detail: {
          reason: d.reason,
          observed: d.observed,
          threshold: d.threshold,
          detector: d.detector,
        },
      })),
      ...(a.reviewed_at
        ? [
            {
              id: a.id + ":review",
              type: "audit",
              title: "Alert reviewed (demo session)",
              at: a.reviewed_at,
              txid: a.txid,
              alert_id: a.id,
              dataset_id: a.dataset_id,
              detail: { status: a.status },
            },
          ]
        : []),
    ]),
  ];
}
export function Timeline({
  caseId,
  demo,
  datasets,
  alerts,
  onTx,
  onAlert,
}: {
  caseId: string;
  demo: boolean;
  datasets: Dataset[];
  alerts: Alert[];
  onTx: (id: string) => void;
  onAlert: (id: string) => void;
}) {
  const [fields, setFields] = useState<Fields>({
      event_type: "all",
      stage: "all",
    }),
    [offset, setOffset] = useState(0),
    [events, setEvents] = useState<Event[]>([]),
    [total, setTotal] = useState(0),
    [limited, setLimited] = useState(false),
    [legacy, setLegacy] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const change = (k: string, v: string) => {
    setFields({ ...fields, [k]: v });
    setOffset(0);
  };
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError("");
    const timer = setTimeout(async () => {
      try {
        validate(fields);
        let result;
        if (demo) {
          const all = demoEvents(alerts)
            .filter(
              (e) =>
                (fields.event_type === "all" || e.type === fields.event_type) &&
                (fields.stage === "all" || e.stage === fields.stage) &&
                (!fields.dataset_id || e.dataset_id === fields.dataset_id) &&
                (!fields.q ||
                  (e.title + " " + e.txid + " " + JSON.stringify(e.detail))
                    .toLowerCase()
                    .includes(fields.q.toLowerCase())) &&
                (!fields.date_from ||
                  new Date(e.at) >= new Date(fields.date_from + "Z")) &&
                (!fields.date_to ||
                  new Date(e.at) <= new Date(fields.date_to + "Z")),
            )
            .sort(
              (a, b) => b.at.localeCompare(a.at) || b.id.localeCompare(a.id),
            );
          result = {
            items: all.slice(offset, offset + 50),
            total: all.length,
            source_limit_reached: false,
            legacy_alerts_without_detection_time: 0,
          };
        } else if (!caseId) result = { items: [], total: 0 };
        else
          result = await api(
            `/cases/${caseId}/timeline?${params({ ...fields, offset: String(offset) })}`,
          );
        if (active) {
          setEvents(result.items);
          setTotal(result.total);
          setLimited(!!result.source_limit_reached);
          setLegacy(result.legacy_alerts_without_detection_time || 0);
        }
      } catch (e) {
        if (active) {
          setError((e as Error).message);
          setEvents([]);
        }
      } finally {
        if (active) setBusy(false);
      }
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [caseId, demo, fields, offset, alerts]);
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <div>
          <h2>From observation to investigation</h2>
          <p>
            Newest first · all times in UTC · source events and processing
            events remain separate
          </p>
        </div>
        <Clock size={20} />
      </div>
      <div className="timeline-filters">
        <label>
          Event type
          <select
            value={fields.event_type}
            onChange={(e) => change("event_type", e.target.value)}
          >
            {[
              ["all", "All events"],
              ["observation", "Transaction observations"],
              ["block", "Reported block times"],
              ["network", "Network observations"],
              ["pipeline", "Processing stages"],
              ["detection", "Anomalies detected"],
              ["audit", "Investigation actions"],
            ].map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Stage
          <select
            value={fields.stage}
            onChange={(e) => change("stage", e.target.value)}
          >
            <option value="all">All stages</option>
            {[
              "validation",
              "feature_engineering",
              "rule_detection",
              "model_scoring",
              "alert_generation",
            ].map((s) => (
              <option key={s} value={s}>
                {stageName(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Dataset
          <select
            value={fields.dataset_id || ""}
            onChange={(e) => change("dataset_id", e.target.value)}
          >
            <option value="">All datasets</option>
            {datasets.map((d) => (
              <option value={d.id} key={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          From (UTC)
          <input
            type="datetime-local"
            value={fields.date_from || ""}
            onChange={(e) => change("date_from", e.target.value)}
          />
        </label>
        <label>
          Through (UTC)
          <input
            type="datetime-local"
            value={fields.date_to || ""}
            onChange={(e) => change("date_to", e.target.value)}
          />
        </label>
        <label>
          Search events
          <input
            placeholder="TXID, event, or reason…"
            value={fields.q || ""}
            onChange={(e) => change("q", e.target.value)}
          />
        </label>
      </div>
      {legacy > 0 && (
        <div className="timeline-notice">
          <Info size={15} />
          {legacy} legacy alerts lack a recorded detection timestamp and are
          omitted from detection events. Their transaction and audit events
          remain available.
        </div>
      )}
      {limited && (
        <div className="timeline-notice">
          Source cap reached: this view uses at most 20,000 records per source.
          Counts describe the available view, not the entire case.
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div
        className={`timeline-list ${busy ? "results-loading" : ""}`}
        aria-busy={busy}
      >
        {events.map((e) => (
          <article key={e.id} className={`timeline-event ${e.type}`}>
            <div className="timeline-marker">
              {e.type === "detection" ? (
                <ShieldCheck size={15} />
              ) : e.type === "pipeline" ? (
                <Filter size={15} />
              ) : (
                <Clock size={15} />
              )}
            </div>
            <time>{utc(e.at)}</time>
            <div className="timeline-content">
              <div className="timeline-event-heading">
                <h3>{e.title}</h3>
                {e.stage ? (
                  <StagePill stage={e.stage} />
                ) : (
                  <span className="chip">{e.type}</span>
                )}
              </div>
              {Boolean(e.detail.reason) && <p>{String(e.detail.reason)}</p>}
              {Boolean(e.detail.actor) && (
                <p>
                  By {String(e.detail.actor)}
                  {e.detail.status ? ` · ${e.detail.status}` : ""}
                </p>
              )}
              {Boolean(e.detail.filename) && <p>{String(e.detail.filename)}</p>}
              {e.detail.source_record != null && (
                <p>
                  Source record {String(e.detail.source_record)} · observation
                  timestamp
                </p>
              )}
              {e.type === "network" && (
                <p>
                  {String(e.detail.peer_ip)}:{String(e.detail.peer_port)} ·
                  sensor {String(e.detail.sensor)}
                </p>
              )}
              <div className="timeline-links">
                {e.txid && (
                  <button
                    className="text-button mono"
                    onClick={() => onTx(e.txid!)}
                  >
                    {short(e.txid, 10)} <ArrowRight size={13} />
                  </button>
                )}
                {e.alert_id && (
                  <button
                    className="text-button"
                    onClick={() => onAlert(e.alert_id!)}
                  >
                    Inspect alert <ChevronRight size={13} />
                  </button>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
      {!events.length && (
        <div className="empty">
          <Clock />
          <h3>
            {busy ? "Loading timeline…" : "No events match these filters"}
          </h3>
          <button
            className="text-button"
            onClick={() => {
              setFields({ event_type: "all", stage: "all" });
              setOffset(0);
            }}
          >
            Reset timeline filters
          </button>
        </div>
      )}
      <div className="table-footer">
        <span>
          {total} matching events{" "}
          {demo ? "· illustrative synthetic history" : ""}
        </span>
        <div className="pagination">
          <button
            className="button small"
            disabled={busy || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </button>
          <span>
            {total ? offset + 1 : 0}–{Math.min(total, offset + 50)}
          </span>
          <button
            className="button small"
            disabled={busy || offset + 50 >= total}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
