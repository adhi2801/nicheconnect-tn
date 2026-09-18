"""Domain errors for the campaigns module."""

from http import HTTPStatus

from app.core.errors import DomainError


class CampaignNotFound(DomainError):
    # Also used when a campaign exists but belongs to someone else: saying
    # "forbidden" would confirm it exists (security.md section 2).
    status_code = HTTPStatus.NOT_FOUND
    code = "campaign_not_found"
    title = "That campaign does not exist"


class BrandProfileRequired(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "brand_profile_required"
    title = "Add your brand profile before posting a campaign"


class CampaignNotEditable(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "campaign_not_editable"
    title = "This campaign can no longer be edited"


class FieldNotEditableNow(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "field_not_editable_now"
    title = "That detail cannot be changed once the campaign is open"


class CampaignStatusConflict(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "campaign_status_conflict"
    title = "This campaign is not in a state where that is allowed"
