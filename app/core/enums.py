from enum import StrEnum


class TeacherStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INJURED = "INJURED"
    DISABLED = "DISABLED"
    RECOVERING = "RECOVERING"


class AttackStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


class QuestionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ANSWERED = "ANSWERED"
    EXPIRED = "EXPIRED"


class QuestionScope(StrEnum):
    DAILY = "DAILY"
    GROUP = "GROUP"


class ResourceType(StrEnum):
    COIN = "COIN"
    DIAMOND = "DIAMOND"
    BANANA = "BANANA"


class DailyQuestType(StrEnum):
    DAILY_LOGIN = "DAILY_LOGIN"
    ANSWER_DAILY_QUESTION = "ANSWER_DAILY_QUESTION"
    CORRECT_ANSWERS = "CORRECT_ANSWERS"
    COMPLETE_BATTLES = "COMPLETE_BATTLES"
    COLLECT_MINE = "COLLECT_MINE"
    JOIN_CHANNEL = "JOIN_CHANNEL"
