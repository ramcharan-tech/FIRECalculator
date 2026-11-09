@echo off
where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    uv run --all-extras streamlit run app.py
) else (
    streamlit run app.py
)
