import { useEffect, useState } from "react";
import {
  AlertTriangle, ChevronRight, Globe, Layers, Link, Shield, Wifi,
} from "lucide-react";
import { api, short, type Cluster } from "./data";

function RiskBadge({ level }: { level: string }) {
  return (
    <span className={`cluster-risk-badge ${level}`}>
      {level === "high" ? "⚠ High risk" : level === "medium" ? "◎ Medium" : "✓ Low"}
    </span>
  );
}

function ClusterCard({
  cluster,
  onSelect,
  selected,
}: {
  cluster: Cluster;
  onSelect: (c: Cluster) => void;
  selected: boolean;
}) {
  const members = cluster.type === "wallet" ? cluster.addresses ?? [] : cluster.ips ?? [];
  return (
    <article
      className={`cluster-card ${cluster.risk_level} ${selected ? "selected" : ""}`}
      onClick={() => onSelect(cluster)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect(cluster)}
    >
      <div className="cluster-card-top">
        <div className="cluster-icon">
          {cluster.type === "wallet" ? <Layers size={15} /> : <Globe size={15} />}
        </div>
        <div className="cluster-info">
          <div className="cluster-header">
            <span className="cluster-type-label">
              {cluster.type === "wallet" ? "Wallet Cluster" : "IP Cluster"}
            </span>
            <RiskBadge level={cluster.risk_level} />
          </div>
          <code className="cluster-id">{cluster.cluster_id}</code>
        </div>
        <ChevronRight size={14} className="cluster-chevron" />
      </div>
      <div className="cluster-meta">
        <span>
          <strong>{cluster.size}</strong> {cluster.type === "wallet" ? "addresses" : "IPs"}
        </span>
        <span>
          <strong>{cluster.txid_count}</strong> transactions
        </span>
        {cluster.has_tor && (
          <span className="cluster-tag tor-tag">
            <Shield size={11} /> Tor
          </span>
        )}
        {cluster.has_vpn && (
          <span className="cluster-tag vpn-tag">
            <Wifi size={11} /> VPN
          </span>
        )}
        {(cluster.high_alert_hits ?? 0) > 0 && (
          <span className="cluster-tag alert-tag">
            <AlertTriangle size={11} /> {cluster.high_alert_hits} high alerts
          </span>
        )}
      </div>
      <div className="cluster-score-row">
        <span className="cluster-score-label">Risk score</span>
        <div className="cluster-score-track">
          <div
            className={`cluster-score-fill ${cluster.risk_level}`}
            style={{ width: `${cluster.risk_score}%` }}
          />
        </div>
        <span className="cluster-score-val">{cluster.risk_score.toFixed(0)}/100</span>
      </div>
      <div className="cluster-members-preview">
        {members.slice(0, 4).map((m, i) => (
          <code key={i} className="member-chip">{short(m, 10)}</code>
        ))}
        {members.length > 4 && (
          <span className="member-more">+{members.length - 4} more</span>
        )}
      </div>
    </article>
  );
}

function ClusterDetail({ cluster }: { cluster: Cluster }) {
  const members = cluster.type === "wallet" ? cluster.addresses ?? [] : cluster.ips ?? [];
  return (
    <aside className="cluster-detail">
      <div className="section-label">ENTITY CLUSTER DETAIL</div>
      <div className="cluster-detail-header">
        <div className="cluster-icon large">
          {cluster.type === "wallet" ? <Layers size={20} /> : <Globe size={20} />}
        </div>
        <div>
          <strong>{cluster.type === "wallet" ? "Wallet Cluster" : "IP Network Cluster"}</strong>
          <code className="cluster-id">{cluster.cluster_id}</code>
          <RiskBadge level={cluster.risk_level} />
        </div>
      </div>

      <div className="cluster-detail-grid">
        <div><small>Heuristic</small><span>{cluster.heuristic.replace(/\+/g, " + ")}</span></div>
        <div><small>Cluster size</small><span>{cluster.size} {cluster.type === "wallet" ? "addresses" : "IPs"}</span></div>
        <div><small>Linked transactions</small><span>{cluster.txid_count}</span></div>
        <div><small>High-priority alerts</small><span>{cluster.high_alert_hits ?? cluster.flagged_alert_hits ?? 0}</span></div>
        {cluster.countries?.length ? (
          <div><small>Countries</small><span>{cluster.countries.join(", ")}</span></div>
        ) : null}
        {cluster.has_tor && (
          <div><small>Tor detected</small><span className="danger">Yes — anonymisation network</span></div>
        )}
        {cluster.has_vpn && (
          <div><small>VPN detected</small><span className="amber">Yes — commercial VPN ASN</span></div>
        )}
      </div>

      <div className="section-label" style={{ marginTop: 16 }}>
        {cluster.type === "wallet" ? "ADDRESSES IN CLUSTER" : "IPS IN CLUSTER"}
      </div>
      <div className="member-list">
        {members.map((m, i) => (
          <div key={i} className="member-row">
            <Link size={11} />
            <code>{m}</code>
          </div>
        ))}
      </div>

      {cluster.txids.length > 0 && (
        <>
          <div className="section-label" style={{ marginTop: 12 }}>LINKED TRANSACTION IDS</div>
          <div className="member-list">
            {cluster.txids.slice(0, 10).map((txid, i) => (
              <div key={i} className="member-row">
                <code>{short(txid, 12)}</code>
              </div>
            ))}
            {cluster.txids.length > 10 && (
              <span className="member-more">+{cluster.txids.length - 10} more TXIDs</span>
            )}
          </div>
        </>
      )}

      <div className="cluster-disclaimer">
        Cluster membership is inferred from heuristics, not confirmed ownership.
        Shared address control or relay co-occurrence does not establish identity.
      </div>
    </aside>
  );
}

export default function Clusters({
  caseId,
  demo,
  demoClusters,
}: {
  caseId: string;
  demo: boolean;
  demoClusters: Cluster[];
}) {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [filter, setFilter] = useState<"all" | "wallet" | "ip">("all");
  const [selected, setSelected] = useState<Cluster | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (demo) {
      setClusters(demoClusters);
      setSelected(demoClusters[0] ?? null);
      return;
    }
    if (!caseId) return;
    setLoading(true);
    api(`/cases/${caseId}/clusters`)
      .then((data) => {
        setClusters(data);
        setSelected(data[0] ?? null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [caseId, demo]);

  const filtered = clusters.filter(
    (c) => filter === "all" || c.type === filter,
  );

  return (
    <div className="clusters-layout">
      {/* Left: list */}
      <div className="clusters-list">
        <div className="clusters-toolbar">
          <div className="filter-tabs">
            {(["all", "wallet", "ip"] as const).map((f) => (
              <button
                key={f}
                className={filter === f ? "active" : ""}
                onClick={() => setFilter(f)}
                id={`cluster-filter-${f}`}
              >
                {f === "all" ? "All clusters" : f === "wallet" ? <><Layers size={13} /> Wallets</> : <><Globe size={13} /> IPs</>}
              </button>
            ))}
          </div>
          <span className="cluster-count">{filtered.length} clusters</span>
        </div>

        {error && <div className="error-banner"><AlertTriangle size={15} />{error}</div>}
        {loading && <div className="empty"><div className="spin-ring" /></div>}

        {!loading && !filtered.length && (
          <div className="empty">
            <Layers />
            <h3>No clusters found</h3>
            <p>Entity clusters appear after dataset analysis. Import transactions with input addresses to enable wallet clustering.</p>
          </div>
        )}

        <div className="cluster-cards">
          {filtered.map((c) => (
            <ClusterCard
              key={c.id}
              cluster={c}
              onSelect={setSelected}
              selected={selected?.id === c.id}
            />
          ))}
        </div>
      </div>

      {/* Right: detail */}
      <div className="clusters-detail-pane">
        {selected ? (
          <ClusterDetail cluster={selected} />
        ) : (
          <div className="empty">
            <Layers />
            <p>Select a cluster to inspect its members and evidence.</p>
          </div>
        )}
      </div>
    </div>
  );
}
