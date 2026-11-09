"""Offline Versus policy tournament with sampled refill, not live-game RNG."""
import argparse
import itertools
import json
import random
from collections import Counter
from pathlib import Path

import move_strategy as ms


POLICIES = ("points", "extras", "charge", "setup", "deny", "setup_deny", "balanced")
CLASSIC = {0, ms.SPECIAL_HORIZONTAL, ms.SPECIAL_VERTICAL, ms.SPECIAL_BOMB}


def actions(board, specials):
    for candidate in ms.generate_candidates(board, specials, skip_plain_without_line=True):
        if any(specials[r][c] not in CLASSIC for r, c in (candidate.start, candidate.target)):
            continue
        result = ms._simulate_created_candidate(board, candidate, include_future_value=False)
        if result is not None:
            yield candidate, result


def play(board, candidate, rng):
    def fill(grid, specials, combos):
        for row in grid:
            for col, value in enumerate(row):
                if value == ms.EMPTY:
                    row[col] = rng.randint(1, 6)
        return grid, specials

    with ms.engine_refill_active(fill):
        return ms._simulate_created_candidate(board, candidate, include_future_value=False)


def choose(board, specials, policy, moves, charge, seed, opponent_follows):
    options = list(actions(board, specials))
    if not options:
        return None

    def base(item):
        _, result = item
        points = ms._instant_score(result)
        extra = bool(result.direct_extra_moves)
        blue = min(result.blue_cells, 7 - charge)
        return points + {"extras": 12 * extra, "charge": 4 * blue,
                         "setup": 5 * extra, "setup_deny": 5 * extra,
                         "balanced": 7 * extra + 2 * blue}.get(policy, 0)

    options.sort(key=base, reverse=True)
    if policy not in {"setup", "deny", "setup_deny", "balanced"}:
        return options[0][0]

    def lookahead(item):
        candidate, _ = item
        result = play(board, candidate, random.Random(seed))
        if result is None:
            return base(item)
        keeps_turn = moves > 1 or bool(result.extra_moves)
        if not keeps_turn and not opponent_follows:
            return base(item)
        if (policy == "setup" and not keeps_turn) or (policy == "deny" and keeps_turn):
            return base(item)
        reply = max((ms._instant_score(r) + 6 * bool(r.direct_extra_moves)
                     for _, r in actions(result.board, result.special_board)), default=0)
        return base(item) + (0.5 if keeps_turn else -0.65) * reply

    return max(options[:4], key=lookahead)[0]


def match(policies, starts, moves_per_turn, turns, seed):
    rng = random.Random(seed)
    rounds, points = [0, 0], [0.0, 0.0]
    for index, (board, specials) in enumerate(starts):
        score, charge = [0.0, 0.0], [0.0, 0.0]
        for turn in range(turns * 2):
            side = (index + turn) % 2
            moves = moves_per_turn
            # A cap bounds long extra chains equally for both seats.
            for _ in range(moves_per_turn + 8):
                if not moves:
                    break
                candidate = choose(board, specials, policies[side], moves, charge[side],
                                   rng.getrandbits(64), turn < turns * 2 - 1)
                if candidate is None:
                    break
                result = play(board, candidate, rng)
                if result is None:
                    break
                score[side] += ms._instant_score(result)
                charge[side] = min(7, charge[side] + result.blue_cells)
                moves -= not bool(result.extra_moves)
                board, specials = result.board, result.special_board
        points = [a + b for a, b in zip(points, score)]
        if score[0] != score[1]:
            rounds[int(score[1] > score[0])] += 1
    return rounds, points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, nargs="+")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--moves", type=int, default=2)
    parser.add_argument("--turns", type=int, default=2, help="turns per player per round")
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--policies", choices=POLICIES, nargs="+", default=POLICIES)
    args = parser.parse_args()
    if min(args.rounds, args.moves, args.turns, args.seeds) < 1:
        parser.error("rounds, moves, turns and seeds must be positive")
    policies = tuple(dict.fromkeys(args.policies))
    if len(policies) < 2:
        parser.error("choose at least two distinct policies")
    boards = []
    paths = (path for folder in args.recording for path in sorted(folder.glob("[0-9][0-9][0-9].json")))
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["profile"]["rules"].get("pvpMode") != 0:
            continue
        if any(not 1 <= color <= 6 for row in record["board"] for color in row):
            continue
        # Use captured colours, with neutral rules and ordinary specials.
        boards.append((record["board"], [[v if v in CLASSIC else 0 for v in row]
                                          for row in record["special_board"]]))
    if not boards:
        parser.error("recording contains no Versus boards")
    wins, ties, margin, head_to_head = Counter(), Counter(), Counter(), Counter()
    for seed in range(args.seeds):
        rng = random.Random(seed)
        starts = rng.choices(boards, k=args.rounds)
        for a, b in itertools.combinations(policies, 2):
            for pair in ((a, b), (b, a)):
                rounds, points = match(pair, starts, args.moves, args.turns, seed)
                margin[pair[0]] += points[0] - points[1]
                margin[pair[1]] += points[1] - points[0]
                if rounds[0] == rounds[1]:
                    ties.update(pair)
                else:
                    winner = int(rounds[1] > rounds[0])
                    wins[pair[winner]] += 1
                    head_to_head[pair[winner], pair[1 - winner]] += 1
    games = (len(policies) - 1) * 2 * args.seeds
    print(f"{len(boards)} starting boards; {games} matches per policy")
    for name in sorted(policies, key=lambda p: (wins[p], margin[p]), reverse=True):
        print(f"{name:9s} W-D-L {wins[name]}-{ties[name]}-{games-wins[name]-ties[name]}"
              f"  mean score margin {margin[name]/games:+.1f}")
    if {"setup", "setup_deny"}.issubset(policies):
        print(f"setup vs setup_deny: {head_to_head['setup', 'setup_deny']}-"
              f"{head_to_head['setup_deny', 'setup']} decisive match wins")


if __name__ == "__main__":
    main()
