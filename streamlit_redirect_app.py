# app.py for the streamlit-redirect branch
# Replace the main app.py with this file on that branch
import streamlit as st

RENDER_URL = "https://elc-tools.onrender.com"

st.set_page_config(page_title="ELC Tools - Redirecting...", page_icon="📦")

st.markdown(
    f'<meta http-equiv="refresh" content="3;url={RENDER_URL}">',
    unsafe_allow_html=True
)

st.markdown(f"""
# 📦 ELC Tools si è trasferito!

L'applicazione è stata spostata a un nuovo indirizzo.

Verrai reindirizzato automaticamente tra 3 secondi...

**Nuovo link:** [{RENDER_URL}]({RENDER_URL})

Aggiorna i tuoi segnalibri.
""")
