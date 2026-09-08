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
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    setError("");
    setLoading(true);
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
            animate: !reduceMotion,
            animationDuration: reduceMotion ? 0 : 620,
            animationEasing: "ease-out-cubic",
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
              selector: 'node[kind="wallet"]',
              style: {
                shape: "ellipse",
                "background-color": "#263744",
                "border-color": "#8ba7ba",
                width: 34,
                height: 34,
              },
            },
            {
              selector: 'node[kind="ip"]',
              style: {
                shape: "hexagon",
                "background-color": "#382d22",
                "border-color": "#e8b36a",
                width: 34,
                height: 34,
              },
            },
            {
              selector: 'node[kind="country"]',
              style: {
                shape: "diamond",
                "background-color": "#203538",
                "border-color": "#55c8c7",
                width: 29,
                height: 29,
              },
            },
            {
              selector: 'node[kind="asn"]',
              style: {
                shape: "round-diamond",
                "background-color": "#302943",
                "border-color": "#a78bda",
                width: 31,
                height: 31,
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
              selector: "node:selected",
              style: {
                "border-width": 4,
                "border-color": "#ffe0a3",
                "overlay-color": "#e8b36a",
                "overlay-opacity": 0.08,
                "overlay-padding": 7,
                "transition-property":
                  "border-width, border-color, overlay-opacity",
                "transition-duration": 180,
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
        setLoading(false);
      })
      .catch((e) => {
        if (!active) return;
        setError(e.message);
        setLoading(false);
      });
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
        className={`graph-canvas ${loading ? "" : "is-ready"}`}
        aria-label={`Transaction graph for ${short(txid)}`}
        aria-busy={loading}
      />
      <div
        className={`graph-loading ${loading ? "visible" : ""}`}
        role="status"
        aria-live="polite"
        aria-hidden={!loading}
      >
        <span />
        <small>Mapping transaction flow</small>
      </div>
      {error && <div className="graph-error">{error}</div>}
      <div className="graph-key">
        <span>
          <i className="key-dot mint" />
          Transaction
        </span>
        <span>
          <i className="key-dot slate" />
          Wallet / output
        </span>
        <span>
          <i className="key-dot cyan" />
          Network IP
        </span>
        <span>
          <i className="key-dot violet" />
          Country / ASN
        </span>
        <span>
          <i className="key-dot amber" />
          Selected
        </span>
      </div>
      <div className="graph-controls">
        <button
          aria-label="Zoom in"
          onClick={() =>
            cy.current?.animate({
              zoom: cy.current.zoom() * 1.2,
              duration: 180,
            })
          }
        >
          <Plus size={15} />
        </button>
        <button
          aria-label="Zoom out"
          onClick={() =>
            cy.current?.animate({
              zoom: cy.current.zoom() / 1.2,
              duration: 180,
            })
          }
        >
          <Minus size={15} />
        </button>
        <button
          aria-label="Fit graph"
          onClick={() => {
            if (!cy.current) return;
            cy.current.animate({
              fit: { eles: cy.current.elements(), padding: 35 },
              duration: 260,
            });
          }}
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
