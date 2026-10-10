const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const { once } = require('node:events');
const { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');
const { BackendRuntime, runtimePaths, runtimeEnvironment, waitForReady } = require('../electron/runtime.cjs');
const resourceCleanups = new WeakMap();

const readyChildSource = String.raw`
  const fs = require('node:fs');
  const http = require('node:http');
  const options = JSON.parse(process.argv[1]);
  if (options.exit) process.exit(options.exit);
  if (options.missing) {
    setInterval(() => {}, 1000);
  } else {
    const server = http.createServer((request, response) => {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ status: options.unhealthy ? 'starting' : 'ok' }));
    });
    server.listen(0, '127.0.0.1', () => {
      const ready = { host: '127.0.0.1', pid: process.pid, port: server.address().port, ...options.ready };
      if (options.partial) fs.writeFileSync(options.file, '{');
      setTimeout(() => fs.writeFileSync(options.file, JSON.stringify(ready)), options.readyDelay || 0);
    });
  }
`;

const runtimeChildSource = String.raw`
  const fs = require('node:fs');
  const path = require('node:path');
  const http = require('node:http');
  const args = process.argv.slice(1);
  const mode = args[0];
  const value = (name) => args[args.indexOf(name) + 1];
  const data = value('--data-dir');
  fs.writeFileSync(path.join(data, mode + '.json'), JSON.stringify({ args, pid: process.pid, env: { PYTHONHOME: process.env.PYTHONHOME, PYTHONPATH: process.env.PYTHONPATH, CHECKER_LAUNCH_TOKEN: process.env.CHECKER_LAUNCH_TOKEN } }));
  if (mode === 'serve') {
    if (args.includes('--with-ocr-child')) {
      const ocr = require('node:child_process').spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
      fs.writeFileSync(path.join(data, 'ocr.pid'), String(ocr.pid));
    }
    const server = http.createServer((request, response) => {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ status: 'ok' }));
    });
    server.listen(0, '127.0.0.1', () => {
      fs.writeFileSync(value('--ready-file'), JSON.stringify({ host: '127.0.0.1', port: server.address().port, pid: process.pid, launch_token: process.env.CHECKER_LAUNCH_TOKEN }));
    });
  } else {
    setInterval(() => {}, 1000);
  }
`;

function temporaryDirectory(t) {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'checker desktop '));
  resourceCleanups.set(t, []);
  t.after(async () => {
    // Close process/log handles before removing the directory, particularly on Windows.
    for (const cleanup of resourceCleanups.get(t).reverse()) await cleanup();
    rmSync(directory, { recursive: true, force: true });
  });
  return directory;
}

function readyChild(t, directory, options = {}) {
  const file = path.join(directory, 'ready.json');
  const child = spawn(process.execPath, ['-e', readyChildSource, JSON.stringify({ ...options, file })], { stdio: 'ignore', windowsHide: true });
  child.on('error', () => {});
  resourceCleanups.get(t).push(async () => {
    if (child.exitCode === null && child.signalCode === null && child.pid) {
      const exited = once(child, 'exit');
      child.kill();
      await exited;
    }
  });
  return { child, file };
}

function testRuntime(t, directory) {
  const paths = {
    command: process.execPath,
    prefix: ['-e', runtimeChildSource, '--'],
    cwd: directory,
    data: path.join(directory, 'jobs'),
    ready: path.join(directory, 'ready.json'),
    log: path.join(directory, 'logs', 'backend.log'),
    web: path.join(directory, 'web assets'),
    ocr: path.join(directory, 'ocr'),
  };
  const failures = [];
  const runtime = new BackendRuntime(paths, true, (error) => failures.push(error));
  resourceCleanups.get(t).push(() => runtime.stop());
  return { runtime, paths, failures };
}

async function waitUntil(predicate, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    assert.ok(Date.now() < deadline, 'Child process did not reach expected state');
    await delay(20);
  }
}

function processExists(pid) {
  try { process.kill(pid, 0); return true; }
  catch (error) {
    if (error.code === 'ESRCH') return false;
    throw error;
  }
}

test('packaged paths use the bundled executable and resources, independent of the current directory', (t) => {
  const directory = temporaryDirectory(t);
  const resourcesPath = path.join(directory, 'installed app', 'resources');
  const userData = path.join(directory, 'user data');
  const paths = runtimePaths({ packaged: true, resourcesPath, appPath: path.join(resourcesPath, 'app.asar'), userData });
  assert.equal(paths.command, path.join(resourcesPath, 'backend', process.platform === 'win32' ? 'checker-backend.exe' : 'checker-backend'));
  assert.deepEqual(paths.prefix, []);
  assert.equal(paths.cwd, path.join(resourcesPath, 'backend'));
  assert.equal(paths.web, path.join(resourcesPath, 'web'));
  assert.equal(paths.ocr, path.join(resourcesPath, 'tesseract'));
  assert.equal(paths.data, path.join(userData, 'jobs'));
  assert.equal(paths.log, path.join(userData, 'logs', 'backend.log'));
  assert.equal(paths.ready, path.join(userData, 'backend-ready.json'));
});

test('development paths locate the source project without changing packaged paths', (t) => {
  const directory = temporaryDirectory(t);
  const paths = runtimePaths({ packaged: false, resourcesPath: 'unused', appPath: path.join(directory, 'desktop'), userData: path.join(directory, 'data') });
  assert.equal(paths.command, 'uv');
  assert.deepEqual(paths.prefix, ['run', '--project', path.join(directory, 'server/services/checker'), '--frozen', 'python', '-m', 'checker.desktop']);
  assert.equal(paths.cwd, directory);
  assert.equal(paths.web, path.join(directory, 'web/app/dist'));
});

test('packaged environment removes external Python paths and selects bundled OCR', (t) => {
  const directory = temporaryDirectory(t);
  const ocr = path.join(directory, 'bundled ocr');
  mkdirSync(ocr);
  const executable = path.join(ocr, process.platform === 'win32' ? 'tesseract.exe' : 'tesseract');
  writeFileSync(executable, 'fixture');
  const previous = { PYTHONHOME: process.env.PYTHONHOME, PYTHONPATH: process.env.PYTHONPATH };
  t.after(() => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  process.env.PYTHONHOME = 'external-python-home';
  process.env.PYTHONPATH = 'external-python-packages';
  const env = runtimeEnvironment({ ocr }, true);
  assert.equal(env.PYTHONHOME, undefined);
  assert.equal(env.PYTHONPATH, undefined);
  assert.equal(env.PYTHONUTF8, '1');
  assert.equal(env.PYTHONUNBUFFERED, '1');
  assert.equal(env.TESSERACT_CMD, executable);
  assert.equal(env.TESSDATA_PREFIX, path.join(ocr, 'tessdata'));
  assert.equal(runtimeEnvironment({ ocr }, false).PYTHONHOME, 'external-python-home');
});

test('readiness requires a live child PID, loopback port and successful health response', async (t) => {
  const directory = temporaryDirectory(t);
  const { child, file } = readyChild(t, directory, { readyDelay: 80, partial: true });
  const origin = await waitForReady(file, child, 5000);
  const ready = JSON.parse(readFileSync(file, 'utf8'));
  assert.equal(ready.pid, child.pid);
  assert.equal(origin, `http://127.0.0.1:${ready.port}`);
  assert.equal((await (await fetch(`${origin}/api/v1/checker/health`)).json()).status, 'ok');
});

test('readiness rejects a stale PID and invalid host or port', async (t) => {
  const invalid = [
    { pid: process.pid },
    { host: '0.0.0.0' },
    { port: 0 },
    { port: 65536 },
    { port: '8080' },
    { port: 8080.5 },
  ];
  for (const ready of invalid) {
    await t.test(JSON.stringify(ready), async (subtest) => {
      const directory = temporaryDirectory(subtest);
      const { child, file } = readyChild(subtest, directory, { ready });
      await assert.rejects(waitForReady(file, child, 5000), /后端启动信息无效/);
    });
  }
});

test('development launcher may report a different positive backend PID with the correct launch token', async (t) => {
  const directory = temporaryDirectory(t);
  const launchToken = randomUUID();
  const { child, file } = readyChild(t, directory, { ready: { pid: process.pid, launch_token: launchToken } });
  const origin = await waitForReady(file, child, 5000, { matchChildPid: false, launchToken });
  const ready = JSON.parse(readFileSync(file, 'utf8'));
  assert.notEqual(ready.pid, child.pid);
  assert.equal(origin, `http://127.0.0.1:${ready.port}`);
});

test('development readiness rejects invalid backend PIDs even with the correct launch token', async (t) => {
  const launchToken = randomUUID();
  for (const pid of [0, -1, '8080', 8080.5]) {
    await t.test(JSON.stringify(pid), async (subtest) => {
      const directory = temporaryDirectory(subtest);
      const { child, file } = readyChild(subtest, directory, { ready: { pid, launch_token: launchToken } });
      await assert.rejects(waitForReady(file, child, 5000, { matchChildPid: false, launchToken }), /后端启动信息无效/);
    });
  }
});

test('readiness rejects missing or incorrect launch tokens for both launcher and packaged PID checks', async (t) => {
  for (const matchChildPid of [false, true]) {
    for (const launch_token of [undefined, randomUUID()]) {
      await t.test(`${matchChildPid ? 'packaged' : 'development'} ${launch_token ? 'incorrect' : 'missing'} token`, async (subtest) => {
        const directory = temporaryDirectory(subtest);
        const { child, file } = readyChild(subtest, directory, { ready: { launch_token } });
        await assert.rejects(waitForReady(file, child, 5000, { matchChildPid, launchToken: randomUUID() }), /后端启动信息无效/);
      });
    }
  }
});

test('readiness fails promptly when the child exits before announcing readiness', async (t) => {
  const directory = temporaryDirectory(t);
  const { child, file } = readyChild(t, directory, { exit: 7 });
  await assert.rejects(waitForReady(file, child, 5000), /提前退出/);
  assert.equal(child.exitCode, 7);
});

test('readiness fails promptly if the backend executable cannot be spawned', async (t) => {
  const directory = temporaryDirectory(t);
  const child = spawn(path.join(directory, 'missing-backend-executable'), [], { stdio: 'ignore', windowsHide: true });
  child.on('error', () => {});
  await assert.rejects(waitForReady(path.join(directory, 'ready.json'), child, 1000), /ENOENT|无法启动|启动失败|提前退出/);
});

test('readiness times out when no readiness file is created', async (t) => {
  const directory = temporaryDirectory(t);
  const { child, file } = readyChild(t, directory, { missing: true });
  await assert.rejects(waitForReady(file, child, 250), /启动超时/);
});

test('readiness times out while the advertised API reports an unhealthy state', async (t) => {
  const directory = temporaryDirectory(t);
  const { child, file } = readyChild(t, directory, { unhealthy: true });
  await assert.rejects(waitForReady(file, child, 400), /启动超时/);
});

test('backend starts API before its worker and stops both processes without a Python installation', async (t) => {
  const directory = temporaryDirectory(t);
  const { runtime, paths, failures } = testRuntime(t, directory);
  writeFileSync(paths.ready, JSON.stringify({ host: '127.0.0.1', pid: -1, port: 12345 }));
  const origin = await runtime.start();
  await waitUntil(() => existsSync(path.join(paths.data, 'worker.json')));
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
  assert.equal(runtime.children.length, 2);
  const serve = JSON.parse(readFileSync(path.join(paths.data, 'serve.json'), 'utf8'));
  const worker = JSON.parse(readFileSync(path.join(paths.data, 'worker.json'), 'utf8'));
  assert.equal(serve.args[0], 'serve');
  assert.equal(worker.args[0], 'worker');
  for (const record of [serve, worker]) {
    assert.ok(record.args.includes('--parent-pid'));
    assert.equal(record.args[record.args.indexOf('--parent-pid') + 1], String(process.pid));
    assert.equal(record.args[record.args.indexOf('--data-dir') + 1], paths.data);
    assert.equal(record.env.PYTHONHOME, undefined);
    assert.equal(record.env.PYTHONPATH, undefined);
    assert.equal(record.env.CHECKER_LAUNCH_TOKEN, runtime.launchToken);
  }
  assert.equal(JSON.parse(readFileSync(paths.ready, 'utf8')).launch_token, runtime.launchToken);
  await Promise.all([runtime.stop(), runtime.stop()]);
  await waitUntil(() => runtime.children.every((child) => child.exitCode !== null || child.signalCode !== null));
  assert.equal(existsSync(paths.ready), false);
  assert.deepEqual(failures, []);
  assert.ok(existsSync(paths.log));
});

test('unexpected backend exit is reported and cleanup still removes readiness', async (t) => {
  const directory = temporaryDirectory(t);
  const { runtime, paths, failures } = testRuntime(t, directory);
  await runtime.start();
  const api = runtime.children[0];
  const exited = once(api, 'exit');
  api.kill();
  await exited;
  assert.ok(failures.some((error) => /serve 进程已退出/.test(error.message)));
  await runtime.stop();
  assert.equal(existsSync(paths.ready), false);
});

test('shutdown after a successful health response prevents a worker from launching', async (t) => {
  const directory = temporaryDirectory(t);
  const { runtime, paths, failures } = testRuntime(t, directory);
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; });
  // Use the actual child's health API, and close the runtime at the await boundary.
  global.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const result = await response.json();
    await runtime.stop();
    return { ok: response.ok, json: async () => result };
  };
  await assert.rejects(runtime.start(), /停止|取消|关闭/);
  assert.equal(runtime.children.length, 1);
  assert.equal(existsSync(path.join(paths.data, 'worker.json')), false);
  assert.equal(existsSync(paths.ready), false);
  assert.deepEqual(failures, []);
});

test('a stopped runtime cannot launch new backend processes', async (t) => {
  const directory = temporaryDirectory(t);
  const { runtime } = testRuntime(t, directory);
  await runtime.stop();
  await assert.rejects(runtime.start(), /停止|取消|关闭/);
  assert.equal(runtime.children.length, 0);
});

test('Unix shutdown removes OCR descendants even after the backend parent exits', { skip: process.platform === 'win32' }, async (t) => {
  const directory = temporaryDirectory(t);
  const { runtime, paths } = testRuntime(t, directory);
  const launch = runtime.launch.bind(runtime);
  runtime.launch = (mode, extra = []) => launch(mode, [...extra, '--with-ocr-child']);
  await runtime.start();
  const ocrPid = Number(readFileSync(path.join(paths.data, 'ocr.pid'), 'utf8'));
  resourceCleanups.get(t).push(async () => {
    if (processExists(ocrPid)) process.kill(ocrPid, 'SIGKILL');
  });
  const api = runtime.children[0];
  const exited = once(api, 'exit');
  api.kill();
  await exited;
  assert.equal(processExists(ocrPid), true, 'Fixture OCR child should survive its crashed parent');
  await runtime.stop();
  await waitUntil(() => !processExists(ocrPid));
});
