@echo off
chcp 65001 > nul
title Sistema de Estágios FAMED/UFPA

echo ======================================================
echo    SISTEMA DE GESTÃO DE ESTÁGIOS - FAMED / UFPA
echo ======================================================
echo.

REM Verifica se o Python está instalado
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] Python não foi encontrado no seu computador!
    echo Por favor, instale o Python 3.10 ou superior em: https://www.python.org/downloads/
    echo IMPORTANTE: Durante a instalação, marque a opção "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

REM Cria o ambiente virtual caso ainda não exista
if not exist ".venv" (
    echo [1/4] Criando ambiente virtual isolado (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
    echo [2/4] Instalando dependencias necessarias (aguarde alguns instantes)...
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip > nul
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao instalar dependencias do requirements.txt.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Ativando ambiente virtual...
    call .venv\Scripts\activate.bat
)

REM Aplica as migrações do banco de dados SQLite e garante usuário admin
echo [2/2] Verificando banco de dados local...
python manage.py migrate --noinput > nul
python manage.py setup_admin > nul

REM Abre o navegador padrão automaticamente após 2 segundos
start "" "http://127.0.0.1:8000/"

echo.
echo ======================================================
echo    SISTEMA PRONTO E EM EXECUÇÃO!
echo ======================================================
echo  Acesse pelo navegador: http://127.0.0.1:8000/
echo  Credenciais de acesso padrão:
echo     - Usuário: diretor
echo     - Senha:   FamedUFPA@2027
echo.
echo  Para ENCERRAR o sistema, pressione Ctrl + C nesta janela.
echo ======================================================
echo.

REM Inicia o servidor local do Django
python manage.py runserver 127.0.0.1:8000
pause
