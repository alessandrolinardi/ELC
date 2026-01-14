"""
Sorter Module
Gestisce la logica di ordinamento delle etichette.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .matcher import MatchResult, MatchReport
from .excel_parser import ExcelData


class SortMethod(Enum):
    """Metodo di ordinamento disponibile."""
    EXCEL_ORDER = "excel_order"        # Segui ordine righe Excel
    ORDER_ID_NUMERIC = "order_id"      # Ordina per suffisso numerico Order ID


@dataclass
class SortedResult:
    """Risultato dell'ordinamento."""
    page_order: list[int]  # Indici delle pagine nel nuovo ordine (0-indexed)
    matched_count: int
    unmatched_count: int
    sort_method: SortMethod


class Sorter:
    """
    Ordina le pagine PDF secondo il metodo specificato.
    """

    def __init__(
        self,
        match_report: MatchReport,
        excel_data: ExcelData
    ):
        """
        Inizializza il sorter.

        Args:
            match_report: Report del matching
            excel_data: Dati Excel per riferimento ordine
        """
        self.match_report = match_report
        self.excel_data = excel_data

        # Crea indice tracking -> posizione Excel
        self._excel_order: dict[str, int] = {}
        for i, order in enumerate(excel_data.orders):
            self._excel_order[order.tracking] = i

    def sort(self, method: SortMethod) -> SortedResult:
        """
        Ordina le pagine secondo il metodo specificato.

        Args:
            method: Metodo di ordinamento

        Returns:
            SortedResult con l'ordine delle pagine
        """
        if method == SortMethod.EXCEL_ORDER:
            return self._sort_by_excel_order()
        elif method == SortMethod.ORDER_ID_NUMERIC:
            return self._sort_by_order_id()
        else:
            raise ValueError(f"Metodo di ordinamento non supportato: {method}")

    def _sort_by_excel_order(self) -> SortedResult:
        """
        Ordina seguendo l'ordine delle righe nell'Excel.

        Returns:
            SortedResult con pagine ordinate
        """
        matched = self.match_report.matched.copy()

        # Ordina per posizione nell'Excel
        def get_excel_position(result: MatchResult) -> int:
            if result.order and result.order.tracking:
                return self._excel_order.get(result.order.tracking, float('inf'))
            return float('inf')

        matched.sort(key=get_excel_position)

        # Costruisci l'ordine finale: matchati + non matchati
        page_order = [r.page_index for r in matched]
        page_order.extend(r.page_index for r in self.match_report.unmatched)

        return SortedResult(
            page_order=page_order,
            matched_count=len(matched),
            unmatched_count=len(self.match_report.unmatched),
            sort_method=SortMethod.EXCEL_ORDER
        )

    def _sort_by_order_id(self) -> SortedResult:
        """
        Ordina per suffisso numerico dell'Order ID.

        Returns:
            SortedResult con pagine ordinate
        """
        matched = self.match_report.matched.copy()

        # Separa quelli con suffisso numerico da quelli senza
        with_numeric: list[tuple[MatchResult, int]] = []
        without_numeric: list[tuple[MatchResult, str]] = []

        for result in matched:
            if result.order and result.order.numeric_suffix is not None:
                with_numeric.append((result, result.order.numeric_suffix))
            elif result.order:
                # Fallback: usa order_id per ordinamento alfabetico
                without_numeric.append((result, result.order.order_id))
            else:
                without_numeric.append((result, ""))

        # Ordina numericamente
        with_numeric.sort(key=lambda x: x[1])

        # Ordina alfabeticamente
        without_numeric.sort(key=lambda x: x[1])

        # Combina: prima numerici, poi alfabetici, infine non matchati
        page_order = [r.page_index for r, _ in with_numeric]
        page_order.extend(r.page_index for r, _ in without_numeric)
        page_order.extend(r.page_index for r in self.match_report.unmatched)

        return SortedResult(
            page_order=page_order,
            matched_count=len(matched),
            unmatched_count=len(self.match_report.unmatched),
            sort_method=SortMethod.ORDER_ID_NUMERIC
        )


def sort_pages(
    match_report: MatchReport,
    excel_data: ExcelData,
    method: SortMethod = SortMethod.EXCEL_ORDER
) -> SortedResult:
    """
    Funzione helper per ordinare le pagine.

    Args:
        match_report: Report del matching
        excel_data: Dati Excel
        method: Metodo di ordinamento

    Returns:
        SortedResult con l'ordine delle pagine
    """
    sorter = Sorter(match_report, excel_data)
    return sorter.sort(method)
