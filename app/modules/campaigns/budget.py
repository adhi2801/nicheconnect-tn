"""A campaign's budget rules, for a new campaign and for a change to one."""

from app.modules.campaigns.models import BUDGETED_TYPES


def budget_problem(
    campaign_type: str, minimum: int | None, maximum: int | None
) -> tuple[str, str] | None:
    """The first budget rule broken, as (code, message), or None.

    The same rules the database enforces, with friendlier messages. A change
    is checked on the campaign as it would be after it, since a change to
    one end, or to the type, can break a rule the change never named.
    """
    if (minimum is None) != (maximum is None):
        return "budget_incomplete", "Give both a minimum and a maximum budget, or neither"
    if minimum is not None and maximum is not None and maximum < minimum:
        return "budget_backwards", "The maximum budget cannot be lower than the minimum"
    if campaign_type == "barter" and minimum is not None:
        return "budget_on_barter", "A barter campaign pays in goods, so it has no budget"
    if campaign_type in BUDGETED_TYPES and minimum is None:
        return "budget_required", "Give a budget range for this campaign type"
    return None
