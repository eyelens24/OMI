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
let selectedTimelineIndex = null;
let timelinePositionInfo = null;
let timelinePositionValues = [];
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
  const raw = record?.[field];
  if (raw === undefined || raw === null || String(raw).trim() === '') return null;
  const value = Number(raw);
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

function detectPositionField(records) {
  const candidates = [
    { field: 'position_quantity', label: 'Shares held', unit: 'shares', kind: 'actual' },
    { field: 'actual_position', label: 'Position held', unit: 'units', kind: 'actual' },
    { field: 'position', label: 'Position held', unit: 'units', kind: 'actual' },
    { field: 'target_quantity', label: 'Target shares', unit: 'shares', kind: 'target' },
    { field: 'target_position', label: 'Target position', unit: 'units', kind: 'target' },
    { field: 'target_weight', label: 'Portfolio weight', unit: 'weight', kind: 'target' },
  ];
  return candidates.find((candidate) => records.some((record) => numericValue(record, candidate.field) !== null)) || null;
}

function positionSeries(records, info) {
  let current = null;
  return records.map((record) => {
    const value = info ? numericValue(record, info.field) : null;
    if (value !== null) current = value;
    return current;
  });
}

function formatPosition(value, info = timelinePositionInfo) {
  if (value === null || value === undefined || !info) return 'Position unavailable';
  if (info.unit === 'weight') return `${(Number(value) * 100).toFixed(1)}% portfolio weight`;
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 })} ${info.unit}`;
}

function renderTimelineDetail(index) {
  const record = timelineRecords[index];
  const detail = document.querySelector('#timelineDetail');
  if (!record) return;
  const pnl = numericValue(record, 'pnl');
  const symbol = record.symbol ? ` · ${escapeHtml(record.symbol)}` : '';
  const held = timelinePositionValues[index];
  const latestAction = [...timelineRecords.slice(0, index + 1)].reverse().find((item) => ['BUY', 'SELL', 'HOLD'].includes(String(item.action || '').toUpperCase()));
  const action = String(latestAction?.action || 'Not recorded').toUpperCase();
  detail.innerHTML = `<div><p class="eyebrow">SELECTED POINT</p><h3>${formatTimestamp(record.timestamp)}${symbol}</h3><strong>${escapeHtml(formatPosition(held))}</strong></div><div><p class="eyebrow">LATEST RECORDED ACTION</p><h3>${escapeHtml(action)}</h3><p class="timeline-missing">${pnl === null ? 'No P&L was recorded at this exact point.' : `${escapeHtml(formatMoney(pnl))} P&amp;L was recorded at this point.`} The receipt below uses only information available by this time.</p></div>`;
  selectedTimelineIndex = index;
  document.querySelectorAll('[data-timeline-index]').forEach((marker) => marker.classList.toggle('selected', Number(marker.dataset.timelineIndex) === index));
  const selection = document.querySelector('#timelineChart .timeline-selection');
  if (selection) {
    const selectedX = 38 + (index / Math.max(1, timelineRecords.length - 1)) * (960 - 76);
    selection.setAttribute('x1', selectedX);
    selection.setAttribute('x2', selectedX);
  }
  diagnoseSelectedLoss(index);
}

async function diagnoseSelectedLoss(index) {
  // A point is explained only from information that existed by that timestamp.
  // The 160-mark lookback is deliberately local: it avoids letting a later
  // deterioration rewrite the explanation for an earlier decision.
  const lookback = 160;
  const windowStart = Math.max(0, index - lookback + 1);
  const records = timelineRecords.slice(windowStart, index + 1);
  const status = document.querySelector('#timelineStatus');
  const record = timelineRecords[index];
  const request = ++lossDiagnosisRequest;
  const receipt = document.querySelector('#aiForensics');
  if (receipt) {
    receipt.hidden = false;
    receipt.innerHTML = `<article class="decision-explainer"><p class="eyebrow">SELECTED POINT AT ${escapeHtml(formatTimestamp(record?.timestamp))}</p><h3>Loading algorithm receipt…</h3><p class="decision-why">Finding the latest retained action and every input available before it.</p></article>`;
  }
  // A selected point supersedes a pending generic replay response.
  replayRequest += 1;
  status.textContent = 'Inspecting selected point…';
  try {
    const asOf = timelineRecords[index].timestamp;
    const response = await fetch('/api/investigation/replay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ records, as_of: asOf, source: 'selected-point-ui' }) });
    const replay = await response.json();
    if (!response.ok) throw new Error(replay.error || 'Could not inspect this point.');
    if (!replay.evidence_ready) throw new Error(replay.reason || 'Selected-point evidence is not ready.');
    if (request !== lossDiagnosisRequest) return;
    renderSnapshotIdentity(replay.snapshot_id, replay.graph?.evidence_semantics || 'Decision receipt uses only records retained by this point.');
    renderLedger(replay.ledger);
    renderAiForensics(replay.ai_forensics, replay.ledger, asOf, replay.detected_decision);
    renderStrategyProfile(replay.strategy_profile);
    if (replay.analysis_ready) {
      renderExplanation(replay.analysis, `Selected point at ${formatTimestamp(asOf)}`, true);
      renderCausalFlow(document.querySelector('#investigationGraph'), replay.graph.nodes, replay.graph.edges);
      status.textContent = `${replay.records} prior-and-current marks analysed · snapshot ${replay.snapshot_id}`;
    } else {
      document.querySelector('#diagnosisTitle').textContent = 'What did the trading algorithm do here?';
      document.querySelector('#diagnosisSubtitle').textContent = `Selected point at ${formatTimestamp(asOf)}. Its action receipt is available; there are not enough points for statistical pattern analysis.`;
      status.textContent = `${replay.records} retained observations · decision receipt shown`;
    }
  } catch (error) {
    if (request === lossDiagnosisRequest) {
      status.textContent = 'Selected-point inspection unavailable';
      notify(error.message);
    }
  }
}

function renderIncidentTimeline(records) {
  // Click-local diagnosis must use chronological evidence; upload order can be arbitrary.
  timelineSourceRecords = [...(records || [])].sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  const firstSymbol = timelineSourceRecords.find((record) => String(record.symbol || '').trim())?.symbol;
  activeTimelineSymbol = firstSymbol ? String(firstSymbol).toUpperCase() : '__all__';
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
  timelinePositionInfo = detectPositionField(timelineRecords);
  timelinePositionValues = positionSeries(timelineRecords, timelinePositionInfo);
  if (timelineRecords.length < 2) { panel.hidden = true; return; }
  symbolPicker.hidden = !symbols.length;
  symbolPicker.innerHTML = symbols.length
    ? symbols.map((symbol) => `<button class="timeline-symbol ${activeTimelineSymbol === symbol ? 'active' : ''}" data-symbol="${escapeHtml(symbol)}">${escapeHtml(symbol)}</button>`).join('')
    : '';
  symbolPicker.querySelectorAll('[data-symbol]').forEach((button) => button.addEventListener('click', () => {
    activeTimelineSymbol = button.dataset.symbol;
    selectedTimelineIndex = null;
    renderTimelineSeries();
  }));
  if (!timelinePositionInfo || !timelinePositionValues.some((value) => value !== null)) {
    chart.innerHTML = `<p class="timeline-empty"><b>Position history was not recorded.</b><span>Add <code>position_quantity</code>, <code>actual_position</code>, <code>target_quantity</code>, <code>target_position</code>, or <code>target_weight</code>. OMI will detect the field automatically.</span></p>`;
    panel.hidden = false;
    document.querySelector('#timelineStatus').textContent = `${activeTimelineSymbol === '__all__' ? 'Portfolio' : activeTimelineSymbol} · position unavailable`;
    document.querySelector('#timelineDetail').innerHTML = '';
    return;
  }
  const width = 960, height = 260, padX = 38, padY = 26;
  const xFor = (index) => padX + (index / Math.max(1, timelineRecords.length - 1)) * (width - padX * 2);
  const knownPositions = timelinePositionValues.filter((value) => value !== null);
  let minimum = Math.min(0, ...knownPositions), maximum = Math.max(0, ...knownPositions);
  const padding = Math.max((maximum - minimum) * 0.12, Math.abs(maximum || minimum) * 0.08, 1);
  minimum -= padding;
  maximum += padding;
  const yFor = (value) => height - padY - ((value - minimum) / (maximum - minimum)) * (height - padY * 2);
  let drawing = false;
  const line = timelinePositionValues.map((value, index) => {
    if (value === null) { drawing = false; return ''; }
    const command = drawing ? 'L' : 'M';
    drawing = true;
    return `${command}${xFor(index).toFixed(1)},${yFor(value).toFixed(1)}`;
  }).join(' ');
  const decisionMarkers = timelineRecords.map((record, index) => {
    const action = String(record.action || '').toUpperCase();
    if (!['BUY', 'SELL', 'HOLD'].includes(action) || timelinePositionValues[index] === null) return '';
    return `<circle class="decision-marker action-${action.toLowerCase()} ${selectedTimelineIndex === index ? 'selected' : ''}" data-timeline-index="${index}" cx="${xFor(index).toFixed(1)}" cy="${yFor(timelinePositionValues[index]).toFixed(1)}" r="5" aria-label="${action} at ${escapeHtml(formatTimestamp(record.timestamp))}" />`;
  }).join('');
  const mid = (minimum + maximum) / 2;
  const axisValue = (value) => timelinePositionInfo.unit === 'weight' ? `${(value * 100).toFixed(1)}%` : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  const initialIndex = selectedTimelineIndex !== null && timelineRecords[selectedTimelineIndex]
    ? selectedTimelineIndex : timelineRecords.length - 1;
  const selectedLine = `<line class="timeline-selection" x1="${xFor(initialIndex)}" x2="${xFor(initialIndex)}" y1="${padY}" y2="${height - padY}" />`;
  chart.innerHTML = `<div class="timeline-legend"><b>${escapeHtml(timelinePositionInfo.label)}</b><span class="action-buy">BUY</span><span class="action-sell">SELL</span><span class="action-hold">HOLD</span><small>Dots are recorded actions. Click anywhere to inspect that point.</small></div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(timelinePositionInfo.label)} over time"><line class="action-guide" x1="${padX}" x2="${width - padX}" y1="${yFor(0).toFixed(1)}" y2="${yFor(0).toFixed(1)}" /><text class="position-axis" x="${padX + 4}" y="${(yFor(maximum) + 11).toFixed(1)}">${escapeHtml(axisValue(maximum))}</text><text class="position-axis" x="${padX + 4}" y="${(yFor(mid) - 5).toFixed(1)}">${escapeHtml(axisValue(mid))}</text><text class="position-axis" x="${padX + 4}" y="${(yFor(minimum) - 5).toFixed(1)}">${escapeHtml(axisValue(minimum))}</text><path class="timeline-line position-line" d="${line}" />${selectedLine}${decisionMarkers}<rect class="timeline-hit-area" x="${padX}" y="0" width="${width - padX * 2}" height="${height - padY}" /><text x="${padX}" y="${height - 5}">${escapeHtml(formatTimestamp(timelineRecords[0].timestamp))}</text><text text-anchor="end" x="${width - padX}" y="${height - 5}">${escapeHtml(formatTimestamp(timelineRecords[timelineRecords.length - 1].timestamp))}</text></svg>`;
  panel.hidden = false;
  const scope = activeTimelineSymbol === '__all__' ? 'All stocks' : activeTimelineSymbol;
  document.querySelector('#timelineStatus').textContent = `${scope} · ${timelinePositionInfo.kind === 'actual' ? 'actual position' : 'target position'} detected from ${timelinePositionInfo.field}`;
  chart.querySelector('svg').addEventListener('click', (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const chartX = ((event.clientX - bounds.left) / bounds.width) * width;
    const ratio = Math.min(1, Math.max(0, (chartX - padX) / (width - padX * 2)));
    renderTimelineDetail(Math.round(ratio * (timelineRecords.length - 1)));
  });
  renderTimelineDetail(initialIndex);
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
  const stepsByKind = Object.fromEntries(ledger.steps.map((step) => [step.kind, step]));
  const action = String(stepsByKind.decision?.action || '').toUpperCase();
  const isSell = action === 'SELL';
  const weightText = (value) => {
    const weight = Number(value);
    return Number.isFinite(weight) ? `${Math.abs(weight * 100).toFixed(1)}%` : 'size retained';
  };
  const amountText = (value) => {
    const amount = Number(value);
    return Number.isFinite(amount) ? formatMoney(amount) : 'P&L retained';
  };
  const cardText = (step) => {
    if (step.kind === 'observation') return { title: 'Inputs captured', detail: 'Decision-time data' };
    if (step.kind === 'decision') return { title: `${String(step.action || 'Decision').toUpperCase()}${step.symbol ? ` ${step.symbol}` : ''}`, detail: 'Model action' };
    if (step.kind === 'target') return { title: `${isSell ? 'Short' : 'Long'} target`, detail: weightText(step.target_weight) };
    if (step.kind === 'fill') return { title: 'Order filled', detail: step.quantity ? `${step.quantity} shares` : 'Execution retained' };
    if (step.kind === 'position') return { title: `${isSell ? 'Short' : 'Long'} position`, detail: step.quantity ? `${step.quantity} shares held` : 'Position retained' };
    if (step.kind === 'pnl') return { title: 'Outcome', detail: amountText(step.pnl) };
    return { title: step.kind, detail: 'Evidence retained' };
  };
  path.innerHTML = ledger.steps.map((step, index) => {
    const text = cardText(step);
    return `<button class="ledger-step status-${escapeHtml(step.status)}" data-ledger-index="${index}"><span>${escapeHtml(step.status)}</span><strong>${escapeHtml(text.title)}</strong><small>${escapeHtml(text.detail)}</small></button>`;
  }).join('<i class="ledger-arrow">→</i>');
  path.querySelectorAll('[data-ledger-index]').forEach((button) => button.addEventListener('click', () => {
    const step = ledger.steps[Number(button.dataset.ledgerIndex)];
    receipt.hidden = false;
    document.querySelector('#ledgerReceiptTitle').textContent = `${step.kind}: ${step.status}`;
    document.querySelector('#ledgerReceiptDetail').textContent = `${step.detail} Event: ${step.event_id || 'not supplied'}.`;
  }));
}

function renderAiForensics(receipts, ledger = {}, asOf = '', importedDecision = null) {
  const panel = document.querySelector('#aiForensics');
  if (!panel) return;
  if (!receipts?.length && !importedDecision) {
    panel.hidden = false;
    panel.innerHTML = `<article class="decision-explainer status-missing"><p class="eyebrow">SELECTED POINT AT ${escapeHtml(formatTimestamp(asOf))}</p><h3>Action not retained</h3><p class="decision-why">A position was recorded, but no prior BUY, SELL, or HOLD action and reason were supplied for this point.</p></article>`;
    return;
  }
  // A selected point needs the latest action available by that point. When a
  // typed receipt exists, enrich it with dynamically detected CSV inputs.
  const typedItem = receipts?.[receipts.length - 1];
  const sameDecision = typedItem && importedDecision && (
    typedItem.decision_id === importedDecision.decision_id || typedItem.timestamp === importedDecision.timestamp
  );
  const item = sameDecision ? {
    ...typedItem,
    signals: { ...(importedDecision.signals || {}), ...(typedItem.signals || {}) },
    known: {
      ...(typedItem.known || {}),
      inputs: { ...(importedDecision.known?.inputs || {}), ...(typedItem.known?.inputs || {}) },
      input_details: { ...(importedDecision.known?.input_details || {}), ...(typedItem.known?.input_details || {}) },
    },
  } : typedItem || importedDecision;
  const action = String(item.action || 'Decision unavailable').toUpperCase();
  const symbol = item.symbol ? ` ${item.symbol}` : '';
  const reason = item.decision_reason || (item.receipt?.reason_codes || []).join(', ') || 'No human-readable decision reason was retained.';
  const signalLabels = {
    alpha_score: 'Alpha score', expected_return: 'Expected return', information_coefficient: 'Information coefficient',
    rank_ic: 'Rank IC', earnings_revision_pct: 'Earnings revision', revenue_growth_yoy: 'Revenue growth',
  };
  const signalValue = (key, value) => ['expected_return', 'earnings_revision_pct', 'revenue_growth_yoy'].includes(key) ? `${value}%` : value;
  const signals = Object.entries(item.signals || {}).slice(0, 3).map(([key, value]) => `<li><span>${escapeHtml(signalLabels[key] || key)}</span><b>${escapeHtml(signalValue(key, value))}</b></li>`).join('');
  const known = item.known || {};
  const inputDetails = known.input_details || {};
  const knownInputs = Object.entries(known.inputs || {}).map(([key, value]) => {
    const availableAt = inputDetails[key]?.available_at;
    return `<li><span>${escapeHtml(signalLabels[key] || key.replaceAll('_', ' '))}</span><span class="decision-known-value"><b>${escapeHtml(signalValue(key, value))}</b>${availableAt ? `<small>available ${escapeHtml(formatTimestamp(availableAt))}</small>` : ''}</span></li>`;
  }).join('');
  const sourceGroups = Object.entries(known.sources || {}).reduce((groups, [field, source]) => {
    const key = `${source.source_id || 'unknown'}|${source.version || ''}|${source.raw_hash || ''}`;
    if (!groups[key]) groups[key] = { ...source, fields: [] };
    groups[key].fields.push(field);
    return groups;
  }, {});
  const knownSources = Object.values(sourceGroups).map((source) => `<li><span>${escapeHtml(source.source_id || 'Unknown source')}</span><span class="decision-known-value"><b>${source.fields.length} input${source.fields.length === 1 ? '' : 's'}</b><small>${source.version ? `${escapeHtml(source.version)} · ` : ''}available ${escapeHtml(formatTimestamp(source.available_at))}</small></span></li>`).join('');
  const knownMeta = [
    ['Model', known.model_version], ['Feature snapshot', known.feature_snapshot_id], ['Available', known.available_at ? formatTimestamp(known.available_at) : null],
  ].filter(([, value]) => value).map(([label, value]) => `<li><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></li>`).join('');
  const target = Number(item.target_weight);
  const targetText = Number.isFinite(target) ? `${(target * 100).toFixed(1)}% target weight` : 'Target weight not retained';
  const intendedText = action === 'HOLD' && Number.isFinite(target) ? `Maintain ${(target * 100).toFixed(1)}% target weight` : targetText;
  const evidence = item.contradictions?.length
    ? item.contradictions.join(' · ')
    : item.missing?.length
      ? `Missing provenance: ${item.missing.join(', ')}.`
      : item.status === 'detected' ? `${item.source} · verify model/version provenance before treating this as a complete audit record.` : `Decision record is retained and time-valid · ${targetText}.`;
  const steps = Object.fromEntries((ledger.steps || []).map((step) => [step.kind, step]));
  const fill = steps.fill || {};
  const position = steps.position || {};
  const outcome = steps.pnl || {};
  const quantity = fill.quantity || position.quantity;
  const fillText = quantity ? `${quantity} shares${fill.price ? ` at ${fill.price}` : ''}` : 'Execution quantity not retained';
  const heldAtPoint = selectedTimelineIndex !== null ? timelinePositionValues[selectedTimelineIndex] : null;
  const positionText = heldAtPoint !== null && heldAtPoint !== undefined
    ? formatPosition(heldAtPoint)
    : position.quantity ? `${position.quantity} shares` : 'Position not retained';
  const pnl = Number(outcome.pnl);
  const outcomeText = Number.isFinite(pnl) ? `${formatMoney(pnl)} P&L` : 'P&L not retained';
  panel.hidden = false;
  const inputCount = Object.keys(known.inputs || {}).length;
  panel.innerHTML = `<article class="decision-explainer status-${escapeHtml(item.status)}"><p class="eyebrow">ALGORITHM ACTION AT ${escapeHtml(formatTimestamp(item.timestamp))}</p><h3>${escapeHtml(action)}${escapeHtml(symbol)}</h3><p class="decision-why"><b>Why:</b> ${escapeHtml(reason)}</p>${signals ? `<ul class="decision-signals">${signals}</ul>` : ''}<details class="decision-context" open><summary>What the algorithm knew (${inputCount} saved input${inputCount === 1 ? '' : 's'})</summary>${knownMeta ? `<ul class="decision-known">${knownMeta}</ul>` : ''}${knownSources ? `<p class="decision-context-label">CONNECTED SOURCES</p><ul class="decision-known">${knownSources}</ul>` : ''}${knownInputs ? `<p class="decision-context-label">INPUT VALUES</p><ul class="decision-known">${knownInputs}</ul>` : '<p>No detailed inputs were retained for this action.</p>'}</details><div class="decision-outcome"><div><span>DECIDED</span><b>${escapeHtml(intendedText)}</b></div><div><span>TRADED</span><b>${escapeHtml(fillText)}</b></div><div><span>POSITION AFTER</span><b>${escapeHtml(positionText)}</b></div><div><span>RECORDED RESULT</span><b>${escapeHtml(outcomeText)}</b></div></div><small>${escapeHtml(evidence)}</small></article>`;
}

function renderStrategyProfile(profile) {
  const target = document.querySelector('#strategyProfile');
  if (!target || !profile) return;
  const detected = Object.entries(profile.detected || {}).filter(([, field]) => field).map(([kind, field]) => `${kind}: ${field}`);
  const inputs = profile.signals || [];
  target.textContent = `${profile.summary}${detected.length ? ` · ${detected.join(' · ')}` : ''}${inputs.length ? ` · inputs: ${inputs.join(', ')}` : ''}`;
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
    ? 'What did the trading algorithm do here?'
    : 'What did the trading algorithm do—and why?';
  document.querySelector('#diagnosisSubtitle').textContent = selectedLoss
    ? `${label}. This receipt uses only records available by the selected point—never later data.`
    : `${label}. Select a point on the position chart to inspect its action, reason, and prior inputs.`;
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
      if (!replay.evidence_ready || !replay.analysis_ready) { graph.innerHTML = `<p class="timeline-missing">${escapeHtml(replay.reason || 'Not enough observations for statistical analysis.')}</p>`; return; }
      renderCausalFlow(graph, replay.graph.nodes, replay.graph.edges);
      // The card flow is the primary evidence surface; rebuild it from this exact snapshot.
      renderExplanation(replay.analysis, `Replay at ${formatTimestamp(visibleTime)}`, true);
      renderLedger(replay.ledger);
      renderAiForensics(replay.ai_forensics, replay.ledger);
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
    // The decision receipt is the primary surface. The graph stays hidden for
    // now, rather than exposing a second timeline that can overwrite a choice.
    panel.hidden = true;
  } catch (error) { panel.hidden = true; console.warn(error); }
}

function renderDiagnosis(result, records, label) {
  results.hidden = false;
  activeRecords = records;
  renderStrategyProfile(result.strategy_profile);
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
  document.querySelector('#engineState').textContent = 'Diagnosis complete';
  document.querySelector('#engineHint').textContent = `${result.records} records checked · choose a stock and click any point on its position history`;
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

document.querySelector('#openRecordedStrategy').addEventListener('click', async () => {
  try {
    setRunning('Opening the newest strategy captured by the local OMI recorder…');
    const strategiesResponse = await fetch('/api/flight-recorder/strategies');
    const strategies = await strategiesResponse.json();
    if (!strategiesResponse.ok) throw new Error(strategies.error || 'Could not list recorded strategies.');
    const latest = strategies.strategies?.[0];
    if (!latest) throw new Error('No strategy has posted evidence yet. Run an instrumented strategy first.');
    const response = await fetch(`/api/flight-recorder/evidence?strategy_id=${encodeURIComponent(latest.strategy_id)}`);
    const recorded = await response.json();
    if (!response.ok) throw new Error(recorded.error || 'Could not open recorded strategy evidence.');
    activeRecords = recorded.events;
    results.hidden = false;
    const pnl = recorded.events.filter((event) => event.kind === 'pnl').reduce((total, event) => total + (numericValue(event, 'pnl') || 0), 0);
    document.querySelector('#pnlMetric').textContent = formatMoney(pnl);
    document.querySelector('#pnlDetail').textContent = `${recorded.events.filter((event) => event.kind === 'pnl').length} recorded P&L marks`;
    document.querySelector('#recordsMetric').textContent = recorded.events.length.toLocaleString();
    document.querySelector('#changeMetric').textContent = 'Recorded';
    document.querySelector('#changeDetail').textContent = recorded.status.latest_event_timestamp ? formatTimestamp(recorded.status.latest_event_timestamp) : '—';
    renderSnapshotIdentity(recorded.snapshot_id, 'Recorder evidence is append-only and bound to this snapshot.');
    renderStrategyProfile(recorded.strategy_profile);
    renderLedger(recorded.ledger);
    renderAiForensics(recorded.ai_forensics, recorded.ledger, recorded.status.latest_event_timestamp, recorded.detected_decision);
    renderIncidentTimeline(recorded.events);
    document.querySelector('#engineState').textContent = 'Recorded strategy ready';
    document.querySelector('#engineHint').textContent = `${recorded.strategy_id} · ${recorded.events.length} linked evidence events · click its position history to replay any point`;
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    document.querySelector('#engineState').textContent = 'Recorder unavailable';
    notify(error.message);
  }
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
    renderAiForensics(result.ai_forensics, result.ledger);
    document.querySelector('#engineState').textContent = 'Demo ready';
    document.querySelector('#engineHint').textContent = 'Local AI decision evidence imported · lifecycle reconciles · rationale contradiction detected.';
  } catch (error) { document.querySelector('#engineState').textContent = 'Import failed'; notify(error.message); }
});

document.querySelector('#loadCompleteLedgerDemo').addEventListener('click', async () => {
  try {
    setRunning('Loading the local full-product CSV demo…');
    const sampleResponse = await fetch('/api/sample/full-product');
    const sample = await sampleResponse.json();
    if (!sampleResponse.ok) throw new Error(sample.error || 'Could not load the full-product CSV.');
    await diagnose(sample.records, 'Built-in full-product CSV demo');
    document.querySelector('#engineHint').textContent = 'Full local CSV analysed · changing share positions, action reasons, dynamic model inputs, execution, and P&L included · no broker connection used.';
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
