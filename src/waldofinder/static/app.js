const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [ch]));
const paths = {
    history: 'M3 10a9 9 0 1 1 2.7 6.4M3 4v6h6M12 7v5l3 2',
    image: 'M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM3 16l5-5 5 5 3-3 5 5M16 7h.01',
    upload: 'M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5',
    grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z',
    split: 'M12 3v7M5 20v-5a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v5M2 20h6M16 20h6',
    refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2',
    plus: 'M12 5v14M5 12h14',
    minus: 'M5 12h14',
    sliders: 'M4 7h6m5 0h5M4 17h12m4 0h0M10 4v6M16 14v6',
    play: 'M8 5v14l11-7Z',
    stop: 'M6 6h12v12H6Z',
    lock: 'M6 10h12v11H6ZM8 10V6a4 4 0 0 1 8 0v4M12 14v3',
    layers: 'm12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 17l10 5 10-5',
    scan: 'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M8 8h8v8H8Z',
    target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 11v2',
    check: 'm5 12 4 4L19 6',
    x: 'm6 6 12 12M18 6 6 18',
    help: 'M9 8a3 3 0 1 1 5 3c-2 1-2 2-2 3M12 18h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z',
    coins: 'M12 3c5 0 9 2 9 4s-4 4-9 4-9-2-9-4 4-4 9-4ZM3 7v5c0 2 4 4 9 4s9-2 9-4V7M3 12v5c0 2 4 4 9 4s9-2 9-4v-5',
    pin: 'M12 3a6 6 0 0 0-6 6c0 5 6 12 6 12s6-7 6-12a6 6 0 0 0-6-6ZM10 9h4m-2-2v4',
    expand: 'M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6',
    download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    sparkles: 'm12 3 2 6 6 2-6 2-2 6-2-6-6-2 6-2Zm8 13 1 3 3 1-3 1-1 3-1-3-3-1 3-1Z'
};

function icon(name) {
    return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.scan}"/></svg>`;
}
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon));
const palette = ['#8d9fc6', '#53675d', '#bd9b78', '#b5a0c9'];
const presets = ['google/gemini-4-argon', 'openai/gpt-6.1-sol'];
const S = {
    token: '',
    image: null,
    sample: null,
    strategy: 'grid',
    models: [...presets],
    choices: [...presets, 'anthropic/claude-sonnet-5.5'],
    catalog: [],
    catalogReady: false,
    run: null,
    modelIndex: 0,
    selected: null,
    preview: [],
    zoom: 1,
    overlay: true,
    mark: false,
    events: [],
    stream: null,
    history: [],
    loading: false
};
let previewTimer, previewVersion = 0,
    toastTimer;

function nameOf(id) {
    const names = {
        'google/gemini-4-argon': 'Gemini 4 Argon',
        'openai/gpt-6.1-sol': 'GPT-6.1 Sol',
        'anthropic/claude-sonnet-5.5': 'Claude Sonnet 5.5'
    };
    return names[id] || id.split('/').slice(1).join('/') || id;
}

function notice(message, error = false) {
    $('message').hidden = !message;
    $('message').textContent = message;
    $('message').className = `message ${error?'error':''}`;
}

function toast(message) {
    clearTimeout(toastTimer);
    $('toast').textContent = message;
    $('toast').hidden = false;
    toastTimer = setTimeout(() => $('toast').hidden = true, 3500);
}
async function api(path, payload) {
    const options = payload === undefined ? {} : {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Waldo-Token': S.token
        },
        body: JSON.stringify(payload)
    };
    const response = await fetch(path, options);
    let data;
    try {
        data = await response.json();
    } catch {
        throw Error('The local server did not return a valid response.');
    }
    if (!response.ok) throw Error(data.error || 'Request failed.');
    return data;
}

function config() {
    return {
        image_id: S.image?.id,
        models: S.models,
        strategy: S.strategy,
        tiles: Number($('tiles').value),
        columns: null,
        overlap: Number($('overlap').value) / 100,
        max_depth: Number($('max-depth').value),
        min_size: Number($('min-size').value),
        concurrency: Number($('concurrency').value),
        max_requests: Number($('max-requests').value),
        threshold: Number($('threshold').value),
        all_candidates: $('all-candidates').checked,
        explore_negatives: $('explore-negatives').checked,
        max_tokens: Number($('max-tokens').value),
        timeout: 90,
        structured: $('structured').checked
    };
}

function busy() {
    return S.loading || ['running', 'queued', 'stopping'].includes(S.run?.status);
}

function model() {
    return S.run?.models[S.modelIndex];
}

function regions() {
    return S.run ? Object.values(model()?.regions || {}) : S.preview;
}

function selected() {
    return regions().find(r => r.region.id === S.selected);
}

function reviewLabel(key = S.selected) {
    return S.run?.review?.labels?.[`${S.modelIndex}:${key}`]?.verdict;
}

function phase(record) {
    if (record.phase === 'processing' || record.phase === 'queued' || record.phase === 'preview') return record.phase;
    if (record.status === 'error') return 'error';
    if (record.resolution === 'candidate') return 'candidate';
    if (record.decision === 'absent' && record.confidence >= (S.run?.config.threshold ?? .7)) return 'negative';
    return record.decision === 'present' ? 'uncertain' : record.decision || 'uncertain';
}

function renderChoices() {
    $('model-options').innerHTML = S.choices.map((id, i) => `<label class="model-choice"><input type="checkbox" value="${esc(id)}" ${S.models.includes(id)?'checked':''} ${busy()?'disabled':''}><span class="model-monogram" style="color:${palette[i%4]}">${esc(id.split('/')[0][0].toUpperCase())}</span><span class="model-info"><strong>${esc(nameOf(id))}</strong><span>${esc(id.split('/')[0])} · 2026 release</span></span><span class="model-dot" style="background:${palette[i%4]}"></span></label>`).join('');
    $('model-options').querySelectorAll('input').forEach(input => input.addEventListener('change', () => {
        if (input.checked && S.models.length >= 4) {
            input.checked = false;
            toast('Compare up to four models per run.');
            return;
        }
        S.models = Array.from($('model-options').querySelectorAll('input:checked')).map(i => i.value);
        onConfig();
    }));
    $('model-count').textContent = S.models.length;
}

function renderControls() {
    const isBusy = busy();
    $('start-button').disabled = isBusy || !S.image || !S.models.length || !S.catalogReady;
    $('start-button').hidden = isBusy;
    $('stop-button').hidden = !isBusy;
    $('stop-button').disabled = S.loading || S.run?.status === 'stopping';
    $('stop-button').innerHTML = icon('stop') + (S.run?.status === 'stopping' ? 'Finishing in-flight calls…' : 'Stop after current calls');
    $('replay-button').disabled = isBusy;
    $('upload-button').disabled = isBusy;
    $('sample-button').disabled = isBusy;
    document.querySelectorAll('.config-section input,.config-section button[data-strategy],.config-section button[data-tiles],#add-model').forEach(el => el.disabled = isBusy);
    $('model-count').textContent = S.models.length;
    const c = config(),
        n = S.models.length,
        planned = Math.min(c.tiles, c.max_requests);
    $('estimate').textContent = S.strategy === 'grid' ? `${c.tiles} regions × ${n} models${planned<c.tiles?' · capped':''}` : `Up to ${Math.min(c.max_requests,2**(c.max_depth+1)-2)*n} calls · ${n} model${n===1?'':'s'}`;
    $('grid-shape').textContent = Math.sqrt(c.tiles) % 1 === 0 ? `${Math.sqrt(c.tiles)} × ${Math.sqrt(c.tiles)}` : 'balanced rows';
    $('overlap-value').textContent = `${$('overlap').value}%`;
    $('grid-options').hidden = S.strategy !== 'grid';
    $('binary-options').hidden = S.strategy !== 'binary';
    $('strategy-help').textContent = S.strategy === 'grid' ? 'A fresh pair of eyes on every tile.' : 'Divide, inspect, then follow the promising branches.';
    document.querySelectorAll('[data-strategy]').forEach(b => b.setAttribute('aria-pressed', b.dataset.strategy === S.strategy));
    document.querySelectorAll('[data-tiles]').forEach(b => b.classList.toggle('active', Number(b.dataset.tiles) === c.tiles));
    $('mark-target').disabled = !S.run;
    $('mark-target').classList.toggle('active', S.mark);
    $('mark-hint').hidden = !S.mark;
    $('overlay').classList.toggle('marking', S.mark);
    if (!S.run) renderStats();
}

function setImage(image) {
    S.image = image;
    $('scene-image').src = image.url;
    $('source-thumb').src = image.url;
    $('source-thumb').hidden = false;
    $('empty-thumb').hidden = true;
    $('source-name').textContent = image.name;
    $('source-size').textContent = `${image.width.toLocaleString()} × ${image.height.toLocaleString()} px`;
    $('scene-dimensions').textContent = `${image.width} × ${image.height}`;
    $('scene-empty').hidden = true;
    $('image-frame').hidden = false;
    $('overlay').setAttribute('viewBox', `0 0 ${image.width} ${image.height}`);
    S.zoom = 1;
    setZoom();
}

function setZoom(delta = 0) {
    S.zoom = Math.max(.5, Math.min(3, S.zoom + delta));
    $('image-frame').style.width = `${S.zoom*100}%`;
    $('zoom-fit').textContent = `${Math.round(S.zoom*100)}%`;
}
async function refreshPreview() {
    if (S.run || !S.image) return;
    const version = ++previewVersion;
    try {
        const data = await api('/api/preview', config());
        if (version !== previewVersion || S.run) return;
        S.preview = data.regions;
        S.selected = S.preview.some(r => r.region.id === S.selected) ? S.selected : S.preview[0]?.region.id;
        notice('');
        renderScene();
        renderInspector();
    } catch (error) {
        if (version === previewVersion) notice(error.message, true);
    }
}

function onConfig() {
    if (S.run && !busy()) {
        S.stream?.close();
        S.run = null;
        S.selected = null;
        S.modelIndex = 0;
        S.mark = false;
        S.events = [];
        notice('');
        $('activity-log').innerHTML = `<div class="activity-empty">${icon('sparkles')}Configuration updated. Start a fresh experiment.</div>`;
        $('elapsed').textContent = '00:00';
        renderAll();
    }
    renderControls();
    if (!S.run) {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(refreshPreview, 180);
    }
    renderTabs();
}

function renderStats() {
    const all = S.run ? S.run.models.flatMap(m => Object.values(m.regions)) : [],
        done = all.filter(r => r.phase === 'done');
    const c = S.run?.config || config(),
        count = S.run?.models.length || S.models.length;
    const budget = (c.strategy === 'grid' ? Math.min(c.tiles, c.max_requests) : Math.min(c.max_requests, 2 ** (c.max_depth + 1) - 2)) * count;
    const candidates = all.filter(r => r.resolution === 'candidate').length;
    const labels = Object.entries(S.run?.review?.labels || {});
    let agreements = 0,
        assessed = 0;
    for (const [key, label] of labels) {
        if (label.verdict === 'unsure') continue;
        const [index, ...id] = key.split(':');
        const record = S.run.models[Number(index)]?.regions[id.join(':')];
        if (record?.decision && record.decision !== 'uncertain') {
            assessed++;
            if (record.decision === label.verdict) agreements++;
        }
    }
    const withCosts = done.filter(r => typeof r.usage?.cost === 'number');
    const cost = withCosts.reduce((sum, r) => sum + r.usage.cost, 0);
    $('stat-checked').textContent = done.length;
    $('stat-budget').textContent = `/ ${budget} ${c.strategy==='grid'?'planned':'max'}`;
    $('stat-candidates').textContent = candidates;
    $('stat-reviewed').textContent = labels.length;
    $('stat-agreement').textContent = assessed ? `${agreements}/${assessed} agree with model` : 'the final say is yours';
    $('stat-cost').textContent = `$${cost.toFixed(5)}`;
    $('cost-detail').textContent = S.run?.source === 'replay' ? 'recorded cost · no new calls' : done.length && withCosts.length < done.length ? 'partial reporting' : 'pay as you explore';
    $('overall-progress').style.width = `${budget?Math.min(100,done.length/budget*100):0}%`;
    const statuses = {
        running: 'Search in progress',
        queued: 'Preparing search',
        stopping: 'Finishing current calls',
        completed: 'Ready for your review',
        cancelled: 'Stopped · partial results',
        failed: 'Search interrupted',
        interrupted: 'Saved partial results'
    };
    $('run-status').className = `run-status ${busy()?'running':''} ${S.run?.status==='failed'?'failed':''}`;
    $('run-status').innerHTML = `<span class="status-dot"></span>${S.run?.source==='replay'?'Replay · ':''}${statuses[S.run?.status] || 'Ready to search'}`;
    $('activity-status').textContent = busy() ? (S.run?.source === 'replay' ? 'Replaying recorded observations' : 'Live model responses') : S.run ? 'All observations are available for inspection' : 'Waiting for your experiment';
    $('activity-dot').classList.toggle('running', busy());
    const countErrors = all.filter(r => r.status === 'error').length;
    if (S.run?.error) notice(S.run.error, true);
    else if (S.run?.status === 'completed' && countErrors) notice(`${countErrors} region request${countErrors===1?'':'s'} failed. Errors are preserved and never counted as negative detections.`, true);
    else if (S.run?.source === 'replay') notice('Recorded sample replay. These are saved model answers; no new API calls are being made.');
    $('export-run').hidden = !S.run;
    if (S.run) {
        if (S.exportURL) URL.revokeObjectURL(S.exportURL);
        S.exportURL = URL.createObjectURL(new Blob([JSON.stringify({
            format_version: 1,
            ...S.run
        }, null, 2)], {
            type: 'application/json'
        }));
        $('export-run').href = S.exportURL;
        $('export-run').download = `${S.run.id}.json`;
    }
}

function renderTabs() {
    const choices = S.run ? S.run.models.map(m => m.model) : S.models;
    $('model-tabs').innerHTML = choices.map((id, i) => {
        const checked = S.run ? Object.values(S.run.models[i].regions).filter(r => r.phase === 'done').length : 0;
        return `<button class="model-tab ${i===S.modelIndex?'active':''}" data-model-index="${i}"><span class="tab-dot" style="background:${palette[i%4]}"></span>${esc(nameOf(id))}<span class="count-badge">${checked}</span></button>`;
    }).join('');
    $('model-tabs').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
        S.modelIndex = Number(button.dataset.modelIndex);
        S.selected = regions().find(r => r.resolution === 'candidate')?.region.id || regions()[0]?.region.id;
        renderAll();
    }));
}

function renderScene() {
    const all = regions();
    const selectedRecord = selected();
    let leaves = all.filter(r => r.resolution !== 'split');
    if (selectedRecord && !leaves.includes(selectedRecord)) leaves.push(selectedRecord);
    const show = S.overlay ? leaves : [];
    const labelScale = S.image ? Math.max(1, S.image.width / 1000) : 1;
    $('overlay').innerHTML = show.map(record => {
        const [x0, y0, x1, y1] = record.region.box, id = record.region.id;
        const state = phase(record);
        const text = `${id}${state==='processing'?' · searching':''}`;
        return `<g><rect tabindex="0" role="button" aria-label="Inspect region ${esc(id)}" data-region="${esc(id)}" class="region-box ${state} ${S.selected===id?'selected':''}" x="${x0}" y="${y0}" width="${x1-x0}" height="${y1-y0}"><title>${esc(id)} · ${esc(state)}</title></rect><g class="region-label" transform="translate(${x0+5*labelScale} ${y0+5*labelScale}) scale(${labelScale})"><rect width="${text.length*7+10}" height="20" rx="3"/><text x="5" y="14">${esc(text)}</text></g></g>`;
    }).join('');
    const point = S.run?.review?.target;
    if (point) {
        $('overlay').insertAdjacentHTML('beforeend', `<g class="target-marker" transform="translate(${point[0]} ${point[1]}) scale(${labelScale})"><circle r="13" fill="#fff"/><circle r="9" fill="#e47a4c"/><path d="M-5 0H5M0-5V5" stroke="#fff" stroke-width="2"/></g>`);
    }
    $('overlay').classList.toggle('marking', S.mark);
}

function previewCrop(record) {
    const img = $('scene-image');
    if (!img.complete || !img.naturalWidth) return '';
    const [x0, y0, x1, y1] = record.crop_box, canvas = document.createElement('canvas');
    canvas.width = x1 - x0;
    canvas.height = y1 - y0;
    canvas.getContext('2d').drawImage(img, x0, y0, x1 - x0, y1 - y0, 0, 0, x1 - x0, y1 - y0);
    return canvas.toDataURL('image/png');
}

function cropURL(record) {
    return record.crop && S.run ? `/api/runs/${encodeURIComponent(S.run.id)}/files/model-${String(S.modelIndex).padStart(2,'0')}/${record.crop}` : previewCrop(record);
}

function renderInspector() {
    const record = selected(),
        done = record?.phase === 'done';
    $('inspector-region').textContent = record?.region.id || '—';
    document.querySelectorAll('[data-verdict]').forEach(button => {
        button.disabled = !done;
        button.classList.toggle('selected', reviewLabel() === button.dataset.verdict);
    });
    $('clear-label').hidden = !reviewLabel();
    $('review-feedback').textContent = '';
    $('review-feedback').className = 'review-feedback';
    if (!record) {
        $('crop-image').hidden = true;
        $('crop-empty').hidden = false;
        $('enlarge-crop').hidden = true;
        $('crop-size').textContent = '';
        $('crop-decision').innerHTML = '<span class="decision-tag neutral">Preview</span><span class="muted tiny">No model answer yet</span>';
        $('crop-reason').textContent = 'Each model sees only this crop. Inspect the details before trusting its answer.';
        $('crop-coordinates').textContent = '—';
        $('crop-latency').textContent = '—';
        return;
    }
    const url = cropURL(record);
    if (url && $('crop-image').getAttribute('src') !== url) $('crop-image').src = url;
    $('crop-image').hidden = !url;
    $('crop-empty').hidden = !!url;
    $('enlarge-crop').hidden = !url;
    const box = record.crop_box;
    $('crop-size').textContent = `${box[2]-box[0]} × ${box[3]-box[1]} px`;
    $('crop-coordinates').textContent = `[${box.join(', ')}]`;
    $('crop-latency').textContent = record.latency_seconds != null ? `${Number(record.latency_seconds).toFixed(2)} s` : '—';
    const status = phase(record),
        label = record.status === 'error' ? 'Request error' : record.phase === 'done' ? record.decision === 'present' ? 'Model says present' : record.decision === 'absent' ? 'Not detected' : 'Uncertain' : status === 'processing' ? 'Looking closely…' : status === 'queued' ? 'In the queue' : 'Preview crop';
    $('crop-decision').innerHTML = `<span class="decision-tag ${record.phase==='done'?(record.status==='error'?'error':record.decision):status==='processing'?'processing':'neutral'}">${esc(label)}</span><span class="tiny">${record.confidence!=null?`${Math.round(record.confidence*100)}% confidence`:record.region.depth?`depth ${record.region.depth}`:'not evaluated'}</span>`;
    $('crop-reason').textContent = record.reason || record.error || (record.phase === 'processing' ? 'This crop is with the model now. Its answer will appear as soon as it arrives.' : 'Each model sees only this crop. Inspect the details before trusting its answer.');
    const verdict = reviewLabel();
    if (verdict) {
        const same = verdict === record.decision;
        $('review-feedback').textContent = verdict === 'unsure' ? 'Saved as unsure. You can revisit this crop anytime.' : same ? 'Saved. Your verdict agrees with the model.' : 'Saved. Your verdict differs from the model.';
        $('review-feedback').classList.toggle('disagree', !same && verdict !== 'unsure');
    }
    const target = S.run?.review?.target;
    $('target-status').hidden = !target;
    if (target) $('target-text').textContent = `Your marker (${target.join(', ')}) is ${target[0]>=box[0]&&target[0]<box[2]&&target[1]>=box[1]&&target[1]<box[3]?'inside':'outside'} this crop.`;
}

function renderCards() {
    const all = regions().filter(r => r.phase === 'done');
    $('regions-count').textContent = all.length;
    const filter = $('region-filter').value;
    const list = all.filter(r => filter === 'all' || filter === 'candidates' && r.resolution === 'candidate' || filter === 'unreviewed' && !reviewLabel(r.region.id) || filter === 'reviewed' && reviewLabel(r.region.id));
    $('region-cards').innerHTML = list.length ? list.map(record => `<button class="region-card ${S.selected===record.region.id?'selected':''}" data-inspect="${esc(record.region.id)}" aria-label="Inspect ${esc(record.region.id)}: ${esc(record.decision || 'error')}"><img src="${esc(cropURL(record))}" alt="Crop ${esc(record.region.id)}" loading="lazy">${reviewLabel(record.region.id)?`<span class="tile-review">${icon('check')}reviewed</span>`:''}<div class="tile-info"><span class="tile-id mono">${esc(record.region.id)}</span><span class="tile-confidence">${record.confidence!=null?Math.round(record.confidence*100)+'%':''}</span></div><div class="tile-info" style="padding-top:0"><span class="decision-tag ${record.status==='error'?'error':record.decision}">${esc(record.decision || 'error')}</span><span class="tiny muted">${record.latency_seconds!=null?record.latency_seconds.toFixed(1)+'s':''}</span></div></button>`).join('') : `<div class="regions-empty">${all.length?'No regions match this filter.':'Results will appear here as each model finishes a crop.'}</div>`;
    $('region-cards').querySelectorAll('[data-inspect]').forEach(button => button.addEventListener('click', () => selectRegion(button.dataset.inspect)));
}

function selectRegion(id) {
    S.selected = id;
    renderScene();
    renderInspector();
    renderCards();
}

function activity(event) {
    const p = event.payload,
        m = p.model_index != null ? S.run?.models[p.model_index] : null,
        n = m ? nameOf(m.model) : '';
    let message = '';
    if (event.type === 'model_started') message = `${esc(n)} <strong>started its search</strong>`;
    if (event.type === 'region_started') message = `${esc(n)} is inspecting <strong>${esc(p.region.id)}</strong>`;
    if (event.type === 'region_finished') {
        const r = p.observation;
        message = `${esc(n)} · <strong>${esc(r.region.id)}</strong> · ${r.status==='error'?'request failed':esc(r.decision)+' · '+Math.round(r.confidence*100)+'% confidence'}`;
    }
    if (event.type === 'run_finished') message = event.payload.status === 'cancelled' ? 'Search stopped. Completed regions are ready for review.' : '<strong>Search complete.</strong> Your eyes get the final say.';
    if (event.type === 'run_stopping') message = 'Stopping after in-flight calls finish. No new crops will be sent.';
    if (event.type === 'run_error') message = esc(p.message);
    if (!message) return;
    S.events.unshift({
        at: event.at,
        message
    });
    S.events = S.events.slice(0, 6);
    $('activity-log').innerHTML = S.events.map(row => `<div class="activity-entry">${icon('scan')}<span>${row.message}</span><time>${new Date(row.at).toLocaleTimeString([],{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time></div>`).join('');
}

function applyEvent(event) {
    if (!S.run || event.seq <= S.run.seq) return;
    S.run.seq = event.seq;
    const p = event.payload,
        m = p.model_index != null ? S.run.models[p.model_index] : null;
    if (m) {
        if (event.type === 'model_started') m.status = 'running';
        if (event.type === 'region_queued' || event.type === 'region_started') {
            const id = p.region.id;
            m.regions[id] = {
                ...m.regions[id],
                ...p,
                phase: event.type === 'region_started' ? 'processing' : 'queued'
            };
            if (S.modelIndex === p.model_index && !S.selected) S.selected = id;
        }
        if (event.type === 'region_finished') {
            const r = p.observation;
            m.regions[r.region.id] = {
                ...m.regions[r.region.id],
                ...r,
                phase: 'done'
            };
            if (S.modelIndex === p.model_index && (!S.selected || selected()?.phase === 'preview')) S.selected = r.region.id;
        }
        if (event.type === 'region_resolved') {
            m.regions[p.region_id].resolution = p.resolution;
            if (p.resolution === 'candidate' && S.modelIndex === p.model_index) S.selected = p.region_id;
        }
        if (event.type === 'model_finished') {
            m.status = p.summary?.stop_reason === 'cancelled' ? 'cancelled' : 'completed';
            m.summary = p.summary;
        }
    }
    if (event.type === 'run_stopping') S.run.status = 'stopping';
    if (event.type === 'run_finished') {
        S.run.status = p.status;
        S.run.finished_at = event.at;
        S.stream?.close();
        if (p.status === 'completed' && S.run.source === 'live') $('replay-button').hidden = false;
        if (!S.selected) S.selected = regions()[0]?.region.id;
    }
    if (event.type === 'run_error') {
        S.run.status = 'failed';
        S.run.error = p.message;
        S.run.finished_at = event.at;
        S.stream?.close();
    }
    if (event.type === 'review_updated') S.run.review = p.review;
    activity(event);
    renderAll();
}

function watch() {
    S.stream?.close();
    if (!S.run || !['running', 'queued', 'stopping'].includes(S.run.status)) return;
    S.stream = new EventSource(`/api/runs/${encodeURIComponent(S.run.id)}/events?since=${S.run.seq}`);
    S.stream.onmessage = message => {
        try {
            applyEvent(JSON.parse(message.data));
        } catch {
            notice('A live update could not be read. Reopen this run from history to refresh.', true);
        }
    };
    S.stream.onerror = async () => {
        if (!S.run || !busy()) return;
        try {
            const snapshot = await api(`/api/runs/${encodeURIComponent(S.run.id)}`);
            if (['completed', 'cancelled', 'failed', 'interrupted'].includes(snapshot.status)) {
                S.stream.close();
                S.run = snapshot;
                renderAll();
            } else $('activity-status').textContent = 'Reconnecting to the live stream…';
        } catch {
            $('activity-status').textContent = 'Connection lost. Reconnecting…';
        }
    };
}

function renderAll() {
    renderControls();
    renderStats();
    renderTabs();
    renderScene();
    renderInspector();
    renderCards();
}

function applyConfig(run) {
    const c = run.config;
    S.strategy = c.strategy;
    for (const [id, key] of Object.entries({
            'tiles': 'tiles',
            'max-depth': 'max_depth',
            'min-size': 'min_size',
            'concurrency': 'concurrency',
            'max-requests': 'max_requests',
            'threshold': 'threshold',
            'max-tokens': 'max_tokens'
        })) {
        if (c[key] != null) $(id).value = c[key];
    }
    $('overlap').value = Math.round(c.overlap * 100);
    for (const [id, key] of Object.entries({
            'explore-negatives': 'explore_negatives',
            'all-candidates': 'all_candidates',
            'structured': 'structured'
        })) $(id).checked = !!c[key];
    S.models = run.models.map(m => m.model);
    S.choices = Array.from(new Set([...S.choices, ...S.models]));
}
async function loadRun(id) {
    const run = await api(`/api/runs/${encodeURIComponent(id)}`);
    S.stream?.close();
    S.run = run;
    S.modelIndex = 0;
    S.selected = Object.values(run.models[0]?.regions || {}).find(r => r.resolution === 'candidate')?.region.id || Object.values(run.models[0]?.regions || {})[0]?.region.id;
    S.events = [];
    S.mark = false;
    applyConfig(run);
    setImage(run.image);
    notice('');
    renderChoices();
    renderAll();
    $('activity-log').innerHTML = `<div class="activity-empty">${icon('history')}Saved experiment loaded. Click a region to inspect or review it.</div>`;
    watch();
    try {
        localStorage.setItem('waldofinder:last-run', id);
    } catch {}
}
async function start(replay = false) {
    if (busy() || !S.image) return;
    S.loading = true;
    notice('');
    renderControls();
    try {
        const run = await api(replay ? '/api/replay' : '/api/runs', config());
        S.run = run;
        S.selected = null;
        S.modelIndex = 0;
        S.mark = false;
        S.events = [];
        setImage(run.image);
        applyConfig(run);
        renderChoices();
        $('activity-log').innerHTML = `<div class="activity-empty">${icon('sparkles')}Preparing the first crops…</div>`;
        S.loading = false;
        renderAll();
        watch();
        try {
            localStorage.setItem('waldofinder:last-run', run.id);
        } catch {}
    } catch (error) {
        S.loading = false;
        notice(error.message, true);
        renderControls();
    }
}
async function review(verdict) {
    if (!selected() || !S.run) return;
    try {
        S.run.review = await api(`/api/runs/${encodeURIComponent(S.run.id)}/review`, {
            label: {
                model_index: S.modelIndex,
                region_id: S.selected,
                verdict
            }
        });
        renderAll();
        toast(verdict === 'clear' ? 'Review cleared.' : 'Review saved locally.');
    } catch (error) {
        notice(error.message, true);
    }
}
async function refreshModels() {
    S.catalogReady = false;
    renderControls();
    $('catalog-status').textContent = 'Loading current vision models…';
    try {
        const data = await api('/api/models');
        S.catalog = data.models;
        S.catalogReady = true;
        renderChoices();
        $('catalog-status').textContent = `${data.models.length} vision models · 2026 only`;
        $('model-catalog').innerHTML = data.models.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
    } catch (error) {
        $('catalog-status').textContent = 'Catalog unavailable · tap refresh';
        notice(error.message, true);
    }
    renderControls();
}

function resetForImage(image) {
    $('elapsed').textContent = '00:00';
    $('activity-log').innerHTML = `<div class="activity-empty">${icon('sparkles')}New scene ready. Configure a search to begin.</div>`;
    S.stream?.close();
    S.run = null;
    S.selected = null;
    S.modelIndex = 0;
    S.events = [];
    S.mark = false;
    try {
        localStorage.removeItem('waldofinder:last-run');
    } catch {}
    setImage(image);
    notice('');
    renderChoices();
    renderAll();
    refreshPreview();
}
$('start-button').addEventListener('click', () => start());
$('replay-button').addEventListener('click', () => start(true));
$('stop-button').addEventListener('click', async () => {
    try {
        const runId = S.run.id;
        const snapshot = await api(`/api/runs/${encodeURIComponent(runId)}/stop`, {});
        // A completion event can arrive before the stop response. Keep the newer state.
        if (S.run?.id === runId && snapshot.seq >= S.run.seq) S.run = snapshot;
        renderAll();
    } catch (error) {
        notice(error.message, true);
    }
});
document.querySelectorAll('[data-strategy]').forEach(button => button.addEventListener('click', () => {
    if (busy()) return;
    S.strategy = button.dataset.strategy;
    onConfig();
}));
document.querySelectorAll('[data-tiles]').forEach(button => button.addEventListener('click', () => {
    $('tiles').value = button.dataset.tiles;
    onConfig();
}));
document.querySelectorAll('#tiles,#max-depth,#min-size,#concurrency,#max-requests,#max-tokens,#threshold,#overlap,#explore-negatives,#all-candidates,#structured').forEach(input => input.addEventListener('input', onConfig));
$('upload-button').addEventListener('click', () => $('image-file').click());
$('sample-button').addEventListener('click', () => resetForImage(S.sample));
$('image-file').addEventListener('change', async () => {
    const file = $('image-file').files[0];
    if (!file) return;
    if (file.size > 20_000_000) {
        notice('Choose an image smaller than 20 MB.', true);
        return;
    }
    try {
        const response = await fetch('/api/images', {
            method: 'POST',
            headers: {
                'X-Waldo-Token': S.token,
                'X-Filename': encodeURIComponent(file.name),
                'Content-Type': file.type || 'application/octet-stream'
            },
            body: file
        });
        const image = await response.json();
        if (!response.ok) throw Error(image.error);
        resetForImage(image);
    } catch (error) {
        notice(error.message, true);
    } finally {
        $('image-file').value = '';
    }
});
$('refresh-models').addEventListener('click', refreshModels);
$('add-model').addEventListener('click', () => {
    const value = $('custom-model').value.trim();
    if (!S.catalog.some(m => m.id === value)) {
        toast('Choose an image-capable model from the catalog.');
        return;
    }
    if (S.models.length >= 4) {
        toast('Compare up to four models per run.');
        return;
    }
    if (!S.choices.includes(value)) S.choices.push(value);
    if (!S.models.includes(value)) S.models.push(value);
    $('custom-model').value = '';
    renderChoices();
    onConfig();
});
$('zoom-in').addEventListener('click', () => setZoom(.25));
$('zoom-out').addEventListener('click', () => setZoom(-.25));
$('zoom-fit').addEventListener('click', () => {
    S.zoom = 1;
    setZoom();
});
$('toggle-grid').addEventListener('click', () => {
    S.overlay = !S.overlay;
    $('toggle-grid').setAttribute('aria-pressed', S.overlay);
    $('toggle-grid').classList.toggle('active', S.overlay);
    renderScene();
});
$('mark-target').addEventListener('click', () => {
    S.mark = !S.mark;
    renderControls();
});
$('overlay').addEventListener('click', async event => {
    if (S.mark && S.run) {
        const bounds = $('overlay').getBoundingClientRect(),
            point = [Math.floor((event.clientX - bounds.left) / bounds.width * S.image.width), Math.floor((event.clientY - bounds.top) / bounds.height * S.image.height)];
        try {
            S.run.review = await api(`/api/runs/${encodeURIComponent(S.run.id)}/review`, {
                target: point
            });
            S.mark = false;
            renderAll();
            toast('Waldo marker saved. Compare it with each crop.');
        } catch (error) {
            notice(error.message, true);
        }
        return;
    }
    const node = event.target.closest('[data-region]');
    if (node) selectRegion(node.dataset.region);
});
$('overlay').addEventListener('keydown', event => {
    if (['Enter', ' '].includes(event.key) && event.target.dataset.region) {
        event.preventDefault();
        selectRegion(event.target.dataset.region);
    }
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && S.mark) {
        S.mark = false;
        renderControls();
    }
});
$('clear-target').addEventListener('click', async () => {
    try {
        S.run.review = await api(`/api/runs/${encodeURIComponent(S.run.id)}/review`, {
            target: null
        });
        renderAll();
        toast('Marker cleared.');
    } catch (error) {
        notice(error.message, true);
    }
});
document.querySelectorAll('[data-verdict]').forEach(button => button.addEventListener('click', () => review(button.dataset.verdict)));
$('clear-label').addEventListener('click', () => review('clear'));
$('region-filter').addEventListener('change', renderCards);
$('enlarge-crop').addEventListener('click', () => {
    $('full-crop').src = $('crop-image').src;
    $('crop-dialog-title').textContent = `${S.selected} · exact crop`;
    $('crop-dialog').showModal();
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
$('history-button').addEventListener('click', async () => {
    try {
        const data = await api('/api/runs');
        S.history = data.runs;
        $('history-list').innerHTML = data.runs.length ? data.runs.map(run => `<button class="history-row" data-run="${esc(run.id)}"><img src="${esc(run.image?.url || '')}" alt="Saved scene"><div><strong>${esc(run.config?.strategy==='binary'?'Binary partition':`${run.config?.tiles || '?'}-region grid`)}${run.source==='replay'?' · Replay':''}</strong><small>${esc(run.models.map(nameOf).join(' · '))}</small><small>${esc(new Date(run.created_at).toLocaleString())}</small></div><span class="history-status">${esc(run.status)}</span></button>`).join('') : '<p class="muted small">Your experiments will appear here.</p>';
        $('history-list').querySelectorAll('[data-run]').forEach(button => button.addEventListener('click', async () => {
            try {
                await loadRun(button.dataset.run);
                $('history-dialog').close();
            } catch (error) {
                notice(error.message, true);
            }
        }));
        $('history-dialog').showModal();
    } catch (error) {
        notice(error.message, true);
    }
});
$('scene-image').addEventListener('load', () => {
    renderScene();
    renderInspector();
});
setInterval(() => {
    if (!S.run) return;
    let seconds;
    if (S.run.finished_at) seconds = (new Date(S.run.finished_at) - new Date(S.run.created_at)) / 1000;
    else if (busy()) seconds = (Date.now() - new Date(S.run.created_at)) / 1000;
    else seconds = S.run.models.reduce((sum, m) => sum + (m.summary?.wall_seconds || 0), 0);
    seconds = Math.max(0, Math.floor(seconds));
    $('elapsed').textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
}, 500);
async function init() {
    renderChoices();
    renderControls();
    renderTabs();
    try {
        const boot = await api('/api/bootstrap');
        S.token = boot.token;
        S.sample = boot.sample;
        S.history = boot.history;
        $('replay-button').hidden = !boot.replay_available;
        $('sample-button').hidden = !boot.sample;
        $('auth-note').textContent = `${boot.auth}. Keys stay local. Live runs use API credits.`;
        if (boot.sample) {
            setImage(boot.sample);
            await refreshPreview();
        } else {
            $('image-frame').hidden = true;
            $('scene-empty').hidden = false;
        }
        let last;
        try {
            last = localStorage.getItem('waldofinder:last-run');
        } catch {}
        boot.history = boot.history.filter(r => r.models.every(id => !['google/gemini-2.5-flash', 'openai/gpt-4.1-mini'].includes(id)));
        const active = boot.history.find(r => ['running', 'queued', 'stopping'].includes(r.status));
        if (active) await loadRun(active.id);
        else if (last && boot.history.some(r => r.id === last)) await loadRun(last);
        renderAll();
        refreshModels();
    } catch (error) {
        notice(error.message, true);
    }
}
init();