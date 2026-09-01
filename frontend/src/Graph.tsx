import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { Maximize, Minus, Plus } from "lucide-react";
import { api, demoGraph, short } from "./data";
export default function Graph({
  txid,
  caseId,
  demo,
  onSelect,
}: {
  txid: string;
  caseId: string;
  demo: boolean;
  onSelect?: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null),
    cy = useRef<cytoscape.Core | null>(null);
  const [error, setError] = useState("");
  const [truncated, setTruncated] = useState(false);
  useEffect(() => {
    let active = true;
    setError("");
    Promise.resolve()
      .then(() =>
        demo ? demoGraph(txid) : api(`/cases/${caseId}/graph/${txid}`),
      )
      .then((data) => {
        if (!active || !ref.current) return;
        setTruncated(data.truncated);
        cy.current = cytoscape({
          container: ref.current,
          elements: [...data.nodes, ...data.edges],
          layout: {
            name: "breadthfirst",
            directed: true,
            padding: 35,
            spacingFactor: 1.1,
          },
          minZoom: 0.2,
          maxZoom: 3,
          style: [
            {
              selector: "node",
              style: {
                "background-color": "#1d2b35",
                "border-color": "#455764",
                "border-width": 1.5,
                label: "data(label)",
                color: "#9aabbc",
                "font-size": 10,
                "text-valign": "bottom",
                "text-margin-y": 8,
                width: 25,
                height: 25,
              },
            },
            {
              selector: 'node[kind="transaction"]',
              style: {
                shape: "round-rectangle",
                "background-color": "#192d28",
                "border-color": "#65dab2",
                width: 42,
                height: 32,
              },
            },
            {
              selector: "node[?focus]",
              style: {
                "background-color": "#b8893f",
                "border-color": "#ffcc78",
                "border-width": 3,
              },
            },
            {
              selector: "edge",
              style: {
                width: 1.2,
                "line-color": "#354351",
                "target-arrow-color": "#536475",
                "target-arrow-shape": "triangle",
                "curve-style": "bezier",
              },
            },
          ],
        });
        cy.current.on("tap", 'node[kind="transaction"]', (e) =>
          onSelect?.(e.target.id()),
        );
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
      cy.current?.destroy();
      cy.current = null;
    };
  }, [txid, caseId, demo]);
  return (
    <div className="graph-wrap">
      <div
        ref={ref}
        className="graph-canvas"
        aria-label={`Transaction graph for ${short(txid)}`}
      />
      {error && <div className="graph-error">{error}</div>}
      <div className="graph-key">
        <span>
          <i className="key-dot mint" />
          Transaction
        </span>
        <span>
          <i className="key-dot slate" />
          Output
        </span>
        <span>
          <i className="key-dot amber" />
          Selected
        </span>
      </div>
      <div className="graph-controls">
        <button
          aria-label="Zoom in"
          onClick={() => cy.current?.zoom(cy.current.zoom() * 1.2)}
        >
          <Plus size={15} />
        </button>
        <button
          aria-label="Zoom out"
          onClick={() => cy.current?.zoom(cy.current.zoom() / 1.2)}
        >
          <Minus size={15} />
        </button>
        <button
          aria-label="Fit graph"
          onClick={() => cy.current?.fit(undefined, 35)}
        >
          <Maximize size={15} />
        </button>
      </div>
      {truncated && (
        <span className="graph-limit">
          Bounded preview · some nodes omitted
        </span>
      )}
    </div>
  );
}
