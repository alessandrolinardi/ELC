"""
Logging Configuration Module
Configura il logging centralizzato per l'applicazione ELC Tools.
"""

import logging
import sys
from io import StringIO
from typing import Optional


class StreamlitLogHandler(logging.Handler):
    """
    Custom handler che salva i log in un buffer per visualizzazione in Streamlit.
    """

    def __init__(self, max_records: int = 500):
        super().__init__()
        self.log_buffer: list[dict] = []
        self.max_records = max_records

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = {
                'timestamp': self.formatter.formatTime(record) if self.formatter else '',
                'level': record.levelname,
                'module': record.module,
                'message': record.getMessage(),
                'func': record.funcName,
                'line': record.lineno
            }
            self.log_buffer.append(log_entry)

            # Mantieni solo gli ultimi N record
            if len(self.log_buffer) > self.max_records:
                self.log_buffer = self.log_buffer[-self.max_records:]
        except Exception:
            self.handleError(record)

    def get_logs(self, level: Optional[str] = None) -> list[dict]:
        """
        Restituisce i log, opzionalmente filtrati per livello.

        Args:
            level: Filtra per livello (DEBUG, INFO, WARNING, ERROR)

        Returns:
            Lista di log entries
        """
        if level:
            return [log for log in self.log_buffer if log['level'] == level]
        return self.log_buffer.copy()

    def clear(self) -> None:
        """Pulisce il buffer dei log."""
        self.log_buffer.clear()


# Singleton per lo Streamlit handler
_streamlit_handler: Optional[StreamlitLogHandler] = None


def get_streamlit_handler() -> StreamlitLogHandler:
    """Restituisce il singleton StreamlitLogHandler."""
    global _streamlit_handler
    if _streamlit_handler is None:
        _streamlit_handler = StreamlitLogHandler()
        _streamlit_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
    return _streamlit_handler


def setup_logging(
    level: int = logging.INFO,
    enable_console: bool = True,
    enable_streamlit: bool = True
) -> None:
    """
    Configura il logging per l'applicazione.

    Args:
        level: Livello di logging (default: INFO)
        enable_console: Abilita output su console (default: True)
        enable_streamlit: Abilita buffer per Streamlit UI (default: True)
    """
    # Configura il root logger per il package src
    root_logger = logging.getLogger('src')
    root_logger.setLevel(level)

    # Rimuovi handler esistenti per evitare duplicati
    root_logger.handlers.clear()

    # Formatter comune
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Streamlit buffer handler
    if enable_streamlit:
        st_handler = get_streamlit_handler()
        st_handler.setLevel(level)
        st_handler.setFormatter(formatter)
        root_logger.addHandler(st_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Ottiene un logger per un modulo specifico.

    Args:
        name: Nome del modulo (es. 'src.pdf_processor')

    Returns:
        Logger configurato
    """
    return logging.getLogger(name)


# Livelli di log come costanti per comodità
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
