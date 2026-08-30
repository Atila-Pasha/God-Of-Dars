from enum import Enum


class TeacherStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INJURED = "INJURED"
    DISABLED = "DISABLED"
    RECOVERING = "RECOVERING"


class AttackStatus(str, Enum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"


class QuestionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ANSWERED = "ANSWERED"
    EXPIRED = "EXPIRED"


class QuestionScope(str, Enum):
    DAILY = "DAILY"
    GROUP = "GROUP"


class ResourceType(str, Enum):
    COIN = "COIN"
    DIAMOND = "DIAMOND"
    BANANA = "BANANA"
