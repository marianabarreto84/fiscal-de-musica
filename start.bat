@echo off
cd /d "%~dp0"

if not exist ".env" (
    copy ".env.example" ".env"
    echo .env criado — edite com seu DATABASE_URL antes de continuar.
    pause
    exit /b
)

poetry install --no-interaction
for /f "tokens=2 delims==" %%a in ('findstr /b "PORT=" .env') do set APP_PORT=%%a
echo Iniciando fiscal-de-musica em http://localhost:%APP_PORT%
start "" "http://localhost:%APP_PORT%"
poetry run python run.py
