from enum import Enum

class UserRole(str, Enum):
    SUPERADMIN = "SuperAdmin"
    ESCUELA    = "Escuela"
    PROFESOR   = "Profesor"
    JUEZ       = "Juez"
    STAFF      = "Staff"