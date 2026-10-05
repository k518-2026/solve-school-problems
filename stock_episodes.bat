@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================================================
echo  『Solve School Problems』小説＆挿絵 5本一括ローカル生成・GitHub Pages公開 (Mac mini M4: Ollama x FLUX.2)
echo ============================================================================
python -m src.main --auto-replenish --min-stock 5 --target-stock 5 --push
pause
