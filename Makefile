start:
	docker compose up --build -d 
	docker compose exec backend alembic -c infrastructure/db/migrations/alembic.ini upgrade head

stop:
	docker compose down --volumes