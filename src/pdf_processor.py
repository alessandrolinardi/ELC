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
    # Organizzati per priorità: prima i pattern più specifici, poi quelli generici
    PATTERNS = {
        'UPS': [
            # Pattern specifici UPS
            re.compile(r'TRACKING\s*#\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'TRACKING\s*NUMBER\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'1Z\s*[A-Z0-9]{6}\s*[A-Z0-9]{10}', re.IGNORECASE),
            re.compile(r'1Z[A-Z0-9]{16}', re.IGNORECASE),
        ],
        'FedEx': [
            # Pattern specifici FedEx
            re.compile(r'TRK#\s*\[?\d*\]?\s*([\d\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'TRACKING\s*(?:ID|#|NUMBER)?\s*:?\s*(\d[\d\s]{10,}?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'(\d{12,22})', re.IGNORECASE),  # FedEx 12-22 digits
            re.compile(r'(\d{4}\s+\d{4}\s+\d{4}(?:\s+\d{4})?)', re.IGNORECASE),  # Spaced format
        ],
        'DHL': [
            # Pattern specifici DHL
            re.compile(r'WAYBILL\s*:?\s*([\d\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'AWB\s*:?\s*([\d\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'SHIPMENT\s*(?:NUMBER|ID|#)?\s*:?\s*([\d\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
            re.compile(r'JD\d{18}', re.IGNORECASE),  # DHL JD format
            re.compile(r'(\d{10,11})', re.IGNORECASE),  # DHL 10-11 digits
        ],
    }

    # Pattern italiani per le etichette
    ITALIAN_PATTERNS = [
        re.compile(r'N\.?\s*SPEDIZIONE\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
        re.compile(r'LETTERA\s*(?:DI)?\s*VETTURA\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
        re.compile(r'CODICE\s*TRACCIAMENTO\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
        re.compile(r'SPEDIZIONE\s*N[°.]?\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
        re.compile(r'NUMERO\s*SPEDIZIONE\s*:?\s*([A-Z0-9\s]+?)(?:\s{2,}|\n|$)', re.IGNORECASE),
    ]

    # Pattern generico come fallback - cerca sequenze alfanumeriche tipiche di tracking
    GENERIC_PATTERNS = [
        # UPS format: 1Z + 16 chars
        re.compile(r'\b(1Z[A-Z0-9]{16})\b', re.IGNORECASE),
        # Long numeric sequences (12-22 digits) - common for FedEx, DHL
        re.compile(r'\b(\d{12,22})\b'),
        # JD + 18 digits (DHL eCommerce)
        re.compile(r'\b(JD\d{18})\b', re.IGNORECASE),
        # Alphanumeric with at least 10 chars near tracking keywords
        re.compile(r'(?:tracking|spedizione|waybill|awb)[^\n]{0,30}?([A-Z0-9]{10,20})', re.IGNORECASE),
    ]

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
        # Fase 1: Prova i pattern specifici per corriere
        for carrier, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    # Prendi il gruppo 1 se esiste, altrimenti gruppo 0
                    try:
                        tracking_raw = match.group(1)
                    except IndexError:
                        tracking_raw = match.group(0)
                    tracking = self.normalize_tracking(tracking_raw)
                    if self._validate_tracking(tracking, carrier):
                        return tracking, carrier

        # Fase 2: Prova i pattern italiani (corriere sconosciuto)
        for pattern in self.ITALIAN_PATTERNS:
            match = pattern.search(text)
            if match:
                tracking = self.normalize_tracking(match.group(1))
                carrier = self._detect_carrier_from_tracking(tracking)
                if len(tracking) >= 8:  # Minimo ragionevole
                    return tracking, carrier

        # Fase 3: Pattern generici come fallback
        for pattern in self.GENERIC_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    tracking_raw = match.group(1)
                except IndexError:
                    tracking_raw = match.group(0)
                tracking = self.normalize_tracking(tracking_raw)
                carrier = self._detect_carrier_from_tracking(tracking)
                if len(tracking) >= 10:  # Minimo per tracking generico
                    return tracking, carrier

        return None, None

    def _detect_carrier_from_tracking(self, tracking: str) -> Optional[str]:
        """
        Tenta di identificare il corriere dal formato del tracking.

        Args:
            tracking: Tracking normalizzato

        Returns:
            Nome del corriere o None
        """
        if tracking.startswith('1Z'):
            return 'UPS'
        elif tracking.startswith('JD'):
            return 'DHL'
        elif tracking.isdigit():
            if len(tracking) == 10 or len(tracking) == 11:
                return 'DHL'
            elif len(tracking) >= 12:
                return 'FedEx'
        return None

    def _is_phone_number(self, number: str) -> bool:
        """
        Verifica se un numero sembra essere un numero di telefono.

        Args:
            number: Numero da verificare

        Returns:
            True se sembra un numero di telefono
        """
        if not number or not number.isdigit():
            return False

        # Numeri di telefono italiani (con prefisso 39)
        # Formato: 39XXXXXXXXXX (12 cifre) o 39XXXXXXXXXXX (13 cifre)
        if number.startswith('39') and len(number) in [12, 13]:
            # Dopo il 39, i cellulari iniziano con 3
            if len(number) >= 3 and number[2] == '3':
                return True

        # Numeri di telefono senza prefisso internazionale
        # Cellulari italiani: 3XXXXXXXXX (10 cifre)
        if number.startswith('3') and len(number) == 10:
            return True

        return False

    def _validate_tracking(self, tracking: str, carrier: str) -> bool:
        """
        Validazione base del tracking number.
        Più permissiva per non escludere formati validi.

        Args:
            tracking: Tracking normalizzato
            carrier: Nome del corriere

        Returns:
            True se il tracking sembra valido
        """
        if not tracking:
            return False

        # Rimuovi caratteri non validi che potrebbero essere stati catturati
        tracking = re.sub(r'[^A-Z0-9]', '', tracking.upper())

        # Escludi numeri di telefono
        if self._is_phone_number(tracking):
            return False

        if not tracking:
            return False

        # Lunghezze minime per corriere (più permissive)
        min_lengths = {
            'UPS': 10,      # Può essere più corto in alcuni formati
            'FedEx': 10,    # Minimo ragionevole
            'DHL': 10,      # 10 cifre standard
        }

        min_len = min_lengths.get(carrier, 8)

        if carrier == 'UPS':
            # UPS tracking tipicamente inizia con 1Z, ma accetta altri formati
            if tracking.startswith('1Z'):
                return len(tracking) >= 18
            # Accetta anche altri formati UPS
            return len(tracking) >= min_len and tracking.isalnum()
        elif carrier == 'FedEx':
            # FedEx è tipicamente numerico ma può avere lettere in alcuni formati
            return len(tracking) >= min_len
        elif carrier == 'DHL':
            # DHL può essere numerico o iniziare con JD
            if tracking.startswith('JD'):
                return len(tracking) >= 10
            return len(tracking) >= min_len

        # Per corrieri non specificati, accetta qualsiasi tracking abbastanza lungo
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
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        try:
            # Usa select() che è MOLTO più veloce di insert_pdf in loop
            doc.select(page_order)

            # Salva in memoria (senza compressione pesante per velocità)
            output = BytesIO()
            doc.save(output, garbage=3, deflate=False)
            return output.getvalue()
        finally:
            doc.close()


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
