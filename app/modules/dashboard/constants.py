from typing import Final

TIMEZONE: Final = "America/Santiago"
CONTRACT_VERSION: Final = 1
DEFAULT_LIMIT: Final = 20
MAX_LIMIT: Final = 100
RANKING_LIMIT: Final = 5
RECURRENCE_HOURS: Final = 30 * 24
AGE_GROUPS: Final = ("HASTA_7_DIAS", "MAS_7_HASTA_28_DIAS", "MAS_28_DIAS")
WORKSHOP_GROUPS: Final = ("INTERNO_TEMUCO", "INTERNO_SANTIAGO", "EXTERNOS")
SELECTION_FIELDS: Final = {
    "taller": {"seleccion_grupo"},
    "antiguedad": {"seleccion_grupo"},
    "mecanico": {"seleccion_mecanico_id"},
    "bus_fallas": {"seleccion_bus_id"},
    "bus_visitas": {"seleccion_bus_id"},
    "visitas_bus": {"seleccion_bus_id"},
    "creadas": {"seleccion_semana"},
    "terminadas": {"seleccion_semana"},
    "reincidencias_bus": {"seleccion_bus_id", "seleccion_periodo"},
}
