@echo off
setlocal EnableExtensions
REM ============================================================
REM  STZ XML Translator — Nuitka Build Script
REM  Flags estaticas definidas em main_qt.py (# nuitka-project:)
REM  Apenas flags dinamicas ficam aqui.
REM ============================================================

REM --- Versao (fonte unica: altere aqui para um novo release) ---
set APP_VERSION=1.2.0.0

REM --- UPX pos-build ---
REM   1 = comprime com UPX (40-60%% menor; aumenta falsos positivos em AV)
REM   0 = sem UPX
set USE_UPX=0

REM --- Installer via Inno Setup ---
REM   1 = gera STZXMLTranslator-Setup.exe
REM   0 = sem installer (usar MSIX via build-msix.ps1)
set BUILD_INSTALLER=0

REM --- Relatorio de compilacao ---
REM   1 = gera compilation-report.xml (mostra tudo incluido no bundle)
REM   0 = sem relatorio
set BUILD_REPORT=1

REM --- Pular upgrade de dependencias (CI / offline) ---
set SKIP_UPGRADE=1

REM --- Nao pausar ao final (CI / automacao) ---
if "%NO_PAUSE%"=="" set NO_PAUSE=0

REM Modo fixo: standalone (definido em main_qt.py via nuitka-project)
set BUILD_MODE=standalone

REM ============================================================

echo ========================================
echo  STZ XML Translator -- Build com Nuitka
echo  Versao: %APP_VERSION%  UPX: %USE_UPX%
echo ========================================
echo.

REM Ativa o ambiente virtual
if exist ".venv\Scripts\activate.bat" (
    echo Ativando ambiente virtual ^(.venv^)...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo Ativando ambiente virtual ^(venv^)...
    call venv\Scripts\activate.bat
) else (
    echo Aviso: nenhum ambiente virtual encontrado, usando Python do sistema.
)

REM Instala/atualiza dependencias de build
if not "%SKIP_UPGRADE%"=="1" (
    echo.
    echo Instalando/atualizando dependencias via pyproject.toml...
    python -m pip install -e ".[dev]"
    if errorlevel 1 (
        echo Erro ao instalar dependencias do pyproject.toml.
        exit /b 1
    )
)

REM Remove artefatos de build anteriores
echo.
echo Limpando artefatos anteriores...
if exist "main_qt.build"              rmdir /s /q "main_qt.build"
if exist "main_qt.onefile-build"      rmdir /s /q "main_qt.onefile-build"
if exist "dist\main_qt.dist"          rmdir /s /q "dist\main_qt.dist"
if exist "dist\STZXMLTranslator.exe"  del   /q    "dist\STZXMLTranslator.exe"
if exist "compilation-report.xml"     del   /q    "compilation-report.xml"

REM Converte icone PNG -> ICO (multi-tamanho)
echo.
if exist "assets\stz-xml.png" (
    echo Convertendo assets\stz-xml.png para assets\icon.ico...
    python -c "from PIL import Image; img=Image.open('assets/stz-xml.png').convert('RGBA'); img.save('assets/icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if errorlevel 1 (
        echo Aviso: conversao PNG->ICO falhou. Rode: python -m pip install -e ".[dev]"
        echo Compilando com o icon.ico existente, se houver.
    )
)

echo.
echo ========================================
echo  Iniciando compilacao...
echo ========================================
echo.

REM Relatorio
set REPORT_PARAM=
if "%BUILD_REPORT%"=="1" set REPORT_PARAM=--report=compilation-report.xml

REM Flags estaticas carregadas dos comentarios # nuitka-project: em main_qt.py
python -m nuitka ^
    --jobs=%NUMBER_OF_PROCESSORS% ^
    --file-version=%APP_VERSION% ^
    --product-version=%APP_VERSION% ^
    %REPORT_PARAM% ^
    main_qt.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo  BUILD FALHOU  ^(exit code %ERRORLEVEL%^)
    echo ========================================
    echo.
    if /I not "%CI%"=="true" if not "%NO_PAUSE%"=="1" pause
    exit /b %ERRORLEVEL%
)

REM --- UPX (pos-build, opcional) ---
if "%USE_UPX%"=="1" (
    echo.
    echo Comprimindo com UPX...
    where upx >nul 2>&1
    if not errorlevel 1 (
        if "%BUILD_MODE%"=="onefile" (
            upx --best --lzma "dist\STZXMLTranslator.exe"
        ) else (
            upx --best --lzma "dist\main_qt.dist\STZXMLTranslator.exe"
            for /r "dist\main_qt.dist" %%f in (*.dll) do upx --best --lzma "%%f"
        )
    ) else (
        echo Aviso: upx.exe nao encontrado no PATH, pulando compressao.
    )
)

REM --- Installer via Inno Setup (so no modo standalone) ---
if "%BUILD_INSTALLER%"=="1" (
    if not "%BUILD_MODE%"=="standalone" (
        echo Aviso: BUILD_INSTALLER=1 requer BUILD_MODE=standalone. Pulando installer.
    ) else (
        echo.
        echo Gerando installer com Inno Setup...
        if exist "C:\Program Files ^(x86^)\Inno Setup 6\ISCC.exe" (
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
            if not errorlevel 1 (
                echo Installer gerado: dist\STZXMLTranslator-Setup.exe
            ) else (
                echo Erro ao gerar installer.
            )
        ) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
            "C:\Program Files\Inno Setup 6\ISCC.exe" installer.iss
            if not errorlevel 1 (
                echo Installer gerado: dist\STZXMLTranslator-Setup.exe
            ) else (
                echo Erro ao gerar installer.
            )
        ) else (
            echo Aviso: ISCC.exe nao encontrado. Instale o Inno Setup 6.
        )
    )
)

echo.
echo ========================================
echo  Build concluido com sucesso!
echo ========================================
echo.
if "%BUILD_MODE%"=="onefile" (
    echo Executavel : dist\STZXMLTranslator.exe
) else (
    echo Pasta      : dist\main_qt.dist\
    echo Executavel : dist\main_qt.dist\STZXMLTranslator.exe
)
if "%BUILD_REPORT%"=="1" echo Relatorio  : compilation-report.xml
echo.
if /I not "%CI%"=="true" if not "%NO_PAUSE%"=="1" pause
