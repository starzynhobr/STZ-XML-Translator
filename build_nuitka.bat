@echo off
REM Compila o STZ XML Translator (PySide6 + QML) com Nuitka.
REM Entry point : main_qt.py
REM Plugin      : pyside6
REM Inclui      : ui/ (QML), locales/, assets/, scripts/

echo ========================================
echo  STZ XML Translator — Build com Nuitka
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

REM Verifica se o icone existe
set ICON_PARAM=
if exist "assets\icon.ico" (
    echo Icone encontrado, incluindo no build...
    set ICON_PARAM=--windows-icon-from-ico=assets/icon.ico
) else (
    echo Aviso: icon.ico nao encontrado em assets\, compilando sem icone...
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
    --include-data-dir=scripts=scripts ^
    --nofollow-import-to=test ^
    --assume-yes-for-downloads ^
    --output-filename=STZXMLTranslator.exe ^
    --output-dir=dist ^
    --company-name="STZ XML Translator" ^
    --product-name="STZ XML Translator" ^
    --file-version=1.2.0.0 ^
    --product-version=1.2.0.0 ^
    --file-description="STZ XML Translator — Ferramenta de traducao de arquivos XML" ^
    --windows-uac-admin=no ^
    main_qt.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  Compilacao concluida com sucesso!
    echo ========================================
    echo.
    echo Executavel gerado em: dist\STZXMLTranslator.exe
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
