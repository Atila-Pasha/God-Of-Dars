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


class DailyQuestType(str, Enum):
    DAILY_LOGIN = "DAILY_LOGIN"
    ANSWER_DAILY_QUESTION = "ANSWER_DAILY_QUESTION"
    CORRECT_ANSWERS = "CORRECT_ANSWERS"
    COMPLETE_BATTLES = "COMPLETE_BATTLES"
    WIN_BATTLES = "WIN_BATTLES"
    COLLECT_MINE = "COLLECT_MINE"
    JOIN_CHANNEL = "JOIN_CHANNEL"
