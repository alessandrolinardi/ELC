"""
Excel Parser Module
Gestisce la lettura e il parsing dei file Excel/XLS da ShippyPro.
Supporta anche file HTML mascherati da XLS (export tipico di ShippyPro).
"""

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from io import BytesIO, StringIO

import pandas as pd

from .logging_config import get_logger

# Logger per questo modulo
logger = get_logger(__name__)


@dataclass
class OrderInfo:
    """Informazioni di un singolo ordine."""
    row_index: int  # Posizione nel file Excel (0-indexed)
    order_id: str   # ID Ordine Marketplace
    tracking: str   # Tracking normalizzato (senza spazi)
    carrier: str    # Corriere (MyDHL, FedEx, UPS)
    numeric_suffix: Optional[int] = None  # Suffisso numerico estratto


@dataclass
class ExcelData:
    """Dati estratti dal file Excel."""
    orders: list[OrderInfo]
    total_rows: int
    columns_found: list[str]
    warnings: list[str]
    # Debug info: quali colonne sono state effettivamente usate
    tracking_column_used: str = ""
    order_id_column_used: str = ""
    carrier_column_used: str = ""


class ExcelParserError(Exception):
    """Errore durante il parsing del file Excel."""
    pass


class ExcelParser:
    """
    Parser per file Excel/XLS da ShippyPro.
    Supporta formati .xlsx, .xls (legacy), e HTML mascherato da XLS.
    """

    # Nomi colonne attesi (case-insensitive)
    # IMPORTANTE: l'ordine conta - le prime corrispondenze hanno priorità
    COLUMN_MAPPINGS = {
        'order_id': ['id ordine marketplace', 'order id', 'id_ordine', 'orderid', 'id ordine'],
        'tracking': [
            # Nomi specifici tracking (priorità alta)
            'tracking', 'tracking number', 'trackingnumber', 'tracking_number',
            'n. spedizione', 'numero spedizione', 'n spedizione',
            'awb', 'waybill', 'lettera di vettura', 'ldv',
            'codice tracking', 'codice spedizione',
            'shipment number', 'shipment id',
            'n. tracking', 'numero tracking',
        ],
        'carrier': ['corriere', 'carrier', 'courier', 'vettore'],
    }

    # Colonne da escludere (NON sono tracking anche se contengono numeri)
    EXCLUDED_COLUMNS = [
        'telefono', 'phone', 'tel', 'mobile', 'cellulare',
        'fax', 'email', 'mail', 'e-mail',
        'cap', 'zip', 'postal', 'postcode',
        'peso', 'weight', 'kg',
        'prezzo', 'price', 'costo', 'cost', 'importo', 'amount',
        'quantità', 'quantity', 'qty',
    ]

    @staticmethod
    def normalize_tracking(tracking: str) -> str:
        """
        Normalizza il tracking rimuovendo tutti gli spazi.

        Args:
            tracking: Tracking number

        Returns:
            Tracking senza spazi, uppercase
        """
        if pd.isna(tracking):
            return ""
        return re.sub(r'\s+', '', str(tracking)).upper()

    @staticmethod
    def extract_numeric_suffix(order_id: str) -> Optional[int]:
        """
        Estrae il suffisso numerico dall'ID ordine.

        Esempio: "3501512414_ORIGINS_99" -> 99

        Args:
            order_id: ID ordine marketplace

        Returns:
            Suffisso numerico o None se non trovato
        """
        if pd.isna(order_id):
            return None

        order_str = str(order_id)

        # Cerca l'ultimo segmento dopo underscore
        parts = order_str.split('_')
        if len(parts) > 1:
            last_part = parts[-1]
            if last_part.isdigit():
                return int(last_part)

        # Fallback: cerca qualsiasi numero alla fine
        match = re.search(r'(\d+)$', order_str)
        if match:
            return int(match.group(1))

        return None

    def _is_excluded_column(self, column_name: str) -> bool:
        """
        Verifica se una colonna è nella lista di esclusione.

        Args:
            column_name: Nome della colonna

        Returns:
            True se la colonna deve essere esclusa
        """
        col_lower = column_name.lower().strip()
        for excluded in self.EXCLUDED_COLUMNS:
            if excluded in col_lower:
                return True
        return False

    def _find_column(self, df: pd.DataFrame, column_type: str) -> Optional[str]:
        """
        Trova la colonna corrispondente nel DataFrame.

        Args:
            df: DataFrame pandas
            column_type: Tipo di colonna da cercare

        Returns:
            Nome della colonna trovata o None
        """
        possible_names = self.COLUMN_MAPPINGS.get(column_type, [])
        df_columns_lower = {col.lower().strip(): col for col in df.columns}

        for name in possible_names:
            if name in df_columns_lower:
                found_col = df_columns_lower[name]
                # Per tracking, verifica che non sia una colonna esclusa
                if column_type == 'tracking' and self._is_excluded_column(found_col):
                    continue
                return found_col

        return None

    def _detect_file_type(self, file_bytes: bytes) -> str:
        """
        Rileva il tipo reale del file dai magic bytes.

        Args:
            file_bytes: Primi bytes del file

        Returns:
            Tipo di file: 'xlsx', 'xls', 'html', 'csv', 'unknown'
        """
        # Check magic bytes
        if file_bytes[:4] == b'PK\x03\x04':
            return 'xlsx'  # ZIP format (XLSX)
        elif file_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return 'xls'  # OLE2 format (XLS)
        elif file_bytes[:5].lower() in (b'<html', b'<!doc', b'<tabl', b'<?xml'):
            return 'html'
        elif b'<html' in file_bytes[:1000].lower() or b'<table' in file_bytes[:1000].lower():
            return 'html'
        elif b',' in file_bytes[:1000] and b'\n' in file_bytes[:1000]:
            return 'csv'
        else:
            return 'unknown'

    def _try_read_excel(
        self,
        file_input: bytes | BytesIO | str,
        filename: str
    ) -> pd.DataFrame:
        """
        Prova a leggere il file Excel con vari metodi.

        Args:
            file_input: File da leggere
            filename: Nome del file (per determinare il formato)

        Returns:
            DataFrame con i dati

        Raises:
            ExcelParserError: Se la lettura fallisce
        """
        errors = []

        # Prepara l'input
        if isinstance(file_input, bytes):
            file_bytes = file_input
        elif isinstance(file_input, BytesIO):
            file_input.seek(0)
            file_bytes = file_input.read()
            file_input.seek(0)
        else:
            with open(file_input, 'rb') as f:
                file_bytes = f.read()

        # Rileva tipo reale del file
        real_type = self._detect_file_type(file_bytes)

        # Metodo 1: Se è HTML (comune per ShippyPro export)
        if real_type == 'html':
            try:
                html_str = file_bytes.decode('utf-8', errors='ignore')
                dfs = pd.read_html(StringIO(html_str))
                if dfs and not dfs[0].empty:
                    return dfs[0]
            except Exception as e:
                errors.append(f"HTML: {str(e)}")

            # Prova con encoding diversi
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    html_str = file_bytes.decode(encoding, errors='ignore')
                    dfs = pd.read_html(StringIO(html_str))
                    if dfs and not dfs[0].empty:
                        return dfs[0]
                except Exception:
                    pass

        # Metodo 2: XLSX con openpyxl
        if real_type in ('xlsx', 'unknown'):
            try:
                df = pd.read_excel(BytesIO(file_bytes), engine='openpyxl')
                if not df.empty:
                    return df
            except Exception as e:
                errors.append(f"openpyxl: {str(e)}")

        # Metodo 3: XLS con xlrd
        if real_type in ('xls', 'unknown'):
            try:
                df = pd.read_excel(BytesIO(file_bytes), engine='xlrd')
                if not df.empty:
                    return df
            except Exception as e:
                errors.append(f"xlrd: {str(e)}")

        # Metodo 3a: Prova calamine (parser Rust, più robusto)
        if real_type in ('xls', 'xlsx', 'unknown'):
            try:
                df = pd.read_excel(BytesIO(file_bytes), engine='calamine')
                if not df.empty:
                    return df
            except Exception as e:
                errors.append(f"calamine: {str(e)}")

        # Metodo 3b: Prova openpyxl anche per XLS (a volte funziona)
        if real_type == 'xls':
            try:
                df = pd.read_excel(BytesIO(file_bytes), engine='openpyxl')
                if not df.empty:
                    return df
            except Exception as e:
                errors.append(f"openpyxl (xls fallback): {str(e)}")

        # Metodo 3c: Prova HTML per file XLS corrotti (comune con export web)
        if real_type == 'xls':
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    html_str = file_bytes.decode(encoding, errors='ignore')
                    dfs = pd.read_html(StringIO(html_str))
                    if dfs and not dfs[0].empty:
                        return dfs[0]
                except Exception:
                    pass
            errors.append("HTML (xls fallback): nessun encoding valido")

        # Metodo 4: CSV fallback
        if real_type in ('csv', 'unknown'):
            for sep in [',', ';', '\t']:
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        df = pd.read_csv(
                            BytesIO(file_bytes),
                            sep=sep,
                            encoding=encoding
                        )
                        if not df.empty and len(df.columns) > 1:
                            return df
                    except Exception:
                        pass
            errors.append("CSV: nessun formato valido trovato")

        # Metodo 5: Auto-detect pandas
        try:
            df = pd.read_excel(BytesIO(file_bytes))
            if not df.empty:
                return df
        except Exception as e:
            errors.append(f"auto: {str(e)}")

        # Metodo 6: Forza lettura HTML come ultima risorsa
        try:
            html_str = file_bytes.decode('utf-8', errors='replace')
            dfs = pd.read_html(StringIO(html_str))
            if dfs and not dfs[0].empty:
                return dfs[0]
        except Exception as e:
            errors.append(f"HTML fallback: {str(e)}")

        raise ExcelParserError(
            f"Impossibile leggere il file Excel.\n"
            f"Tipo rilevato: {real_type}\n"
            f"Errori:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    def _convert_with_libreoffice(self, filepath: str) -> pd.DataFrame:
        """
        Converte un file XLS legacy usando LibreOffice.

        Args:
            filepath: Path al file XLS

        Returns:
            DataFrame con i dati

        Raises:
            ExcelParserError: Se la conversione fallisce
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Converti a XLSX
            result = subprocess.run(
                [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'xlsx',
                    '--outdir', tmpdir,
                    filepath
                ],
                capture_output=True,
                timeout=30
            )

            if result.returncode != 0:
                raise ExcelParserError(
                    f"LibreOffice conversion failed: {result.stderr.decode()}"
                )

            # Trova il file convertito
            converted_files = list(Path(tmpdir).glob('*.xlsx'))
            if not converted_files:
                raise ExcelParserError("File XLSX non trovato dopo conversione")

            return pd.read_excel(converted_files[0], engine='openpyxl')

    def parse_excel(
        self,
        file_input: bytes | BytesIO | str,
        filename: str = "orders.xlsx"
    ) -> ExcelData:
        """
        Legge e parsa il file Excel degli ordini.

        Args:
            file_input: Contenuto del file o path
            filename: Nome del file (per determinare il formato)

        Returns:
            ExcelData con gli ordini estratti

        Raises:
            ExcelParserError: Se il file non può essere letto o mancano colonne
        """
        logger.info(f"Parsing Excel file: {filename}")
        warnings = []

        # Leggi il file
        df = self._try_read_excel(file_input, filename)
        logger.debug(f"DataFrame loaded: {len(df)} rows, columns: {df.columns.tolist()}")

        # Pulisci nomi colonne (rimuovi spazi extra, newlines)
        df.columns = [str(col).strip().replace('\n', ' ') for col in df.columns]

        # Trova le colonne necessarie
        order_id_col = self._find_column(df, 'order_id')
        tracking_col = self._find_column(df, 'tracking')
        carrier_col = self._find_column(df, 'carrier')

        logger.debug(f"Column mapping: order_id='{order_id_col}', tracking='{tracking_col}', carrier='{carrier_col}'")

        missing_cols = []
        if not order_id_col:
            missing_cols.append("ID Ordine Marketplace")
        if not tracking_col:
            missing_cols.append("Tracking")
        if not carrier_col:
            missing_cols.append("Corriere")

        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            raise ExcelParserError(
                f"Colonne mancanti nel file Excel: {', '.join(missing_cols)}.\n"
                f"Colonne trovate: {', '.join(df.columns.tolist())}"
            )

        # Estrai gli ordini
        orders = []
        empty_tracking_count = 0
        for idx, row in df.iterrows():
            tracking = self.normalize_tracking(row[tracking_col])

            if not tracking:
                empty_tracking_count += 1
                warnings.append(f"Riga {idx + 2}: tracking vuoto, ignorata")
                continue

            order_id = str(row[order_id_col]) if not pd.isna(row[order_id_col]) else ""
            carrier = str(row[carrier_col]) if not pd.isna(row[carrier_col]) else ""

            order = OrderInfo(
                row_index=idx,
                order_id=order_id,
                tracking=tracking,
                carrier=carrier,
                numeric_suffix=self.extract_numeric_suffix(order_id)
            )
            orders.append(order)

        if empty_tracking_count > 0:
            logger.warning(f"Skipped {empty_tracking_count} rows with empty tracking")

        logger.info(f"Excel parsing complete: {len(orders)} orders extracted from {len(df)} rows")

        return ExcelData(
            orders=orders,
            total_rows=len(df),
            columns_found=df.columns.tolist(),
            warnings=warnings,
            tracking_column_used=tracking_col or "",
            order_id_column_used=order_id_col or "",
            carrier_column_used=carrier_col or ""
        )


def parse_excel_file(
    file_input: bytes | BytesIO | str,
    filename: str = "orders.xlsx"
) -> ExcelData:
    """
    Funzione helper per parsare un file Excel.

    Args:
        file_input: Contenuto del file o path
        filename: Nome del file

    Returns:
        ExcelData con gli ordini estratti
    """
    parser = ExcelParser()
    return parser.parse_excel(file_input, filename)
