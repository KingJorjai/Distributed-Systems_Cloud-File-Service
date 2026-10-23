"""User-facing protocol error messages shared by the CLI and GUI."""

ER_MSG = (
    "Correcto.",
    "Comando desconocido o inesperado.",
    "Usuario desconocido.",
    "Clave de paso o password incorrecto.",
    "Error al crear la lista de ficheros.",
    "El fichero no existe.",
    "Error al bajar el fichero.",
    "Un usuario anonimo no tiene permisos para esta operacion.",
    "El fichero es demasiado grande.",
    "Error al preparar el fichero para subirlo.",
    "Error al subir el fichero.",
    "Error al borrar el fichero.",
    "No hay quórum suficiente para confirmar la operación.",
    "Este servidor no es el primario.",
    "No se puede compartir un fichero con uno mismo.",
    "El registro está desactivado.",
    "Datos de registro no válidos.",
    "El usuario está deshabilitado.",
    "El usuario ya existe.",
    "La línea del protocolo es demasiado larga.",
    "Conflicto de revisión.",
)


def message(code):
    try:
        return ER_MSG[int(code)]
    except (IndexError, TypeError, ValueError):
        return "Error {}.".format(code)
