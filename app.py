"""
ELC Tools - Estée Lauder Logistics
App Streamlit multi-funzione per la gestione delle spedizioni.
"""

import io
import csv
import re
import logging
import requests
from datetime import datetime, date, time, timedelta

import streamlit as st
import pandas as pd

from src.pdf_processor import PDFProcessor
from src.excel_parser import ExcelParser, ExcelParserError
from src.matcher import Matcher, UnmatchedReason, MatchType
from src.sorter import Sorter, SortMethod
from src.zip_validator import ZipValidator, ValidationReport
from src.address_book import (
    load_addresses, save_addresses, get_address_by_id, get_default_address,
    add_address, update_address, delete_address, set_default_address,
    get_address_display_name, get_address_summary, Address, is_sheets_configured
)
from src.logging_config import setup_logging, get_streamlit_handler, DEBUG, INFO
from src.security import (
    check_rate_limit, record_usage, get_usage_stats, get_client_ip,
    validate_excel_content, sanitize_filename, record_failed_attempt,
    MAX_VALIDATIONS_PER_DAY_PER_IP, MAX_VALIDATIONS_PER_HOUR_PER_IP,
    get_debug_info, MIN_SECONDS_BETWEEN_REQUESTS
)
from src.config import get_secret


# Initialize logging (only once per session)
if 'logging_initialized' not in st.session_state:
    setup_logging(level=INFO, enable_console=False, enable_streamlit=True)
    st.session_state.logging_initialized = True


# ============================================================================
# SECURITY LIMITS - Prevent abuse and DoS
# ============================================================================
MAX_FILE_SIZE_MB = 50  # Maximum file size in MB
MAX_PDF_PAGES = 500    # Maximum pages in PDF
MAX_EXCEL_ROWS = 1000  # Maximum rows in Excel for ZIP validation
# Note: API rate limits are now handled by src/security.py with persistent storage


def check_file_size(file, max_mb: int = MAX_FILE_SIZE_MB) -> bool:
    """Check if uploaded file exceeds size limit."""
    if file is None:
        return True
    file.seek(0, 2)  # Seek to end
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)  # Reset to beginning
    return size_mb <= max_mb


def get_file_size_mb(file) -> float:
    """Get file size in MB."""
    if file is None:
        return 0
    file.seek(0, 2)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    return size_mb


def check_daily_api_limit(rows_to_validate: int) -> tuple[bool, str]:
    """
    Check if we're within API call limits (1000 per 12-hour window).
    Uses Supabase for persistent storage.
    Returns (is_allowed, message).
    """
    client_ip = get_client_ip()
    allowed, message, usage_info = check_rate_limit(client_ip, rows_to_validate)

    if not allowed:
        return False, message

    # Build informative message
    current = usage_info.get('current_usage', 0)
    limit = usage_info.get('limit', 1000)
    return True, f"Utilizzo API: {current} + {rows_to_validate} = {current + rows_to_validate}/{limit}"


def record_api_usage(rows_validated: int):
    """Record API usage for persistent rate limiting."""
    client_ip = get_client_ip()
    record_usage(client_ip, rows_validated)


def check_cooldown() -> tuple[bool, int]:
    """
    Check if enough time has passed since last validation.
    Returns (is_allowed, seconds_remaining).
    """
    if 'last_validation_time' not in st.session_state:
        return True, 0

    elapsed = (datetime.now() - st.session_state.last_validation_time).total_seconds()
    if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
        return False, int(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    return True, 0


def record_validation_time():
    """Record the time of the last validation."""
    st.session_state.last_validation_time = datetime.now()


# Configurazione pagina
st.set_page_config(
    page_title="ELC Tools - Estée Lauder",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="expanded"
)

# CSS personalizzato
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .result-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
    }
    .stDownloadButton > button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


def generate_csv_report(match_report, sorted_result) -> str:
    """Genera il report CSV delle etichette non matchate."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Pagina Originale",
        "Tracking Estratto",
        "Corriere",
        "Motivo"
    ])

    for result in match_report.unmatched:
        tracking = result.tracking if result.tracking else "(non estratto)"
        carrier = result.carrier if result.carrier else "-"
        reason = result.unmatched_reason.value if result.unmatched_reason else "Sconosciuto"

        writer.writerow([
            result.page_number,
            tracking,
            carrier,
            reason
        ])

    return output.getvalue()


def label_sorter_page():
    """Page for Label Sorter feature."""
    st.markdown("# 📦 Label Sorter")
    st.markdown("*Riordina le etichette di spedizione secondo l'ordine degli ordini*")

    # User guide
    with st.expander("📖 Come usare questo strumento", expanded=False):
        st.markdown("""
**1. Scarica le etichette da ordinare**
- Scarica il PDF con le etichette generate che vuoi riordinare

**2. Esporta l'Excel da ShippyPro**
- Vai su **Etichette generate**
- Filtra gli ordini interessati
- Seleziona gli ordini
- Clicca sul menu a tendina **Crea documenti**
- Clicca su **Crea lista ordini XLS**

**3. Carica i file**
- Carica il PDF delle etichette e il file Excel esportato
- Scegli la modalità di ordinamento

**4. Scarica il risultato**
- Scarica il nuovo PDF con le etichette ordinate
        """)

    st.markdown("---")

    # Initialize session state for persisting results
    if 'label_sorter_results' not in st.session_state:
        st.session_state.label_sorter_results = None

    # Sezione Upload
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📄 PDF Etichette")
        pdf_files = st.file_uploader(
            "Carica i PDF con le etichette",
            type=["pdf"],
            key="pdf_uploader",
            help="Uno o più PDF con etichette (DHL, FedEx, UPS). Verranno uniti automaticamente.",
            accept_multiple_files=True,
            on_change=lambda: st.session_state.update({'label_sorter_results': None})
        )

    with col2:
        st.markdown("### 📊 Excel Ordini")
        excel_file = st.file_uploader(
            "Carica il file Excel degli ordini",
            type=["xlsx", "xls"],
            key="excel_uploader",
            help="Export da ShippyPro con ID Ordine, Tracking, Corriere",
            on_change=lambda: st.session_state.update({'label_sorter_results': None})
        )

    # Metodo di ordinamento
    st.markdown("### 🔢 Metodo di ordinamento")
    sort_method = st.radio(
        "Seleziona come ordinare le etichette:",
        options=[
            ("Segui ordine Excel", SortMethod.EXCEL_ORDER),
            ("Ordina per Order ID (numerico crescente)", SortMethod.ORDER_ID_NUMERIC)
        ],
        format_func=lambda x: x[0],
        horizontal=True,
        index=1,  # Default: Order ID numerico
        key="sort_method"
    )

    # Bottone elabora
    st.markdown("---")
    process_button = st.button(
        "🚀 Elabora",
        type="primary",
        disabled=not (pdf_files and excel_file),
        use_container_width=True,
        key="label_sorter_process"
    )

    # Elaborazione
    if process_button and pdf_files and excel_file:
        # Security checks
        total_pdf_size = 0
        for pdf_file in pdf_files:
            if not check_file_size(pdf_file, MAX_FILE_SIZE_MB):
                st.error(f"❌ File PDF '{pdf_file.name}' troppo grande. Massimo: {MAX_FILE_SIZE_MB}MB")
                st.stop()
            total_pdf_size += get_file_size_mb(pdf_file)
        if total_pdf_size > MAX_FILE_SIZE_MB * 2:  # Allow more for multiple files
            st.error(f"❌ Dimensione totale PDF troppo grande ({total_pdf_size:.1f}MB). Massimo: {MAX_FILE_SIZE_MB * 2}MB")
            st.stop()
        if not check_file_size(excel_file, MAX_FILE_SIZE_MB):
            st.error(f"❌ File Excel troppo grande. Massimo: {MAX_FILE_SIZE_MB}MB")
            st.stop()

        status_container = st.container()

        with status_container:
            st.markdown("### 🔄 Elaborazione in corso...")

            try:
                pdf_processor = PDFProcessor()
                excel_parser = ExcelParser()

                # Step 1: Leggi e unisci PDF
                with st.status(f"📄 Step 1/5: Lettura {len(pdf_files)} PDF...", expanded=True) as status:
                    import fitz  # PyMuPDF for merging

                    if len(pdf_files) == 1:
                        st.write("Caricamento file PDF...")
                        pdf_bytes = pdf_files[0].read()
                        st.write(f"✓ File caricato: {len(pdf_bytes):,} bytes")
                    else:
                        st.write(f"Unione di {len(pdf_files)} file PDF...")
                        merged_doc = fitz.open()
                        for i, pdf_file in enumerate(pdf_files):
                            pdf_file.seek(0)
                            file_bytes = pdf_file.read()
                            st.write(f"  → {pdf_file.name}: {len(file_bytes):,} bytes")
                            temp_doc = fitz.open(stream=file_bytes, filetype="pdf")
                            merged_doc.insert_pdf(temp_doc)
                            temp_doc.close()
                        # Save merged PDF to bytes
                        pdf_bytes = merged_doc.tobytes()
                        merged_doc.close()
                        st.write(f"✓ PDF unito: {len(pdf_bytes):,} bytes totali")

                    st.write("Estrazione pagine e tracking...")
                    pdf_data = pdf_processor.process_pdf(pdf_bytes)
                    st.write(f"✓ Pagine trovate: {pdf_data.total_pages}")

                    # Security check: page limit
                    if pdf_data.total_pages > MAX_PDF_PAGES:
                        st.error(f"❌ Troppe pagine nel PDF ({pdf_data.total_pages}). Massimo: {MAX_PDF_PAGES}")
                        st.stop()

                    extracted = [(p.page_number, p.tracking, p.carrier) for p in pdf_data.pages[:5] if p.tracking]
                    if extracted:
                        st.write(f"✓ Primi tracking estratti: {extracted}")
                    else:
                        st.warning("⚠️ Nessun tracking estratto dalle prime pagine")

                    status.update(label=f"✅ Step 1/5: PDF letto ({pdf_data.total_pages} pagine)", state="complete")

                # Step 2: Leggi Excel
                with st.status("📊 Step 2/5: Lettura Excel...", expanded=True) as status:
                    st.write("Caricamento file Excel...")
                    excel_bytes = excel_file.read()
                    st.write(f"✓ File caricato: {len(excel_bytes):,} bytes")

                    st.write("Parsing dati ordini...")
                    try:
                        excel_data = excel_parser.parse_excel(excel_bytes, excel_file.name)
                        st.write(f"✓ Ordini trovati: {len(excel_data.orders)}")
                        st.write(f"✓ Colonne trovate: {excel_data.columns_found}")
                        st.write(f"✓ Colonna Tracking usata: **{excel_data.tracking_column_used}**")

                        if excel_data.orders:
                            first_orders = [(o.order_id, o.tracking) for o in excel_data.orders[:3]]
                            st.write(f"✓ Primi ordini (ID, Tracking): {first_orders}")

                        status.update(label=f"✅ Step 2/5: Excel letto ({len(excel_data.orders)} ordini)", state="complete")
                    except ExcelParserError as e:
                        status.update(label="❌ Step 2/5: Errore lettura Excel", state="error")
                        st.error(f"Errore: {str(e)}")
                        st.stop()

                if excel_data.warnings:
                    with st.expander(f"⚠️ {len(excel_data.warnings)} avvisi lettura Excel"):
                        for warning in excel_data.warnings:
                            st.warning(warning)

                # Step 3: Matching
                with st.status("🔗 Step 3/5: Matching tracking...", expanded=True) as status:
                    st.write("Creazione indice tracking Excel...")
                    matcher = Matcher(pdf_data, excel_data)
                    st.write(f"✓ Indice creato con {len(excel_data.orders)} tracking")

                    st.write("Matching pagine PDF con ordini Excel...")
                    match_report = matcher.match_all()
                    st.write(f"✓ Matchate: {len(match_report.matched)} / {match_report.total_pages}")
                    st.write(f"✓ Non matchate: {len(match_report.unmatched)}")
                    st.write(f"✓ Match rate: {match_report.match_rate}%")

                    status.update(label=f"✅ Step 3/5: Matching completato ({match_report.match_rate}%)", state="complete")

                # Step 4: Ordinamento
                with st.status("🔢 Step 4/5: Ordinamento pagine...", expanded=True) as status:
                    st.write(f"Metodo: {sort_method[0]}")
                    sorter = Sorter(match_report, excel_data)
                    sorted_result = sorter.sort(sort_method[1])
                    st.write(f"✓ Ordine calcolato per {len(sorted_result.page_order)} pagine")
                    st.write(f"✓ Prime pagine nell'ordine: {sorted_result.page_order[:10]}...")

                    status.update(label=f"✅ Step 4/5: Ordinamento completato", state="complete")

                # Step 5: Genera PDF riordinato
                with st.status("📝 Step 5/5: Generazione PDF...", expanded=True) as status:
                    st.write(f"Riordinamento {len(sorted_result.page_order)} pagine...")
                    st.write("Questo potrebbe richiedere alcuni secondi per PDF grandi...")

                    reordered_pdf = pdf_processor.reorder_pdf(
                        pdf_bytes,
                        sorted_result.page_order
                    )

                    st.write(f"✓ PDF generato: {len(reordered_pdf):,} bytes")
                    status.update(label=f"✅ Step 5/5: PDF generato ({len(reordered_pdf):,} bytes)", state="complete")

                st.success("🎉 Elaborazione completata con successo!")

                # Generate CSV report and store results in session state
                csv_report = generate_csv_report(match_report, sorted_result)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                st.session_state.label_sorter_results = {
                    'reordered_pdf': reordered_pdf,
                    'csv_report': csv_report,
                    'match_report': match_report,
                    'sorted_result': sorted_result,
                    'pdf_data': pdf_data,
                    'timestamp': timestamp
                }

            except Exception as e:
                st.error(f"❌ Errore durante l'elaborazione: {str(e)}")
                st.exception(e)
                st.stop()

    # Display results from session state (persists across reruns)
    if st.session_state.label_sorter_results:
        results = st.session_state.label_sorter_results
        match_report = results['match_report']
        sorted_result = results['sorted_result']
        pdf_data = results['pdf_data']

        st.markdown("---")
        st.markdown("## ✅ Risultato")

        col_stat1, col_stat2, col_stat3 = st.columns(3)

        with col_stat1:
            st.metric(label="Etichette elaborate", value=pdf_data.total_pages)

        with col_stat2:
            st.metric(label="Matchate", value=f"{sorted_result.matched_count} ({match_report.match_rate}%)")

        with col_stat3:
            st.metric(label="Non matchate", value=sorted_result.unmatched_count)

        st.markdown("### 📥 Download")
        col_dl1, col_dl2 = st.columns(2)

        with col_dl1:
            st.download_button(
                label="📄 Scarica PDF Riordinato",
                data=results['reordered_pdf'],
                file_name=f"etichette_ordinate_{results['timestamp']}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="download_pdf"
            )

        with col_dl2:
            st.download_button(
                label="📋 Scarica Report CSV",
                data=results['csv_report'],
                file_name=f"report_non_matchate_{results['timestamp']}.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_csv"
            )

        if match_report.unmatched:
            st.markdown("### ⚠️ Etichette non matchate")
            st.markdown("*Queste etichette sono state inserite in fondo al PDF*")

            unmatched_data = []
            for result in match_report.unmatched:
                unmatched_data.append({
                    "Pag.": result.page_number,
                    "Tracking estratto": result.tracking if result.tracking else "(non riconosciuto)",
                    "Corriere": result.carrier if result.carrier else "-",
                    "Motivo": result.unmatched_reason.value if result.unmatched_reason else "Sconosciuto"
                })

            st.dataframe(unmatched_data, use_container_width=True, hide_index=True)

            # Debug mode - show raw text from pages with unrecognized tracking
            with st.expander("🔍 Debug: Testo estratto dalle pagine problematiche"):
                st.markdown("*Questo testo è estratto direttamente dal PDF. Utile per capire perché il tracking non viene riconosciuto.*")
                unrecognized_pages = [r for r in match_report.unmatched
                                      if r.unmatched_reason and r.unmatched_reason.value == "Pattern tracking non identificato"]
                if unrecognized_pages:
                    for result in unrecognized_pages[:5]:  # Show first 5
                        page_info = pdf_data.pages[result.page_index]
                        st.markdown(f"**Pagina {result.page_number}:**")
                        st.code(page_info.raw_text[:1000] if page_info.raw_text else "(nessun testo estratto)", language=None)
                        st.markdown("---")
                    if len(unrecognized_pages) > 5:
                        st.info(f"Mostrate solo le prime 5 pagine di {len(unrecognized_pages)} con tracking non riconosciuto.")
                else:
                    st.info("Nessuna pagina con tracking non riconosciuto (problema di match con Excel).")

            # Debug: Show fuzzy/partial matches that may need review
            with st.expander("🔍 Debug: Match con confidenza ridotta"):
                st.markdown("*Match trovati con metodi fuzzy o parziali (potrebbero richiedere verifica)*")
                fuzzy_matches = [r for r in match_report.matched
                                 if r.match_type in (MatchType.FUZZY, MatchType.PARTIAL)]
                if fuzzy_matches:
                    fuzzy_data = []
                    for result in fuzzy_matches:
                        match_type_label = {
                            MatchType.FUZZY: "🔸 Fuzzy (simile)",
                            MatchType.PARTIAL: "🔹 Parziale"
                        }.get(result.match_type, "Altro")

                        fuzzy_data.append({
                            "Pag.": result.page_number,
                            "Tracking PDF": result.tracking,
                            "Tracking Excel": result.order.tracking if result.order else "-",
                            "Tipo": match_type_label,
                            "Confidenza": f"{result.match_confidence}%"
                        })
                    st.dataframe(fuzzy_data, use_container_width=True, hide_index=True)
                else:
                    st.info("Tutti i match sono esatti (100% confidenza).")
        else:
            st.success("🎉 Tutte le etichette sono state matchate!")

        # Button to clear results and start over
        if st.button("🔄 Nuova elaborazione", use_container_width=True, key="new_label_sort"):
            st.session_state.label_sorter_results = None
            st.rerun()


def zip_validator_page():
    """Page for Address Validator feature."""
    st.markdown("# 📍 Address Validator")
    st.markdown("*Valida e correggi indirizzi italiani con AI + Google Address Validation*")

    # Quick start — always visible
    st.info("**Come funziona:** 1. Carica il file Excel → 2. Clicca Avvia Validazione → 3. Scarica il file corretto")

    # Detailed guide — collapsed
    with st.expander("📖 Guida dettagliata", expanded=False):
        st.markdown("""
**Formato file**
- [Scarica il template](https://docs.google.com/spreadsheets/d/1eKfU6G-wzpNa8HZDcuddpJAZHEzWUKJUFw-y5LFDKOU/edit?usp=sharing) — Colonne richieste: **Street 1**, **City**, **Zip**
- Colonne opzionali: Country, State/Province, Phone, Order Number, Cash on Delivery

**Cosa viene corretto automaticamente?**
- CAP errati o incompleti (es: "187" → "00187")
- Vie con errori di battitura (es: "Via Roam" → "Via Roma")
- Tipo di via errato (es: "Via 24 Maggio" → "Piazza 24 Maggio")
- Centro Commerciale separato in Street 2
- Contrassegno (COD) impostato a 0
- Telefono mancante compilato con numero default

**Legenda risultati**

| | Significato |
|---|---|
| ✓ | Verificato |
| 🔄 | Corretto automaticamente |
| ⚠️ | Da verificare manualmente |

**Limiti:** Max 1.000 righe per file, 1.000 validazioni ogni 12 ore
        """)

    st.markdown("---")

    # Initialize session state for persisting results
    if 'zip_validation_results' not in st.session_state:
        st.session_state.zip_validation_results = None

    # Upload
    st.markdown("### 📊 File Indirizzi")
    excel_file = st.file_uploader(
        "Carica il file Excel con gli indirizzi",
        type=["xlsx", "xls"],
        key="zip_excel_uploader",
        help="File con colonne: Street 1, City, Zip, Country",
        on_change=lambda: st.session_state.update({'zip_validation_results': None})
    )

    # Usage info — compact bar
    client_ip = get_client_ip()
    usage_stats = get_usage_stats(client_ip)
    current_usage = usage_stats.get('current_usage', 0)
    limit = usage_stats.get('limit', 1000)
    remaining = usage_stats.get('remaining', 1000)
    period_end = usage_stats.get('period_end', '00:00')
    st.caption(f"📊 Validazioni disponibili: **{remaining}** di {limit} | Reset: {period_end}")

    # Advanced settings — hidden by default
    confidence_threshold = 90
    street_confidence_threshold = 85
    pin_valid = False

    with st.expander("⚙️ Opzioni avanzate", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            confidence_threshold = st.slider(
                "Soglia auto-correzione CAP",
                min_value=50, max_value=100, value=90, step=5,
                help="CAP corretti automaticamente solo se confidenza ≥ soglia"
            )
        with col2:
            street_confidence_threshold = st.slider(
                "Soglia auto-correzione Via",
                min_value=50, max_value=100, value=85, step=5,
                help="Vie corrette automaticamente solo se confidenza ≥ soglia"
            )

        st.markdown("---")
        pin_input = st.text_input(
            "🔑 PIN bypass PO",
            type="password",
            max_chars=4,
            help="Inserisci il PIN per scaricare anche senza PO valido"
        )
        bypass_pin = get_secret("app", "bypass_pin") or ""
        pin_valid = bool(bypass_pin) and pin_input == bypass_pin
        if pin_input and not pin_valid:
            st.warning("PIN non valido")
        elif pin_valid:
            st.success("PIN corretto — validazione PO disabilitata")

        st.markdown("---")
        st.caption("🔧 Debug")
        debug_info = get_debug_info(client_ip)
        st.write(f"Period: `{debug_info.get('period_id', 'N/A')}` | "
                 f"Supabase: `{debug_info.get('supabase_connected', False)}` | "
                 f"Usage: `{debug_info.get('current_usage', 0)}/{debug_info.get('limit', 1000)}`")

    process_button = st.button(
        "🔍 Avvia Validazione",
        type="primary",
        disabled=not excel_file,
        use_container_width=True,
        key="zip_validator_process"
    )

    if process_button and excel_file:
        # Security check: file size
        if not check_file_size(excel_file, MAX_FILE_SIZE_MB):
            st.error(f"❌ File troppo grande. Massimo: {MAX_FILE_SIZE_MB}MB")
            st.stop()

        # Security check: cooldown between validations (skipped with PIN)
        if not pin_valid:
            cooldown_ok, seconds_remaining = check_cooldown()
            if not cooldown_ok:
                st.warning(f"⏳ Attendi {seconds_remaining} secondi prima della prossima validazione.")
                st.stop()

        try:
            # Read Excel
            with st.status("📊 Lettura file...", expanded=True) as status:
                excel_bytes = excel_file.read()
                st.write(f"✓ File caricato: {len(excel_bytes):,} bytes")

                # Try to read with pandas - store working engine for consistency
                excel_engine = None
                try:
                    df = pd.read_excel(io.BytesIO(excel_bytes), engine='openpyxl')
                    excel_engine = 'openpyxl'
                except:
                    try:
                        df = pd.read_excel(io.BytesIO(excel_bytes), engine='calamine')
                        excel_engine = 'calamine'
                    except:
                        df = pd.read_excel(io.BytesIO(excel_bytes))

                # Store original df before any filtering
                original_df = df.copy()

                # Security check: validate Excel content for malicious formulas
                content_valid, content_error = validate_excel_content(df)
                if not content_valid:
                    st.error(f"❌ Contenuto non valido: {content_error}")
                    record_failed_attempt(get_client_ip())
                    st.stop()

                st.write(f"✓ Righe trovate: {len(df)}")
                st.write(f"✓ Colonne: {', '.join(df.columns[:8].tolist())}...")

                # Security check: row limit for API calls
                if len(df) > MAX_EXCEL_ROWS:
                    st.error(f"❌ Troppe righe ({len(df)}). Massimo: {MAX_EXCEL_ROWS} per limitare chiamate API.")
                    st.info("💡 Suggerimento: dividi il file in batch più piccoli.")
                    st.stop()

                # Security check: daily API limit (skipped with PIN)
                if pin_valid:
                    st.write("✓ Limite API bypassato con PIN")
                else:
                    daily_ok, daily_msg = check_daily_api_limit(len(df))
                    if not daily_ok:
                        st.error(f"❌ {daily_msg}")
                        st.info("💡 Il limite si resetta a mezzanotte.")
                        st.stop()
                    st.write(f"✓ {daily_msg}")

                status.update(label=f"✅ File letto ({len(df)} righe)", state="complete")

            # Country filtering is now handled by Claude's country detection
            # inside process_dataframe (non-IT addresses are skipped automatically)

            # Get API keys via centralized config
            google_api_key = get_secret("google", "api_key")
            anthropic_api_key = get_secret("anthropic", "api_key")

            if not google_api_key:
                st.error("❌ Google Address Validation API key non configurata")
                st.stop()

            api_mode = "Google Address Validation"
            if anthropic_api_key:
                api_mode += " + Claude AI"
            else:
                api_mode += " + regex parsing"

            validator = ZipValidator(
                confidence_threshold=confidence_threshold,
                street_confidence_threshold=street_confidence_threshold,
                google_api_key=google_api_key,
                anthropic_api_key=anthropic_api_key
            )

            # Progress container with phase feedback
            progress_bar = st.progress(0)
            status_text = st.empty()
            validation_start = datetime.now()

            def update_progress(current, total, message):
                pct = min(current / total, 1.0) if total > 0 else 0
                progress_bar.progress(pct)
                # Estimate time remaining for validation phase
                if current > 20 and total > 0:
                    elapsed = (datetime.now() - validation_start).total_seconds()
                    progress_frac = (current - 20) / (total - 20) if total > 20 else 1
                    if progress_frac > 0.05:
                        eta = int(elapsed / progress_frac * (1 - progress_frac))
                        status_text.text(f"⏳ {message} (~{eta}s rimanenti)")
                        return
                status_text.text(f"⏳ {message}")

            with st.spinner(f"Validazione {len(df)} indirizzi..."):
                report, preprocessed_df = validator.process_dataframe(df, progress_callback=update_progress)

            progress_bar.progress(1.0)
            status_text.text("✅ Validazione completata!")

            # Generate files using preprocessed DataFrame (with C.C. moved to Street 2)
            corrected_excel = validator.generate_corrected_excel(preprocessed_df, report)
            review_excel = validator.generate_review_report(report)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.session_state.zip_validation_results = {
                'report': report,
                'corrected_excel': corrected_excel,
                'review_excel': review_excel,
                'timestamp': timestamp,
                'api_mode': api_mode,
            }

            # Record API usage for rate limiting
            record_api_usage(len(df))
            record_validation_time()

        except Exception as e:
            st.error(f"❌ Errore: {str(e)}")
            st.exception(e)

    # Display results from session state (persists across reruns)
    if st.session_state.zip_validation_results:
        results = st.session_state.zip_validation_results
        report = results['report']

        st.markdown("---")
        st.markdown("## ✅ Risultato")
        st.caption(f"Validato con: {results.get('api_mode', 'N/A')}")

        # ZIP stats
        st.markdown("#### 📮 CAP")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("✓ Validi", report.valid_count)

        with col2:
            st.metric("🔄 Corretti", report.corrected_count)

        with col3:
            st.metric("⚠️ Da rivedere", report.review_count)

        with col4:
            st.metric("⏭️ Saltati", report.skipped_count)

        # Street stats
        st.markdown("#### 🛣️ Vie")
        col_s1, col_s2, col_s3 = st.columns(3)

        with col_s1:
            st.metric("✓ Verificate", report.street_verified_count)

        with col_s2:
            st.metric("🔄 Corrette", report.street_corrected_count)

        with col_s3:
            not_verified = report.total_rows - report.street_verified_count - report.street_corrected_count - report.skipped_count
            st.metric("⚠️ Da verificare", max(0, not_verified))

        # PO validation warning
        if report.po_invalid_count > 0:
            st.markdown("#### 🚨 Numeri Ordine (PO)")
            if pin_valid:
                st.warning(f"⚠️ {report.po_invalid_count} righe hanno un PO non valido o mancante (bypass attivo con PIN)")
            else:
                st.error(f"**ATTENZIONE:** {report.po_invalid_count} righe hanno un PO non valido o mancante!")
                st.warning(
                    "I PO devono essere numeri a 10 cifre che iniziano con '350' (es: 3501494822).\n\n"
                    "Il download sarà disabilitato finché tutti i PO non saranno corretti.\n\n"
                    "💡 Inserisci il PIN per scaricare senza PO valido."
                )

        # Preview results — simplified view by default
        st.markdown("### 📋 Dettaglio validazione")

        simple_data = []
        full_data = []
        for r in report.results:
            # Status emoji
            if r.is_valid and r.street_verified:
                status = "✓"
            elif r.auto_corrected or r.street_auto_corrected:
                status = "🔄"
            elif not r.is_valid or (r.suggested_street and not r.street_verified):
                status = "⚠️"
            else:
                status = "✓"

            # Simple row — essential info only
            simple_row = {
                "Stato": status,
                "Città": r.city or "-",
                "Via": r.street or "-",
                "CAP": r.original_zip,
            }
            # Show correction inline if any
            corrections = []
            if r.auto_corrected and r.suggested_zip:
                corrections.append(f"CAP → {r.suggested_zip}")
            if r.street_auto_corrected and r.suggested_street:
                corrections.append(f"Via → {r.suggested_street}")
            if r.po_invalid:
                corrections.append(f"PO ❌")
            simple_row["Correzioni"] = " | ".join(corrections) if corrections else "-"
            simple_data.append(simple_row)

            # Full row — all details
            full_data.append({
                "Stato": status,
                "Città": r.city or "-",
                "Via Orig.": r.street or "-",
                "Via Sugg.": r.suggested_street or "-",
                "CAP Orig.": r.original_zip,
                "CAP Sugg.": r.suggested_zip or "-",
                "Paese": f"{r.country_code}{'*' if r.country_detected else ''}",
                "Tel.": "+" if r.phone_missing else "✓",
                "COD": f"{r.original_cod}→0" if r.cod_changed else "0",
                "PO": f"❌ {r.po_value[:15]}" if r.po_invalid else (f"✓ {r.po_extracted}" if r.po_extracted else "-"),
                "Note": r.reason,
            })

        if simple_data:
            total_rows = len(simple_data)

            # Show simplified table
            st.dataframe(
                simple_data[:10],
                use_container_width=True,
                hide_index=True
            )
            if total_rows > 10:
                st.caption(f"Mostrate 10 di {total_rows} righe")

            st.caption("**Legenda:** ✓ OK | 🔄 Corretto | ⚠️ Da verificare")

            # Full detail in expander
            with st.expander(f"📋 Vista completa ({total_rows} righe)"):
                st.dataframe(
                    full_data,
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )

        # Downloads - now using pre-generated files from session state
        st.markdown("### 📥 Download")

        # Disable downloads if there are invalid POs (unless PIN bypass is active)
        download_disabled = report.po_invalid_count > 0 and not pin_valid
        if download_disabled:
            st.error("⛔ Download disabilitato: correggi prima i PO non validi nel file originale")

        col_dl1, col_dl2 = st.columns(2)

        with col_dl1:
            st.download_button(
                label="📄 Scarica File Corretto",
                data=results['corrected_excel'],
                file_name=f"indirizzi_corretti_{results['timestamp']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_corrected",
                disabled=download_disabled
            )

        with col_dl2:
            st.download_button(
                label="📋 Scarica Report Revisione",
                data=results['review_excel'],
                file_name=f"report_revisione_{results['timestamp']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_review",
                disabled=download_disabled
            )

        # Button to clear results and start over
        if st.button("🔄 Nuova validazione", use_container_width=True):
            st.session_state.zip_validation_results = None
            st.rerun()


def send_pickup_request(
    carrier: str,
    pickup_date: date,
    time_start: time,
    time_end: time,
    company: str,
    contact_name: str,
    address: str,
    zip_code: str,
    city: str,
    province: str,
    reference: str,
    num_packages: int,
    weight_per_package: float,
    length: float,
    width: float,
    height: float,
    use_pallet: bool,
    num_pallets: int,
    pallet_length: float,
    pallet_width: float,
    pallet_height: float,
    notes: str
) -> tuple[bool, str]:
    """
    Send pickup request via Zapier webhook.

    Returns:
        Tuple of (success, message)
    """
    # Calculate totals
    total_weight = num_packages * weight_per_package
    shipment_type = "FREIGHT" if total_weight > 70 else "NORMAL"
    package_volume = length * width * height / 1000000  # in cubic meters
    total_volume = package_volume * num_packages

    # Format date/time
    date_str = pickup_date.strftime("%d/%m/%Y")
    time_start_str = time_start.strftime("%H:%M")
    time_end_str = time_end.strftime("%H:%M")
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Build subject for email
    subject = f"{carrier} - {date_str} - {shipment_type}"

    # Build dimensions strings
    package_dimensions_str = f"{length} x {width} x {height} cm"
    pallet_dimensions_str = f"{pallet_length} x {pallet_width} x {pallet_height} cm" if use_pallet else "-"

    # Prepare payload for Zapier - all fields exposed individually
    payload = {
        # === Email/Meta fields ===
        "subject": subject,
        "timestamp": timestamp,
        "shipment_type": shipment_type,

        # === Carrier ===
        "carrier": carrier,

        # === Date/Time ===
        "pickup_date": date_str,
        "time_start": time_start_str,
        "time_end": time_end_str,
        "time_window": f"{time_start_str} - {time_end_str}",

        # === Address - Individual fields ===
        "company": company,
        "contact_name": contact_name,
        "address": address,
        "zip_code": zip_code,
        "city": city,
        "province": province,
        "reference": reference,
        # Address - Formatted
        "full_address": f"{address}, {zip_code} {city} ({province})",
        "address_line1": f"{company} - {contact_name}" if contact_name else company,
        "address_line2": f"{address}, {zip_code} {city} ({province})",

        # === Package Details - Individual fields ===
        "num_packages": num_packages,
        "weight_per_package": weight_per_package,
        "weight_per_package_str": f"{weight_per_package} kg",
        "package_length": length,
        "package_width": width,
        "package_height": height,
        # Package - Calculated
        "total_weight": total_weight,
        "total_weight_str": f"{total_weight:.1f} kg",
        "package_dimensions": package_dimensions_str,
        "package_volume_m3": round(package_volume, 3),
        "total_volume_m3": round(total_volume, 3),

        # === Pallet Details ===
        "use_pallet": use_pallet,
        "use_pallet_str": "Sì" if use_pallet else "No",
        "num_pallets": num_pallets if use_pallet else 0,
        "pallet_length": pallet_length if use_pallet else 0,
        "pallet_width": pallet_width if use_pallet else 0,
        "pallet_height": pallet_height if use_pallet else 0,
        "pallet_dimensions": pallet_dimensions_str,

        # === Notes ===
        "notes": notes if notes else "",
        "has_notes": bool(notes),

        # === Summary for email body ===
        "summary_packages": f"{num_packages} colli x {weight_per_package} kg = {total_weight:.1f} kg totali",
        "summary_dimensions": f"Dimensioni collo: {package_dimensions_str}",
        "summary_pallet": f"{num_pallets} pallet ({pallet_dimensions_str})" if use_pallet else "Nessun pallet"
    }

    try:
        # Get Zapier webhook URL from secrets
        webhook_url = get_secret("zapier", "webhook_url")
        if not webhook_url:
            return False, "Configurazione Zapier mancante. Aggiungi ZAPIER_WEBHOOK_URL nelle variabili d'ambiente."

        # Send POST request to Zapier
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            return True, "Richiesta inviata tramite Zapier"
        else:
            return False, f"Errore Zapier: HTTP {response.status_code}"

    except KeyError as e:
        return False, f"Configurazione mancante: {e}"
    except requests.exceptions.Timeout:
        return False, "Timeout connessione a Zapier"
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {str(e)}"
    except Exception as e:
        return False, f"Errore: {str(e)}"


def address_book_management():
    """Address book management UI (expander)."""
    with st.expander("📒 Gestione Rubrica Indirizzi", expanded=False):
        addresses = load_addresses()

        # Add new address form
        if st.session_state.get('show_add_address_form', False):
            st.markdown("#### ➕ Nuovo Indirizzo")
            with st.form("add_address_form"):
                new_name = st.text_input("Nome indirizzo *", placeholder="Es: Magazzino Bologna")
                new_company = st.text_input("Azienda *", value="Estée Lauder")
                new_contact_name = st.text_input("Nome e Cognome referente", placeholder="Mario Rossi")
                new_street = st.text_input("Indirizzo *", placeholder="Via Emilia 50")

                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    new_zip = st.text_input("CAP *", placeholder="40100", max_chars=5)
                with col2:
                    new_city = st.text_input("Città *", placeholder="Bologna")
                with col3:
                    new_province = st.text_input("Provincia", placeholder="BO", max_chars=2)

                new_reference = st.text_input("Telefono", placeholder="051 123456")
                new_is_default = st.checkbox("Imposta come predefinito")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.form_submit_button("💾 Salva", use_container_width=True):
                        if not new_name or not new_company or not new_street or not new_zip or not new_city:
                            st.error("❌ Compila tutti i campi obbligatori")
                        elif not new_zip.isdigit() or len(new_zip) != 5:
                            st.error("❌ CAP deve essere di 5 cifre")
                        else:
                            result = add_address(
                                name=new_name,
                                company=new_company,
                                contact_name=new_contact_name or "",
                                street=new_street,
                                zip_code=new_zip,
                                city=new_city,
                                province=new_province or "",
                                reference=new_reference or "",
                                is_default=new_is_default
                            )
                            if result:
                                st.session_state.show_add_address_form = False
                                st.success("✅ Indirizzo aggiunto!")
                                st.rerun()
                            else:
                                st.error("❌ Nome indirizzo già esistente")
                with col_cancel:
                    if st.form_submit_button("Annulla", use_container_width=True):
                        st.session_state.show_add_address_form = False
                        st.rerun()
        else:
            if st.button("➕ Aggiungi indirizzo", use_container_width=True):
                st.session_state.show_add_address_form = True
                st.rerun()

        # List existing addresses
        if addresses:
            st.markdown("---")
            for addr in addresses:
                with st.container():
                    col_info, col_actions = st.columns([3, 1])

                    with col_info:
                        prefix = "⭐" if addr.is_default else "📍"
                        default_label = " **(PREDEFINITO)**" if addr.is_default else ""
                        st.markdown(f"**{prefix} {addr.name}**{default_label}")
                        st.caption(f"{addr.company}")
                        if addr.contact_name:
                            st.caption(f"Referente: {addr.contact_name}")
                        st.caption(f"{addr.street}, {addr.zip} {addr.city} ({addr.province})")
                        if addr.reference:
                            st.caption(f"Tel: {addr.reference}")

                    with col_actions:
                        if not addr.is_default:
                            if st.button("⭐", key=f"default_{addr.id}", help="Imposta predefinito"):
                                set_default_address(addr.id)
                                st.rerun()
                        if len(addresses) > 1:
                            if st.button("🗑️", key=f"delete_{addr.id}", help="Elimina"):
                                delete_address(addr.id)
                                st.rerun()

                    st.markdown("---")


def pickup_request_page():
    """Page for Courier Pickup Request feature."""
    st.markdown("# 🚚 Richiesta Ritiro Corriere")
    st.markdown("*Richiedi un ritiro merce ai corrieri*")

    # User guide
    st.info(
        "**Come usare questo strumento:**\n"
        "- Seleziona un indirizzo dalla rubrica o inseriscine uno nuovo\n"
        "- Compila i dettagli del ritiro e invia la richiesta"
    )

    # Check if Supabase is configured
    if not is_sheets_configured():
        st.warning(
            "⚠️ **Rubrica non configurata**: La rubrica indirizzi richiede Supabase. "
            "Configura le credenziali in Streamlit Secrets per salvare gli indirizzi."
        )

    st.markdown("---")

    # Initialize session state
    if 'pickup_request_sent' not in st.session_state:
        st.session_state.pickup_request_sent = False
    if 'selected_address_id' not in st.session_state:
        default_addr = get_default_address()
        st.session_state.selected_address_id = default_addr.id if default_addr else None

    # Show success message and reset button if request was sent
    if st.session_state.pickup_request_sent:
        st.success("✅ Richiesta inviata con successo!")
        st.info("📧 Richiesta inviata tramite Zapier")
        if st.button("🔄 Nuova richiesta", use_container_width=True):
            st.session_state.pickup_request_sent = False
            st.rerun()
        return

    # Address book management (expander)
    address_book_management()

    # Load addresses for selection
    addresses = load_addresses()

    # Build address options for dropdown
    address_options = {get_address_display_name(addr): addr.id for addr in addresses}
    address_options["➕ Nuovo indirizzo (inserimento manuale)"] = "new"

    # Get current selection
    current_selection = None
    for display_name, addr_id in address_options.items():
        if addr_id == st.session_state.selected_address_id:
            current_selection = display_name
            break
    if current_selection is None:
        current_selection = list(address_options.keys())[0] if addresses else "➕ Nuovo indirizzo (inserimento manuale)"

    # Address selection (outside form for reactivity)
    st.markdown("### 📍 Indirizzo Ritiro")
    selected_display = st.selectbox(
        "Seleziona indirizzo:",
        options=list(address_options.keys()),
        index=list(address_options.keys()).index(current_selection) if current_selection in address_options else 0,
        key="address_selector"
    )
    selected_address_id = address_options[selected_display]
    st.session_state.selected_address_id = selected_address_id

    # Get selected address data
    selected_address = get_address_by_id(selected_address_id) if selected_address_id != "new" else None
    is_from_book = selected_address is not None

    # Show address preview if from book
    if is_from_book:
        st.info(f"📍 **{selected_address.company}** - {get_address_summary(selected_address)}")

    # Carrier selection (outside form for reactivity)
    st.markdown("### 🚛 Corriere")
    carrier = st.radio(
        "Seleziona il corriere:",
        options=["FedEx", "DHL", "UPS"],
        horizontal=True,
        key="carrier"
    )

    # Date and time section
    st.markdown("### 📅 Data e Orario")
    col_date, col_time_start, col_time_end = st.columns(3)

    with col_date:
        pickup_date = st.date_input(
            "Data ritiro *",
            value=date.today() + timedelta(days=1),
            min_value=date.today(),
            key="pickup_date"
        )

    with col_time_start:
        time_start = st.time_input(
            "Orario inizio *",
            value=time(9, 0),
            key="time_start"
        )

    with col_time_end:
        time_end = st.time_input(
            "Orario fine *",
            value=time(18, 0),
            key="time_end"
        )

    # Address fields - pre-filled if from book, editable if new
    st.markdown("### 📍 Dettagli Indirizzo")

    if is_from_book:
        st.caption("🔒 Indirizzo selezionato dalla rubrica")
        company = selected_address.company
        contact_name = selected_address.contact_name
        address = selected_address.street
        zip_code = selected_address.zip
        city = selected_address.city
        province = selected_address.province
        reference = selected_address.reference

        # Show read-only display using markdown (avoids caching issues with disabled inputs)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Azienda:** {company}")
            st.markdown(f"**Referente:** {contact_name if contact_name else '-'}")
            st.markdown(f"**Indirizzo:** {address}")
        with col2:
            st.markdown(f"**CAP / Città:** {zip_code} {city} ({province})")
            st.markdown(f"**Telefono:** {reference if reference else '-'}")
    else:
        company = st.text_input(
            "Azienda *",
            value="Estée Lauder",
            key="company"
        )

        contact_name = st.text_input(
            "Nome e Cognome referente",
            placeholder="Mario Rossi",
            key="contact_name"
        )

        address = st.text_input(
            "Indirizzo *",
            placeholder="Via Turati 3",
            key="address"
        )

        col_zip, col_city, col_province = st.columns([1, 2, 1])

        with col_zip:
            zip_code = st.text_input(
                "CAP *",
                placeholder="20121",
                max_chars=5,
                key="zip_code"
            )

        with col_city:
            city = st.text_input(
                "Città *",
                placeholder="Milano",
                key="city"
            )

        with col_province:
            province = st.text_input(
                "Provincia",
                placeholder="MI",
                max_chars=2,
                key="province"
            )

        reference = st.text_input(
            "Telefono",
            placeholder="02 1234567",
            key="reference"
        )

    # Package details section
    st.markdown("### 📦 Dettagli Colli")

    col_packages, col_weight = st.columns(2)

    with col_packages:
        num_packages = st.number_input(
            "Numero colli *",
            min_value=1,
            value=1,
            step=1,
            key="num_packages"
        )

    with col_weight:
        weight_per_package = st.number_input(
            "Peso singolo collo (kg) *",
            min_value=0.1,
            value=1.0,
            step=0.5,
            key="weight_per_package"
        )

    st.markdown("**Dimensioni singolo collo (cm):** *")
    col_l, col_w, col_h = st.columns(3)

    with col_l:
        length = st.number_input(
            "Lunghezza *",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key="length"
        )

    with col_w:
        width = st.number_input(
            "Larghezza *",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key="width"
        )

    with col_h:
        height = st.number_input(
            "Altezza *",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key="height"
        )

    # Pallet section
    st.markdown("### 🎨 Pallet")

    use_pallet = st.checkbox(
        "Raggruppamento su pallet",
        key="use_pallet"
    )

    num_pallets = 0
    pallet_length = 0.0
    pallet_width = 0.0
    pallet_height = 0.0

    if use_pallet:
        num_pallets = st.number_input(
            "Numero pallet *",
            min_value=1,
            value=1,
            step=1,
            key="num_pallets"
        )

        st.markdown("**Dimensioni pallet (cm):** *")
        col_pl, col_pw, col_ph = st.columns(3)

        with col_pl:
            pallet_length = st.number_input(
                "Lunghezza pallet *",
                min_value=0.0,
                value=120.0,  # Standard EUR pallet
                step=1.0,
                key="pallet_length"
            )

        with col_pw:
            pallet_width = st.number_input(
                "Larghezza pallet *",
                min_value=0.0,
                value=80.0,  # Standard EUR pallet
                step=1.0,
                key="pallet_width"
            )

        with col_ph:
            pallet_height = st.number_input(
                "Altezza pallet *",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key="pallet_height"
            )

    # Notes section
    st.markdown("### 📝 Note")
    notes = st.text_area(
        "Note aggiuntive",
        placeholder="Eventuali note per il corriere...",
        key="notes"
    )

    # Dynamic Summary section (outside form - updates in real-time)
    st.markdown("### 📊 Riepilogo")
    total_weight = num_packages * weight_per_package
    shipment_type = "FREIGHT" if total_weight > 70 else "NORMAL"

    col_summary1, col_summary2 = st.columns(2)
    with col_summary1:
        st.metric("Peso totale", f"{total_weight:.1f} kg")
    with col_summary2:
        st.metric("Tipo spedizione", f"{shipment_type}")

    if total_weight > 70:
        st.warning("⚠️ Peso superiore a 70 kg - Spedizione FREIGHT")

    # Submit button in a form for proper submission handling
    st.markdown("---")
    with st.form("pickup_request_form"):
        submitted = st.form_submit_button(
            "📧 Invia Richiesta",
            type="primary",
            use_container_width=True
        )

        if submitted:
            # Validation
            errors = []

            if not address:
                errors.append("Indirizzo obbligatorio")

            if not zip_code:
                errors.append("CAP obbligatorio")
            elif not zip_code.isdigit() or len(zip_code) != 5:
                errors.append("CAP deve essere di 5 cifre")

            if not city:
                errors.append("Città obbligatoria")

            if time_end <= time_start:
                errors.append("Orario fine deve essere successivo all'orario inizio")

            # Dimensions validation: all required
            if length <= 0:
                errors.append("Lunghezza collo obbligatoria")
            if width <= 0:
                errors.append("Larghezza collo obbligatoria")
            if height <= 0:
                errors.append("Altezza collo obbligatoria")

            # Pallet dimensions validation
            if use_pallet:
                if pallet_length <= 0:
                    errors.append("Lunghezza pallet obbligatoria")
                if pallet_width <= 0:
                    errors.append("Larghezza pallet obbligatoria")
                if pallet_height <= 0:
                    errors.append("Altezza pallet obbligatoria")

            if errors:
                for error in errors:
                    st.error(f"❌ {error}")
            else:
                # Send request via Zapier
                with st.spinner("Invio richiesta in corso..."):
                    success, message = send_pickup_request(
                        carrier=carrier,
                        pickup_date=pickup_date,
                        time_start=time_start,
                        time_end=time_end,
                        company=company,
                        contact_name=contact_name or "",
                        address=address,
                        zip_code=zip_code,
                        city=city,
                        province=province or "",
                        reference=reference or "",
                        num_packages=num_packages,
                        weight_per_package=weight_per_package,
                        length=length,
                        width=width,
                        height=height,
                        use_pallet=use_pallet,
                        num_pallets=num_pallets,
                        pallet_length=pallet_length,
                        pallet_width=pallet_width,
                        pallet_height=pallet_height,
                        notes=notes or ""
                    )

                if success:
                    st.session_state.pickup_request_sent = True
                    st.rerun()
                else:
                    st.error(f"❌ {message}")


def main():
    # Sidebar navigation
    st.sidebar.markdown("# 🛠️ ELC Tools")
    st.sidebar.markdown("Strumenti per la logistica Estée Lauder")
    st.sidebar.markdown("---")

    feature = st.sidebar.radio(
        "Seleziona funzionalità:",
        options=[
            "📦 Label Sorter",
            "📍 Address Validator",
            "🚚 Richiesta Ritiro"
        ],
        index=0,
        key="feature_selector"
    )

    st.sidebar.markdown("---")

    # Log viewer in sidebar (collapsible)
    with st.sidebar.expander("📋 Log Viewer", expanded=False):
        log_handler = get_streamlit_handler()
        logs = log_handler.get_logs()

        # Filter options
        log_level = st.selectbox(
            "Filtra per livello:",
            options=["Tutti", "DEBUG", "INFO", "WARNING", "ERROR"],
            index=0,
            key="log_level_filter"
        )

        if log_level != "Tutti":
            logs = [l for l in logs if l['level'] == log_level]

        # Display logs
        if logs:
            st.caption(f"Ultimi {len(logs)} log")
            for log in reversed(logs[-20:]):  # Show last 20
                level_color = {
                    'DEBUG': '🔵',
                    'INFO': '🟢',
                    'WARNING': '🟡',
                    'ERROR': '🔴'
                }.get(log['level'], '⚪')

                st.markdown(
                    f"<small>{level_color} <code>{log['timestamp'][-8:]}</code> "
                    f"<b>{log['module']}</b>: {log['message'][:80]}</small>",
                    unsafe_allow_html=True
                )

            if st.button("🗑️ Pulisci log", key="clear_logs"):
                log_handler.clear()
                st.rerun()
        else:
            st.info("Nessun log disponibile")

    st.sidebar.markdown(
        "<div style='font-size: 0.8rem; color: #888;'>"
        "ELC Tools v2.0<br>"
        "Estée Lauder Logistics"
        "</div>",
        unsafe_allow_html=True
    )

    # Route to selected feature
    if feature == "📦 Label Sorter":
        label_sorter_page()
    elif feature == "📍 Address Validator":
        zip_validator_page()
    elif feature == "🚚 Richiesta Ritiro":
        pickup_request_page()


if __name__ == "__main__":
    main()
