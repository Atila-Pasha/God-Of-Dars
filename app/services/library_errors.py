class LibraryError(RuntimeError):
    """Base class for Library domain errors."""


class InvalidQuestion(LibraryError):
    pass


class QuestionNotFound(LibraryError):
    pass


class GroupNotFound(LibraryError):
    pass


class GroupQuestionNotFound(LibraryError):
    pass


class WrongGroup(LibraryError):
    pass


class QuestionExpired(LibraryError):
    pass


class QuestionAlreadyAnswered(LibraryError):
    pass


class DuplicateAnswer(LibraryError):
    pass


class InvalidAnswer(LibraryError):
    pass


class RewardNotConfigured(LibraryError):
    pass


# Descriptive aliases for callers that prefer exception names with a suffix.
QuestionNotFoundError = QuestionNotFound
GroupQuestionNotFoundError = GroupQuestionNotFound
QuestionExpiredError = QuestionExpired
QuestionAlreadyAnsweredError = QuestionAlreadyAnswered
WrongGroupError = WrongGroup
