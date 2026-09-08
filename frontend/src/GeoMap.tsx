import { useEffect, useState } from "react";
import { Globe, Shield, Wifi, AlertTriangle, TrendingUp } from "lucide-react";
import { api, type GeoSummary, type GeoCountry } from "./data";

const FLAG_MAP: Record<string, string> = {
  US: "🇺🇸", RU: "🇷🇺", CN: "🇨🇳", DE: "🇩🇪", NL: "🇳🇱", UA: "🇺🇦",
  GB: "🇬🇧", FR: "🇫🇷", JP: "🇯🇵", KR: "🇰🇷", SG: "🇸🇬", AU: "🇦🇺",
  BR: "🇧🇷", CA: "🇨🇦", IN: "🇮🇳", IR: "🇮🇷", KP: "🇰🇵", XX: "🌐",
  Unknown: "❓", private: "🔒", loopback: "🔁",
};

const RISK_COUNTRIES = new Set(["RU", "CN", "KP", "IR", "UA", "XX"]);

function CountryBar({ item, max }: { item: GeoCountry; max: number }) {
  const pct = max > 0 ? (item.count / max) * 100 : 0;
  const isRisky = RISK_COUNTRIES.has(item.country);
  const hasTor = item.tor_count > 0;
  const hasVpn = item.vpn_count > 0;
  return (
    <div className="geo-row">
      <div className="geo-label">
        <span className="geo-flag">{FLAG_MAP[item.country] ?? "🌍"}</span>
        <span className="geo-country">{item.country}</span>
        {isRisky && <span className="geo-tag risk">High-risk jurisdiction</span>}
        {hasTor && <span className="geo-tag tor">Tor</span>}
        {hasVpn && <span className="geo-tag vpn">VPN</span>}
      </div>
      <div className="geo-bar-wrap">
        <div
          className={`geo-bar ${hasTor ? "tor-bar" : hasVpn ? "vpn-bar" : isRisky ? "risk-bar" : "normal-bar"}`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <span className="geo-count">{item.count.toLocaleString()}</span>
      <div className="geo-asns">
        {item.asns.slice(0, 3).map((a) => (
          <span key={a} className="asn-badge">{a}</span>
        ))}
      </div>
    </div>
  );
}

export default function GeoMap({
  caseId,
  demo,
  demoData,
}: {
  caseId: string;
  demo: boolean;
  demoData?: GeoSummary;
}) {
  const [data, setData] = useState<GeoSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (demo) {
      setData(demoData ?? null);
      return;
    }
    if (!caseId) return;
    api(`/cases/${caseId}/geo-summary`)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [caseId, demo]);

  if (error) return <div className="empty"><AlertTriangle /><p>{error}</p></div>;
  if (!data) return <div className="empty geo-loading"><Globe className="spin" /><p>Loading geo data…</p></div>;
  if (!data.countries.length)
    return (
      <div className="empty">
        <Globe />
        <h3>No network observations</h3>
        <p>Import a dataset with IP/port fields to see geographic intelligence.</p>
      </div>
    );

  const max = Math.max(...data.countries.map((c) => c.count));

  return (
    <div className="geo-map-panel">
      {/* Summary ribbon */}
      <div className="geo-stats">
        <div className="geo-stat">
          <Globe size={16} />
          <div>
            <strong>{data.total_observations.toLocaleString()}</strong>
            <small>Total relay observations</small>
          </div>
        </div>
        <div className="geo-stat">
          <Shield size={16} className="amber-icon" />
          <div>
            <strong>{data.tor_observations}</strong>
            <small>Via Tor exit nodes</small>
          </div>
        </div>
        <div className="geo-stat">
          <Wifi size={16} className="muted-icon" />
          <div>
            <strong>{data.vpn_observations}</strong>
            <small>Via VPN infrastructure</small>
          </div>
        </div>
        <div className="geo-stat">
          <TrendingUp size={16} />
          <div>
            <strong>{data.countries.length}</strong>
            <small>Jurisdictions observed</small>
          </div>
        </div>
      </div>

      {/* Country breakdown */}
      <div className="geo-bars-container">
        <div className="geo-legend">
          <span className="geo-legend-dot normal-bar" /> Normal &nbsp;
          <span className="geo-legend-dot risk-bar" /> High-risk jurisdiction &nbsp;
          <span className="geo-legend-dot tor-bar" /> Tor &nbsp;
          <span className="geo-legend-dot vpn-bar" /> VPN
        </div>
        {data.countries.map((c) => (
          <CountryBar key={c.country} item={c} max={max} />
        ))}
      </div>

      <p className="geo-disclaimer">
        IP-to-country mapping is approximate. A relay IP does not establish
        transaction origin, sender nationality, or wallet ownership.
      </p>
    </div>
  );
}
