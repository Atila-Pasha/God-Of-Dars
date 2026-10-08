from aiogram.filters.callback_data import CallbackData


class ChanceBoxCallback(CallbackData, prefix="chance_box"):
    box_id: int


class ChanceBoxCaptchaCallback(CallbackData, prefix="chance_box_answer"):
    box_id: int
    answer: str


class ChanceCardCallback(CallbackData, prefix="chance_card"):
    card_id: int
