up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head

test:
	docker compose exec backend pytest -q

frontend:
	cd frontend && npm install && npm run dev

backend:
	cd backend && uvicorn app.main:app --reload --port 8000
