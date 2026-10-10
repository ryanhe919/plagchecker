const { app, BrowserWindow, dialog, Menu, session } = require('electron');
const { mkdirSync, writeFileSync, readFileSync, existsSync } = require('node:fs');
const path = require('node:path');
const { BackendRuntime, runtimePaths } = require('./runtime.cjs');

const argument = (name) => process.argv.find((value) => value.startsWith(`${name}=`))?.slice(name.length + 1);
const smokeReport = argument('--smoke-test');
const smokeFixtures = argument('--smoke-fixtures');
app.setName('标衡');
app.setPath('userData', argument('--data-dir') || path.join(app.getPath('appData'), 'BiaoHeng'));

let runtime;
let window;
let stopping = false;
let failureHandled = false;
let exitCode = 0;

async function finish(code = 0) {
  if (stopping) return;
  stopping = true;
  exitCode = code;
  await runtime?.stop();
  app.exit(exitCode);
}

async function fail(error) {
  if (failureHandled || stopping) return;
  failureHandled = true;
  console.error(error);
  if (smokeReport) {
    mkdirSync(path.dirname(smokeReport), { recursive: true });
    const log = runtime?.paths.log;
    writeFileSync(smokeReport, JSON.stringify({
      ok: false, error: error.stack || String(error),
      backendLog: log && existsSync(log) ? readFileSync(log, 'utf8').slice(-16000) : '',
    }, null, 2));
  } else {
    dialog.showErrorBox('标衡启动失败', `${error.message}\n\n诊断日志：${path.join(app.getPath('userData'), 'logs', 'backend.log')}`);
  }
  await finish(1);
}

function restrictSession(origin) {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    const url = new URL(details.url);
    callback({ cancel: !['data:', 'blob:', 'devtools:'].includes(url.protocol) && url.origin !== origin });
  });
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({ responseHeaders: {
      ...details.responseHeaders,
      'Content-Security-Policy': ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"],
    } });
  });
  session.defaultSession.on('will-download', (_event, item) => {
    item.setSaveDialogOptions({ defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) });
  });
}

async function start() {
  const paths = runtimePaths({ packaged: app.isPackaged, resourcesPath: process.resourcesPath, appPath: app.getAppPath(), userData: app.getPath('userData') });
  runtime = new BackendRuntime(paths, app.isPackaged, fail);
  const origin = await runtime.start();
  if (stopping) return;
  restrictSession(origin);
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: '文件', submenu: [{ role: 'quit', label: '退出' }] },
    { label: '编辑', submenu: [{ role: 'undo', label: '撤销' }, { role: 'redo', label: '重做' }, { type: 'separator' }, { role: 'cut', label: '剪切' }, { role: 'copy', label: '复制' }, { role: 'paste', label: '粘贴' }, { role: 'selectAll', label: '全选' }] },
    { label: '视图', submenu: [{ role: 'reload', label: '刷新' }, { role: 'resetZoom', label: '实际大小' }, { role: 'zoomIn', label: '放大' }, { role: 'zoomOut', label: '缩小' }, { role: 'togglefullscreen', label: '全屏' }] },
  ]));
  window = new BrowserWindow({
    width: 1440, height: 960, minWidth: 960, minHeight: 640,
    title: '标衡 · 标书相似性核查', show: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
  window.webContents.on('will-redirect', (event, url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
  window.webContents.on('render-process-gone', (_event, details) => fail(new Error(`界面进程已退出：${details.reason}`)));
  window.on('closed', () => { window = null; });
  await window.loadURL(`${origin}/new`);
  if (stopping || !window || window.isDestroyed()) return;
  if (smokeReport) {
    const { runSmoke } = require('./smoke.cjs');
    const report = await runSmoke({ window, origin, paths, fixtures: smokeFixtures });
    mkdirSync(path.dirname(smokeReport), { recursive: true });
    writeFileSync(smokeReport, JSON.stringify({ ...report, backendPids: runtime.children.map((child) => child.pid) }, null, 2));
    await finish();
  } else {
    window.show();
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.focus(); } });
  app.on('before-quit', (event) => { if (!stopping) { event.preventDefault(); void finish(); } });
  app.on('window-all-closed', () => { void finish(); });
  app.whenReady().then(start).catch(fail);
}
