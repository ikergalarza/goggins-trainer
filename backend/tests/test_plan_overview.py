"""Resumen del plan por semanas, calculado en el SERVIDOR.

Goggins contaba las sesiones por semana a mano y se equivocaba ("semana 7 dic:
sim 12 + stations 17 = 2 Hyrox" cuando el 17 cae en la semana siguiente), así
que daba por cumplida una regla que no lo estaba. Ahora cuenta el servidor.
"""
from datetime import date

from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import plan_overview as po


def _w(db, user, dia, tipo, status=WorkoutStatus.planned):
    w = Workout(user_id=user.id, date=dia, type=tipo, status=status, day_of_week=dia.weekday())
    db.add(w); db.commit(); db.refresh(w)
    return w


def test_cada_tipo_cae_en_su_categoria():
    assert po.category_of("hyrox_stations") == "hyrox"
    assert po.category_of("hyrox_sim") == "hyrox"
    for t in ("easy_run", "tempo", "intervals", "long_run", "recovery", "fartlek", "hill_repeats"):
        assert po.category_of(t) == "run", t
    for t in ("strength_upper", "strength_lower", "strength_full"):
        assert po.category_of(t) == "strength", t
    assert po.category_of("mobility") == "mobility"
    assert po.category_of("race") == "race"
    assert po.category_of("rest") == "rest"
    assert po.category_of("swim") == "other"


def test_las_semanas_son_de_lunes_a_domingo_y_no_se_mezclan(db, user):
    # El caso real: el simulacro del sábado 12 y las estaciones del jueves 17 NO son la misma semana.
    _w(db, user, date(2026, 12, 12), WorkoutType.hyrox_sim)
    _w(db, user, date(2026, 12, 17), WorkoutType.hyrox_stations)
    weeks = po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 20))
    assert [(w["week_start"], w["counts"]["hyrox"]) for w in weeks] == [("2026-12-07", 1), ("2026-12-14", 1)]


def test_domingo_y_lunes_van_a_semanas_distintas(db, user):
    _w(db, user, date(2026, 12, 13), WorkoutType.hyrox_stations)   # domingo
    _w(db, user, date(2026, 12, 14), WorkoutType.hyrox_stations)   # lunes siguiente
    weeks = po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 20))
    assert [w["counts"]["hyrox"] for w in weeks] == [1, 1]


def test_cuenta_lo_planificado_y_lo_completado_pero_no_lo_saltado(db, user):
    _w(db, user, date(2026, 12, 8), WorkoutType.hyrox_stations, WorkoutStatus.planned)
    _w(db, user, date(2026, 12, 9), WorkoutType.hyrox_stations, WorkoutStatus.completed)
    _w(db, user, date(2026, 12, 10), WorkoutType.hyrox_stations, WorkoutStatus.skipped)
    assert po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 13))[0]["counts"]["hyrox"] == 2


def test_un_rango_parcial_se_amplia_a_semanas_completas(db, user):
    _w(db, user, date(2026, 12, 7), WorkoutType.easy_run)          # lunes, fuera del rango pedido
    weeks = po.overview(db, user.id, date(2026, 12, 10), date(2026, 12, 11))
    assert len(weeks) == 1 and weeks[0]["week_start"] == "2026-12-07" and weeks[0]["counts"]["run"] == 1


def test_semanas_vacias_tambien_salen(db, user):
    weeks = po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 27))
    assert [w["week_start"] for w in weeks] == ["2026-12-07", "2026-12-14", "2026-12-21"]
    assert all(w["counts"]["hyrox"] == 0 and w["total"] == 0 for w in weeks)


def test_dias_libres_y_sesiones_legibles(db, user):
    w = _w(db, user, date(2026, 12, 9), WorkoutType.tempo)
    semana = po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 13))[0]
    assert semana["free_weekdays"] == ["lunes", "martes", "jueves", "viernes", "sábado", "domingo"]
    assert semana["sessions"] == [f"miércoles 9 · tempo · id {w.id}"]


def test_la_linea_resumen_dice_lo_que_importa(db, user):
    _w(db, user, date(2026, 12, 8), WorkoutType.easy_run)
    _w(db, user, date(2026, 12, 12), WorkoutType.hyrox_sim)
    linea = po.week_line(po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 13))[0])
    assert linea.startswith("2026-12-07")
    assert "hyrox 1" in linea and "run 1" in linea and "fuerza 0" in linea and "total 2" in linea


def test_no_mezcla_entrenos_de_otro_usuario(db, user, other_user):
    _w(db, other_user, date(2026, 12, 8), WorkoutType.hyrox_stations)
    assert po.overview(db, user.id, date(2026, 12, 7), date(2026, 12, 13))[0]["total"] == 0
