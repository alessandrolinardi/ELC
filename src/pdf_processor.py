"""
PDF Processor Module
Gestisce l'estrazione dei tracking number dalle etichette PDF.
Supporta i formati: DHL, FedEx, UPS.
"""

import re
from dataclasses import dataclass
from typing import Optional
from io import BytesIO

import fitz  # PyMuPDF


@dataclass
class PageInfo:
    """Informazioni estratte da una singola pagina PDF."""
    page_number: int  # 1-indexed
    tracking: Optional[str]
    carrier: Optional[str]
    raw_text: str
    extraction_error: Optional[str] = None


@dataclass
class PDFData:
    """Dati estratti da un intero PDF."""
    pages: list[PageInfo]
    total_pages: int
    pdf_bytes: bytes


class PDFProcessor:
    """
    Processa PDF di etichette di spedizione.
    Estrae tracking numbers da DHL, FedEx, UPS.
    """

    # Pattern per estrazione tracking - compilati per performance
    PATTERNS = {
        'UPS': re.compile(
            r'TRACKING\s*#\s*:\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)',
            re.IGNORECASE
        ),
        'FedEx': re.compile(
            r'TRK#\s*\[?\d+\]?\s*([\d\s]+?)(?:\s{2,}|\n|$)',
            re.IGNORECASE
        ),
        'DHL': re.compile(
            r'WAYBILL\s+([\d\s]+?)(?:\s{2,}|\n|$)',
            re.IGNORECASE
        ),
    }

    # Pattern alternativi per maggiore copertura
    ALT_PATTERNS = {
        'UPS': re.compile(
            r'1Z\s*[A-Z0-9\s]{15,}',
            re.IGNORECASE
        ),
        'FedEx': re.compile(
            r'\b(\d{4}\s*\d{4}\s*\d{4}\s*\d{4})\b'
        ),
        'DHL': re.compile(
            r'\b(\d{2}\s*\d{4}\s*\d{4})\b'
        ),
    }

    @staticmethod
    def normalize_tracking(tracking: str) -> str:
        """
        Normalizza il tracking rimuovendo tutti gli spazi.

        Args:
            tracking: Tracking number con possibili spazi

        Returns:
            Tracking number senza spazi
        """
        return re.sub(r'\s+', '', tracking).upper()

    def extract_tracking_from_text(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """
        Estrae il tracking number e identifica il corriere dal testo.

        Args:
            text: Testo estratto dalla pagina PDF

        Returns:
            Tuple (tracking_normalizzato, carrier) o (None, None) se non trovato
        """
        # Prova prima i pattern principali
        for carrier, pattern in self.PATTERNS.items():
            match = pattern.search(text)
            if match:
                tracking = self.normalize_tracking(match.group(1))
                # Validazione base del tracking
                if self._validate_tracking(tracking, carrier):
                    return tracking, carrier

        # Fallback ai pattern alternativi
        for carrier, pattern in self.ALT_PATTERNS.items():
            match = pattern.search(text)
            if match:
                tracking = self.normalize_tracking(match.group(0) if carrier == 'UPS' else match.group(1))
                if self._validate_tracking(tracking, carrier):
                    return tracking, carrier

        return None, None

    def _validate_tracking(self, tracking: str, carrier: str) -> bool:
        """
        Validazione base del tracking number.

        Args:
            tracking: Tracking normalizzato
            carrier: Nome del corriere

        Returns:
            True se il tracking sembra valido
        """
        if not tracking:
            return False

        # Lunghezze tipiche per corriere
        min_lengths = {
            'UPS': 18,      # 1Z + 16 caratteri
            'FedEx': 12,    # 12-15 cifre
            'DHL': 10,      # 10 cifre
        }

        min_len = min_lengths.get(carrier, 8)

        if carrier == 'UPS':
            # UPS tracking inizia con 1Z
            return tracking.startswith('1Z') and len(tracking) >= min_len
        elif carrier == 'FedEx':
            # FedEx è numerico
            return tracking.isdigit() and len(tracking) >= min_len
        elif carrier == 'DHL':
            # DHL è numerico
            return tracking.isdigit() and len(tracking) >= min_len

        return len(tracking) >= min_len

    def process_pdf(self, pdf_input: bytes | BytesIO | str) -> PDFData:
        """
        Processa un PDF ed estrae le informazioni da ogni pagina.

        Args:
            pdf_input: Bytes del PDF, BytesIO, o path al file

        Returns:
            PDFData con le informazioni estratte

        Raises:
            ValueError: Se il PDF non può essere aperto
        """
        try:
            if isinstance(pdf_input, str):
                doc = fitz.open(pdf_input)
                with open(pdf_input, 'rb') as f:
                    pdf_bytes = f.read()
            elif isinstance(pdf_input, BytesIO):
                pdf_bytes = pdf_input.getvalue()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            else:
                pdf_bytes = pdf_input
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Impossibile aprire il PDF: {str(e)}")

        pages = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                try:
                    # Estrai testo dalla pagina
                    text = page.get_text("text")

                    # Estrai tracking
                    tracking, carrier = self.extract_tracking_from_text(text)

                    page_info = PageInfo(
                        page_number=page_num + 1,  # 1-indexed
                        tracking=tracking,
                        carrier=carrier,
                        raw_text=text[:500]  # Limita per memoria
                    )

                except Exception as e:
                    page_info = PageInfo(
                        page_number=page_num + 1,
                        tracking=None,
                        carrier=None,
                        raw_text="",
                        extraction_error=str(e)
                    )

                pages.append(page_info)
        finally:
            doc.close()

        return PDFData(
            pages=pages,
            total_pages=len(pages),
            pdf_bytes=pdf_bytes
        )

    def reorder_pdf(
        self,
        pdf_bytes: bytes,
        page_order: list[int]
    ) -> bytes:
        """
        Riordina le pagine di un PDF secondo l'ordine specificato.

        Args:
            pdf_bytes: PDF originale come bytes
            page_order: Lista di indici pagina (0-indexed) nel nuovo ordine

        Returns:
            Nuovo PDF con pagine riordinate come bytes
        """
        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        new_doc = fitz.open()

        try:
            for page_idx in page_order:
                new_doc.insert_pdf(src_doc, from_page=page_idx, to_page=page_idx)

            # Salva in memoria
            output = BytesIO()
            new_doc.save(output, garbage=4, deflate=True)
            return output.getvalue()
        finally:
            src_doc.close()
            new_doc.close()


def extract_tracking_from_page(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Funzione helper per estrarre tracking da una singola pagina.

    Args:
        text: Testo della pagina

    Returns:
        Tuple (tracking, carrier) o (None, None)
    """
    processor = PDFProcessor()
    return processor.extract_tracking_from_text(text)
