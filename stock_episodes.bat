@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================================================
echo  『Solve School Problems』ストック＆挿絵 自動補充 (Gemini/Gemma4 x FLUX.2)
echo ============================================================================
python -m src.main --auto-replenish --min-stock 1 --target-stock 6 --push
pause
