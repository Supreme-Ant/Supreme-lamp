/* ═══════════════════════════════════════════════════
   Crypto Trading Bot Dashboard - Frontend
   ═══════════════════════════════════════════════════ */

const REFRESH_MS = 15000;
let equityChart = null;
let strategyChart = null;
let historyDays = 7;

// ── Initialization ──────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initChartControls();
    refreshAll();
    setInterval(refreshAll, REFRESH_MS);
});

// ── Tabs ────────────────────────────────────────────

function initTabs() {
    document.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        });
    });
}

function initChartControls() {
    document.querySelectorAll('.chip[data-days]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.chip[data-days]').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            historyDays = parseInt(btn.dataset.days);
            loadEquityChart();
        });
    });
}

// ── Data Fetching ───────────────────────────────────

async function api(url) {
    try {
        const r = await fetch(url);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return await r.json();
    } catch (e) {
        console.error('API error:', url, e);
        return null;
    }
}

async function refreshAll() {
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

    const [summary, positions, trades, tradesFull, signals, risk, botStatus, strategies, performance] =
        await Promise.all([
            api('/api/portfolio/summary'),
            api('/api/portfolio/positions'),
            api('/api/trades?limit=10'),
            api('/api/trades?limit=50'),
            api('/api/strategies/signals'),
            api('/api/risk/status'),
            api('/api/bot/status'),
            api('/api/strategies/status'),
            api('/api/portfolio/performance'),
        ]);

    if (summary) renderKPIs(summary);
    if (positions) {
        renderPositionsMini(positions);
        renderPositionsFull(positions);
    }
    if (trades) renderTradesTable('trades-body-overview', trades);
    if (tradesFull) renderTradesTable('trades-body-full', tradesFull);
    if (signals) renderSignals(signals);
    if (risk) renderRisk(risk);
    if (botStatus) renderBotStatus(botStatus);
    if (strategies || performance) renderStrategies(strategies, performance);
    if (performance) renderStrategyChart(performance);

    loadEquityChart();
}

// ── KPIs ────────────────────────────────────────────

function renderKPIs(d) {
    setKPI('total-value', fmtUSD(d.total_value_usdt));
    setKPI('available-usdt', fmtUSD(d.available_usdt));
    setKPI('daily-pnl', fmtPnL(d.daily_pnl), d.daily_pnl);
    setKPI('total-pnl', fmtPnL(d.total_pnl), d.total_pnl);
    setKPI('unrealized-pnl', fmtPnL(d.unrealized_pnl), d.unrealized_pnl);
    setKPI('num-positions', d.num_positions);
}

function setKPI(id, text, numVal) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.classList.remove('positive', 'negative');
    if (numVal !== undefined) {
        if (numVal > 0) el.classList.add('positive');
        else if (numVal < 0) el.classList.add('negative');
    }
}

// ── Bot Status ──────────────────────────────────────

function renderBotStatus(s) {
    const badge = document.getElementById('bot-status');
    badge.textContent = s.mode.toUpperCase();
    badge.className = 'mode-badge ' + s.mode;
}

// ── Equity Chart ────────────────────────────────────

async function loadEquityChart() {
    const data = await api('/api/portfolio/history?days=' + historyDays);
    if (!data) return;

    const labels = data.map(d => {
        const dt = new Date(d.timestamp);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    const balances = data.map(d => d.total_balance);
    const pnls = data.map(d => d.total_pnl);

    const ctx = document.getElementById('equity-chart');
    if (!ctx) return;

    if (equityChart) equityChart.destroy();

    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, 'rgba(59,130,246,.25)');
    gradient.addColorStop(1, 'rgba(59,130,246,.01)');

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Balance',
                    data: balances,
                    borderColor: '#3b82f6',
                    backgroundColor: gradient,
                    fill: true,
                    tension: .35,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#3b82f6',
                },
                {
                    label: 'PnL',
                    data: pnls,
                    borderColor: '#a78bfa',
                    backgroundColor: 'transparent',
                    borderWidth: 1.5,
                    borderDash: [4, 3],
                    tension: .35,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#a78bfa',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: {
                        color: '#6b7a90',
                        font: { family: "'SF Mono', monospace", size: 11 },
                        boxWidth: 12,
                        boxHeight: 2,
                        padding: 16,
                    },
                },
                tooltip: {
                    backgroundColor: '#1a2030',
                    borderColor: '#2a3548',
                    borderWidth: 1,
                    titleColor: '#e4e8ef',
                    bodyColor: '#6b7a90',
                    titleFont: { family: "'SF Mono', monospace", size: 12 },
                    bodyFont: { family: "'SF Mono', monospace", size: 11 },
                    padding: 10,
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': ' + fmtUSD(ctx.raw),
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(30,39,54,.5)', drawBorder: false },
                    ticks: { color: '#3d4a5c', font: { size: 10 }, maxRotation: 0 },
                },
                y: {
                    grid: { color: 'rgba(30,39,54,.5)', drawBorder: false },
                    ticks: {
                        color: '#3d4a5c',
                        font: { size: 10 },
                        callback: v => '$' + v.toLocaleString(),
                    },
                },
            },
        },
    });
}

// ── Strategy Doughnut ───────────────────────────────

function renderStrategyChart(perf) {
    const names = Object.keys(perf);
    if (names.length === 0) return;

    const colors = {
        ai: '#3b82f6',
        copy: '#a78bfa',
        signal: '#22d3ee',
        manual: '#f59e0b',
    };

    const ctx = document.getElementById('strategy-chart');
    if (!ctx) return;

    if (strategyChart) strategyChart.destroy();

    strategyChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: names.map(n => n.charAt(0).toUpperCase() + n.slice(1)),
            datasets: [{
                data: names.map(n => perf[n].total_trades),
                backgroundColor: names.map(n => colors[n] || '#6b7a90'),
                borderColor: '#151a23',
                borderWidth: 3,
                hoverOffset: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '68%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a2030',
                    borderColor: '#2a3548',
                    borderWidth: 1,
                    titleColor: '#e4e8ef',
                    bodyColor: '#6b7a90',
                    titleFont: { family: "'SF Mono', monospace", size: 12 },
                    bodyFont: { family: "'SF Mono', monospace", size: 11 },
                    padding: 10,
                },
            },
        },
    });

    // Custom legend
    const legendEl = document.getElementById('strategy-legend');
    legendEl.innerHTML = names.map(n => `
        <div class="legend-item">
            <span class="legend-dot" style="background:${colors[n] || '#6b7a90'}"></span>
            ${n.charAt(0).toUpperCase() + n.slice(1)} (${perf[n].total_trades})
        </div>
    `).join('');
}

// ── Risk Status ─────────────────────────────────────

function renderRisk(r) {
    const maxPos = r.max_positions || 5;
    const openPos = r.open_positions || 0;
    const posPct = Math.min((openPos / maxPos) * 100, 100);

    document.getElementById('risk-positions').textContent = openPos + ' / ' + maxPos;
    document.getElementById('risk-positions-bar').style.width = posPct + '%';

    document.getElementById('risk-daily-pnl').textContent = fmtPnL(r.daily_pnl);
    const dailyPct = r.daily_loss_limit_pct
        ? Math.min(Math.abs(r.daily_pnl || 0) / (r.daily_loss_limit_pct * 100) * 100, 100)
        : 0;
    document.getElementById('risk-daily-bar').style.width = dailyPct + '%';

    const drawdown = r.drawdown_pct || 0;
    const maxDD = r.max_drawdown_pct || 10;
    document.getElementById('risk-drawdown').textContent = drawdown.toFixed(1) + '%';
    document.getElementById('risk-drawdown-bar').style.width = Math.min((drawdown / maxDD) * 100, 100) + '%';

    const cooldownEl = document.getElementById('risk-cooldown');
    cooldownEl.textContent = r.cooldown_active ? 'ACTIVE' : 'Off';
    cooldownEl.style.color = r.cooldown_active ? 'var(--red)' : '';

    document.getElementById('risk-peak').textContent = fmtUSD(r.peak_balance);
    document.getElementById('risk-streak').textContent = r.consecutive_losses || '0';
}

// ── Positions ───────────────────────────────────────

function renderPositionsMini(positions) {
    const el = document.getElementById('positions-mini');
    if (!positions || positions.length === 0) {
        el.innerHTML = '<div class="empty-msg">No open positions</div>';
        return;
    }
    el.innerHTML = positions.map(p => {
        const pnlClass = p.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        return `
            <div class="pos-card ${p.side}">
                <div class="pos-info">
                    <span class="pos-symbol">${p.symbol}</span>
                    <span class="pos-meta">${p.side.toUpperCase()} &middot; ${p.amount.toFixed(6)} &middot; ${p.strategy}</span>
                </div>
                <div style="display:flex;align-items:center">
                    <div class="pos-pnl">
                        <span class="pos-pnl-val ${pnlClass}">${fmtPnL(p.unrealized_pnl)}</span>
                        <span class="pos-pnl-pct ${pnlClass}">${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(1)}%</span>
                    </div>
                    <button class="pos-close-btn" onclick="closePosition(${p.id})">Close</button>
                </div>
            </div>`;
    }).join('');
}

function renderPositionsFull(positions) {
    const tbody = document.getElementById('positions-body');
    if (!positions || positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="empty-cell">No open positions</td></tr>';
        return;
    }
    tbody.innerHTML = positions.map(p => {
        const pnlClass = p.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        const sideClass = p.side === 'long' ? 'side-long' : 'side-short';
        return `<tr>
            <td><strong>${p.symbol}</strong></td>
            <td class="${sideClass}">${p.side.toUpperCase()}</td>
            <td>${fmtPrice(p.entry_price)}</td>
            <td>${fmtPrice(p.current_price)}</td>
            <td>${p.amount.toFixed(6)}</td>
            <td>${fmtUSD(p.current_value)}</td>
            <td class="${pnlClass}">${fmtPnL(p.unrealized_pnl)}</td>
            <td class="${pnlClass}">${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(1)}%</td>
            <td>${fmtPrice(p.stop_loss)} / ${fmtPrice(p.take_profit)}</td>
            <td>${p.strategy}</td>
            <td>${fmtTime(p.opened_at)}</td>
            <td><button class="pos-close-btn" onclick="closePosition(${p.id})">Close</button></td>
        </tr>`;
    }).join('');
}

// ── Trades Table ────────────────────────────────────

function renderTradesTable(tbodyId, trades) {
    const tbody = document.getElementById(tbodyId);
    const cols = tbodyId === 'trades-body-full' ? 10 : 9;
    if (!trades || trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${cols}" class="empty-cell">No trades yet</td></tr>`;
        return;
    }
    const showFee = tbodyId === 'trades-body-full';
    tbody.innerHTML = trades.map(t => {
        const sideClass = t.side === 'buy' ? 'side-buy' : 'side-sell';
        const pnlClass = (t.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
        const modeBadge = t.is_paper
            ? '<span class="badge badge-paper">Paper</span>'
            : '<span class="badge badge-live">Live</span>';
        const feeCol = showFee ? `<td>${t.fee ? fmtUSD(t.fee) : '--'}</td>` : '';
        return `<tr>
            <td>${fmtTime(t.created_at)}</td>
            <td><strong>${t.symbol}</strong></td>
            <td class="${sideClass}">${t.side.toUpperCase()}</td>
            <td>${t.amount.toFixed(6)}</td>
            <td>${fmtPrice(t.price)}</td>
            <td>${fmtUSD(t.cost)}</td>
            ${feeCol}
            <td class="${pnlClass}">${t.pnl != null ? fmtPnL(t.pnl) : '--'}</td>
            <td>${t.strategy}</td>
            <td>${modeBadge}</td>
        </tr>`;
    }).join('');
}

// ── Signals ─────────────────────────────────────────

function renderSignals(signals) {
    const tbody = document.getElementById('signals-body');
    if (!signals || signals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No signals yet</td></tr>';
        return;
    }
    tbody.innerHTML = signals.map(s => {
        const actionClass = s.action === 'buy' ? 'side-buy' : s.action === 'sell' ? 'side-sell' : '';
        return `<tr>
            <td>${fmtTime(s.created_at)}</td>
            <td><strong>${s.symbol}</strong></td>
            <td class="${actionClass}">${s.action.toUpperCase()}</td>
            <td>${(s.confidence * 100).toFixed(0)}%</td>
            <td>${s.ta_score != null ? s.ta_score.toFixed(2) : '--'}</td>
            <td>${s.ml_score != null ? s.ml_score.toFixed(2) : '--'}</td>
            <td>${s.acted_on ? '<span class="pnl-positive">Yes</span>' : '<span style="color:var(--text-muted)">No</span>'}</td>
        </tr>`;
    }).join('');
}

// ── Strategies ──────────────────────────────────────

function renderStrategies(statuses, performance) {
    const grid = document.getElementById('strategies-grid');
    const names = { ai: 'AI Trading', copy: 'Copy Trading', signal: 'Signal Following' };
    const icons = { ai: '&#9733;', copy: '&#8644;', signal: '&#9889;' };

    grid.innerHTML = Object.entries(names).map(([key, label]) => {
        const status = statuses && statuses[key];
        const perf = performance && performance[key];
        const isActive = status && status.is_active;
        const dotClass = isActive ? 'active' : 'inactive';
        const statusText = isActive ? 'Running' : 'Stopped';
        const toggleClass = isActive ? 'running' : 'stopped';
        const toggleText = isActive ? 'Stop Strategy' : 'Start Strategy';

        const totalTrades = perf ? perf.total_trades : 0;
        const winRate = perf ? perf.win_rate.toFixed(0) + '%' : '--';
        const totalPnl = perf ? fmtPnL(perf.total_pnl) : '--';
        const avgPnl = perf ? fmtPnL(perf.avg_pnl) : '--';
        const pnlClass = perf && perf.total_pnl >= 0 ? 'pnl-positive' : perf && perf.total_pnl < 0 ? 'pnl-negative' : '';

        return `
            <div class="strat-card">
                <div class="strat-top">
                    <span class="strat-name">${icons[key]} ${label}</span>
                    <span class="strat-status"><span class="strat-dot ${dotClass}"></span>${statusText}</span>
                </div>
                <div class="strat-metrics">
                    <div class="strat-metric">
                        <span class="strat-metric-label">Trades</span>
                        <span class="strat-metric-value">${totalTrades}</span>
                    </div>
                    <div class="strat-metric">
                        <span class="strat-metric-label">Win Rate</span>
                        <span class="strat-metric-value">${winRate}</span>
                    </div>
                    <div class="strat-metric">
                        <span class="strat-metric-label">Total PnL</span>
                        <span class="strat-metric-value ${pnlClass}">${totalPnl}</span>
                    </div>
                    <div class="strat-metric">
                        <span class="strat-metric-label">Avg PnL</span>
                        <span class="strat-metric-value">${avgPnl}</span>
                    </div>
                </div>
                <button class="strat-toggle ${toggleClass}" onclick="toggleStrategy('${key}')">
                    ${toggleText}
                </button>
            </div>`;
    }).join('');
}

// ── Actions ─────────────────────────────────────────

async function closePosition(positionId) {
    if (!confirm('Close this position at market price?')) return;
    try {
        const r = await fetch('/api/positions/' + positionId + '/close', { method: 'POST' });
        if (r.ok) refreshAll();
        else alert('Failed to close position');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function toggleStrategy(name) {
    const cards = document.querySelectorAll('.strat-card');
    let isActive = false;
    cards.forEach(c => {
        if (c.querySelector('.strat-name').textContent.toLowerCase().includes(name === 'ai' ? 'ai' : name)) {
            isActive = c.querySelector('.strat-dot').classList.contains('active');
        }
    });
    const action = isActive ? 'stop' : 'start';
    try {
        await fetch('/api/strategies/' + name + '/' + action, { method: 'POST' });
        refreshAll();
    } catch (e) {
        console.error('Toggle error:', e);
    }
}

async function submitManualTrade(event) {
    event.preventDefault();
    const symbol = document.getElementById('trade-symbol').value;
    const side = document.querySelector('input[name="side"]:checked').value;
    const amount = parseFloat(document.getElementById('trade-amount').value);
    const resultDiv = document.getElementById('trade-result');

    try {
        const r = await fetch('/api/trades/manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, side, amount }),
        });
        const data = await r.json();
        if (r.ok && !data.error) {
            resultDiv.className = 'trade-result success';
            resultDiv.textContent = 'Order placed: ' + side.toUpperCase() + ' ' + symbol + ' ($' + amount.toFixed(2) + ')';
            refreshAll();
            setTimeout(() => { resultDiv.className = 'trade-result'; }, 5000);
        } else {
            resultDiv.className = 'trade-result error';
            resultDiv.textContent = 'Error: ' + (data.error || data.detail || 'Order failed');
        }
    } catch (e) {
        resultDiv.className = 'trade-result error';
        resultDiv.textContent = 'Error: ' + e.message;
    }
}

// ── Formatters ──────────────────────────────────────

function fmtUSD(v) {
    if (v == null) return '--';
    return '$' + parseFloat(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPnL(v) {
    if (v == null) return '--';
    const n = parseFloat(v);
    const prefix = n >= 0 ? '+' : '';
    return prefix + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPrice(v) {
    if (v == null) return '--';
    const n = parseFloat(v);
    if (n >= 1000) return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (n >= 1) return '$' + n.toFixed(4);
    return '$' + n.toFixed(8);
}

function fmtTime(iso) {
    if (!iso) return '--';
    return new Date(iso).toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
}
