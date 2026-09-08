import { Info } from "lucide-react";
import type { MLExplanation, FeatureContribution } from "./data";

function ContributionBar({ fc, max }: { fc: FeatureContribution; max: number }) {
  const pct = max > 0 ? (Math.abs(fc.contribution) / max) * 100 : 0;
  const positive = fc.contribution >= 0;
  return (
    <div className="shap-row">
      <div className="shap-feature">
        <code>{fc.feature}</code>
        <small className="shap-desc">{fc.description}</small>
      </div>
      <div className="shap-bar-wrap">
        {positive ? (
          <div className="shap-bar-positive" style={{ width: `${Math.max(3, pct)}%` }} />
        ) : (
          <div className="shap-bar-negative" style={{ width: `${Math.max(3, pct)}%` }} />
        )}
      </div>
      <div className="shap-values">
        <span className={`shap-contrib ${positive ? "pos" : "neg"}`}>
          {positive ? "+" : ""}{fc.contribution.toFixed(3)}
        </span>
        <span className="shap-raw-val">val={fc.value.toFixed(2)}</span>
      </div>
    </div>
  );
}

export default function MLExplain({ explain }: { explain: MLExplanation | null }) {
  if (!explain) return null;
  const { feature_contributions: contribs } = explain;
  if (!contribs?.length) return null;

  const max = Math.max(...contribs.map((c) => Math.abs(c.contribution)));
  const topPositive = contribs.filter((c) => c.contribution > 0).slice(0, 4);
  const topNegative = contribs.filter((c) => c.contribution < 0).slice(0, 2);

  return (
    <section className="ml-explain">
      <div className="section-label">AI/ML FEATURE ATTRIBUTION</div>
      <div className="ml-explain-header">
        <div>
          <h3>Why this transaction was flagged</h3>
          <p>Approximate feature contributions to anomaly score ({explain.score.toFixed(1)}/100)</p>
        </div>
        <span className="chip">{explain.model_version}</span>
      </div>

      <div className="shap-legend">
        <span><i className="shap-dot pos-dot" /> Increases anomaly score</span>
        <span><i className="shap-dot neg-dot" /> Decreases anomaly score</span>
      </div>

      <div className="shap-list">
        {topPositive.map((fc, i) => (
          <ContributionBar key={`pos-${i}`} fc={fc} max={max} />
        ))}
        {topNegative.map((fc, i) => (
          <ContributionBar key={`neg-${i}`} fc={fc} max={max} />
        ))}
      </div>

      {contribs.length > 6 && (
        <div className="shap-remaining">
          + {contribs.length - 6} additional features with smaller contributions
        </div>
      )}

      <div className="ml-disclaimer">
        <Info size={13} />
        <span>{explain.disclaimer}</span>
      </div>
    </section>
  );
}
