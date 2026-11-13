"""5.817 Billie passive, enabled for supported live candidates by user request.

EndMoveWithPassiveAbility 0x5a1437c -> ConvertToCrosses 0x5a14054 ->
BillieBoomDefaultVariant.SelectCrossPositions 0x5aa05f0 and ApplyConversions
0x5abb6c4. Booster Use / scored GameLogic clones / Remove are NOT implemented.
Only the recorded default variant (line/square matches, bombs) is covered.
"""
from dataclasses import dataclass, replace

from engine_refill import SIM_SPECIAL_TO_ENGINE, UnsupportedRefill, color_maps


@dataclass(frozen=True)
class BilliePassive:
    # ToSpecial preserves color; BLOCKED in the simulator loses this value.
    drone_color: int                 # engine colour, not simulator colour
    create: int = 3
    chance: int = 60                # post-match uses SecondaryCreate chance
    block_chance: int = 100
    suppress_once: bool = False     # free board ability: NoFreeMove... is false

    @classmethod
    def from_record(cls, record, *, drone_color=None):
        players = (record.get("snapshot_state") or {}).get("players") or []
        me = next((p for p in players if p.get("player_type") == 0), {})
        params = me.get("special_ability_params") or {}
        fields = me.get("special_ability_fields") or {}
        if (me.get("special_ability_type") != 41
                or params.get("specialsChance") != "Bomb,1|Fireworks,0|Row,0|Column,0"
                or int(params.get("chanceToPickEnergyColors", -1)) != -1
                or int(params.get("chanceToPickExtraMove", -1)) != -1
                or fields.get("removePreviousPieces") is not False):
            raise UnsupportedRefill("Billie: only the captured default passive variant is ported")
        slots = record.get("billie_slots") or []
        if slots:
            if len(slots) != 1 or slots[0].get("canBeMatched") is not False or slots[0].get("movable") is not True:
                raise UnsupportedRefill("Billie: unexpected drone slot flags")
            drone_color = slots[0].get("color")
        if drone_color not in record["profile"]["spawning"]["gameColors"]:
            raise UnsupportedRefill("Billie: raw drone colour missing from recording")
        return cls(int(drone_color), int(params["postMatchCreate"]),
                   int(params["chanceToPickMatchablePieceOnSecondaryCreate"]),
                   int(params["chanceToBlockNeighbors"]),
                   bool(me.get("active_board_ability") == 22 or
                        (me.get("is_board_ability_used_this_move") and me.get("board_ability_used_this_move") == 22)))


def _possible_pieces(board, square=False, specials=None):
    """Ordered distinct pieces taking part in an ordinary possible line match.

GetPossibleMoves 0x591f870: x, y, Down, Right (reverse ordinary swaps excluded).
GetMoveCombosOutcome 0x591529c: source then target. BlobMatchChecker 0x596d570:
vertical Up/Down, horizontal Left/Right. The Billie selector removes the
combo's moved position and appends its pre-swap source (0x5aa1a8c).
No special effects are simulated here and no engine RNG is consumed.
"""
    n = len(board)
    seen, ordered = set(), []

    def movable(r, c):
        # GetValidOutcomes checks IsImmovable. A drone is movable but cannot
        # match, so a plain piece can form a combo by taking its place.
        return board[r][c] > 0 or (specials is not None and specials[r][c] == 14)

    for c in range(n):
        for r in range(n):
            for dy, dx in ((1, 0), (0, 1)):
                y, x = r + dy, c + dx
                if (y >= n or x >= n or not movable(r, c) or not movable(y, x)
                        or board[r][c] == board[y][x]):
                    continue
                # GetValidOutcomes 0x592421c handles a special+special merge
                # before GetMoveCombosOutcome. Its type-9 combo contains only
                # the two specials; neither is an ordinary Billie target.
                # Do not invent ordinary colour matches for that swap.
                merge_specials = (1, 2, 3, 4, 46)
                if (specials is not None and specials[r][c] in merge_specials
                        and specials[y][x] in merge_specials):
                    continue
                swapped = [list(row) for row in board]
                swapped[r][c], swapped[y][x] = swapped[y][x], swapped[r][c]
                for endpoint, source in (((r, c), (y, x)), ((y, x), (r, c))):
                    rr, cc = endpoint
                    if swapped[rr][cc] <= 0:
                        continue
                    cells = []
                    for axis in (((-1, 0), (1, 0)), ((0, -1), (0, 1))):
                        line = []
                        for dr, dc in axis:
                            yy, xx = rr + dr, cc + dc
                            while (0 <= yy < n and 0 <= xx < n
                                   and swapped[yy][xx] == swapped[rr][cc]):
                                line.append((yy, xx))
                                yy, xx = yy + dr, xx + dc
                        if len(line) >= 2:
                            cells.extend(line)
                    if square:
                        # BlobMatchChecker's four single-step patterns, in
                        # cctor order: upper-left, upper-right, lower-left,
                        # lower-right. Each buffer starts with endpoint.
                        for offsets in (((-1, -1), (-1, 0), (0, -1)),
                                        ((-1, 0), (-1, 1), (0, 1)),
                                        ((0, -1), (1, -1), (1, 0)),
                                        ((0, 1), (1, 1), (1, 0))):
                            points = [(rr + dr, cc + dc) for dr, dc in offsets]
                            if all(0 <= yy < n and 0 <= xx < n and swapped[yy][xx] == swapped[rr][cc]
                                   for yy, xx in points):
                                cells.extend(points)
                    if cells:
                        for point in (*cells, source):
                            if point not in seen:
                                seen.add(point)
                                ordered.append(point)
    return ordered


def finish_passive(model, result):
    """Mutate only the candidate result and its private RNG; return audit event.

The caller must establish an ordinary, fully resolved legal swap. This is a
    partially verified path; never infer raw colour or booster flags in live play.
"""
    config = model.billie
    if config is not None and config.suppress_once:
        # EndMoveWithPassiveAbility 0x5a144d8 returns before ConvertToCrosses.
        # Consume neither target-selection nor conversion RNG. Next swap is normal.
        model.billie = replace(config, suppress_once=False)
        return None
    if config is None or not result.cleared_cells:
        return None
    board = [[int(v) for v in row] for row in result.board]
    special = [[int(v) for v in row] for row in result.special_board]
    n = len(board)
    if sum(v == 14 for row in special for v in row) != 1:
        raise UnsupportedRefill("Billie passive needs exactly one surviving drone")
    from simulator_capture import decode_dictionary
    square = bool((decode_dictionary(model.profile["rules"].get("_extraData")) or {}).get("allowSquareMatches"))
    to_engine, _ = color_maps(model.profile)
    rng, before = model.rng, model.rng.counter
    block = rng.chance(config.block_chance)  # context ctor, even at 100

    def valid(p):
        r, c = p
        # Literal bounds in b__2 / b__4: y=0 IS allowed, x=0 is not.
        return (1 <= c < n - 1 and r < n - 1 and special[r][c] == 0
                and to_engine.get(board[r][c]) in (6, 3, 5, 7, 8))

    def near(p, q):
        return abs(p[0] - q[0]) + abs(p[1] - q[1]) <= 1

    # Where(IsSpecial) 0x5aa1a74: IsBoardSpecial 0x592e824 (engine 16..20, e.g.
    # mushroom 19, crystal 18) is not IsSpecial, so it does not block a bomb.
    current = [(r, c) for r in range(n) for c in range(n)
               if special[r][c] and special[r][c] != 14
               and not 16 <= SIM_SPECIAL_TO_ENGINE.get(special[r][c], 0) <= 20]
    matchable = rng.shuffled([p for p in _possible_pieces(board, square, special) if valid(p)])
    # The fallback predicate excludes ALL initial matchable candidates, not
    # just selected ones; otherwise both the shuffle count and targets drift.
    initial = set(matchable)
    unblocked = [p for p in matchable if not any(near(p, q) for q in current)]
    selected = []
    matchable_count = len(matchable)
    for _ in range(max(0, config.create)):
        if len(matchable) < 2:
            break
        if rng.chance(config.chance):
            p = (unblocked if block and unblocked else matchable)[0]
            selected.append(p)
            matchable.remove(p)
            unblocked = [q for q in unblocked if q != p and (not block or not near(p, q))]
    fallback_count = 0
    if len(selected) < config.create:
        fallback = rng.shuffled([(r, c) for c in range(n) for r in range(n)
                                 if valid((r, c)) and (r, c) not in initial])
        fallback_count = len(fallback)
        free_fallback = [p for p in fallback if not any(near(p, q) for q in current + selected)]
        while len(matchable) > 1 or len(fallback) > 1:
            if block:
                pool = free_fallback or fallback or unblocked or matchable
            else:
                pool = fallback or matchable
            p = pool[0]
            selected.append(p)
            matchable = [q for q in matchable if q != p]
            fallback = [q for q in fallback if q != p]
            unblocked = [q for q in unblocked if q != p and (not block or not near(p, q))]
            free_fallback = [q for q in free_fallback if q != p and (not block or not near(p, q))]
            if len(selected) >= config.create:
                break
    for r, c in selected:
        rng.range(0, 1)  # Random(convertValues): still draws with one Bomb
        special[r][c] = 3
    result.special_board = special
    event = {"type": "billie_passive", "rng_before": before, "rng_after": rng.counter,
             "matchable_candidates": matchable_count, "fallback_candidates": fallback_count,
             "selected": selected, "block_neighbors": block}
    result.intent_events.append(event)
    return event
