"""The auto-join decision engine: one registry, five stages.

This module is the only definition of the auto-join decision. Everything that
decides, explains or previews what auto-join does (the automation cycle, the
preview endpoints, the Giveaways lens, the label on every giveaway) goes
through it; there is no SQL mirror.

Stages, in order:

1. **Gates** (:data:`GATES`, never lifted): ``expired`` (end_time None or
   past), ``hidden``, ``entered``, ``unsafe`` (``is_safe is False``, which
   covers unsafe and borderline verdicts; ``None`` = never checked passes).
2. **Priority match**: the giveaway is matched against the user's ordered
   priority list (:data:`PRIORITY_TYPES`). The first matching item gives its
   ``priority`` (type) and ``rank`` (index); no match gives ``priority None``
   and ``rank len(list)``.
3. **Exemption**: a priority type's ``exempt_from_filters`` is fixed in the
   registry (wishlist and DLC are exempt, ending soon is not). A giveaway is
   exempt when it matches *any* exempt item in the list, not only the first
   match; ``lifted_by`` records that item. Exemption skips stage 4 only.
4. **Filters** (:data:`FILTERS`, unless exempt), first failure wins:
   ``price_below_min``, ``genre_excluded`` (unknown genres pass),
   ``genre_not_included`` (only with a non-empty include list; unknown genres
   fail), ``no_game_data`` (a score, reviews or age threshold is set and no
   game is cached), ``score_below_min`` (unknown score counts as 0),
   ``reviews_below_min`` (unknown count counts as 0), ``game_too_old``
   (unknown release date fails).
5. **Ordering** (:func:`order_key`): by rank; inside the ending-soon group by
   end_time ascending; then giveaways that also match a later *exempt* item
   of the list come first (this keeps today's "wishlist and DLC before
   wishlist only" order); otherwise the pool's price-descending order is kept
   by a stable sort.

The budget is not a filter: :class:`CycleBudget` walks the ordered enter
list with the cycle's points and gives ``budget_floor`` and ``cycle_cap``
(:data:`OUTCOMES`); :func:`plan_cycle` records the expected outcome (and
``points_accumulating``) before the entry loop, which walks the same list
with the balance actually spent and records what happened. The per-cycle cap
counts entry attempts; giveaways skipped for points do not use a slot.

Every decision carries a small detail dict with the user's values (actual vs
threshold), and :func:`explain` renders it in the user's terms. Genre matching
folds ASCII letters only (:func:`core.text.ascii_lower`), the same fold the
settings normaliser uses for duplicates.

The registry is served as data by ``GET /giveaways/registry``
(:func:`registry_as_data`); the frontend fetches it and never mirrors it.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from core.text import ascii_lower
from models.game import Game
from models.giveaway import Giveaway
from models.settings import Settings

# A decision detail: a small flat JSON object (ints, strings, null, or the
# cached genre list) stored on Giveaway.eligibility_detail.
type Detail = dict[str, Any]
type RuleKind = Literal["gate", "filter", "outcome"]
type DecisionKind = Literal["enter", "gate", "filter", "budget"]

# Settings bounds shared with the API schemas and the registry endpoint.
GENRE_LIST_MAX_ITEMS = 50
GENRE_NAME_MAX_LENGTH = 64
THRESHOLD_MIN = 5
THRESHOLD_MAX = 10080
THRESHOLD_DEFAULT = 60
# Genre names listed in a genre_not_included label before it is cut short.
GENRE_LABEL_MAX_NAMES = 6

# === Decision codes (stored on Giveaway.eligibility_reason) ===
ELIGIBLE = "eligible"
EXPIRED = "expired"
HIDDEN = "hidden"
ENTERED = "entered"
UNSAFE = "unsafe"
PRICE_BELOW_MIN = "price_below_min"
GENRE_EXCLUDED = "genre_excluded"
GENRE_NOT_INCLUDED = "genre_not_included"
NO_GAME_DATA = "no_game_data"
SCORE_BELOW_MIN = "score_below_min"
REVIEWS_BELOW_MIN = "reviews_below_min"
GAME_TOO_OLD = "game_too_old"
BUDGET_FLOOR = "budget_floor"
CYCLE_CAP = "cycle_cap"
POINTS_ACCUMULATING = "points_accumulating"

# The one-word term for the enter state (D18): the client composes the
# tooltip from the detail (lifted_by, priority, rank).
ENTER_TERM = "Joinable"


# ============================================================================
# Policy
# ============================================================================


def fold_genres(values: Iterable[object]) -> frozenset[str]:
    """Fold genre names for matching: strip, ASCII-lowercase, drop empties.

    Non-string items are ignored. The settings normaliser rejects them on
    input; this only guards stored data edited by hand.
    """
    return frozenset(
        ascii_lower(value.strip())
        for value in values
        if isinstance(value, str) and value.strip()
    )


def normalize_genre_list(values: object, field_name: str) -> list[str]:
    """Validate and normalize a genre list (excluded or included); the single validation path.

    In order: require a list of strings, strip each item, drop empty items,
    reject any item longer than GENRE_NAME_MAX_LENGTH, dedupe
    case-insensitively keeping the first spelling, and reject more than
    GENRE_LIST_MAX_ITEMS remaining items. Used by the API schemas (422), the
    settings service (400 on input, CONFIG_002 on a stored row) and
    :func:`policy_from_settings` (fail closed on a stored row).

    Args:
        values: the submitted or stored value.
        field_name: the settings field, named in every error message.

    Returns:
        The normalized list, in the user's order.

    Raises:
        ValueError: on a non-list, a non-string item, an over-long item or
            too many items.

    Example:
        >>> normalize_genre_list([" Action", "action", "Indie", ""], "excluded_genres")
        ['Action', 'Indie']
    """
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValueError(f"{field_name} must be a list of strings")

    stripped = [v.strip() for v in values]
    stripped = [v for v in stripped if v]
    if any(len(v) > GENRE_NAME_MAX_LENGTH for v in stripped):
        raise ValueError(
            f"each {field_name} item must be at most {GENRE_NAME_MAX_LENGTH} characters"
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for value in stripped:
        # Same fold as the genre match (ASCII only): "Éducation" and
        # "éducation" are distinct there, so both are kept here; only
        # spellings that match identically are merged.
        key = ascii_lower(value)
        if key not in seen:
            seen.add(key)
            normalized.append(value)

    if len(normalized) > GENRE_LIST_MAX_ITEMS:
        raise ValueError(f"{field_name} accepts at most {GENRE_LIST_MAX_ITEMS} genres")
    return normalized


# What each policy column is called in a user-facing "cannot be read" message.
_POLICY_COLUMN_LABELS = {
    "autojoin_priorities": "Auto-join priorities setting",
    "excluded_genres": "Genre list setting",
    "included_genres": "Genre list setting",
}


class InvalidPolicyError(ValueError):
    """A policy column (priority list or genre list) that cannot be read.

    ``setting`` names the column; the message is the user-facing sentence
    ("Auto-join priorities setting is invalid: ..."), never a session value.
    """

    def __init__(self, setting: str, problem: str) -> None:
        self.setting = setting
        self.problem = problem
        super().__init__(f"{_POLICY_COLUMN_LABELS[setting]} is invalid: {problem}")


def check_policy_column(setting: str, raw: object) -> None:
    """Validate one stored or submitted policy column with the engine's parser.

    ``autojoin_priorities`` goes through :func:`parse_priorities`, the genre
    lists through :func:`normalize_genre_list`.

    Raises:
        InvalidPolicyError: naming the column and the parse error.
    """
    try:
        if setting == "autojoin_priorities":
            parse_priorities(raw)
        else:
            normalize_genre_list(raw, setting)
    except ValueError as e:
        raise InvalidPolicyError(setting, str(e)) from e


@dataclass(frozen=True)
class PriorityItem:
    """One entry of the user's ordered priority list."""

    type: str
    threshold_minutes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """The stored JSON shape: ``{"type"}`` plus the type's parameters."""
        data: dict[str, Any] = {"type": self.type}
        for param in PRIORITY_TYPES[self.type].params:
            data[param.name] = getattr(self, param.name)
        return data


@dataclass(frozen=True)
class AutoJoinPolicy:
    """Everything the engine reads, built only by :func:`policy_from_settings`.

    ``min_score``, ``min_reviews`` and ``max_game_age`` are ``None`` when the
    filter is off; 0 is a real minimum that still needs cached game data.
    The genre lists are folded for matching in ``__post_init__``.
    """

    min_price: int = 0
    min_score: int | None = None
    min_reviews: int | None = None
    max_game_age: int | None = None
    excluded_genres: frozenset[str] = frozenset()
    included_genres: frozenset[str] = frozenset()
    priorities: tuple[PriorityItem, ...] = ()
    start_at: int = 0
    stop_at: int = 0
    max_entries_per_cycle: int = 10
    auto_hide_unsafe: bool = True

    def __post_init__(self) -> None:
        """Fold both genre lists for ASCII case-insensitive matching."""
        object.__setattr__(self, "excluded_genres", fold_genres(self.excluded_genres))
        object.__setattr__(self, "included_genres", fold_genres(self.included_genres))

    @property
    def needs_game_data(self) -> bool:
        """Whether a quality threshold is set, so a missing game fails."""
        return (
            self.min_score is not None
            or self.min_reviews is not None
            or self.max_game_age is not None
        )


@dataclass(frozen=True)
class PolicyFields:
    """The seven raw policy values a preview may supply instead of the row."""

    autojoin_min_price: int
    autojoin_min_score: int | None
    autojoin_min_reviews: int | None
    autojoin_max_game_age: int | None
    excluded_genres: list[str]
    included_genres: list[str]
    autojoin_priorities: list[dict[str, Any]]


def _read_priorities(raw: object) -> tuple[PriorityItem, ...]:
    try:
        return parse_priorities(raw)
    except ValueError as e:
        raise InvalidPolicyError("autojoin_priorities", str(e)) from e


def _read_genres(raw: object, setting: str) -> frozenset[str]:
    """A genre list column folded for matching; None reads as empty."""
    values = [] if raw is None else raw
    check_policy_column(setting, values)
    return fold_genres(values)


def policy_from_settings(settings: Settings, override: PolicyFields | None = None) -> AutoJoinPolicy:
    """Build the auto-join policy; the only place settings reach the engine.

    With ``override`` the seven policy values come from it and the stored
    priority and genre lists are not read; the budget fields (start/stop
    thresholds, per-cycle cap, auto-hide) always come from ``settings``.

    Raises:
        InvalidPolicyError: (a ValueError) when the priority list or a genre
            list in use cannot be parsed. Fail closed: a mis-read priority
            list could lift the wrong giveaways, and a mis-read genre list
            (a string folds into single letters) would let excluded genres
            through.
    """
    source = override if override is not None else PolicyFields(
        autojoin_min_price=settings.autojoin_min_price,
        autojoin_min_score=settings.autojoin_min_score,
        autojoin_min_reviews=settings.autojoin_min_reviews,
        autojoin_max_game_age=settings.autojoin_max_game_age,
        excluded_genres=settings.excluded_genres,
        included_genres=settings.included_genres,
        autojoin_priorities=settings.autojoin_priorities,
    )
    return AutoJoinPolicy(
        min_price=source.autojoin_min_price or 0,
        min_score=source.autojoin_min_score,
        min_reviews=source.autojoin_min_reviews,
        max_game_age=source.autojoin_max_game_age,
        excluded_genres=_read_genres(source.excluded_genres, "excluded_genres"),
        included_genres=_read_genres(source.included_genres, "included_genres"),
        priorities=_read_priorities(source.autojoin_priorities),
        start_at=settings.autojoin_start_at or 0,
        stop_at=settings.autojoin_stop_at or 0,
        max_entries_per_cycle=settings.max_entries_per_cycle or 10,
        auto_hide_unsafe=bool(settings.auto_hide_unsafe),
    )


# ============================================================================
# Rules: gates and filters
# ============================================================================


@dataclass(frozen=True)
class Candidate:
    """What a rule's check sees."""

    giveaway: Giveaway
    game: Game | None
    policy: AutoJoinPolicy
    now: datetime


@dataclass(frozen=True)
class Rule:
    """A registry entry: code, kind, labels and (for gates/filters) the check.

    ``check`` returns the detail dict when the rule fires, else ``None``
    (outcomes never fire: they are recorded by plan_cycle, not checked).
    ``explain`` renders a detail holding every key in ``required``; any other
    detail renders the bare ``label``.
    """

    code: str
    kind: RuleKind
    label: str
    explain: Callable[[Detail], str]
    required: tuple[str, ...] = ()
    check: Callable[[Candidate], Detail | None] = field(default=lambda _candidate: None)
    setting: str | None = None


def _fixed(text: str) -> Callable[[Detail], str]:
    """An explain function that ignores the detail."""
    return lambda _detail: text


def _check_expired(c: Candidate) -> Detail | None:
    end_time = c.giveaway.end_time
    return {} if end_time is None or end_time <= c.now else None


def _check_hidden(c: Candidate) -> Detail | None:
    return {} if c.giveaway.is_hidden else None


def _check_entered(c: Candidate) -> Detail | None:
    return {} if c.giveaway.is_entered else None


def _check_unsafe(c: Candidate) -> Detail | None:
    return {"safety_score": c.giveaway.safety_score} if c.giveaway.is_safe is False else None


def _check_price(c: Candidate) -> Detail | None:
    if c.giveaway.price < c.policy.min_price:
        return {"price": c.giveaway.price, "min_price": c.policy.min_price}
    return None


def _check_genre_excluded(c: Candidate) -> Detail | None:
    # Negative filter: no cached game, genres NULL or [] pass.
    if not c.policy.excluded_genres or c.game is None or not c.game.genres:
        return None
    for genre in c.game.genres:
        if isinstance(genre, str) and ascii_lower(genre) in c.policy.excluded_genres:
            return {"genre": genre}
    return None


def _check_genre_not_included(c: Candidate) -> Detail | None:
    # Positive filter, fail closed: unknown genres cannot satisfy it.
    if not c.policy.included_genres:
        return None
    if c.game is None or c.game.genres is None:
        return {"genres": None}
    genres = list(c.game.genres)
    if any(isinstance(g, str) and ascii_lower(g) in c.policy.included_genres for g in genres):
        return None
    return {"genres": genres}


def _check_no_game_data(c: Candidate) -> Detail | None:
    return {} if c.policy.needs_game_data and c.game is None else None


def _check_score(c: Candidate) -> Detail | None:
    if c.policy.min_score is None or c.game is None:
        return None
    score = c.game.review_score or 0
    return {"score": score, "min_score": c.policy.min_score} if score < c.policy.min_score else None


def _check_reviews(c: Candidate) -> Detail | None:
    if c.policy.min_reviews is None or c.game is None:
        return None
    reviews = c.game.total_reviews or 0
    if reviews < c.policy.min_reviews:
        return {"reviews": reviews, "min_reviews": c.policy.min_reviews}
    return None


def _check_age(c: Candidate) -> Detail | None:
    if c.policy.max_game_age is None or c.game is None:
        return None
    # release_date is stored as ISO "YYYY-MM-DD", so a string compare works.
    cutoff = f"{c.now.year - c.policy.max_game_age}-01-01"
    release_date = c.game.release_date
    if release_date is None or release_date < cutoff:
        return {"release_date": release_date, "max_game_age": c.policy.max_game_age}
    return None


def _explain_genre_not_included(detail: Detail) -> str:
    genres = detail["genres"]
    if genres is None:
        return "Steam genres not cached yet; unknown genres fail your included-genre filter; checked again next cycle"
    if not genres:
        return "It has no Steam genres, so it cannot match your included list"
    names = ", ".join(str(g) for g in genres[:GENRE_LABEL_MAX_NAMES])
    if len(genres) > GENRE_LABEL_MAX_NAMES:
        names += ", …"
    return f"None of its genres ({names}) is on your included list"


def _explain_game_too_old(detail: Detail) -> str:
    if detail["release_date"] is None:
        return f"Release date unknown; games with unknown age fail your {detail['max_game_age']}-year limit"
    return f"Released {detail['release_date']}, older than your {detail['max_game_age']}-year limit"


BUDGET_FLOOR_LABEL = "Not entered last cycle: points floor"


def _explain_budget_floor(detail: Detail) -> str:
    price, points, stop_at = detail["price"], detail["points"], detail["stop_at"]
    if not all(isinstance(v, int) for v in (price, points, stop_at)):
        return BUDGET_FLOOR_LABEL
    return f"Not entered last cycle: {price}P would leave {points - price}P, below your {stop_at}P floor"


GATES: tuple[Rule, ...] = (
    Rule(EXPIRED, "gate", "Giveaway has ended", _fixed("Giveaway has ended"), check=_check_expired),
    Rule(HIDDEN, "gate", "Hidden", _fixed("Hidden"), check=_check_hidden),
    Rule(ENTERED, "gate", "Already entered", _fixed("Already entered"), check=_check_entered),
    Rule(
        UNSAFE, "gate", "Flagged unsafe or borderline by the safety check",
        _fixed("Flagged unsafe or borderline by the safety check"), check=_check_unsafe,
    ),
)

FILTERS: tuple[Rule, ...] = (
    Rule(
        PRICE_BELOW_MIN, "filter", "Price below minimum",
        lambda d: f"Price {d['price']}P is below your minimum {d['min_price']}P",
        required=("price", "min_price"), check=_check_price, setting="autojoin_min_price",
    ),
    Rule(
        GENRE_EXCLUDED, "filter", "Game genre is excluded",
        lambda d: f"Genre {d['genre']} is on your excluded list",
        required=("genre",), check=_check_genre_excluded, setting="excluded_genres",
    ),
    Rule(
        GENRE_NOT_INCLUDED, "filter", "No genre on your included list", _explain_genre_not_included,
        required=("genres",), check=_check_genre_not_included, setting="included_genres",
    ),
    Rule(
        NO_GAME_DATA, "filter", "No Steam game data cached",
        _fixed(
            "No Steam data cached yet; unknown data never passes the score, reviews or age filters; "
            "checked again next cycle"
        ),
        check=_check_no_game_data,
    ),
    Rule(
        SCORE_BELOW_MIN, "filter", "Review score below minimum",
        lambda d: f"Review score {d['score']} is below your minimum {d['min_score']}",
        required=("score", "min_score"), check=_check_score, setting="autojoin_min_score",
    ),
    Rule(
        REVIEWS_BELOW_MIN, "filter", "Too few reviews",
        lambda d: f"{d['reviews']} reviews is below your minimum {d['min_reviews']}",
        required=("reviews", "min_reviews"), check=_check_reviews, setting="autojoin_min_reviews",
    ),
    Rule(
        GAME_TOO_OLD, "filter", "Game older than allowed (or release date unknown)", _explain_game_too_old,
        required=("release_date", "max_game_age"), check=_check_age, setting="autojoin_max_game_age",
    ),
)

OUTCOMES: tuple[Rule, ...] = (
    Rule(ELIGIBLE, "outcome", ENTER_TERM, _fixed(ENTER_TERM)),
    Rule(
        BUDGET_FLOOR, "outcome", BUDGET_FLOOR_LABEL, _explain_budget_floor,
        required=("price", "points", "stop_at"),
    ),
    Rule(
        CYCLE_CAP, "outcome", "Not entered last cycle: per cycle cap",
        lambda d: f"Not entered last cycle: the {d['cap']} per cycle cap was reached",
        required=("cap",),
    ),
    Rule(
        POINTS_ACCUMULATING, "outcome", "Not entered last cycle: accumulating points",
        lambda d: f"Not entered last cycle: {d['points']}P is below your {d['start_at']}P start threshold",
        required=("points", "start_at"),
    ),
)

RULES: dict[str, Rule] = {rule.code: rule for rule in (*GATES, *FILTERS, *OUTCOMES)}

# Bare label per code (kept under this name for existing imports).
REASON_LABELS: dict[str, str] = {code: rule.label for code, rule in RULES.items()}


# ============================================================================
# Priority types
# ============================================================================


@dataclass(frozen=True)
class PriorityParam:
    """A parameter a priority item carries, with its bounds and default."""

    name: str
    min: int
    max: int
    default: int


@dataclass(frozen=True)
class PriorityType:
    """A registry entry for a priority list item.

    ``exempt_from_filters`` is fixed per type (D1a). ``within_group_key``
    orders the giveaways this type matched first; ``None`` keeps the pool's
    price order.
    """

    type: str
    label: str
    description: str
    exempt_from_filters: bool
    params: tuple[PriorityParam, ...]
    matches: Callable[[Giveaway, PriorityItem, datetime], bool]
    within_group_key: Callable[[Giveaway], datetime] | None = None


def _ends_within(giveaway: Giveaway, item: PriorityItem, now: datetime) -> bool:
    """Ending soon: at most threshold_minutes left (exactly at counts)."""
    if giveaway.end_time is None or item.threshold_minutes is None:
        return False
    return giveaway.end_time - now <= timedelta(minutes=item.threshold_minutes)


def _end_time_key(giveaway: Giveaway) -> datetime:
    # Only called for matched ending-soon giveaways, whose end_time is set.
    return giveaway.end_time or datetime.min


PRIORITY_TYPES: dict[str, PriorityType] = {
    "wishlist": PriorityType(
        type="wishlist",
        label="Wishlist",
        description="Games on your Steam wishlist",
        exempt_from_filters=True,
        params=(),
        matches=lambda giveaway, _item, _now: bool(giveaway.is_wishlist),
    ),
    "dlc": PriorityType(
        type="dlc",
        label="DLC",
        description="DLC for games you own, from the DLC listing",
        exempt_from_filters=True,
        params=(),
        matches=lambda giveaway, _item, _now: bool(giveaway.is_dlc),
    ),
    "ending_soon": PriorityType(
        type="ending_soon",
        label="Ending soon",
        description="Giveaways ending within the threshold, soonest first",
        exempt_from_filters=False,
        params=(PriorityParam("threshold_minutes", THRESHOLD_MIN, THRESHOLD_MAX, THRESHOLD_DEFAULT),),
        matches=_ends_within,
        within_group_key=_end_time_key,
    ),
}

MAX_PRIORITY_ITEMS = len(PRIORITY_TYPES)


def parse_priorities(raw: object) -> tuple[PriorityItem, ...]:
    """Validate a stored or submitted priority list; the single validation path.

    Raises:
        ValueError: on a non-list, too many items, a non-object item, a missing
            or unknown type, a duplicate type, an unknown key, or a missing,
            non-integer or out-of-range parameter.
    """
    if not isinstance(raw, list):
        raise ValueError("autojoin_priorities must be a list")
    if len(raw) > MAX_PRIORITY_ITEMS:
        raise ValueError(f"autojoin_priorities accepts at most {MAX_PRIORITY_ITEMS} items")

    items: list[PriorityItem] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("each autojoin_priorities item must be an object")
        type_name = entry.get("type")
        if not isinstance(type_name, str):
            raise ValueError("each autojoin_priorities item needs a string 'type'")
        priority_type = PRIORITY_TYPES.get(type_name)
        if priority_type is None:
            raise ValueError(f"unknown priority type '{type_name[:32]}'")
        if type_name in seen:
            raise ValueError(f"duplicate priority type '{type_name}'")
        seen.add(type_name)

        allowed = {"type", *(param.name for param in priority_type.params)}
        if set(entry) - allowed:
            raise ValueError(f"priority type '{type_name}' accepts only: {', '.join(sorted(allowed))}")

        values: dict[str, int] = {}
        for param in priority_type.params:
            value = entry.get(param.name)
            if value is None:
                raise ValueError(f"priority type '{type_name}' requires {param.name}")
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{param.name} must be an integer")
            if not param.min <= value <= param.max:
                raise ValueError(f"{param.name} must be between {param.min} and {param.max}")
            values[param.name] = value
        items.append(PriorityItem(type=type_name, **values))
    return tuple(items)


# ============================================================================
# Decision, ordering, cycle plan
# ============================================================================


@dataclass(frozen=True)
class Decision:
    """The engine's verdict for one giveaway.

    ``priority``/``rank``: first matching priority item (rank = its index, or
    ``len(list)`` when nothing matched). ``lifted_by``: the first exempt item
    in list order that matched, when the filters were skipped.
    """

    code: str
    detail: Detail = field(default_factory=dict)
    lifted_by: str | None = None
    priority: str | None = None
    rank: int = 0

    @property
    def enter(self) -> bool:
        """Whether the giveaway passed gates and filters (an enter candidate)."""
        return self.code == ELIGIBLE


def _matches(giveaway: Giveaway, item: PriorityItem, now: datetime) -> bool:
    return PRIORITY_TYPES[item.type].matches(giveaway, item, now)


def _first_gate(candidate: Candidate) -> tuple[str, Detail] | None:
    """The first gate that fires for a candidate, as (code, detail), else None."""
    for rule in GATES:
        detail = rule.check(candidate)
        if detail is not None:
            return rule.code, detail
    return None


def gate_of(giveaway: Giveaway, policy: AutoJoinPolicy, now: datetime) -> tuple[str, Detail] | None:
    """The gate a giveaway is stopped by now (expired, hidden, entered, unsafe), else None.

    Gates read only the giveaway row, so no game data is needed. The entry
    loop uses this after an attempt that entered nothing: an inline safety
    check that flagged the giveaway leaves it unsafe or hidden, and that, not
    the pre-attempt eligible, is the decision to record.
    """
    return _first_gate(Candidate(giveaway=giveaway, game=None, policy=policy, now=now))


def decide(giveaway: Giveaway, game: Game | None, policy: AutoJoinPolicy, now: datetime) -> Decision:
    """Run gates, priority match, exemption and filters for one giveaway."""
    candidate = Candidate(giveaway=giveaway, game=game, policy=policy, now=now)
    unmatched_rank = len(policy.priorities)

    gate = _first_gate(candidate)
    if gate is not None:
        code, detail = gate
        return Decision(code=code, detail=detail, rank=unmatched_rank)

    priority: str | None = None
    rank = unmatched_rank
    lifted_by: str | None = None
    for index, item in enumerate(policy.priorities):
        if not _matches(giveaway, item, now):
            continue
        if priority is None:
            priority, rank = item.type, index
        if lifted_by is None and PRIORITY_TYPES[item.type].exempt_from_filters:
            lifted_by = item.type

    if lifted_by is None:
        for rule in FILTERS:
            detail = rule.check(candidate)
            if detail is not None:
                return Decision(code=rule.code, detail=detail, priority=priority, rank=rank)

    return Decision(
        code=ELIGIBLE,
        detail={"priority": priority, "rank": rank, "lifted_by": lifted_by},
        lifted_by=lifted_by,
        priority=priority,
        rank=rank,
    )


def order_key(
    giveaway: Giveaway, decision: Decision, policy: AutoJoinPolicy, now: datetime
) -> tuple[int, datetime, tuple[bool, ...]]:
    """Entry-order sort key for an enter candidate.

    Meant for a stable sort over a pool already in price-descending order:
    rank first; then the matched type's within-group key (ending soon:
    end_time ascending; others constant); then, inside a group, giveaways that
    also match a later exempt item of the list come first (so wishlist + DLC
    giveaways precede wishlist-only ones, as today).
    """
    group_key = datetime.min
    later_exempt: tuple[bool, ...] = ()
    if decision.priority is not None:
        priority_type = PRIORITY_TYPES[decision.priority]
        if priority_type.within_group_key is not None:
            group_key = priority_type.within_group_key(giveaway)
        later_exempt = tuple(
            not (PRIORITY_TYPES[item.type].exempt_from_filters and _matches(giveaway, item, now))
            for item in policy.priorities[decision.rank + 1:]
        )
    return (decision.rank, group_key, later_exempt)


def order_candidates(
    decided: list[tuple[Giveaway, Decision]], policy: AutoJoinPolicy, now: datetime
) -> list[tuple[Giveaway, Decision]]:
    """The enter candidates of a price-descending pool, in entry order."""
    enter = [(g, d) for g, d in decided if d.enter]
    enter.sort(key=lambda pair: order_key(pair[0], pair[1], policy, now))
    return enter


@dataclass
class CycleBudget:
    """The running points balance and per-cycle cap of one cycle's entry walk.

    The single budget rule, shared by :func:`plan_cycle` (which assumes every
    attempt spends its price) and the entry loop (which spends what each
    entry actually cost, so a failed attempt leaves the balance unchanged and
    a later candidate the plan expected to be unaffordable is still tried).
    """

    points: int
    stop_at: int
    cap: int
    attempts: int = 0

    @classmethod
    def for_cycle(cls, points: int, policy: AutoJoinPolicy) -> CycleBudget:
        """The budget of a cycle starting with ``points``."""
        return cls(points=points, stop_at=policy.stop_at, cap=policy.max_entries_per_cycle)

    def skip(self, price: int) -> tuple[str, Detail] | None:
        """Why a candidate at ``price`` must not be attempted now, or None.

        Once ``cap`` attempts were made every candidate is ``cycle_cap``; a
        price that would take the balance below ``stop_at`` is
        ``budget_floor`` (skipped, not stopping: a cheaper one may still fit,
        and a skip uses no slot).
        """
        if self.attempts >= self.cap:
            return CYCLE_CAP, {"cap": self.cap}
        if self.points - price < self.stop_at:
            return BUDGET_FLOOR, {"price": price, "points": self.points, "stop_at": self.stop_at}
        return None

    def attempt(self, spent: int) -> None:
        """Count one entry attempt that spent ``spent`` points (0 on failure)."""
        self.attempts += 1
        self.points -= spent


def plan_cycle(
    candidates: list[tuple[Giveaway, Decision]], points: int | None, policy: AutoJoinPolicy
) -> list[tuple[Giveaway, str, Detail]]:
    """Apply the points budget and the per-cycle cap to ordered enter candidates.

    The expected outcome, recorded before the entry loop runs (the loop
    records what actually happened afterwards):

    - ``points`` None (balance unavailable): every candidate keeps
      ``eligible``; the budget is not applied this cycle and nothing is
      entered.
    - ``points < start_at``: every candidate becomes ``points_accumulating``.
    - otherwise :class:`CycleBudget` walks the list assuming every attempt
      succeeds and spends its price: ``cycle_cap`` once
      ``max_entries_per_cycle`` attempts are planned, ``budget_floor`` for a
      price that would take the running balance below ``stop_at``, and
      ``eligible`` (an attempt) for the others.
    """
    if points is None:
        return [(g, d.code, d.detail) for g, d in candidates]
    if points < policy.start_at:
        detail = {"points": points, "start_at": policy.start_at}
        return [(g, POINTS_ACCUMULATING, dict(detail)) for g, _ in candidates]

    planned: list[tuple[Giveaway, str, Detail]] = []
    budget = CycleBudget.for_cycle(points, policy)
    for giveaway, decision in candidates:
        skip = budget.skip(giveaway.price)
        if skip is not None:
            planned.append((giveaway, *skip))
        else:
            planned.append((giveaway, decision.code, decision.detail))
            budget.attempt(giveaway.price)
    return planned


def count_codes(codes: Iterable[str]) -> dict[str, int]:
    """Per-code counts in first-seen order."""
    return dict(Counter(codes))


# ============================================================================
# Explanation and registry data
# ============================================================================


def explain(code: str | None, detail: Detail | None) -> str | None:
    """Render a stored decision in the user's terms.

    ``None`` code renders ``None``; an unknown code renders the code itself;
    a detail missing any key the rule needs renders the rule's bare label.
    """
    if code is None:
        return None
    rule = RULES.get(code)
    if rule is None:
        return code
    if detail is None or any(key not in detail for key in rule.required):
        return rule.label
    return rule.explain(detail)


def kind_of(code: str | None) -> DecisionKind | None:
    """The family a decision code belongs to, from registry membership."""
    if code is None:
        return None
    rule = RULES.get(code)
    if rule is None:
        return None
    if rule.kind == "gate":
        return "gate"
    if rule.kind == "filter":
        return "filter"
    return "enter" if code == ELIGIBLE else "budget"


def registry_as_data() -> dict[str, Any]:
    """The registry as served by ``GET /giveaways/registry``."""
    return {
        "gates": [{"code": rule.code, "label": rule.label} for rule in GATES],
        "filters": [
            {"code": rule.code, "label": rule.label, "setting": rule.setting} for rule in FILTERS
        ],
        "outcomes": [{"code": rule.code, "label": rule.label} for rule in OUTCOMES],
        "priority_types": [
            {
                "type": pt.type,
                "label": pt.label,
                "description": pt.description,
                "exempt_from_filters": pt.exempt_from_filters,
                "params": [
                    {"name": p.name, "min": p.min, "max": p.max, "default": p.default} for p in pt.params
                ],
            }
            for pt in PRIORITY_TYPES.values()
        ],
        "limits": {
            "genre_max_items": GENRE_LIST_MAX_ITEMS,
            "genre_max_length": GENRE_NAME_MAX_LENGTH,
            "max_priority_items": MAX_PRIORITY_ITEMS,
        },
    }
