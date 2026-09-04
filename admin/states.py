from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    search = State()
    resource_coin = State()
    resource_diamond = State()
    resource_banana = State()


class BroadcastStates(StatesGroup):
    content = State()


class BuffetStates(StatesGroup):
    convert_amount = State()


class QuestionStates(StatesGroup):
    text = State()
    answer = State()
    hours = State()
    coin = State()
    diamond = State()
    banana = State()


class TeacherStates(StatesGroup):
    name = State()
    damage = State()
    max_hp = State()
    purchase_price = State()
    upgrade_price = State()
    unlock_level = State()
    ability_text = State()
    sticker = State()
    emoji = State()


class ShieldStates(StatesGroup):
    name = State()
    reduction_percent = State()
    flat_absorption = State()
    purchase_price = State()
    unlock_level = State()
    description = State()


class ChannelStates(StatesGroup):
    value = State()


class ChanceBoxStates(StatesGroup):
    section = State()
    value = State()


class ChanceCardStates(StatesGroup):
    target = State()
    value = State()
