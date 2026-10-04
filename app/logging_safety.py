"""Defence in depth for the logs: no article text in any log line.

The app never logs request bodies, and uvicorn's access log writes the method, path and status only. This module guards
against a future mistake (an exception message or a log call that carries a piece of an article): any run of Arabic text
with more than ``MAX_ARABIC_LETTERS`` letters in a log message, its arguments or its traceback is replaced by a marker that
gives only its length. Percent-encoded Arabic (a query string in the access log) is decoded before the check.

It is installed twice: as a log-record factory (so every record is scrubbed when it is created, whatever handler later
writes it) and as a filter on the root and uvicorn handlers that exist when the app starts.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote_plus

MAX_ARABIC_LETTERS = 20

# Arabic letters, marks and presentation forms; a run may contain spaces, tatweel, joiners and Arabic punctuation between words.
_AR = "؀-ۿݐ-ݿࡰ-ࣿﭐ-﷿ﹰ-ﻼ"
_RUN = re.compile(f"[{_AR}](?:[{_AR}\\s‌-‏«»﴾﴿.,:!()\\-]*[{_AR}])?")
_LETTER = re.compile("[ء-غف-يٱ-ۓەݐ-ݿﭐ-﷿ﹰ-ﻼ]")


def _redact_runs(text: str) -> str:
    def repl(m: re.Match) -> str:
        letters = len(_LETTER.findall(m.group(0)))
        return f"[Arabic text removed: {letters} letters]" if letters > MAX_ARABIC_LETTERS else m.group(0)

    return _RUN.sub(repl, text)


def scrub(text: str) -> str:
    """``text`` with every long Arabic run replaced; percent-encoded Arabic is decoded first so it is caught too."""
    out = _redact_runs(text)
    if "%" in out:
        decoded = unquote_plus(out)  # a query string encodes spaces as +
        red = _redact_runs(decoded)
        if red != decoded:
            return red
    return out


def has_article_text(text: str) -> bool:
    return scrub(text) != text


def _scrub_arg(arg):
    if isinstance(arg, str):
        return scrub(arg)
    if isinstance(arg, (int, float, bool)) or arg is None:
        return arg
    text = str(arg)
    red = scrub(text)
    return red if red != text else arg


def scrub_record(record: logging.LogRecord) -> logging.LogRecord:
    """Scrub ``record`` in place (message, arguments, traceback, stack). Keeps the shape of ``args`` (uvicorn's access
    formatter unpacks a 5-tuple)."""
    try:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_scrub_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _scrub_arg(v) for k, v in record.args.items()}
        if record.exc_info and record.exc_info[0] is not None:
            text = logging.Formatter().formatException(record.exc_info)
            red = scrub(text)
            if red != text:  # the traceback carries text: keep the redacted copy only
                record.exc_text = red
                record.exc_info = None
        elif record.exc_text:
            record.exc_text = scrub(record.exc_text)
        if record.stack_info:
            record.stack_info = scrub(record.stack_info)
        # last check on the final message (an argument object whose str() is long text, a %-format that joins pieces)
        message = record.getMessage()
        if scrub(message) != message:
            record.msg, record.args = scrub(message), ()
    except Exception:  # never let the scrubber break logging; drop the content instead
        record.msg, record.args, record.exc_info, record.exc_text = "[log record removed by the scrubber]", (), None, None
    return record


class ArticleTextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        scrub_record(record)
        return True


_FILTER = ArticleTextFilter()
_installed_factory = False


def install() -> None:
    """Install the record factory once, and the filter on the handlers of the root and uvicorn loggers (idempotent)."""
    global _installed_factory
    if not _installed_factory:
        previous = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            return scrub_record(previous(*args, **kwargs))

        logging.setLogRecordFactory(factory)
        _installed_factory = True
    for name in (None, "uvicorn", "uvicorn.error", "uvicorn.access", "auditor"):
        logger = logging.getLogger(name)
        for handler in logger.handlers:
            if _FILTER not in handler.filters:
                handler.addFilter(_FILTER)
