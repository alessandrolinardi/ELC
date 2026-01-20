"""
Matcher Module
Gestisce il matching tra tracking numbers estratti dai PDF e quelli dell'Excel.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .pdf_processor import PageInfo, PDFData
from .excel_parser import OrderInfo, ExcelData


class UnmatchedReason(Enum):
    """Motivo per cui un'etichetta non è stata matchata."""
    TRACKING_NOT_IN_EXCEL = "Tracking non trovato in Excel"
    TRACKING_NOT_RECOGNIZED = "Pattern tracking non identificato"
    EXTRACTION_ERROR = "Errore estrazione testo"


class MatchType(Enum):
    """Tipo di match trovato."""
    EXACT = "exact"              # Match esatto
    NORMALIZED = "normalized"    # Match dopo normalizzazione
    PARTIAL = "partial"          # Match parziale (subset)
    FUZZY = "fuzzy"              # Match fuzzy (1-2 digit differenza)
    NONE = "none"                # Nessun match


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
    match_type: MatchType = field(default=MatchType.NONE)
    match_confidence: int = 0  # 0-100


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

    # Soglia minima per match parziale (percentuale di sovrapposizione)
    PARTIAL_MATCH_MIN_OVERLAP = 0.8  # 80%

    # Soglia massima di differenze per fuzzy match
    FUZZY_MAX_DIFFERENCES = 2

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
        # Lista di tutti i tracking per fuzzy matching
        self._all_trackings: list[tuple[str, OrderInfo]] = []

        for order in excel_data.orders:
            if order.tracking:
                normalized = order.tracking.upper().replace(' ', '')

                # Indicizza varianti del tracking
                self._tracking_index[normalized] = order
                self._tracking_index[order.tracking] = order

                # Variante senza zeri iniziali (per alcuni sistemi)
                stripped = normalized.lstrip('0')
                if stripped and stripped != normalized:
                    self._tracking_index[stripped] = order

                # Salva per fuzzy matching
                self._all_trackings.append((normalized, order))

    def _count_differences(self, s1: str, s2: str) -> int:
        """
        Conta le differenze tra due stringhe della stessa lunghezza.

        Args:
            s1: Prima stringa
            s2: Seconda stringa

        Returns:
            Numero di caratteri diversi
        """
        if len(s1) != len(s2):
            return max(len(s1), len(s2))
        return sum(c1 != c2 for c1, c2 in zip(s1, s2))

    def _find_order_by_tracking(self, tracking: str) -> tuple[Optional[OrderInfo], MatchType, int]:
        """
        Cerca un ordine dato il tracking con diversi metodi di matching.

        Args:
            tracking: Tracking number normalizzato

        Returns:
            Tuple (OrderInfo, MatchType, confidence) - confidence è 0-100
        """
        if not tracking:
            return None, MatchType.NONE, 0

        tracking_normalized = tracking.upper().replace(' ', '')

        # 1. Match esatto (confidence 100%)
        if tracking_normalized in self._tracking_index:
            return self._tracking_index[tracking_normalized], MatchType.EXACT, 100

        # 2. Match senza zeri iniziali
        tracking_stripped = tracking_normalized.lstrip('0')
        if tracking_stripped and tracking_stripped in self._tracking_index:
            return self._tracking_index[tracking_stripped], MatchType.NORMALIZED, 98

        # 3. Match parziale SICURO (richiede almeno 80% di sovrapposizione)
        for excel_tracking, order in self._all_trackings:
            # PDF tracking contiene Excel tracking
            if tracking_normalized.endswith(excel_tracking):
                overlap = len(excel_tracking) / len(tracking_normalized)
                if overlap >= self.PARTIAL_MATCH_MIN_OVERLAP:
                    confidence = int(90 + (overlap - 0.8) * 50)  # 90-100 based on overlap
                    return order, MatchType.PARTIAL, min(confidence, 99)

            # Excel tracking contiene PDF tracking
            if excel_tracking.endswith(tracking_normalized):
                overlap = len(tracking_normalized) / len(excel_tracking)
                if overlap >= self.PARTIAL_MATCH_MIN_OVERLAP:
                    confidence = int(90 + (overlap - 0.8) * 50)
                    return order, MatchType.PARTIAL, min(confidence, 99)

        # 4. Fuzzy match (per errori di OCR o battitura - max 2 differenze)
        best_match = None
        best_confidence = 0

        for excel_tracking, order in self._all_trackings:
            # Solo se lunghezze simili (differenza max 1)
            len_diff = abs(len(tracking_normalized) - len(excel_tracking))
            if len_diff > 1:
                continue

            # Se stessa lunghezza, conta differenze dirette
            if len_diff == 0:
                differences = self._count_differences(tracking_normalized, excel_tracking)
                if differences <= self.FUZZY_MAX_DIFFERENCES:
                    # Confidence decresce con il numero di differenze
                    confidence = 95 - (differences * 10)  # 95% per 0 diff, 85% per 1, 75% per 2
                    if confidence > best_confidence:
                        best_match = order
                        best_confidence = confidence
            else:
                # Lunghezza diversa di 1: prova aggiungendo/rimuovendo un carattere
                shorter = tracking_normalized if len(tracking_normalized) < len(excel_tracking) else excel_tracking
                longer = excel_tracking if len(tracking_normalized) < len(excel_tracking) else tracking_normalized

                # Prova a trovare dove manca il carattere
                for i in range(len(longer)):
                    test = longer[:i] + longer[i+1:]
                    if test == shorter:
                        confidence = 80  # Manca un carattere
                        if confidence > best_confidence:
                            best_match = order
                            best_confidence = confidence
                        break

        if best_match:
            return best_match, MatchType.FUZZY, best_confidence

        return None, MatchType.NONE, 0

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
                unmatched_reason=UnmatchedReason.EXTRACTION_ERROR,
                match_type=MatchType.NONE,
                match_confidence=0
            )

        # Nessun tracking estratto
        if not page.tracking:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=None,
                carrier=page.carrier,
                matched=False,
                unmatched_reason=UnmatchedReason.TRACKING_NOT_RECOGNIZED,
                match_type=MatchType.NONE,
                match_confidence=0
            )

        # Cerca match nell'Excel
        order, match_type, confidence = self._find_order_by_tracking(page.tracking)

        if order:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=page.tracking,
                carrier=page.carrier,
                matched=True,
                order=order,
                match_type=match_type,
                match_confidence=confidence
            )
        else:
            return MatchResult(
                page_number=page.page_number,
                page_index=page.page_number - 1,
                tracking=page.tracking,
                carrier=page.carrier,
                matched=False,
                unmatched_reason=UnmatchedReason.TRACKING_NOT_IN_EXCEL,
                match_type=MatchType.NONE,
                match_confidence=0
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
