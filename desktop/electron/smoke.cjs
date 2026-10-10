const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');

async function readJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  assert.equal(response.status, 200, `${url}: HTTP ${response.status}`);
  return response.json();
}

async function runSmoke({ window, origin, paths, fixtures }) {
  assert.ok(fixtures, '--smoke-fixtures is required');
  assert.ok(existsSync(path.join(paths.data, 'history.sqlite3')), 'SQLite history is missing');
  const renderer = await window.webContents.executeJavaScript(`({ title: document.title, text: document.querySelector('#app').innerText, node: typeof require })`);
  assert.ok(renderer.text.includes('检测'), 'Vue application did not render');
  assert.equal(renderer.node, 'undefined', 'Renderer should not expose Node.js');
  const previous = await readJson(`${origin}/api/v1/checker/history`);
  const runs = [];
  for (const [label, names, reference] of [
    ['docx-reference-images', ['甲.docx', '乙.docx'], '招标文件.docx'],
    ['pdf-text-and-chinese-ocr', ['文字.pdf', '扫描.pdf'], null],
  ]) {
    const inputs = names.map((name) => ({ name, bytes: readFileSync(path.join(fixtures, name)).toString('base64') }));
    const tender = reference ? { name: reference, bytes: readFileSync(path.join(fixtures, reference)).toString('base64') } : null;
    const submitted = await window.webContents.executeJavaScript(`(async () => {
      const form = new FormData();
      const append = (key, input) => form.append(key, new File([Uint8Array.from(atob(input.bytes), c => c.charCodeAt(0))], input.name));
      for (const input of ${JSON.stringify(inputs)}) append('files', input);
      const tender = ${JSON.stringify(tender)};
      if (tender) append('reference', tender);
      form.append('settings', '{}');
      const response = await fetch('/api/v1/checker/jobs', { method: 'POST', body: form });
      return { status: response.status, body: await response.json() };
    })()`);
    assert.equal(submitted.status, 202, JSON.stringify(submitted));
    const id = submitted.body.id;
    const deadline = Date.now() + 180000;
    let status;
    do {
      status = await readJson(`${origin}/api/v1/checker/jobs/${id}`);
      assert.notEqual(status.state, 'failed', status.error || status.message);
      if (status.state === 'completed') break;
      await delay(250);
    } while (Date.now() < deadline);
    assert.equal(status.state, 'completed', 'Analysis timed out');
    const result = await readJson(`${origin}/api/v1/checker/jobs/${id}/result`);
    assert.equal(result.documents.length, 2);
    assert.equal(result.pairs.length, 1);
    if (reference) {
      assert.ok(result.pairs[0].similarity > 0, 'Real text comparison did not run');
      assert.equal(result.pairs[0].exact_image_count, 1);
      assert.equal(result.reference.name, reference);
      assert.ok(result.documents.every((document) => document.excluded_reference_chars > 0));
    } else {
      assert.ok(result.documents[0].chars > 20, 'PDF text extraction failed');
      const scan = result.documents.find((document) => document.name === '扫描.pdf');
      assert.equal(scan.ocr_pages, 1, 'Native PDFium/OCR path did not run');
      assert.ok(scan.chars > 20, 'OCR extracted no usable text');
      assert.match(scan.content.map((block) => block.text).join(''), /[\u4e00-\u9fff]/, 'Chinese OCR language model did not work');
    }
    assert.ok(!existsSync(path.join(paths.data, id, 'source-0.docx')) && !existsSync(path.join(paths.data, id, 'source-0.pdf')), 'Uploads should be cleaned after analysis');
    await window.loadURL(`${origin}/jobs/${id}`);
    await window.webContents.executeJavaScript('new Promise(resolve => setTimeout(resolve, 500))');
    assert.ok((await window.webContents.executeJavaScript("document.querySelector('#app').innerText")).includes('检测'), 'Report route did not render');
    runs.push({ label, id, documents: result.documents.map(({ name, chars, ocr_pages }) => ({ name, chars, ocr_pages })) });
  }
  const history = await readJson(`${origin}/api/v1/checker/history`);
  assert.ok(runs.every(({ id }) => history.items.some((item) => item.id === id)));
  // A second executable run must read every report produced by the first run.
  for (const item of previous.items.filter((item) => item.state === 'completed')) {
    await readJson(`${origin}/api/v1/checker/jobs/${item.id}/result`);
  }
  await window.loadURL(`${origin}/history`);
  assert.ok((await window.webContents.executeJavaScript("document.querySelector('#app').innerText")).includes('历史'));
  return { ok: true, renderer: renderer.title, bundledBackend: paths.command, historyCount: history.items.length, restoredReports: previous.items.length, runs };
}

module.exports = { runSmoke };
