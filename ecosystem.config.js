module.exports = {
  apps: [
    {
      name: 'role-play-card',
      cwd: __dirname,
      script: 'python',
      args: ['python-service/src/pm2_server.py'],
      env: {
        PYTHONUNBUFFERED: '1',
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 1000,
    },
  ],
};
