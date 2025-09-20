.PHONY: run migrate revision fmt

run:
docker compose up --build

migrate:
docker compose exec api alembic upgrade head

revision:
docker compose exec api alembic revision --autogenerate -m "$(m)"

fmt:
python -m black app
