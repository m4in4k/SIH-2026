import { useEffect, useState, useRef, type FormEvent } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  FolderOpen,
  Globe,
  LayoutDashboard,
  Layers,
  LogIn,
  LogOut,
  Network,
  Plus,
  Search,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Upload,
  Users,
  X,
  AlertTriangle,
  Clock,
  RefreshCw,
  CheckCircle2,
  Info,
} from "lucide-react";
import Graph from "./Graph";
import GeoMap from "./GeoMap";
import Clusters from "./Clusters";
import MLExplain from "./MLExplain";
import {
  RecordsView,
  Timeline,
  TransactionDrawer,
  DetectionEvidence,
  StagePill,
  utc,
} from "./Investigation";
import {
  api,
  btc,
  demoAlerts,
  demoCase,
  demoClusters,
  demoDataset,
  demoGeoSummary,
  demoGraph,
  demoMLExplain,
  demoSummary,
  demoTx,
  download,
  short,
  type Alert,
  type Case,
  type Cluster,
  type Dataset,
  type GeoSummary,
  type MLExplanation,
  type Summary,
  type Tx,
  type User,
} from "./data";
type Page =
  | "Overview"
  | "Transactions"
  | "Alert queue"
  | "Investigation timeline"
  | "Graph explorer"
  | "Entity clusters"
  | "Datasets"
  | "Team & access";
const nav = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Transactions", icon: Activity },
  { name: "Alert queue", icon: ShieldCheck },
  { name: "Graph explorer", icon: Network },
  { name: "Entity clusters", icon: Layers },
  { name: "Investigation timeline", icon: Clock },
  { name: "Datasets", icon: Database },
] as const;
const date = (s: string) =>
  new Date(s).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value}`}>
      {value === "high"
        ? "High priority"
        : value === "medium"
          ? "Medium"
          : value}
    </span>
  );
}
export default function App() {
  const initialAuth = new URLSearchParams(window.location.search).get("auth");
  const [page, setPage] = useState<Page>("Overview"),
    [user, setUser] = useState<User | null>(null),
    [demo, setDemo] = useState(true),
    [cases, setCases] = useState<Case[]>([demoCase]),
    [current, setCurrent] = useState<Case>(demoCase),
    [summary, setSummary] = useState<Summary>(demoSummary()),
    [alerts, setAlerts] = useState<Alert[]>(demoAlerts),
    [datasets, setDatasets] = useState<Dataset[]>([demoDataset]);
  const [login, setLogin] = useState(initialAuth === "signin" || initialAuth === "signup"),
    [signup, setSignup] = useState(initialAuth === "signup"),
    [create, setCreate] = useState(false),
    [selected, setSelected] = useState<Alert | null>(null),
    [txDetail, setTxDetail] = useState<{ txid: string } | null>(null),
    [graphTx, setGraphTx] = useState(demoAlerts[0].txid),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [members, setMembers] = useState<any[]>([]),
    [mlExplain, setMlExplain] = useState<MLExplanation | null>(null);
  const datasetInput = useRef<HTMLInputElement>(null);
  const pendingDataset = useRef<string | null>(null);
  const activeCase = useRef(current.id);
  activeCase.current = current.id;
  const canWrite = !demo && ["admin", "analyst"].includes(current.member_role);
  async function loadCases() {
    const list = await api("/cases");
    setCases(list);
    setCurrent(
      list[0] || {
        id: "",
        name: "No cases yet",
        description: "Create your first investigation case",
        member_role: "admin",
      },
    );
    setDemo(false);
  }
  useEffect(() => {
    api("/auth/me")
      .then((u) => {
        setUser(u);
        return loadCases();
      })
      .catch(() => {});
  }, []);
  async function refresh() {
    if (demo) return;
    setError("");
    if (!current.id) {
      setSummary({
        transactions: 0,
        total_output_sats: 0,
        alerts_count: 0,
        high_priority: 0,
        chart: [],
        alerts: [],
        datasets: [],
      });
      setAlerts([]);
      setDatasets([]);
      return;
    }
    setLoading(true);
    const requestedCase = current.id;
    try {
      const [s, a, d] = await Promise.all([
        api(`/cases/${current.id}/summary`),
        api(`/cases/${current.id}/alerts`),
        api(`/cases/${current.id}/datasets`),
      ]);
      if (activeCase.current !== requestedCase) return;
      setSummary(s);
      setAlerts(a);
      setDatasets(d);
      setGraphTx(a[0]?.txid || "");
      const pending = pendingDataset.current
        ? d.find((dataset: Dataset) => dataset.id === pendingDataset.current)
        : undefined;
      if (pending?.status === "completed") {
        pendingDataset.current = null;
        setPage("Alert queue");
        setNotice(
          `Analysis complete: ${pending.count.toLocaleString()} records processed and ${a.length.toLocaleString()} alerts ready for review.`,
        );
      } else if (pending?.status === "failed") {
        pendingDataset.current = null;
        setPage("Datasets");
        setError(pending.error || "Dataset analysis failed. Review the dataset details.");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, [current.id, demo]);
  useEffect(() => {
    if (demo || !current.id) return;
    let active = true;
    const timer = setTimeout(
      () =>
        api(`/cases/${current.id}/transactions?offset=0`)
          .then((r) => {
            if (active) {
              if (!graphTx && r.items[0]) setGraphTx(r.items[0].txid);
            }
          })
          .catch((e) => active && setError(e.message)),
      200,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [current.id, demo, summary.transactions]);
  useEffect(() => {
    if (demo || !datasets.some((d) => ["queued", "running"].includes(d.status)))
      return;
    const timer = setInterval(() => void refresh(), 2500);
    return () => clearInterval(timer);
  }, [datasets, demo]);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    if (page === "Team & access" && !demo && current.id)
      api(`/cases/${current.id}/members`)
        .then(setMembers)
        .catch((e) => setError(e.message));
  }, [page, current.id, demo]);
  function navigate(p: Page) {
    setPage(p);
  }
  function openAuth(createAccount = false) {
    setSignup(createAccount);
    setError("");
    setLogin(true);
  }
  function closeAuth() {
    setLogin(false);
    setSignup(false);
    setError("");
    if (window.location.search) window.history.replaceState({}, "Dashboard", "/dashboard");
  }
  function showDemo() {
    setDemo(true);
    setCases([demoCase]);
    setCurrent(demoCase);
    setSummary(demoSummary());
    setAlerts(demoAlerts);
    setDatasets([demoDataset]);
    setGraphTx(demoAlerts[0].txid);
    setLogin(false);
    setSignup(false);
    setError("");
    if (window.location.search) window.history.replaceState({}, "Dashboard", "/dashboard");
  }
  async function submitLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const u = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      setUser(u);
      await loadCases();
      closeAuth();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submitSignup(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const password = String(form.get("password") || "");
    if (password !== String(form.get("confirmPassword") || "")) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const u = await api("/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          password,
        }),
      });
      setUser(u);
      await loadCases();
      closeAuth();
      setNotice("Account created. Welcome to Sentinel Tool.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createCase(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      const c = await api("/cases", {
        method: "POST",
        body: JSON.stringify({
          name: f.get("name"),
          description: f.get("description"),
        }),
      });
      setCases([...cases, c]);
      setCurrent(c);
      setCreate(false);
      setNotice("Investigation case created.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file: File) {
    setBusy(true);
    setError("");
    const data = new FormData();
    data.append("file", file);
    try {
      let targetCase = current;
      if (!targetCase.id) {
        targetCase = await api("/cases", {
          method: "POST",
          body: JSON.stringify({
            name: `Investigation · ${file.name.replace(/\.[^.]+$/, "").slice(0, 80)}`,
            description: "Automatically created for the imported dataset.",
          }),
        });
        setCases((existing) => [...existing, targetCase]);
        setCurrent(targetCase);
      }
      const result = await api(`/cases/${targetCase.id}/datasets`, {
        method: "POST",
        body: data,
      });
      pendingDataset.current = result.id;
      setDatasets((existing) => [result, ...existing.filter((d) => d.id !== result.id)]);
      setNotice(
        result.status === "completed"
          ? "Dataset validated and analyzed. Opening your results."
          : result.status === "failed"
            ? "Dataset validation failed. Review its recorded error."
            : "Dataset uploaded. Sentinel is validating and analyzing it automatically.",
      );
      if (result.status === "completed") {
        pendingDataset.current = null;
        setPage("Alert queue");
      } else if (targetCase.id === current.id) {
        await refresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function chooseDataset() {
    if (!user) {
      navigate("Datasets");
      openAuth();
      return;
    }
    navigate("Datasets");
    datasetInput.current?.click();
  }
  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await api("/auth/logout", { method: "POST" });
      setUser(null);
      showDemo();
      setLogin(true);
      setSignup(false);
      window.history.pushState({}, "Sign in", "/dashboard?auth=signin");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function seedDemo() {
    setBusy(true);
    try {
      const result = await api(`/cases/${current.id}/demo`, { method: "POST" });
      setNotice(
        result.status === "completed"
          ? "Synthetic training dataset analyzed."
          : "Synthetic training dataset queued.",
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openAlertWithExplain(alert: Alert) {
    setSelected(alert);
    if (!demo && current.id && alert.id) {
      try {
        const explain = await api(`/cases/${current.id}/ml-explain/${alert.id}`);
        setMlExplain(explain);
      } catch {
        // Non-critical — explainability is a best-effort enhancement
      }
    }
  }

  async function report() {
    try {
      const data = demo
        ? {
            case: demoCase,
            alerts,
            dataset: demoDataset,
            disclaimer:
              "SYNTHETIC DEMO — illustrative scores, not measured model results. Unusual activity is not proof of wrongdoing.",
          }
        : await api(`/cases/${current.id}/report`);
      download(data, `sentinel-evidence-${current.id}.json`);
      setNotice("Evidence report exported.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function review(a: Alert) {
    try {
      const updated = demo
        ? {
            ...a,
            status: a.status === "open" ? "reviewed" : "open",
            reviewed_at: new Date().toISOString(),
          }
        : await api(`/cases/${current.id}/alerts/${a.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              status: a.status === "open" ? "reviewed" : "open",
            }),
          });
      setAlerts(alerts.map((x) => (x.id === a.id ? updated : x)));
      setSelected(updated);
      setNotice(
        demo
          ? "Demo review updated for this session only."
          : "Review status saved.",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function alertTable(rows: Alert[]) {
    return (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Signal / transaction</th>
              <th>Priority</th>
              <th>
                Anomaly score <Info size={12} />
              </th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} onClick={() => void openAlertWithExplain(a)}>
                <td>
                  <button
                    className="text-button"
                    onClick={() => void openAlertWithExplain(a)}
                  >
                    {a.title}
                  </button>
                  <span className="mono sub">{short(a.txid)}</span>
                  <StagePill stage={a.first_detected_stage} />
                </td>
                <td>
                  <Badge value={a.severity} />
                </td>
                <td>
                  <span className="score">
                    {a.model_version?.startsWith("rules-only")
                      ? "—"
                      : a.score.toFixed(0)}
                    <small>/100</small>
                  </span>
                  <span className="score-track">
                    <i style={{ width: `${a.score}%` }} />
                  </span>
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
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <div className="empty">
            <ShieldCheck />
            <h3>No alerts to show</h3>
            <p>Import a dataset or adjust your filters.</p>
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <span className="brand-symbol">
            <Shield size={22} />
          </span>
          <span>
            SENTINEL TOOL
            <small>AI-POWERED BITCOIN INTELLIGENCE</small>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <div className="workspace-switch">
          <span className="workspace-icon">ST</span>
          <span>
            SENTINEL TOOL<small>Investigation workspace</small>
          </span>
          <ShieldCheck size={15} />
        </div>
        <div className="workspace-label">INVESTIGATE</div>
        <nav>
          {nav.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={page === name ? "active" : ""}
              onClick={() => navigate(name)}
            >
              <Icon size={18} />
              <span>{name}</span>
              {name === "Alert queue" && (
                <b>{alerts.filter((a) => a.status === "open").length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={page === "Team & access" ? "active" : ""}
            onClick={() => navigate("Team & access")}
          >
            <Users size={18} />
            Team & access
          </button>
          <div className="local-status">
            <span className="live-dot" />
            <div>
              {demo ? "Demo environment" : "Private workspace"}
              <small>
                {demo ? "Synthetic data only" : "Case-scoped access controls"}
              </small>
            </div>
          </div>
          <button
            className="user-card"
            onClick={() => (user ? void signOut() : openAuth())}
          >
            <span className="avatar">
              {user ? user.name.slice(0, 2).toUpperCase() : "IF"}
            </span>
            <span>
              {user?.name || "Guest analyst"}
              <small>{user ? "Sign out" : "Sign in to your workspace"}</small>
            </span>
            {user ? <LogOut size={15} /> : <LogIn size={15} />}
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            Workspace <ChevronRight size={13} />
            <span>{page}</span>
          </div>
          <div className="top-actions">
            <span className="environment">
              <span className="live-dot" />
              {demo ? "DEMO MODE" : "CONNECTED"}
            </span>
            <button
              className="icon-button"
              aria-label="Open alerts"
              onClick={() => navigate("Alert queue")}
            >
              <Bell size={18} />
              <i />
            </button>
            {!user && (
              <button className="button small" onClick={() => openAuth()}>
                Sign in <ArrowUpRight size={14} />
              </button>
            )}
          </div>
        </header>
        <main key={page} className="page-motion">
          <div
            className={`route-progress ${loading || busy ? "visible" : ""}`}
            role="progressbar"
            aria-label="Loading workspace data"
            aria-hidden={!(loading || busy)}
          >
            <span />
          </div>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                SENTINEL TOOL /{" "}
                {page === "Overview" ? "COMMAND CENTER" : "INVESTIGATION"}
              </div>
              <h1>{page === "Overview" ? "Follow the signals." : page}</h1>
              <p>
                {page === "Overview"
                  ? "Turn transaction activity into evidence you can investigate."
                  : page === "Datasets"
                    ? "Bring your evidence together. Preserve every source."
                    : page === "Investigation timeline"
                      ? "Follow observations, detection stages, and analyst actions in chronological order."
                      : page === "Graph explorer"
                        ? "Trace observed output relationships. Ownership remains unknown."
                        : page === "Entity clusters"
                          ? "Wallet clusters (common-input-ownership) and IP clusters (co-occurrence) ranked by risk score."
                          : page === "Team & access"
                            ? "Give the right people access to the right investigation."
                            : page === "Transactions"
                              ? "Search and inspect the transaction records in this case."
                              : "Prioritize unusual activity. Review the evidence behind every signal."}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="button"
                disabled={!demo && !current.id}
                onClick={report}
              >
                <ArrowDownToLine size={15} />
                Export report
              </button>
              <button
                className="button primary"
                onClick={chooseDataset}
              >
                <Plus size={16} />
                Import dataset
              </button>
            </div>
          </div>
          <input
            ref={datasetInput}
            type="file"
            accept=".csv,.json,.xml"
            hidden
            disabled={!canWrite || busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
              e.target.value = "";
            }}
          />
          {demo && (
            <div className="demo-banner">
              <span>
                <Info size={15} />
                <strong>Training workspace</strong> You’re exploring synthetic
                data. Scores are illustrative, not live model results.
              </span>
              <button onClick={() => (user ? loadCases() : openAuth())}>
                Open my workspace <ArrowRight size={14} />
              </button>
            </div>
          )}
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={17} />
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          <div className="case-bar">
            <div className="case-select">
              <FolderOpen size={16} />
              <select
                aria-label="Select investigation case"
                value={current.id}
                onChange={(e) =>
                  setCurrent(cases.find((c) => c.id === e.target.value)!)
                }
              >
                {cases.length ? (
                  cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))
                ) : (
                  <option value="">No cases yet</option>
                )}
              </select>
              <ChevronDown size={13} />
            </div>
            <span className="case-desc">{current.description}</span>
            <div className="case-actions">
              {!demo && user?.role !== "viewer" && (
                <button className="text-button" onClick={() => setCreate(true)}>
                  <Plus size={14} />
                  New case
                </button>
              )}
              <button
                className="icon-button"
                aria-label="Refresh data"
                onClick={() =>
                  demo
                    ? setNotice("Demo data is a fixed synthetic snapshot.")
                    : refresh()
                }
              >
                <RefreshCw size={15} className={loading ? "spin" : ""} />
              </button>
              <span className="small-label">
                {demo
                  ? "Reference snapshot"
                  : loading
                    ? "Loading…"
                    : "Case overview"}
              </span>
            </div>
          </div>
          {page === "Overview" && (
            <>
              <div className="stats-grid">
                {[
                  {
                    label: "Transactions analyzed",
                    value: summary.transactions.toLocaleString(),
                    detail: "Across imported datasets",
                    icon: Activity,
                  },
                  {
                    label: "Output value observed",
                    value: btc(summary.total_output_sats),
                    suffix: "BTC",
                    detail: "Includes change · not net flow",
                    icon: Database,
                  },
                  {
                    label: "Signals detected",
                    value: summary.alerts_count,
                    detail: "Unusual patterns for review",
                    icon: ShieldCheck,
                  },
                  {
                    label: "High-priority signals",
                    value: summary.high_priority,
                    detail: "Evidence requires analyst review",
                    icon: AlertTriangle,
                  },
                ].map((s, i) => (
                  <section className={`stat-card stat-${i}`} key={s.label}>
                    <div className="stat-label">
                      {s.label}
                      <s.icon size={16} />
                    </div>
                    <div className="stat-value">
                      {s.value}
                      <small>{s.suffix}</small>
                    </div>
                    <span className="stat-detail">
                      {i === 3 && <i className="amber-dot" />}
                      {s.detail}
                    </span>
                  </section>
                ))}
              </div>
              <div className="overview-grid">
                <section className="panel activity-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Transaction activity</h2>
                      <p>Observation or block time · missing dates excluded</p>
                    </div>
                    <span className="chip">
                      {demo ? "24 hours" : "Imported period"} · UTC
                    </span>
                  </div>
                  <div className="chart-legend">
                    <span className="key-dot mint" />
                    Transactions{" "}
                    <span className="chart-note">
                      {summary.transactions.toLocaleString()} records
                    </span>
                  </div>
                  <div className="activity-chart">
                    <div className="chart-grid">
                      <span>Activity</span>
                      <i />
                      <i />
                      <i />
                      <i />
                    </div>
                    <div className="bars">
                      {summary.chart.map((p, i) => (
                        <div
                          className="bar-slot"
                          key={i}
                          title={`${p.label}: ${p.count} transactions`}
                        >
                          <div
                            style={{
                              height: `${Math.max(3, (p.count / Math.max(1, ...summary.chart.map((x) => x.count))) * 100)}%`,
                            }}
                          />
                          <span>
                            {i %
                              Math.max(
                                1,
                                Math.floor(summary.chart.length / 6),
                              ) ===
                            0
                              ? p.label
                              : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                    {!summary.chart.length && (
                      <div className="chart-empty">
                        Import data to see transaction activity.
                      </div>
                    )}
                  </div>
                </section>
                <section className="panel posture-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Review priorities</h2>
                      <p>A starting point, not a verdict</p>
                    </div>
                    <ShieldCheck size={18} />
                  </div>
                  <div className="priority-total">
                    <strong>
                      {alerts.filter((a) => a.status === "open").length}
                    </strong>
                    <span>
                      signals awaiting
                      <br />
                      analyst review
                    </span>
                    <div className="priority-ring">
                      <Shield size={27} />
                    </div>
                  </div>
                  <div className="priority-line">
                    <span>
                      <i className="key-dot amber" />
                      High priority
                    </span>
                    <strong>
                      {alerts.filter((a) => a.severity === "high").length}
                    </strong>
                  </div>
                  <div className="priority-line">
                    <span>
                      <i className="key-dot mint" />
                      Other signals
                    </span>
                    <strong>
                      {alerts.filter((a) => a.severity !== "high").length}
                    </strong>
                  </div>
                  <button
                    className="button full"
                    onClick={() => navigate("Alert queue")}
                  >
                    Review alert queue <ArrowRight size={15} />
                  </button>
                </section>
              </div>
              <div className="overview-bottom">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        Signals worth a closer look{" "}
                        <span className="count-bubble">{alerts.length}</span>
                      </h2>
                      <p>Ranked by review priority</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("Alert queue")}
                    >
                      View all <ArrowUpRight size={14} />
                    </button>
                  </div>
                  {alertTable(alerts.slice(0, 4))}
                </section>
                <section className="panel graph-preview">
                  <div className="panel-heading">
                    <div>
                      <h2>Follow the transaction trail</h2>
                      <p>Selected signal · two-hop neighborhood</p>
                    </div>
                    <button
                      className="icon-button"
                      aria-label="Open graph explorer"
                      onClick={() => navigate("Graph explorer")}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  </div>
                  {graphTx ? (
                    <Graph txid={graphTx} caseId={current.id} demo={demo} />
                  ) : (
                    <div className="empty">
                      <Network />
                      <p>Import transactions to build a graph.</p>
                    </div>
                  )}
                  <div className="graph-footer">
                    <span className="mono">
                      {graphTx ? short(graphTx, 9) : "No transaction selected"}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => navigate("Graph explorer")}
                    >
                      Explore <ArrowRight size={13} />
                    </button>
                  </div>
                </section>
              </div>
              {/* Geo Intelligence panel */}
              <section className="panel geo-overview-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Network relay geography</h2>
                    <p>IP observations by country — Tor exits and VPN infrastructure highlighted</p>
                  </div>
                  <button
                    className="icon-button"
                    aria-label="Open entity clusters"
                    onClick={() => navigate("Entity clusters")}
                  >
                    <Globe size={17} />
                  </button>
                </div>
                <GeoMap
                  caseId={current.id}
                  demo={demo}
                  demoData={demoGeoSummary}
                />
              </section>
            </>
          )}

          {(page === "Alert queue" || page === "Transactions") && (
            <RecordsView
              key={`${page}:${current.id}:${demo}`}
              mode={page === "Transactions" ? "transactions" : "alerts"}
              caseId={current.id}
              demo={demo}
              datasets={datasets}
              alerts={alerts}
              onTx={setTxDetail}
              onAlert={setSelected}
            />
          )}
          {page === "Investigation timeline" && (
            <Timeline
              key={`${current.id}:${demo}`}
              caseId={current.id}
              demo={demo}
              datasets={datasets}
              alerts={alerts}
              onTx={(id) => setTxDetail({ txid: id })}
              onAlert={async (id) => {
                const existing = alerts.find((a) => a.id === id);
                if (existing) setSelected(existing);
                else
                  try {
                    setSelected(
                      await api(`/cases/${current.id}/alert-details/${id}`),
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  }
              }}
            />
          )}
          {page === "Graph explorer" && (
            <section className="panel large-graph">
              <div className="toolbar">
                <form
                  className="graph-search"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    setGraphTx(String(f.get("txid")));
                  }}
                >
                  <Search size={17} />
                  <input
                    name="txid"
                    aria-label="Transaction ID"
                    placeholder="Enter an exact transaction ID"
                    defaultValue={graphTx}
                    key={current.id}
                  />
                  <button className="button small" type="submit">
                    Trace transaction <ArrowRight size={14} />
                  </button>
                </form>
              </div>
              {graphTx ? (
                <Graph
                  txid={graphTx}
                  caseId={current.id}
                  demo={demo}
                  onSelect={(id) => {
                    setTxDetail({ txid: id });
                  }}
                />
              ) : (
                <div className="empty">
                  <Network />
                  <p>
                    Select or import a transaction to explore its neighborhood.
                  </p>
                </div>
              )}
              <div className="table-footer">
                Edges represent outputs created and spent. Addresses and
                transaction relationships do not establish wallet ownership.
              </div>
            </section>
          )}
          {page === "Entity clusters" && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div className="panel-heading" style={{ padding: "20px 24px 0" }}>
                <div>
                  <h2>Entity Clusters</h2>
                  <p>Wallet groups (common-input-ownership) · IP relay clusters (co-occurrence) · Risk-scored</p>
                </div>
                <span className="chip">DBSCAN + Union-Find</span>
              </div>
              <Clusters
                key={`${current.id}:${demo}`}
                caseId={current.id}
                demo={demo}
                demoClusters={demoClusters}
              />
            </section>
          )}

          {page === "Datasets" && (
            <>
              <div className="import-grid">
                <section className="panel upload-panel">
                  <Upload size={30} />
                  <h2>Start with your evidence</h2>
                  <p>
                    Import CSV, JSON, or XML transaction records.
                    <br />
                    Files are validated before analysis. Maximum 4 MB on Vercel
                    or 10 MB when self-hosted.
                  </p>
                  <button
                    className={`button primary ${!canWrite ? "disabled" : ""}`}
                    onClick={chooseDataset}
                  >
                    <Plus size={16} />
                    {busy ? "Processing…" : "Choose a dataset"}
                  </button>
                  {demo && (
                    <button
                      className="text-button"
                      onClick={() => openAuth()}
                    >
                      Sign in to upload your data <ArrowRight size={14} />
                    </button>
                  )}
                  {!demo && !current.id && (
                    <button
                      className="text-button"
                      onClick={() => setCreate(true)}
                    >
                      Create a case first
                    </button>
                  )}
                </section>
                <section className="panel import-guide">
                  <span className="eyebrow">REPRODUCIBLE BY DESIGN</span>
                  <h2>Every signal has a source.</h2>
                  <p>
                    Imports retain the file hash and record number. Analysis
                    records its model version and reasons.
                  </p>
                  <div>
                    <CheckCircle2 size={16} /> Read-only source processing
                  </div>
                  <div>
                    <CheckCircle2 size={16} /> Duplicate and schema validation
                  </div>
                  <div>
                    <CheckCircle2 size={16} /> Isolated case access
                  </div>
                  <div className="guide-actions">
                    <button
                      className="button small"
                      onClick={() =>
                        download(
                          { transactions: demoTx.slice(0, 50) },
                          "sentinel-example.json",
                        )
                      }
                    >
                      <ArrowDownToLine size={14} />
                      Sample JSON
                    </button>
                    <button
                      className="button small"
                      disabled={!canWrite || busy}
                      onClick={seedDemo}
                    >
                      Load training data
                    </button>
                  </div>
                </section>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Imported datasets</h2>
                    <p>{datasets.length} sources in this investigation</p>
                  </div>
                  <Database size={18} />
                </div>
                <div className="dataset-list">
                  {datasets.map((d) => (
                    <div className="dataset-row" key={d.id}>
                      <span className="file-icon">
                        <FileText size={21} />
                      </span>
                      <div className="dataset-info">
                        <strong>{d.name}</strong>
                        <span>
                          {d.count} records · {date(d.created_at)}
                        </span>
                        {d.sha256 && (
                          <small className="mono">
                            SHA-256 {short(d.sha256, 12)}
                          </small>
                        )}
                        {d.error && <small className="danger">{d.error}</small>}
                        {d.warnings?.map((w) => (
                          <small key={w}>{w}</small>
                        ))}
                      </div>
                      <Badge value={d.status} />
                      {["queued", "running"].includes(d.status) && (
                        <span>{d.progress || 0}%</span>
                      )}
                    </div>
                  ))}
                  {!datasets.length && (
                    <div className="empty">
                      <Database />
                      <p>
                        No datasets yet. Import a file or load synthetic
                        training data.
                      </p>
                    </div>
                  )}
                </div>
              </section>
            </>
          )}
          {page === "Team & access" && (
            <section className="panel team-panel">
              <div className="panel-heading">
                <div>
                  <h2>Case members</h2>
                  <p>
                    Access is enforced by the backend on every case operation.
                  </p>
                </div>
                <Users size={20} />
              </div>
              {demo ? (
                <div className="empty">
                  <Shield />
                  <h3>A private space for your team</h3>
                  <p>
                    Sign in to create cases and assign analyst or viewer access.
                  </p>
                  <button
                    className="button primary"
                    onClick={() => openAuth()}
                  >
                    Sign in <ArrowRight size={15} />
                  </button>
                </div>
              ) : (
                <>
                  <div className="dataset-list">
                    {members.map((m) => (
                      <div className="dataset-row" key={m.id}>
                        <span className="avatar">{m.name.slice(0, 2)}</span>
                        <div className="dataset-info">
                          <strong>{m.name}</strong>
                          <span>{m.email}</span>
                        </div>
                        <Badge value={m.case_role} />
                      </div>
                    ))}
                  </div>
                  {current.member_role === "admin" && (
                    <form
                      className="member-form"
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        try {
                          await api(`/cases/${current.id}/members`, {
                            method: "POST",
                            body: JSON.stringify({
                              email: f.get("email"),
                              role: f.get("role"),
                            }),
                          });
                          setMembers(await api(`/cases/${current.id}/members`));
                          setNotice("Case membership updated.");
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      <h3>Add an existing user to this case</h3>
                      <label>
                        Email
                        <input
                          name="email"
                          type="email"
                          required
                          placeholder="analyst@your-team.org"
                        />
                      </label>
                      <label>
                        Case role
                        <select name="role">
                          <option value="analyst">
                            Analyst — import and review
                          </option>
                          <option value="viewer">
                            Viewer — read and export
                          </option>
                        </select>
                      </label>
                      <button className="button primary">
                        Grant case access
                      </button>
                    </form>
                  )}
                  {user?.role === "admin" && (
                    <form
                      className="member-form"
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const el = e.currentTarget,
                          f = new FormData(el);
                        try {
                          await api("/users", {
                            method: "POST",
                            body: JSON.stringify(Object.fromEntries(f)),
                          });
                          el.reset();
                          setNotice(
                            "User created. Add them to a case to grant access.",
                          );
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      <h3>Create a workspace user</h3>
                      <label>
                        Name
                        <input name="name" required minLength={2} />
                      </label>
                      <label>
                        Email
                        <input name="email" type="email" required />
                      </label>
                      <label>
                        Temporary password
                        <input
                          name="password"
                          type="password"
                          required
                          minLength={12}
                          autoComplete="new-password"
                        />
                      </label>
                      <label>
                        Workspace role
                        <select name="role">
                          <option value="analyst">Analyst</option>
                          <option value="viewer">Viewer</option>
                        </select>
                      </label>
                      <button className="button primary">Create user</button>
                    </form>
                  )}
                </>
              )}
            </section>
          )}
          <footer>
            <span>
              <ShieldCheck size={13} /> Evidence-led analysis. Human judgment
              required.
            </span>
            <span>
              SENTINEL TOOL <i /> AI-POWERED BITCOIN INTELLIGENCE
            </span>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <Check size={17} />
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {login && (
        <div className="modal-overlay" onClick={closeAuth}>
          <section
            className="modal auth-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label={signup ? "Close signup" : "Close sign in"}
              onClick={closeAuth}
            >
              <X size={20} />
            </button>
            <span className="login-mark">
              <Shield size={28} />
            </span>
            <div className="eyebrow">YOUR INVESTIGATION WORKSPACE</div>
            <h2 id="auth-title">
              {signup ? "Create your Sentinel Tool account." : "Welcome to Sentinel Tool."}
            </h2>
            <p>
              {signup
                ? "Start a private workspace for your Bitcoin investigations."
                : "Sign in to continue to your investigation workspace."}
            </p>
            <form onSubmit={signup ? submitSignup : submitLogin}>
              {signup && (
                <label>
                  Full name
                  <input
                    autoFocus
                    name="name"
                    type="text"
                    autoComplete="name"
                    minLength={2}
                    maxLength={80}
                    required
                    placeholder="Your name"
                  />
                </label>
              )}
              <label>
                Email address
                <input
                  autoFocus={!signup}
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="you@example.com"
                />
              </label>
              <label>
                Password
                <input
                  name="password"
                  type="password"
                  autoComplete={signup ? "new-password" : "current-password"}
                  minLength={signup ? 12 : 1}
                  maxLength={256}
                  required
                  placeholder={signup ? "At least 12 characters" : "Enter your password"}
                />
              </label>
              {signup && (
                <label>
                  Confirm password
                  <input
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={256}
                    required
                    placeholder="Enter the password again"
                  />
                </label>
              )}
              {error && (
                <p className="danger" role="alert">
                  {error}
                </p>
              )}
              <button className="button primary full" disabled={busy}>
                {busy
                  ? signup
                    ? "Creating account…"
                    : "Signing in…"
                  : signup
                    ? "Create account"
                    : "Sign in securely"}
                <ArrowRight size={16} />
              </button>
            </form>
            <div className="auth-switch">
              <span>{signup ? "Already have an account?" : "New to Sentinel Tool?"}</span>
              <button
                className="text-button"
                onClick={() => openAuth(!signup)}
                disabled={busy}
              >
                {signup ? "Sign in" : "Create an account"}
                <ArrowRight size={14} />
              </button>
            </div>
            <button className="text-button demo-auth-link" onClick={showDemo}>
              Explore synthetic demo instead <ArrowRight size={14} />
            </button>
          </section>
        </div>
      )}
      {create && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="case-title"
          >
            <button
              className="modal-close"
              aria-label="Close"
              onClick={() => setCreate(false)}
            >
              <X size={20} />
            </button>
            <h2 id="case-title">Open an investigation</h2>
            <p>A case keeps evidence, alerts, and team access together.</p>
            <form onSubmit={createCase}>
              <label>
                Case name
                <input
                  autoFocus
                  name="name"
                  required
                  minLength={3}
                  maxLength={100}
                  placeholder="Operation Northstar"
                />
              </label>
              <label>
                Description
                <textarea
                  name="description"
                  maxLength={500}
                  placeholder="What are you investigating?"
                />
              </label>
              {error && <p className="danger">{error}</p>}
              <button className="button primary full" disabled={busy}>
                Create case <Plus size={15} />
              </button>
            </form>
          </section>
        </div>
      )}
      {selected && (
        <div className="drawer-overlay" onClick={() => setSelected(null)}>
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="alert-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-top">
              <span className="eyebrow">SIGNAL DETAIL</span>
              <button
                className="icon-button"
                aria-label="Close alert"
                onClick={() => setSelected(null)}
              >
                <X size={20} />
              </button>
            </div>
            <Badge value={selected.severity} />
            <h2 id="alert-title">{selected.title}</h2>
            <p className="mono break">{selected.txid}</p>
            <div className="alert-score">
              <strong>
                {selected.model_version?.startsWith("rules-only")
                  ? "—"
                  : selected.score.toFixed(0)}
                <small>/100</small>
              </strong>
              <span>
                {demo ? "Illustrative anomaly score" : "Relative anomaly score"}
                <small>Not a probability of wrongdoing</small>
              </span>
            </div>
            <DetectionEvidence
              alert={selected}
              dataset={datasets.find((d) => d.id === selected.dataset_id)}
            />
            <MLExplain
              explain={
                demo
                  ? demoMLExplain(selected)
                  : mlExplain?.alert_id === selected.id
                    ? mlExplain
                    : null
              }
            />
            <h3>Why this was flagged</h3>
            {selected.reasons.map((r) => (
              <div className="reason" key={r}>
                <span />
                <p>{r}</p>
              </div>
            ))}
            <div className="safeguard">
              <Info size={18} />
              <div>
                <strong>Consider an alternative</strong>
                <p>{selected.alternative}</p>
              </div>
            </div>
            <h3>Evidence lineage</h3>
            <dl>
              <dt>Transaction observed</dt>
              <dd>{utc(selected.transaction_observed_at)}</dd>
              <dt>Detected by analysis</dt>
              <dd>{utc(selected.detected_at)}</dd>
              <dt>Alert record created</dt>
              <dd>
                {selected.detected_at
                  ? utc(selected.created_at)
                  : "Legacy timestamp basis not recorded"}
              </dd>
              <dt>Model</dt>
              <dd>{selected.model_version || "sentinel-iforest-v1"}</dd>
              <dt>Dataset</dt>
              <dd className="mono">{selected.dataset_id}</dd>
              <dt>Attribution</dt>
              <dd>Ownership unknown</dd>
            </dl>
            <button
              className="button primary full"
              onClick={() => {
                setGraphTx(selected.txid);
                navigate("Graph explorer");
                setSelected(null);
              }}
            >
              <Network size={16} />
              Explore transaction graph
            </button>
            <button
              className="button full"
              disabled={!demo && !canWrite}
              onClick={() => review(selected)}
            >
              <CheckCircle2 size={16} />
              {selected.status === "open"
                ? "Mark as reviewed"
                : "Reopen for review"}
            </button>
            <button
              className="button full"
              onClick={() => {
                setTxDetail({ txid: selected.txid });
                setSelected(null);
              }}
            >
              Inspect full transaction <ArrowRight size={15} />
            </button>
            <button className="text-button" onClick={report}>
              <ArrowDownToLine size={14} />
              Export case evidence
            </button>
          </aside>
        </div>
      )}
      {txDetail && (
        <TransactionDrawer
          txid={txDetail.txid}
          caseId={current.id}
          demo={demo}
          alerts={alerts}
          onClose={() => setTxDetail(null)}
          onSelect={(id) => setTxDetail({ txid: id })}
          onTrace={(id) => {
            setGraphTx(id);
            navigate("Graph explorer");
            setTxDetail(null);
          }}
          onAlert={(a) => {
            setTxDetail(null);
            setSelected(a);
          }}
        />
      )}
    </div>
  );
}
