import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";
import {BrowserRouter, Routes, Route, NavLink} from "react-router-dom";
import axios from "axios";
import {create} from "zustand";
import {
  ShieldCheck, LayoutDashboard, ScanLine, Link2, AlertTriangle, FileText,
  LogOut, Menu, Moon, Sun, Sparkles, BellRing, RefreshCw, ExternalLink,
  CheckCircle2, Image as ImageIcon
} from "lucide-react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

let csrfToken = "";

async function loadCsrfToken() {
  try {
    const response = await api.get("/auth/csrf");
    csrfToken = response.data.csrf_token;
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
    config.headers["X-CSRF-Token"] = csrfToken;
  }

  return config;
});

const useAuth = create(set => ({
  user: null, loading: true,
  setUser: user => set({user, loading:false}),
  logout: async () => {
    try { await api.post("/auth/logout"); } finally { set({user:null, loading:false}); }
  }
}));

async function csrf() { try { await api.get("/auth/me"); } catch (_) {} }

function App() {
  const {user, setUser, loading} = useAuth();
  const [dark, setDark] = useState(localStorage.getItem("theme") === "dark");
  useEffect(() => {
  loadCsrfToken()
    .finally(() =>
      api
        .get("/auth/me")
        .then((r) => setUser(r.data))
        .catch(() => setUser(null))
    );
}, [setUser]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  if (loading) return <div className="center"><div className="pulse"/></div>;
  return user ? <Shell dark={dark} setDark={setDark}/> : <Auth/>;
}

function Auth() {
  const [mode,setMode] = useState("login"), [email,setEmail] = useState(""), [password,setPassword] = useState(""), [error,setError] = useState("");
  const setUser = useAuth(s => s.setUser);
  async function submit(e) {
    e.preventDefault(); setError("");
    try { const r = await api.post("/auth/"+mode,{email,password}); setUser(r.data); }
    catch (e) { setError(e.response?.data?.detail || "Authentication failed"); }
  }
  return <main className="auth-page"><div className="auth-glow"/>
    <section className="auth-card">
      <div className="brand"><div className="logo"><ShieldCheck/></div><div><b>LeakGuard</b><span>Privacy intelligence</span></div></div>
      <h1>{mode==="login" ? "Secure your public footprint." : "Create your LeakGuard workspace."}</h1>
      <p className="muted">Detect exposed PII, credentials and sensitive content from your authorized Mastodon account.</p>
      <form onSubmit={submit}>
        <label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label>
        <label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} minLength="12" required/></label>
        {error && <div className="error">{error}</div>}
        <button className="primary wide">{mode==="login" ? "Sign in" : "Create account"}</button>
      </form>
      <button className="link" onClick={()=>setMode(mode==="login"?"register":"login")}>
        {mode==="login" ? "Need an account? Create one" : "Already registered? Sign in"}
      </button>
    </section>
  </main>;
}

function Shell({dark,setDark}) {
  const [open,setOpen] = useState(false), [unread,setUnread] = useState(0);
  const logout = useAuth(s=>s.logout), user = useAuth(s=>s.user);
  const nav = [
    ["/","Dashboard",LayoutDashboard],["/scan","AI Scanner",ScanLine],
    ["/accounts","Mastodon",Link2],["/incidents","Incidents",AlertTriangle],
    ["/alerts","Alerts",BellRing],["/reports","Reports",FileText]
  ];
  async function loadUnread() {
    try { const r = await api.get("/alerts"); setUnread(r.data.filter(a=>!a.read).length); } catch (_) {}
  }
  useEffect(()=>{loadUnread(); const t=setInterval(loadUnread,30000); return ()=>clearInterval(t)},[]);
  return <div className="app">
    <aside className={open ? "sidebar open" : "sidebar"}>
      <div className="brand"><div className="logo"><ShieldCheck/></div><div><b>LeakGuard</b><span>Security console</span></div></div>
      <nav>{nav.map(([to,label,Icon])=><NavLink key={to} to={to} end={to==="/"} onClick={()=>setOpen(false)}>
        <Icon size={18}/><span>{label}</span>{label==="Alerts" && unread>0 && <span className="alert-badge">{unread>99?"99+":unread}</span>}
      </NavLink>)}</nav>
      <div className="sidebar-bottom">
        <div className="user-chip"><div className="avatar">{user.email[0].toUpperCase()}</div><div><b>{user.email}</b><span>{user.role}</span></div></div>
        <button className="ghost" onClick={logout}><LogOut size={17}/> Sign out</button>
      </div>
    </aside>
    {open && <div className="overlay" onClick={()=>setOpen(false)}/>}
    <main className="content"><header>
      <button className="mobile-menu ghost" onClick={()=>setOpen(true)}><Menu/></button>
      <div className="header-title"><Sparkles size={16}/> Privacy operations center</div>
      <button className="ghost icon-btn" onClick={()=>setDark(!dark)} aria-label="Toggle theme">{dark?<Sun size={18}/>:<Moon size={18}/>}</button>
    </header>
      <Routes>
        <Route path="/" element={<Dashboard/>}/><Route path="/scan" element={<Scanner/>}/>
        <Route path="/accounts" element={<Accounts/>}/><Route path="/incidents" element={<Incidents/>}/>
        <Route path="/alerts" element={<Alerts/>}/><Route path="/reports" element={<Reports/>}/>
      </Routes>
    </main>
  </div>;
}

function Stat({label,value,sub}) { return <div className="stat card"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>; }

function Dashboard() {
  const [d,setD] = useState(null), [alerts,setAlerts] = useState([]), [incidents,setIncidents] = useState([]);
  async function load() {
    const [a,b,c] = await Promise.all([api.get("/dashboard"),api.get("/alerts"),api.get("/incidents")]);
    setD(a.data); setAlerts(b.data.slice(0,4)); setIncidents(c.data.slice(0,4));
  }
  useEffect(()=>{load().catch(()=>{}); const t=setInterval(()=>load().catch(()=>{}),30000); return ()=>clearInterval(t)},[]);
  if (!d) return <div className="center"><div className="pulse"/></div>;
  return <div className="page">
    <div className="page-head"><div><p className="eyebrow">OVERVIEW</p><h1>Security dashboard</h1><p className="muted">Authorized Mastodon content is synchronized and analyzed automatically.</p></div><NavLink className="primary" to="/scan"><ScanLine size={17}/> Run scan</NavLink></div>
    <div className="stats">
      <Stat label="Risk score" value={d.risk_score+"/100"} sub="Average analyzed risk"/>
      <Stat label="Mastodon accounts" value={d.connected_accounts} sub="Connected identities"/>
      <Stat label="Analyses" value={d.total_scans} sub="Stored detections"/>
      <Stat label="Open incidents" value={d.open_incidents} sub={`${d.unread_alerts} unread alerts`}/>
    </div>
    <div className="grid-2">
      <section className="card panel"><div className="panel-title"><h2>Risk distribution</h2><span className="tag">Live</span></div>
        {Object.entries(d.severity_breakdown).map(([k,v])=><div className="bar-row" key={k}><span>{k}</span><div><i style={{width:`${Math.min(100,v*18)}%`}}/></div><b>{v}</b></div>)}
      </section>
      <section className="card panel"><div className="panel-title"><h2>Recent alerts</h2><NavLink to="/alerts" className="link">View all</NavLink></div>
        {alerts.length ? alerts.map(a=><div className="alert-row" key={a.id}><div className={`dot ${a.severity.toLowerCase()}`}/><div><b>{a.message}</b><small>{new Date(a.created_at).toLocaleString()}</small></div></div>) : <div className="empty">No alerts yet.</div>}
      </section>
    </div>
    <section className="card panel"><div className="panel-title"><h2>Recent threats</h2><NavLink to="/incidents" className="link">Open incident queue</NavLink></div>
      {incidents.length ? incidents.map(i=><div className="threat-row" key={i.id}><div className={`severity ${String(i.severity||"").toLowerCase()}`}>{i.severity||"UNKNOWN"}</div><div><b>{i.title}</b><span>{i.risk_score ?? "—"}/100 · {i.decision||"—"} · {i.source_platform||"manual"}</span></div></div>) : <div className="empty">No incidents yet.</div>}
    </section>
    <section className="card panel"><div className="panel-title"><h2>Detection policy</h2><span className="tag">Explainable</span></div>
      <div className="policy-grid"><div><b>Very low / Low</b><span>Allow or show a privacy tip.</span></div><div><b>Medium</b><span>Allow with a privacy warning.</span></div><div><b>High</b><span>Warning + incident creation.</span></div><div><b>Critical</b><span>Block decision + incident creation.</span></div></div>
    </section>
  </div>;
}

function ResultView({r}) {
  if (!r) return <div className="empty big"><Sparkles/><h2>Ready to analyze</h2><p>LeakGuard detects PII, credentials, financial patterns, IPs and secret-like values.</p></div>;
  return <div className="result"><div className="score-ring"><span>{r.risk_score}</span><small>/100</small></div><div className={`severity ${r.severity.toLowerCase()}`}>{r.severity}</div><h2>{r.decision.replaceAll("_"," ")}</h2><p>{r.explanation}</p>
    <h3>Findings</h3>{r.findings.length?r.findings.map((f,i)=><div className="finding" key={i}><b>{f.type}</b><span>{Math.round(f.confidence*100)}% confidence · {f.severity}</span><code>{f.evidence}</code></div>):<div className="empty">No sensitive patterns detected.</div>}
    <h3>Recommendations</h3>{r.recommendations.length?<ul>{r.recommendations.map(x=><li key={x}>{x}</li>)}</ul>:<div className="muted">No action required.</div>}
  </div>;
}

function Scanner() {
  const [mode,setMode]=useState("text"), [text,setText]=useState("Contact me at alice@example.com. My temporary API key is sk-abcdefghijklmnopqrstuvwxyz123456"), [file,setFile]=useState(null), [r,setR]=useState(null), [busy,setBusy]=useState(false), [error,setError]=useState("");
  async function scan(e) {
    e.preventDefault(); setBusy(true); setError("");
    try { setR((await api.post("/scan",{content:text})).data); } catch(e) { setError(e.response?.data?.detail||"Scan failed"); } finally { setBusy(false); }
  }
  async function scanImage(e) {
    e.preventDefault(); if(!file) return; setBusy(true); setError("");
    try { const fd=new FormData(); fd.append("file",file); setR((await api.post("/scan/image",fd,{headers:{"Content-Type":"multipart/form-data"}})).data); }
    catch(e) { setError(e.response?.data?.detail||"Image scan failed"); } finally { setBusy(false); }
  }
  return <div className="page"><div className="page-head"><div><p className="eyebrow">AI ANALYSIS</p><h1>Leak scanner</h1><p className="muted">Analyze text or extract text from an image with OCR before publishing.</p></div></div>
    <div className="scanner-grid"><section className="card panel">
      <div className="tabs"><button className={mode==="text"?"tab active":"tab"} onClick={()=>setMode("text")}><FileText size={15}/> Text</button><button className={mode==="image"?"tab active":"tab"} onClick={()=>setMode("image")}><ImageIcon size={15}/> Image OCR</button></div>
      {mode==="text" ? <form onSubmit={scan}><label>Content to analyze<textarea value={text} onChange={e=>setText(e.target.value)} rows="14" maxLength="100000"/></label><div className="scan-actions"><span className="muted">{text.length.toLocaleString()} characters</span><button className="primary" disabled={busy}>{busy?"Analyzing…":"Analyze with AI"}</button></div></form>
      : <form onSubmit={scanImage}><label>Image file<input className="file-input" type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>setFile(e.target.files?.[0]||null)}/></label><p className="muted">PNG, JPEG or WebP · max configured upload size.</p><div className="scan-actions"><span className="muted">{file?.name||"No file selected"}</span><button className="primary" disabled={!file||busy}>{busy?"Reading…":"Run OCR + AI"}</button></div></form>}
      {error&&<div className="error">{error}</div>}
    </section><section className="card panel"><ResultView r={r}/></section></div>
  </div>;
}

function Accounts() {
  const [accounts,setAccounts]=useState([]), [busy,setBusy]=useState("");
  async function load(){setAccounts((await api.get("/accounts")).data)}
  useEffect(()=>{load().catch(()=>{})},[]);
  async function sync(id){setBusy(id);try{await api.post(`/accounts/${id}/sync`);await load()}catch(e){alert(e.response?.data?.detail||"Sync failed")}finally{setBusy("")}}
  async function disconnect(id){if(!confirm("Disconnect this Mastodon account?")) return; await api.delete(`/accounts/${id}`); await load()}
  return <div className="page"><div className="page-head"><div><p className="eyebrow">INTEGRATION</p><h1>Mastodon</h1><p className="muted">Official Mastodon OAuth with server-side encrypted tokens and automatic background synchronization.</p></div><button className="primary" onClick={()=>window.location.href=`${API}/oauth/mastodon/start`}><Link2 size={17}/> Connect Mastodon</button></div>
    <section className="card panel"><div className="panel-title"><h2>Connected identities</h2><span className="tag">{accounts.length}</span></div>
      {accounts.length ? accounts.map(a=><div className="account-row" key={a.id}><div className="platform-icon small">M</div><div><b>{a.username}</b><span>Mastodon · {a.instance_url ? new URL(a.instance_url).hostname : "instance"} · {a.scopes||"read scopes"}</span><span>Last sync: {a.last_sync?new Date(a.last_sync).toLocaleString():"not yet"}</span></div><div className="row-actions"><button className="ghost" disabled={busy===a.id} onClick={()=>sync(a.id)}><RefreshCw size={14}/> {busy===a.id?"Syncing…":"Sync now"}</button><button className="danger" onClick={()=>disconnect(a.id)}>Disconnect</button></div></div>) : <div className="empty"><Link2/><p>No Mastodon account connected.</p><button className="primary" onClick={()=>window.location.href=`${API}/oauth/mastodon/start`}>Connect @mastodon</button></div>}
    </section>
    <section className="card panel"><div className="panel-title"><h2>Automatic monitoring</h2><span className="tag">60 sec</span></div><p className="muted">The backend checks connected Mastodon accounts, stores new statuses, analyzes unprocessed content and creates incidents/alerts for high or critical findings.</p></section>
  </div>;
}

function IncidentCard({r,onUpdated}) {
  const [status,setStatus]=useState(r.status), [notes,setNotes]=useState(r.notes||""), [resolution,setResolution]=useState(r.resolution||""), [busy,setBusy]=useState(false);
  async function save(){setBusy(true);try{await api.patch(`/incidents/${r.id}`,{status,notes,resolution:resolution||null});onUpdated()}catch(e){alert(e.response?.data?.detail||"Update failed")}finally{setBusy(false)}}
  return <article className="incident-card"><div className="incident-head"><div><div className={`severity ${String(r.severity||"").toLowerCase()}`}>{r.severity||"UNKNOWN"}</div><h2>{r.title}</h2><span>{new Date(r.created_at).toLocaleString()} · {r.source_platform||"manual"}</span></div><div className="risk-box"><b>{r.risk_score ?? "—"}</b><small>risk</small></div></div>
    <div className="detail-grid"><div><b>Decision</b><span>{r.decision||"—"}</span></div><div><b>Confidence</b><span>{r.confidence!=null?Math.round(r.confidence*100)+"%":"—"}</span></div><div><b>Source</b>{r.source_url?<a href={r.source_url} target="_blank" rel="noreferrer">Open status <ExternalLink size={13}/></a>:<span>Manual scan</span>}</div></div>
    <p className="explanation">{r.explanation||"No explanation available."}</p>
    {r.findings?.length>0 && <><h3>Evidence</h3>{r.findings.map((f,i)=><div className="finding" key={i}><b>{f.type}</b><span>{Math.round(f.confidence*100)}% · {f.severity}</span><code>{f.evidence}</code></div>)}</>}
    {r.recommendations?.length>0 && <><h3>Recommended actions</h3><ul>{r.recommendations.map(x=><li key={x}>{x}</li>)}</ul></>}
    {r.source_content && <details><summary>Source content</summary><pre className="source-content">{r.source_content}</pre></details>}
    <div className="incident-form"><label>Status<select value={status} onChange={e=>setStatus(e.target.value)}><option>OPEN</option><option>ACKNOWLEDGED</option><option>INVESTIGATING</option><option>RESOLVED</option><option>FALSE_POSITIVE</option></select></label><label>Notes<textarea value={notes} onChange={e=>setNotes(e.target.value)} rows="3"/></label><label>Resolution<textarea value={resolution} onChange={e=>setResolution(e.target.value)} rows="3" placeholder="Required when resolving a real incident."/></label><button className="primary" onClick={save} disabled={busy}>{busy?"Saving…":"Save incident"}</button></div>
  </article>;
}

function Incidents() {
  const [rows,setRows]=useState([]);
  async function load(){setRows((await api.get("/incidents")).data)}
  useEffect(()=>{load().catch(()=>{})},[]);
  return <div className="page"><div className="page-head"><div><p className="eyebrow">RESPONSE</p><h1>Incidents</h1><p className="muted">Review evidence, recommended action and lifecycle state for every detected leak.</p></div></div>
    {rows.length ? <div className="incident-list">{rows.map(r=><IncidentCard key={r.id} r={r} onUpdated={load}/>)}</div> : <section className="card panel"><div className="empty big"><CheckCircle2/><h2>No open findings</h2><p>Run a scan or wait for the Mastodon monitor to detect a leak.</p></div></section>}
  </div>;
}

function Alerts() {
  const [rows,setRows]=useState([]);
  async function load(){setRows((await api.get("/alerts")).data)}
  useEffect(()=>{load().catch(()=>{});const t=setInterval(()=>load().catch(()=>{}),30000);return()=>clearInterval(t)},[]);
  async function read(id){await api.post(`/alerts/${id}/read`);await load()}
  return <div className="page"><div className="page-head"><div><p className="eyebrow">NOTIFICATIONS</p><h1>Alerts</h1><p className="muted">Unread detection alerts are kept here until reviewed.</p></div></div>
    <section className="card panel">{rows.length?rows.map(a=><div className="alert-item" key={a.id}><div className={`dot ${a.severity.toLowerCase()}`}/><div className="alert-main"><div><b>{a.message}</b>{!a.read&&<span className="new-badge">NEW</span>}</div><small>{new Date(a.created_at).toLocaleString()}</small></div><div className="row-actions">{a.incident_id&&<NavLink className="link" to="/incidents">View incident</NavLink>}{!a.read&&<button className="ghost" onClick={()=>read(a.id)}>Mark read</button>}</div></div>):<div className="empty big"><BellRing/><h2>No alerts</h2><p>New high-risk detections will appear here.</p></div>}</section>
  </div>;
}

function Reports() {
  function download(type){window.open(`${API}/reports/${type}`,"_blank")}
  return <div className="page"><div className="page-head"><div><p className="eyebrow">EXPORT</p><h1>Security reports</h1><p className="muted">Export the evidence trail for review, audit or submission.</p></div></div>
    <div className="report-grid"><section className="card panel"><FileText/><h2>JSON evidence report</h2><p className="muted">Includes risk, findings, recommendations, explanations and Mastodon source references.</p><button className="primary" onClick={()=>download("json")}>Open JSON</button></section><section className="card panel"><FileText/><h2>CSV incident report</h2><p className="muted">Spreadsheet-friendly incident status, risk, decision and source summary.</p><button className="primary" onClick={()=>download("csv")}>Download CSV</button></section></div>
    <section className="card panel"><h2>Report coverage</h2><p className="muted">Reports are scoped to your account and generated directly from PostgreSQL. OAuth tokens and secrets are never included.</p></section>
  </div>;
}

createRoot(document.getElementById("root")).render(<BrowserRouter><App/></BrowserRouter>);
