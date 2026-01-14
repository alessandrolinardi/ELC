"""
Excel Parser Module
Gestisce la lettura e il parsing dei file Excel/XLS da ShippyPro.
"""

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from io import BytesIO

import pandas as pd


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


class ExcelParserError(Exception):
    """Errore durante il parsing del file Excel."""
    pass


class ExcelParser:
    """
    Parser per file Excel/XLS da ShippyPro.
    Supporta formati .xlsx e .xls (legacy).
    """

    # Nomi colonne attesi (case-insensitive)
    COLUMN_MAPPINGS = {
        'order_id': ['id ordine marketplace', 'order id', 'id_ordine', 'orderid', 'id ordine'],
        'tracking': ['tracking', 'tracking number', 'trackingnumber', 'tracking_number'],
        'carrier': ['corriere', 'carrier', 'courier', 'vettore'],
    }

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
                return df_columns_lower[name]

        return None

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

        # Prepara l'input per pandas
        if isinstance(file_input, bytes):
            input_data = BytesIO(file_input)
        elif isinstance(file_input, BytesIO):
            input_data = file_input
            input_data.seek(0)
        else:
            input_data = file_input

        is_xls = filename.lower().endswith('.xls')

        # Metodo 1: openpyxl (per xlsx)
        if not is_xls:
            try:
                if isinstance(input_data, BytesIO):
                    input_data.seek(0)
                df = pd.read_excel(input_data, engine='openpyxl')
                if not df.empty:
                    return df
            except Exception as e:
                errors.append(f"openpyxl: {str(e)}")

        # Metodo 2: xlrd (per xls legacy)
        try:
            if isinstance(input_data, BytesIO):
                input_data.seek(0)
            df = pd.read_excel(input_data, engine='xlrd')
            if not df.empty:
                return df
        except Exception as e:
            errors.append(f"xlrd: {str(e)}")

        # Metodo 3: Conversione con LibreOffice (solo per file su disco)
        if isinstance(file_input, str) and Path(file_input).exists():
            try:
                df = self._convert_with_libreoffice(file_input)
                if not df.empty:
                    return df
            except Exception as e:
                errors.append(f"LibreOffice: {str(e)}")

        # Metodo 4: Fallback con engine=None (auto-detect)
        try:
            if isinstance(input_data, BytesIO):
                input_data.seek(0)
            df = pd.read_excel(input_data)
            if not df.empty:
                return df
        except Exception as e:
            errors.append(f"auto: {str(e)}")

        raise ExcelParserError(
            f"Impossibile leggere il file Excel. Errori:\n" +
            "\n".join(f"  - {e}" for e in errors)
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
        warnings = []

        # Leggi il file
        df = self._try_read_excel(file_input, filename)

        # Trova le colonne necessarie
        order_id_col = self._find_column(df, 'order_id')
        tracking_col = self._find_column(df, 'tracking')
        carrier_col = self._find_column(df, 'carrier')

        missing_cols = []
        if not order_id_col:
            missing_cols.append("ID Ordine Marketplace")
        if not tracking_col:
            missing_cols.append("Tracking")
        if not carrier_col:
            missing_cols.append("Corriere")

        if missing_cols:
            raise ExcelParserError(
                f"Colonne mancanti nel file Excel: {', '.join(missing_cols)}.\n"
                f"Colonne trovate: {', '.join(df.columns.tolist())}"
            )

        # Estrai gli ordini
        orders = []
        for idx, row in df.iterrows():
            tracking = self.normalize_tracking(row[tracking_col])

            if not tracking:
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

        return ExcelData(
            orders=orders,
            total_rows=len(df),
            columns_found=df.columns.tolist(),
            warnings=warnings
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
