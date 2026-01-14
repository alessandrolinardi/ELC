"""
Matcher Module
Gestisce il matching tra tracking numbers estratti dai PDF e quelli dell'Excel.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .pdf_processor import PageInfo, PDFData
from .excel_parser import OrderInfo, ExcelData


class UnmatchedReason(Enum):
    """Motivo per cui un'etichetta non è stata matchata."""
    TRACKING_NOT_IN_EXCEL = "Tracking non trovato in Excel"
    TRACKING_NOT_RECOGNIZED = "Pattern tracking non identificato"
    EXTRACTION_ERROR = "Errore estrazione testo"


@dataclass
class MatchResult:
    """Risultato del match per una singola pagina."""
    page_number: int         # Numero pagina PDF (1-indexed)
    page_index: int          # Indice pagina PDF (0-indexed)
    tracking: Optional[str]  # Tracking estratto
    carrier: Optional[str]   # Corriere identificato
    matched: bool            # Se è stato trovato match
    order: Optional[OrderInfo] = None  # Ordine corrispondente
    unmatched_reason: Optional[UnmatchedReason] = None


@dataclass
class MatchReport:
    """Report completo del matching."""
    matched: list[MatchResult]
    unmatched: list[MatchResult]
    total_pages: int
    match_rate: float  # Percentuale di match (0-100)


class Matcher:
    """
    Esegue il matching tra pagine PDF e ordini Excel.
    """

    def __init__(self, pdf_data: PDFData, excel_data: ExcelData):
        """
        Inizializza il matcher.

        Args:
            pdf_data: Dati estratti dal PDF
            excel_data: Dati estratti dall'Excel
        """
        self.pdf_data = pdf_data
        self.excel_data = excel_data

        # Costruisce un indice tracking -> ordine per match veloce
        self._tracking_index: dict[str, OrderInfo] = {}
        for order in excel_data.orders:
            if order.tracking:
                # Indicizza anche varianti del tracking
                self._tracking_index[order.tracking] = order
                # Alcune varianti comuni
                self._tracking_index[order.tracking.replace(' ', '')] = order

    def _find_order_by_tracking(self, tracking: str) -> Optional[OrderInfo]:
        """
        Cerca un ordine dato il tracking.

        Args:
            tracking: Tracking number normalizzato

        Returns:
            OrderInfo se trovato, None altrimenti
        """
        if not tracking:
            return None

        # Match esatto
        if tracking in self._tracking_index:
            return self._tracking_index[tracking]

        # Prova con varianti
        tracking_upper = tracking.upper()
        if tracking_upper in self._tracking_index:
            return self._tracking_index[tracking_upper]

        # Prova match parziale (tracking PDF potrebbe essere più lungo)
        for excel_tracking, order in self._tracking_index.items():
            if tracking.endswith(excel_tracking) or excel_tracking.endswith(tracking):
                return order

        return None

    def match_all(self) -> MatchReport:
        """
        Esegue il matching di tutte le pagine.

        Returns:
            MatchReport con i risultati
        """
        matched = []
        unmatched = []

        for page in self.pdf_data.pages:
            result = self._match_page(page)

            if result.matched:
                matched.append(result)
            else:
                unmatched.append(result)

        total = len(self.pdf_data.pages)
        match_rate = (len(matched) / total * 100) if total > 0 else 0

        return MatchReport(
            matched=matched,
            unmatched=unmatched,
            total_pages=total,
            match_rate=round(match_rate, 1)
        )

    def _match_page(self, page: PageInfo) -> MatchResult:
        """
        Esegue il matching per una singola pagina.

        Args:
            page: Informazioni della pagina

        Returns:
            MatchResult con il risultato
        """
        # Gestisci errori di estrazione
        if page.extraction_error:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=None,
                carrier=None,
                matched=False,
                unmatched_reason=UnmatchedReason.EXTRACTION_ERROR
            )

        # Nessun tracking estratto
        if not page.tracking:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=None,
                carrier=page.carrier,
                matched=False,
                unmatched_reason=UnmatchedReason.TRACKING_NOT_RECOGNIZED
            )

        # Cerca match nell'Excel
        order = self._find_order_by_tracking(page.tracking)

        if order:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=page.tracking,
                carrier=page.carrier,
                matched=True,
                order=order
            )
        else:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=page.tracking,
                carrier=page.carrier,
                matched=False,
                unmatched_reason=UnmatchedReason.TRACKING_NOT_IN_EXCEL
            )


def match_pdf_to_excel(pdf_data: PDFData, excel_data: ExcelData) -> MatchReport:
    """
    Funzione helper per eseguire il matching.

    Args:
        pdf_data: Dati dal PDF
        excel_data: Dati dall'Excel

    Returns:
        MatchReport con i risultati
    """
    matcher = Matcher(pdf_data, excel_data)
    return matcher.match_all()
