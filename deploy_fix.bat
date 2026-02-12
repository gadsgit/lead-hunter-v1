@echo off
echo ===================================================
echo   Lead Hunter Deployment Script
echo   Pushing Memory Optimization Fix to GitHub...
echo ===================================================

echo.
echo [1/3] Adding files to Git staging area...
git add .
if %errorlevel% neq 0 (
    echo [ERROR] Git command failed. Is git installed?
    echo Please install Git from: https://git-scm.com/download/win
    pause
    exit /b
)

echo.
echo [2/3] Committing changes...
git commit -m "Fix SyntaxError and Implement Atomic Scraping"
if %errorlevel% neq 0 (
    echo [INFO] Nothing to commit. Moving to push...
)

echo.
echo [3/3] Pushing to GitHub (Triggers Render Deploy)...
git push
if %errorlevel% neq 0 (
    echo [ERROR] Git push failed. Please check your internet connection or GitHub credentials.
    pause
    exit /b
)

echo.
echo ===================================================
echo   SUCCESS! Deployment Triggered.
echo   Check Render Dashboard in 2-3 minutes:
echo   https://dashboard.render.com
echo ===================================================
echo.
pause
