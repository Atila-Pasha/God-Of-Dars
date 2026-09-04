from aiogram.fsm.state import State, StatesGroup


class BuffetStates(StatesGroup):
    convert_amount = State()


class ChanceCardStates(StatesGroup):
    waiting_captcha = State()
