# School Data Transformer (Robust)

A single-page Streamlit app for uploading school spreadsheets and downloading all processed outputs as one ZIP bundle.

This version adds:
- Auto-detected CSV delimiters and Excel sheet selection
- Fuzzy column matching (case-insensitive, contains-based)
- Diagnostics expander showing row counts and matched columns
- Safer fallbacks so outputs aren't empty if column names differ slightly

## Quickstart

```bash
pip install -r requirements.txt
streamlit run app.py
```
