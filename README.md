# Label Sorter - Estée Lauder Logistics

App web Streamlit per riordinare etichette di spedizione in PDF multi-pagina, basandosi su un file Excel di riferimento.

## Funzionalità

- **Caricamento PDF**: Supporta PDF con etichette DHL, FedEx e UPS (1 etichetta per pagina)
- **Caricamento Excel**: Supporta file .xlsx e .xls (export ShippyPro)
- **Estrazione tracking automatica**: Riconosce automaticamente i pattern tracking dei tre corrieri
- **Matching intelligente**: Associa le etichette PDF agli ordini Excel tramite tracking number
- **Due metodi di ordinamento**:
  - Segui ordine Excel (mantiene l'ordine delle righe)
  - Ordina per Order ID numerico (estrae il suffisso numerico)
- **Report dettagliato**: Genera report CSV delle etichette non matchate
- **Output PDF**: PDF riordinato con etichette non matchate in fondo

## Installazione

### Requisiti
- Python 3.10+
- pip

### Setup locale

```bash
# Clona il repository
git clone <repository-url>
cd label-sorter

# Crea ambiente virtuale (opzionale ma consigliato)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Installa dipendenze
pip install -r requirements.txt

# Avvia l'app
streamlit run app.py
```

### Deploy su Streamlit Cloud

1. Fai il push del codice su GitHub
2. Vai su [share.streamlit.io](https://share.streamlit.io)
3. Collega il repository
4. Seleziona `app.py` come entry point
5. Deploy!

## Utilizzo

1. **Carica il PDF** con le etichette di spedizione
2. **Carica l'Excel** degli ordini (export ShippyPro)
3. **Seleziona il metodo di ordinamento**:
   - *Segui ordine Excel*: le etichette seguiranno l'ordine delle righe nell'Excel
   - *Ordina per Order ID*: le etichette saranno ordinate per il numero finale dell'ID ordine
4. **Clicca "Elabora"**
5. **Scarica**:
   - Il PDF riordinato
   - Il report CSV delle etichette non matchate

## Formati supportati

### Pattern tracking riconosciuti

| Corriere | Pattern nel PDF | Esempio |
|----------|-----------------|---------|
| UPS | `TRACKING #: <numero>` | `TRACKING #: 1Z FC2 577 68 0034 1731` |
| FedEx | `TRK# [box] <numero>` | `TRK# [0881] 8878 9864 4283` |
| DHL | `WAYBILL <numero>` | `WAYBILL 63 3270 4114` |

### Colonne Excel richieste

| Colonna | Descrizione | Esempio |
|---------|-------------|---------|
| ID Ordine Marketplace | Identificativo ordine | `3501512414_ORIGINS_99` |
| Tracking | Numero tracking | `6332702261` |
| Corriere | Nome corriere | `MyDHL`, `FedEx`, `UPS` |

## Struttura progetto

```
label-sorter/
├── app.py                    # Entry point Streamlit
├── requirements.txt          # Dipendenze
├── .gitignore
├── README.md
├── src/
│   ├── __init__.py
│   ├── pdf_processor.py      # Estrazione tracking e manipolazione PDF
│   ├── excel_parser.py       # Lettura e parsing Excel
│   ├── matcher.py            # Logica di match tracking
│   └── sorter.py             # Logica di ordinamento
└── tests/
    ├── __init__.py
    ├── test_pdf_processor.py
    └── test_excel_parser.py
```

## Test

```bash
# Esegui tutti i test
pytest tests/ -v

# Esegui test specifici
pytest tests/test_pdf_processor.py -v
pytest tests/test_excel_parser.py -v
```

## Performance

- Ottimizzato per batch di 300-400 pagine PDF
- Target RAM: < 800MB per elaborazione
- Target tempo: < 2 minuti per 400 etichette
- Usa PyMuPDF (fitz) per performance ottimali

## Tecnologie

- **UI**: Streamlit >= 1.28.0
- **PDF**: PyMuPDF (fitz) >= 1.23.0
- **Excel**: pandas + openpyxl + xlrd
- **Testing**: pytest

## Licenza

Uso interno Estée Lauder Companies.
