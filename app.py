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
        index=1,  # Default: Order ID numerico
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
        # Container per i log di debug
        status_container = st.container()

        with status_container:
            st.markdown("### 🔄 Elaborazione in corso...")

            try:
                # Inizializza processori
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

                    # Mostra primi tracking estratti
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

                        # Mostra primi ordini
                        if excel_data.orders:
                            first_orders = [(o.order_id, o.tracking) for o in excel_data.orders[:3]]
                            st.write(f"✓ Primi ordini: {first_orders}")

                        status.update(label=f"✅ Step 2/5: Excel letto ({len(excel_data.orders)} ordini)", state="complete")
                    except ExcelParserError as e:
                        status.update(label="❌ Step 2/5: Errore lettura Excel", state="error")
                        st.error(f"Errore: {str(e)}")
                        st.stop()

                # Mostra warning Excel se presenti
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

            except Exception as e:
                st.error(f"❌ Errore durante l'elaborazione: {str(e)}")
                st.exception(e)
                st.stop()

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
