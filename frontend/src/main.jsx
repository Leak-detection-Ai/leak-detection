import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
} from "react-router-dom";
import axios from "axios";
import { create } from "zustand";
import { createWorker } from "tesseract.js";

import {
  ShieldCheck,
  LayoutDashboard,
  ScanLine,
  Link2,
  AlertTriangle,
  FileText,
  LogOut,
  Menu,
  Moon,
  Sun,
  Sparkles,
  BellRing,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  Image as ImageIcon,
} from "lucide-react";

import "./styles.css";

const API =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api";

/* -------------------------------------------------------
   API CLIENT
------------------------------------------------------- */

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

let csrfToken = "";

async function loadCsrfToken() {
  try {
    const response = await api.get("/auth/csrf");
    csrfToken = response.data.csrf_token || "";
  } catch (error) {
    console.error("Failed to initialize CSRF token", error);
  }
}

api.interceptors.request.use((config) => {
  const method = (config.method || "").toLowerCase();

  if (
    csrfToken &&
    ["post", "patch", "put", "delete"].includes(method)
  ) {
    config.headers = config.headers || {};
    config.headers["X-CSRF-Token"] = csrfToken;
  }

  return config;
});

/* -------------------------------------------------------
   AUTH STORE
------------------------------------------------------- */

const useAuth = create((set) => ({
  user: null,
  loading: true,

  setUser: (user) =>
    set({
      user,
      loading: false,
    }),

  logout: async () => {
    try {
      await api.post("/auth/logout");
    } catch (error) {
      console.error("Logout failed", error);
    } finally {
      set({
        user: null,
        loading: false,
      });
    }
  },
}));

/* -------------------------------------------------------
   APP
------------------------------------------------------- */

function App() {
  const { user, setUser, loading } = useAuth();

  const [dark, setDark] = useState(
    localStorage.getItem("theme") === "dark"
  );

  useEffect(() => {
    loadCsrfToken().finally(() => {
      api
        .get("/auth/me")
        .then((response) => {
          setUser(response.data);
        })
        .catch(() => {
          setUser(null);
        });
    });
  }, [setUser]);

  useEffect(() => {
    document.documentElement.dataset.theme = dark
      ? "dark"
      : "light";

    localStorage.setItem(
      "theme",
      dark ? "dark" : "light"
    );
  }, [dark]);

  if (loading) {
    return (
      <div className="center">
        <div className="pulse" />
      </div>
    );
  }

  return user ? (
    <Shell dark={dark} setDark={setDark} />
  ) : (
    <Auth />
  );
}

/* -------------------------------------------------------
   AUTH
------------------------------------------------------- */

function Auth() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const setUser = useAuth((state) => state.setUser);

  async function submit(event) {
    event.preventDefault();

    setError("");
    setBusy(true);

    try {
      const response = await api.post(
        `/auth/${mode}`,
        {
          email,
          password,
        }
      );

      setUser(response.data);

      /* Refresh CSRF token after authentication */
      await loadCsrfToken();
    } catch (error) {
      setError(
        error.response?.data?.detail ||
          "Authentication failed"
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-glow" />

      <section className="auth-card">
        <div className="brand">
          <div className="logo">
            <ShieldCheck />
          </div>

          <div>
            <b>LeakGuard</b>
            <span>Privacy intelligence</span>
          </div>
        </div>

        <h1>
          {mode === "login"
            ? "Secure your public footprint."
            : "Create your LeakGuard workspace."}
        </h1>

        <p className="muted">
          Detect exposed PII, credentials and sensitive
          content from your authorized Mastodon account.
        </p>

        <form onSubmit={submit}>
          <label>
            Email

            <input
              type="email"
              value={email}
              onChange={(event) =>
                setEmail(event.target.value)
              }
              required
            />
          </label>

          <label>
            Password

            <input
              type="password"
              value={password}
              onChange={(event) =>
                setPassword(event.target.value)
              }
              minLength="12"
              required
            />
          </label>

          {error && <div className="error">{error}</div>}

          <button
            className="primary wide"
            disabled={busy}
          >
            {busy
              ? "Please wait..."
              : mode === "login"
              ? "Sign in"
              : "Create account"}
          </button>
        </form>

        <button
          className="link"
          onClick={() =>
            setMode(
              mode === "login"
                ? "register"
                : "login"
            )
          }
        >
          {mode === "login"
            ? "Need an account? Create one"
            : "Already registered? Sign in"}
        </button>
      </section>
    </main>
  );
}

/* -------------------------------------------------------
   SHELL
------------------------------------------------------- */

function Shell({ dark, setDark }) {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);

  const logout = useAuth((state) => state.logout);
  const user = useAuth((state) => state.user);

  const nav = [
    ["/", "Dashboard", LayoutDashboard],
    ["/scan", "AI Scanner", ScanLine],
    ["/accounts", "Mastodon", Link2],
    ["/incidents", "Incidents", AlertTriangle],
    ["/alerts", "Alerts", BellRing],
    ["/reports", "Reports", FileText],
  ];

  async function loadUnread() {
    try {
      const response = await api.get("/alerts");

      const count = response.data.filter(
        (alert) => !alert.read
      ).length;

      setUnread(count);
    } catch (error) {
      console.error(
        "Failed to load unread alerts",
        error
      );
    }
  }

  useEffect(() => {
    loadUnread();

    const timer = setInterval(
      loadUnread,
      30000
    );

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="app">
      <aside
        className={
          open
            ? "sidebar open"
            : "sidebar"
        }
      >
        <div className="brand">
          <div className="logo">
            <ShieldCheck />
          </div>

          <div>
            <b>LeakGuard</b>
            <span>Security console</span>
          </div>
        </div>

        <nav>
          {nav.map(
            ([to, label, Icon]) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                onClick={() =>
                  setOpen(false)
                }
              >
                <Icon size={18} />

                <span>{label}</span>

                {label === "Alerts" &&
                  unread > 0 && (
                    <span className="alert-badge">
                      {unread > 99
                        ? "99+"
                        : unread}
                    </span>
                  )}
              </NavLink>
            )
          )}
        </nav>

        <div className="sidebar-bottom">
          <div className="user-chip">
            <div className="avatar">
              {user?.email?.[0]?.toUpperCase() ||
                "U"}
            </div>

            <div>
              <b>{user?.email}</b>
              <span>{user?.role}</span>
            </div>
          </div>

          <button
            className="ghost"
            onClick={logout}
          >
            <LogOut size={17} />
            Sign out
          </button>
        </div>
      </aside>

      {open && (
        <div
          className="overlay"
          onClick={() => setOpen(false)}
        />
      )}

      <main className="content">
        <header>
          <button
            className="mobile-menu ghost"
            onClick={() => setOpen(true)}
          >
            <Menu />
          </button>

          <div className="header-title">
            <Sparkles size={16} />
            Privacy operations center
          </div>

          <button
            className="ghost icon-btn"
            onClick={() =>
              setDark(!dark)
            }
            aria-label="Toggle theme"
          >
            {dark ? (
              <Sun size={18} />
            ) : (
              <Moon size={18} />
            )}
          </button>
        </header>

        <Routes>
          <Route
            path="/"
            element={<Dashboard />}
          />

          <Route
            path="/scan"
            element={<Scanner />}
          />

          <Route
            path="/accounts"
            element={<Accounts />}
          />

          <Route
            path="/incidents"
            element={<Incidents />}
          />

          <Route
            path="/alerts"
            element={<Alerts />}
          />

          <Route
            path="/reports"
            element={<Reports />}
          />
        </Routes>
      </main>
    </div>
  );
}

/* -------------------------------------------------------
   STAT
------------------------------------------------------- */

function Stat({
  label,
  value,
  sub,
}) {
  return (
    <div className="stat card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

/* -------------------------------------------------------
   DASHBOARD
------------------------------------------------------- */

function Dashboard() {
  const [dashboard, setDashboard] =
    useState(null);

  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] =
    useState([]);

  async function load() {
    const [
      dashboardResponse,
      alertsResponse,
      incidentsResponse,
    ] = await Promise.all([
      api.get("/dashboard"),
      api.get("/alerts"),
      api.get("/incidents"),
    ]);

    setDashboard(
      dashboardResponse.data
    );

    setAlerts(
      alertsResponse.data.slice(0, 4)
    );

    setIncidents(
      incidentsResponse.data.slice(0, 4)
    );
  }

  useEffect(() => {
    load().catch((error) =>
      console.error(
        "Dashboard loading failed",
        error
      )
    );

    const timer = setInterval(
      () =>
        load().catch((error) =>
          console.error(
            "Dashboard refresh failed",
            error
          )
        ),
      30000
    );

    return () => clearInterval(timer);
  }, []);

  if (!dashboard) {
    return (
      <div className="center">
        <div className="pulse" />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            OVERVIEW
          </p>

          <h1>Security dashboard</h1>

          <p className="muted">
            Authorized Mastodon content is
            synchronized and analyzed
            automatically.
          </p>
        </div>

        <NavLink
          className="primary"
          to="/scan"
        >
          <ScanLine size={17} />
          Run scan
        </NavLink>
      </div>

      <div className="stats">
        <Stat
          label="Risk score"
          value={`${dashboard.risk_score}/100`}
          sub="Average analyzed risk"
        />

        <Stat
          label="Mastodon accounts"
          value={dashboard.connected_accounts}
          sub="Connected identities"
        />

        <Stat
          label="Analyses"
          value={dashboard.total_scans}
          sub="Stored detections"
        />

        <Stat
          label="Open incidents"
          value={dashboard.open_incidents}
          sub={`${dashboard.unread_alerts} unread alerts`}
        />
      </div>

      <div className="grid-2">
        <section className="card panel">
          <div className="panel-title">
            <h2>Risk distribution</h2>
            <span className="tag">
              Live
            </span>
          </div>

          {Object.entries(
            dashboard.severity_breakdown || {}
          ).map(([severity, count]) => (
            <div
              className="bar-row"
              key={severity}
            >
              <span>{severity}</span>

              <div>
                <i
                  style={{
                    width: `${Math.min(
                      100,
                      count * 18
                    )}%`,
                  }}
                />
              </div>

              <b>{count}</b>
            </div>
          ))}
        </section>

        <section className="card panel">
          <div className="panel-title">
            <h2>Recent alerts</h2>

            <NavLink
              to="/alerts"
              className="link"
            >
              View all
            </NavLink>
          </div>

          {alerts.length ? (
            alerts.map((alert) => (
              <div
                className="alert-row"
                key={alert.id}
              >
                <div
                  className={`dot ${String(
                    alert.severity || ""
                  ).toLowerCase()}`}
                />

                <div>
                  <b>{alert.message}</b>

                  <small>
                    {new Date(
                      alert.created_at
                    ).toLocaleString()}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <div className="empty">
              No alerts yet.
            </div>
          )}
        </section>
      </div>

      <section className="card panel">
        <div className="panel-title">
          <h2>Recent threats</h2>

          <NavLink
            to="/incidents"
            className="link"
          >
            Open incident queue
          </NavLink>
        </div>

        {incidents.length ? (
          incidents.map((incident) => (
            <div
              className="threat-row"
              key={incident.id}
            >
              <div
                className={`severity ${String(
                  incident.severity || ""
                ).toLowerCase()}`}
              >
                {incident.severity ||
                  "UNKNOWN"}
              </div>

              <div>
                <b>{incident.title}</b>

                <span>
                  {incident.risk_score ??
                    "—"}
                  /100 ·{" "}
                  {incident.decision ||
                    "—"}{" "}
                  ·{" "}
                  {incident.source_platform ||
                    "manual"}
                </span>
              </div>
            </div>
          ))
        ) : (
          <div className="empty">
            No incidents yet.
          </div>
        )}
      </section>

      <section className="card panel">
        <div className="panel-title">
          <h2>Detection policy</h2>

          <span className="tag">
            Explainable
          </span>
        </div>

        <div className="policy-grid">
          <div>
            <b>Very low / Low</b>
            <span>
              Allow or show a privacy tip.
            </span>
          </div>

          <div>
            <b>Medium</b>
            <span>
              Allow with a privacy warning.
            </span>
          </div>

          <div>
            <b>High</b>
            <span>
              Warning + incident creation.
            </span>
          </div>

          <div>
            <b>Critical</b>
            <span>
              Block decision + incident
              creation.
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}

/* -------------------------------------------------------
   RESULT VIEW
------------------------------------------------------- */

function ResultView({ result }) {
  if (!result) {
    return (
      <div className="empty big">
        <Sparkles />

        <h2>Ready to analyze</h2>

        <p>
          LeakGuard detects PII,
          credentials, financial patterns,
          IPs and secret-like values.
        </p>
      </div>
    );
  }

  return (
    <div className="result">
      <div className="score-ring">
        <span>{result.risk_score}</span>
        <small>/100</small>
      </div>

      <div
        className={`severity ${String(
          result.severity || ""
        ).toLowerCase()}`}
      >
        {result.severity}
      </div>

      <h2>
        {String(
          result.decision || ""
        ).replaceAll("_", " ")}
      </h2>

      <p>
        {result.explanation}
      </p>

      <h3>Findings</h3>

      {result.findings?.length ? (
        result.findings.map(
          (finding, index) => (
            <div
              className="finding"
              key={`${finding.type}-${index}`}
            >
              <b>{finding.type}</b>

              <span>
                {Math.round(
                  finding.confidence * 100
                )}
                % confidence ·{" "}
                {finding.severity}
              </span>

              <code>
                {finding.evidence}
              </code>
            </div>
          )
        )
      ) : (
        <div className="empty">
          No sensitive patterns detected.
        </div>
      )}

      <h3>Recommendations</h3>

      {result.recommendations
        ?.length ? (
        <ul>
          {result.recommendations.map(
            (recommendation) => (
              <li
                key={recommendation}
              >
                {recommendation}
              </li>
            )
          )}
        </ul>
      ) : (
        <div className="muted">
          No action required.
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------
   SCANNER
------------------------------------------------------- */

function Scanner() {
  const [mode, setMode] =
    useState("text");

  const [text, setText] = useState(
    "Contact me at alice@example.com. My temporary API key is sk-abcdefghijklmnopqrstuvwxyz123456"
  );

  const [file, setFile] =
    useState(null);

  const [ocrText, setOcrText] =
    useState("");

  const [result, setResult] =
    useState(null);

  const [busy, setBusy] =
    useState(false);

  const [error, setError] =
    useState("");

  async function scan(event) {
    event.preventDefault();

    setBusy(true);
    setError("");

    try {
      const response = await api.post(
        "/scan",
        {
          content: text,
        }
      );

      setResult(response.data);
    } catch (error) {
      setError(
        error.response?.data?.detail ||
          "Scan failed"
      );
    } finally {
      setBusy(false);
    }
  }

  async function scanImage(event) {
    event.preventDefault();

    if (!file) return;

    setBusy(true);
    setError("");
    setOcrText("");
    setResult(null);

    let worker = null;

    try {
      /*
        Browser-side OCR.
        This avoids requiring the Tesseract
        executable inside Vercel.
      */
      worker = await createWorker("eng");

      const {
        data,
      } = await worker.recognize(file);

      const extractedText =
        data.text.trim();

      if (worker) {
        await worker.terminate();
        worker = null;
      }

      if (!extractedText) {
        throw new Error(
          "No readable text was found in the image."
        );
      }

      /*
        Show exactly what OCR extracted.
      */
      setOcrText(extractedText);

      /*
        Also put OCR text into the text
        scanner state.
      */
      setText(extractedText);

      /*
        Send extracted text to the
        existing AI analysis endpoint.
      */
      const response =
        await api.post("/scan", {
          content: extractedText,
        });

      setResult(response.data);
    } catch (error) {
      if (worker) {
        try {
          await worker.terminate();
        } catch {
          // Ignore cleanup errors.
        }
      }

      setError(
        error.response?.data?.detail ||
          error.message ||
          "Image OCR failed"
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            AI ANALYSIS
          </p>

          <h1>Leak scanner</h1>

          <p className="muted">
            Analyze text or extract text
            from an image with OCR before
            publishing.
          </p>
        </div>
      </div>

      <div className="scanner-grid">
        <section className="card panel">
          <div className="tabs">
            <button
              type="button"
              className={
                mode === "text"
                  ? "tab active"
                  : "tab"
              }
              onClick={() => {
                setMode("text");
                setError("");
              }}
            >
              <FileText size={15} />
              Text
            </button>

            <button
              type="button"
              className={
                mode === "image"
                  ? "tab active"
                  : "tab"
              }
              onClick={() => {
                setMode("image");
                setError("");
              }}
            >
              <ImageIcon size={15} />
              Image OCR
            </button>
          </div>

          {mode === "text" ? (
            <form onSubmit={scan}>
              <label>
                Content to analyze

                <textarea
                  value={text}
                  onChange={(event) =>
                    setText(
                      event.target.value
                    )
                  }
                  rows="14"
                  maxLength="100000"
                />
              </label>

              <div className="scan-actions">
                <span className="muted">
                  {text.length.toLocaleString()}{" "}
                  characters
                </span>

                <button
                  className="primary"
                  disabled={busy}
                >
                  {busy
                    ? "Analyzing..."
                    : "Analyze with AI"}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={scanImage}>
              <label>
                Image file

                <input
                  className="file-input"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(event) => {
                    const selectedFile =
                      event.target.files?.[0] ||
                      null;

                    setFile(selectedFile);
                    setOcrText("");
                    setResult(null);
                    setError("");
                  }}
                />
              </label>

              <p className="muted">
                PNG, JPEG or WebP · OCR runs
                in your browser.
              </p>

              <div className="scan-actions">
                <span className="muted">
                  {file?.name ||
                    "No file selected"}
                </span>

                <button
                  className="primary"
                  disabled={!file || busy}
                >
                  {busy
                    ? "Reading image..."
                    : "Run OCR + AI"}
                </button>
              </div>
            </form>
          )}

          {ocrText && (
            <details className="ocr-preview">
              <summary>
                Show extracted text
              </summary>

              <pre>{ocrText}</pre>
            </details>
          )}

          {error && (
            <div className="error">
              {error}
            </div>
          )}
        </section>

        <section className="card panel">
          <ResultView result={result} />
        </section>
      </div>
    </div>
  );
}

/* -------------------------------------------------------
   MASTODON ACCOUNTS
------------------------------------------------------- */

function Accounts() {
  const [accounts, setAccounts] =
    useState([]);

  const [busy, setBusy] =
    useState("");

  const [error, setError] =
    useState("");

  async function load() {
    const response =
      await api.get("/accounts");

    setAccounts(response.data);
  }

  useEffect(() => {
    load().catch((error) =>
      console.error(
        "Account loading failed",
        error
      )
    );
  }, []);

  async function sync(id) {
    setBusy(id);
    setError("");

    try {
      await api.post(
        `/accounts/${id}/sync`
      );

      await load();
    } catch (error) {
      setError(
        error.response?.data?.detail ||
          "Sync failed"
      );
    } finally {
      setBusy("");
    }
  }

  async function disconnect(id) {
    const confirmed = window.confirm(
      "Disconnect this Mastodon account?"
    );

    if (!confirmed) return;

    setBusy(`disconnect:${id}`);
    setError("");

    try {
      await api.delete(
        `/accounts/${id}`
      );

      await load();
    } catch (error) {
      setError(
        error.response?.data?.detail ||
          "Disconnect failed"
      );
    } finally {
      setBusy("");
    }
  }

  function connectMastodon() {
    window.location.href =
      `${API}/oauth/mastodon/start`;
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            INTEGRATION
          </p>

          <h1>Mastodon</h1>

          <p className="muted">
            Official Mastodon OAuth with
            server-side encrypted tokens and
            automatic synchronization.
          </p>
        </div>

        <button
          className="primary"
          onClick={connectMastodon}
        >
          <Link2 size={17} />
          Connect Mastodon
        </button>
      </div>

      {error && (
        <div className="error">
          {error}
        </div>
      )}

      <section className="card panel">
        <div className="panel-title">
          <h2>
            Connected identities
          </h2>

          <span className="tag">
            {accounts.length}
          </span>
        </div>

        {accounts.length ? (
          accounts.map((account) => (
            <div
              className="account-row"
              key={account.id}
            >
              <div className="platform-icon small">
                M
              </div>

              <div>
                <b>
                  {account.username}
                </b>

                <span>
                  Mastodon ·{" "}
                  {account.instance_url
                    ? new URL(
                        account.instance_url
                      ).hostname
                    : "instance"}{" "}
                  ·{" "}
                  {account.scopes ||
                    "read scopes"}
                </span>

                <span>
                  Last sync:{" "}
                  {account.last_sync
                    ? new Date(
                        account.last_sync
                      ).toLocaleString()
                    : "not yet"}
                </span>
              </div>

              <div className="row-actions">
                <button
                  className="ghost"
                  disabled={
                    busy === account.id ||
                    busy ===
                      `disconnect:${account.id}`
                  }
                  onClick={() =>
                    sync(account.id)
                  }
                >
                  <RefreshCw size={14} />

                  {busy === account.id
                    ? "Syncing..."
                    : "Sync now"}
                </button>

                <button
                  className="danger"
                  disabled={
                    busy ===
                    `disconnect:${account.id}`
                  }
                  onClick={() =>
                    disconnect(account.id)
                  }
                >
                  {busy ===
                  `disconnect:${account.id}`
                    ? "Disconnecting..."
                    : "Disconnect"}
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="empty">
            <Link2 />

            <p>
              No Mastodon account connected.
            </p>

            <button
              className="primary"
              onClick={connectMastodon}
            >
              Connect Mastodon
            </button>
          </div>
        )}
      </section>

      <section className="card panel">
        <div className="panel-title">
          <h2>
            Automatic monitoring
          </h2>

          <span className="tag">
            60 sec
          </span>
        </div>

        <p className="muted">
          The backend checks connected
          Mastodon accounts, stores new
          statuses, analyzes unprocessed
          content and creates incidents and
          alerts for high or critical
          findings.
        </p>
      </section>
    </div>
  );
}

/* -------------------------------------------------------
   INCIDENT CARD
------------------------------------------------------- */

function IncidentCard({
  incident,
  onUpdated,
}) {
  const [status, setStatus] =
    useState(incident.status);

  const [notes, setNotes] =
    useState(incident.notes || "");

  const [resolution, setResolution] =
    useState(
      incident.resolution || ""
    );

  const [busy, setBusy] =
    useState(false);

  async function save() {
    setBusy(true);

    try {
      await api.patch(
        `/incidents/${incident.id}`,
        {
          status,
          notes,
          resolution:
            resolution || null,
        }
      );

      await onUpdated();
    } catch (error) {
      window.alert(
        error.response?.data?.detail ||
          "Update failed"
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="incident-card">
      <div className="incident-head">
        <div>
          <div
            className={`severity ${String(
              incident.severity || ""
            ).toLowerCase()}`}
          >
            {incident.severity ||
              "UNKNOWN"}
          </div>

          <h2>{incident.title}</h2>

          <span>
            {new Date(
              incident.created_at
            ).toLocaleString()}{" "}
            ·{" "}
            {incident.source_platform ||
              "manual"}
          </span>
        </div>

        <div className="risk-box">
          <b>
            {incident.risk_score ??
              "—"}
          </b>

          <small>risk</small>
        </div>
      </div>

      <div className="detail-grid">
        <div>
          <b>Decision</b>
          <span>
            {incident.decision ||
              "—"}
          </span>
        </div>

        <div>
          <b>Confidence</b>
          <span>
            {incident.confidence != null
              ? `${Math.round(
                  incident.confidence * 100
                )}%`
              : "—"}
          </span>
        </div>

        <div>
          <b>Source</b>

          {incident.source_url ? (
            <a
              href={incident.source_url}
              target="_blank"
              rel="noreferrer"
            >
              Open status
              <ExternalLink size={13} />
            </a>
          ) : (
            <span>
              Manual scan
            </span>
          )}
        </div>
      </div>

      <p className="explanation">
        {incident.explanation ||
          "No explanation available."}
      </p>

      {incident.findings?.length > 0 && (
        <>
          <h3>Evidence</h3>

          {incident.findings.map(
            (finding, index) => (
              <div
                className="finding"
                key={`${finding.type}-${index}`}
              >
                <b>{finding.type}</b>

                <span>
                  {Math.round(
                    finding.confidence * 100
                  )}
                  % ·{" "}
                  {finding.severity}
                </span>

                <code>
                  {finding.evidence}
                </code>
              </div>
            )
          )}
        </>
      )}

      {incident.recommendations
        ?.length > 0 && (
        <>
          <h3>
            Recommended actions
          </h3>

          <ul>
            {incident.recommendations.map(
              (recommendation) => (
                <li
                  key={recommendation}
                >
                  {recommendation}
                </li>
              )
            )}
          </ul>
        </>
      )}

      {incident.source_content && (
        <details>
          <summary>
            Source content
          </summary>

          <pre className="source-content">
            {incident.source_content}
          </pre>
        </details>
      )}

      <div className="incident-form">
        <label>
          Status

          <select
            value={status}
            onChange={(event) =>
              setStatus(
                event.target.value
              )
            }
          >
            <option>
              OPEN
            </option>

            <option>
              ACKNOWLEDGED
            </option>

            <option>
              INVESTIGATING
            </option>

            <option>
              RESOLVED
            </option>

            <option>
              FALSE_POSITIVE
            </option>
          </select>
        </label>

        <label>
          Notes

          <textarea
            value={notes}
            onChange={(event) =>
              setNotes(
                event.target.value
              )
            }
            rows="3"
          />
        </label>

        <label>
          Resolution

          <textarea
            value={resolution}
            onChange={(event) =>
              setResolution(
                event.target.value
              )
            }
            rows="3"
            placeholder="Required when resolving a real incident."
          />
        </label>

        <button
          className="primary"
          onClick={save}
          disabled={busy}
        >
          {busy
            ? "Saving..."
            : "Save incident"}
        </button>
      </div>
    </article>
  );
}

/* -------------------------------------------------------
   INCIDENTS
------------------------------------------------------- */

function Incidents() {
  const [rows, setRows] =
    useState([]);

  async function load() {
    const response =
      await api.get("/incidents");

    setRows(response.data);
  }

  useEffect(() => {
    load().catch((error) =>
      console.error(
        "Incident loading failed",
        error
      )
    );
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            RESPONSE
          </p>

          <h1>Incidents</h1>

          <p className="muted">
            Review evidence, recommended
            action and lifecycle state for
            every detected leak.
          </p>
        </div>
      </div>

      {rows.length ? (
        <div className="incident-list">
          {rows.map((incident) => (
            <IncidentCard
              key={incident.id}
              incident={incident}
              onUpdated={load}
            />
          ))}
        </div>
      ) : (
        <section className="card panel">
          <div className="empty big">
            <CheckCircle2 />

            <h2>
              No open findings
            </h2>

            <p>
              Run a scan or wait for the
              Mastodon monitor to detect a
              leak.
            </p>
          </div>
        </section>
      )}
    </div>
  );
}

/* -------------------------------------------------------
   ALERTS
------------------------------------------------------- */

function Alerts() {
  const [rows, setRows] =
    useState([]);

  const [error, setError] =
    useState("");

  async function load() {
    const response =
      await api.get("/alerts");

    setRows(response.data);
  }

  useEffect(() => {
    load().catch((error) =>
      console.error(
        "Alert loading failed",
        error
      )
    );

    const timer = setInterval(
      () =>
        load().catch((error) =>
          console.error(
            "Alert refresh failed",
            error
          )
        ),
      30000
    );

    return () =>
      clearInterval(timer);
  }, []);

  async function markRead(id) {
    setError("");

    try {
      await api.post(
        `/alerts/${id}/read`
      );

      await load();
    } catch (error) {
      setError(
        error.response?.data?.detail ||
          "Failed to mark alert as read"
      );
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            NOTIFICATIONS
          </p>

          <h1>Alerts</h1>

          <p className="muted">
            Unread detection alerts are
            kept here until reviewed.
          </p>
        </div>
      </div>

      {error && (
        <div className="error">
          {error}
        </div>
      )}

      <section className="card panel">
        {rows.length ? (
          rows.map((alert) => (
            <div
              className="alert-item"
              key={alert.id}
            >
              <div
                className={`dot ${String(
                  alert.severity || ""
                ).toLowerCase()}`}
              />

              <div className="alert-main">
                <div>
                  <b>{alert.message}</b>

                  {!alert.read && (
                    <span className="new-badge">
                      NEW
                    </span>
                  )}
                </div>

                <small>
                  {new Date(
                    alert.created_at
                  ).toLocaleString()}
                </small>
              </div>

              <div className="row-actions">
                {alert.incident_id && (
                  <NavLink
                    className="link"
                    to="/incidents"
                  >
                    View incident
                  </NavLink>
                )}

                {!alert.read && (
                  <button
                    className="ghost"
                    onClick={() =>
                      markRead(alert.id)
                    }
                  >
                    Mark read
                  </button>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="empty big">
            <BellRing />

            <h2>No alerts</h2>

            <p>
              New high-risk detections will
              appear here.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

/* -------------------------------------------------------
   REPORTS
------------------------------------------------------- */

function Reports() {
  function download(type) {
    window.open(
      `${API}/reports/${type}`,
      "_blank"
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            EXPORT
          </p>

          <h1>
            Security reports
          </h1>

          <p className="muted">
            Export the evidence trail for
            review, audit or submission.
          </p>
        </div>
      </div>

      <div className="report-grid">
        <section className="card panel">
          <FileText />

          <h2>
            JSON evidence report
          </h2>

          <p className="muted">
            Includes risk, findings,
            recommendations, explanations
            and Mastodon source references.
          </p>

          <button
            className="primary"
            onClick={() =>
              download("json")
            }
          >
            Open JSON
          </button>
        </section>

        <section className="card panel">
          <FileText />

          <h2>
            CSV incident report
          </h2>

          <p className="muted">
            Spreadsheet-friendly incident
            status, risk, decision and source
            summary.
          </p>

          <button
            className="primary"
            onClick={() =>
              download("csv")
            }
          >
            Download CSV
          </button>
        </section>
      </div>

      <section className="card panel">
        <h2>
          Report coverage
        </h2>

        <p className="muted">
          Reports are scoped to your account
          and generated directly from
          PostgreSQL. OAuth tokens and
          secrets are never included.
        </p>
      </section>
    </div>
  );
}

/* -------------------------------------------------------
   APP MOUNT
------------------------------------------------------- */

createRoot(
  document.getElementById("root")
).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);