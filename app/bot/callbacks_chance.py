from aiogram.filters.callback_data import CallbackData


class ChanceBoxCallback(CallbackData, prefix="chance_box"):
    box_id: int


class ChanceCardCallback(CallbackData, prefix="chance_card"):
    card_id: int
