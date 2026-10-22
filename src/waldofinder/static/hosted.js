// Visitor-local history. No API keys or other visitors' runs are stored here.
const database = new Promise((resolve, reject) => {
    const request = indexedDB.open('waldofinder-hosted', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('runs', {keyPath: 'id'});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(Error('Browser storage is unavailable.'));
});
export async function saveRun(run) {
    const copy = structuredClone(run), db = await database;
    return new Promise((resolve, reject) => {
        const tx = db.transaction('runs', 'readwrite');
        tx.objectStore('runs').put(copy);
        tx.oncomplete = resolve;
        tx.onerror = () => reject(Error('Could not save browser history. Export this run before closing the tab.'));
    });
}
export async function getRun(id) {
    const db = await database;
    return new Promise((resolve, reject) => {
        const request = db.transaction('runs').objectStore('runs').get(id);
        request.onsuccess = () => request.result ? resolve(request.result) : reject(Error('Run not found in this browser.'));
        request.onerror = () => reject(Error('Could not read browser history.'));
    });
}
export async function history() {
    const db = await database;
    return new Promise((resolve, reject) => {
        const request = db.transaction('runs').objectStore('runs').getAll();
        request.onsuccess = () => resolve(request.result.sort((a,b) => b.created_at.localeCompare(a.created_at)).map(run => ({...run,models:run.models.map(m => m.model)})));
        request.onerror = () => reject(Error('Could not read browser history.'));
    });
}
export async function imageFile(file) {
    if (file.size > 3000000) throw Error('Hosted images must be up to 3 MB. Source pixels are never automatically resized or compressed.');
    if (!['image/jpeg','image/png','image/webp'].includes(file.type)) throw Error('Choose PNG, JPEG or WebP.');
    const url = await new Promise((resolve,reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(Error('Could not read image.'));
        reader.readAsDataURL(file);
    });
    const image = new Image();
    image.src = url;
    await image.decode();
    if (image.naturalWidth * image.naturalHeight > 40000000) throw Error('Choose an image up to 40 megapixels.');
    return {id: crypto.randomUUID(), name: file.name, width: image.naturalWidth, height: image.naturalHeight, url};
}
export async function sourceData(image) {
    if (image.url.startsWith('data:')) return image.url;
    const response = await fetch(image.url);
    if (!response.ok) throw Error('Could not load source image.');
    const file = new File([await response.blob()], 'scene.jpg', {type:'image/jpeg'});
    return (await imageFile(file)).url;
}
export async function* updates(response) {
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let pending = '';
    try {
        while (true) {
            const {value, done} = await reader.read();
            pending += decoder.decode(value || new Uint8Array(), {stream: !done});
            let end;
            while ((end = pending.indexOf('\n')) >= 0) {
                const line = pending.slice(0,end);
                pending = pending.slice(end+1);
                if (line.trim()) yield JSON.parse(line);
            }
            if (done) break;
        }
        if (pending.trim()) yield JSON.parse(pending);
    } finally {
        reader.releaseLock();
    }
}
