from aiogram.fsm.state import State, StatesGroup


class BuffetStates(StatesGroup):
    convert_amount = State()


class ChanceCardStates(StatesGroup):
    waiting_captcha = State()


class AttackMenuStates(StatesGroup):
    waiting_target = State()
    selecting_teachers = State()
