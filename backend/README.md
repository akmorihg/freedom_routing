## Init Alembic (migrations)

```bash
docker compose exec backend alembic -c infrastructure/db/migrations/alembic.ini init infrastructure/db/migrations
```

### Make migration
```bash
docker compose exec backend alembic -c infrastructure/db/migrations/alembic.ini revision --autogenerate
```

### Migrate
```bash
docker compose exec backend alembic -c infrastructure/db/migrations/alembic.ini upgrade head
```