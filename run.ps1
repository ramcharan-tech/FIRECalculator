if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run --all-extras streamlit run app.py
} else {
    streamlit run app.py
}
