"""
ELC Tools - Estée Lauder Logistics
App Streamlit multi-funzione per la gestione delle spedizioni.
"""

import io
import csv
from datetime import datetime

import streamlit as st
import pandas as pd

from src.pdf_processor import PDFProcessor
from src.excel_parser import ExcelParser, ExcelParserError
from src.matcher import Matcher, UnmatchedReason
from src.sorter import Sorter, SortMethod
from src.zip_validator import ZipValidator, ValidationReport


# ============================================================================
# SECURITY LIMITS - Prevent abuse and DoS
# ============================================================================
MAX_FILE_SIZE_MB = 50  # Maximum file size in MB
MAX_PDF_PAGES = 500    # Maximum pages in PDF
MAX_EXCEL_ROWS = 1000  # Maximum rows in Excel for ZIP validation
MAX_ZIP_VALIDATIONS_PER_SESSION = 500  # Limit API calls to Nominatim


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
    st.markdown("---")

    # Initialize session state for persisting results
    if 'label_sorter_results' not in st.session_state:
        st.session_state.label_sorter_results = None

    # Sezione Upload
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📄 PDF Etichette")
        pdf_file = st.file_uploader(
            "Carica il PDF con le etichette",
            type=["pdf"],
            key="pdf_uploader",
            help="Un PDF con una etichetta per pagina (DHL, FedEx, UPS)",
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
        disabled=not (pdf_file and excel_file),
        use_container_width=True,
        key="label_sorter_process"
    )

    # Elaborazione
    if process_button and pdf_file and excel_file:
        # Security checks
        if not check_file_size(pdf_file, MAX_FILE_SIZE_MB):
            st.error(f"❌ File PDF troppo grande. Massimo: {MAX_FILE_SIZE_MB}MB")
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

                # Step 1: Leggi PDF
                with st.status("📄 Step 1/5: Lettura PDF...", expanded=True) as status:
                    st.write("Caricamento file PDF...")
                    pdf_bytes = pdf_file.read()
                    st.write(f"✓ File caricato: {len(pdf_bytes):,} bytes")

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
                        st.write(f"✓ Colonne: {', '.join(excel_data.columns_found[:5])}...")

                        if excel_data.orders:
                            first_orders = [(o.order_id, o.tracking) for o in excel_data.orders[:3]]
                            st.write(f"✓ Primi ordini: {first_orders}")

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
        else:
            st.success("🎉 Tutte le etichette sono state matchate!")

        # Button to clear results and start over
        if st.button("🔄 Nuova elaborazione", use_container_width=True, key="new_label_sort"):
            st.session_state.label_sorter_results = None
            st.rerun()


def zip_validator_page():
    """Page for ZIP Code Validator feature."""
    st.markdown("# 📍 ZIP Code Validator")
    st.markdown("*Valida e correggi i CAP negli indirizzi di spedizione*")

    # User guide
    st.info(
        "**Come usare questo strumento:**\n"
        "- Carica un file Excel con il formato corretto. "
        "[Scarica il template](https://docs.google.com/spreadsheets/d/1eKfU6G-wzpNa8HZDcuddpJAZHEzWUKJUFw-y5LFDKOU/edit?usp=sharing)\n"
        "- Al termine della validazione, scarica il file corretto e caricalo su ShippyPro"
    )

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

    # Settings
    col1, col2 = st.columns(2)

    with col1:
        confidence_threshold = st.slider(
            "Soglia confidenza per auto-correzione",
            min_value=50,
            max_value=100,
            value=90,
            step=5,
            help="ZIP corretti automaticamente solo se confidenza ≥ soglia"
        )

    with col2:
        country_filter = st.selectbox(
            "Filtra per paese",
            options=["Solo IT", "Tutti"],
            index=0,
            help="Attualmente la validazione supporta solo indirizzi italiani"
        )

    # Process button
    st.markdown("---")
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

        try:
            # Read Excel
            with st.status("📊 Lettura file...", expanded=True) as status:
                excel_bytes = excel_file.read()
                st.write(f"✓ File caricato: {len(excel_bytes):,} bytes")

                # Try to read with pandas
                try:
                    df = pd.read_excel(io.BytesIO(excel_bytes), engine='openpyxl')
                except:
                    try:
                        df = pd.read_excel(io.BytesIO(excel_bytes), engine='calamine')
                    except:
                        df = pd.read_excel(io.BytesIO(excel_bytes))

                st.write(f"✓ Righe trovate: {len(df)}")
                st.write(f"✓ Colonne: {', '.join(df.columns[:8].tolist())}...")

                # Security check: row limit for API calls
                if len(df) > MAX_EXCEL_ROWS:
                    st.error(f"❌ Troppe righe ({len(df)}). Massimo: {MAX_EXCEL_ROWS} per limitare chiamate API.")
                    st.info("💡 Suggerimento: dividi il file in batch più piccoli.")
                    st.stop()

                status.update(label=f"✅ File letto ({len(df)} righe)", state="complete")

            # Filter by country if needed
            if country_filter == "Solo IT":
                country_col = None
                for col in df.columns:
                    if col.lower().strip() in ['country', 'paese', 'nazione']:
                        country_col = col
                        break

                if country_col:
                    original_count = len(df)
                    df_filtered = df[df[country_col].str.upper().isin(['IT', 'ITALY'])]
                    if len(df_filtered) < len(df):
                        st.info(f"ℹ️ Filtrati {original_count - len(df_filtered)} indirizzi non italiani")
                    df = df_filtered

            if len(df) == 0:
                st.warning("⚠️ Nessun indirizzo italiano trovato nel file")
                st.stop()

            # Validate
            validator = ZipValidator(confidence_threshold=confidence_threshold)

            # Progress container
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(current, total, message):
                progress_bar.progress(current / total)
                status_text.text(f"⏳ {message} ({current}/{total})")

            with st.spinner(f"Validazione {len(df)} indirizzi... (circa {len(df) * 1.1:.0f} secondi)"):
                report = validator.process_dataframe(df, progress_callback=update_progress)

            progress_bar.progress(100)
            status_text.text("✅ Validazione completata!")

            # Re-read original file for corrected output
            excel_file.seek(0)
            original_df = pd.read_excel(excel_file)

            # Generate files and store in session state
            corrected_excel = validator.generate_corrected_excel(original_df, report)
            review_excel = validator.generate_review_report(report)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.session_state.zip_validation_results = {
                'report': report,
                'corrected_excel': corrected_excel,
                'review_excel': review_excel,
                'timestamp': timestamp
            }

        except Exception as e:
            st.error(f"❌ Errore: {str(e)}")
            st.exception(e)

    # Display results from session state (persists across reruns)
    if st.session_state.zip_validation_results:
        results = st.session_state.zip_validation_results
        report = results['report']

        st.markdown("---")
        st.markdown("## ✅ Risultato")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("✓ Validi", report.valid_count)

        with col2:
            st.metric("🔄 Corretti", report.corrected_count)

        with col3:
            st.metric("⚠️ Da rivedere", report.review_count)

        with col4:
            st.metric("⏭️ Saltati", report.skipped_count)

        # Preview changes
        if report.corrected_count > 0 or report.review_count > 0:
            st.markdown("### 📋 Dettaglio modifiche")

            preview_data = []
            for r in report.results:
                if not r.is_valid:
                    preview_data.append({
                        "Città": r.city[:20],
                        "Via": r.street[:25] + "..." if len(r.street) > 25 else r.street,
                        "ZIP Orig.": r.original_zip,
                        "ZIP Sugg.": r.suggested_zip or "-",
                        "Conf.": f"{r.confidence}%",
                        "Stato": "🔄 Corretto" if r.auto_corrected else "⚠️ Rivedere"
                    })

            if preview_data:
                PREVIEW_ROWS = 7
                total_rows = len(preview_data)

                if total_rows <= PREVIEW_ROWS:
                    # Show all rows if within limit
                    st.dataframe(preview_data, use_container_width=True, hide_index=True)
                else:
                    # Show preview with count
                    st.dataframe(preview_data[:PREVIEW_ROWS], use_container_width=True, hide_index=True)
                    st.caption(f"Mostrati {PREVIEW_ROWS} di {total_rows} record")

                    # Expandable full view
                    with st.expander(f"📋 Mostra tutti i {total_rows} record"):
                        st.dataframe(
                            preview_data,
                            use_container_width=True,
                            hide_index=True,
                            height=400  # Scrollable height
                        )

        # Downloads - now using pre-generated files from session state
        st.markdown("### 📥 Download")
        col_dl1, col_dl2 = st.columns(2)

        with col_dl1:
            st.download_button(
                label="📄 Scarica File Corretto",
                data=results['corrected_excel'],
                file_name=f"indirizzi_corretti_{results['timestamp']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_corrected"
            )

        with col_dl2:
            st.download_button(
                label="📋 Scarica Report Revisione",
                data=results['review_excel'],
                file_name=f"report_revisione_{results['timestamp']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_review"
            )

        # Button to clear results and start over
        if st.button("🔄 Nuova validazione", use_container_width=True):
            st.session_state.zip_validation_results = None
            st.rerun()


def main():
    # Sidebar navigation
    st.sidebar.markdown("# 🛠️ ELC Tools")
    st.sidebar.markdown("Strumenti per la logistica Estée Lauder")
    st.sidebar.markdown("---")

    feature = st.sidebar.radio(
        "Seleziona funzionalità:",
        options=[
            "📦 Label Sorter",
            "📍 ZIP Validator"
        ],
        index=0,
        key="feature_selector"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='font-size: 0.8rem; color: #888;'>"
        "ELC Tools v1.1<br>"
        "Estée Lauder Logistics"
        "</div>",
        unsafe_allow_html=True
    )

    # Route to selected feature
    if feature == "📦 Label Sorter":
        label_sorter_page()
    elif feature == "📍 ZIP Validator":
        zip_validator_page()


if __name__ == "__main__":
    main()
