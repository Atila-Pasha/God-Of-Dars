class SchoolError(RuntimeError):
    """Base class for user-facing My School domain errors."""


class SchoolUserNotFound(SchoolError):
    pass


class ResourceNotFound(SchoolError):
    pass


class InsufficientCoins(SchoolError):
    pass


class TeacherNotFound(SchoolError):
    pass


class TeacherNotOwned(SchoolError):
    pass


class TeacherAlreadyOwned(SchoolError):
    pass


class TeacherLocked(SchoolError):
    pass


class TeacherLimitReached(SchoolError):
    pass


class TeacherSlotLocked(SchoolError):
    pass


class TeacherNotPurchasable(SchoolError):
    pass


class InvalidTeacherState(SchoolError):
    pass


class CastleNotFound(SchoolError):
    pass


class CastleUpgradeUnavailable(SchoolError):
    pass


class OperationNotConfigured(SchoolError):
    pass


class ShieldNotFound(SchoolError):
    pass


class ShieldLocked(SchoolError):
    pass


class ShieldNotPurchasable(SchoolError):
    pass


class MineNotFound(SchoolError):
    pass


class MineLevelLocked(SchoolError):
    pass


class MineUpgradeUnavailable(SchoolError):
    pass
