(() => {
  'use strict';

  const DEFAULT_API = 'http://127.0.0.1:8000';
  const API = localStorage.getItem('finsight-api') || DEFAULT_API;
  const AGENTS = [
    ['financial_statement', 'Financial Statement Agent', 'Company filings and core financial metrics'],
    ['news_research', 'News Research Agent', 'Recent headlines and company coverage'],
    ['market_data', 'Market Data Agent', 'Price history and market profile'],
    ['risk_analysis', 'Risk Analysis Agent', 'Volatility, drawdown and financial risk'],
    ['competitor_analysis', 'Competitor Analysis Agent', 'Peer metrics and market context'],
    ['investment_decision', 'Investment Decision Agent', 'Weighted research assessment'],
    ['report_generation', 'Report Generation Agent', 'Consolidated research report'],
  ];
  const PAGE_META = {
    dashboard: ['Overview', 'Research activity and company insights'],
    'new-research': ['New Research', 'Start a new seven-agent research workflow'],
    history: ['Research History', 'Browse stored research jobs and reports'],
    companies: ['Companies', 'Registered companies in your workspace'],
    job: ['Live Research', 'Agent statuses and outputs for this research job'],
    decision: ['Investment Decision', 'Actual assessment and supporting evidence from the decision agent'],
    financial: ['Financial Analysis', 'Reported financial statement data'],
    market: ['Market Analysis', 'Price history and market data'],
    risk: ['Risk Analysis', 'Reported market and financial risk measures'],
    competitors: ['Competitor Analysis', 'Peer comparisons with source currencies preserved'],
    news: ['News Research', 'Articles returned by the news research agent'],
    report: ['Final Report', 'Stored consolidated report from the report generation agent'],
    settings: ['Settings', 'Configure this browser’s FastAPI connection'],
  };

  const state = {
    jobs: [], companies: [], currentJob: null, currentAgents: [], timer: null,
    charts: [], lookup: null, historyQuery: '', historyStatus: 'all', historySort: 'newest', historyPage: 1,
  };
  const $ = (selector, root = document) => root.querySelector(selector);
  const content = $('#content');
  const notice = $('#notice');

  class ApiError extends Error {
    constructor(message, status) { super(message); this.status = status; }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]);
  }

  function apiUrl(path) { return `${API.replace(/\/$/, '')}${path}`; }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    let response;
    try {
      response = await fetch(apiUrl(path), {
        ...options,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...options.headers,
        },
      });
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The backend request timed out. Check that FastAPI is running.');
      throw new Error(`Cannot reach ${API}. Start FastAPI and check Settings for the API address.`);
    } finally {
      clearTimeout(timer);
    }
    let data;
    try { data = await response.json(); }
    catch { throw new ApiError(`The backend returned an invalid response (${response.status}).`, response.status); }
    if (!response.ok) {
      const detail = data?.detail;
      const message = typeof detail === 'string' ? detail
        : Array.isArray(detail) ? detail.map((item) => item.msg).join(', ')
          : `Request failed (${response.status}).`;
      throw new ApiError(message, response.status);
    }
    return data;
  }

  async function loadAll(resource) {
    const records = [];
    let skip = 0;
    while (true) {
      const page = await api(`${resource}?skip=${skip}&limit=100`);
      records.push(...page);
      if (page.length < 100) return records;
      skip += 100;
    }
  }
  const getCompanies = () => loadAll('/api/companies');
  const getJobs = () => loadAll('/api/research-jobs');
  async function findExistingJob(companyId, start, end) {
    let skip = 0;
    while (true) {
      const jobs = await api(`/api/research-jobs?skip=${skip}&limit=100`);
      const match = jobs.find((item) => item.company_id === companyId
        && String(item.research_period_start || '').slice(0, 10) === start
        && String(item.research_period_end || '').slice(0, 10) === end);
      if (match) return match;
      if (jobs.length < 100) return null;
      skip += 100;
    }
  }
  async function loadBase() {
    const [jobs, companies] = await Promise.all([getJobs(), getCompanies()]);
    state.jobs = jobs;
    state.companies = companies;
    return { jobs, companies };
  }
  const companyFor = (job) => state.companies.find((item) => item.id === job?.company_id) || null;
  const agentFor = (type, runs = state.currentAgents) => runs.find((run) => run.agent_type === type) || null;
  const outputFor = (type, runs = state.currentAgents) => agentFor(type, runs)?.output_data || {};

  function route() {
    const [page = 'dashboard', id] = (location.hash.slice(1) || 'dashboard').split('/');
    return { page, id };
  }
  function navPage(page) { return ['job', 'decision', 'financial', 'market', 'risk', 'competitors', 'news', 'report'].includes(page) ? 'history' : page; }
  function setPageHead(page, description) {
    const [title, defaultDescription] = PAGE_META[page] || PAGE_META.dashboard;
    $('#pageTitle').textContent = title;
    $('#pageDesc').textContent = description || defaultDescription;
    $('#pageCrumb').textContent = title;
    $('#eyebrow').textContent = page === 'dashboard' ? 'FINSIGHT AI' : 'RESEARCH WORKSPACE';
    $('#headAction').style.display = ['dashboard', 'history', 'companies'].includes(page) ? '' : 'none';
    const active = navPage(page);
    document.querySelectorAll('#nav a[data-page]').forEach((link) => link.classList.toggle('active', link.dataset.page === active));
  }

  function showNotice(message, type = 'info') {
    notice.textContent = message;
    notice.className = `notice show ${type}`;
    clearTimeout(showNotice.timer);
    showNotice.timer = setTimeout(() => { notice.className = 'notice'; }, 7000);
  }
  function loading(message = 'Loading live data…') {
    return `<div class="loading"><span class="spinner"></span>${escapeHtml(message)}</div>`;
  }
  function statusBadge(status = 'pending') {
    const safeStatus = ['pending', 'running', 'completed', 'failed'].includes(status) ? status : 'pending';
    return `<span class="badge ${safeStatus}">${safeStatus}</span>`;
  }
  function formatDate(value, includeTime = false) {
    if (!value) return 'Unavailable';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return escapeHtml(value);
    return date.toLocaleString(undefined, includeTime
      ? { dateStyle: 'medium', timeStyle: 'short' }
      : { year: 'numeric', month: 'short', day: 'numeric' });
  }
  function formatNumber(value, currency = '') {
    if (value === null || value === undefined || value === '') return 'Unavailable';
    const number = Number(value);
    if (!Number.isFinite(number)) return escapeHtml(value);
    try {
      return new Intl.NumberFormat(undefined, currency
        ? { style: 'currency', currency, maximumFractionDigits: 2 }
        : { maximumFractionDigits: 2 }).format(number);
    } catch {
      return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number)}${currency ? ` ${escapeHtml(currency)}` : ''}`;
    }
  }
  function formatPercent(value) {
    if (value === null || value === undefined || value === '') return 'Unavailable';
    const number = Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : escapeHtml(value);
  }
  function metricCard(label, value, detail = '') {
    return `<div class="metric"><span>${escapeHtml(label)}</span><b>${escapeHtml(value ?? 'Unavailable')}</b>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div>`;
  }
  function metricGrid(entries, className = '') {
    return `<div class="metric-grid ${className}">${entries.map(([label, value, detail]) => metricCard(label, value, detail)).join('')}</div>`;
  }
  function empty(message) { return `<div class="empty">${escapeHtml(message)}</div>`; }
  function chartPanel(title, subtitle, key, description, hasData) {
    return panel(title, subtitle, hasData && window.Chart
      ? `<div class="chart-box"><canvas id="${key}" role="img" aria-label="${escapeHtml(description)}"></canvas></div>`
      : empty(!window.Chart ? 'Chart.js is unavailable. Reload to try again.' : 'The stored agent output does not contain enough data for this visualization.'));
  }
  function makeChart(canvasId, config) {
    const canvas = $(`#${canvasId}`);
    if (!canvas || !window.Chart) return;
    const chart = new Chart(canvas, config);
    state.charts.push(chart);
  }
  const chartColors = ['#53a4ff', '#34c99a', '#f5b94c', '#bb8cff', '#ff7885'];
  function chartOptions(extra = {}) {
    return { responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: 'index' },
      plugins: { legend: { labels: { color: '#a9b8ca', usePointStyle: true, boxWidth: 7, font: { size: 10 } } }, tooltip: { backgroundColor: '#101e2e', borderColor: '#2b4058', borderWidth: 1, titleColor: '#e7eef8', bodyColor: '#c2cede' } },
      scales: { x: { ticks: { color: '#8797ad', maxTicksLimit: 8 }, grid: { color: '#ffffff0b' } }, y: { ticks: { color: '#8797ad' }, grid: { color: '#ffffff0b' } } }, ...extra };
  }
  function num(value) { const n = Number(value); return value !== null && value !== '' && Number.isFinite(n) ? n : null; }
  function metricValue(item) { return num(item && typeof item === 'object' ? item.value : item); }
  function safeLink(value) {
    try {
      const url = new URL(value);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
    } catch { return '#'; }
  }
  function panel(title, subtitle, body, actions = '') {
    return `<section class="panel"><div class="panel-head"><div><h2>${escapeHtml(title)}</h2>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}</div>${actions}</div>${body}</section>`;
  }
  function companyLink(job) {
    const company = companyFor(job) || {};
    return `<div class="company-cell"><b>${escapeHtml(company.company_name || 'Company')}</b><small>${escapeHtml(company.ticker_symbol || '—')}${company.exchange ? ` · ${escapeHtml(company.exchange)}` : ''}</small></div>`;
  }
  function jobTable(jobs) {
    if (!jobs.length) return empty('No research jobs match this view.');
    return `<div class="table-wrap"><table><thead><tr><th>Company</th><th>Job</th><th>Research period</th><th>Created</th><th>Status</th><th></th></tr></thead><tbody>${jobs.map((job) => `<tr>
      <td>${companyLink(job)}</td><td>#${job.id}</td>
      <td>${formatDate(job.research_period_start)} – ${formatDate(job.research_period_end)}</td>
      <td>${formatDate(job.created_at)}</td><td>${statusBadge(job.status)}</td>
      <td><a class="text-link" href="#job/${job.id}">${job.status === 'completed' ? 'Open research' : 'View progress'} →</a></td>
    </tr>`).join('')}</tbody></table></div>`;
  }
  function agentTabs(jobId, active = '') {
    const pages = [
      ['decision', 'Investment decision'], ['financial', 'Financials'], ['market', 'Market'],
      ['risk', 'Risk'], ['competitors', 'Peers'], ['news', 'News'], ['report', 'Final report'],
    ];
    return `<nav class="analysis-tabs" aria-label="Research analysis">${pages.map(([page, label]) => `<a class="${active === page ? 'active' : ''}" href="#${page}/${jobId}">${label}</a>`).join('')}</nav>`;
  }
  function listItems(items, emptyMessage = 'No data was returned by the agent.') {
    if (!Array.isArray(items) || !items.length) return empty(emptyMessage);
    return `<ul class="evidence-list">${items.map((item) => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
  }

  async function checkConnection() {
    const indicator = $('#connection');
    try {
      await api('/health');
      indicator.className = 'connection online';
      indicator.innerHTML = '<span></span>Backend connected';
    } catch {
      indicator.className = 'connection offline';
      indicator.innerHTML = '<span></span>Backend offline';
    }
  }

  async function dashboard() {
    setPageHead('dashboard', 'Live research activity, company search, and stored investment reports.');
    content.innerHTML = loading('Loading research jobs and companies…');
    try {
      const { jobs, companies } = await loadBase();
      const counts = ['completed', 'running', 'failed', 'pending'].map((status) => jobs.filter((job) => job.status === status).length);
      const latest = jobs[0];
      const latestAgents = latest ? await api(`/api/research-jobs/${latest.id}/agents`) : [];
      const latestOutput = (type) => latestAgents.find((run) => run.agent_type === type && run.status === 'completed')?.output_data || {};
      const latestMarket = latestOutput('market_data');
      const latestPrices = Array.isArray(latestMarket.historical_prices) ? latestMarket.historical_prices : [];
      const latestDecision = latestOutput('investment_decision');
      const recent = jobs.slice(0, 6);
      const recentCompanies = [...new Set(jobs.map((job) => job.company_id))]
        .slice(0, 6)
        .map((companyId) => ({ company: companies.find((item) => item.id === companyId), job: jobs.find((item) => item.company_id === companyId) }))
        .filter((item) => item.company);
      content.innerHTML = `
        <section class="search-hero panel">
          <div><span class="section-kicker">MARKET RESEARCH WORKSPACE</span><h2>Research a company</h2><p>Search your registered companies or start a fresh seven-agent analysis.</p></div>
          <form id="companySearch" class="company-search"><label for="companyQuery">Company or ticker</label><div><input id="companyQuery" class="field" placeholder="Search AAPL, Apple…" autocomplete="off"><button class="button primary" type="submit">Search</button></div></form>
        </section>
        <div id="companySearchResults"></div>
        <div class="stats">${[
          ['Research jobs', jobs.length, 'All stored jobs'], ['Completed', counts[0], 'Reports available'],
          ['Running', counts[1], 'In progress'], ['Failed', counts[2], 'Require review'], ['Companies', companies.length, 'Registered'],
        ].map(([label, value, foot]) => `<div class="stat"><span class="stat-label">${label}</span><b class="stat-value">${value}</b><small class="stat-foot">${foot}</small></div>`).join('')}</div>
        <div class="grid-two">
          ${panel('Latest agent activity', latest ? `Job #${latest.id} · ${companyFor(latest)?.ticker_symbol || 'Company'}` : 'No research has been started', latest ? `${agentCards(latestAgents, latest.id)}<a class="text-link block-link" href="#job/${latest.id}">Open live research →</a>` : empty('Start a research job to see agent activity.'))}
          ${panel('Start a new analysis', 'Use the existing company and job API workflow', `<p class="summary">Run financial, news, market, risk, competitor, investment decision, and report generation agents in dependency order.</p><a href="#new-research" class="button primary inline-button">Start new research →</a>`)}
        </div>
        <div class="grid-two">${panel('Recently researched companies', 'Most recent company jobs in the database', recentCompanies.length ? `<div class="company-results">${recentCompanies.map(({ company, job }) => `<article class="company-result"><div><b>${escapeHtml(company.company_name)}</b><small>${escapeHtml(company.ticker_symbol)} · ${escapeHtml(company.exchange)}</small></div><a class="text-link" href="#job/${job.id}">Job #${job.id} · ${escapeHtml(job.status)} →</a></article>`).join('')}</div>` : empty('No company has been researched yet.'))}${panel('Recent research jobs', 'Loaded from the FastAPI research-jobs endpoint', jobTable(recent), '<a class="text-link" href="#history">View history →</a>')}</div>
        <div class="grid-two">${chartPanel('Latest market performance', latest ? `Job #${latest.id} · ${latestPrices.length} stored observations` : 'No completed market output', 'dashboardPriceChart', 'Latest researched stock closing prices and trading volume', latestPrices.some((item) => num(item.close) !== null))}${chartPanel('Investment score profile', latest ? `Job #${latest.id} · agent-reported category scores` : 'No completed decision output', 'dashboardDecisionChart', 'Latest investment decision category score breakdown', !!latestDecision.category_scores)}</div>
      `;
      $('#companySearch').onsubmit = (event) => {
        event.preventDefault();
        const query = $('#companyQuery').value.trim().toLowerCase();
        const matches = companies.filter((company) => `${company.company_name} ${company.ticker_symbol} ${company.exchange}`.toLowerCase().includes(query));
        const jobsForMatches = jobs.filter((job) => matches.some((company) => company.id === job.company_id));
        const host = $('#companySearchResults');
        if (!query) { host.innerHTML = ''; return; }
        host.innerHTML = `<section class="panel search-results"><div class="panel-head"><div><h2>Search results</h2><p>${matches.length} registered compan${matches.length === 1 ? 'y' : 'ies'} found</p></div><a class="button ghost small" href="#new-research">Research a ticker →</a></div>${matches.length ? `<div class="company-results">${matches.map((company) => {
          const latestJob = jobsForMatches.filter((job) => job.company_id === company.id).sort((a, b) => b.id - a.id)[0];
          return `<article class="company-result"><div><b>${escapeHtml(company.company_name)}</b><small>${escapeHtml(company.ticker_symbol)} · ${escapeHtml(company.exchange)}</small></div>${latestJob ? `<a class="text-link" href="#job/${latestJob.id}">Latest job #${latestJob.id} ${statusBadge(latestJob.status)}</a>` : `<a class="text-link" href="#new-research/${company.id}">Start research for this company →</a>`}</article>`;
        }).join('')}</div>` : empty('No registered company matched. Start new research to register it.')}</section>`;
      };
      requestAnimationFrame(() => {
        const points = latestPrices.filter((item) => num(item.close) !== null);
        if (points.length) makeChart('dashboardPriceChart', { type: 'line', data: { labels: points.map((item) => item.date), datasets: [
          { label: `Close (${latestMarket.currency || 'currency unavailable'})`, data: points.map((item) => num(item.close)), yAxisID: 'price', borderColor: chartColors[0], backgroundColor: '#53a4ff18', fill: true, tension: .22, pointRadius: 0, borderWidth: 2 },
          { label: 'Volume', data: points.map((item) => num(item.volume)), yAxisID: 'volume', type: 'bar', backgroundColor: '#34c99a44', borderColor: '#34c99a', borderWidth: 0, barPercentage: .8 },
        ] }, options: chartOptions({ scales: { x: { ticks: { color: '#8797ad', maxTicksLimit: 8 }, grid: { color: '#ffffff0b' } }, price: { position: 'left', ticks: { color: '#8797ad' }, grid: { color: '#ffffff0b' }, title: { display: true, text: latestMarket.currency || 'Price', color: '#8797ad' } }, volume: { position: 'right', ticks: { color: '#8797ad', callback: (v) => Intl.NumberFormat(undefined, { notation: 'compact' }).format(v) }, grid: { display: false } } } }) });
        const categories = latestDecision.category_scores || {};
        const entries = Object.entries(categories).filter(([, item]) => num(item?.score) !== null);
        if (entries.length) makeChart('dashboardDecisionChart', { type: 'bar', data: { labels: entries.map(([key]) => key.replaceAll('_', ' ')), datasets: [{ label: 'Score / 100', data: entries.map(([, item]) => num(item.score)), backgroundColor: entries.map((_, i) => `${chartColors[i % chartColors.length]}bb`), borderRadius: 4 }] }, options: chartOptions({ indexAxis: 'y', scales: { x: { min: 0, max: 100, ticks: { color: '#8797ad' }, grid: { color: '#ffffff0b' } }, y: { ticks: { color: '#a9b8ca' }, grid: { display: false } } } }) });
      });
    } catch (error) {
      content.innerHTML = panel('Dashboard unavailable', 'The live API request failed', `<div class="error-card">${escapeHtml(error.message)}</div><button class="button ghost" id="retryDashboard">Retry</button>`);
      $('#retryDashboard').onclick = dashboard;
    }
  }

  function agentOutputPreview(type, output) {
    const financial = output.financial_metrics || {};
    const risk = output.market_risk_metrics || {};
    const financialRisk = output.financial_risk_metrics || {};
    // if (type === 'financial_statement') {
    //   return metricGrid([
    //     ['Revenue', formatNumber(financial.revenue)], ['Net income', formatNumber(financial.net_income)],
    //     ['Assets', formatNumber(financial.total_assets)], ['Liabilities', formatNumber(financial.total_liabilities)],
    //     ['Operating cash flow', formatNumber(financial.operating_cash_flow)], ['Capital expenditures', formatNumber(financial.capital_expenditures)],
    //   ]);
    // }
    if (type === 'financial_statement') {
      return metricGrid(financialMetrics(output));
    }
    if (type === 'market_data') {
      return metricGrid([
        ['Current price', formatNumber(output.current_price, output.currency)], ['Previous close', formatNumber(output.previous_close, output.currency)],
        ['Market capitalization', formatNumber(output.market_cap, output.currency)], ['Trading days', output.total_trading_days],
      ]);
    }
    if (type === 'risk_analysis') {
      return metricGrid([
        ['Annualized volatility', formatPercent(risk.annualized_volatility)], ['Maximum drawdown', formatPercent(risk.maximum_drawdown)],
        ['Net profit margin', formatPercent(financialRisk.net_profit_margin)], ['Liabilities / assets', formatPercent(financialRisk.liabilities_to_assets_ratio)],
      ]);
    }
    if (type === 'competitor_analysis') {
      return `<p class="summary">${Number(output.comparison_summary?.successful_comparisons ?? 0)} successful peer comparisons</p>${competitorTable(output.competitors || [])}`;
    }
    if (type === 'news_research') {
      const articles = output.articles || [];
      return articles.length ? `<div class="article-list">${articles.slice(0, 3).map(articleCard).join('')}</div>` : empty('No news articles were returned.');
    }
    if (type === 'investment_decision') {
      return `<div class="decision-inline"><b>${escapeHtml(output.investment_assessment || 'Assessment unavailable')}</b><span>${output.overall_score == null ? 'No score' : `${escapeHtml(output.overall_score)}/100`}</span><small>Confidence: ${escapeHtml(output.confidence_level || 'Unavailable')}</small></div>`;
    }
    if (type === 'report_generation') return `<p class="summary">${escapeHtml(output.report_title || 'Consolidated report generated.')}</p>`;
    return empty('Agent output is not available yet.');
  }

  function agentCards(runs, jobId) {
    const byType = Object.fromEntries(runs.map((run) => [run.agent_type, run]));
    const completed = AGENTS.filter(([type]) => byType[type]?.status === 'completed').length;
    const overall = Math.round(completed / AGENTS.length * 100);
    return `<div class="overall-progress"><div><b>Workflow progress</b><span>${completed} of 7 agents completed · ${overall}%</span></div><div class="progress overall"><i style="width:${overall}%"></i></div></div><div class="agents">${AGENTS.map(([type, title, description], index) => {
      const run = byType[type];
      const status = run?.status || 'pending';
      const width = status === 'completed' || status === 'failed' ? 100 : status === 'running' ? 32 : 0;
      const detailRoute = { investment_decision: 'decision', report_generation: 'report', financial_statement: 'financial', market_data: 'market', risk_analysis: 'risk', competitor_analysis: 'competitors', news_research: 'news' }[type];
      const detailLink = run?.output_data && jobId ? `<a class="text-link" href="#${detailRoute}/${jobId}">View agent output →</a>` : '';
      const failure = status === 'failed' && run?.error_message ? `<div class="error-card agent-error"><b>Agent error</b><p>${escapeHtml(run.error_message)}</p></div>` : '';
      return `<article class="agent ${status}"><div class="agent-top"><span class="agent-index">0${index + 1}</span><div><b class="agent-name">${title}</b><small class="agent-desc">${description}</small></div>${statusBadge(status)}</div><div class="progress"><i class="${status === 'running' ? 'is-running' : ''}" style="width:${width}%"></i></div><div class="agent-foot"><span>${run?.completed_at ? `Completed ${formatDate(run.completed_at, true)}` : run?.started_at ? `Started ${formatDate(run.started_at, true)}` : 'Waiting for dependencies'}</span>${detailLink}</div>${run?.output_data ? `<div class="agent-output">${agentOutputPreview(type, run.output_data)}</div>` : ''}${failure}</article>`;
    }).join('')}</div>`;
  }

  function getPendingWorkflow() {
    try { return JSON.parse(sessionStorage.getItem('finsight-pending-workflow') || 'null'); }
    catch { return null; }
  }
  function savePendingWorkflow(value) { sessionStorage.setItem('finsight-pending-workflow', JSON.stringify(value)); }
  function requestKey(ticker, exchange, start, end) { return [ticker.toUpperCase(), exchange.trim().toLowerCase(), start, end].join('|'); }
  function toggleNewCompanyFields(visible) {
    $('#newCompanyFields').hidden = !visible;
    $('#companyMatch').hidden = visible;
    $('#companyName').required = visible;
    $('#country').required = visible;
  }

  function newResearch(companyId = null) {
    setPageHead('new-research');
    const today = new Date();
    const endDefault = today.toISOString().slice(0, 10);
    const startDate = new Date(today);
    startDate.setFullYear(startDate.getFullYear() - 1);
    content.innerHTML = `
      <section class="panel form-panel"><div class="panel-head"><div><h2>Configure stock research</h2><p>Company identity and date range are sent using the existing backend schemas.</p></div></div>
      <form id="researchForm" novalidate>
        <div class="form-grid">
          <div class="form-field"><label for="ticker">Ticker symbol *</label><input class="field" id="ticker" required maxlength="32" placeholder="AAPL" autocomplete="off"></div>
          <div class="form-field"><label for="exchange">Exchange *</label><input class="field" id="exchange" required maxlength="100" placeholder="NASDAQ" autocomplete="off"></div>
          <div class="form-field"><label for="startDate">Research start date *</label><input class="field" id="startDate" type="date" required value="${startDate.toISOString().slice(0, 10)}"></div>
          <div class="form-field"><label for="endDate">Research end date *</label><input class="field" id="endDate" type="date" required value="${endDefault}"></div>
        </div>
        <div class="company-match" id="companyMatch" hidden></div>
        <div class="new-company-fields" id="newCompanyFields" hidden>
          <h3>Register this company</h3><p class="form-note">The company endpoint requires a name, ticker, exchange, and country. Optional profile fields may be left blank.</p>
          <div class="form-grid">
            <div class="form-field"><label for="companyName">Company name *</label><input class="field" id="companyName" maxlength="255" placeholder="Apple Inc."></div>
            <div class="form-field"><label for="country">Country *</label><input class="field" id="country" maxlength="100" placeholder="United States"></div>
            <div class="form-field"><label for="sector">Sector</label><input class="field" id="sector" maxlength="150" placeholder="Optional"></div>
            <div class="form-field"><label for="industry">Industry</label><input class="field" id="industry" maxlength="150" placeholder="Optional"></div>
            <div class="form-field"><label for="currency">Currency</label><input class="field" id="currency" maxlength="10" placeholder="USD"></div>
          </div>
        </div>
        <div class="form-note form-footnote">The end date year selects the fiscal year used by the financial agent. Both dates are required by this workflow.</div>
        <div class="form-actions"><button class="button ghost" type="button" id="lookupCompany">Check company</button><button class="button primary" id="startResearch" type="submit">Start seven-agent research →</button></div>
      </form></section>
      <section class="panel"><div class="panel-head"><div><h2>Research sequence</h2><p>The backend controls execution order and job state.</p></div></div><div class="workflow-strip">${AGENTS.map(([type, title], index) => `<span><i>${index + 1}</i>${title.replace(' Agent', '')}</span>`).join('')}</div></section>`;

    let matchedCompany = null;
    async function lookup() {
      const ticker = $('#ticker').value.trim().toUpperCase();
      const exchange = $('#exchange').value.trim();
      if (!ticker || !exchange) { showNotice('Enter both a ticker and exchange to check the company directory.', 'error'); return; }
      const button = $('#lookupCompany');
      button.disabled = true;
      button.textContent = 'Checking…';
      try {
        matchedCompany = await api(`/api/companies/${encodeURIComponent(ticker)}?exchange=${encodeURIComponent(exchange)}`);
        toggleNewCompanyFields(false);
        $('#companyMatch').innerHTML = `<b>${escapeHtml(matchedCompany.company_name)}</b><span>${escapeHtml(matchedCompany.ticker_symbol)} · ${escapeHtml(matchedCompany.exchange)} · ${escapeHtml(matchedCompany.country)}</span><small>Registered company found. The existing company record will be used.</small>`;
        $('#companyMatch').hidden = false;
      } catch (error) {
        if (error.status === 404) {
          matchedCompany = null;
          $('#companyName').value = '';
          $('#country').value = '';
          toggleNewCompanyFields(true);
          $('#companyMatch').hidden = true;
        } else showNotice(error.message, 'error');
      } finally {
        button.disabled = false;
        button.textContent = 'Check company';
      }
    }
    $('#lookupCompany').onclick = lookup;
    $('#ticker').addEventListener('change', () => { matchedCompany = null; toggleNewCompanyFields(false); $('#companyMatch').hidden = true; });
    $('#exchange').addEventListener('change', () => { matchedCompany = null; toggleNewCompanyFields(false); $('#companyMatch').hidden = true; });
    if (companyId) {
      getCompanies().then((companies) => {
        state.companies = companies;
        const company = companies.find((item) => String(item.id) === String(companyId));
        if (!company) return;
        $('#ticker').value = company.ticker_symbol;
        $('#exchange').value = company.exchange;
        lookup();
      }).catch((error) => showNotice(error.message, 'error'));
    }

    $('#researchForm').onsubmit = async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!form.reportValidity()) return;
      const button = $('#startResearch');
      if (button.disabled) return;
      const ticker = $('#ticker').value.trim().toUpperCase();
      const exchange = $('#exchange').value.trim();
      const start = $('#startDate').value;
      const end = $('#endDate').value;
      if (start > end) { showNotice('Start date must be on or before the end date.', 'error'); return; }
      const key = requestKey(ticker, exchange, start, end);
      button.disabled = true;
      $('#lookupCompany').disabled = true;
      button.innerHTML = '<span class="spinner"></span> Starting workflow…';
      try {
        let company = matchedCompany;
        if (!company || company.ticker_symbol.toUpperCase() !== ticker || company.exchange.toLowerCase() !== exchange.toLowerCase()) {
          try { company = await api(`/api/companies/${encodeURIComponent(ticker)}?exchange=${encodeURIComponent(exchange)}`); }
          catch (error) {
            if (error.status !== 404) throw error;
            if (!$('#companyName').value.trim() || !$('#country').value.trim()) {
              toggleNewCompanyFields(true);
              throw new Error('Enter the company name and country, then start again.');
            }
            try {
              company = await api('/api/companies', {
                method: 'POST', body: JSON.stringify({
                  company_name: $('#companyName').value.trim(), ticker_symbol: ticker,
                  exchange, country: $('#country').value.trim(),
                  sector: $('#sector').value.trim() || null, industry: $('#industry').value.trim() || null,
                  currency: $('#currency').value.trim().toUpperCase() || null,
                })
              });
            } catch (createError) {
              if (createError.status !== 409) throw createError;
              company = await api(`/api/companies/${encodeURIComponent(ticker)}?exchange=${encodeURIComponent(exchange)}`);
            }
          }
        }

        let marker = getPendingWorkflow();
        let job = null;
        if (marker?.key === key) {
          job = await api(`/api/research-jobs/${marker.jobId}`);
        } else {
          job = await findExistingJob(company.id, start, end);
          if (!job) {
            job = await api('/api/research-jobs', {
              method: 'POST', body: JSON.stringify({
                company_id: company.id,
                research_period_start: `${start}T00:00:00`,
                research_period_end: `${end}T00:00:00`,
              })
            });
          }
          marker = { key, jobId: job.id };
          savePendingWorkflow(marker);
        }
        if (job.status !== 'pending') {
          if (['running', 'completed'].includes(job.status)) { location.hash = `#job/${job.id}`; return; }
          throw new Error(`Job #${job.id} is ${job.status} and will not be restarted. Choose a different research date range to create a fresh job.`);
        }

        await api(`/api/research-jobs/${job.id}/agents`, { method: 'POST' });
        job = await api(`/api/research-jobs/${job.id}`);
        if (job.status === 'pending') {
          await api(`/api/research-jobs/${job.id}/run`, { method: 'POST' });
        }
        location.hash = `#job/${job.id}`;
      } catch (error) {
        showNotice(error.message, 'error');
        button.disabled = false;
        $('#lookupCompany').disabled = false;
        button.textContent = 'Start seven-agent research →';
      }
    };
  }

  async function history() {
    setPageHead('history');
    content.innerHTML = loading('Loading research history…');
    try {
      const { jobs } = await loadBase();
      renderHistory(jobs);
    } catch (error) { content.innerHTML = panel('Research history unavailable', '', `<div class="error-card">${escapeHtml(error.message)}</div>`); }
  }
  function renderHistory(jobs) {
    const query = state.historyQuery.trim().toLowerCase();
    let rows = jobs.filter((job) => {
      const company = companyFor(job) || {};
      const matchesQuery = !query || `${company.company_name} ${company.ticker_symbol} ${job.id}`.toLowerCase().includes(query);
      return matchesQuery && (state.historyStatus === 'all' || job.status === state.historyStatus);
    });
    rows.sort((a, b) => state.historySort === 'oldest' ? a.id - b.id : b.id - a.id);
    const pageSize = 20;
    const pages = Math.max(1, Math.ceil(rows.length / pageSize));
    state.historyPage = Math.min(state.historyPage, pages);
    const pageRows = rows.slice((state.historyPage - 1) * pageSize, state.historyPage * pageSize);
    const first = rows.length ? (state.historyPage - 1) * pageSize + 1 : 0;
    const last = Math.min(state.historyPage * pageSize, rows.length);
    content.innerHTML = panel('All research jobs', `${rows.length} stored jobs · newest jobs first by default`, `
      <div class="filters"><input class="field" id="historySearch" value="${escapeHtml(state.historyQuery)}" placeholder="Search ticker, company, or job ID"><select class="field" id="historyStatus">${['all', 'pending', 'running', 'completed', 'failed'].map((status) => `<option value="${status}" ${state.historyStatus === status ? 'selected' : ''}>${status === 'all' ? 'All statuses' : status}</option>`).join('')}</select><select class="field" id="historySort"><option value="newest" ${state.historySort === 'newest' ? 'selected' : ''}>Newest first</option><option value="oldest" ${state.historySort === 'oldest' ? 'selected' : ''}>Oldest first</option></select></div>${jobTable(pageRows)}<div class="pagination"><span>Showing ${first}–${last} of ${rows.length} · Page ${state.historyPage} of ${pages}</span><div><button class="button ghost small" id="historyPrev" ${state.historyPage <= 1 ? 'disabled' : ''}>Previous</button> <button class="button ghost small" id="historyNext" ${state.historyPage >= pages ? 'disabled' : ''}>Next</button></div></div>`,
      '<a class="button primary small" href="#new-research">New research</a>');
    $('#historySearch').oninput = (event) => { state.historyQuery = event.target.value; state.historyPage = 1; renderHistory(jobs); const input = $('#historySearch'); input.focus(); input.setSelectionRange(input.value.length, input.value.length); };
    $('#historyStatus').onchange = (event) => { state.historyStatus = event.target.value; state.historyPage = 1; renderHistory(jobs); };
    $('#historySort').onchange = (event) => { state.historySort = event.target.value; state.historyPage = 1; renderHistory(jobs); };
    $('#historyPrev').onclick = () => { state.historyPage -= 1; renderHistory(jobs); };
    $('#historyNext').onclick = () => { state.historyPage += 1; renderHistory(jobs); };
  }

  async function companies() {
    setPageHead('companies'); content.innerHTML = loading('Loading registered companies…');
    try {
      const { jobs, companies: rows } = await loadBase();
      content.innerHTML = panel('Company directory', `${rows.length} companies loaded from the backend`, rows.length ? `<div class="table-wrap"><table><thead><tr><th>Company</th><th>Exchange</th><th>Country</th><th>Sector</th><th>Currency</th><th>Research jobs</th><th></th></tr></thead><tbody>${rows.map((company) => {
        const companyJobs = jobs.filter((job) => job.company_id === company.id);
        const latest = companyJobs[0];
        return `<tr><td><div class="company-cell"><b>${escapeHtml(company.company_name)}</b><small>${escapeHtml(company.ticker_symbol)}</small></div></td><td>${escapeHtml(company.exchange)}</td><td>${escapeHtml(company.country)}</td><td>${escapeHtml(company.sector || 'Unavailable')}</td><td>${escapeHtml(company.currency || 'Unavailable')}</td><td>${companyJobs.length}</td><td>${latest ? `<a class="text-link" href="#job/${latest.id}">Latest job →</a>` : '—'}</td></tr>`;
      }).join('')}</tbody></table></div>` : empty('No companies have been registered yet.'), '<a class="button primary small" href="#new-research">New research</a>');
    } catch (error) { content.innerHTML = panel('Company directory unavailable', '', `<div class="error-card">${escapeHtml(error.message)}</div>`); }
  }

  async function loadResearch(id) {
    const [job, runs] = await Promise.all([api(`/api/research-jobs/${id}`), api(`/api/research-jobs/${id}/agents`)]);
    state.currentJob = job;
    state.currentAgents = runs;
    if (!state.companies.length) state.companies = await getCompanies();
    return { job, runs, company: companyFor(job) || {} };
  }
  function scheduleRefresh(id, status) {
    clearTimeout(state.timer);
    if (status === 'running' || status === 'pending') state.timer = setTimeout(() => renderJob(id), 4000);
  }
  async function jobView(id) {
    setPageHead('job', `Live updates from research job #${id}.`);
    content.innerHTML = loading(`Loading job #${id} and agent output…`);
    try {
      const { job, runs, company } = await loadResearch(id);
      const completed = runs.filter((run) => run.status === 'completed').length;
      content.innerHTML = `<section class="job-hero panel"><div><span class="section-kicker">RESEARCH JOB #${escapeHtml(id)}</span><h2>${escapeHtml(company.company_name || 'Company')} <small>${escapeHtml(company.ticker_symbol || '')}</small></h2><p>${escapeHtml(company.exchange || '')} · ${formatDate(job.research_period_start)} – ${formatDate(job.research_period_end)}</p></div><div class="job-hero-status">${statusBadge(job.status)}<small>${completed} / 7 agents completed</small></div></section>
        ${job.error_message ? `<div class="error-card job-error"><b>Job error</b><p>${escapeHtml(job.error_message)}</p></div>` : ''}
        ${agentTabs(id)}
        ${panel('Seven-agent workflow', job.status === 'running' ? 'Automatically refreshed every four seconds while running.' : 'Current stored status and outputs for each agent.', agentCards(runs, id), `<button class="button ghost small" id="refreshJob">Refresh now</button>`)}
        ${metricGrid([['Created', formatDate(job.created_at, true)], ['Started', formatDate(job.started_at, true)], ['Completed', formatDate(job.completed_at, true)], ['Agent records', `${runs.length} / 7`]])}`;
      $('#refreshJob').onclick = () => renderJob(id);
      scheduleRefresh(id, job.status);
    } catch (error) {
      content.innerHTML = panel(`Job #${escapeHtml(id)} unavailable`, 'The job detail or agent endpoint returned an error', `<div class="error-card">${escapeHtml(error.message)}</div><a class="text-link" href="#history">Back to research history →</a>`);
      clearTimeout(state.timer);
    }
  }
  const renderJob = (id) => jobView(id);

  function financialMetrics(output) {
    const metrics = output.financial_metrics || {};
    const value = (name) => {
      const item = metrics[name];
      return item && typeof item === 'object' && 'value' in item ? item.value : item;
    };
    return [
      ['Revenue', value('revenue')], ['Net income', value('net_income')], ['Total assets', value('total_assets')],
      ['Total liabilities', value('total_liabilities')], ['Operating cash flow', value('operating_cash_flow')], ['Capital expenditures', value('capital_expenditures')],
    ].map(([label, amount]) => [label, formatNumber(amount)]);
  }

  function categoryScores(decision) {
    const labels = [
      ['financial_health', 'Financial health'], ['news_sentiment', 'News sentiment'],
      ['market_performance', 'Market performance'], ['risk_assessment', 'Risk assessment'],
      ['competitive_position', 'Competitive position'],
    ];
    return labels.map(([key, label]) => {
      const item = decision.category_scores?.[key];
      const score = item?.score ?? decision[`${key}_score`];
      return [label, score == null ? 'Unavailable' : `${score} / 100`, item?.coverage == null ? '' : `${Math.round(item.coverage * 100)}% data coverage`];
    });
  }
  function articleCard(article) {
    const publisher = article.source || 'Publisher unavailable';
    const sentiment = article.sentiment || article.sentiment_label;
    return `<article class="article"><a href="${escapeHtml(safeLink(article.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.title || 'Headline unavailable')}</a><p>${escapeHtml(article.description || 'No article summary was provided.')}</p><div class="article-meta"><span>${escapeHtml(publisher)}</span><span>${formatDate(article.published_at, true)}</span>${sentiment ? `<span class="sentiment">${escapeHtml(sentiment)}</span>` : '<span class="muted">Sentiment not supplied</span>'}</div></article>`;
  }
  function competitorTable(peers, target = null) {
    const entries = [...(target ? [{ ...target, comparison_role: 'Target' }] : []), ...(Array.isArray(peers) ? peers : [])];
    if (!entries.length) return empty('No peer profiles were stored by the competitor agent.');
    const fields = [
      ['Company', (item) => `${escapeHtml(item.company_name || 'Unavailable')}<small class="table-sub">${escapeHtml(item.ticker_symbol || '')} ${item.comparison_role ? `· ${item.comparison_role}` : ''}</small>`],
      ['Currency', (item) => escapeHtml(item.currency || 'Unavailable')],
      ['Revenue', (item) => formatNumber(item.total_revenue, item.currency)],
      ['Market cap', (item) => formatNumber(item.market_cap, item.currency)],
      ['Profit margin', (item) => formatPercent(item.profit_margin)],
      ['Return on equity', (item) => formatPercent(item.return_on_equity)],
      ['Debt / equity', (item) => formatNumber(item.debt_to_equity)],
      ['P/E', (item) => formatNumber(item.price_to_earnings)],
    ];
    return `<div class="currency-note">Currency is shown per company. Values are not converted or compared across currencies.</div><div class="table-wrap"><table><thead><tr>${fields.map(([label]) => `<th>${label}</th>`).join('')}</tr></thead><tbody>${entries.map((item) => `<tr class="${item.status === 'failed' ? 'failed-row' : ''}">${fields.map(([, render], index) => `<td>${index === 0 ? render(item) : item.status === 'failed' ? escapeHtml(item.error || 'Profile unavailable') : render(item)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function renderChart(canvas, prices, currency) {
    if (!window.Chart || !canvas || !prices?.length) return;
    const valid = prices.filter((item) => num(item.close) !== null);
    if (!valid.length) return;
    makeChart(canvas.id, { type: 'line', data: { labels: valid.map((item) => item.date), datasets: [
      { label: `Close (${currency || 'currency unavailable'})`, data: valid.map((item) => num(item.close)), yAxisID: 'price', borderColor: chartColors[0], backgroundColor: '#53a4ff18', fill: true, tension: .22, pointRadius: 0, borderWidth: 2 },
      { label: 'Volume', data: valid.map((item) => num(item.volume)), yAxisID: 'volume', type: 'bar', backgroundColor: '#34c99a44', borderColor: '#34c99a', borderWidth: 0, barPercentage: .8 },
    ] }, options: chartOptions({ scales: { x: { ticks: { maxTicksLimit: 8, color: '#8797ad' }, grid: { color: '#ffffff0b' } }, price: { position: 'left', ticks: { color: '#8797ad' }, grid: { color: '#ffffff0b' }, title: { display: true, text: currency || 'Price', color: '#8797ad' } }, volume: { position: 'right', ticks: { color: '#8797ad', callback: (v) => Intl.NumberFormat(undefined, { notation: 'compact' }).format(v) }, grid: { display: false } } } }) });
  }

  async function analysisPage(page, id) {
    setPageHead(page, `Actual stored agent output for research job #${id}.`);
    content.innerHTML = loading(`Loading ${PAGE_META[page][0].toLowerCase()} from job #${id}…`);
    try {
      const { job, runs, company } = await loadResearch(id);
      const reportRun = agentFor('report_generation', runs);
      let report = reportRun?.output_data || {};
      if (page === 'report' && reportRun?.status === 'completed') {
        const reportResponse = await api(`/api/research-jobs/${id}/report`);
        report = reportResponse.report || report;
      }
      const decision = outputFor('investment_decision', runs);
      const financial = outputFor('financial_statement', runs);
      const market = outputFor('market_data', runs);
      const risk = outputFor('risk_analysis', runs);
      const competitor = outputFor('competitor_analysis', runs);
      const news = outputFor('news_research', runs);
      const dataByPage = {
        decision: agentFor('investment_decision', runs), financial: agentFor('financial_statement', runs),
        market: agentFor('market_data', runs), risk: agentFor('risk_analysis', runs),
        competitors: agentFor('competitor_analysis', runs), news: agentFor('news_research', runs),
        report: reportRun,
      }[page];
      const routePage = page === 'report' ? 'report' : page;
      let body = '';
      if (!dataByPage || dataByPage.status !== 'completed' || !dataByPage.output_data) {
        body = `<div class="agent-state-panel">${statusBadge(dataByPage?.status || 'pending')}<h2>${escapeHtml(PAGE_META[page][0])} output is not available yet</h2><p>Only stored agent output is shown here. This view will update when the agent completes.</p>${dataByPage?.error_message ? `<div class="error-card">${escapeHtml(dataByPage.error_message)}</div>` : ''}<a class="button ghost" href="#job/${id}">View agent progress</a></div>`;
      } else if (routePage === 'decision') {
        body = `<div class="decision-hero"><div><span class="section-kicker">INVESTMENT DECISION AGENT</span><h2>${escapeHtml(decision.investment_assessment || 'Assessment unavailable')}</h2><p>${escapeHtml(decision.final_explanation || 'No explanation was returned by the decision agent.')}</p></div><div class="score-orb"><b>${decision.overall_score == null ? '—' : escapeHtml(decision.overall_score)}</b><small>OUT OF 100</small></div></div>
          ${metricGrid([['Confidence', decision.confidence_level], ['Data coverage', decision.data_coverage == null ? 'Unavailable' : `${Math.round(decision.data_coverage * 100)}%`], ['Financial health', decision.financial_health_score == null ? 'Unavailable' : `${decision.financial_health_score} / 100`], ['News sentiment', decision.news_sentiment_score == null ? 'Unavailable' : `${decision.news_sentiment_score} / 100`], ['Market performance', decision.market_performance_score == null ? 'Unavailable' : `${decision.market_performance_score} / 100`], ['Risk assessment', decision.risk_assessment_score == null ? 'Unavailable' : `${decision.risk_assessment_score} / 100`], ['Competitive position', decision.competitive_position_score == null ? 'Unavailable' : `${decision.competitive_position_score} / 100`]])}
          ${chartPanel('Investment score breakdown', 'Agent reported category scores and coverage', 'decisionScoreChart', 'Investment decision category score breakdown', Object.values(decision.category_scores || {}).some((item) => num(item?.score) !== null))}
          ${panel('Category score detail', 'Scores and evidence returned by the decision agent', metricGrid(categoryScores(decision)))}
          <div class="grid-two">${panel('Positive factors', '', listItems(decision.positive_factors))}${panel('Negative factors', '', listItems(decision.negative_factors))}</div>
          <div class="grid-two">${panel('Major investment risks', '', listItems(decision.major_investment_risks))}${panel('Reasons supporting assessment', '', listItems(decision.reasons_supporting_assessment))}</div>
          <div class="grid-two">${panel('Missing or unreliable data', '', listItems(decision.missing_or_unreliable_data))}${panel('Conditions that could change the assessment', '', listItems(decision.conditions_that_could_change_assessment))}</div>
          ${panel('Scoring methodology', 'Provided by the Investment Decision Agent', `<p class="summary">${escapeHtml(decision.scoring_methodology || 'Unavailable')}</p><div class="source-list">${Object.entries(decision.category_weights || {}).map(([name, weight]) => `<span>${escapeHtml(name.replaceAll('_', ' '))}<b>${Math.round(Number(weight) * 100)}%</b></span>`).join('')}</div>`)}`;
        requestAnimationFrame(() => {
          const entries = Object.entries(decision.category_scores || {}).filter(([, item]) => num(item?.score) !== null);
          if (entries.length) makeChart('decisionScoreChart', { type: 'bar', data: { labels: entries.map(([key]) => key.replaceAll('_', ' ')), datasets: [{ label: 'Score / 100', data: entries.map(([, item]) => num(item.score)), backgroundColor: entries.map((_, i) => `${chartColors[i % chartColors.length]}bb`), borderRadius: 4 }] }, options: chartOptions({ indexAxis: 'y', scales: { x: { min: 0, max: 100, ticks: { color: '#8797ad' }, grid: { color: '#ffffff0b' } }, y: { ticks: { color: '#a9b8ca' }, grid: { display: false } } } }) });
        });
      } else if (routePage === 'financial') {
        const fm = financial.financial_metrics || {};
        const revenue = metricValue(fm.revenue), income = metricValue(fm.net_income);
        body = `${metricGrid(financialMetrics(financial))}${chartPanel('Reported revenue and net income', `FY ${financial.fiscal_year ?? 'Unavailable'} · ${fm.revenue?.unit || fm.net_income?.unit || 'unit unavailable'}`, 'financialChart', 'Reported annual revenue and net income', revenue !== null || income !== null)}${panel('Financial data provenance', 'Stored Financial Statement Agent output', `<p><b>Source:</b> ${escapeHtml(financial.source || 'Unavailable')}</p><p><b>Fiscal year:</b> ${escapeHtml(financial.fiscal_year ?? 'Unavailable')}</p><p><b>Retrieved:</b> ${formatDate(financial.retrieved_at_utc, true)}</p>${financial.source_url ? `<a class="text-link" target="_blank" rel="noopener noreferrer" href="${escapeHtml(safeLink(financial.source_url))}">Open source filing data →</a>` : ''}`)}`;
        requestAnimationFrame(() => { const vals = [revenue, income]; if (vals.some((v) => v !== null)) makeChart('financialChart', { type: 'bar', data: { labels: ['Revenue', 'Net income'], datasets: [{ label: `FY ${financial.fiscal_year ?? ''} (${fm.revenue?.unit || fm.net_income?.unit || 'reported units'})`, data: vals, backgroundColor: [chartColors[0], chartColors[1]], borderRadius: 5 }] }, options: chartOptions({ plugins: { ...chartOptions().plugins, legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatNumber(ctx.raw, fm.revenue?.unit || fm.net_income?.unit) } } }, scales: { x: { ticks: { color: '#a9b8ca' }, grid: { display: false } }, y: { ticks: { color: '#8797ad', callback: (v) => Intl.NumberFormat(undefined, { notation: 'compact' }).format(v) }, grid: { color: '#ffffff0b' } } } }) }); });
      } else if (routePage === 'market') {
        const prices = market.historical_prices || [];
        const volumes = prices.map((price) => Number(price.volume)).filter(Number.isFinite);
        const latestVolume = prices.at(-1)?.volume;
        const priceTable = prices.length
          ? `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead><tbody>${prices.slice(-30).reverse().map((item) => `<tr><td>${formatDate(item.date)}</td><td>${formatNumber(item.open, market.currency)}</td><td>${formatNumber(item.high, market.currency)}</td><td>${formatNumber(item.low, market.currency)}</td><td>${formatNumber(item.close, market.currency)}</td><td>${formatNumber(item.volume)}</td></tr>`).join('')}</tbody></table></div>`
          : empty('No historical rows were stored.');
        body = `${metricGrid([['Current price', formatNumber(market.current_price, market.currency)], ['Previous close', formatNumber(market.previous_close, market.currency)], ['Market capitalization', formatNumber(market.market_cap, market.currency)], ['Latest trading volume', formatNumber(latestVolume)], ['52-week high', formatNumber(market.fifty_two_week_high, market.currency)], ['52-week low', formatNumber(market.fifty_two_week_low, market.currency)]])}
          ${chartPanel('Historical close and volume', `${prices.length} stored trading days · ${escapeHtml(market.currency || 'Currency unavailable')}`, 'priceChart', 'Historical stock closing price and trading volume', prices.some((item) => num(item.close) !== null))}
          ${panel('Historical market data', 'Price and volume values from the stored market output', priceTable)}
          <p class="form-note">${volumes.length} historical volume values are available. Source: ${escapeHtml(market.source || 'Unavailable')} · Retrieved ${formatDate(market.retrieved_at_utc, true)}.</p>`;
        requestAnimationFrame(() => renderChart($('#priceChart'), prices, market.currency));
      } else if (routePage === 'risk') {
        const marketRisk = risk.market_risk_metrics || {};
        const financialRisk = risk.financial_risk_metrics || {};
        const riskItems = [['Annualized volatility', num(marketRisk.annualized_volatility)], ['Maximum drawdown', num(marketRisk.maximum_drawdown)], ['Net profit margin', num(financialRisk.net_profit_margin)], ['Liabilities / assets', num(financialRisk.liabilities_to_assets_ratio)]].filter(([, value]) => value !== null);
        body = `${metricGrid([['Annualized volatility', formatPercent(marketRisk.annualized_volatility)], ['Maximum drawdown', formatPercent(marketRisk.maximum_drawdown)], ['Net profit margin', formatPercent(financialRisk.net_profit_margin)], ['Liabilities / assets', formatPercent(financialRisk.liabilities_to_assets_ratio)], ['Trading days analyzed', marketRisk.historical_trading_days]])}
          ${chartPanel('Risk profile', 'Reported ratios from market and financial risk outputs', 'riskChart', 'Reported risk metrics', riskItems.length > 0)}
          ${panel('Major investment risks', 'Actual risks identified by the decision agent', listItems(decision.major_investment_risks))}
          ${panel('Risk data sources', '', listItems(risk.data_sources))}`;
        requestAnimationFrame(() => { if (riskItems.length) makeChart('riskChart', { type: 'bar', data: { labels: riskItems.map(([label]) => label), datasets: [{ label: 'Reported ratio', data: riskItems.map(([, value]) => value * 100), backgroundColor: riskItems.map((_, i) => `${chartColors[i % chartColors.length]}bb`), borderRadius: 4 }] }, options: chartOptions({ scales: { x: { ticks: { color: '#a9b8ca' }, grid: { display: false } }, y: { ticks: { color: '#8797ad', callback: (v) => `${v}%` }, grid: { color: '#ffffff0b' } } } }) }); });
      } else if (routePage === 'competitors') {
        const peers = (competitor.competitors || []).filter((item) => item.status !== 'failed');
        const target = competitor.target_company;
        const comparable = [target, ...peers].filter((item) => item && item.currency === target?.currency && num(item.total_revenue) !== null);
        body = `${panel('Company profile', 'Target profile returned by the competitor agent', competitorTable([], target))}${chartPanel('Revenue comparison', `Companies with reported revenue in ${target?.currency || 'the same currency'}`, 'competitorChart', 'Competitor revenue comparison in source currency', comparable.length > 1)}${panel('Peer comparison', 'Each metric retains its source company currency', competitorTable(competitor.competitors || []))}`;
        requestAnimationFrame(() => { if (comparable.length > 1) makeChart('competitorChart', { type: 'bar', data: { labels: comparable.map((item) => item.ticker_symbol || item.company_name), datasets: [{ label: `Revenue (${target.currency})`, data: comparable.map((item) => num(item.total_revenue)), backgroundColor: comparable.map((_, i) => `${chartColors[i % chartColors.length]}bb`), borderRadius: 4 }] }, options: chartOptions({ plugins: { ...chartOptions().plugins, tooltip: { callbacks: { label: (ctx) => formatNumber(ctx.raw, target.currency) } } }, scales: { x: { ticks: { color: '#a9b8ca' }, grid: { display: false } }, y: { ticks: { color: '#8797ad', callback: (v) => Intl.NumberFormat(undefined, { notation: 'compact' }).format(v) }, grid: { color: '#ffffff0b' } } } }) }); });
      } else if (routePage === 'news') {
        const articles = news.articles || [];
        body = `${metricGrid([['Articles found', news.total_results], ['Publisher', news.source], ['Sentiment output', articles.some((item) => item.sentiment || item.sentiment_label) ? 'Per-article values available' : 'Not supplied by news agent']])}
          ${panel('News articles', `${articles.length} articles stored in this job`, articles.length ? `<div class="article-list">${articles.map(articleCard).join('')}</div>` : empty('No news articles were returned by the News Research Agent.'))}
          ${decision.news_sentiment_score != null ? panel('Decision agent news score', `${decision.news_sentiment_score} / 100`, listItems((decision.reasons_supporting_assessment || []).filter((item) => /news|sentiment/i.test(item)))) : ''}`;
      } else {
        const reportData = report;
        const consolidated = [
          ['Executive summary', reportData.executive_summary],
          ['Financial analysis', JSON.stringify(reportData.financial_analysis || {}, null, 2)],
          ['Market analysis', JSON.stringify(reportData.market_analysis || {}, null, 2)],
          ['Risk analysis', JSON.stringify(reportData.risk_analysis || {}, null, 2)],
          ['News analysis', JSON.stringify(reportData.news_analysis || {}, null, 2)],
          ['Competitor analysis', JSON.stringify(reportData.competitor_analysis || {}, null, 2)],
        ];
        body = `<div class="report-actions"><span>${statusBadge(job.status)} ${escapeHtml(company.company_name || '')} · Job #${job.id}</span><button class="button primary" id="printReport">Print / Save as PDF</button></div>
          ${reportData.final_assessment ? `<div class="decision-hero compact"><div><span class="section-kicker">FINAL ASSESSMENT</span><h2>${escapeHtml(reportData.final_assessment)}</h2><p>${escapeHtml(reportData.executive_summary || '')}</p></div><div class="score-orb"><b>${reportData.overall_score == null ? '—' : escapeHtml(reportData.overall_score)}</b><small>OUT OF 100</small></div></div>` : ''}
          ${consolidated.map(([title, value]) => panel(title, '', value && title === 'Executive summary' ? `<p class="summary">${escapeHtml(value)}</p>` : `<pre class="report-json">${escapeHtml(value)}</pre>`)).join('')}
          ${panel('Investment decision output', 'Stored decision agent result embedded in the report', `<p><a class="text-link" href="#decision/${id}">Open full investment decision analysis →</a></p><pre class="report-json">${escapeHtml(JSON.stringify(reportData.investment_decision || decision, null, 2))}</pre>`)}
          ${panel('Report metadata', 'Fields returned by Report Generation Agent', `<pre class="report-json">${escapeHtml(JSON.stringify({ report_title: reportData.report_title, generated_at_utc: reportData.generated_at_utc, data_sources: reportData.data_sources, agent_status: reportData.agent_status }, null, 2))}</pre>`)}`;
      }
      const companyLabel = `${company.company_name || 'Company'} ${company.ticker_symbol ? `(${company.ticker_symbol})` : ''}`;
      content.innerHTML = `<section class="job-hero panel"><div><span class="section-kicker">JOB #${job.id} · ${escapeHtml(companyLabel)}</span><h2>${escapeHtml(PAGE_META[page][0])}</h2><p>${formatDate(job.research_period_start)} – ${formatDate(job.research_period_end)}</p></div><div>${statusBadge(job.status)}<small class="block-muted">Agent status: ${escapeHtml(dataByPage?.status || 'unavailable')}</small></div></section>${agentTabs(id, page)}${body}`;
      $('#printReport')?.addEventListener('click', () => window.print());
      scheduleRefresh(id, job.status);
    } catch (error) {
      content.innerHTML = panel(`${PAGE_META[page][0]} unavailable`, `Job #${escapeHtml(id)}`, `<div class="error-card">${escapeHtml(error.message)}</div><a class="button ghost" href="#job/${id}">Return to job progress</a>`);
      clearTimeout(state.timer);
    }
  }

  async function settings() {
    setPageHead('settings');
    content.innerHTML = panel('Backend connection', 'This API URL is stored in this browser only.', `
      <form id="settingsForm"><div class="form-field"><label for="apiBase">FastAPI base URL</label><input class="field" id="apiBase" type="url" required value="${escapeHtml(API)}" placeholder="http://127.0.0.1:8000"></div>
      <p class="form-note">The frontend calls the existing /health and /api routes. The backend must allow the frontend origin through CORS.</p>
      <button class="button primary" type="submit">Save backend URL</button></form>`);
    $('#settingsForm').onsubmit = (event) => {
      event.preventDefault();
      const value = $('#apiBase').value.trim().replace(/\/$/, '');
      try { new URL(value); } catch { showNotice('Enter a valid URL.', 'error'); return; }
      localStorage.setItem('finsight-api', value);
      showNotice('Backend URL saved. Reloading the application…', 'success');
      setTimeout(() => location.reload(), 500);
    };
  }

  async function render() {
    clearTimeout(state.timer);
    state.charts.forEach((chart) => chart.destroy()); state.charts = [];
    notice.className = 'notice';
    const { page, id } = route();
    if (page === 'dashboard') await dashboard();
    else if (page === 'new-research') newResearch(id);
    else if (page === 'history') await history();
    else if (page === 'companies') await companies();
    else if (page === 'job') await jobView(id);
    else if (['decision', 'financial', 'market', 'risk', 'competitors', 'news', 'report'].includes(page) && id) await analysisPage(page, id);
    else if (page === 'settings') await settings();
    else { location.hash = '#dashboard'; return; }
    checkConnection();
  }

  window.addEventListener('hashchange', render);
  window.addEventListener('beforeunload', () => { clearTimeout(state.timer); state.charts.forEach((chart) => chart.destroy()); });
  render();
})();
