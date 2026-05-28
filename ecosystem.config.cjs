const rootDir = __dirname;
const host = process.env.RPC_HOST || '127.0.0.1';
const port = process.env.RPC_PORT || '8765';

module.exports = {
  apps: [
    {
      name: 'role-play-card',
      cwd: rootDir,
      script: 'python',
      args: ['python-service/src/pm2_server.py'],
      env: {
        PYTHONUNBUFFERED: '1',
        RPC_HOST: host,
        RPC_PORT: port,
        RPC_APP_DATA: process.env.RPC_APP_DATA || '.role-play-card-data',
        RPC_STATIC_DIR: process.env.RPC_STATIC_DIR || 'vue-renderer/dist',
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 1000,
    },
  ],
};
