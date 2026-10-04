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


def today_madrid() -> date:
    return datetime.now(TZ).date()


def weekday_es(d: date) -> str:
    return WEEKDAYS_ES[d.weekday()]
