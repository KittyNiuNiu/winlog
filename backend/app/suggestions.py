"""AI suggestions for an entry's category and tags (issue #16).

Operation `suggestCategoryAndTags` in openapi.yaml. Covers FR-S1 and FR-S2, and the
acceptance criteria in product-spec.md §7.3 and §8.

- The request needs a valid token. Without one, the request gets `not_authenticated` and no
  AI call is made: authentication runs before the endpoint.
- The text follows the entry text rules (`app.entries.EntryText`): missing, empty or
  whitespace-only text is the shared validation error, which counts against no limit.
- The AI is called only through the limited entry point (`LimitedAIDependency`, issue #15),
  so the daily limits are checked before the call. A reached limit is the 429
  `limit_reached` error naming the limit.
- Only the entry text goes to the AI (§8). The user's tags are not sent: suggested names are
  matched to them after the call.
- An AI timeout or provider failure is the 503 `ai_unavailable` error, so the user can fill
  in the fields manually (§7.3).
- Suggested tag names are cleaned with #8's rules. A name that matches one of the user's own
  tags, ignoring case, gets that tag's stored spelling (found with `lookup_tags`). Names that
  match each other after cleaning are returned once, and at most `MAX_SUGGESTED_TAGS` are
  returned, in the order the AI gave them. Names longer than the tag name limit
  (`MAX_TAG_NAME_CHARACTERS`) after cleaning are left out before the first five are taken, so
  every suggested name can be saved (issue #43).
- Nothing is saved: no entry and no tag. Only the usage counts of #15 change.

Privacy: nothing here is logged. The entry text and the suggested tags never appear in a log
or an error message, and the AI error is not chained to the `ai_unavailable` error, so the
provider's exception (which may repeat the text) cannot reach a traceback (`AGENTS.md`).
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai import AIError, LimitedAIDependency
from app.auth import AuthenticateFirstRoute, CurrentUser
from app.db import get_session
from app.entries import Category, EntryText
from app.errors import ApiError
from app.models import User
from app.tags import MAX_TAG_NAME_CHARACTERS, lookup_tags, match_keys, normalise_tag_name

router = APIRouter(tags=["AI"], route_class=AuthenticateFirstRoute)

# openapi.yaml `Suggestion.tags` (maxItems) and product-spec.md §7.3.
MAX_SUGGESTED_TAGS = 5


class SuggestionRequest(BaseModel):
    """The request body (components.schemas.SuggestionRequest)."""

    # Fields the contract does not define are ignored.
    model_config = ConfigDict(extra="ignore")

    text: EntryText


class Suggestion(BaseModel):
    """The suggestion as the API returns it (components.schemas.Suggestion)."""

    category: Category
    tags: list[str] = Field(max_length=MAX_SUGGESTED_TAGS)


def ai_unavailable() -> ApiError:
    """openapi.yaml's 503 `ai_unavailable` error. It never says why the AI call failed."""
    return ApiError(503, "ai_unavailable", "The AI is not available right now.")


def suggested_tag_names(session: Session, user: User, names: Sequence[str]) -> list[str]:
    """The tag names to return for the AI's suggested names.

    Each name is cleaned with #8's rules, and names that are empty or longer than
    `MAX_TAG_NAME_CHARACTERS` after cleaning are left out (#43). A name that matches one of
    the user's tags, ignoring case as #8 does, gets the tag's stored spelling; other names
    keep their cleaned spelling. Names that match each
    other are returned once, first one first, and at most `MAX_SUGGESTED_TAGS` names are
    returned. Reads only the user's own tags and creates nothing.
    """
    cleaned = [
        name
        for name in map(normalise_tag_name, names)
        if name and len(name) <= MAX_TAG_NAME_CHARACTERS
    ]
    if not cleaned:
        return []
    existing = lookup_tags(session, user, cleaned)
    # The match key of a stored tag is the key the lookup matched it on.
    keys = match_keys(session, [*cleaned, *(tag.name for tag in existing)])
    stored = {keys[tag.name]: tag.name for tag in existing}
    result: dict[str, str] = {}
    for name in cleaned:
        key = keys[name]
        if key not in result:
            result[key] = stored.get(key, name)
        if len(result) == MAX_SUGGESTED_TAGS:
            break
    return list(result.values())


@router.post(
    "/suggestions",
    operation_id="suggestCategoryAndTags",
    summary="Get AI suggestions for an entry's category and tags.",
    response_model=Suggestion,
)
def suggest_category_and_tags(
    body: SuggestionRequest,
    user: CurrentUser,
    ai: LimitedAIDependency,
    session: Annotated[Session, Depends(get_session)],
) -> Suggestion:
    # The AI call can take seconds. Close the session first, so no database connection or
    # transaction is held during it. The user stays loaded, and the session opens a new
    # connection for the tag lookup.
    session.close()
    try:
        suggestion = ai.suggest(user.id, body.text)
    except AIError:
        # `from None`: the provider's exception may repeat the entry text, so it must not
        # appear as the cause or context of this error in any traceback.
        raise ai_unavailable() from None
    return Suggestion(
        category=suggestion.category,
        tags=suggested_tag_names(session, user, suggestion.tags),
    )
