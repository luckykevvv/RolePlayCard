import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiPort = Number(env.API_PORT || env.PORT || env.RPC_PORT || 8765);
  const apiHostRaw = env.API_HOST || env.HOST || env.BIND_HOST || env.RPC_HOST || '127.0.0.1';
  const apiHost = apiHostRaw === '0.0.0.0' ? '127.0.0.1' : apiHostRaw;
  const apiTarget = env.API_BASE_URL || `http://${apiHost}:${apiPort}`;
  const webPort = Number(env.WEB_PORT || 5173);

  return {
    plugins: [vue()],
    server: {
      host: env.WEB_HOST || '127.0.0.1',
      port: Number.isFinite(webPort) ? webPort : 5173,
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
