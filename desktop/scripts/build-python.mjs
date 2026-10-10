import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const result = spawnSync('uv', [
  'run', '--project', 'server/services/checker', '--frozen', '--group', 'packaging',
  'pyinstaller', '--clean', '--noconfirm',
  '--distpath', 'desktop/python/dist', '--workpath', 'desktop/python/build',
  'desktop/python/checker.spec',
], { cwd: root, stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
