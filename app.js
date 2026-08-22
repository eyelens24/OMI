const toast = document.querySelector('#toast');
const results = document.querySelector('#results');
const branches = document.querySelector('#branches');
let activeRecords = [];
let activeEdges = [];
let activePaths = [];
let activeTopicLevels = {};
let activeSecondary = [];
let selectedEdge = null;
let pendingMarketFile = null;
let activeRoot = null;
let timelineRecords = [];
let timelineSourceRecords = [];
let activeTimelineSymbol = '__all__';
let lossDiagnosisRequest = 0;
let replayRequest = 0;

function notify(message) {
  toast.textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 3000);
}

function formatMoney(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

function numericValue(record, field) {
  const value = Number(record?.[field]);
  return Number.isFinite(value) ? value : null;
}

function renderSnapshotIdentity(snapshotId, semantics = '') {
  const identity = document.querySelector('#snapshotIdentity');
  if (identity) identity.textContent = snapshotId || '—';
  const detail = document.querySelector('#commandCenterDetail');
  if (detail) detail.textContent = `${semantics || 'Evidence is bound to the displayed immutable snapshot.'} local-only/read-only.`;
}

function renderCounterfactualCards(cards = []) {
  const panel = document.querySelector('#counterfactualCards');
  if (!panel) return;
  panel.innerHTML = cards.length ? cards.map((card) => `<article class="basket-card"><span>BOUNDED SENSITIVITY</span><strong>${escapeHtml(card.title)}</strong><small>${escapeHtml(formatMoney(card.counterfactual_pnl))} counterfactual P&amp;L · ${escapeHtml(card.limitation)}</small></article>`).join('') : '<small>Counterfactual cards require explicit additive attribution components. They are not causal claims.</small>';
}

async function refreshIncidentCommand(records, label) {
  const response = await fetch('/api/incident-command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records, label, source: 'ui' }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not refresh command center.');
  renderSnapshotIdentity(result.incident.snapshot_id, result.commander_note);
}

function formatTimestamp(value) {
  return String(value || '—').replace('T', ' ').slice(0, 16);
}

function materialLossIndexes(records) {
  const losses = records.map((record, index) => ({ index, pnl: numericValue(record, 'pnl') }))
    .filter((item) => item.pnl !== null && item.pnl < 0)
    .sort((a, b) => a.pnl - b.pnl);
  const chosen = [];
  const minimumDistance = Math.max(8, Math.floor(records.length / 12));
  for (const item of losses) {
    if (chosen.every((index) => Math.abs(index - item.index) >= minimumDistance)) chosen.push(item.index);
    if (chosen.length === 5) break;
  }
  return chosen.sort((a, b) => a - b);
}

function decisionEvidence(record) {
  const fields = [
    ['action', 'Recorded action'], ['side', 'Recorded side'], ['target_position', 'Target position'],
    ['target_weight', 'Target weight'], ['position', 'Recorded position'], ['alpha_score', 'Alpha score'],
    ['expected_return', 'Expected return'], ['rank', 'Alpha rank'], ['rank_ic', 'Rank IC'],
    ['information_coefficient', 'Information coefficient'], ['decision_reason', 'Recorded rationale'],
  ];
  return fields.filter(([field]) => record[field] !== undefined && record[field] !== null && String(record[field]).trim() !== '')
    .map(([field, label]) => [label, record[field]]);
}

function renderTimelineDetail(index) {
  const record = timelineRecords[index];
  const detail = document.querySelector('#timelineDetail');
  if (!record) return;
  const evidence = decisionEvidence(record);
  const pnl = numericValue(record, 'pnl');
  const symbol = record.symbol ? ` · ${escapeHtml(record.symbol)}` : '';
  const evidenceHtml = evidence.length
    ? `<dl>${evidence.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>`
    : `<p class="timeline-missing">No explicit decision fields were recorded for this loss. The app can show what happened to P&amp;L, but cannot honestly state why the bot chose the position. Record <code>action</code> or <code>target_position</code>, plus <code>alpha_score</code>, <code>expected_return</code>, or <code>decision_reason</code>.</p>`;
  detail.innerHTML = `<div><p class="eyebrow">SELECTED LOSS EVENT</p><h3>${formatTimestamp(record.timestamp)}${symbol}</h3><strong>${pnl === null ? 'P&L unavailable' : `${formatMoney(pnl)} P&L`}</strong></div><div><p class="eyebrow">DECISION-TIME EVIDENCE</p>${evidenceHtml}</div>`;
  document.querySelectorAll('[data-loss-index]').forEach((marker) => marker.classList.toggle('selected', Number(marker.dataset.lossIndex) === index));
  diagnoseSelectedLoss(index);
}

async function diagnoseSelectedLoss(index) {
  // A loss is explained only from information that existed by that timestamp.
  // The 160-mark lookback is deliberately local: it avoids letting a later
  // deterioration rewrite the explanation for an earlier decision.
  const lookback = 160;
  const windowStart = Math.max(0, index - lookback + 1);
  const records = timelineRecords.slice(windowStart, index + 1);
  const status = document.querySelector('#timelineStatus');
  if (records.length < 50) {
    status.textContent = 'Short evidence window: showing a candidate investigation route';
    const observedPnl = numericValue(record, 'pnl');
    // A short window may not support statistical ranking, but it must still show
    // an honest route rather than inheriting a different event or going blank.
    window.activeExplanationBlocks = [
      { stage: 'Observed outcome', title: 'Recorded loss event', copy: `${observedPnl === null ? 'P&L was recorded' : `${formatMoney(observedPnl)} P&L was recorded`} at this event.`, detail: 'Observed accounting outcome.', kind: 'outcome', support: 'supported' },
      { stage: 'Candidate route', title: 'Data, decision, translation, execution, or market layer', copy: 'The short retained history cannot rank one layer reliably.', detail: 'Evidence required: decision, target, fill, position, and point-in-time market records.', kind: 'candidate', support: 'candidate' },
      { stage: 'Investigation outcome', title: 'Collect the missing chain before naming a cause', copy: 'OMI has produced a bounded candidate route, not a causal conclusion.', detail: 'No causal claim is made until the links reconcile.', kind: 'outcome', support: 'gap' },
    ];
    activeRoot = null;
    activePaths = [];
    activeSecondary = [];
    renderBranches();
    document.querySelector('#rootHypothesis').hidden = true;
    document.querySelector('#snapshotIdentity').textContent = 'short-window';
    return;
  }
  const request = ++lossDiagnosisRequest;
  // A selected loss supersedes a pending generic replay response.
  replayRequest += 1;
  status.textContent = 'Diagnosing selected loss…';
  try {
    const asOf = timelineRecords[index].timestamp;
    const response = await fetch('/api/investigation/replay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records, as_of: asOf, source: 'selected-loss-ui' }) });
    const replay = await response.json();
    if (!response.ok) throw new Error(replay.error || 'Could not diagnose this loss.');
    if (!replay.evidence_ready) throw new Error(replay.reason || 'Selected-loss evidence is not ready.');
    if (request !== lossDiagnosisRequest) return;
    renderSnapshotIdentity(replay.snapshot_id, replay.graph?.evidence_semantics);
    renderExplanation(replay.analysis, `Selected loss at ${formatTimestamp(asOf)}`, true);
    renderLedger(replay.ledger);
    renderAiForensics(replay.ai_forensics);
    // Analysis and graph carry one immutable point-in-time identity.
    renderCausalFlow(document.querySelector('#investigationGraph'), replay.graph.nodes, replay.graph.edges);
    status.textContent = `${replay.records} prior-and-current marks analysed · snapshot ${replay.snapshot_id}`;
  } catch (error) {
    if (request === lossDiagnosisRequest) {
      status.textContent = 'Selected-loss diagnosis unavailable';
      notify(error.message);
    }
  }
}

function renderIncidentTimeline(records) {
  // Click-local diagnosis must use chronological evidence; upload order can be arbitrary.
  timelineSourceRecords = [...(records || [])].sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  activeTimelineSymbol = '__all__';
  renderTimelineSeries();
}

function renderTimelineSeries() {
  timelineRecords = activeTimelineSymbol === '__all__'
    ? timelineSourceRecords
    : timelineSourceRecords.filter((record) => String(record.symbol || '').toUpperCase() === activeTimelineSymbol);
  const panel = document.querySelector('#incidentTimeline');
  const chart = document.querySelector('#timelineChart');
  const symbolPicker = document.querySelector('#timelineSymbols');
  const symbols = [...new Set(timelineSourceRecords.map((record) => String(record.symbol || '').toUpperCase()).filter(Boolean))];
  if (timelineRecords.length < 2 || !timelineRecords.some((record) => numericValue(record, 'pnl') !== null)) {
    panel.hidden = true;
    return;
  }
  symbolPicker.hidden = !symbols.length;
  symbolPicker.innerHTML = symbols.length
    ? [`<button class="timeline-symbol ${activeTimelineSymbol === '__all__' ? 'active' : ''}" data-symbol="__all__">All stocks</button>`, ...symbols.map((symbol) => `<button class="timeline-symbol ${activeTimelineSymbol === symbol ? 'active' : ''}" data-symbol="${escapeHtml(symbol)}">${escapeHtml(symbol)}</button>`)].join('')
    : '';
  symbolPicker.querySelectorAll('[data-symbol]').forEach((button) => button.addEventListener('click', () => {
    activeTimelineSymbol = button.dataset.symbol;
    renderTimelineSeries();
  }));
  const equityValues = timelineRecords.map((record, index) => {
    // `equity` in a combined file is often strategy-level. A ticker view must
    // rebuild its own cumulative P&L instead of accidentally plotting that
    // aggregate field for every stock.
    if (activeTimelineSymbol === '__all__') {
      const equity = numericValue(record, 'equity');
      if (equity !== null) return equity;
    }
    return timelineRecords.slice(0, index + 1).reduce((total, row) => total + (numericValue(row, 'pnl') || 0), 0);
  });
  const min = Math.min(...equityValues);
  const max = Math.max(...equityValues);
  const range = max - min || 1;
  const width = 960, height = 260, padX = 38, padY = 26;
  const xFor = (index) => padX + (index / Math.max(1, timelineRecords.length - 1)) * (width - padX * 2);
  const yFor = (value) => height - padY - ((value - min) / range) * (height - padY * 2);
  const line = equityValues.map((value, index) => `${index ? 'L' : 'M'}${xFor(index).toFixed(1)},${yFor(value).toFixed(1)}`).join(' ');
  const lossIndexes = materialLossIndexes(timelineRecords);
  const markers = lossIndexes.map((index) => `<circle class="loss-marker" data-loss-index="${index}" cx="${xFor(index).toFixed(1)}" cy="${yFor(equityValues[index]).toFixed(1)}" r="6" tabindex="0" role="button" aria-label="Inspect loss at ${escapeHtml(formatTimestamp(timelineRecords[index].timestamp))}" />`).join('');
  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Equity or cumulative P and L through the incident"><line class="timeline-zero" x1="${padX}" x2="${width - padX}" y1="${yFor(0).toFixed(1)}" y2="${yFor(0).toFixed(1)}" /><path class="timeline-line" d="${line}" />${markers}<text x="${padX}" y="${height - 5}">${escapeHtml(formatTimestamp(timelineRecords[0].timestamp))}</text><text text-anchor="end" x="${width - padX}" y="${height - 5}">${escapeHtml(formatTimestamp(timelineRecords[timelineRecords.length - 1].timestamp))}</text></svg>`;
  panel.hidden = false;
  const scope = activeTimelineSymbol === '__all__' ? 'All stocks' : activeTimelineSymbol;
  document.querySelector('#timelineStatus').textContent = `${scope} · ${lossIndexes.length} material loss${lossIndexes.length === 1 ? '' : 'es'} marked`;
  chart.querySelectorAll('[data-loss-index]').forEach((marker) => {
    const select = () => renderTimelineDetail(Number(marker.dataset.lossIndex));
    marker.addEventListener('click', select);
    marker.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
  });
  renderTimelineDetail(lossIndexes[0] ?? timelineRecords.length - 1);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

function setRunning(message) {
  document.querySelector('#engineState').textContent = 'Running';
  document.querySelector('#engineHint').textContent = message;
}

function renderRecorderStatus(status) {
  const state = document.querySelector('#recorderState');
  const meta = document.querySelector('#recorderMeta');
  if (!status?.events) {
    state.textContent = 'No events yet';
    meta.textContent = 'Read-only collector · never routes or modifies trades';
    return;
  }
  state.textContent = `${status.events.toLocaleString()} events recorded`;
  const types = Object.entries(status.by_type || {}).map(([type, count]) => `${count} ${type.replaceAll('_', ' ')}`).join(' · ');
  const latest = status.latest_event_timestamp?.slice(0, 16).replace('T', ' ');
  meta.textContent = `${status.strategy_id || 'All strategies'} · latest evidence ${latest || '—'} · ${types}`;
}

async function refreshRecorderStatus(strategyId = '') {
  const response = await fetch(`/api/flight-recorder/status${strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ''}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not load recorder status.');
  renderRecorderStatus(result.status);
}

function alignmentGap() {
  // Fundamental snapshots are commonly daily rather than intraday. The server
  // still uses an as-of join and never matches a future observation.
  return 1440;
}

function openEvidence(edge) {
  selectedEdge = edge;
  const drawer = document.querySelector('#drawer');
  const stats = [
    ['Pearson correlation', edge.pearson], ['Spearman correlation', edge.spearman],
    ['Partial correlation', edge.partial], ['Best lag', edge.best_lag],
    ['Lag correlation', edge.lag_correlation], ['p-value', edge.p_value],
    ['FDR-adjusted q', edge.q_value ?? '—'],
    ['Sample size', edge.sample_size], ['Confidence', `${edge.confidence}%`],
  ];
  document.querySelector('#drawerTitle').textContent = `${edge.source} → ${edge.target}`;
  document.querySelector('#drawerCopy').textContent = `What we observed: ${edge.evidence_detail || edge.explanation} ${edge.evidence_kind ? 'The upstream pattern is derived from the uploaded inputs. It describes a pattern and does not prove an external event caused it.' : 'This is a relationship in the data, not proof that the first topic caused the second.'}`;
  document.querySelector('#edgeStats').innerHTML = stats.map(([label, value]) => `<div class="stat"><span>${label}</span><strong>${value}</strong></div>`).join('');
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  document.querySelector('#backdrop').classList.add('show');
}

function closeEvidence() {
  document.querySelector('#drawer').classList.remove('open');
  document.querySelector('#drawer').setAttribute('aria-hidden', 'true');
  document.querySelector('#backdrop').classList.remove('show');
}

function primaryPath() {
  const outcome = 'Strategy loss';
  const root = activeRoot || activePaths[0]?.source;
  if (!root) return [];
  const visit = (topic, seen = new Set()) => {
    if (topic === outcome) return { score: 0, edges: [] };
    const choices = activePaths.filter((edge) => edge.source === topic && !seen.has(edge.target) && (activeTopicLevels[edge.target] ?? 0) > (activeTopicLevels[topic] ?? 0));
    const candidates = choices.map((edge) => {
      const rest = visit(edge.target, new Set([...seen, topic]));
      return rest ? { score: (edge.score || edge.confidence) + rest.score, edges: [edge, ...rest.edges] } : null;
    }).filter(Boolean);
    return candidates.sort((a, b) => b.score - a.score)[0] || null;
  };
  return visit(root)?.edges || [];
}

function renderBranches() {
  const blocks = window.activeExplanationBlocks || [];
  const secondaryTopics = [...new Set(activeSecondary.map((edge) => edge.source))];
  if (!blocks.length) {
    branches.innerHTML = `<section class="plain-diagnosis"><div class="plain-head"><span>NO COMPLETE FLOW YET</span><h3>The app cannot draw a full explanation from the available fields.</h3><p>Add aligned fundamental inputs, a stock <code>return</code>, and strategy <code>pnl</code>. Add alpha-score/rank or target-versus-actual-weight fields to diagnose the research and portfolio layers.</p></div></section>`;
    return;
  }
  const stages = blocks.map((block, index) => {
    const support = block.support === 'candidate' ? 'CANDIDATE HYPOTHESIS' : block.support === 'gap' ? 'EVIDENCE GAP' : escapeHtml(block.stage);
    const card = `<article class="flow-node block-${escapeHtml(block.kind || 'effect')}"><span>${support}</span><strong>${escapeHtml(block.title)}</strong><small>${escapeHtml(block.copy)}</small><em>${escapeHtml(block.detail)}</em></article>`;
    if (!index) return card;
    const link = block.link || (index === 1 ? blocks[0].link : null);
    if (link?.kind === 'evidence') {
      return `<button class="flow-arrow" data-block-edge="${index}" aria-label="Inspect evidence for ${escapeHtml(link.edge.source)} to ${escapeHtml(link.edge.target)}"><span>DATA SHOWS</span><b>→</b><small>${link.edge.confidence}% support</small></button>${card}`;
    }
    return `<div class="flow-arrow static-arrow" title="${escapeHtml(link?.detail || 'This is an interpretation of the preceding measured observation.')}"><span>${escapeHtml(link?.label || 'THEN')}</span><b>→</b><small>interpretation</small></div>${card}`;
  }).join('');
  branches.innerHTML = `<section class="flow-diagnosis"><div class="flow-head"><span>EXPLANATION BUILT FROM YOUR DATA</span><h3>Start with the first measured break.</h3><p>Blocks appear only when the incident has evidence for them. Purple arrows are measured relationships; grey arrows explain what a measured change means.</p></div><div class="flow-scroll"><div class="flow-row">${stages}</div></div><div class="other-summary"><strong>Other leads to rule out:</strong> ${secondaryTopics.length ? `${secondaryTopics.join(', ')} also moved with the loss, but are not on the main explanation because a supported route was not retained.` : 'No separate direct-loss leads were retained.'}</div></section>`;
  branches.querySelectorAll('[data-block-edge]').forEach((element) => element.addEventListener('click', () => openEvidence(blocks[Number(element.dataset.blockEdge)].link.edge)));
}

function renderFaultAudit(domains) {
  const container = document.querySelector('#faultDomains');
  container.innerHTML = (domains || []).map((domain) => {
    const status = domain.status.replace('_', ' ');
    const findings = domain.findings.length
      ? `<ul class="fault-findings">${domain.findings.map((finding) => `<li><b>${escapeHtml(finding.label)} · ${escapeHtml(finding.status)}</b>${escapeHtml(finding.detail)}</li>`).join('')}</ul>`
      : '';
    const missing = domain.missing_fields.length ? `<div class="fault-missing">To deepen this check: ${escapeHtml(domain.missing_fields.slice(0, 5).join(', '))}</div>` : '';
    return `<details class="fault-domain" ${domain.status === 'alert' || domain.status === 'watch' ? 'open' : ''}><summary><span>FAULT DOMAIN <b class="fault-status ${escapeHtml(domain.status)}">${escapeHtml(status)}</b></span><strong>${escapeHtml(domain.title)}</strong></summary><p>${escapeHtml(domain.summary)}</p>${findings}${missing}</details>`;
  }).join('');
}

function renderImplementationAudit(domains) {
  const section = document.querySelector('#implementationAudit');
  const container = document.querySelector('#implementationDomains');
  if (!section || !container) return;
  const assessable = (domains || []).filter((domain) => domain.status !== 'not_assessable');
  if (!assessable.length) {
    section.hidden = true;
    return;
  }
  container.innerHTML = assessable.map((domain) => {
    const status = domain.status.replace('_', ' ');
    const findings = domain.findings.length
      ? `<ul class="fault-findings">${domain.findings.map((finding) => `<li><b>${escapeHtml(finding.label)} · ${escapeHtml(finding.status)}</b>${escapeHtml(finding.detail)}</li>`).join('')}</ul>`
      : '';
    return `<details class="fault-domain" ${domain.status === 'alert' || domain.status === 'watch' ? 'open' : ''}><summary><span>CONTEXT <b class="fault-status ${escapeHtml(domain.status)}">${escapeHtml(status)}</b></span><strong>${escapeHtml(domain.title)}</strong></summary><p>${escapeHtml(domain.summary)}</p>${findings}</details>`;
  }).join('');
  section.hidden = false;
}

function renderAlphaAudit(domains) {
  const section = document.querySelector('#alphaAudit');
  const container = document.querySelector('#alphaDomains');
  const assessable = (domains || []).filter((domain) => domain.status !== 'not_assessable');
  if (!assessable.length) {
    section.hidden = true;
    return;
  }
  container.innerHTML = assessable.map((domain) => {
    const status = domain.status.replace('_', ' ');
    const findings = domain.findings.length
      ? `<ul class="fault-findings">${domain.findings.map((finding) => `<li><b>${escapeHtml(finding.label)} · ${escapeHtml(finding.status)}</b>${escapeHtml(finding.detail)}</li>`).join('')}</ul>`
      : '';
    return `<details class="fault-domain" ${domain.status === 'alert' || domain.status === 'watch' ? 'open' : ''}><summary><span>ALPHA LAYER <b class="fault-status ${escapeHtml(domain.status)}">${escapeHtml(status)}</b></span><strong>${escapeHtml(domain.title)}</strong></summary><p>${escapeHtml(domain.summary)}</p>${findings}</details>`;
  }).join('');
  section.hidden = false;
}

function renderPatternDiscovery(discovery) {
  const section = document.querySelector('#patternAudit');
  const container = document.querySelector('#patternDiscovery');
  const detectors = discovery?.detectors || [];
  const unclassified = discovery?.unclassified_patterns || [];
  if (!detectors.length && !unclassified.length) {
    section.hidden = true;
    return;
  }
  const clusters = detectors.map((detector) => `<details class="fault-domain"><summary><span>PATTERN DETECTOR <b class="fault-status watch">${escapeHtml(detector.state)}</b></span><strong>${escapeHtml(detector.title)}</strong></summary><p>${escapeHtml(detector.detail)}</p><div class="fault-missing">Features: ${escapeHtml(detector.features.join(', '))} · ${escapeHtml(detector.algorithm)} · ${escapeHtml(detector.confidence)}% separation confidence.</div></details>`).join('');
  const unknown = unclassified.length ? `<details class="fault-domain" open><summary><span>REQUIRES REVIEW <b class="fault-status watch">unclassified</b></span><strong>Shifting fields outside reviewed routes</strong></summary><p>These changes were detected but are deliberately not named as causes. A reviewer can label them or leave them unknown.</p><ul class="fault-findings">${unclassified.map((item) => `<li><b>${escapeHtml(item.label)} · ${escapeHtml(item.status)}</b>${escapeHtml(item.detail)}</li>`).join('')}</ul></details>` : '';
  container.innerHTML = clusters + unknown;
  section.hidden = false;
}

function renderConfirmationPlan(steps) {
  const panel = document.querySelector('#confirmationPlan');
  const list = document.querySelector('#confirmationSteps');
  if (!steps?.length) {
    panel.hidden = true;
    return;
  }
  list.innerHTML = steps.map((step) => `<li>${escapeHtml(step)}</li>`).join('');
  panel.hidden = false;
}

function renderBasket(basket) {
  const panel = document.querySelector('#basketPanel');
  if (!panel) return;
  if (!basket?.available) {
    panel.hidden = true;
    return;
  }
  const list = (items, formatter, empty) => items.length
    ? `<ul class="basket-list">${items.map(formatter).join('')}</ul>`
    : `<small>${empty}</small>`;
  const exposures = list(basket.top_exposures || [], (item) => `<li><b>${escapeHtml(item.symbol)}</b><span>${formatMoney(item.notional)} · ${Math.round((item.share || 0) * 100)}%</span></li>`, 'No notional or price data was supplied.');
  const losses = list(basket.top_losses || [], (item) => `<li><b>${escapeHtml(item.symbol)}</b><span>${formatMoney(item.pnl)}</span></li>`, 'No per-symbol P&L was supplied.');
  document.querySelector('#basketSummary').textContent = basket.summary;
  const basis = basket.exposure_basis === 'latest position snapshot' ? 'Latest basket value' : 'Total traded notional';
  document.querySelector('#basketGrid').innerHTML = `<article class="basket-card"><span>INSTRUMENTS</span><strong>${basket.symbols} symbols</strong><small>${basket.rows} symbol rows · ${basket.buy_count} buys · ${basket.sell_count} sells</small></article><article class="basket-card"><span>${escapeHtml(basket.exposure_basis || 'trading activity').toUpperCase()} CONCENTRATION</span><strong>${basket.largest_activity_share === null ? '—' : `${Math.round(basket.largest_activity_share * 100)}% in largest symbol`}</strong><small>${basis}: ${formatMoney(basket.activity_notional)}</small>${exposures}</article><article class="basket-card"><span>LOWEST P&amp;L CONTRIBUTORS</span><strong>Names to investigate</strong><small>Symbols with the lowest summed uploaded P&amp;L.</small>${losses}</article>`;
  panel.hidden = false;
}

function renderLedger(ledger) {
  const path = document.querySelector('#ledgerPath');
  const receipt = document.querySelector('#ledgerReceipt');
  if (!path || !ledger?.steps) return;
  path.innerHTML = ledger.steps.map((step, index) => `<button class="ledger-step status-${escapeHtml(step.status)}" data-ledger-index="${index}"><span>${escapeHtml(step.status)}</span><strong>${escapeHtml(step.kind)}</strong><small>${escapeHtml(step.event_id || step.detail)}</small></button>`).join('<i class="ledger-arrow">→</i>');
  path.querySelectorAll('[data-ledger-index]').forEach((button) => button.addEventListener('click', () => {
    const step = ledger.steps[Number(button.dataset.ledgerIndex)];
    receipt.hidden = false;
    document.querySelector('#ledgerReceiptTitle').textContent = `${step.kind}: ${step.status}`;
    document.querySelector('#ledgerReceiptDetail').textContent = `${step.detail} Event: ${step.event_id || 'not supplied'}.`;
  }));
}

function renderAiForensics(receipts) {
  const panel = document.querySelector('#aiForensics');
  if (!panel) return;
  if (!receipts?.length) { panel.hidden = true; return; }
  panel.hidden = false;
  panel.innerHTML = receipts.map((item) => `<article class="ledger-receipt"><p class="eyebrow">AI DECISION PROVENANCE · ${escapeHtml(item.status)}</p><h3>${escapeHtml(item.decision_id || 'unidentified decision')}</h3><p>${escapeHtml((item.contradictions || item.missing || ['Provenance supported.']).join(' · '))}</p></article>`).join('');
}

function renderExplanation(result, label, selectedLoss = false) {
  activeEdges = result.edges;
  activePaths = result.explanation_paths || result.edges;
  window.activeExplanationBlocks = result.explanation_blocks || [];
  activeTopicLevels = result.topic_levels || {};
  activeSecondary = result.secondary_leads || [];
  activeRoot = result.root_hypothesis?.label || null;
  const summary = result.summary;
  document.querySelector('#diagnosisTitle').textContent = selectedLoss
    ? 'What may explain this selected loss?'
    : `What may explain this ${summary.pnl < 0 ? 'loss' : 'outcome'}?`;
  document.querySelector('#diagnosisSubtitle').textContent = selectedLoss
    ? `${label}. This uses only the 160 observations ending at this loss—never later data.`
    : `${label}. Start with the candidate below, then follow its evidence path.`;
  const root = result.root_hypothesis;
  const rootCauses = result.root_causes || [];
  const rootCard = document.querySelector('#rootHypothesis');
  const rootCandidates = document.querySelector('#rootCandidates');
  rootCard.hidden = !root?.confidence && !rootCauses.length;
  if (rootCauses.length) {
    const primary = rootCauses[0];
    document.querySelector('#rootKicker').textContent = 'LEADING ROOT-CAUSE CANDIDATE';
    document.querySelector('#rootLabel').textContent = primary.title;
    document.querySelector('#rootDetail').textContent = `${primary.detail} This is the leading candidate to test, not a confirmed cause.`;
    rootCandidates.innerHTML = rootCauses.slice(1).length
      ? `<p>Other root-cause candidates to rule out:</p><ul>${rootCauses.slice(1).map((candidate) => `<li><b>${escapeHtml(candidate.title)}</b><span>Detected around ${escapeHtml(candidate.onset.slice(0, 16).replace('T', ' '))} · r = ${escapeHtml(candidate.association)}</span></li>`).join('')}</ul>`
      : '';
  } else if (selectedLoss) {
    document.querySelector('#rootKicker').textContent = 'NO NEW ROOT-CAUSE CANDIDATE IN THIS WINDOW';
    document.querySelector('#rootLabel').textContent = 'No new measurable break';
    document.querySelector('#rootDetail').textContent = 'This loss may reflect an issue already under way, or evidence the current data cannot distinguish. It is not enough to name a new root cause for this timestamp.';
    rootCandidates.innerHTML = '';
  } else if (root?.confidence) {
    const story = primaryPath();
    document.querySelector('#rootKicker').textContent = 'UPSTREAM PATTERN, NOT A ROOT CAUSE';
    document.querySelector('#rootLabel').textContent = `Detected ${root.label.toLowerCase()} pattern`;
    document.querySelector('#rootDetail').textContent = `The app found a shared pattern using ${root.features.join(', ').replaceAll('_', ' ')}. The clearest measured story is ${story.length ? story.map((edge, index) => index ? edge.target : edge.source).join(' → ') : 'not yet complete'}. Treat this as a starting point to investigate, not a confirmed root cause.`;
    rootCandidates.innerHTML = '';
  }
  renderFaultAudit(result.fundamental_domains || []);
  renderAlphaAudit(result.alpha_domains || []);
  renderPatternDiscovery(result.pattern_discovery);
  renderBranches();
  renderConfirmationPlan(result.confirmation_plan || []);
}

function renderCausalFlow(container, nodes, edges) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const ordered = [];
  const add = (node) => { if (node && !ordered.includes(node)) ordered.push(node); };
  edges.forEach((edge) => { add(byId.get(edge.source)); add(byId.get(edge.target)); });
  nodes.forEach(add);
  container.innerHTML = `<div class="causal-flow">${ordered.map((node, index) => `${index ? '<div class="causal-arrow" aria-hidden="true">→</div>' : ''}<article class="causal-step ${escapeHtml(node.evidence_type)}"><span>${escapeHtml(node.evidence_type)}</span><strong>${escapeHtml(node.label)}</strong></article>`).join('')}</div>`;
}

async function renderInvestigationGraph(records, analysis) {
  const panel = document.querySelector('#investigationGraphPanel');
  const graph = document.querySelector('#investigationGraph');
  const scrubber = document.querySelector('#replayScrubber');
  const moment = document.querySelector('#replayMoment');
  try {
    const response = await fetch('/api/investigation/graph', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records, analysis }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not build investigation graph.');
    const render = async (index) => {
      const visibleTime = result.graph.timeline[index]?.timestamp;
      moment.textContent = visibleTime ? formatTimestamp(visibleTime) : '—';
      const request = ++replayRequest;
      const replayResponse = await fetch('/api/investigation/replay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records, as_of: visibleTime }) });
      const replay = await replayResponse.json();
      if (request !== replayRequest) return;
      if (!replay.evidence_ready) { graph.innerHTML = `<p class="timeline-missing">${escapeHtml(replay.reason)}</p>`; return; }
      renderCausalFlow(graph, replay.graph.nodes, replay.graph.edges);
      // The card flow is the primary evidence surface; rebuild it from this exact snapshot.
      renderExplanation(replay.analysis, `Replay at ${formatTimestamp(visibleTime)}`, true);
      renderLedger(replay.ledger);
    renderAiForensics(replay.ai_forensics);
      renderSnapshotIdentity(replay.snapshot_id, replay.graph.evidence_semantics);
      const summary = replay.analysis.summary;
      document.querySelector('#pnlMetric').textContent = formatMoney(summary.pnl);
      document.querySelector('#pnlDetail').textContent = `As of ${formatTimestamp(visibleTime)} · ${replay.records} observations`;
      document.querySelector('#changeMetric').textContent = summary.change_label || 'No break yet';
      document.querySelector('#changeDetail').textContent = formatTimestamp(summary.change_point.timestamp);
    };
    scrubber.max = Math.max(0, result.graph.timeline.length - 1);
    scrubber.value = scrubber.max;
    scrubber.oninput = () => { render(Number(scrubber.value)).catch((error) => console.warn(error)); };
    render(Number(scrubber.value)).catch((error) => console.warn(error));
    // Keep replay controls beside the card flow; the old standalone graph is retired.
    let controls = document.querySelector('#replayControls');
    if (!controls) {
      controls = document.createElement('div');
      controls.id = 'replayControls';
      controls.className = 'section-actions';
      document.querySelector('.diagnosis .section-head').append(controls);
    }
    controls.append(moment, scrubber);
    panel.hidden = true;
  } catch (error) { panel.hidden = true; console.warn(error); }
}

function renderDiagnosis(result, records, label) {
  results.hidden = false;
  activeRecords = records;
  const summary = result.summary;
  document.querySelector('#pnlMetric').textContent = formatMoney(summary.pnl);
  document.querySelector('#pnlDetail').textContent = summary.expected_pnl === null
    ? `P&L anomaly z-score ${summary.pnl_zscore}`
    : `Expected ${formatMoney(summary.expected_pnl)} · shortfall ${formatMoney(summary.implementation_shortfall)}`;
  document.querySelector('#recordsMetric').textContent = result.records.toLocaleString();
  document.querySelector('#changeMetric').textContent = result.summary.change_label || 'Detected';
  document.querySelector('#changeDetail').textContent = summary.change_point.timestamp.slice(0, 16).replace('T', ' ');
  renderIncidentTimeline(records);
  renderExplanation(result, label);
  renderCounterfactualCards();
  refreshIncidentCommand(records, label).catch((error) => console.warn(error));
  renderInvestigationGraph(records, result);
  document.querySelector('#engineState').textContent = 'Diagnosis complete';
  document.querySelector('#engineHint').textContent = `${result.records} P&L marks checked · select a marked loss for its local diagnosis`;
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function diagnose(records, label) {
  setRunning('Checking for unusual changes and possible links to the strategy outcome…');
  const response = await fetch('/api/analyse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Analysis failed.');
  renderDiagnosis(result, records, label);
}

function parseCsv(text) {
  const [header, ...lines] = text.trim().split(/\r?\n/);
  const fields = header.split(',').map((value) => value.trim());
  return lines.filter(Boolean).map((line) => Object.fromEntries(fields.map((field, index) => [field, line.split(',')[index]?.trim()])));
}

document.querySelector('#loadFlightDemo').addEventListener('click', async () => {
  try {
    setRunning('Loading the built-in test CSV and rebuilding its decision-time evidence…');
    const response = await fetch('/api/flight-recorder/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not run the built-in test CSV.');
    renderRecorderStatus(result.status);
    renderDiagnosis(result.analysis, result.records, 'Built-in test CSV diagnosed through the local flight recorder');
    document.querySelector('#engineHint').textContent = `Built-in fundamental_failure.csv analysed · ${result.status.events.toLocaleString()} local evidence events · no upload or broker connection used`;
  } catch (error) { document.querySelector('#engineState').textContent = 'Run failed'; notify(error.message); }
});

document.querySelector('#loadEvidenceDemo').addEventListener('click', async () => {
  try {
    setRunning('Importing the local AI rationale contradiction bundle…');
    const bundleResponse = await fetch('/examples/ai-rationale-contradiction.json');
    const bundle = await bundleResponse.json();
    const response = await fetch('/api/evidence-bundle/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bundle) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not validate the AI demo bundle.');
    activeRecords = result.events;
    document.querySelector('#results').hidden = false;
    document.querySelector('#snapshotIdentity').textContent = 'demo-ai-contradiction';
    renderLedger(result.ledger);
    renderAiForensics(result.ai_forensics);
    document.querySelector('#engineState').textContent = 'Demo ready';
    document.querySelector('#engineHint').textContent = 'Local AI decision evidence imported · lifecycle reconciles · rationale contradiction detected.';
  } catch (error) { document.querySelector('#engineState').textContent = 'Import failed'; notify(error.message); }
});

document.querySelector('#refreshRecorder').addEventListener('click', async () => {
  try { await refreshRecorderStatus(); } catch (error) { notify(error.message); }
});

refreshRecorderStatus().catch(() => {});

document.querySelector('#exportReceipt').addEventListener('click', async () => {
  if (!activeRecords.length) return notify('Analyse local evidence before exporting a receipt.');
  try {
    const asOf = activeRecords[activeRecords.length - 1].timestamp;
    const response = await fetch('/api/reproducibility-receipt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records: activeRecords, as_of: asOf, source: 'ui-export' }) });
    const receipt = await response.json();
    if (!response.ok) throw new Error(receipt.error || 'Could not export receipt.');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], { type: 'application/json' }));
    link.download = `omi-receipt-${receipt.snapshot_id}.json`; link.click(); URL.revokeObjectURL(link.href);
    renderSnapshotIdentity(receipt.snapshot_id, 'Reproducibility receipt exported.');
  } catch (error) { notify(error.message); }
});

document.querySelector('#uploadData').addEventListener('click', () => document.querySelector('#csvInput').click());
document.querySelector('#uploadIncidentBundle').addEventListener('click', () => document.querySelector('#incidentBundleInput').click());
document.querySelector('#incidentBundleInput').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    setRunning('Validating point-in-time evidence and data lineage…');
    const response = await fetch('/api/incident-bundle/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: await file.text() });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Incident Bundle validation failed.');
    const receipt = result.receipt;
    const blocked = Object.entries(receipt.assessment_blocked_for).filter(([, value]) => value).map(([name]) => name.replaceAll('_', ' '));
    document.querySelector('#engineState').textContent = receipt.assessment_blocked ? 'Evidence blocked' : 'Evidence checked';
    document.querySelector('#engineHint').textContent = `Evidence receipt · ${receipt.counts.decisions} decisions · ${receipt.counts.pnl} P&L rows${blocked.length ? ` · unavailable: ${blocked.join(', ')}` : ' · attribution-ready'}`;
    notify(`Evidence receipt ready for ${receipt.incident_id}.`);
  } catch (error) { document.querySelector('#engineState').textContent = 'Validation failed'; notify(error.message); }
  finally { event.target.value = ''; }
});
document.querySelector('#uploadBundle').addEventListener('click', () => {
  pendingMarketFile = null;
  document.querySelector('#marketCsvInput').value = '';
  document.querySelector('#strategyCsvInput').value = '';
  document.querySelector('#marketCsvInput').click();
});
document.querySelector('#csvInput').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try { await diagnose(parseCsv(await file.text()), file.name); } catch (error) { document.querySelector('#engineState').textContent = 'Run failed'; notify(error.message); }
});

document.querySelector('#marketCsvInput').addEventListener('change', (event) => {
  pendingMarketFile = event.target.files[0] || null;
  if (!pendingMarketFile) return;
  notify(`Market file selected: ${pendingMarketFile.name}. Now choose the strategy-performance CSV.`);
  document.querySelector('#strategyCsvInput').click();
});

document.querySelector('#strategyCsvInput').addEventListener('change', async (event) => {
  const strategyFile = event.target.files[0];
  if (!pendingMarketFile || !strategyFile) return;
  const marketFile = pendingMarketFile;
  pendingMarketFile = null;
  try {
    setRunning(`Aligning ${marketFile.name} with ${strategyFile.name} without using future market rows…`);
    const response = await fetch('/api/analyse-bundle', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ market_csv: await marketFile.text(), strategy_csv: await strategyFile.text(), max_gap_minutes: alignmentGap(), label: `${marketFile.name} + ${strategyFile.name}` }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not align the uploaded CSVs.');
    renderDiagnosis(result.analysis, result.records, `Aligned ${marketFile.name} with ${strategyFile.name}`);
    const alignment = result.alignment;
    document.querySelector('#engineHint').textContent = `${alignment.matched_rows}/${alignment.strategy_rows} strategy rows matched · average market-data age ${alignment.mean_gap_minutes} min · no future rows used`;
  } catch (error) { document.querySelector('#engineState').textContent = 'Run failed'; notify(error.message); }
  finally {
    document.querySelector('#marketCsvInput').value = '';
    document.querySelector('#strategyCsvInput').value = '';
  }
});

document.querySelector('#closeDrawer').addEventListener('click', closeEvidence);
document.querySelector('#backdrop').addEventListener('click', closeEvidence);
