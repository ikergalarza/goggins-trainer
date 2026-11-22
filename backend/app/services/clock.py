"""Fecha "de verdad" del atleta.

El servidor (Railway) corre en UTC, pero el atleta vive en España: entre las
00:00 y las 02:00 españolas, date.today() del servidor todavía es AYER. Todo
lo que razone sobre "hoy" (el chat de Goggins, la colocación de semanas del
plan) debe usar esta fecha, no la del sistema.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")

WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def now_madrid() -> datetime:
    return datetime.now(TZ)


def today_madrid() -> date:
    return now_madrid().date()


def to_madrid(dt: datetime) -> datetime:
    """Pasa un datetime a hora española. Los naive (SQLite en tests) se toman como UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ)


def weekday_es(d: date) -> str:
    return WEEKDAYS_ES[d.weekday()]
