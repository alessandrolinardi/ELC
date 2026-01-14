"""
Label Sorter - Estée Lauder Logistics
App Streamlit per riordinamento etichette di spedizione PDF.
"""

import io
import csv
from datetime import datetime

import streamlit as st

from src.pdf_processor import PDFProcessor
from src.excel_parser import ExcelParser, ExcelParserError
from src.matcher import Matcher, UnmatchedReason
from src.sorter import Sorter, SortMethod


# Configurazione pagina
st.set_page_config(
    page_title="Label Sorter - Estée Lauder",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="collapsed"
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

    # Header
    writer.writerow([
        "Pagina Originale",
        "Tracking Estratto",
        "Corriere",
        "Motivo"
    ])

    # Righe non matchate
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


def main():
    # Header
    st.markdown("# 📦 Label Sorter")
    st.markdown("*Riordina le etichette di spedizione secondo l'ordine degli ordini*")
    st.markdown("---")

    # Sezione Upload
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📄 PDF Etichette")
        pdf_file = st.file_uploader(
            "Carica il PDF con le etichette",
            type=["pdf"],
            key="pdf_uploader",
            help="Un PDF con una etichetta per pagina (DHL, FedEx, UPS)"
        )

    with col2:
        st.markdown("### 📊 Excel Ordini")
        excel_file = st.file_uploader(
            "Carica il file Excel degli ordini",
            type=["xlsx", "xls"],
            key="excel_uploader",
            help="Export da ShippyPro con ID Ordine, Tracking, Corriere"
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
        key="sort_method"
    )

    # Bottone elabora
    st.markdown("---")
    process_button = st.button(
        "🚀 Elabora",
        type="primary",
        disabled=not (pdf_file and excel_file),
        use_container_width=True
    )

    # Elaborazione
    if process_button and pdf_file and excel_file:
        try:
            with st.spinner("Elaborazione in corso..."):
                # Inizializza processori
                pdf_processor = PDFProcessor()
                excel_parser = ExcelParser()

                # Step 1: Leggi PDF
                progress = st.progress(0, text="Lettura PDF...")
                pdf_bytes = pdf_file.read()
                pdf_data = pdf_processor.process_pdf(pdf_bytes)
                progress.progress(30, text=f"PDF letto: {pdf_data.total_pages} pagine")

                # Step 2: Leggi Excel
                progress.progress(40, text="Lettura Excel...")
                excel_bytes = excel_file.read()
                try:
                    excel_data = excel_parser.parse_excel(excel_bytes, excel_file.name)
                except ExcelParserError as e:
                    st.error(f"❌ Errore lettura Excel: {str(e)}")
                    return

                progress.progress(50, text=f"Excel letto: {len(excel_data.orders)} ordini")

                # Mostra warning Excel se presenti
                if excel_data.warnings:
                    with st.expander("⚠️ Avvisi lettura Excel"):
                        for warning in excel_data.warnings:
                            st.warning(warning)

                # Step 3: Matching
                progress.progress(60, text="Matching tracking...")
                matcher = Matcher(pdf_data, excel_data)
                match_report = matcher.match_all()
                progress.progress(70, text=f"Match completato: {match_report.match_rate}%")

                # Step 4: Ordinamento
                progress.progress(80, text="Ordinamento pagine...")
                sorter = Sorter(match_report, excel_data)
                sorted_result = sorter.sort(sort_method[1])

                # Step 5: Genera PDF riordinato
                progress.progress(90, text="Generazione PDF...")
                reordered_pdf = pdf_processor.reorder_pdf(
                    pdf_bytes,
                    sorted_result.page_order
                )

                progress.progress(100, text="Completato!")

            # Risultati
            st.markdown("---")
            st.markdown("## ✅ Risultato")

            # Statistiche
            col_stat1, col_stat2, col_stat3 = st.columns(3)

            with col_stat1:
                st.metric(
                    label="Etichette elaborate",
                    value=pdf_data.total_pages
                )

            with col_stat2:
                st.metric(
                    label="Matchate",
                    value=f"{sorted_result.matched_count} ({match_report.match_rate}%)"
                )

            with col_stat3:
                st.metric(
                    label="Non matchate",
                    value=sorted_result.unmatched_count
                )

            # Download buttons
            st.markdown("### 📥 Download")
            col_dl1, col_dl2 = st.columns(2)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            with col_dl1:
                st.download_button(
                    label="📄 Scarica PDF Riordinato",
                    data=reordered_pdf,
                    file_name=f"etichette_ordinate_{timestamp}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            with col_dl2:
                csv_report = generate_csv_report(match_report, sorted_result)
                st.download_button(
                    label="📋 Scarica Report CSV",
                    data=csv_report,
                    file_name=f"report_non_matchate_{timestamp}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Dettaglio non matchate
            if match_report.unmatched:
                st.markdown("### ⚠️ Etichette non matchate")
                st.markdown(
                    "*Queste etichette sono state inserite in fondo al PDF*"
                )

                # Tabella non matchate
                unmatched_data = []
                for result in match_report.unmatched:
                    unmatched_data.append({
                        "Pag.": result.page_number,
                        "Tracking estratto": result.tracking if result.tracking else "(non riconosciuto)",
                        "Corriere": result.carrier if result.carrier else "-",
                        "Motivo": result.unmatched_reason.value if result.unmatched_reason else "Sconosciuto"
                    })

                st.dataframe(
                    unmatched_data,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("🎉 Tutte le etichette sono state matchate!")

        except Exception as e:
            st.error(f"❌ Errore durante l'elaborazione: {str(e)}")
            st.exception(e)

    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #888; font-size: 0.8rem;'>"
        "Label Sorter v1.0 - Estée Lauder Logistics"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
