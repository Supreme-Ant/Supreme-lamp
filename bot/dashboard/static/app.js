/* Crypto Trading Bot Dashboard - Frontend JavaScript */

const REFRESH_INTERVAL = 15000; // 15 seconds
let countdown = 15;

// ── Initialization ──────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
    setInterval(refreshAll, REFRESH_INTERVAL);
    setInterval(updateCountdown, 1000);
});

function updateCountdown() {
    countdown--;
    if (countdown <= 0) countdown = 15;
    document.getElementById('refresh-countdown').textContent = countdown;
}

// ── Data Fetching ───────────────────────────────────

async function fetchJSON(url) {
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
    } catch (e) {
        console.error(`Fetch error: ${url}`, e);
        return null;
    }
}

async function refreshAll() {
    countdown = 15;
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

    // Fetch all data in parallel
    const [summary, positions, trades, signals, risk, botStatus, strategies] = await Promise.all([
        fetchJSON('/api/portfolio/summary'),
        fetchJSON('/api/portfolio/positions'),
        fetchJSON('/api/trades?limit=20'),
        fetchJSON('/api/strategies/signals'),
        fetchJSON('/api/risk/status'),
        fetchJSON('/api/bot/status'),
        fetchJSON('/api/strategies/status'),
    ]);

    if (summary) renderPortfolio(summary);
    if (positions) renderPositions(positions);
    if (trades) renderTrades(trades);
    if (signals) renderSignals(signals);
    if (risk) renderRisk(risk);
    if (botStatus) renderBotStatus(botStatus);
    if (strategies) renderStrategies(strategies);
}

// ── Rendering ───────────────────────────────────────

function renderPortfolio(data) {
    setMetric('total-value', formatUSD(data.total_value_usdt));
    setMetric('available-usdt', formatUSD(data.available_usdt));
    setMetric('daily-pnl', formatPnL(data.daily_pnl));
    setMetric('total-pnl', formatPnL(data.total_pnl));
    setMetric('unrealized-pnl', formatPnL(data.unrealized_pnl));
    setMetric('num-positions', data.num_positions);
}

function renderPositions(positions) {
    const tbody = document.getElementById('positions-body');
    if (!positions || positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty">No open positions</td></tr>';
        return;
    }
    tbody.innerHTML = positions.map(p => `
        <tr>
            <td><strong>${p.symbol}</strong></td>
            <td class="side-${p.side === 'long' ? 'buy' : 'sell'}">${p.side.toUpperCase()}</td>
            <td>${formatPrice(p.entry_price)}</td>
            <td>${formatPrice(p.current_price)}</td>
            <td>${p.amount.toFixed(6)}</td>
            <td class="${p.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                ${formatPnL(p.unrealized_pnl)}
            </td>
            <td class="${p.unrealized_pnl_pct >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                ${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(1)}%
            </td>
            <td>${p.strategy}</td>
            <td><button class="btn-danger" onclick="closePosition(${p.id})">Close</button></td>
        </tr>
    `).join('');
}

function renderTrades(trades) {
    const tbody = document.getElementById('trades-body');
    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty">No trades yet</td></tr>';
        return;
    }
    tbody.innerHTML = trades.map(t => `
        <tr>
            <td>${formatTime(t.created_at)}</td>
            <td><strong>${t.symbol}</strong></td>
            <td class="side-${t.side}">${t.side.toUpperCase()}</td>
            <td>${t.amount.toFixed(6)}</td>
            <td>${formatPrice(t.price)}</td>
            <td>${formatUSD(t.cost)}</td>
            <td class="${(t.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                ${t.pnl != null ? formatPnL(t.pnl) : '--'}
            </td>
            <td>${t.strategy}</td>
            <td>${t.is_paper ? 'PAPER' : 'LIVE'}</td>
        </tr>
    `).join('');
}

function renderSignals(signals) {
    const tbody = document.getElementById('signals-body');
    if (!signals || signals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">No signals yet</td></tr>';
        return;
    }
    tbody.innerHTML = signals.map(s => `
        <tr>
            <td>${formatTime(s.created_at)}</td>
            <td><strong>${s.symbol}</strong></td>
            <td class="side-${s.action === 'buy' ? 'buy' : s.action === 'sell' ? 'sell' : ''}">${s.action.toUpperCase()}</td>
            <td>${(s.confidence * 100).toFixed(0)}%</td>
            <td>${s.ta_score ? s.ta_score.toFixed(2) : '--'}</td>
            <td>${s.ml_score ? s.ml_score.toFixed(2) : '--'}</td>
            <td>${s.acted_on ? 'Yes' : 'No'}</td>
        </tr>
    `).join('');
}

function renderRisk(risk) {
    setMetric('risk-positions', `${risk.open_positions}/${risk.max_positions}`);
    setMetric('risk-daily-pnl', formatPnL(risk.daily_pnl));
    setMetric('risk-cooldown', risk.cooldown_active ? 'ACTIVE' : 'Off');
    setMetric('risk-peak', formatUSD(risk.peak_balance));

    const cooldownEl = document.getElementById('risk-cooldown');
    if (risk.cooldown_active) cooldownEl.style.color = 'var(--red)';
}

function renderBotStatus(status) {
    const badge = document.getElementById('bot-status');
    const mode = status.mode.toUpperCase();
    badge.textContent = `${mode} | Running`;
    badge.className = `status-badge ${status.mode}`;
}

function renderStrategies(strategies) {
    for (const [name, data] of Object.entries(strategies)) {
        const card = document.getElementById(`strategy-${name}`);
        if (!card) continue;
        const statusDiv = card.querySelector('.strategy-status');
        if (data.is_active) {
            card.classList.add('active');
            card.classList.remove('inactive');
            statusDiv.textContent = 'Active';
            if (data.total_pnl !== undefined) {
                statusDiv.textContent += ` | PnL: ${formatPnL(data.total_pnl)}`;
            }
        } else {
            card.classList.add('inactive');
            card.classList.remove('active');
            statusDiv.textContent = 'Inactive';
        }
    }
}

// ── Actions ─────────────────────────────────────────

async function closePosition(positionId) {
    if (!confirm('Close this position at market price?')) return;
    try {
        const resp = await fetch(`/api/positions/${positionId}/close`, { method: 'POST' });
        if (resp.ok) {
            refreshAll();
        } else {
            alert('Failed to close position');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function toggleStrategy(name) {
    const card = document.getElementById(`strategy-${name}`);
    const isActive = card.classList.contains('active');
    const action = isActive ? 'stop' : 'start';

    try {
        const resp = await fetch(`/api/strategies/${name}/${action}`, { method: 'POST' });
        if (resp.ok) {
            refreshAll();
        }
    } catch (e) {
        console.error('Toggle strategy error:', e);
    }
}

async function submitManualTrade(event) {
    event.preventDefault();
    const symbol = document.getElementById('trade-symbol').value;
    const side = document.getElementById('trade-side').value;
    const amountUsdt = parseFloat(document.getElementById('trade-amount').value);
    const resultDiv = document.getElementById('trade-result');

    try {
        // Get current price to calculate amount
        const summary = await fetchJSON('/api/portfolio/summary');
        const resp = await fetch('/api/trades/manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, side, amount: amountUsdt }),
        });

        const data = await resp.json();
        if (resp.ok && !data.error) {
            resultDiv.style.background = 'rgba(63, 185, 80, 0.15)';
            resultDiv.textContent = `Order placed: ${side.toUpperCase()} ${symbol}`;
            refreshAll();
        } else {
            resultDiv.style.background = 'rgba(248, 81, 73, 0.15)';
            resultDiv.textContent = `Error: ${data.error || data.detail || 'Order failed'}`;
        }
    } catch (e) {
        resultDiv.style.background = 'rgba(248, 81, 73, 0.15)';
        resultDiv.textContent = `Error: ${e.message}`;
    }
}

// ── Formatters ──────────────────────────────────────

function formatUSD(val) {
    if (val == null) return '--';
    return '$' + parseFloat(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPnL(val) {
    if (val == null) return '--';
    const num = parseFloat(val);
    const prefix = num >= 0 ? '+' : '';
    return prefix + '$' + Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPrice(val) {
    if (val == null) return '--';
    const num = parseFloat(val);
    if (num >= 1000) return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (num >= 1) return '$' + num.toFixed(4);
    return '$' + num.toFixed(8);
}

function formatTime(isoStr) {
    if (!isoStr) return '--';
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function setMetric(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
    // Apply color classes for PnL values
    if (typeof value === 'string' && value.startsWith('+$')) {
        el.className = 'metric-value positive';
    } else if (typeof value === 'string' && value.startsWith('-$')) {
        el.className = 'metric-value negative';
    }
}
