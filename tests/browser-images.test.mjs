import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const app = readFileSync(new URL('../src/waldofinder/static/app.js', import.meta.url), 'utf8');
const imageFunctions = app.slice(app.indexOf('function fitImage()'), app.indexOf('async function preview()'));
const cropFunctions = app.slice(app.indexOf('function originalCropSource()'), app.indexOf('function renderReview()'));
const tick = () => new Promise(resolve => setImmediate(resolve));
const sample = () => ({url: '/sample.jpg', width: 3000, height: 1926,
    display: {url: '/display.webp', srcset: '/display.webp 1440w, /sample.jpg 3000w', sizes: '100vw'}});

function fixture() {
    const nodes = new Map(), images = [], draws = [], notices = [], state = {};
    const node = id => {
        if (!nodes.has(id)) nodes.set(id, {style: {}, attrs: {}, clientWidth: 1200, clientHeight: 800,
            setAttribute(k, v) { this.attrs[k] = v; },
            getAttribute(k) { return k === 'src' ? this.src : this.attrs[k]; },
            removeAttribute(k) { delete this[k]; delete this.attrs[k]; },
            showModal() { this.open = true; }});
        return nodes.get(id);
    };
    let renders = 0;
    class Source {
        constructor() { images.push(this); }
        decode() { return new Promise((yes, no) => { this.finish = yes; this.fail = no; }); }
    }
    const context = vm.createContext({S: state, cropSourceState: null, Image: Source,
        $: node, getComputedStyle: () => ({paddingLeft: '12'}),
        renderReview: () => { renders++; }, notice: message => notices.push(message),
        document: {createElement: () => ({getContext: () => ({drawImage: (...args) => draws.push(args)}),
            toDataURL: () => 'data:image/png;base64,exact-crop'})},
    });
    new vm.Script(imageFunctions + '\n' + cropFunctions).runInContext(context);
    return {context, state, images, draws, notices, node, renders: () => renders};
}

test('display selection leaves source identity, original geometry and upload behaviour intact', () => {
    const f = fixture(), image = sample();
    f.context.setImage(image);
    assert.equal(f.state.image, image);
    assert.equal(f.node('scene-image').src, '/display.webp');
    assert.equal(f.node('overlay').attrs.viewBox, '0 0 3000 1926');
    assert.equal(f.node('image-frame').style.width, '1176px');
    assert.equal(f.images.length, 0, 'startup must not eagerly download a second source');
    f.context.setImage({url: 'data:image/png;base64,upload', width: 600, height: 400});
    assert.equal(f.node('scene-image').srcset, undefined);
    assert.equal(f.node('scene-image').sizes, undefined);
    assert.equal(f.node('scene-image').src, 'data:image/png;base64,upload');
});

test('crop waits for original pixels and preserves exact bounds rather than drawing the derivative', async () => {
    const f = fixture(); f.context.setImage(sample());
    const record = {region: {box: [0, 0, 1080, 693]}};
    assert.equal(f.context.previewCrop(record), '');
    assert.equal(f.draws.length, 0);
    assert.equal(f.images[0].src, '/sample.jpg');
    f.images[0].naturalWidth = 3000; f.images[0].naturalHeight = 1926;
    f.images[0].finish(); await tick();
    assert.equal(f.renders(), 1);
    assert.equal(f.context.previewCrop(record), 'data:image/png;base64,exact-crop');
    assert.equal(f.draws[0][0], f.images[0]);
    assert.deepEqual(f.draws[0].slice(1), [0, 0, 1080, 693, 0, 0, 1080, 693]);
    f.context.previewCrop({region: {box: [2990, 1916, 3000, 1926]}});
    assert.deepEqual(f.draws[1].slice(1), [2990, 1916, 10, 10, 0, 0, 10, 10]);
    assert.equal(f.images.length, 1);
});

test('failed or dimension-mismatched originals never become incorrect crops or retry automatically', async () => {
    for (const fail of [true, false]) {
        const f = fixture(); f.context.setImage(sample()); f.context.originalCropSource();
        if (fail) f.images[0].fail(Error('Unavailable'));
        else { f.images[0].naturalWidth = 1440; f.images[0].naturalHeight = 924; f.images[0].finish(); }
        await tick();
        assert.equal(f.context.originalCropSource(), null);
        assert.equal(f.notices.length, 1);
        assert.equal(f.images.length, 1);
        assert.equal(f.renders(), 1, 'the open review must update its failure status');
    }
});

test('a late decode cannot overwrite or report errors for a subsequently selected image', async () => {
    const f = fixture(); f.context.setImage(sample()); f.context.originalCropSource();
    f.context.setImage({url: '/other.png', width: 20, height: 10});
    f.images[0].fail(Error('Old image failed')); await tick();
    assert.equal(f.notices.length, 0); assert.equal(f.renders(), 0);
    assert.equal(f.node('scene-image').src, '/other.png');
});

test('failed display falls back to the original once, without a responsive reload loop', () => {
    const f = fixture(); f.context.setImage(sample()); f.context.restoreOriginalDisplay();
    assert.equal(f.node('scene-image').src, '/sample.jpg');
    assert.equal(f.node('scene-image').srcset, undefined);
    f.context.restoreOriginalDisplay();
    assert.equal(f.node('scene-image').src, '/sample.jpg');
});

test('explicit crop retry clears its own failure notice while preserving unrelated errors', () => {
    const inspect = app.slice(app.indexOf('function inspect('), app.indexOf('async function saveTarget('));
    for (const currentMessage of ['Original unavailable', 'A different request failed']) {
        const f = fixture(); f.context.setImage(sample());
        Object.assign(f.context, {models: () => [], recordFor: () => null, renderAll() {}});
        f.node('message').textContent = currentMessage;
        new vm.Script("cropSourceState={url:'/sample.jpg',error:true,errorMessage:'Original unavailable'};" + inspect).runInContext(f.context);
        f.context.inspect('root', 0);
        assert.equal(f.node('review-dialog').open, true);
        assert.equal(f.notices.length, currentMessage === 'Original unavailable' ? 1 : 0);
        assert.equal(f.context.originalCropSource(), null);
        assert.equal(f.images.length, 1, 'the explicit action allows one new source attempt');
    }
});

test('hosted search fetches unchanged original bytes despite attached display metadata', async () => {
    const source = readFileSync(new URL('../src/waldofinder/static/hosted.js', import.meta.url), 'utf8');
    const fn = source.slice(source.indexOf('export async function sourceData'), source.indexOf('export async function* updates')).replace('export ', '');
    const requests = [], raw = new Uint8Array([255, 216, 255, 224, 1, 2, 3]);
    const context = vm.createContext({
        fetch: async url => { requests.push(url); return {ok: true, blob: async () => raw}; },
        File: class { constructor(parts) { this.parts = parts; } },
        imageFile: async file => ({url: file.parts[0]}),
    });
    new vm.Script(fn).runInContext(context);
    assert.equal(await context.sourceData(sample()), raw);
    assert.deepEqual(requests, ['/sample.jpg']);
    assert.equal(await context.sourceData({url: 'data:image/png;base64,unchanged', display: sample().display}), 'data:image/png;base64,unchanged');
    assert.equal(requests.length, 1);
});
