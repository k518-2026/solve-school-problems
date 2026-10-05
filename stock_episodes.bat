@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================================================
echo  『Solve School Problems』小説＆挿絵 ローカル生成・GitHub Pages公開 (Mac mini M4: Ollama x FLUX.2)
echo ============================================================================
python -m src.main --auto-replenish --min-stock 1 --target-stock 6 --push
pause
