import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ mode }) => {
  const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const env = {
    ...loadEnv(mode, projectRoot, ''),
    ...loadEnv(mode, process.cwd(), ''),
    ...process.env,
  };
  const appPort = Number(env.APP_PORT || env.PORT || env.RPC_PORT || 8765);
  const apiPort = Number(env.API_PORT || 8766);
  const apiHostRaw = env.API_HOST || '127.0.0.1';
  const apiHost = apiHostRaw === '0.0.0.0' ? '127.0.0.1' : apiHostRaw;
  const apiTarget = env.API_BASE_URL || `http://${apiHost}:${apiPort}`;
  const webPort = Number(env.WEB_PORT || env.APP_PORT || env.PORT || 8765);
  const webHost = env.WEB_HOST || env.APP_HOST || env.HOST || '127.0.0.1';

  return {
    plugins: [vue()],
    server: {
      host: webHost,
      port: Number.isFinite(webPort) ? webPort : (Number.isFinite(appPort) ? appPort : 8765),
      strictPort: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
