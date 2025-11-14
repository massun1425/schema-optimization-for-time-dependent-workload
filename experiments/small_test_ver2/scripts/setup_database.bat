@echo off
REM データベースセットアップスクリプト - Windows バッチファイル版
REM 使い方: setup_database.bat [small_test|imdb]

echo.
echo ============================================================
echo データベースセットアップスクリプト (Windows)
echo ============================================================
echo.

REM 引数チェック
if "%1"=="" (
    echo エラー: データベースタイプを指定してください
    echo.
    echo 使い方:
    echo   setup_database.bat small_test    - 小規模テストデータベース
    echo   setup_database.bat imdb          - IMDb データベース
    echo.
    exit /b 1
)

if not "%1"=="small_test" if not "%1"=="imdb" (
    echo エラー: 無効なデータベースタイプです: %1
    echo 有効な値: small_test, imdb
    echo.
    exit /b 1
)

REM Python スクリプトを実行
python experiments\small_test_ver2\scripts\setup_database.py --type %1 %2 %3 %4 %5

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo ✅ セットアップが完了しました
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo ❌ セットアップに失敗しました
    echo ============================================================
    exit /b 1
)
