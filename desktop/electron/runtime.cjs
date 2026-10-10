const { spawn } = require('node:child_process');
const { existsSync, mkdirSync, openSync, closeSync, readFileSync, rmSync } = require('node:fs');
const path = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');

function runtimePaths({ packaged, resourcesPath, appPath, userData }) {
  const root = path.resolve(appPath, '..');
  return {
    command: packaged
      ? path.join(resourcesPath, 'backend', process.platform === 'win32' ? 'checker-backend.exe' : 'checker-backend')
      : 'uv',
    prefix: packaged ? [] : ['run', '--project', path.join(root, 'server/services/checker'), '--frozen', 'python', '-m', 'checker.desktop'],
    web: packaged ? path.join(resourcesPath, 'web') : path.join(root, 'web/app/dist'),
    ocr: packaged ? path.join(resourcesPath, 'tesseract') : path.join(appPath, '.cache/tesseract'),
    data: path.join(userData, 'jobs'),
    ready: path.join(userData, 'backend-ready.json'),
    log: path.join(userData, 'logs', 'backend.log'),
    cwd: packaged ? path.join(resourcesPath, 'backend') : root,
  };
}

function runtimeEnvironment(paths, packaged) {
  const env = { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' };
  if (packaged) {
    delete env.PYTHONHOME;
    delete env.PYTHONPATH;
  }
  const executable = path.join(paths.ocr, process.platform === 'win32' ? 'tesseract.exe' : 'tesseract');
  if (existsSync(executable)) {
    env.TESSERACT_CMD = executable;
    env.TESSDATA_PREFIX = path.join(paths.ocr, 'tessdata');
  }
  return env;
}

async function waitForReady(file, child, timeoutMs = 60000) {
  if (!child.pid) throw new Error('无法启动 Python 服务，请检查随包后端和日志');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) throw new Error('Python 服务提前退出');
    try {
      const ready = JSON.parse(readFileSync(file, 'utf8'));
      if (ready.host !== '127.0.0.1' || ready.pid !== child.pid || !Number.isInteger(ready.port) || ready.port < 1 || ready.port > 65535) {
        throw new Error('后端启动信息无效');
      }
      const origin = `http://127.0.0.1:${ready.port}`;
      const response = await fetch(`${origin}/api/v1/checker/health`, { signal: AbortSignal.timeout(2000) });
      if (response.ok && (await response.json()).status === 'ok') return origin;
    } catch (error) {
      if (error.message === '后端启动信息无效') throw error;
    }
    await delay(100);
  }
  throw new Error('Python 服务启动超时');
}

async function stopChild(child) {
  if (!child.pid) return;
  if (process.platform === 'win32') {
    if (child.exitCode !== null || child.signalCode !== null) return;
    await new Promise((resolve) => {
      const taskkill = spawn(path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe'), ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true });
      taskkill.once('error', resolve);
      taskkill.once('exit', resolve);
    });
    return;
  }
  const killGroup = (signal) => {
    try { process.kill(-child.pid, signal); } catch (error) { if (error.code !== 'ESRCH') throw error; }
  };
  killGroup('SIGTERM');
  const deadline = Date.now() + 5000;
  while (child.exitCode === null && child.signalCode === null && Date.now() < deadline) await delay(50);
  // OCR children share the group and may outlive their Python parent.
  killGroup('SIGKILL');
}

class BackendRuntime {
  constructor(paths, packaged, onFailure) {
    this.paths = paths;
    this.packaged = packaged;
    this.onFailure = onFailure;
    this.children = [];
    this.stopping = false;
  }

  launch(mode, extra = []) {
    const child = spawn(this.paths.command, [
      ...this.paths.prefix, mode, '--data-dir', this.paths.data, '--parent-pid', String(process.pid), ...extra,
    ], {
      cwd: this.paths.cwd,
      env: runtimeEnvironment(this.paths, this.packaged),
      stdio: ['ignore', this.logFd, this.logFd],
      windowsHide: true,
      detached: process.platform !== 'win32',
    });
    this.children.push(child);
    child.once('error', (error) => { if (!this.stopping) this.onFailure(error); });
    child.once('exit', (code, signal) => {
      if (!this.stopping) this.onFailure(new Error(`${mode} 进程已退出 (${signal || code})`));
    });
    return child;
  }

  async start() {
    if (this.stopping) throw new Error('应用已关闭');
    mkdirSync(path.dirname(this.paths.log), { recursive: true });
    mkdirSync(this.paths.data, { recursive: true });
    rmSync(this.paths.ready, { force: true });
    this.logFd = openSync(this.paths.log, 'a');
    const api = this.launch('serve', ['--ready-file', this.paths.ready, '--web-dir', this.paths.web]);
    const origin = await waitForReady(this.paths.ready, api);
    if (this.stopping) throw new Error('应用已关闭');
    this.launch('worker');
    return origin;
  }

  async stop() {
    if (this.stopPromise) return this.stopPromise;
    this.stopping = true;
    this.stopPromise = (async () => {
      await Promise.allSettled(this.children.map(stopChild));
      if (this.logFd !== undefined) closeSync(this.logFd);
      rmSync(this.paths.ready, { force: true });
    })();
    return this.stopPromise;
  }
}

module.exports = { BackendRuntime, runtimePaths, runtimeEnvironment, waitForReady };
