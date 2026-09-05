from types import SimpleNamespace

import pytest

from app.bot.utils.attack import teacher_phrase
from app.services.attack_service import AttackService


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("افلاطون", "دبیر افلاطون"),
        ("افلاطون، ارسطو", "دبیر های افلاطون ارسطو"),
        ("افلاطون، ارسطو، نیوتن", "دبیر های افلاطون ارسطو نیوتن"),
    ],
)
def test_teacher_phrase_matches_attack_teacher_count(names, expected):
    assert teacher_phrase(names) == expected


class _ClaimSession:
    def __init__(self, rowcounts: list[int]) -> None:
        self.rowcounts = iter(rowcounts)

    async def execute(self, statement):
        return SimpleNamespace(rowcount=next(self.rowcounts))


@pytest.mark.asyncio
@pytest.mark.parametrize("record_ids", [(1,), (1, 2), (1, 2, 3, 4)])
async def test_attack_xp_claim_is_one_time_for_any_command_size(record_ids):
    session = _ClaimSession([1, *([0] * (len(record_ids) - 1))])

    claims = [
        await AttackService._claim_attack_xp(
            session, attack_command_id="command-100", attack_id=record_id
        )
        for record_id in record_ids
    ]

    assert claims.count(True) == 1
