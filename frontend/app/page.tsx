'use client';

import { useEffect, useState } from 'react';
import {
  Activity, ArrowDownRight, ArrowUpRight, Bell, BookOpen, BriefcaseBusiness,
  FileText, LayoutDashboard, Search, ShieldCheck, Sparkles, UploadCloud,
} from 'lucide-react';

// Browser requests stay on the frontend origin. Next.js proxies /api and
// /health to FastAPI server-side, avoiding Codespaces private-port auth/CORS.
function getApiBase() {
  return '';
}

type Company = { ticker: string; name: string; sector: string };
type Announcement = {
  id: string; ticker: string; company: string; category: string; title: string;
  summary: string; priority: string; published_at: string | null; is_demo: boolean;
  source_url?: string | null; source_name?: string; exchange?: string;
};

export default function Home() {
  const [tab, setTab] = useState('Overview');
  const [portfolio, setPortfolio] = useState<Company[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [announcementMode, setAnnouncementMode] = useState('Loading');
  const [announcementNote, setAnnouncementNote] = useState('');
  const [announcementSource, setAnnouncementSource] = useState('');
  const [announcementErrors, setAnnouncementErrors] = useState<string[]>([]);
  const [announcementHours, setAnnouncementHours] = useState('24');
  const [includeRoutine, setIncludeRoutine] = useState(true);
  const [apiStatus, setApiStatus] = useState('Connecting');
  const [ticker, setTicker] = useState('TCS.NS');
  const [question, setQuestion] = useState('What does management say about growth outlook and key risks?');
  const [research, setResearch] = useState<any>(null);
  const [sourceResults, setSourceResults] = useState<any>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadTicker, setUploadTicker] = useState('TCS.NS');
  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [market, setMarket] = useState<any>(null);
  const [marketError, setMarketError] = useState('');
  const [alertTicker, setAlertTicker] = useState('RELIANCE.NS');
  const [averageDays, setAverageDays] = useState('20');
  const [autoWatch, setAutoWatch] = useState(true);
  const [alertPct, setAlertPct] = useState('3');
  const [alertVol, setAlertVol] = useState('2');
  const [alertResult, setAlertResult] = useState<any>(null);
  const [resultsAnalysis, setResultsAnalysis] = useState<any>(null);

  useEffect(() => {
    fetch(`${getApiBase()}/health`).then(r => r.ok ? setApiStatus('Connected') : setApiStatus('Unavailable')).catch(() => setApiStatus('Offline'));
    fetch(`${getApiBase()}/api/portfolio`).then(r => r.json()).then(d => setPortfolio(d.items || [])).catch(() => {});
    loadAnnouncements('24', true);
  }, []);

  useEffect(() => {
    if (tab === 'Overview') loadMarket('RELIANCE.NS');
  }, [tab]);

  async function loadAnnouncements(hours = announcementHours, routine = includeRoutine) {
    setAnnouncementMode('Loading');
    setAnnouncementNote('');
    setAnnouncementSource('');
    setAnnouncementErrors([]);
    try {
      const params = new URLSearchParams({ hours, include_routine: String(routine) });
      const response = await fetch(`${getApiBase()}/api/announcements?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Announcement feed unavailable');
      setAnnouncements(data.items || []);
      setAnnouncementMode(data.mode || 'unknown');
      setAnnouncementNote(data.note || '');
      setAnnouncementSource(data.source || '');
      setAnnouncementErrors(Array.isArray(data.errors) ? data.errors : []);
    } catch (error: any) {
      setAnnouncements([]);
      setAnnouncementMode('source_unavailable');
      setAnnouncementNote(error.message || 'Could not load corporate announcements.');
    }
  }

  async function loadMarket(symbol: string) {
    setMarketError('');
    try {
      const response = await fetch(`${getApiBase()}/api/market/${encodeURIComponent(symbol)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Market data unavailable');
      setMarket(data);
    } catch (error: any) {
      setMarketError(error.message);
      setMarket(null);
    }
  }

  async function discoverSources() {
    setSourceLoading(true); setSourceResults(null);
    try {
      const response = await fetch(`${getApiBase()}/api/sources/${encodeURIComponent(ticker)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Source discovery failed');
      setSourceResults(data);
    } catch (error: any) {
      setSourceResults({ error: error.message, items: [] });
    } finally { setSourceLoading(false); }
  }

  async function runResearch() {
    setBusy(true); setResearch(null);
    try {
      const response = await fetch(`${getApiBase()}/api/research`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, question }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Research failed');
      setResearch(data);
    } catch (error: any) {
      setResearch({ answer: error.message, sources: [], grounded: false });
    } finally { setBusy(false); }
  }

  async function upload() {
    if (!file) return;
    setBusy(true); setUploadStatus('Uploading and extracting PDF…');
    const form = new FormData(); form.append('file', file);
    try {
      const response = await fetch(`${getApiBase()}/api/documents/upload?ticker=${encodeURIComponent(uploadTicker)}`, { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Upload failed');
      setUploadStatus(`Indexed ${data.chunks_added} text chunks from ${data.pages} pages.`);
      setFile(null);
    } catch (error: any) { setUploadStatus(error.message); }
    finally { setBusy(false); }
  }

  async function analyzeFiling(tickerValue: string, sourceUrl: string) {
    setBusy(true); setResultsAnalysis(null); setUploadTicker(tickerValue);
    try {
      const response = await fetch(`${getApiBase()}/api/results/analyze-filing`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: tickerValue, source_url: sourceUrl }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not analyze filing');
      setResultsAnalysis(data);
      setTab('Documents');
    } catch (error: any) {
      setResultsAnalysis({ status: 'error', message: error.message });
      setTab('Documents');
    } finally { setBusy(false); }
  }

  async function analyzeResults() {
    setBusy(true); setResultsAnalysis(null);
    try {
      const response = await fetch(`${getApiBase()}/api/results/analyze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: uploadTicker }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Results analysis failed');
      setResultsAnalysis(data);
    } catch (error: any) {
      setResultsAnalysis({ status: 'error', message: error.message });
    } finally { setBusy(false); }
  }

  async function evaluateAlert() {
    setBusy(true); setAlertResult(null);
    try {
      const response = await fetch(`${getApiBase()}/api/alerts/evaluate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: alertTicker, price_change_pct: Number(alertPct), volume_multiple: Number(alertVol), average_days: Number(averageDays) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not evaluate');
      setAlertResult({ ...data, checked_at: new Date().toISOString() });
    } catch (error: any) { setAlertResult({ error: error.message, checked_at: new Date().toISOString() }); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (tab !== 'Alerts' || !autoWatch) return;
    // End-of-day market data is cached by the API for 15 minutes. Polling at
    // that cadence avoids hammering the upstream provider.
    const check = async () => {
      try {
        const response = await fetch(`${getApiBase()}/api/alerts/evaluate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ticker: alertTicker,
            price_change_pct: Number(alertPct),
            volume_multiple: Number(alertVol),
            average_days: Number(averageDays),
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Alert check unavailable');
        setAlertResult({ ...data, checked_at: new Date().toISOString() });
      } catch (error: any) {
        setAlertResult({ error: error.message, checked_at: new Date().toISOString() });
      }
    };
    void check();
    const timer = window.setInterval(check, 15 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [tab, autoWatch, alertTicker, alertPct, alertVol, averageDays]);

  const highCount = announcements.filter(a => a.priority === 'high').length;
  const researchPrompts = [
    ['Business snapshot', 'Summarize the business segments, products and revenue mix described in the uploaded primary sources.'],
    ['Financial snapshot', 'Summarize the latest reported revenue, margins, PAT and key financial ratios. Cite the source pages.'],
    ['Trajectory', 'Analyze the multi-year trajectory in revenue, margins and profitability. What is growing or compressing?'],
    ['Balance sheet', 'Assess debt, leverage, working capital and funding structure from the uploaded reports.'],
    ['Cash quality', 'Compare accounting profit with operating cash flow and free cash flow. Is profit converting into cash?'],
    ['Narrative vs numbers', 'Compare management commentary with reported financial performance. Where do they agree or diverge?'],
    ['Guidance', 'Extract management guidance on growth, margins and capex. Separate explicit guidance from general commentary.'],
    ['Bull vs bear', 'Present the strongest evidence-backed bull case and bear case using only the uploaded primary sources.'],
    ['Promises vs delivery', 'Across the last four available quarters, compare management growth and margin guidance with the reported outcomes.'],
  ] as const;
  const nav = [
    ['Overview', LayoutDashboard], ['Smart Digest', Bell], ['Company Research', BookOpen],
    ['Alerts', Activity], ['Documents', FileText],
  ] as const;

  return (
    <main className="min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-[1440px]">
        <aside className="hidden w-[245px] shrink-0 border-r border-slate-800/80 px-5 py-7 lg:block">
          <div className="mb-10 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-lime-400 text-slate-950 font-black text-xl">F</div>
            <div><div className="text-xl font-black tracking-[.18em]">FINN</div><div className="text-[9px] tracking-[.2em] text-slate-500">INVESTMENT INTELLIGENCE</div></div>
          </div>
          <div className="mb-3 px-3 text-[10px] font-bold uppercase tracking-[.18em] text-slate-600">Workspace</div>
          <nav className="space-y-1">{nav.map(([label, Icon]) => (
            <button key={label} onClick={() => setTab(label)} className={`navitem w-full ${tab === label ? 'active' : ''}`}>
              <Icon size={17}/>{label}{label === 'Smart Digest' && highCount > 0 && <span className="ml-auto rounded-full bg-lime-300 px-2 py-0.5 text-[10px] font-bold text-slate-950">{highCount}</span>}
            </button>
          ))}</nav>
          <div className="mt-10 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300"><ShieldCheck size={15} className="text-lime-300"/> Evidence-first AI</div>
            <p className="text-[11px] leading-5 text-slate-500">Research answers are grounded in uploaded documents. Missing evidence is called out, not guessed.</p>
          </div>
        </aside>

        <section className="min-w-0 flex-1 px-4 py-5 sm:px-7 lg:px-10 lg:py-8">
          <header className="mb-8 flex items-center justify-between">
            <div className="flex items-center gap-3 lg:hidden"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-lime-300 font-black text-slate-950">F</div><span className="font-black tracking-[.18em]">FINN</span></div>
            <div className="hidden lg:block"><div className="text-xs text-slate-500">Investment intelligence workspace</div><div className="mt-1 text-sm font-semibold text-slate-300">Push signals. Pull evidence. Understand businesses.</div></div>
            <span className={`rounded-full border px-3 py-1.5 text-[10px] ${apiStatus === 'Connected' ? 'border-lime-400/30 text-lime-300' : 'border-amber-500/30 text-amber-300'}`}>● API {apiStatus}</span>
          </header>

          <div className="mb-7 flex items-end justify-between">
            <div><div className="mb-2 text-[10px] font-bold uppercase tracking-[.22em] text-lime-300">{tab}</div><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{tab === 'Overview' ? 'Your investment intelligence workspace' : tab}</h1><p className="mt-2 max-w-2xl text-sm text-slate-500">Surface relevant information and ground research in primary company sources.</p></div>
            <span className="hidden pill sm:inline-flex">{portfolio.length || 18} companies tracked</span>
          </div>

          {tab === 'Overview' && <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
            <div className="panel p-5 sm:p-6">
              <div className="mb-5 flex items-center justify-between"><div><h2 className="font-semibold">Portfolio pulse</h2><p className="mt-1 text-xs text-slate-500">Latest available daily data · Yahoo Finance</p></div><button onClick={() => loadMarket('RELIANCE.NS')} className="btn btn-ghost">Refresh</button></div>
              {market ? <div className="grid gap-4 sm:grid-cols-2">
                <div><div className="text-xs text-slate-500">Reliance Industries · RELIANCE.NS</div><div className="mt-2 metric">₹{Number(market.latest_close).toLocaleString('en-IN')}</div><div className={`mt-2 flex items-center gap-1 text-sm ${market.price_change_pct >= 0 ? 'text-lime-300' : 'text-rose-400'}`}>{market.price_change_pct >= 0 ? <ArrowUpRight size={16}/> : <ArrowDownRight size={16}/>} {market.price_change_pct}% daily move</div></div>
                <div className="rounded-xl bg-slate-950/50 p-4"><div className="text-xs text-slate-500">Volume vs. 20-day average</div><div className="mt-2 metric">{market.volume_multiple ?? 'N/A'}×</div><div className="mt-1 text-xs text-slate-500">{Number(market.latest_volume).toLocaleString('en-IN')} shares</div></div>
                <div className="sm:col-span-2 text-[10px] text-slate-600">As of {new Date(market.as_of).toLocaleString()} · {market.source} · {market.cache_status}</div>
              </div> : <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center text-sm text-slate-500">{marketError || 'Loading market data…'}</div>}
            </div>
            <div className="panel p-5 sm:p-6"><div className="mb-4 flex items-center gap-2"><Sparkles className="text-lime-300"/><h2 className="font-semibold">Today’s focus</h2></div><div className="text-sm text-slate-400">Start with material company disclosures, unusual trading activity and changes in business fundamentals.</div><button onClick={() => setTab('Smart Digest')} className="btn btn-ghost mt-5 w-full">Open smart digest</button></div>
            <div className="panel p-5 sm:p-6 xl:col-span-2"><div className="mb-4 flex items-center justify-between"><h2 className="font-semibold">Watchlist</h2><span className="text-xs text-slate-500">Configured companies</span></div><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{portfolio.map(c => <div key={c.ticker} className="rounded-lg border border-slate-800 bg-slate-950/30 p-3"><div className="text-sm font-semibold">{c.name}</div><div className="mt-1 text-xs text-slate-500">{c.ticker} · {c.sector}</div></div>)}</div></div>
          </div>}

          {tab === 'Smart Digest' && <div className="panel p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div><h2 className="font-semibold">Portfolio announcement digest</h2><p className="mt-1 text-xs text-slate-500">NSE corporate filings · newest material items first</p></div>
              <span className="pill">{announcementMode === 'live' ? (announcementErrors.length > 0 ? 'RSS fallback · degraded' : 'Live NSE source') : announcementMode.replace(/_/g, ' ')}</span>
            </div>
            <div className="mb-5 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <label className="text-xs text-slate-400">Time window
                <select className="field mt-2" value={announcementHours} onChange={e => { setAnnouncementHours(e.target.value); loadAnnouncements(e.target.value, includeRoutine); }}>
                  <option value="24">Last 24 hours</option><option value="48">Last 48 hours</option><option value="72">Last 3 days</option><option value="168">Last 7 days</option><option value="336">Last 14 days</option><option value="720">Last 30 days</option>
                </select>
              </label>
              <label className="flex items-center gap-2 pb-3 text-xs text-slate-400"><input type="checkbox" checked={includeRoutine} onChange={e => { setIncludeRoutine(e.target.checked); loadAnnouncements(announcementHours, e.target.checked); }}/> Include routine / low-priority filings</label>
              <button onClick={() => loadAnnouncements()} className="btn btn-ghost">Refresh feed</button>
            </div>
            {announcementMode === 'source_unavailable' && <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200">Live NSE source is currently unavailable. FINN will not replace missing live filings with demo announcements. {announcementNote}</div>}
            {announcementMode === 'live' && <div className="mb-4 rounded-lg border border-lime-500/20 bg-lime-500/5 p-3 text-xs text-lime-200">Source: {announcementSource || announcements[0]?.source_name || 'NSE corporate filings'}. {announcementErrors.length > 0 ? `Fallback used after source error: ${announcementErrors.join(' · ')}` : 'Live source request completed.'} FINN's category and priority are first-pass keyword classifications, not exchange-assigned labels.</div>}
            {announcementMode === 'demo_examples' && <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200">Illustrative examples only — not real company disclosures.</div>}
            {announcementNote && announcementMode !== 'source_unavailable' && <p className="mb-3 text-xs text-slate-500">{announcementNote}</p>}
            <div className="mb-4 flex flex-wrap gap-2 text-[10px] text-slate-500"><span className="pill">High: {announcements.filter(a => a.priority === 'high').length}</span><span className="pill">Medium: {announcements.filter(a => a.priority === 'medium').length}</span><span className="pill">Low: {announcements.filter(a => a.priority === 'low').length}</span><span className="ml-auto self-center">{announcements.length} filings in selected window</span></div>
            {announcements.length === 0 && announcementMode !== 'source_unavailable' && <div className="rounded-xl border border-dashed border-slate-700 p-10 text-center"><div className="text-sm font-semibold text-slate-300">No matching filings found</div><p className="mt-2 text-xs text-slate-500">{announcementErrors.length > 0 ? 'The primary NSE feed failed and the fallback returned no matching portfolio filings. This is not confirmation that no disclosures exist.' : 'No portfolio announcements were returned for this time window and selected filters.'}</p></div>}
            <div className="space-y-3">{announcements.map(a => <article key={a.id} className="rounded-xl border border-slate-800 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3"><div className="font-semibold">{a.company} <span className="ml-1 text-xs font-normal text-slate-500">{a.ticker}</span></div><span className="pill">{a.priority} priority</span></div>
              <h3 className="mt-3 text-sm">{a.title}</h3><p className="mt-2 text-xs leading-5 text-slate-400">{a.summary}</p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-slate-600"><span>{a.category}</span><span>{a.published_at ? new Date(a.published_at).toLocaleString() : 'Time unavailable'}</span><span>{a.exchange || 'NSE'}</span>{a.is_demo && <span className="text-amber-300">DEMO</span>}{a.source_url && <a className="text-lime-300 underline" href={a.source_url} target="_blank" rel="noreferrer">Open filing ↗</a>}{a.source_url && a.category === 'results' && <button disabled={busy} onClick={() => analyzeFiling(a.ticker, a.source_url!)} className="text-lime-300 underline disabled:opacity-50">Analyze results</button>}</div>
            </article>)}</div>
          </div>}

          {tab === 'Company Research' && <div className="grid gap-5 lg:grid-cols-2">
            <div className="panel p-5 sm:p-6"><div className="mb-5 flex items-center gap-2"><Search className="text-lime-300"/><h2 className="font-semibold">Research a company</h2></div><label className="mb-2 block text-xs text-slate-400">NSE/BSE ticker</label><input className="field mb-4" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}/><label className="mb-2 block text-xs text-slate-400">Research question</label><textarea className="field min-h-[120px]" value={question} onChange={e => setQuestion(e.target.value)}/><div className="mt-4"><div className="mb-2 text-xs font-semibold text-slate-400">Research angles</div><div className="flex flex-wrap gap-2">{researchPrompts.map(([label, prompt]) => <button key={label} type="button" onClick={() => setQuestion(prompt)} className="rounded-full border border-slate-700 px-3 py-1.5 text-[10px] text-slate-400 transition hover:border-lime-400/50 hover:text-lime-300">{label}</button>)}</div></div><button disabled={busy} onClick={runResearch} className="btn btn-primary mt-4 w-full disabled:opacity-50">{busy ? 'Researching…' : 'Research from primary sources'} <Sparkles className="ml-1 inline" size={14}/></button><div className="mt-4 rounded-xl border border-slate-800 p-3"><div className="text-xs font-semibold text-slate-300">Find primary-source documents</div><p className="mt-1 text-[10px] leading-4 text-slate-500">Discover annual reports, quarterly results, investor presentations and concall transcripts indexed by Screener.</p><button disabled={sourceLoading} onClick={discoverSources} className="btn btn-ghost mt-3 w-full disabled:opacity-50">{sourceLoading ? 'Searching Screener…' : 'Find company documents'}</button>{sourceResults?.error && <p className="mt-2 text-xs text-rose-300">{sourceResults.error}</p>}{sourceResults?.items?.length > 0 && <div className="mt-3 space-y-2">{sourceResults.items.map((item: any, i: number) => <a key={i} href={item.url} target="_blank" rel="noreferrer" className="block rounded-lg bg-slate-950/50 p-2 text-xs text-lime-300 hover:bg-slate-900">{item.label}<span className="mt-1 block text-[10px] text-slate-500">{item.category.replace(/_/g, ' ')} · {item.is_index_page ? 'Screener index' : item.host}</span></a>)}</div>}{sourceResults && !sourceResults.error && sourceResults.items?.length === 0 && <p className="mt-2 text-xs text-slate-500">No matching document links found on the indexed company page.</p>}</div><p className="mt-4 text-xs leading-5 text-slate-500">Upload primary-source documents first. FINN will not invent missing evidence.</p><button onClick={() => setTab('Documents')} className="btn btn-ghost mt-3 w-full"><UploadCloud className="mr-2 inline" size={14}/>Upload company documents</button></div>
            <div className="panel min-h-[350px] p-5 sm:p-6"><h2 className="font-semibold">Research output</h2>{research ? <><div className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-300">{research.answer}</div>{research.sources?.map((source: any, i: number) => <div key={i} className="mt-3 rounded-lg bg-slate-950/50 p-3"><div className="text-xs font-semibold text-lime-300">{source.document} · page {source.page}</div><p className="mt-2 text-xs text-slate-500">{source.excerpt}</p></div>)}</> : <div className="mt-20 text-center text-sm text-slate-500">Your evidence-grounded research will appear here.</div>}</div>
          </div>}

          {tab === 'Alerts' && <div className="grid gap-5 lg:grid-cols-2">
            <div className="panel p-5 sm:p-6"><h2 className="font-semibold">Configure market triggers</h2><p className="mt-1 text-xs text-slate-500">Evaluate thresholds against the latest available daily data.</p><label className="mt-4 flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={autoWatch} onChange={e => setAutoWatch(e.target.checked)}/> Auto-watch while this screen is open (checks every 15 minutes)</label><label className="mb-2 mt-5 block text-xs text-slate-400">Portfolio company</label><select className="field" value={alertTicker} onChange={e => setAlertTicker(e.target.value)}>{portfolio.map(company => <option key={company.ticker} value={company.ticker}>{company.name} · {company.ticker}</option>)}</select><label className="mb-2 mt-4 block text-xs text-slate-400">Daily price move threshold (±%)</label><input className="field" type="number" min="0.1" step="0.1" value={alertPct} onChange={e => setAlertPct(e.target.value)}/><label className="mb-2 mt-4 block text-xs text-slate-400">Volume spike threshold (×)</label><input className="field" type="number" min="1" step="0.1" value={alertVol} onChange={e => setAlertVol(e.target.value)}/><label className="mb-2 mt-4 block text-xs text-slate-400">Volume baseline (trading days)</label><input className="field" type="number" min="2" max="250" value={averageDays} onChange={e => setAverageDays(e.target.value)}/><button disabled={busy} onClick={evaluateAlert} className="btn btn-primary mt-5 w-full">{busy ? 'Evaluating…' : 'Evaluate Reliance alerts'}</button></div>
            <div className="panel p-5 sm:p-6"><h2 className="font-semibold">Latest evaluation</h2>{alertResult ? alertResult.error ? <p className="mt-4 text-sm text-rose-300">{alertResult.error}</p> : <><span className="pill mt-4 inline-block">{alertResult.triggered ? 'Threshold crossed' : 'No threshold crossed'}</span><div className="mt-4 space-y-2">{alertResult.reasons.length ? alertResult.reasons.map((reason: string, i: number) => <div key={i} className="rounded-lg bg-slate-950/50 p-3 text-sm">{reason}</div>) : <p className="text-sm text-slate-400">No configured alert condition was met.</p>}</div><p className="mt-4 text-xs text-slate-500">Evaluation mode: {alertResult.evaluation_mode}</p><p className="mt-1 text-[10px] text-slate-600">Last checked: {alertResult.checked_at ? new Date(alertResult.checked_at).toLocaleString() : '—'}</p></> : <div className="mt-20 text-center text-xs text-slate-500">Run an evaluation to see whether thresholds were crossed.</div>}</div>
          </div>}

          {tab === 'Documents' && <div className="grid gap-5 lg:grid-cols-2"><div className="panel p-5 sm:p-6"><div className="mb-4 flex items-center gap-2"><UploadCloud className="text-lime-300"/><h2 className="font-semibold">Add primary-source documents</h2></div><p className="mb-5 text-xs leading-5 text-slate-500">Upload annual reports, quarterly results or earnings-call transcripts as PDF. Scanned-PDF OCR is not enabled.</p><label className="mb-2 block text-xs text-slate-400">Company ticker</label><input className="field mb-4" value={uploadTicker} onChange={e => setUploadTicker(e.target.value.toUpperCase())}/><label className="mb-2 block text-xs text-slate-400">PDF document</label><input className="field" type="file" accept="application/pdf" onChange={e => setFile(e.target.files?.[0] || null)}/><button disabled={!file || busy} onClick={upload} className="btn btn-primary mt-4 w-full disabled:opacity-50">{busy ? 'Processing…' : 'Upload and index PDF'}</button>{uploadStatus && <p className="mt-3 text-xs text-lime-300">{uploadStatus}</p>}<div className="mt-6 border-t border-slate-800 pt-5"><h3 className="font-semibold">Quarterly results intelligence</h3><p className="mt-2 text-xs leading-5 text-slate-500">Extract Revenue, EBITDA, PBT and PAT for the latest quarter and available QoQ / YoY comparators from uploaded source PDFs. Figures without page evidence are discarded.</p><button disabled={busy} onClick={analyzeResults} className="btn btn-ghost mt-4 w-full disabled:opacity-50">{busy ? 'Analyzing…' : 'Analyze uploaded quarterly results'}</button>{resultsAnalysis && <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4"><div className="text-sm font-semibold">{resultsAnalysis.status === 'extracted' ? 'Extraction complete' : resultsAnalysis.status === 'needs_documents' ? 'Upload a source document first' : 'Results analysis'}</div><p className="mt-2 text-xs leading-5 text-slate-400">{resultsAnalysis.message || resultsAnalysis.disclaimer}</p>{resultsAnalysis.metrics && Object.keys(resultsAnalysis.metrics).length > 0 && <><div className="mt-3 text-[10px] text-slate-500">{resultsAnalysis.basis} · {resultsAnalysis.unit || 'unit not identified'} · {resultsAnalysis.periods?.current_quarter || 'Current quarter'}</div><div className="mt-3 space-y-3">{Object.entries(resultsAnalysis.metrics).map(([metric, values]: [string, any]) => <div key={metric} className="rounded-lg border border-slate-800 p-3"><div className="text-xs font-semibold uppercase text-lime-300">{metric}</div><div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5"><div><div className="text-slate-500">Current</div><div>{values.current_quarter?.value ?? '—'}</div></div><div><div className="text-slate-500">Previous Q</div><div>{values.previous_quarter?.value ?? '—'}</div></div><div><div className="text-slate-500">Year ago Q</div><div>{values.year_ago_quarter?.value ?? '—'}</div></div><div><div className="text-slate-500">QoQ</div><div>{values.qoq_change_pct == null ? '—' : `${values.qoq_change_pct}%`}</div></div><div><div className="text-slate-500">YoY</div><div>{values.yoy_change_pct == null ? '—' : `${values.yoy_change_pct}%`}</div></div></div><div className="mt-2 text-[10px] leading-4 text-slate-500">Evidence: {(['current_quarter', 'previous_quarter', 'year_ago_quarter'] as const).filter(period => values[period]).map(period => `${period.replace(/_/g, ' ')} p${values[period].page}: ${values[period].evidence}`).join(' · ') || 'No source-supported values extracted'}</div></div>)}</div><p className="mt-3 text-[10px] leading-4 text-amber-300">{resultsAnalysis.disclaimer}</p></>}{resultsAnalysis.sources?.map((source: any, i: number) => <div key={i} className="mt-3 rounded-lg bg-slate-950/50 p-3"><div className="text-xs font-semibold text-lime-300">{source.document} · page {source.page}</div><p className="mt-2 text-xs leading-5 text-slate-500">{source.excerpt}</p></div>)}</div>}</div></div><div className="panel p-5 sm:p-6"><h2 className="font-semibold">Source discipline</h2><div className="mt-4 space-y-3 text-xs leading-5 text-slate-400"><div className="rounded-lg bg-slate-950/50 p-3"><span className="font-semibold text-lime-300">Allowed for Pull</span><br/>Annual reports, quarterly results, company filings, investor presentations and earnings-call transcripts.</div><div className="rounded-lg bg-slate-950/50 p-3"><span className="font-semibold text-rose-300">Not used for Pull</span><br/>Broker notes, news articles, secondary research and unsupported model knowledge.</div><p>Uploaded text is held in the running backend process. Restarting the backend clears its in-memory index.</p></div></div></div>}
          <footer className="mt-10 border-t border-slate-800/80 pt-5 text-[10px] leading-5 text-slate-600">FINN is an engineering prototype, not investment advice. Market data availability depends on the upstream provider. Demo announcement cards are illustrative and must not be interpreted as real company disclosures.</footer>
        </section>
      </div>
      <div className="fixed bottom-0 left-0 right-0 z-20 flex justify-around border-t border-slate-800 bg-[#081321]/95 px-2 py-2 backdrop-blur lg:hidden">{nav.map(([label, Icon]) => <button key={label} onClick={() => setTab(label)} className={`flex flex-col items-center gap-1 px-2 py-1 text-[9px] ${tab === label ? 'text-lime-300' : 'text-slate-500'}`}><Icon size={17}/>{label === 'Company Research' ? 'Research' : label === 'Smart Digest' ? 'Digest' : label}</button>)}</div>
    </main>
  );
}
