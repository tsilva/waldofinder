import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const app = readFileSync(new URL('../src/waldofinder/static/app.js', import.meta.url), 'utf8');
const start = app.indexOf('async function init() {');
const end = app.indexOf('\ninit();', start);
assert.ok(start >= 0 && end > start);
const original = app.slice(start, end);
assert.equal(original.split("import('./hosted.js')").length, 2);
// Stub the module dependency; execute the actual startup function unchanged otherwise.
const startup = original.replace("import('./hosted.js')", '__loadHosted()');
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return {promise, resolve, reject};
};

function fixture({marker = true, last = null, storageThrows = false} = {}) {
    const boot = deferred(), module = deferred(), history = deferred(), calls = [];
    const elements = new Map();
    const state = {};
    const hosted = {history: () => { calls.push('history'); return history.promise; }};
    const context = vm.createContext({
        S: state,
        document: {querySelector: () => marker ? {} : null},
        localStorage: {getItem: () => {
            if (storageThrows) throw Error('Storage denied');
            return last;
        }},
        $: id => {
            if (!elements.has(id)) elements.set(id, {replaceChildren() {}});
            return elements.get(id);
        },
        api: path => { calls.push(path); return boot.promise; },
        __loadHosted: () => { calls.push('module'); return module.promise; },
        renderChoices() {}, renderConfig() {}, renderAll() {},
        setImage: image => { state.image = image; calls.push('image:' + image.id); },
        loadRun: async id => { calls.push('restore:' + id); },
        preview: async () => { calls.push('preview'); },
        refreshModels: () => { calls.push('models'); },
        notice: message => { calls.push('error:' + message); },
    });
    new vm.Script(startup).runInContext(context);
    const run = context.init();
    return {boot, module, history, hosted, calls, state, run};
}

const payload = (hosted = true) => ({hosted, token: hosted ? '' : 'local-token',
    prompt: 'grid', localization_prompt: 'bbox', reference: {url: '/fixture.jpg'},
    history: [], sample: {id: 'sample'}});

test('starts both hosted reads and waits for history before selecting an image', async () => {
    const f = fixture();
    assert.deepEqual(f.calls, ['/bootstrap.json', 'module']);
    f.module.resolve(f.hosted); await tick();
    assert.ok(f.calls.includes('history'));
    f.boot.resolve(payload()); await tick();
    assert.equal(f.state.image, undefined);
    f.history.resolve([]); await f.run;
    assert.equal(f.state.hosted, f.hosted);
    assert.deepEqual(f.calls.slice(-3), ['image:sample', 'preview', 'models']);
});

test('history may finish first without selecting an image before bootstrap', async () => {
    const f = fixture();
    f.module.resolve(f.hosted); f.history.resolve([]); await tick();
    assert.equal(f.state.image, undefined);
    f.boot.resolve(payload()); await f.run;
    assert.equal(f.state.image.id, 'sample');
});

for (const [label, history, last, expected] of [
    ['active run wins over last run', [{id: 'active', status: 'running'}, {id: 'last', status: 'done'}], 'last', 'restore:active'],
    ['saved last run restores', [{id: 'last', status: 'done'}], 'last', 'restore:last'],
    ['missing saved run uses sample', [], 'missing', 'preview'],
]) {
    test(label, async () => {
        const f = fixture({last});
        f.module.resolve(f.hosted); f.history.resolve(history); f.boot.resolve(payload());
        await f.run;
        assert.deepEqual(f.calls.slice(-3), ['image:sample', expected, 'models']);
    });
}

test('denied localStorage retains the sample fallback', async () => {
    const f = fixture({storageThrows: true});
    f.module.resolve(f.hosted); f.history.resolve([]); f.boot.resolve(payload());
    await f.run;
    assert.deepEqual(f.calls.slice(-3), ['image:sample', 'preview', 'models']);
});

test('local bootstrap keeps its token and never loads hosted storage', async () => {
    const f = fixture({marker: false});
    f.boot.resolve(payload(false)); await f.run;
    assert.equal(f.state.token, 'local-token');
    assert.ok(f.calls.includes('/api/bootstrap'));
    assert.ok(!f.calls.includes('module'));
});

test('legacy hosted response without the static marker still loads history', async () => {
    const f = fixture({marker: false});
    assert.deepEqual(f.calls, ['/api/bootstrap']);
    f.boot.resolve(payload()); await tick();
    assert.ok(f.calls.includes('module'));
    f.module.resolve(f.hosted); f.history.resolve([]); await f.run;
    assert.equal(f.state.hosted, f.hosted);
});

test('early history failure is handled while bootstrap is still pending', async () => {
    const f = fixture();
    f.module.resolve(f.hosted); await tick();
    f.history.reject(Error('History unavailable')); await f.run;
    assert.ok(f.calls.includes('error:History unavailable'));
    assert.equal(f.state.image, undefined);
    f.boot.resolve(payload());
});

test('bootstrap failure also handles a later storage failure', async () => {
    const f = fixture();
    f.boot.reject(Error('Bootstrap unavailable')); await f.run;
    f.module.resolve(f.hosted); await tick();
    f.history.reject(Error('History unavailable')); await tick();
    assert.ok(f.calls.includes('error:Bootstrap unavailable'));
    assert.equal(f.state.image, undefined);
});
