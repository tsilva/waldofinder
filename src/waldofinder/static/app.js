const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [ch]));
const paths = {
    sliders: 'M4 7h6m5 0h5M4 17h12m4 0h0M10 4v6M16 14v6',
    image: 'M3 3h18v18H3ZM3 16l5-5 5 5 3-3 5 5M16 7h.01',
    history: 'M3 10a9 9 0 1 1 2.7 6.4M3 4v6h6M12 7v5l3 2',
    download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    play: 'M8 5v14l11-7Z',
    stop: 'M6 6h12v12H6Z',
    pin: 'M12 3a6 6 0 0 0-6 6c0 5 6 12 6 12s6-7 6-12a6 6 0 0 0-6-6ZM10 9h4m-2-2v4',
    refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2',
    x: 'm6 6 12 12M18 6 6 18'
};
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[el.dataset.icon]}"/></svg>`);
const presets = ['google/gemini-4-argon', 'openai/gpt-6.1-sol'];
const S = {
    token: '',
    image: null,
    models: [...presets],
    choices: [...presets, 'anthropic/claude-sonnet-5.5'],
    catalog: [],
    catalogReady: false,
    referenceReady: false,
    run: null,
    preview: [],
    stream: null,
    loading: false,
    selected: null,
    modelIndex: 0,
    mark: false,
    reviewPending: false
};
let previewVersion = 0,
    renderPending = false,
    configBefore = null;
const fields = {
    'tiles': 'tiles',
    'max-depth': 'max_depth',
    'min-size': 'min_size',
    'concurrency': 'concurrency',
    'max-requests': 'max_requests',
    'threshold': 'threshold',
    'max-tokens': 'max_tokens',
    'timeout': 'timeout'
};
const nameOf = id => ({
    'google/gemini-4-argon': 'Gemini 4 Argon',
    'openai/gpt-6.1-sol': 'GPT-6.1 Sol',
    'anthropic/claude-sonnet-5.5': 'Claude Sonnet 5.5'
} [id] || id.split('/').slice(1).join('/') || id);
const aliasOf = (id, i) => ({
    'google/gemini-4-argon': 'G4',
    'openai/gpt-6.1-sol': 'GPT6.1',
    'anthropic/claude-sonnet-5.5': 'C5.5'
} [id] || `M${i+1}`);
const running = () => ['running', 'queued', 'stopping'].includes(S.run?.status);
const busy = () => S.loading || running();
const models = () => S.run?.models || S.models.map(model => ({
    model,
    regions: {}
}));
const selected = () => S.run?.models[S.modelIndex]?.regions[S.selected] || S.preview.find(r => r.region.id === S.selected);
const verdict = (index = S.modelIndex, id = S.selected) => S.run?.review?.labels?.[`${index}:${id}`]?.verdict;

function notice(text = '', error = false) {
    $('message').textContent = text;
    $('message').hidden = !text;
    $('message').classList.toggle('error', error);
}
async function api(path, payload) {
    const response = await fetch(path, payload === undefined ? {} : {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Waldo-Token': S.token
        },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Request failed.');
    return data;
}

function config() {
    const c = {
        image_id: S.image?.id,
        models: [...S.models],
        strategy: $('strategy').value,
        columns: null,
        overlap: Number($('overlap').value) / 100,
        reasoning_effort: $('reasoning-effort').value,
        structured: $('structured').checked,
        explore_negatives: $('explore-negatives').checked,
        all_candidates: $('all-candidates').checked
    };
    for (const [id, key] of Object.entries(fields)) c[key] = Number($(id).value);
    return c;
}

function renderConfig() {
    $('grid-options').hidden = $('strategy').value !== 'grid';
    $('binary-options').hidden = $('strategy').value !== 'binary';
    const c = config(),
        count = S.models.length;
    const cap = c.strategy === 'grid' ? Math.min(c.tiles, c.max_requests) : Math.min(c.max_requests, 2 ** (c.max_depth + 1) - 2);
    $('estimate').textContent = `${count} model${count===1?'':'s'} · up to ${cap*count} calls · ${c.concurrency} parallel · uses API credits`;
}

function renderChoices() {
    $('model-options').innerHTML = S.choices.map((id, i) => `<label class="model-choice"><input type="checkbox" value="${esc(id)}" ${S.models.includes(id)?'checked':''}><span>${esc(nameOf(id))}</span><small>${esc(aliasOf(id,i))}</small></label>`).join('');
    $('model-options').querySelectorAll('input').forEach(input => input.addEventListener('change', () => {
        const checked = [...$('model-options').querySelectorAll('input:checked')].map(el => el.value);
        if (checked.length > 4) {
            input.checked = false;
            $('config-error').textContent = 'Select up to four models.';
            $('config-error').hidden = false;
            return;
        }
        S.models = checked;
        renderConfig();
    }));
}

function fitImage() {
    if (!S.image) return;
    const stage = $('scene-viewport'),
        padding = parseFloat(getComputedStyle(stage).paddingLeft) * 2;
    const scale = Math.min((stage.clientWidth - padding) / S.image.width, (stage.clientHeight - padding) / S.image.height);
    $('image-frame').style.width = `${Math.max(1,S.image.width*scale)}px`;
    $('image-frame').style.height = `${Math.max(1,S.image.height*scale)}px`;
}

function setImage(image) {
    S.image = image;
    if ($('scene-image').getAttribute('src') !== image.url) $('scene-image').src = image.url;
    $('image-frame').hidden = false;
    $('scene-empty').hidden = true;
    $('overlay').setAttribute('viewBox', `0 0 ${image.width} ${image.height}`);
    fitImage();
}
async function preview() {
    const version = ++previewVersion;
    if (!S.image || S.run || !S.models.length) {
        renderAll();
        return;
    }
    try {
        const data = await api('/api/preview', config());
        if (version !== previewVersion || S.run) return;
        S.preview = data.regions;
        renderAll();
    } catch (error) {
        if (version === previewVersion) notice(error.message, true);
    }
}

function phase(record) {
    if (!record || record.phase === 'preview') return 'preview';
    if (record.phase !== 'done') return running() ? record.phase : 'untested';
    if (record.status === 'error') return 'error';
    if (record.decision === 'present' && record.confidence >= (S.run?.config.threshold ?? .7)) return 'candidate';
    if (record.decision === 'absent' && record.confidence >= (S.run?.config.threshold ?? .7)) return 'negative';
    return 'uncertain';
}

function statusText(record) {
    const state = phase(record);
    if (state === 'preview') return 'Ready';
    if (state === 'processing') return 'Running';
    if (state === 'queued') return 'Queued';
    if (state === 'untested') return 'Not tested';
    if (state === 'error') return 'Error';
    const decision = record.decision === 'present' ? 'Present' : record.decision === 'absent' ? 'Absent' : 'Uncertain';
    return `${decision} ${Math.round(record.confidence*100)}%`;
}

function sceneLeaves() {
    const all = new Map();
    models().forEach(m => Object.values(m.regions).forEach(r => all.set(r.region.id, r)));
    if (!all.size) return S.preview;
    // A shared binary partition uses the deepest complete pair found by any model.
    return [...all.values()].filter(r => {
        const id = r.region.id;
        if (all.has(`${id}.0`) && all.has(`${id}.1`)) return false;
        let ancestor = id;
        while (ancestor.includes('.')) {
            ancestor = ancestor.slice(0, ancestor.lastIndexOf('.'));
            if (all.has(ancestor) && !(all.has(`${ancestor}.0`) && all.has(`${ancestor}.1`))) return false;
        }
        return true;
    });
}

function recordFor(m, region) {
    let id = region.id;
    while (id) {
        if (m.regions[id]) return m.regions[id];
        if (!id.includes('.')) break;
        id = id.slice(0, id.lastIndexOf('.'));
    }
    return null;
}

function renderScene() {
    if (!S.image) return;
    const entries = models(),
        leaves = sceneLeaves();
    const scale = $('image-frame').clientWidth / S.image.width || 1;
    $('overlay').innerHTML = leaves.map(record => {
        const region = record.region,
            [x, y, x1, y1] = region.box,
            w = x1 - x,
            h = y1 - y;
        const rows = entries.map((m, i) => ({
            i,
            m,
            r: recordFor(m, region)
        }));
        // Keep the mask undecided until all models reject the region. Individual
        // model badges retain their own decisions when the models disagree.
        const priorities = ['processing', 'candidate', 'uncertain', 'queued', 'error', 'untested', 'preview', 'negative'];
        const active = priorities.map(state => rows.find(row => phase(row.r) === state)).find(Boolean) || rows[0];
        const maxText = Math.max(...rows.map(({
            i,
            m,
            r
        }) => `${aliasOf(m.model,i)} · ${statusText(r)}${r && r.region.id!==region.id?' ↑':''}`.length));
        const size = Math.max(.1, Math.min(11 / scale, (w - 8) / (maxText * .62 + 2), (h - 6) / (entries.length * 1.65 + 1.4)));
        const line = size * 1.65,
            inset = Math.min(5 / scale, w * .03, h * .03);
        const badges = rows.map(({
            i,
            m,
            r
        }, row) => {
            const parent = r && r.region.id !== region.id;
            const text = `${aliasOf(m.model,i)} · ${statusText(r)}${parent?' ↑':''}`;
            const title = `${nameOf(m.model)} · ${region.id}: ${statusText(r)}${parent?` (parent ${r.region.id})`:''}${verdict(i,r?.region.id)?' · human reviewed':''}`;
            return `<g class="status-row ${phase(r)}" role="button" tabindex="0" aria-label="${esc(title)}" data-region="${esc(r?.region.id || region.id)}" data-model="${i}" transform="translate(${x+inset} ${y+inset+size*1.35+row*line})"><title>${esc(title)}</title><rect width="${Math.min(w-2*inset,size*(text.length*.62+1.5))}" height="${line-1/scale}" rx="${2/scale}"/><text x="${size*.6}" y="${size*1.13}" font-size="${size}">${esc(text)}</text>${verdict(i,r?.region.id)?`<circle class="review-dot" cx="${size*.25}" cy="${size*.25}" r="${size*.22}"/>`:''}</g>`;
        }).join('');
        return `<g><rect class="region-box ${phase(active?.r)} ${S.selected===region.id?'selected':''}" x="${x}" y="${y}" width="${w}" height="${h}" tabindex="0" role="button" data-region="${esc(region.id)}" data-model="${active?.i || 0}" aria-label="Review region ${esc(region.id)}"><title>${esc(region.id)} · click a model status to review</title></rect><text class="region-label" x="${x+inset}" y="${y+inset+size}" font-size="${size}">${esc(region.id)}</text>${badges}</g>`;
    }).join('');
    const target = S.run?.review?.target;
    if (target) $('overlay').insertAdjacentHTML('beforeend', `<g class="target-marker" transform="translate(${target[0]} ${target[1]}) scale(${1/scale})"><circle r="10" fill="#fff"/><circle r="7" fill="#d64b3b"/><path d="M-4 0H4M0-4V4" stroke="#fff" stroke-width="2"/></g>`);
    $('overlay').classList.toggle('marking', S.mark);
}

function renderControls() {
    $('mask-legend').hidden = !S.image;
    $('start-button').hidden = busy();
    $('start-button').disabled = busy() || !S.image || !S.models.length || !S.catalogReady || !S.referenceReady;
    $('stop-button').hidden = !busy();
    $('stop-button').disabled = S.loading || S.run?.status === 'stopping';
    $('config-fields').disabled = busy();
    $('upload-button').disabled = busy();
    $('export-button').disabled = !S.run;
    $('mark-target').disabled = !S.run;
    $('mark-target').classList.toggle('active', S.mark);
    $('mark-hint').hidden = !S.mark;
    $('clear-target').hidden = !S.run?.review?.target;
    const all = S.run?.models.flatMap(m => Object.values(m.regions)) || [],
        done = all.filter(r => r.phase === 'done');
    const active = all.filter(r => r.phase === 'processing').length;
    const candidates = all.filter(r => r.resolution === 'candidate').length;
    const errors = done.filter(r => r.status === 'error').length;
    const cost = done.reduce((sum, r) => sum + (Number(r.usage?.cost) || 0), 0);
    const incomplete = done.some(r => r.usage?.cost == null);
    const reviewed = Object.keys(S.run?.review?.labels || {}).length;
    const status = S.loading ? 'Starting…' : S.run?.status || 'Ready';
    $('run-status').textContent = `${S.run?.source === 'replay' ? 'Replay · ' : ''}${status === 'stopping' ? 'Stopping…' : status[0].toUpperCase() + status.slice(1)}`;
    $('stats').textContent = S.run ? `${done.length} calls · ${active} running · ${candidates} candidates · ${reviewed} reviewed${errors?` · ${errors} errors`:''} · $${cost.toFixed(5)}${incomplete?' + unreported':''}` : `${$('strategy').value==='grid'?`${$('tiles').value} regions`:'Binary'} · ${S.models.length} models · ${$('concurrency').value} parallel`;
    $('stats').title = $('stats').textContent;
}

function previewCrop(record) {
    if (!$('scene-image').complete || !$('scene-image').naturalWidth) return '';
    const [x, y, x1, y1] = record.crop_box || record.region.box, canvas = document.createElement('canvas');
    canvas.width = x1 - x;
    canvas.height = y1 - y;
    canvas.getContext('2d').drawImage($('scene-image'), x, y, x1 - x, y1 - y, 0, 0, x1 - x, y1 - y);
    return canvas.toDataURL('image/png');
}

function renderReview() {
    if (!$('review-dialog').open) return;
    const entries = models(),
        m = entries[S.modelIndex];
    $('review-model').innerHTML = entries.map((entry, i) => `<option value="${i}" ${i===S.modelIndex?'selected':''}>${esc(nameOf(entry.model))}</option>`).join('');
    const records = S.run ? Object.values(m?.regions || {}) : S.preview;
    if (!records.some(r => r.region.id === S.selected)) S.selected = records[0]?.region.id;
    $('review-region').innerHTML = records.map(r => `<option ${r.region.id===S.selected?'selected':''} value="${esc(r.region.id)}">${esc(r.region.id)} · ${esc(statusText(r))}</option>`).join('');
    const r = selected();
    if (!r) {
        $('crop-image').hidden = true;
        $('crop-decision').textContent = 'Waiting for region';
        $('crop-reason').textContent = '';
        $('crop-meta').textContent = '';
    } else {
        const src = r.crop && S.run ? `/api/runs/${encodeURIComponent(S.run.id)}/files/${m.summary?.artifact_dir || `model-${String(S.modelIndex).padStart(2,'0')}`}/${r.crop}` : previewCrop(r);
        if ($('crop-image').getAttribute('src') !== src) $('crop-image').src = src;
        $('crop-image').hidden = !src;
        $('crop-decision').textContent = `${r.phase==='done' && r.status!=='error'?'Model: ':''}${statusText(r)}`;
        const box = r.crop_box || r.region.box;
        const detail = r.request_settings?.image_detail || (S.run ? S.run.image_detail || 'auto' : 'original');
        $('crop-meta').textContent = `${box[2]-box[0]} × ${box[3]-box[1]} px · ${detail} detail${r.latency_seconds!=null?` · ${r.latency_seconds.toFixed(2)}s`:''} · [${box.join(', ')}]`;
        $('crop-reason').textContent = r.reason || r.error || '';
    }
    document.querySelectorAll('[data-verdict]').forEach(button => {
        button.disabled = !S.run || r?.phase !== 'done' || S.reviewPending;
        button.classList.toggle('selected', verdict() === button.dataset.verdict);
    });
    $('clear-label').hidden = !verdict();
    $('clear-label').disabled = S.reviewPending;
    $('review-feedback').textContent = verdict() ? `Saved: ${verdict()}. Model prediction remains unchanged.` : 'Human labels are saved separately from model predictions.';
}

function renderAll() {
    renderControls();
    renderScene();
    renderReview();
}

function scheduleRender() {
    if (!renderPending) {
        renderPending = true;
        requestAnimationFrame(() => {
            renderPending = false;
            renderAll();
        });
    }
}

function applyEvent(event) {
    if (!S.run || event.seq <= S.run.seq) return;
    S.run.seq = event.seq;
    const p = event.payload,
        m = p.model_index != null ? S.run.models[p.model_index] : null;
    if (m) {
        if (event.type === 'model_started') m.status = 'running';
        if (event.type === 'region_queued' || event.type === 'region_started') m.regions[p.region.id] = {
            ...m.regions[p.region.id],
            ...p,
            phase: event.type === 'region_started' ? 'processing' : 'queued'
        };
        if (event.type === 'region_finished') {
            const r = p.observation;
            m.regions[r.region.id] = {
                ...m.regions[r.region.id],
                ...r,
                phase: 'done'
            };
        }
        if (event.type === 'region_resolved' && m.regions[p.region_id]) m.regions[p.region_id].resolution = p.resolution;
        if (event.type === 'model_finished') {
            m.status = p.summary.stop_reason === 'cancelled' ? 'cancelled' : 'completed';
            m.summary = p.summary;
        }
    }
    if (event.type === 'run_stopping') S.run.status = 'stopping';
    if (event.type === 'run_finished' || event.type === 'run_error') {
        S.run.status = event.type === 'run_error' ? 'failed' : p.status;
        S.run.finished_at = event.at;
        S.stream?.close();
        if (event.type === 'run_error') notice(p.message, true);
    }
    if (event.type === 'review_updated') S.run.review = p.review;
    scheduleRender();
}

function acceptSnapshot(snapshot) {
    // A completion event can beat a slower stop/reconnect response.
    if (S.run?.id === snapshot.id && snapshot.seq >= S.run.seq) {
        S.run = snapshot;
        renderAll();
    }
}

function watch() {
    S.stream?.close();
    if (!running()) return;
    const id = S.run.id,
        stream = new EventSource(`/api/runs/${encodeURIComponent(id)}/events?since=${S.run.seq}`);
    S.stream = stream;
    stream.onmessage = message => {
        if (S.run?.id === id) {
            try {
                applyEvent(JSON.parse(message.data));
            } catch {
                notice('Cannot read a live update. Reopen this run from history.', true);
            }
        }
    };
    stream.onerror = async () => {
        if (S.run?.id !== id || !running()) {
            stream.close();
            return;
        }
        try {
            const snapshot = await api(`/api/runs/${encodeURIComponent(id)}`);
            acceptSnapshot(snapshot);
            if (!running()) stream.close();
        } catch {
            notice('Connection lost. Reconnecting…', true);
        }
    };
}

function applyConfig(run) {
    const c = run.config;
    $('strategy').value = c.strategy;
    $('reasoning-effort').value = c.reasoning_effort || 'low';
    for (const [id, key] of Object.entries(fields))
        if (c[key] != null) $(id).value = c[key];
    $('overlap').value = Math.round(c.overlap * 100);
    for (const [id, key] of Object.entries({
            'explore-negatives': 'explore_negatives',
            'all-candidates': 'all_candidates',
            'structured': 'structured'
        })) $(id).checked = !!c[key];
    S.models = run.models.map(m => m.model);
    S.choices = [...new Set([...S.choices, ...S.models])];
    renderChoices();
    renderConfig();
}
async function loadRun(id) {
    const run = await api(`/api/runs/${encodeURIComponent(id)}`);
    S.stream?.close();
    S.run = run;
    S.selected = null;
    S.modelIndex = 0;
    S.mark = false;
    S.preview = [];
    applyConfig(run);
    setImage(run.image);
    notice(run.error || '', !!run.error);
    renderAll();
    watch();
    try {
        localStorage.setItem('waldofinder:last-run', id);
    } catch {}
}
async function start() {
    if (busy() || !S.image) return;
    S.loading = true;
    notice();
    renderControls();
    try {
        const run = await api('/api/runs', config());
        S.stream?.close();
        S.run = run;
        S.selected = null;
        S.modelIndex = 0;
        S.mark = false;
        S.loading = false;
        setImage(run.image);
        applyConfig(run);
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
async function review(value) {
    if (!S.run || !selected() || S.reviewPending) return;
    const id = S.run.id,
        index = S.modelIndex,
        region = S.selected;
    S.reviewPending = true;
    renderReview();
    try {
        const saved = await api(`/api/runs/${encodeURIComponent(id)}/review`, {
            label: {
                model_index: index,
                region_id: region,
                verdict: value
            }
        });
        if (S.run?.id === id) S.run.review = saved;
    } catch (error) {
        notice(error.message, true);
    } finally {
        S.reviewPending = false;
        renderAll();
    }
}
async function refreshModels() {
    S.catalogReady = false;
    renderControls();
    $('catalog-status').textContent = 'Loading catalog…';
    try {
        const data = await api('/api/models');
        S.catalog = data.models;
        S.catalogReady = true;
        $('catalog-status').textContent = `${data.models.length} vision models · 2026`;
        $('model-catalog').innerHTML = data.models.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
    } catch (error) {
        $('catalog-status').textContent = 'Catalog unavailable';
        notice(error.message, true);
    }
    renderControls();
}

function resetRun() {
    S.stream?.close();
    S.run = null;
    S.selected = null;
    S.mark = false;
    S.preview = [];
    try {
        localStorage.removeItem('waldofinder:last-run');
    } catch {}
}
$('configure-button').addEventListener('click', () => {
    configBefore = config();
    $('config-error').hidden = true;
    renderConfig();
    $('config-dialog').showModal();
});
$('config-form').addEventListener('input', renderConfig);
$('config-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy()) {
        $('config-dialog').close();
        return;
    }
    if (!S.models.length) {
        $('config-error').textContent = 'Select at least one model.';
        $('config-error').hidden = false;
        return;
    }
    // Validate and prepare the exact preview before replacing a saved run's view.
    try {
        const data = await api('/api/preview', config());
        resetRun();
        S.preview = data.regions;
        configBefore = null;
        $('config-dialog').close();
        notice();
        renderAll();
    } catch (error) {
        $('config-error').textContent = error.message;
        $('config-error').hidden = false;
    }
});
$('refresh-models').addEventListener('click', refreshModels);
$('add-model').addEventListener('click', () => {
    const id = $('custom-model').value.trim();
    if (!S.catalog.some(m => m.id === id) || S.models.length >= 4) {
        $('config-error').textContent = 'Choose a 2026 vision model; four models maximum.';
        $('config-error').hidden = false;
        return;
    }
    S.choices = [...new Set([...S.choices, id])];
    S.models = [...new Set([...S.models, id])];
    $('custom-model').value = '';
    renderChoices();
    renderConfig();
});
$('start-button').addEventListener('click', start);
$('stop-button').addEventListener('click', async () => {
    try {
        const id = S.run.id;
        acceptSnapshot(await api(`/api/runs/${encodeURIComponent(id)}/stop`, {}));
    } catch (error) {
        notice(error.message, true);
    }
});
$('upload-button').addEventListener('click', () => $('image-file').click());
$('image-file').addEventListener('change', async () => {
    const file = $('image-file').files[0];
    if (!file) return;
    try {
        const response = await fetch('/api/images', {
            method: 'POST',
            headers: {
                'X-Waldo-Token': S.token,
                'X-Filename': encodeURIComponent(file.name)
            },
            body: file
        });
        const image = await response.json();
        if (!response.ok) throw Error(image.error || 'Upload failed.');
        resetRun();
        setImage(image);
        notice();
        await preview();
    } catch (error) {
        notice(error.message, true);
    }
    $('image-file').value = '';
});

function inspect(id, index) {
    S.modelIndex = index;
    const m = models()[index],
        r = recordFor(m, {
            id
        });
    S.selected = r?.region.id || id;
    if (!$('review-dialog').open) $('review-dialog').showModal();
    renderAll();
}
async function saveTarget(target) {
    const id = S.run?.id;
    if (!id) return;
    try {
        const saved = await api(`/api/runs/${encodeURIComponent(id)}/review`, {
            target
        });
        if (S.run?.id === id) S.run.review = saved;
        S.mark = false;
        renderAll();
    } catch (error) {
        notice(error.message, true);
    }
}
$('overlay').addEventListener('click', event => {
    if (S.mark) {
        const box = $('overlay').getBoundingClientRect();
        saveTarget([Math.min(S.image.width - 1, Math.max(0, Math.floor((event.clientX - box.left) / box.width * S.image.width))), Math.min(S.image.height - 1, Math.max(0, Math.floor((event.clientY - box.top) / box.height * S.image.height)))]);
        return;
    }
    const target = event.target.closest('[data-region]');
    if (target) inspect(target.dataset.region, Number(target.dataset.model));
});
$('overlay').addEventListener('keydown', event => {
    const target = event.target.closest('[data-region]');
    if (target && ['Enter', ' '].includes(event.key)) {
        event.preventDefault();
        inspect(target.dataset.region, Number(target.dataset.model));
    }
});
$('review-model').addEventListener('change', () => {
    S.modelIndex = Number($('review-model').value);
    const r = recordFor(models()[S.modelIndex], {
        id: S.selected || ''
    });
    S.selected = r?.region.id || null;
    renderReview();
});
$('review-region').addEventListener('change', () => {
    S.selected = $('review-region').value;
    renderAll();
});
$('mark-target').addEventListener('click', () => {
    S.mark = !S.mark;
    renderAll();
});
$('clear-target').addEventListener('click', () => saveTarget(null));
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        S.mark = false;
        renderAll();
    }
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
document.querySelectorAll('[data-verdict]').forEach(button => button.addEventListener('click', () => review(button.dataset.verdict)));
$('clear-label').addEventListener('click', () => review('clear'));
$('history-button').addEventListener('click', async () => {
    try {
        const data = await api('/api/runs');
        $('history-list').innerHTML = data.runs.length ? data.runs.map(run => `<button class="history-row" data-run="${esc(run.id)}"><img src="${esc(run.image.url)}" alt="Saved scene"><div><strong>${esc(run.config.strategy==='grid'?`${run.config.tiles} regions`:'Binary partition')}</strong><small>${esc(run.models.map(nameOf).join(' · '))}</small><small>${run.reference?'Visual reference + occlusion':'Text only'} · ${esc(run.image_detail || 'auto')} detail · ${esc(run.config.reasoning_effort || 'low')} effort · ${esc(run.config.max_tokens)} tokens</small><small>${esc(new Date(run.created_at).toLocaleString())}</small></div><span>${esc(run.status)}</span></button>`).join('') : '<p class="subtle">No saved runs.</p>';
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
$('export-button').addEventListener('click', async () => {
    try {
        const snapshot = await api(`/api/runs/${encodeURIComponent(S.run.id)}`),
            blob = new Blob([JSON.stringify(snapshot, null, 2)], {
                type: 'application/json'
            }),
            url = URL.createObjectURL(blob),
            link = document.createElement('a');
        link.href = url;
        link.download = `${snapshot.id}.json`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
        notice(error.message, true);
    }
});
new ResizeObserver(() => {
    fitImage();
    scheduleRender();
}).observe($('scene-viewport'));
$('scene-image').addEventListener('load', scheduleRender);
async function init() {
    renderChoices();
    renderConfig();
    renderAll();
    try {
        const boot = await api('/api/bootstrap');
        S.token = boot.token;
        S.referenceReady = !!boot.reference;
        if (boot.reference) {
            $('reference-image').src = boot.reference.url;
            $('reference-image').hidden = false;
            $('prompt-preview').textContent = boot.prompt;
        }
        if (boot.sample) setImage(boot.sample);
        let last;
        try {
            last = localStorage.getItem('waldofinder:last-run');
        } catch {}
        const active = boot.history.find(run => ['running', 'queued', 'stopping'].includes(run.status));
        if (active) await loadRun(active.id);
        else if (last && boot.history.some(run => run.id === last)) await loadRun(last);
        else await preview();
        renderAll();
        if (!S.referenceReady) notice('Waldo reference missing. Restart the server with --reference /path/to/waldo.png.', true);
        refreshModels();
    } catch (error) {
        notice(error.message, true);
    }
}
init();
$('config-dialog').addEventListener('close', () => {
    if (!configBefore) return;
    applyConfig({
        config: configBefore,
        models: configBefore.models.map(model => ({
            model
        }))
    });
    configBefore = null;
    renderControls();
});
