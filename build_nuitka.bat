@echo off
REM Compila o Game XML Translator (versão PySide6 + QML) com Nuitka.
REM Entry point: main_qt.py   Plugin: pyside6   Inclui: ui/, locales/, assets/

echo ========================================
echo  Compilando com Nuitka (PySide6 + QML)
echo ========================================
echo.

REM Ativa o ambiente virtual se existir
if exist ".venv\Scripts\activate.bat" (
    echo Ativando ambiente virtual...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo Ativando ambiente virtual...
    call venv\Scripts\activate.bat
)

echo.
echo Instalando/Atualizando Nuitka...
python -m pip install --upgrade pip
python -m pip install --upgrade nuitka ordered-set zstandard

echo.
echo ========================================
echo  Iniciando compilacao...
echo ========================================
echo.

REM Verifica se o ícone existe
set ICON_PARAM=
if exist "assets\icon.ico" (
    echo Icone encontrado, incluindo no build...
    set ICON_PARAM=--windows-icon-from-ico=assets/icon.ico
) else (
    echo Aviso: icon.ico nao encontrado em assets/, compilando sem icone...
)

python -m nuitka ^
    --standalone ^
    --onefile ^
    --enable-plugin=pyside6 ^
    %ICON_PARAM% ^
    --windows-console-mode=disable ^
    --include-data-dir=ui=ui ^
    --include-data-dir=locales=locales ^
    --include-data-dir=assets=assets ^
    --include-data-dir=core=core ^
    --nofollow-import-to=test ^
    --assume-yes-for-downloads ^
    --output-filename=GameXMLTranslator.exe ^
    --output-dir=dist ^
    --company-name="Game XML Translator" ^
    --product-name="Game XML Translator" ^
    --file-version=1.2.0.0 ^
    --product-version=1.2.0.0 ^
    --file-description="Tradutor de arquivos XML de jogos" ^
    --windows-uac-admin=no ^
    main_qt.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  Compilacao concluida com sucesso!
    echo ========================================
    echo.
    echo O executavel foi gerado em: dist\GameXMLTranslator.exe
    echo.
    pause
) else (
    echo.
    echo ========================================
    echo  ERRO na compilacao!
    echo ========================================
    echo.
    pause
)
