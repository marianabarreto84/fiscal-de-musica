@echo off
cd /d "%~dp0"

if not exist ".env" (
    copy ".env.example" ".env"
    echo .env criado — edite com seu DATABASE_URL antes de continuar.
    pause
    exit /b
)

poetry install --no-interaction
echo Iniciando fiscal-de-musica em http://localhost:8002
start "" "http://localhost:8002"
poetry run python run.py
