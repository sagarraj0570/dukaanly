import yaml
with open('../docker-compose.yml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

data['services']['worker'] = {
    'build': {
        'context': './backend',
        'dockerfile': 'Dockerfile'
    },
    'container_name': 'dukaanly_worker',
    'restart': 'unless-stopped',
    'command': 'celery -A app.core.celery_app worker --loglevel=info',
    'environment': [
        'DATABASE_URL=postgresql+asyncpg://:@postgres:5432/',
        'REDIS_URL=redis://redis:6379/0',
        'SECRET_KEY='
    ],
    'depends_on': {
        'postgres': {'condition': 'service_healthy'},
        'redis': {'condition': 'service_healthy'}
    },
    'networks': ['dukaanly_net']
}

with open('../docker-compose.yml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, sort_keys=False)
