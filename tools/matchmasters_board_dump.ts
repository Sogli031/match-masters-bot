import "frida-il2cpp-bridge";

type RawSlot = {
    x: number;
    y: number;
    row: number;
    col: number;
    color: number;
    color2: number;
    value: number;
    originalValue: number;
    holdValue: number;
    relatedPlayerIndex: number;
    status: number;
    score: number;
    scoreModifierOrigin: number;
    scoreModifierBonus: number;
    energy: number;
    hitPoints: number;
    origin: number;
    damageable: boolean;
    autoDestruct: boolean;
    canBeMatched: boolean;
    movable: boolean;
    createdFromCombo: boolean;
    skipDestroyTillMoveEnds: boolean;
    activateOnHitpointReduced: boolean;
    isLiveEventPiece: boolean;
};

type BoardAbilityState = {
    type: number | null;
    name: string | null;
    index: number | null;
};

type PlayerState = {
    index: number | null;
    score: number | null;
    turn_score: number | null;
    spawn_bonus: number | null;
    max_round_score: number | null;
    rounds_won: number | null;
    energy: number | null;
    energy_to_ability: number | null;
    energy_full: boolean | null;
    energy_colors: number[] | null;
    booster_activations_left: number | null;
    score_multiplier: number | null;
    health: number | null;
    slot_type: number | null;
    bonus_tiles_collected: number | null;
    special_ability_type: number | null;
    special_ability_name: string | null;
    special_ability_description: string | null;
    special_ability_params: Record<string, string> | null;
    special_ability_fields: Record<string, any> | null;
    /** Counters the engine computes for the ability (MixyMeow.UsesLeft and
     *  friends live as strings in BoardModel.extraData, behind getters). Read
     *  on manual dumps only -- the getters allocate -- and null otherwise. */
    special_ability_engine: Record<string, number | null> | null;
    /** Raw SlotColor enum values, in the order collected by the SE passive
     *  path. Field-only read on manual dumps; useful to verify Take(n) against
     *  the prediction without inferring colours from a randomly refilled board. */
    ufo_colors_exploded_this_move: number[] | null;
    active_special_ability_type: number | null;
    is_ability_used_this_move: boolean | null;
    is_board_ability_used_this_move: boolean | null;
    board_ability_used_this_move: number | null;
    active_board_ability: number | null;
    board_abilities: BoardAbilityState[] | null;
    is_my_turn: boolean | null;
    has_played_this_turn: boolean | null;
    player_type: number | null;
    mutation_fields: Record<string, any> | null;
};

type RulesState = {
    id: string | null;
    title: string | null;
    board_model_name: number | null;
    pvp_mode: number | null;
    rumble_type: number | null;
    board_size: number | null;
    colors_count: number | null;
    moves_per_turn: number | null;
    additional_moves: number | null;
    turns_per_game: number | null;
    time_per_turn: number | null;
    is_timer: boolean | null;
    extra_move_enabled: boolean | null;
    energy_mult: number | null;
    special_combo_score_multiplier: number | null;
    both_colors_charge_energy: boolean | null;
    explosion_on_match: boolean | null;
    destroy_row_on_horizontal_match: boolean | null;
    destroy_column_on_vertical_match: boolean | null;
    vertical_match_increase_multiplier: boolean | null;
    vertical_match_destroy_color: boolean | null;
    specials_auto_explode: boolean | null;
    all_specials_lightning: boolean | null;
    every_match_is_special: boolean | null;
    match_creates_special_chance: number | null;
    bigger_bomb_area: boolean | null;
    ability_locked: boolean | null;
    reshuffle_every_turn: boolean | null;
    solo_refill_mode: boolean | null;
    solo_targets: number[] | null;
    rumble_players_amount: number | null;
    is_square_match: boolean | null;
    // Which SlotColors charge the booster and by how much: colorComboEnergy is
    // the base table, _colorEnergyOverride the mode's override. Keys are
    // SlotColor numbers as strings. The field sweep below only records these
    // dictionaries as type markers, so they are decoded here explicitly --
    // multiplier-mushrooms (2026-08-24) charges a non-blue color and the bot
    // cannot know which without this.
    color_combo_energy: Record<string, number> | null;
    color_energy_override: Record<string, number> | null;
    // Every MatchRulesModel field the bridge can read, under its engine name.
    // The named entries above stay as they are -- they are what the bot's code
    // reads -- but this is what makes "what is actually turned on in this
    // match" answerable without anyone having to pick the fields in advance.
    engine_fields: Record<string, any> | null;
};

type GameStateBlock = {
    game_state: number | null;
    is_active: boolean | null;
    is_singleplayer_board: boolean | null;
    moves: number | null;
    moves_made_this_turn: number | null;
    chain_reaction: number | null;
    current_turn: number | null;
    turns: number | null;
    turns_total: number | null;
    current_round: number | null;
    rounds: number | null;
    rounds_total: number | null;
    accumulated_move_score: number | null;
    accumulated_turn_score: number | null;
    remaining_time: number | null;
    timer_paused: boolean | null;
    current_player_index: number | null;
    opponent_index: number | null;
    energy_charging_colors: number[] | null;
    opponent_energy_charging_colors: number[] | null;
    players: PlayerState[];
    rules: RulesState | null;
};

/** Froggy Fu's own live state, read off the ability instance.
 *
 *  `attractionMoveData` is the point of this block: the engine records every
 *  swap the gather performs, in order, so it is the only place the finished
 *  pull can be read from. The animation plays those steps out one at a time,
 *  which is why no captured frame ever shows the settled board -- see
 *  docs/game_mode_logic_from_code.md section 9. */
type FroggyState = {
    attraction_moves: number[][][] | null;
    pull_cluster: number[][] | null;
    stamped_positions: number[][] | null;
    planned_lotuses: number[][] | null;
    error: string | null;
};

type JellyState = {
    keys: Record<string, string | null> | null;
    all_infected: number[][] | null;
    source_cell: number[][] | null;
    conversion_point: number[] | null;
    verified: boolean;
    error: string | null;
};

type Snapshot = {
    schema_version: number;
    type: string;
    captured_at: string;
    reason: string;
    stable: boolean;
    rows: number;
    columns: number;
    game_logic: string;
    board_object: string;
    board_fields: Record<string, any> | null;
    board_directions: Record<string, any> | null;
    /** Per-column `CellModel.scoreMultiplier`, left to right; null when unread. */
    cell_multipliers: number[] | null;
    /** CellModel.cellType per cell as [row][col]; null when not read. */
    cell_types: number[][] | null;
    mutation_fields: Record<string, any> | null;
    active_mutations: Record<string, any>[] | null;
    board_extra_data: Record<string, string> | null;
    /** What the extraData read saw: dictionary field names, count, entry
     *  layout and any per-entry error. The played board's dictionary has read
     *  as {} in every recording while the engine demonstrably keeps the jelly
     *  zone and Mixy's UsesLeft in it, so the read itself is under suspicion
     *  and this is the evidence a live match leaves behind. */
    board_extra_data_diag: Record<string, any> | null;
    jelly: JellyState | null;
    froggy: FroggyState | null;
    signature: string;
    state_signature: string;
    slots: RawSlot[];
    state: GameStateBlock | null;
    state_error: string | null;
    /** The game build this snapshot was read from (Il2Cpp.application.version),
     *  so a weird move can later be dated to "since the game updated" instead
     *  of guessed at. Read once at attach. */
    game_version: string | null;
    /** name -> numeric value for every member of the engine enums the host has
     *  hardcoded numbers for. The host checks these against its own tables: an
     *  update that inserts a member mid-enum shifts every later value, and the
     *  shifted numbers are all still "known", so no unknown-value warning would
     *  ever fire -- the board would simply be read wrong. Read once at attach
     *  (literal fields, i.e. metadata; see readEnumTables) and cached. */
    enums: Record<string, Record<string, number>> | null;
};

const EXPECTED_OFFSETS: Record<string, number> = {
    "GameLogic.board": 0xb8,
    "GameLogic.currentGameState": 0xd0,
    "GameLogic.isAISimulation": 0xe8,
    "BoardModel.slots": 0x20,
    "SlotModel.color": 0x10,
    "SlotModel.color2": 0x11,
    "SlotModel.value": 0x12,
    "SlotModel.originalValue": 0x13,
    "SlotModel.holdValue": 0x14,
    "SlotModel.relatedPlayerIndex": 0x15,
    "SlotModel.status": 0x18,
    "SlotModel.score": 0x1c,
    "SlotModel.scoreModifierOrigin": 0x1d,
    "SlotModel.scoreModifierBonus": 0x1e,
    "SlotModel.energy": 0x1f,
    "SlotModel.hitPoints": 0x20,
    "SlotModel.origin": 0x2c,
};

const SLOT_FALLBACKS: Record<string, [number, "u8" | "u32" | "bool"]> = {
    color: [0x10, "u8"],
    color2: [0x11, "u8"],
    value: [0x12, "u8"],
    originalValue: [0x13, "u8"],
    holdValue: [0x14, "u8"],
    relatedPlayerIndex: [0x15, "u8"],
    status: [0x18, "u32"],
    score: [0x1c, "u8"],
    scoreModifierOrigin: [0x1d, "u8"],
    scoreModifierBonus: [0x1e, "u8"],
    energy: [0x1f, "u8"],
    hitPoints: [0x20, "u8"],
    damageable: [0x21, "bool"],
    autoDestruct: [0x23, "bool"],
    canBeMatched: [0x24, "bool"],
    movable: [0x25, "bool"],
    createdFromCombo: [0x26, "bool"],
    skipDestroyTillMoveEnds: [0x27, "bool"],
    activateOnHitpointReduced: [0x28, "bool"],
    origin: [0x2c, "u32"],
    isLiveEventPiece: [0x30, "bool"],
};

let gameLogicClass: Il2Cpp.Class | null = null;
let gameDataClass: Il2Cpp.Class | null = null;
let boardClass: Il2Cpp.Class | null = null;
let slotClass: Il2Cpp.Class | null = null;
let cachedGameLogic: Il2Cpp.Object | null = null;
let froggyClass: Il2Cpp.Class | null = null;
let cachedFroggy: Il2Cpp.Object | null = null;
// Il2Cpp.gc.choose walks the heap, and on Unity 6 it does so with the world
// stopped: the game freezes for the walk (~37 ms measured), and the bridge
// calls back into JavaScript while every game thread is suspended. A game
// thread suspended inside one of this agent's hooks holds the JS lock, and
// then the callback can never run and the world is never restarted -- the
// game stays frozen. Three recorded mid-match freezes (2026-09-07, -12, -14)
// all happened while matches were running heap walks on a timer, one of them
// every 5 s. So inside a match a walk is a budget, not a retry loop:
//
// * the abilities are looked up on the players first, which is field reads;
// * one walk per match with no hint at all (the ability may exist before
//   anything shows on the board);
// * a few more only once the board proves the ability is in play (a lotus
//   tile, a jelly key), spaced out, and then never again for that match.
const ABILITY_CHOOSE_BLIND_PER_MATCH = 1;
const ABILITY_CHOOSE_HINTED_PER_MATCH = 3;
const ABILITY_CHOOSE_SPACING_MS = 10000;
// Match3Engine.SpecialAbilityType (IL2CPP metadata 2026-08-21). Each player's
// PlayerModel.specialAbilityType says which booster they brought, so a match
// with neither of these on either side needs no walk at all -- and every
// match start used to pay both blind walks for nothing (instances=0 in every
// logged one; the 09:08:24 freeze was in one of them).
const ABILITY_TYPE_JELLY_SE = 60;
const ABILITY_TYPE_FROGGY_FU = 63;
let froggyChooses = 0;
let froggyChooseAfter = 0;
// GameLogic walks inside a running match. resolveGameLogic only walks there
// when the cached logic's board reads null (every other in-match state returns
// the cache), and that used to be unbudgeted: one walk from the poll and a
// second from matchEnded in the same tick, again on every tick for as long as
// the board stayed null. Now it is a budget like the ability walks: a couple
// per match, spaced out; past it the cached logic is kept, the poll errors on
// the null board, and the "nema table" / quiet backstops close the match.
const IN_MATCH_RESOLVE_WALKS_PER_MATCH = 2;
const IN_MATCH_RESOLVE_SPACING_MS = 5000;
let inMatchResolveWalks = 0;
let inMatchResolveAfter = 0;
// SlotModel.value of the Froggy lotus. Its presence on the board is the cheap
// proof that this match is a Froggy one, read off slots that are dumped anyway.
const FROGGY_LOTUS_SLOT_VALUE = 40;
let jellyClass: Il2Cpp.Class | null = null;
let cachedJelly: Il2Cpp.Object | null = null;
let jellyChooses = 0;
let jellyChooseAfter = 0;
// Every heap walk this agent takes, for the host's freeze log: how many, the
// last one's purpose and cost, and when it ran. Sent with each heartbeat, and
// each walk also announces itself before it stops the world, so a freeze that
// starts inside one leaves its name behind.
let chooseCount = 0;
let lastChooseWhy: string | null = null;
let lastChooseMs: number | null = null;
let lastChooseAt: number | null = null;
// Heartbeat: proof of life for the host's freeze watchdog. A settled board
// sends nothing, so silence alone cannot tell "quiet" from "stuck".
const HEARTBEAT_ACTIVE_MS = 1000;
const HEARTBEAT_IDLE_MS = 5000;
let heartbeatAfter = 0;
let lastTickMs = 0;
let maxTickMs = 0;
// The jelly writes its zone into BoardModel.extraData under engine-formatted
// keys; any of them naming the jelly or its infected area means the SE is live.
const JELLY_EXTRA_DATA_HINT = /jelly|infected/i;
// The key strings the engine formats per ability type and player index. They do
// not change while a match runs, so they are resolved once and then only their
// values are read -- see readJellyState.
let cachedJellyKeys: Record<string, string | null> | null = null;
// The engine's own deserialiser allocates, so it runs on demand rather than on
// every poll: manual dumps always, and in trace mode on settled boards no more
// often than this.
let jellyDeepAfter = 0;
const JELLY_DEEP_INTERVAL_MS = 500;
// The board whose `extraData` actually carries the jelly keys. Repeated manual
// dumps (2026-08-23/24) showed `GameLogic.board`'s dictionary empty for whole
// matches while `get_AllInfected` -- which walks player -> logic -> board --
// found the area, so the engine demonstrably writes to some *other* BoardModel
// instance. When the main read comes back empty and a jelly is live, the heap
// is swept for BoardModel instances and the one carrying a jelly key is
// adopted; found once, it is cached for the rest of the match.
let cachedExtraDataBoard: Il2Cpp.Object | null = null;
let extraDataScanned = false;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let pollMilliseconds = 250;
// What the agent does while no match is running. Measured on 2026-08-21:
// one `Il2Cpp.gc.choose` costs ~37 ms and one full snapshot ~114 ms, so the
// old behaviour -- attach, then poll both every 100 ms whether or not a match
// exists -- kept a thread inside the game process busy more than full time,
// in the lobby, where the game allocates hardest. Reading the *static*
// `GameLogic.GameCount` costs 0 ms and ticks exactly when a match starts, so
// idling is now free and the heap walk happens once per match.
let idleMilliseconds = 1000;
let matchActive = false;
let lastGameCount: number | null = null;
// A snapshot that never changes means the match is over (the engine leaves the
// finished GameLogic on the heap, board and all -- measured), so an idle
// timeout is the backstop for ends this agent cannot name.
let lastChangeTimestamp = 0;
// An unchanged board alone is not an ended match. Timeout is opt-in.
let idleAfterQuietMs = 0;
let consecutivePollErrors = 0;
// The counter only rises once per match, so on its own it cannot recover from
// a false end: a long popup can outlast the quiet timeout while the match is
// still very much on, and the counter would never rise again to say so. This
// is the recheck that reopens it -- one heap walk (~37 ms, measured) every few
// seconds while idle, which is also what catches attaching mid-match.
let recheckAfter = 0;
const IDLE_RECHECK_MS = 5000;
// Outside a match the GameLogic heap walk is paced by what the last one cost.
// Measured 2026-09-15 00:12: right after a match the lobby walks took 155, 290,
// 2022, 495 and 1292 ms within nine seconds -- the game frozen for two whole
// seconds at a time, for a check nobody was waiting on. A slow walk now pushes
// the next one out by IDLE_CHOOSE_COST_FACTOR times its cost, between the
// normal check interval and IDLE_CHOOSE_MAX_DELAY_MS.
//
// The delay is the one thing that can hide a match start, so it is bounded on
// two sides. First, the constructor hook is off in the shipping config (see
// READER_CTOR_HOOK in memory_gui.py), so the walk it defers is the ONLY way a
// new match gets noticed: with the cap at 30 s, one 2 s lobby walk blinded the
// agent for as long as the pending window lasts, and the match started inside
// that blindness was never picked up until the user left and re-entered it
// (reported 2026-09-15). The cap is now well under the pending window. Second,
// a rising GameCount (the counter, or `wake`) clears the delay outright: a
// match that just started is precisely the moment a walk is worth its cost.
let idleChooseAfter = 0;
const IDLE_CHOOSE_COST_FACTOR = 20;
const IDLE_CHOOSE_MAX_DELAY_MS = 8000;
// Once the lobby walk has found the last match's leftover logic, that object
// is kept and NOT walked for again on every state check: each lobby walk stops
// the world for 160-180 ms (measured 2026-09-15 09:16-09:19, one every 4 s),
// and the ninth of those never came back -- the game froze in the lobby,
// right after a concede, with the agent's last message the walk's "begin".
// A rising GameCount (or `wake`) still walks at once; this is only the
// backstop for a match start the counter did not announce.
const IDLE_WALK_INTERVAL_MS = 60000;
// How many resolves the pacing refused, for the heartbeat: a missed start with
// this climbing is the pacing, not the engine.
let deferredResolves = 0;
// Which match the per-match heap-walk budgets were last reset for. The quiet
// timeout closes a match whose board stops moving and reopens it when play
// resumes; that is still the same match, and resetting the budgets on every
// reopen cost two walks every ~46 s while the board simply sat there
// (2026-09-15 00:02-00:08).
let budgetMatchHandle: string | null = null;
// The engine's own GameState, checked on a slow timer, is the signal that
// actually works. Measured 2026-08-21: attaching mid-match picks the match up
// through this test every time, while waiting in the lobby and then entering a
// match did not -- GameCount does not rise the way this agent assumed. So the
// state is the primary signal now and the counter is only an accelerator.
//
// It costs one heap walk (~37 ms) per check, i.e. under 2% of one core at this
// interval, against the ~150% the original always-on poll spent doing the same
// walk plus a full snapshot every 100 ms.
let stateCheckAfter = 0;
const IDLE_STATE_CHECK_MS = 2000;
// A fresh agent cannot tell a running match from the last one's corpse: both
// have a board and an in-match state (-3 or -9 in every recorded case). The
// four "vec u partiji" corpses of 2026-09-18/19 were each read as live for
// ~30 s until the next match replaced them. So what the first tick finds is
// only a candidate: it opens once the logic shows life (state, moves, turn,
// player, turn score or clock change) or a different logic turns up. A match
// on our untimed turn stays shut until the user asks for a move -- `wake`
// opens it then, exactly as it always did.
let attachProbe: { key: string | null; print: string } | null = null;
// The counter rises when the engine *creates* the GameLogic, which is before it
// hands it a board -- so the check right at that moment can legitimately fail,
// and the counter will never rise again to give a second chance. This keeps
// trying for a while after a rise instead of losing the match entirely.
let pendingMatchUntil = 0;
let pendingSince: number | null = null;
const PENDING_MATCH_MS = 30000;
// Option B: instead of finding the match's GameLogic by walking the heap, be
// told about it. `GameLogic..ctor` is hooked and simply records `this`, so
// resolving costs a pointer check rather than ~37 ms of `Il2Cpp.gc.choose`.
//
// Hooking is not free of risk here -- this is an ARM64 game running under
// BlueStacks' native bridge, which is why hooking was written off once before
// -- so it is strictly an optimisation: if installing it throws, or the
// recorded pointer does not hold up, everything falls back to the heap walk.
let useCtorHook = true;
let ctorHookState: "off" | "on" | "failed" = "off";
let ctorHookError: string | null = null;
let constructedHandle: NativePointer | null = null;
// The installed .ctor listeners, so switching the hook off (configure with
// withCtorHook=false) really removes them instead of leaving a JS callback on
// every GameLogic construction for the rest of the process.
const ctorHookListeners: InvocationListener[] = [];
let ctorHookDetachPending = false;
let constructedSeen: string | null = null;
let constructedCount = 0;
// The last few constructions, newest last. One pointer is not enough to catch
// a new match: the AI's simulation GameLogics construct constantly, so by the
// time resolve() looks, `constructedHandle` usually points at a sim and the
// real new match's instance is a few constructions back. Measured 2026-08-26
// 02:47: a Chest match abandoned at currentGameState -9 (an in-match value)
// kept the cache alive forever, and the next match's 7x7 board was never
// picked up -- the bot kept playing the dead 8x8 board.
const CONSTRUCTED_RING_MAX = 32;
const constructedRing: NativePointer[] = [];
// constructedCount at the last ring scan, so a poll without new constructions
// costs nothing extra.
let ringScannedAtCount = -1;
// How often the hook actually saved a heap walk, and how often it did not --
// the only way to tell "the hook works" from "the hook silently does nothing".
let resolveByHook = 0;
let resolveByChoose = 0;
// Surrender is invisible to the state gate: a conceded match leaves the local
// GameLogic frozen mid-turn with an in-match state, so the only end that ever
// fired was the 45 s quiet timeout -- during which auto kept swiping at a
// board nobody was playing. The engine does have one exact word for it:
// Match3Engine.Match3GameData.Conceded() runs the moment either side gives up
// (IL2CPP metadata 2026-08-21). The hook records the timestamp and nothing
// else -- same standing rule as the ctor hook: read, never call.
let concedeHookState: "off" | "on" | "failed" = "off";
let concedeHookError: string | null = null;
let concededAt: number | null = null;
// Leaving a match is invisible to everything above: no Conceded() runs in a
// solo mode or when the client just backs out to the lobby, and the state
// stays in-match on a GameLogic nobody is playing (the abandoned Chest match
// measured 2026-08-26). The engine does tear the match down, though:
// Match3Engine.GameLogic.Dispose() runs on the logic of the match being left
// (and on every finished one). Simulations are disposed all the time, so the
// hook only records WHICH object went, and matchEnded() compares it with the
// logic it is actually reading. Same standing rule: read, never call.
let disposeHookState: "off" | "on" | "failed" = "off";
let disposeHookError: string | null = null;
let disposedHandle: NativePointer | null = null;
let disposedAt: number | null = null;
let disposedCount = 0;
// The GameLogic the last match ended on. The engine leaves it on the heap with
// its board intact and -- after a concede, an abandoned match or the quiet
// timeout -- with an IN-MATCH state (a conceded versus match sat at -3 for the
// whole 45 s quiet wait, 2026-09-15 08:46). Every "is a match running" test
// then keeps answering yes on that corpse: the idle state check reopened it two
// seconds after the quiet timeout closed it, the resolve cached it as the live
// logic, and a real match that started meanwhile was never looked at. Held as
// a string because the pointer object is gone with the cache; compared, never
// dereferenced.
let endedLogicHandle: string | null = null;

function isEndedLogic(instance: Il2Cpp.Object): boolean {
    if (endedLogicHandle == null) return false;
    try {
        return instance.handle.toString() === endedLogicHandle;
    } catch (_) {
        return false;
    }
}

// Matches that are over for good: a concede, a Dispose, a finished state, the
// user's own "Prekini partiju". Their GameLogic is never read again, whatever
// its state says and however its board moves -- unlike the soft end above,
// where a quiet board is only a guess and a board that moves reopens it.
// Keyed by GameLogic pointer AND board pointer, so an address the GC hands to
// a new match's logic does not inherit the verdict (its board is a new object).
// The host persists these keys across its own restarts and hands them back on
// attach (markDead): a fresh agent otherwise takes the previous session's dead
// match for a running one ("vec u partiji" on a Solo Challenge that had ended,
// every GUI restart, 2026-09-15 09:06).
const deadLogicKeys = new Set<string>();
const DEAD_LOGIC_KEYS_MAX = 64;
// Ends that are guesses rather than the engine's word; only these may reopen.
const SOFT_END_REASONS = new Set(["tabla se ne menja", "nema table", "GameLogic je nestao"]);

function boardPointerOf(instance: Il2Cpp.Object): string {
    try {
        const board = instance.field<Il2Cpp.Object>("board").value;
        return board == null ? "0" : board.handle.toString();
    } catch (_) {
        try {
            return instance.handle.add(EXPECTED_OFFSETS["GameLogic.board"]).readPointer().toString();
        } catch (_2) {
            return "?";
        }
    }
}

function logicKey(instance: Il2Cpp.Object): string | null {
    try {
        return `${instance.handle.toString()}/${boardPointerOf(instance)}`;
    } catch (_) {
        return null;
    }
}

function isDeadLogic(instance: Il2Cpp.Object): boolean {
    if (deadLogicKeys.size === 0) return false;
    const key = logicKey(instance);
    return key != null && deadLogicKeys.has(key);
}

function markLogicDead(key: string | null): void {
    if (key == null) return;
    deadLogicKeys.add(key);
    while (deadLogicKeys.size > DEAD_LOGIC_KEYS_MAX) {
        const oldest = deadLogicKeys.values().next().value;
        if (oldest == null) break;
        deadLogicKeys.delete(oldest);
    }
}

/** `GameLogic.GameIndex`: the engine numbers every logic it builds, so the
 *  highest index among the real (non-simulation) instances is the newest
 *  match. `gc.choose` has no order, and "the last one" was last game's corpse
 *  often enough (2026-09-15 09:05: a finished Color Crush lost to the disposed
 *  Multiplier Mushrooms match before it, and the agent kept reading that). */
function readGameIndex(instance: Il2Cpp.Object): number | null {
    try {
        const field = instance.tryField<any>("<GameIndex>k__BackingField");
        if (field != null) return asNumber(field.value);
    } catch (_) {
    }
    return null;
}
// Reported once: every candidate claiming to be a simulation means the
// `isAISimulation` read is wrong, and that is worth knowing about.
let simulationOnlyReported = false;
// The engine's own GameState enum, which does not run the way the member order
// suggests: the in-match states are NEGATIVE (-1 Initializing, -3 waiting for
// the turn, -5 move playing, -7 move end, down to -9) and the finished states
// are positive (2..7). This is the numbering memory_gui has been showing all
// along in GAME_STATE_LABELS; reading it as "0..8 means a match" meant the gate
// could never recognise one -- which is exactly what it did.
const GAME_STATE_IN_MATCH_MAX = -1;
const GAME_STATE_IN_MATCH_MIN = -9;
const GAME_STATE_FINISHED_MIN = 2;
const GAME_STATE_FINISHED_MAX = 7;
let requiredStableSamples = 3;
let candidateSignature: string | null = null;
let candidateCount = 0;
let lastSentSignature: string | null = null;
let lastSentStateSignature: string | null = null;
// Whether the last snapshot that went out called the board settled. See
// sendSnapshot: the settle itself is a change worth resending for.
let lastSentStable: boolean | null = null;
// Game-state reading stays off until the host asks for it, so the poll that
// starts on load can only ever touch the board.
let includeState = false;
// Debug trace: also push the unsettled frames between two stable boards. Off
// by default -- normal play only wants the settled board, and every extra
// frame is another read in the game's process.
let traceMode = false;
let ready = false;
let lastError: string | null = null;

function asNumber(value: any): number {
    if (typeof value === "number") return value;
    if (typeof value === "boolean") return value ? 1 : 0;
    if (value == null) return 0;
    if (typeof value.toNumber === "function") return value.toNumber();
    if (typeof value.tryField === "function") {
        const underlying = value.tryField("value__");
        if (underlying != null) return asNumber(underlying.value);
    }
    const parsed = Number(value.toString());
    if (!Number.isFinite(parsed)) throw new Error(`not a numeric value: ${value}`);
    return parsed;
}

function readNative(object: Il2Cpp.Object, offset: number, kind: "u8" | "u32" | "bool"): any {
    const address = object.handle.add(offset);
    if (kind === "u32") return address.readU32();
    if (kind === "bool") return address.readU8() !== 0;
    return address.readU8();
}

function readSlotField(object: Il2Cpp.Object, name: string): any {
    try {
        const value = object.field<any>(name).value;
        if (
            typeof value === "number"
            || typeof value === "boolean"
            || (value != null && typeof value.toNumber === "function")
        ) {
            return value;
        }
        if (value != null && typeof value.tryField === "function") {
            const underlying = value.tryField("value__");
            if (underlying != null) return underlying.value;
        }
        const fallback = SLOT_FALLBACKS[name];
        if (fallback != null) return readNative(object, fallback[0], fallback[1]);
        return value;
    } catch (error) {
        const fallback = SLOT_FALLBACKS[name];
        if (fallback == null) throw error;
        return readNative(object, fallback[0], fallback[1]);
    }
}

function readBoolean(object: Il2Cpp.Object, name: string): boolean {
    const value = readSlotField(object, name);
    return typeof value === "boolean" ? value : asNumber(value) !== 0;
}

// The engine enums whose numeric values the Python side has hardcoded. Read
// once at attach, cached for the life of the session: enum members are
// *literal* static fields, so their values come out of the IL2CPP metadata
// blob (il2cpp_field_static_get_value) -- a memory/metadata read, no game
// method runs. The same mechanism produced data/il2cpp_symbols.json live on
// 2026-08-21, so it is proven on this exact game.
const ENUM_TABLE_CLASSES = [
    "Match3Engine.SlotValueType",
    "Match3Engine.SlotColor",
    "Match3Engine.BoardModelName",
    "Match3Engine.SpecialAbilityType",
];
let cachedEnumTables: Record<string, Record<string, number>> | null = null;
let cachedGameVersion: string | null = null;

function readEnumTables(image: Il2Cpp.Image): Record<string, Record<string, number>> {
    const tables: Record<string, Record<string, number>> = {};
    for (const fullName of ENUM_TABLE_CLASSES) {
        let klass: Il2Cpp.Class | null = null;
        try {
            klass = image.class(fullName);
        } catch (_) {
            klass = null;
        }
        if (klass == null) continue;
        const table: Record<string, number> = {};
        for (const field of klass.fields) {
            let name: string | null = null;
            try {
                name = field.name;
            } catch (_) {
                continue;
            }
            if (name == null) continue;
            try {
                if (!field.isLiteral) continue;  // skips the instance value__
                table[name] = asNumber(field.value);
            } catch (_) {
                // One unreadable member costs that member, not the table --
                // the host reports it as missing, which is the honest answer.
            }
        }
        // Keyed by the short name ("SlotValueType"): that is what the host's
        // expected tables use, and the namespace carries no information here.
        tables[fullName.split(".").pop() as string] = table;
    }
    return tables;
}

function findAssemblyImage(): Il2Cpp.Image {
    const preferred = ["Match3Engine", "Match3Engine.dll"];
    for (const name of preferred) {
        const assembly = Il2Cpp.domain.tryAssembly(name);
        if (assembly != null) return assembly.image;
    }
    for (const assembly of Il2Cpp.domain.assemblies) {
        try {
            assembly.image.class("Match3Engine.GameLogic");
            return assembly.image;
        } catch (_) {
        }
    }
    throw new Error("assembly containing Match3Engine.GameLogic was not found");
}

function initializeMetadata(): void {
    const image = findAssemblyImage();
    gameLogicClass = image.class("Match3Engine.GameLogic");
    boardClass = image.class("Match3Engine.BoardModel");
    try {
        gameDataClass = image.class("Match3Engine.Match3GameData");
    } catch (_) {
        gameDataClass = null;
    }
    slotClass = image.class("Match3Engine.SlotModel");
    try {
        froggyClass = image.class("Match3Engine.FroggyFu");
    } catch (_) {
        froggyClass = null;
    }
    try {
        jellyClass = image.class("Match3Engine.JellySE");
    } catch (_) {
        jellyClass = null;
    }

    const checks: Record<string, any> = {};
    const descriptors: [string, Il2Cpp.Class, string][] = [
        ["GameLogic.board", gameLogicClass, "board"],
        ["BoardModel.slots", boardClass, "<slots>k__BackingField"],
        ["SlotModel.color", slotClass, "color"],
        ["SlotModel.color2", slotClass, "color2"],
        ["SlotModel.value", slotClass, "value"],
        ["SlotModel.originalValue", slotClass, "originalValue"],
        ["SlotModel.holdValue", slotClass, "holdValue"],
        ["SlotModel.relatedPlayerIndex", slotClass, "relatedPlayerIndex"],
        ["SlotModel.status", slotClass, "status"],
        ["SlotModel.score", slotClass, "score"],
        ["SlotModel.scoreModifierOrigin", slotClass, "scoreModifierOrigin"],
        ["SlotModel.scoreModifierBonus", slotClass, "scoreModifierBonus"],
        ["SlotModel.energy", slotClass, "energy"],
        ["SlotModel.hitPoints", slotClass, "hitPoints"],
        ["SlotModel.origin", slotClass, "origin"],
    ];
    for (const [label, klass, fieldName] of descriptors) {
        try {
            const actual = klass.field(fieldName).offset;
            checks[label] = {
                expected: EXPECTED_OFFSETS[label],
                actual,
                matches: actual === EXPECTED_OFFSETS[label],
            };
        } catch (error) {
            checks[label] = { expected: EXPECTED_OFFSETS[label], error: String(error) };
        }
    }
    // Once, here, never per dump: the tables are compile-time constants for
    // the life of the process, and the per-move budget has been blown by less.
    const enumStart = Date.now();
    try {
        cachedEnumTables = readEnumTables(image);
    } catch (_) {
        cachedEnumTables = null;
    }
    const enumMilliseconds = Date.now() - enumStart;
    try {
        cachedGameVersion = Il2Cpp.application.version ?? null;
    } catch (_) {
        cachedGameVersion = null;
    }
    send({
        type: "metadata",
        assembly: image.assembly.name,
        offsets: checks,
        game_version: cachedGameVersion,
        enums: cachedEnumTables,
        enum_read_ms: enumMilliseconds,
    });
}

/** Is this the engine's own lookahead rather than the match being played?
 *
 *  `GameLogic` is also instantiated for AI simulation, board and all. Those
 *  instances must never become the board this bot plays on -- with the ctor
 *  hook they arrive far more often than the heap walk ever surfaced them. */
function isSimulation(instance: Il2Cpp.Object): boolean {
    try {
        const field = instance.tryField<any>("isAISimulation");
        if (field != null) {
            const value = field.value;
            if (typeof value === "boolean") return value;
            return asNumber(value) !== 0;
        }
    } catch (_) {
    }
    try {
        return instance.handle.add(EXPECTED_OFFSETS["GameLogic.isAISimulation"]).readU8() !== 0;
    } catch (_) {
        return false;
    }
}

function hasBoard(instance: Il2Cpp.Object): boolean {
    try {
        const board = instance.field<Il2Cpp.Object>("board").value;
        return board != null && !board.handle.isNull();
    } catch (_) {
        try {
            return !instance.handle.add(EXPECTED_OFFSETS["GameLogic.board"]).readPointer().isNull();
        } catch (_) {
            return false;
        }
    }
}

/** The usable GameLogic: playing, not simulating. */
function isPlayable(instance: Il2Cpp.Object): boolean {
    return hasBoard(instance) && !isSimulation(instance);
}

/** Has this instance's match already ended?
 *
 *  The engine leaves finished matches on the heap with their board intact, so
 *  "has a board" is not evidence of anything. Without this the cache latched
 *  onto the previous match and never let go: every later check read that dead
 *  object, saw a win state, and reported no match -- which is why the only fix
 *  was restarting the GUI, i.e. starting with an empty cache. */
function stateIsFinished(instance: Il2Cpp.Object): boolean {
    const state = readGameStateEnum(instance);
    return state != null && state >= GAME_STATE_FINISHED_MIN;
}

/** A construction newer than the cache that already looks like a real match.
 *
 *  stateIsFinished cannot catch an *abandoned* match: the engine leaves it at
 *  an in-match state (-9 observed) with its board intact, so the cache test
 *  passes forever. The ring is the counter-evidence -- when the engine has
 *  built a newer GameLogic that is playable (has a board, not an AI
 *  simulation) and unfinished, that is the match actually on screen. A fresh
 *  construction whose board is not set yet keeps the scan pending so the next
 *  poll re-checks it. */
function newerPlayableConstruction(): Il2Cpp.Object | null {
    if (cachedGameLogic == null || !useCtorHook) return null;
    if (constructedCount === ringScannedAtCount) return null;
    let sawPending = false;
    for (let i = constructedRing.length - 1; i >= 0; i--) {
        const handle = constructedRing[i];
        if (handle == null || handle.isNull()) continue;
        if (handle.equals(cachedGameLogic.handle)) continue;
        try {
            const candidate = new Il2Cpp.Object(handle);
            if (!hasBoard(candidate)) {
                sawPending = true;
                continue;
            }
            if (isPlayable(candidate) && !stateIsFinished(candidate)) {
                ringScannedAtCount = constructedCount;
                return candidate;
            }
        } catch (_) {
        }
    }
    if (!sawPending) ringScannedAtCount = constructedCount;
    return null;
}

/** Il2Cpp.gc.choose, announced and measured.
 *
 *  The "begin" message goes out before the world is stopped, so if the game
 *  never comes back the host's freeze log still names the walk it froze in. */
function chooseInstances(klass: Il2Cpp.Class, why: string): Il2Cpp.Object[] {
    chooseCount += 1;
    lastChooseWhy = why;
    lastChooseAt = Date.now();
    send({ type: "choose", phase: "begin", why, count: chooseCount, match_active: matchActive });
    const started = Date.now();
    try {
        const instances = Il2Cpp.gc.choose(klass);
        lastChooseMs = Date.now() - started;
        send({
            type: "choose", phase: "end", why, count: chooseCount,
            match_active: matchActive, ms: lastChooseMs, instances: instances.length,
        });
        return instances;
    } catch (error) {
        lastChooseMs = Date.now() - started;
        send({
            type: "choose", phase: "end", why, count: chooseCount,
            match_active: matchActive, ms: lastChooseMs, error: String(error),
        });
        throw error;
    }
}

/** The equipped ability of either player, if it is an instance of `klass`.
 *
 *  `PlayerControl.ability` is the live SpecialAbility, so an ability that a
 *  player brought is found with field reads instead of a heap walk. */
function abilityFromPlayers(klass: Il2Cpp.Class): Il2Cpp.Object | null {
    const logic = cachedGameLogic;
    if (logic == null) return null;
    try {
        for (const control of listItems(fieldValue(logic, "players"), 8)) {
            const ability = fieldValue(control, "ability");
            if (ability == null || ability.class == null) continue;
            if (ability.class.handle.equals(klass.handle) || ability.class.isSubclassOf(klass, false)) {
                return ability as Il2Cpp.Object;
            }
        }
    } catch (_) {
        // fall back to the budgeted walk
    }
    return null;
}

/** Did either player bring this SpecialAbilityType? Field reads only.
 *
 *  `true` / `false` when the players' models are readable, `null` when they
 *  are not (no players yet, unexpected layout) -- and only a definite `false`
 *  is allowed to skip a walk. */
function playersBroughtAbility(typeId: number): boolean | null {
    const logic = cachedGameLogic;
    if (logic == null) return null;
    let seen = 0;
    try {
        for (const control of listItems(fieldValue(logic, "players"), 8)) {
            const type = fieldNumber(fieldValue(control, "model"), "specialAbilityType");
            if (type == null) continue;
            seen += 1;
            if (type === typeId) return true;
        }
    } catch (_) {
        return null;
    }
    return seen > 0 ? false : null;
}

/** May an ability lookup walk the heap now? Spends the budget if so. */
function abilityChooseAllowed(onBoard: boolean, used: number, after: number): boolean {
    if (Date.now() < after) return false;
    const budget = onBoard
        ? ABILITY_CHOOSE_BLIND_PER_MATCH + ABILITY_CHOOSE_HINTED_PER_MATCH
        : ABILITY_CHOOSE_BLIND_PER_MATCH;
    return used < budget;
}

function resolveGameLogic(): Il2Cpp.Object {
    // The cache is only good while its match is still running -- see
    // stateIsFinished. Checking costs one 32-bit read; not checking cost every
    // match after the first.
    // Between matches the cache holds the corpse of the match that ended (it
    // is what the walk finds when nothing else is there): finished, dead, or
    // closed by the quiet timeout. It is kept and handed back -- every idle
    // test reads it as "no match" -- and the heap is walked for a newer object
    // only when the counter says a match started, or on the slow backstop.
    // Walking on every 2 s state check instead is what froze the game in the
    // lobby (IDLE_WALK_INTERVAL_MS).
    if (
        !matchActive
        && cachedGameLogic != null
        && hasBoard(cachedGameLogic)
        && (
            isDeadLogic(cachedGameLogic)
            || isEndedLogic(cachedGameLogic)
            || stateIsFinished(cachedGameLogic)
        )
    ) {
        const now = Date.now();
        if (now >= pendingMatchUntil && now < idleChooseAfter) return cachedGameLogic;
        cachedGameLogic = null;
    }
    // A match that just finished is still THE match until matchEnded reports
    // it: hunting for another logic here handed the poll last game's corpse
    // (in-match state, board intact) in the very tick the end should have
    // been seen, and the end was never reported (2026-09-15 09:05).
    if (
        matchActive
        && cachedGameLogic != null
        && hasBoard(cachedGameLogic)
        && stateIsFinished(cachedGameLogic)
    ) {
        return cachedGameLogic;
    }
    if (
        cachedGameLogic != null
        && hasBoard(cachedGameLogic)
        && !stateIsFinished(cachedGameLogic)
    ) {
        const fresher = newerPlayableConstruction();
        if (fresher != null) {
            cachedGameLogic = fresher;
            resolveByHook += 1;
            send({
                type: "error",
                stage: "resolve",
                message:
                    "novi GameLogic konstruisan tokom kesirane partije; "
                    + "prelazim na noviju instancu",
            });
        }
        return cachedGameLogic;
    }
    // In a match the cache only gets this far when its board reads null (or
    // an earlier in-match walk found nothing). Kept aside: if the in-match
    // walk budget says no, it is handed back instead of walking.
    const keptInMatch = matchActive ? cachedGameLogic : null;
    cachedGameLogic = null;
    if (gameLogicClass == null) throw new Error("GameLogic metadata is not initialized");
    // What the ctor hook last saw being constructed. Checked before the heap
    // walk and never trusted blindly: a simulation instance, or one whose board
    // is not set yet, sends this straight on to the walk.
    if (useCtorHook && constructedHandle != null && !constructedHandle.isNull()) {
        try {
            const candidate = new Il2Cpp.Object(constructedHandle);
            if (isPlayable(candidate) && !stateIsFinished(candidate)) {
                cachedGameLogic = candidate;
                resolveByHook += 1;
                return candidate;
            }
        } catch (_) {
        }
    }
    // Paced only while nothing suggests a match: once the counter has risen
    // the pending window is open and every walk inside it is one that may
    // pick the match up, so the pacing steps aside for it.
    if (!matchActive && Date.now() < idleChooseAfter && Date.now() >= pendingMatchUntil) {
        deferredResolves += 1;
        throw new Error("GameLogic heap walk deferred (last lobby walk was slow)");
    }
    // Inside a match: the per-match budget (IN_MATCH_RESOLVE_WALKS_PER_MATCH),
    // and never twice within the spacing -- which also keeps matchEnded from
    // walking again in the tick the poll already walked in.
    if (matchActive) {
        const now = Date.now();
        if (inMatchResolveWalks >= IN_MATCH_RESOLVE_WALKS_PER_MATCH || now < inMatchResolveAfter) {
            deferredResolves += 1;
            if (keptInMatch != null) {
                cachedGameLogic = keptInMatch;
                return keptInMatch;
            }
            throw new Error("GameLogic heap walk refused inside the match (budget spent)");
        }
        inMatchResolveWalks += 1;
        inMatchResolveAfter = now + IN_MATCH_RESOLVE_SPACING_MS;
    }
    const walkStarted = Date.now();
    const instances = chooseInstances(gameLogicClass, "GameLogic");
    if (!matchActive) {
        // Inside the pending window (the counter rose, the match's logic may
        // not have its board yet) the retries stay quick and cost-paced; a
        // lobby with nothing announced is walked once a minute at most.
        const cost = Date.now() - walkStarted;
        const paced = Math.min(
            IDLE_CHOOSE_MAX_DELAY_MS,
            Math.max(IDLE_STATE_CHECK_MS, cost * IDLE_CHOOSE_COST_FACTOR),
        );
        idleChooseAfter = Date.now() + (
            Date.now() < pendingMatchUntil ? paced : Math.max(paced, IDLE_WALK_INTERVAL_MS)
        );
    }
    const withBoard = instances.filter(hasBoard);
    resolveByChoose += 1;
    if (withBoard.length === 0) {
        throw new Error(`active Match3Engine.GameLogic not found (${instances.length} heap instances)`);
    }
    // Matches that are over for good are not candidates at all: the engine
    // leaves them on the heap looking playable, and reading one is exactly
    // the stuck reader this exists to prevent.
    const active = withBoard.filter(instance => !isDeadLogic(instance));
    if (active.length === 0) {
        throw new Error(
            `every GameLogic with a board (${withBoard.length}) belongs to a match that already ended`
        );
    }
    // Prefer a real match over the engine's AI simulation -- but only as a
    // preference. If `isAISimulation` ever reads wrong, a filter would leave
    // the bot with no board at all, which is a far worse failure than reading
    // one lookahead board: it means the match is never picked up.
    const playing = active.filter(instance => !isSimulation(instance));
    let chosen = playing.length > 0 ? playing : active;
    // The newest match wins. `gc.choose` gives no ordering guarantee, so "the
    // last one" can just as easily be last game's corpse as this game's board;
    // GameIndex is the engine's own order. A newest match that has finished is
    // still the right answer: it means the match is over, not that an older
    // in-match-looking corpse is the live one.
    let newestIndex: number | null = null;
    for (const instance of chosen) {
        const index = readGameIndex(instance);
        if (index != null && (newestIndex == null || index > newestIndex)) newestIndex = index;
    }
    if (newestIndex != null) {
        const newest = chosen.filter(instance => readGameIndex(instance) === newestIndex);
        if (newest.length > 0) chosen = newest;
    }
    // Among equals, prefer a match that has not ended, and not the one the
    // quiet timeout closed (that one only comes back through matchIsRunning's
    // moved-board test).
    const live = chosen.filter(instance => !stateIsFinished(instance));
    if (live.length > 0) chosen = live;
    const fresh = chosen.filter(instance => !isEndedLogic(instance));
    if (fresh.length > 0) chosen = fresh;
    if (playing.length === 0 && !simulationOnlyReported) {
        simulationOnlyReported = true;
        send({
            type: "error",
            stage: "resolve",
            message:
                `sve GameLogic instance (${active.length}) tvrde da su AI simulacija; `
                + "igram na poslednjoj",
        });
    }
    cachedGameLogic = chosen[chosen.length - 1];
    return cachedGameLogic;
}

/** The newest dead-listed logic whose match the engine still calls open.
 *
 *  Only ever on the user's say-so (wake). The dead list is the host's memory
 *  of ends, and one of those ends is the host's own "Predaja" button -- which
 *  the user can press on a match that is still running. 2026-09-15 10:28:46:
 *  Predaja five seconds into a Dustville Duel, GUI restarted, the fresh agent
 *  was handed the key back and the only GameLogic with a board was "a match
 *  that already ended" -- while the game was in that very match; only a game
 *  restart got it back. When the user asks for a move, the engine's own state
 *  outranks the host's earlier verdict: a logic the engine still calls open is
 *  revived, one it calls finished stays dead. */
function reviveNewestDeadLogic(): Il2Cpp.Object | null {
    if (gameLogicClass == null || deadLogicKeys.size === 0) return null;
    const instances = chooseInstances(gameLogicClass, "GameLogic (ozivljavanje)");
    const candidates = instances.filter(
        instance =>
            hasBoard(instance)
            && !isSimulation(instance)
            && isDeadLogic(instance)
            && !stateIsFinished(instance)
    );
    if (candidates.length === 0) return null;
    let chosen = candidates[candidates.length - 1];
    let newestIndex: number | null = null;
    for (const instance of candidates) {
        const index = readGameIndex(instance);
        if (index != null && (newestIndex == null || index > newestIndex)) {
            newestIndex = index;
            chosen = instance;
        }
    }
    const key = logicKey(chosen);
    if (key != null) deadLogicKeys.delete(key);
    try {
        if (endedLogicHandle != null && chosen.handle.toString() === endedLogicHandle) {
            endedLogicHandle = null;
        }
    } catch (_) {
    }
    // The quiet-timeout latch belongs to the verdict being overturned.
    quietSignature = null;
    cachedGameLogic = chosen;
    return chosen;
}

/** Record every GameLogic the engine builds, so resolving never has to search.
 *
 *  The handler does the least it possibly can -- store a pointer -- because it
 *  runs inside the game's own thread on every construction, simulations
 *  included. No engine method is called from here; see the standing rule that
 *  the agent may read memory and nothing else. */
function installCtorHook(): void {
    if (!useCtorHook || ctorHookState !== "off" || gameLogicClass == null) return;
    try {
        let attached = 0;
        for (const method of gameLogicClass.methods) {
            if (method.name !== ".ctor") continue;
            const address = method.virtualAddress;
            if (address == null || address.isNull()) continue;
            ctorHookListeners.push(Interceptor.attach(address, {
                onEnter(args: InvocationArguments): void {
                    constructedHandle = args[0];
                    constructedCount += 1;
                    constructedRing.push(args[0]);
                    if (constructedRing.length > CONSTRUCTED_RING_MAX) {
                        constructedRing.shift();
                    }
                },
            }));
            attached += 1;
        }
        ctorHookState = attached > 0 ? "on" : "failed";
        if (attached === 0) ctorHookError = "nijedan .ctor nema adresu";
    } catch (error) {
        // A failed hook is not a failed agent: the heap walk still works, and
        // saying so beats dying on an optimisation.
        ctorHookState = "failed";
        ctorHookError = String(error);
    }
}

/** Take the .ctor listeners off again (configure with withCtorHook=false).
 *
 *  Never in the middle of a match: unhooking there is the riskier move, so
 *  a request that arrives mid-match only stops trusting the hook and the
 *  detach itself waits for the match to end (setMatchActive). Nothing here
 *  runs inside a hook, and nothing runs per poll. */
function removeCtorHook(): void {
    constructedHandle = null;
    constructedSeen = null;
    constructedRing.length = 0;
    ringScannedAtCount = -1;
    if (ctorHookListeners.length === 0) {
        ctorHookDetachPending = false;
        return;
    }
    if (matchActive) {
        ctorHookDetachPending = true;
        return;
    }
    ctorHookDetachPending = false;
    while (ctorHookListeners.length > 0) {
        const listener = ctorHookListeners.pop();
        try {
            if (listener != null) listener.detach();
        } catch (error) {
            ctorHookError = `detach: ${String(error)}`;
        }
    }
    constructedRing.length = 0;
    constructedHandle = null;
    if (ctorHookState === "on") ctorHookState = "off";
}

/** Record the moment either player concedes, so the match closes right away.
 *
 *  Match3GameData.Conceded() is the engine's own concede notification -- it
 *  runs for a local surrender and for the opponent's alike. The handler stores
 *  one timestamp and returns; matchEnded() does the rest on the next poll. A
 *  failed hook only costs the fast exit: the quiet timeout still closes the
 *  match the slow way. */
function installConcedeHook(): void {
    if (concedeHookState !== "off" || gameDataClass == null) return;
    try {
        let attached = 0;
        for (const method of gameDataClass.methods) {
            if (method.name !== "Conceded") continue;
            const address = method.virtualAddress;
            if (address == null || address.isNull()) continue;
            Interceptor.attach(address, {
                onEnter(): void {
                    concededAt = Date.now();
                },
            });
            attached += 1;
        }
        concedeHookState = attached > 0 ? "on" : "failed";
        if (attached === 0) concedeHookError = "Conceded nema adresu";
    } catch (error) {
        concedeHookState = "failed";
        concedeHookError = String(error);
    }
}

/** Record which GameLogic the engine disposed, so an abandoned match closes.
 *
 *  GameLogic.Dispose() runs for the AI's lookahead copies too, so the handler
 *  stores the pointer and a timestamp and nothing else; whether it was OUR
 *  match is decided on the next poll against the cached logic. A failed hook
 *  only loses the fast exit -- the quiet timeout still closes the match. */
function installDisposeHook(): void {
    if (disposeHookState !== "off" || gameLogicClass == null) return;
    try {
        let attached = 0;
        for (const method of gameLogicClass.methods) {
            if (method.name !== "Dispose" || method.parameterCount !== 0) continue;
            const address = method.virtualAddress;
            if (address == null || address.isNull()) continue;
            Interceptor.attach(address, {
                onEnter(args: InvocationArguments): void {
                    disposedHandle = args[0];
                    disposedAt = Date.now();
                    disposedCount += 1;
                },
            });
            attached += 1;
        }
        disposeHookState = attached > 0 ? "on" : "failed";
        if (attached === 0) disposeHookError = "GameLogic.Dispose nema adresu";
    } catch (error) {
        disposeHookState = "failed";
        disposeHookError = String(error);
    }
}

/** Was the logic this agent is reading disposed by the engine? */
function readingLogicDisposed(): boolean {
    if (disposedHandle == null || cachedGameLogic == null) return false;
    return disposedHandle.equals(cachedGameLogic.handle);
}

function boardObject(logic: Il2Cpp.Object): Il2Cpp.Object {
    try {
        const value = logic.field<Il2Cpp.Object>("board").value;
        if (value == null || value.handle.isNull()) throw new Error("GameLogic.board is null");
        return value;
    } catch (_) {
        const pointer = logic.handle.add(EXPECTED_OFFSETS["GameLogic.board"]).readPointer();
        if (pointer.isNull()) throw new Error("GameLogic.board is null at fallback offset 0xB8");
        return new Il2Cpp.Object(pointer);
    }
}

function readSlot(slot: Il2Cpp.Object, x: number, y: number): RawSlot {
    return {
        x,
        y,
        row: y,
        col: x,
        color: asNumber(readSlotField(slot, "color")),
        color2: asNumber(readSlotField(slot, "color2")),
        value: asNumber(readSlotField(slot, "value")),
        originalValue: asNumber(readSlotField(slot, "originalValue")),
        holdValue: asNumber(readSlotField(slot, "holdValue")),
        relatedPlayerIndex: asNumber(readSlotField(slot, "relatedPlayerIndex")),
        status: asNumber(readSlotField(slot, "status")),
        score: asNumber(readSlotField(slot, "score")),
        scoreModifierOrigin: asNumber(readSlotField(slot, "scoreModifierOrigin")),
        scoreModifierBonus: asNumber(readSlotField(slot, "scoreModifierBonus")),
        energy: asNumber(readSlotField(slot, "energy")),
        hitPoints: asNumber(readSlotField(slot, "hitPoints")),
        origin: asNumber(readSlotField(slot, "origin")),
        damageable: readBoolean(slot, "damageable"),
        autoDestruct: readBoolean(slot, "autoDestruct"),
        canBeMatched: readBoolean(slot, "canBeMatched"),
        movable: readBoolean(slot, "movable"),
        createdFromCombo: readBoolean(slot, "createdFromCombo"),
        skipDestroyTillMoveEnds: readBoolean(slot, "skipDestroyTillMoveEnds"),
        activateOnHitpointReduced: readBoolean(slot, "activateOnHitpointReduced"),
        isLiveEventPiece: readBoolean(slot, "isLiveEventPiece"),
    };
}

function signatureFor(slots: RawSlot[]): string {
    let hash = 0x811c9dc5;
    const fields = [
        "color", "color2", "value", "originalValue", "holdValue", "status",
        "score", "scoreModifierBonus", "energy", "hitPoints", "origin",
    ];
    for (const slot of slots) {
        for (const name of fields) {
            let value = Number((slot as any)[name]) >>> 0;
            for (let shift = 0; shift < 32; shift += 8) {
                hash ^= (value >>> shift) & 0xff;
                hash = Math.imul(hash, 0x01000193) >>> 0;
            }
        }
    }
    return hash.toString(16).padStart(8, "0");
}

function asText(value: any): string | null {
    if (value == null) return null;
    if (typeof value === "string") return value;
    if (typeof value.content === "string") return value.content;
    if (value.handle != null && value.handle.isNull()) return null;
    const text = String(value);
    return text === "null" || text === "undefined" ? null : text;
}

/** A managed reference that is safe to touch.
 *
 *  The bridge happily wraps a NULL pointer in an Il2Cpp.Object, and reading a
 *  field or invoking a method on such a wrapper dereferences NULL and takes the
 *  whole game process down with it. Every state read goes through this gate. */
function usable(object: any): any {
    if (object == null) return null;
    if (typeof object !== "object") return object;  // ints/bools pass through
    const handle = object.handle;
    if (handle == null) return object;
    return handle.isNull() ? null : object;
}

/** Invoke a parameterless getter, yielding null instead of throwing.
 *  Reserved for values the engine computes; anything backed by a plain field is
 *  read as a field instead, which needs no method call at all. */
function callGetter(object: any, name: string): any {
    const target = usable(object);
    if (target == null) return null;
    try {
        const method = target.tryMethod(name, 0);
        if (method == null) return null;
        return usable(method.invoke());
    } catch (_) {
        return null;
    }
}

function getterNumber(object: any, name: string): number | null {
    const value = callGetter(object, name);
    if (value == null) return null;
    try {
        return asNumber(value);
    } catch (_) {
        return null;
    }
}

function getterBoolean(object: any, name: string): boolean | null {
    const value = callGetter(object, name);
    if (value == null) return null;
    if (typeof value === "boolean") return value;
    try {
        return asNumber(value) !== 0;
    } catch (_) {
        return null;
    }
}

function fieldValue(object: any, name: string): any {
    const target = usable(object);
    if (target == null) return null;
    try {
        const field = target.tryField(name);
        if (field == null) return null;
        const value = field.value;
        return typeof value === "object" ? usable(value) : value;
    } catch (_) {
        return null;
    }
}

function fieldNumber(object: any, name: string): number | null {
    const value = fieldValue(object, name);
    if (value == null) return null;
    try {
        return asNumber(value);
    } catch (_) {
        return null;
    }
}

function fieldBoolean(object: any, name: string): boolean | null {
    const value = fieldValue(object, name);
    if (value == null) return null;
    if (typeof value === "boolean") return value;
    try {
        return asNumber(value) !== 0;
    } catch (_) {
        return null;
    }
}

/** Read a List<int>/List<SlotColor> into plain numbers; enums arrive as value types. */
function listItems(list: any, limit: number): any[] {
    const target = usable(list);
    if (target == null) return [];
    try {
        const countMethod = target.tryMethod("get_Count", 0);
        const getItem = target.tryMethod("get_Item", 1);
        if (countMethod == null || getItem == null) return [];
        const count = asNumber(countMethod.invoke());
        if (!Number.isFinite(count) || count <= 0) return [];
        const values: any[] = [];
        for (let index = 0; index < Math.min(count, limit); index++) {
            values.push(getItem.invoke(index));
        }
        return values;
    } catch (_) {
        return [];
    }
}

function numberList(list: any, limit: number = 32): number[] | null {
    if (usable(list) == null) return null;
    try {
        return listItems(list, limit).map(asNumber);
    } catch (_) {
        return null;
    }
}

function readBoardAbilities(control: any): BoardAbilityState[] | null {
    const list = fieldValue(control, "BoardAbilities");
    if (usable(list) == null) return null;
    return listItems(list, 8).map((ability) => {
        const config = fieldValue(ability, "<Config>k__BackingField");
        return {
            type: fieldNumber(ability, "<Type>k__BackingField"),
            name: asText(fieldValue(config, "name")),
            index: fieldNumber(config, "index"),
        };
    });
}

function readAbilityParams(config: any): Record<string, string> | null {
    const list = fieldValue(config, "additionalParams");
    if (usable(list) == null) return null;
    const params: Record<string, string> = {};
    for (const param of listItems(list, 24)) {
        const key = asText(fieldValue(param, "<key>k__BackingField"));
        if (key == null) continue;
        params[key] = String(asText(fieldValue(param, "<value>k__BackingField")));
    }
    return params;
}

// SpecialAbilityType.MixyMeow, the one ability whose live counters are worth
// a getter call: the drawn code stays in `activeColors` after its last use,
// so only `UsesLeft` says whether it can still be cashed.
const ABILITY_TYPE_MIXY_MEOW = 59;
// SpecialAbilityType.UFOBeamSE: its armed eyes are `colorsToPick -
// ColorsPicked` (Use sets the first per activation-this-turn and zeroes the
// second; AfterDestroyWithPassiveAbility raises ColorsPicked and
// PassiveActivates per eye fired), all kept as extraData strings behind
// getters, and `get_RemainingHudEyes` is the engine's own HUD count.
const ABILITY_TYPE_UFO_SE = 49;

/** The engine's own counters for the equipped ability, via its getters.
 *
 *  `MixyMeow.get_UsesLeft` (rva 0x585dfe8) walks player -> logic -> board ->
 *  extraData and `Convert.ToInt32`s the string under `get_UsesLeftKey`
 *  (String.Format, i.e. an allocation), returning 0 when the key is absent --
 *  which is also what an exhausted code reads, and either way means "no code
 *  move". `Use` writes it on every activation and `FoundTargetColor` takes one
 *  off per credited match, so it is the number the host otherwise has to infer
 *  from a two-second transient. Manual dumps only, like the jelly deep read:
 *  the GUI asks for one before every move, and the plain poll never allocates
 *  inside the game. */
function readAbilityEngineCounters(
    ability: any,
    abilityType: number | null,
): Record<string, number | null> | null {
    const target = usable(ability);
    if (target == null) return null;
    try {
        if (abilityType === ABILITY_TYPE_MIXY_MEOW) {
            return {
                uses_left: getterNumber(target, "get_UsesLeft"),
                passive_uses_since_activate: getterNumber(
                    target,
                    "get_NumOfPassiveUsesSinceLastActivate",
                ),
                activates: getterNumber(target, "get_Activates"),
            };
        }
        if (abilityType === ABILITY_TYPE_UFO_SE) {
            return {
                remaining_hud_eyes: getterNumber(target, "get_RemainingHudEyes"),
                colors_to_pick: getterNumber(target, "get_colorsToPick"),
                colors_picked: getterNumber(target, "get_ColorsPicked"),
                passive_activates: getterNumber(target, "get_PassiveActivates"),
            };
        }
        return null;
    } catch (_) {
        return null;
    }
}

function readPlayer(control: any, deep: boolean = false): PlayerState {
    // Everything here is a plain field on PlayerControl or its PlayerModel;
    // only EnergyToAbility (the booster denominator) is computed by the engine
    // and therefore worth a method call. The player name is deliberately never
    // read: the snapshot must stay free of account identifiers.
    const model = fieldValue(control, "model");
    const ability = fieldValue(control, "ability");
    const abilityConfig = fieldValue(ability, "<Config>k__BackingField");
    const abilityType = fieldNumber(model, "specialAbilityType");
    return {
        index: fieldNumber(model, "index"),
        score: fieldNumber(model, "score"),
        turn_score: fieldNumber(model, "turnScore"),
        spawn_bonus: fieldNumber(model, "spawnBonus"),
        max_round_score: fieldNumber(model, "maxRoundScore"),
        rounds_won: fieldNumber(model, "roundsWon"),
        energy: fieldNumber(model, "energy"),
        energy_to_ability: getterNumber(control, "get_EnergyToAbility"),
        energy_full: getterBoolean(control, "get_IsSpecialAbilityEnergyFull"),
        energy_colors: numberList(fieldValue(control, "energyColors")),
        booster_activations_left: null,
        score_multiplier: fieldNumber(model, "scoreMultiplier"),
        health: fieldNumber(model, "health"),
        slot_type: fieldNumber(model, "slotType"),
        bonus_tiles_collected: fieldNumber(model, "bonusTilesCollected"),
        // Which SE booster this player brought, per Match3Engine.SpecialAbilityType.
        special_ability_type: abilityType,
        // SpecialAbility.Config.name is the booster's in-game name, which is
        // what the bot's own booster list is keyed on.
        special_ability_name: asText(fieldValue(abilityConfig, "name")),
        // Description and tuning params describe how this booster behaves. The
        // shipped Constants asset only covers the classic set, so the modern
        // boosters can be learned no other way than from the live model.
        special_ability_description: asText(fieldValue(abilityConfig, "description")),
        special_ability_params: readAbilityParams(abilityConfig),
        // The live SpecialAbility instance, not its config: `activeSpecialAbility
        // Type` on the model is only 49 for the single frame the UFO activation
        // animation runs in, so the host cannot see from it how many eyes are
        // still armed. Whatever counter the ability keeps for that is one of
        // these fields -- a read-only scalar sweep, same as the mutation one.
        special_ability_fields: readAllInstanceFields(ability),
        special_ability_engine: deep ? readAbilityEngineCounters(ability, abilityType) : null,
        ufo_colors_exploded_this_move: deep && abilityType === ABILITY_TYPE_UFO_SE
            ? intListValues(fieldValue(control, "colorsExplodedThisMove"), 16)
            : null,
        active_special_ability_type: fieldNumber(model, "activeSpecialAbilityType"),
        // Nine board models return from their hook without applying the mode's
        // own rule when the player spent an ability this move (decoded from
        // libil2cpp.so -- see docs/game_mode_logic_from_code.md). The three
        // fields the engine reads for that decision are plain booleans/enums on
        // PlayerModel at 0xc0 / 0xc2 / 0xc4, so no method call is needed.
        is_ability_used_this_move: fieldBoolean(model, "isAbilityUsedThisMove"),
        is_board_ability_used_this_move: fieldBoolean(
            model,
            "isBoardAbilityUsedThisMove",
        ),
        board_ability_used_this_move: fieldNumber(model, "boardAbilityUsedThisMove"),
        active_board_ability: fieldNumber(model, "activeBoardAbilityType"),
        board_abilities: readBoardAbilities(control),
        is_my_turn: fieldBoolean(control, "<IsMyTurn>k__BackingField"),
        has_played_this_turn: fieldBoolean(model, "HasPlayedThisTurn"),
        // PlayerClientControl.Type (Local/Remote/AI) is the only thing that says
        // which side is us; the player on turn is not necessarily us.
        player_type: fieldNumber(control, "<Type>k__BackingField"),
        // Mutation Lab keeps the picked mutations on the PlayerModel, and the
        // catalogue extracted from the client (docs/game_mode_rules.md) names
        // ~30 mutation types -- far more than it is worth hand-listing here
        // before a single live match has been seen. A sweep answers "what is
        // actually on this player" instead, but PlayerModel is also where the
        // account identifiers live, so it is filtered down to the mutation
        // fields *inside the process*: what is not read cannot leak.
        mutation_fields: readMutationFields(model),
    };
}

// MatchRulesModel does not change while a match is open, so the full field
// sweep runs once per rules object rather than on every poll.
let cachedRulesKey: string | null = null;
let cachedDirectionsKey: string | null = null;
let cachedDirections: Record<string, any> | null = null;
let cachedRulesFields: Record<string, any> | null = null;

/** Read a field value into JSON *without running any game code*.
 *
 *  This is the hard rule for the sweep: it walks fields nobody vetted, so it
 *  may only do plain memory loads. Calling a method on an arbitrary managed
 *  object -- `get_Count` on something that is not a list, a property getter
 *  with a side effect -- runs engine code on the game's own thread, and the
 *  first version of this function did exactly that and crashed Match Masters
 *  on attach (2026-08-17). Primitives, enums (their `value__` field) and
 *  strings (a buffer read) are all field reads; everything else is reported as
 *  a "<TypeName>" marker, which still says the field exists and what it is.
 */
function ruleFieldValue(target: any, name: string): any {
    const value = fieldValue(target, name);
    if (value == null) return null;
    const kind = typeof value;
    if (kind === "boolean" || kind === "number" || kind === "string") return value;
    let className: string | null = null;
    try {
        className = value.class != null ? String(value.class.name) : null;
    } catch (_) {
        className = null;
    }
    if (className === "String") return asText(value);
    // An enum arrives as a value type whose only content is `value__`.
    try {
        if (typeof value.tryField === "function") {
            const underlying = value.tryField("value__");
            if (underlying != null) {
                const number = Number(underlying.value);
                if (Number.isFinite(number)) return number;
            }
        }
    } catch (_) {
        // not an enum
    }
    return className == null ? null : `<${className}>`;
}

const SCALAR_FIELD_TYPES = new Set([
    "System.Boolean", "System.Byte", "System.SByte", "System.Int16",
    "System.UInt16", "System.Int32", "System.UInt32", "System.Int64",
    "System.UInt64", "System.Single", "System.Double", "System.String",
]);

/** Whether the sweep may read this field's value at all.
 *
 *  Type first, value second: a scalar or an enum is a plain memory load, while
 *  a reference field points at another managed object whose contents this
 *  sweep has no business walking. Those are reported by type name instead. */
function isReadableRuleField(field: any): boolean {
    try {
        if (field.isStatic || field.isThreadStatic || field.isLiteral) return false;
        const type = field.type;
        if (type == null) return false;
        if (SCALAR_FIELD_TYPES.has(String(type.name))) return true;
        return type.class != null && type.class.isEnum === true;
    } catch (_) {
        return false;
    }
}

/** Every instance field on one engine object, keyed by its engine name.
 *
 *  Read-only and method-free by construction (see ruleFieldValue). One field
 *  that misbehaves costs that field, not the sweep: each read is guarded, so
 *  the answer stays as complete as the process allows. */
function readAllInstanceFields(instance: any): Record<string, any> | null {
    const target = usable(instance);
    if (target == null) return null;
    const values: Record<string, any> = {};
    let fields: any[] = [];
    try {
        fields = target.class.fields;
    } catch (_) {
        fields = [];
    }
    for (const field of fields) {
        let name: string | null = null;
        try {
            name = field.name;
        } catch (_) {
            continue;
        }
        if (name == null || Object.prototype.hasOwnProperty.call(values, name)) continue;
        try {
            if (isReadableRuleField(field)) {
                values[name] = ruleFieldValue(target, name);
            } else {
                let typeName: string | null = null;
                try {
                    typeName = field.type != null ? String(field.type.name) : null;
                } catch (_) {
                    typeName = null;
                }
                const contents = intCollectionValue(target, name, typeName);
                if (contents !== undefined) {
                    values[name] = contents;
                    if (typeName != null && INT_DICTIONARY_TYPES.has(typeName)) {
                        values[`${name}__diag`] = intDictionaryDiag(fieldValue(target, name));
                    }
                } else if (typeName != null) {
                    values[name] = `<${typeName}>`;
                }
            }
        } catch (_) {
            // Leave this one out rather than lose the rest.
        }
    }
    return values;
}

/** MatchRulesModel's fields. Cached: a ruleset is fixed for the whole match. */
function readAllRuleFields(rules: any): Record<string, any> | null {
    const target = usable(rules);
    if (target == null) return null;
    let key: string | null = null;
    try {
        key = String(target.handle);
    } catch (_) {
        key = null;
    }
    if (key != null && key === cachedRulesKey) return cachedRulesFields;
    const values = readAllInstanceFields(target);
    cachedRulesKey = key;
    cachedRulesFields = values;
    return values;
}

/** Just the mutation-related fields of one engine object.
 *
 *  PlayerModel carries the account's own name and ids next to its game numbers,
 *  and the snapshot must never carry those (see readPlayer). Narrowing the
 *  sweep by name here rather than in the host is what keeps that true: an
 *  identifier that is never read cannot be forwarded by mistake. */
function readMutationFields(instance: any): Record<string, any> | null {
    const all = readAllInstanceFields(instance);
    if (all == null) return null;
    const values: Record<string, any> = {};
    for (const name of Object.keys(all)) {
        if (name.toLowerCase().includes("mutation")) values[name] = all[name];
    }
    return values;
}

/** Every `*Directions` table on the board, as [x, y] offset pairs.
 *
 *  These are the blast shapes: `bombDirections`, `bigBombDirections`,
 *  `heartDirections`, `starDirections`, `xDirections`, `squareDirections` and
 *  the rest. The decompiled sources carry the method signatures but no bodies,
 *  which is why several modes in docs/game_mode_rules.md are written up as
 *  "the geometry is unknown" -- the geometry is right here, as plain data.
 *
 *  Arrays are walked through Il2Cpp.Array's own indexer, i.e. a memory read
 *  per element; nothing on this path invokes a game method (see ruleFieldValue).
 *  Read once per board object and cached: these tables are compiled constants. */
function readDirectionTables(board: any): Record<string, any> | null {
    const target = usable(board);
    if (target == null) return null;
    let key: string | null = null;
    try {
        key = String(target.handle);
    } catch (_) {
        key = null;
    }
    if (key != null && key === cachedDirectionsKey) return cachedDirections;

    const tables: Record<string, any> = {};
    let fields: any[] = [];
    try {
        fields = target.class.fields;
    } catch (_) {
        fields = [];
    }
    for (const field of fields) {
        let name: string | null = null;
        try {
            name = field.name;
        } catch (_) {
            continue;
        }
        if (name == null || !/directions$/i.test(name)) continue;
        try {
            // The 2026-08-19 capture read all nineteen of these as null off the
            // instance: they are compiled constants, i.e. static fields, which
            // hang off the class rather than the object.
            let array = fieldValue(target, name);
            if (array == null) array = staticFieldValue(target, name);
            if (array == null) {
                tables[name] = "<unreadable>";
                continue;
            }
            const length = Number((array as any).length);
            if (!Number.isFinite(length) || length <= 0 || length > 256) {
                tables[name] = `<length:${(array as any).length}>`;
                continue;
            }
            const points: number[][] = [];
            for (let index = 0; index < length; index++) {
                const point = (array as any).get(index);
                const numbers = valueTypeNumbers(point);
                if (numbers != null) points.push(numbers);
            }
            // A shape that read as zero points would silently look like a shape
            // the board does not have, so say what its elements are made of
            // instead -- that is what turns a failed read into a fixable one.
            tables[name] = points.length > 0
                ? points
                : { length, element_fields: valueTypeFieldNames(point0(array)) };
        } catch (error) {
            tables[name] = `<error:${String(error)}>`;
        }
    }
    cachedDirectionsKey = key;
    cachedDirections = tables;
    return tables;
}

/** A List<T>'s elements read straight off its backing array.
 *
 *  Deliberately not listItems(): that one calls get_Count/get_Item, and calling
 *  a game method from a sweep is what crashed Match Masters on attach once
 *  already. `_items` and `_size` are plain fields, so this is a memory read. */
function listItemsByField(list: any, limit: number = 32): any[] {
    const target = usable(list);
    if (target == null) return [];
    try {
        const items = fieldValue(target, "_items");
        const size = Number(fieldValue(target, "_size"));
        if (items == null || !Number.isFinite(size) || size <= 0) return [];
        const values: any[] = [];
        for (let index = 0; index < Math.min(size, limit); index++) {
            values.push((items as any).get(index));
        }
        return values;
    } catch (_) {
        return [];
    }
}

const INT_LIST_TYPE = "System.Collections.Generic.List<System.Int32>";
// Enum-element lists whose values are plain ints under value__. MixyMeow keeps
// its live suitcase code in `activeColors : List<Match3Engine.SlotColor>`
// (il2cpp_symbols 2026-08-23), and without this the whole Mixy state dumped as
// a "<List`1>" marker -- which is why the host still had to read the code
// colours off the screen.
const ENUM_INT_LIST_TYPES = new Set([
    "System.Collections.Generic.List<Match3Engine.SlotColor>",
]);
const INT_DICTIONARY_TYPES = new Set([
    "System.Collections.Generic.Dictionary<System.Int32,System.Int32>",
    "System.Collections.Generic.Dictionary<System.Int32, System.Int32>",
    "System.Collections.Generic.Dictionary<Match3Engine.SlotColor,System.Int32>",
    "System.Collections.Generic.Dictionary<Match3Engine.SlotColor, System.Int32>",
]);

/** A List<int> or Dictionary<int,int> field read as actual numbers.
 *
 *  The sweep normally reports a reference field as a "<TypeName>" marker, and
 *  for these two shapes that marker is the whole answer thrown away: The Floor
 *  Is Lava keeps its per-column match counter in
 *  `FloorIsLavaBoard.ColumnsEruptionDictionary`, which is where the mode's only
 *  state lives (2026-08-19 capture). Both are read through their backing fields
 *  only -- `_items`/`_size` for the list, `entries`/`count` for the dictionary
 *  -- so this stays inside the no-method rule that keeps the game alive on
 *  attach. `undefined` means "not one of these", which is not the same as an
 *  empty collection. */
function intCollectionValue(
    target: any,
    name: string,
    typeName: string | null,
): number[] | Record<string, number> | null | undefined {
    if (typeName == null) return undefined;
    if (typeName === INT_LIST_TYPE || ENUM_INT_LIST_TYPES.has(typeName)) {
        return intListValues(fieldValue(target, name));
    }
    if (INT_DICTIONARY_TYPES.has(typeName)) {
        return intDictionaryValues(fieldValue(target, name));
    }
    return undefined;
}

/** One list element as a number: a plain int directly, an enum via value__.
 *
 *  A List<SlotColor>'s backing array hands its elements back as value types,
 *  so Number(item) alone is NaN for them -- the same unwrap ruleFieldValue
 *  already does for scalar enum fields applies per element here. */
function listItemNumber(item: any): number | null {
    const direct = Number(item);
    if (Number.isFinite(direct)) return direct;
    try {
        if (item != null && typeof item.tryField === "function") {
            const underlying = item.tryField("value__");
            if (underlying != null) {
                const number = Number(underlying.value);
                if (Number.isFinite(number)) return number;
            }
        }
    } catch (_) {
        // not an enum element
    }
    return null;
}

function intListValues(list: any, limit: number = 64): number[] | null {
    const target = usable(list);
    if (target == null) return null;
    const values: number[] = [];
    for (const item of listItemsByField(target, limit)) {
        const number = listItemNumber(item);
        if (number == null) return null;
        values.push(number);
    }
    return values;
}

/** Dictionary<int,int> as a plain object, straight out of its entry array.
 *
 *  `entries` is an array of `Entry { hashCode, next, key, value }` structs, and
 *  `count` is how many of its slots have ever been used -- the same bound the
 *  engine's own enumerator walks. The struct is read positionally by
 *  valueTypeNumbers, and the corlib field names differ between Unity versions
 *  ("entries"/"_entries"), so both spellings are tried. Freed slots are left in
 *  by design: which keys are meaningful is the host's judgement, not the
 *  agent's, and the host sanitises them against the board size. */
function intDictionaryValues(
    dictionary: any,
    limit: number = 64,
): Record<string, number> | null {
    const target = usable(dictionary);
    if (target == null) return null;
    let entries: any = null;
    for (const name of ["entries", "_entries"]) {
        const value = fieldValue(target, name);
        if (value != null) {
            entries = value;
            break;
        }
    }
    let count = NaN;
    for (const name of ["count", "_count"]) {
        // A field this corlib does not have reads as null, and Number(null) is
        // 0 -- finite. Without this guard "count" (absent here; the field is
        // "_count") answered 0 and every dictionary looked empty.
        const field = fieldValue(target, name);
        if (field == null) continue;
        const value = Number(field);
        if (Number.isFinite(value)) {
            count = value;
            break;
        }
    }
    if (!Number.isInteger(count) || count < 0) return null;
    if (count === 0) return {};
    if (entries == null) return null;
    // The bridge path further down (`entries.get(i)` -> ValueType -> `.field`)
    // returns nothing for generic entry structs on the played board -- the same
    // failure rawStringDictionaryEntries documents -- which is why
    // FloorIsLavaBoard.ColumnsEruptionDictionary read `{}` in every poll while
    // the columns were visibly heated. Entry<int,int> has one fixed layout, so
    // it is read raw first and the bridge is only the fallback.
    const raw = rawIntDictionaryEntries(entries, count, limit);
    if (raw != null) return raw;
    const values: Record<string, number> = {};
    let decoded = 0;
    for (let index = 0; index < Math.min(count, limit); index++) {
        let numbers: number[] | null = null;
        try {
            numbers = valueTypeNumbers((entries as any).get(index));
        } catch (_) {
            numbers = null;
        }
        if (numbers == null) continue;
        decoded++;
        if (numbers.length >= 4) {
            const [hashCode, , key, value] = numbers;
            // A never-used slot carries a negative hash in the Mono layout.
            if (hashCode < 0) continue;
            values[String(key)] = value;
        } else if (numbers.length === 2) {
            values[String(numbers[0])] = numbers[1];
        }
    }
    // Used slots that would not decode are "unknown", never "empty": the host
    // treats null as no reading and an object as the engine's word.
    if (decoded === 0) return null;
    return values;
}

/** The dictionary's own bookkeeping plus its first raw slots, unfiltered.
 *
 *  `version` moves on every write, so a counter that stays `{}` with a moving
 *  version is being filled and cleared between polls, while a frozen version
 *  means the engine never touches this dictionary at all. */
function intDictionaryDiag(dictionary: any): Record<string, any> | null {
    const target = usable(dictionary);
    if (target == null) return null;
    const diag: Record<string, any> = {};
    try {
        diag.handle = String(target.handle);
        diag.fields = (target.class.fields as any[])
            .filter((field: any) => !field.isStatic)
            .map((field: any) => String(field.name));
        for (const name of ["count", "_count", "freeCount", "_freeCount", "freeList", "_freeList", "version", "_version"]) {
            const field = fieldValue(target, name);
            if (field == null) continue;
            const value = Number(field);
            if (Number.isFinite(value)) diag[name.replace(/^_/, "")] = value;
        }
        let entries: any = null;
        for (const name of ["entries", "_entries"]) {
            const value = fieldValue(target, name);
            if (value != null) {
                entries = value;
                break;
            }
        }
        if (entries == null) {
            diag.entries = null;
            return diag;
        }
        const length = Number(entries.length);
        diag.entries_length = length;
        let base: NativePointer | null = null;
        try {
            base = entries.elements.handle;
        } catch (_) {
            base = null;
        }
        if (base == null) base = entries.handle.add(Il2Cpp.Array.headerSize);
        const slots: number[][] = [];
        for (let index = 0; index < Math.min(length, 8); index++) {
            const item = base.add(index * 16);
            slots.push([item.readS32(), item.add(4).readS32(), item.add(8).readS32(), item.add(12).readS32()]);
        }
        diag.raw_slots = slots;
    } catch (error) {
        diag.error = String(error);
    }
    return diag;
}

/** Dictionary<int,int> entries straight out of the entry array's memory.
 *
 *  `Entry { int hashCode; int next; int key; int value; }` is 16 bytes in every
 *  corlib Unity ships. A freed slot has hashCode -1 in the Mono layout and
 *  next < -1 in the CoreCLR one; both are skipped. Returns null when the array
 *  cannot be addressed, so the caller can still try the bridge. */
function rawIntDictionaryEntries(
    entries: any,
    count: number,
    limit: number,
): Record<string, number> | null {
    try {
        let length = NaN;
        try {
            length = Number(entries.length);
        } catch (_) {
            length = NaN;
        }
        if (!Number.isFinite(length) || length < count) return null;
        let base: NativePointer | null = null;
        try {
            base = entries.elements.handle;
        } catch (_) {
            base = null;
        }
        if (base == null) base = entries.handle.add(Il2Cpp.Array.headerSize);
        const values: Record<string, number> = {};
        for (let index = 0; index < Math.min(count, limit); index++) {
            const item = base.add(index * 16);
            const hashCode = item.readS32();
            const next = item.add(4).readS32();
            if (hashCode < 0 || next < -1) continue;
            values[String(item.add(8).readS32())] = item.add(12).readS32();
        }
        return values;
    } catch (_) {
        return null;
    }
}

/** `BoardModel.extraData` as plain strings -- where JellySE keeps its state.
 *
 *  JellySE has no field for the infected area: `get_AllInfected` walks
 *  `player -> logic -> board -> extraData` and deserialises the points out of a
 *  string kept under a per-player key (the same dictionary holds the target
 *  colour, the phase and the uses left). That is the whole jelly overlay, which
 *  the screen path can only guess at from washed-out saturation.
 *
 *  Read through `entries`/`count` like the int dictionary above -- field reads
 *  only, no `get_Count`. Values are boxed, so anything that is not a string
 *  (the dictionary is `<string, object>`) is reported by its type name rather
 *  than skipped: an unknown key is still evidence of what the mode stores. */
/** A boxed dictionary value as text: strings verbatim, boxed numbers as their
 *  decimal (the jelly and Mixy keys hold `SerializePoints` strings and ints
 *  the engine reads back with `Convert.ToInt32`), anything else by type. */
function boxedValueText(pointer: NativePointer): string {
    if (pointer.isNull()) return "";
    const object = new Il2Cpp.Object(pointer);
    let className = "";
    try {
        className = String(object.class.name);
    } catch (_) {
        return "";
    }
    const payload = pointer.add(Il2Cpp.Object.headerSize);
    switch (className) {
        case "String":
            return new Il2Cpp.String(pointer).content ?? "";
        case "Int32":
        case "UInt32":
            return String(payload.readS32());
        case "Int64":
            return String(payload.readS64());
        case "Int16":
        case "UInt16":
            return String(payload.readS16());
        case "Byte":
        case "SByte":
        case "Boolean":
            return String(payload.readU8());
        case "Single":
            return String(payload.readFloat());
        case "Double":
            return String(payload.readDouble());
        default:
            return `<${className}>`;
    }
}

/** The dictionary's entries read straight out of memory.
 *
 *  The bridge path below (`entries.get(i)` -> `Il2Cpp.ValueType` -> `.field`)
 *  has returned nothing on the played board in every recording while the
 *  engine's own getters read the same dictionary fine, so this second reader
 *  uses only the class metadata (entry element size and field offsets) and
 *  raw pointer reads. Value-type field offsets in the metadata include the
 *  object header, hence the subtraction. */
function rawStringDictionaryEntries(
    entries: any,
    count: number,
    limit: number,
    diag: Record<string, any>,
): Record<string, string> {
    const values: Record<string, string> = {};
    try {
        let elementClass: any = null;
        try {
            elementClass = entries.elementType?.class ?? null;
        } catch (_) {
            elementClass = null;
        }
        if (elementClass == null) {
            try {
                elementClass = entries.class?.type?.class?.elementClass ?? null;
            } catch (_) {
                elementClass = null;
            }
        }
        if (elementClass == null) {
            diag.raw_error = "no element class";
            return values;
        }
        const fields = (elementClass.fields as any[]).filter(
            (field: any) => !field.isStatic && !field.isLiteral,
        );
        let size = NaN;
        try {
            size = Number(elementClass.arrayElementSize);
        } catch (_) {
            size = NaN;
        }
        if (!Number.isFinite(size) || size <= 0) {
            // Fall back to the extent of the fields, 8-byte aligned.
            const extents = fields.map((field: any) => Number(field.offset) - Il2Cpp.Object.headerSize + 8);
            size = Math.max(...extents, 8);
            size = Math.ceil(size / 8) * 8;
        }
        let base: NativePointer | null = null;
        try {
            base = entries.elements.handle;
        } catch (_) {
            base = null;
        }
        if (base == null) base = entries.handle.add(Il2Cpp.Array.headerSize);
        diag.raw = {
            size,
            fields: fields.map((field: any) => `${field.name}@${field.offset}`),
        };
        const keyField =
            fields.find((field: any) => field.name === "key") ?? fields[2];
        const valueField =
            fields.find((field: any) => field.name === "value") ?? fields[3];
        if (keyField == null || valueField == null) {
            diag.raw_error = "entry layout not recognised";
            return values;
        }
        const keyOffset = Number(keyField.offset) - Il2Cpp.Object.headerSize;
        const valueOffset = Number(valueField.offset) - Il2Cpp.Object.headerSize;
        let read = 0;
        for (let index = 0; index < Math.min(count, limit); index++) {
            try {
                const item = base.add(index * size);
                const keyPointer = item.add(keyOffset).readPointer();
                // A freed or never-used slot has no key.
                if (keyPointer.isNull()) continue;
                const key = new Il2Cpp.String(keyPointer).content;
                if (key == null || key === "") continue;
                values[key] = boxedValueText(item.add(valueOffset).readPointer());
                read++;
            } catch (error) {
                if (diag.raw_entry_error == null) diag.raw_entry_error = String(error);
            }
        }
        diag.raw_read = read;
    } catch (error) {
        diag.raw_error = String(error);
    }
    return values;
}

function readStringDictionary(
    dictionary: any,
    limit: number = 64,
    diag: Record<string, any> | null = null,
): Record<string, string> | null {
    const target = usable(dictionary);
    if (target == null) {
        if (diag != null) diag.dictionary = "null";
        return null;
    }
    const notes: Record<string, any> = diag ?? {};
    try {
        notes.dictionary_fields = (target.class.fields as any[])
            .filter((field: any) => !field.isStatic)
            .map((field: any) => field.name);
    } catch (_) {
        // metadata only
    }
    let entries: any = null;
    for (const name of ["entries", "_entries"]) {
        const value = fieldValue(target, name);
        if (value != null) {
            entries = value;
            notes.entries_field = name;
            break;
        }
    }
    let count = NaN;
    for (const name of ["count", "_count"]) {
        // Same guard as intDictionaryValues: an absent field is null, and
        // Number(null) === 0 would stop the search at the wrong spelling.
        const field = fieldValue(target, name);
        if (field == null) continue;
        const value = Number(field);
        if (Number.isFinite(value)) {
            count = value;
            notes.count_field = name;
            break;
        }
    }
    notes.count = Number.isFinite(count) ? count : null;
    if (entries == null || !Number.isFinite(count)) return null;
    try {
        notes.entries_length = Number(entries.length);
    } catch (_) {
        notes.entries_length = null;
    }
    const values: Record<string, string> = {};
    let bridgeRead = 0;
    for (let index = 0; index < Math.min(count, limit); index++) {
        try {
            const entry = (entries as any).get(index);
            if (entry == null) continue;
            // Positionally, like the int dictionary above: the Entry struct is
            // { hashCode, next, key, value } but the *names* differ between
            // corlib versions, and reading them by name threw once per entry --
            // which the catch turned into an empty dictionary rather than an
            // error, so a live jelly reported no state at all.
            const fields = valueTypeFields(entry).filter(
                (field: any) => !field.isStatic && !field.isLiteral,
            );
            if (index === 0) notes.entry_fields = fields.map((field: any) => field.name);
            if (fields.length < 4) continue;
            const key = asText(usable(entry.field(fields[2].name).value));
            if (key == null || key === "") continue;
            const raw = usable(entry.field(fields[3].name).value);
            let text = asText(raw);
            if (text == null && raw != null) {
                try {
                    text = boxedValueText(raw.handle);
                } catch (_) {
                    text = null;
                }
            }
            values[key] = text == null ? "" : text;
            bridgeRead++;
        } catch (error) {
            if (notes.bridge_entry_error == null) notes.bridge_entry_error = String(error);
            continue;
        }
    }
    notes.bridge_read = bridgeRead;
    // The bridge read came back with nothing the dictionary says it holds:
    // read the entries raw before concluding the dictionary is empty.
    if (bridgeRead === 0 && count > 0) {
        const raw = rawStringDictionaryEntries(entries, count, limit, notes);
        for (const key of Object.keys(raw)) values[key] = raw[key];
        notes.source = Object.keys(raw).length > 0 ? "raw" : "empty";
    } else {
        notes.source = "bridge";
    }
    return values;
}

/** Does this `extraData` dump carry the live jelly's state?
 *
 *  The engine-named key is the proof when we have it; the hint regex covers a
 *  jelly whose keys have not been resolved yet. */
function hasJellyExtraData(values: Record<string, string> | null): boolean {
    if (values == null) return false;
    const named =
        cachedJellyKeys != null ? cachedJellyKeys["all_infected"] : null;
    for (const key of Object.keys(values)) {
        if (named != null && key === named) return true;
        if (JELLY_EXTRA_DATA_HINT.test(key)) return true;
    }
    return false;
}

/** The BoardModel instance whose `extraData` the jelly actually writes to.
 *
 *  Only hunted while a jelly instance is resolved -- the sweep is a heap walk
 *  and most matches have no jelly. The played board is skipped (its dictionary
 *  is the one that came back empty); of the rest, anything carrying a jelly
 *  key qualifies. A lookahead board copied from the real one would carry the
 *  same zone, so adopting it by mistake still reads the right cells. */
function extraDataFallbackBoard(board: Il2Cpp.Object): Il2Cpp.Object | null {
    if (cachedExtraDataBoard != null) {
        try {
            if (!cachedExtraDataBoard.handle.isNull()) return cachedExtraDataBoard;
        } catch (_) {
            // fall through to a fresh hunt
        }
        cachedExtraDataBoard = null;
    }
    if (cachedJelly == null) return null;
    // Once per match. This used to repeat every 5 s for as long as the played
    // board's dictionary stayed empty -- a whole jelly match of stop-the-world
    // walks, and the 2026-09-12 20:04 freeze was one of those matches. The host
    // decodes the zone without it (verified=false).
    if (extraDataScanned) return null;
    extraDataScanned = true;
    // A board of THIS match's logic wins outright; any other live owner (the
    // AI's lookahead copy, an unreadable `logic`) is only the fallback. A
    // board whose logic is over -- dead, closed, finished -- is last match's
    // leftover still lying on the heap with last match's jelly keys, and is
    // never adopted: it would be cached for the whole match.
    let fallback: Il2Cpp.Object | null = null;
    try {
        const instances = chooseInstances(board.class, "BoardModel extraData");
        for (const instance of instances) {
            try {
                if (instance.handle.equals(board.handle)) continue;
                const owner = extraDataBoardOwner(instance);
                if (owner === "over") continue;
                if (owner === "other" && fallback != null) continue;
                const values = readStringDictionary(
                    fieldValue(instance, "extraData"),
                );
                if (!hasJellyExtraData(values)) continue;
                if (owner === "current") {
                    cachedExtraDataBoard = instance;
                    return instance;
                }
                fallback = instance;
            } catch (_) {
                continue;
            }
        }
    } catch (_) {
        // gc.choose itself failed; the next scan window retries.
    }
    if (fallback != null) cachedExtraDataBoard = fallback;
    return fallback;
}

/** Whose board is this? `BoardModel.logic` against the logic being read.
 *
 *  Field reads only, and only on the once-per-match extraData scan. */
function extraDataBoardOwner(instance: Il2Cpp.Object): "current" | "other" | "over" {
    let owner: any = null;
    try {
        owner = usable(fieldValue(instance, "logic"));
    } catch (_) {
        owner = null;
    }
    if (owner == null || owner.handle == null) return "other";
    const current = cachedGameLogic;
    try {
        if (current != null && owner.handle.equals(current.handle)) return "current";
    } catch (_) {
    }
    try {
        const logic = owner as Il2Cpp.Object;
        if (isDeadLogic(logic) || isEndedLogic(logic) || stateIsFinished(logic)) return "over";
    } catch (_) {
    }
    return "other";
}

/** The mutations currently in force, as GameLogic.mutationsActivatedList.
 *
 *  The 2026-08-19 sweep found the list but reported it as a type marker, which
 *  is the difference between knowing where a mutation is and knowing which one
 *  it is. Several mutation types (VerticalMatchDestroyColor, ColorChargesEnergy,
 *  SpecialsAutoExplode, DestroyRow/ColumnOnMatch) are rules the simulator
 *  already implements, so the id and type here are directly actionable. */
function readActiveMutations(logic: any): Record<string, any>[] | null {
    const list = fieldValue(logic, "mutationsActivatedList");
    if (list == null) return null;
    const mutations: Record<string, any>[] = [];
    for (const item of listItemsByField(list)) {
        const fields = readAllInstanceFields(item);
        if (fields == null) continue;
        // MutationLabMutation itself only carries the numeric `type` and its
        // running totals; the id ("vertical-match-destroy-color") is on the
        // config model it points at. Reading it means the host never has to
        // guess an enum ordering -- the ids are the same ones the shipped
        // catalogue uses (data/mutation_lab_catalogue.json).
        const config = fieldValue(item, "<config>k__BackingField");
        if (config != null) {
            const configFields = readAllInstanceFields(config);
            if (configFields != null) fields["config"] = configFields;
        }
        mutations.push(fields);
    }
    return mutations;
}

/** A static field's value, read off the class instead of an instance. */
function staticFieldValue(instance: any, name: string): any {
    try {
        const field = instance.class.tryField(name);
        if (field == null) return null;
        const value = field.value;
        return typeof value === "object" ? usable(value) : value;
    } catch (_) {
        return null;
    }
}

function point0(array: any): any {
    try {
        return (array as any).get(0);
    } catch (_) {
        return null;
    }
}

/** A struct's numeric fields, in declaration order -- Point becomes [x, y].
 *
 *  Reading them by position rather than by name is deliberate: the first
 *  attempt at this assumed `x`/`y` and produced eighteen empty tables, which
 *  says nothing about whether the read or the guess was wrong. */
function valueTypeNumbers(value: any): number[] | null {
    if (value == null) return null;
    const numbers: number[] = [];
    try {
        for (const field of valueTypeFields(value)) {
            if (field.isStatic || field.isLiteral) continue;
            const raw = value.field(field.name).value;
            const number = Number(raw);
            if (!Number.isFinite(number)) return null;
            numbers.push(number);
        }
    } catch (_) {
        return null;
    }
    return numbers.length > 0 ? numbers : null;
}

function valueTypeFieldNames(value: any): string[] | null {
    if (value == null) return null;
    try {
        const fields = valueTypeFields(value);
        return fields.length > 0
            ? fields.map((field: any) => `${field.name}:${field.type.name}`)
            : null;
    } catch (_) {
        return null;
    }
}

/** The declared fields of a struct element.
 *
 *  An element of a value-type array is an Il2Cpp.ValueType, which reaches its
 *  class through `.type.class` -- it has no `.class` of its own. Assuming it did
 *  is what made nineteen readable direction tables report zero points. */
function valueTypeFields(value: any): any[] {
    for (const owner of [value?.type?.class, value?.class]) {
        try {
            const fields = owner?.fields;
            if (fields != null && fields.length > 0) return fields;
        } catch (_) {
            // try the next one
        }
    }
    return [];
}

/** The active BoardModel's own fields, per snapshot and deliberately uncached.
 *
 *  Board models keep the mode's live state on themselves rather than on the
 *  slots -- Column Mania's per-column x1..x10 multipliers are on the board, not
 *  in `SlotModel.score`, which is why 60 captured frames of that mode showed
 *  nothing but ordinary pieces. Sweeping the board object is what turns the
 *  next such capture into a mapping instead of another open question. */
/** A List<Point> as [[x, y], ...], read through `_items`/`_size`.
 *
 *  Field reads only: `get_Count` on a generic list is what killed the game on
 *  attach the first time this agent swept unknown objects. */
function pointListValues(list: any, limit: number = 64): number[][] | null {
    const target = usable(list);
    if (target == null) return null;
    const points: number[][] = [];
    for (const item of listItemsByField(target, limit)) {
        const numbers = valueTypeNumbers(item);
        if (numbers == null) return null;
        points.push(numbers);
    }
    return points;
}

function resolveFroggy(onBoard: boolean): Il2Cpp.Object | null {
    if (cachedFroggy != null) {
        try {
            if (!cachedFroggy.handle.isNull()) return cachedFroggy;
        } catch (_) {
            // fall through and choose again
        }
        cachedFroggy = null;
    }
    if (froggyClass == null) return null;
    const owned = abilityFromPlayers(froggyClass);
    if (owned != null) {
        cachedFroggy = owned;
        return cachedFroggy;
    }
    // A lotus on the board proves the ability is in play whatever the models
    // say; without that proof, players who did not bring it are not searched.
    if (!onBoard && playersBroughtAbility(ABILITY_TYPE_FROGGY_FU) === false) return null;
    if (!abilityChooseAllowed(onBoard, froggyChooses, froggyChooseAfter)) return null;
    froggyChooses += 1;
    froggyChooseAfter = Date.now() + ABILITY_CHOOSE_SPACING_MS;
    try {
        const instances = chooseInstances(froggyClass, "FroggyFu");
        if (instances.length === 0) return null;
        cachedFroggy = instances[instances.length - 1];
        return cachedFroggy;
    } catch (_) {
        return null;
    }
}

/** Froggy Fu's recorded gather, straight off the ability instance.
 *
 *  `attractionMoveData` is a List<List<Point>>: one entry per swap the pull
 *  performed, each holding the two cells that were swapped. Replaying them in
 *  order reproduces the board the gather leaves behind, which no captured frame
 *  can show -- the animation is drawn one recorded step at a time.
 *
 *  `currentResolvePullCluster` is the gathered blob the engine is about to
 *  destroy, so it doubles as a direct check on `froggy_pull_landing_cells`. */
function readFroggyState(onBoard: boolean): FroggyState | null {
    const instance = resolveFroggy(onBoard);
    if (instance == null) return null;
    try {
        const moves: number[][][] = [];
        for (const step of listItemsByField(
            fieldValue(instance, "<attractionMoveData>k__BackingField"),
            256,
        )) {
            const points = pointListValues(step, 8);
            if (points != null && points.length > 0) moves.push(points);
        }
        return {
            attraction_moves: moves.length > 0 ? moves : null,
            pull_cluster: pointListValues(
                fieldValue(instance, "<currentResolvePullCluster>k__BackingField"),
            ),
            stamped_positions: pointListValues(
                fieldValue(instance, "<stampedPositions>k__BackingField"),
            ),
            planned_lotuses: pointListValues(
                fieldValue(instance, "plannedLotusPositionsThisActivation"),
            ),
            error: null,
        };
    } catch (error) {
        cachedFroggy = null;
        return {
            attraction_moves: null,
            pull_cluster: null,
            stamped_positions: null,
            planned_lotuses: null,
            error: String(error),
        };
    }
}

function resolveJelly(onBoard: boolean): Il2Cpp.Object | null {
    if (cachedJelly != null) {
        try {
            if (!cachedJelly.handle.isNull()) return cachedJelly;
        } catch (_) {
            // fall through and choose again
        }
        cachedJelly = null;
        cachedJellyKeys = null;
    }
    if (jellyClass == null) return null;
    const owned = abilityFromPlayers(jellyClass);
    if (owned != null) {
        cachedJelly = owned;
        cachedJellyKeys = null;
        return cachedJelly;
    }
    if (!onBoard && playersBroughtAbility(ABILITY_TYPE_JELLY_SE) === false) return null;
    if (!abilityChooseAllowed(onBoard, jellyChooses, jellyChooseAfter)) return null;
    jellyChooses += 1;
    jellyChooseAfter = Date.now() + ABILITY_CHOOSE_SPACING_MS;
    try {
        const instances = chooseInstances(jellyClass, "JellySE");
        if (instances.length === 0) return null;
        cachedJelly = instances[instances.length - 1];
        cachedJellyKeys = null;
        return cachedJelly;
    } catch (_) {
        return null;
    }
}

/** Which `extraData` keys this match's jelly uses.
 *
 *  The keys are `String.Format(template, abilityType, playerIndex)`, so their
 *  text cannot be known offline -- but it is fixed for the whole match, which is
 *  why the six getters run once per resolved instance and the result is cached.
 *  Everything after that is a plain dictionary read on the host side. */
function readJellyKeys(instance: any): Record<string, string | null> | null {
    if (cachedJellyKeys != null) return cachedJellyKeys;
    const names: [string, string][] = [
        ["all_infected", "get_AllInfectedKey"],
        ["source_cell", "get_SourceCellToInfectedKey"],
        ["target_color", "get_TargetColorKey"],
        ["phase", "get_PhaseKey"],
        ["uses_left", "get_UsesLeftKey"],
        ["total_uses_this_turn", "get_TotalUsesThisTurnKey"],
    ];
    const keys: Record<string, string | null> = {};
    let resolved = 0;
    for (const [label, getter] of names) {
        const text = asText(callGetter(instance, getter));
        keys[label] = text;
        if (text != null) resolved++;
    }
    if (resolved === 0) return null;
    cachedJellyKeys = keys;
    return keys;
}

/** The jelly's infected area, named by the engine rather than guessed at.
 *
 *  Two legs, deliberately. The keys (and, on a manual dump, the decoded points)
 *  come from the ability instance; the per-poll values come from the board's
 *  `extraData`, which is field reads only. `get_AllInfected` runs the engine's
 *  own deserialiser, which settles the payload format outright -- but it also
 *  allocates, so it is reserved for the verification dumps and never runs on
 *  the 250 ms poll. `verified` says which of the two produced the points. */
function readJellyState(deep: boolean, onBoard: boolean): JellyState | null {
    const instance = resolveJelly(onBoard);
    if (instance == null) return null;
    try {
        const keys = readJellyKeys(instance);
        let allInfected: number[][] | null = null;
        let sourceCell: number[][] | null = null;
        if (deep) {
            allInfected = pointListValues(callGetter(instance, "get_AllInfected"));
            sourceCell = pointListValues(
                callGetter(instance, "get_SourceCellToInfected"),
            );
        }
        return {
            keys,
            all_infected: allInfected,
            source_cell: sourceCell,
            conversion_point: valueTypeNumbers(
                fieldValue(instance, "ConversionPoint"),
            ),
            verified: deep && allInfected != null,
            error: null,
        };
    } catch (error) {
        cachedJelly = null;
        cachedJellyKeys = null;
        return {
            keys: null,
            all_infected: null,
            source_cell: null,
            conversion_point: null,
            verified: false,
            error: String(error),
        };
    }
}

/** The board's per-column score multiplier, off `CellModel.scoreMultiplier`.
 *
 *  Column Mania (`ColumnManiaBoard`, board model 32) keeps its whole mode state
 *  here: `onGameStart` writes 1 into every cell, and `onMoveEnd` raises every
 *  column that had something destroyed in it by one, capped at `MaxMultiplier`.
 *  The column list it accumulates during the move (`colsToIncrease`) is already
 *  swept into `board_fields`, but that is the pending delta -- the standing
 *  multiplier the bot has to score against is only in the cells.
 *
 *  A whole column shares one multiplier, so row 0 is the column's value; the
 *  other rows are read anyway and the maximum wins, which keeps the read honest
 *  if some future mode ever varies it down a column.
 */
function readCellMultipliers(board: any, rows: number, columns: number): number[] | null {
    const target = usable(board);
    if (target == null) return null;
    let getCell: any = null;
    try {
        getCell = target.method("GetCell", 2);
    } catch (_) {
        return null;
    }
    if (getCell == null) return null;
    const multipliers: number[] = [];
    for (let x = 0; x < columns; x++) {
        let best: number | null = null;
        for (let y = 0; y < rows; y++) {
            let value: number | null = null;
            try {
                const cell = getCell.invoke(x, y);
                value = fieldNumber(cell, "scoreMultiplier");
            } catch (_) {
                value = null;
            }
            if (value == null || !Number.isFinite(value)) continue;
            if (best == null || value > best) best = value;
        }
        // A column that read as nothing is not a x0 column; it is a failed read,
        // and scoring it as zero would be worse than not reporting at all.
        if (best == null) return null;
        multipliers.push(best);
    }
    return multipliers;
}


// Board models whose mode state is CellModel.cellType. 10 = VegasViewsBoard
// (CellType.Vegas = 2), 12 = FunkyTilesBoard (CellType.Funky = 3). Others that
// mark cells the same way (Bullseye 5, ExtraMove 6, BuriedTreasure 7/8, Hive 9)
// can be added here once the host has a use for them.
const CELL_TYPE_BOARD_MODELS = new Set<number>([10, 12]);

/** `CellModel.cellType` for every cell, [row][col] like `board`. */
function readCellTypes(board: any, rows: number, columns: number): number[][] | null {
    const target = usable(board);
    if (target == null) return null;
    let getCell: any = null;
    try {
        getCell = target.method("GetCell", 2);
    } catch (_) {
        return null;
    }
    if (getCell == null) return null;
    const grid: number[][] = [];
    for (let y = 0; y < rows; y++) {
        const row: number[] = [];
        for (let x = 0; x < columns; x++) {
            let value: number | null = null;
            try {
                const cell = getCell.invoke(x, y);
                value = listItemNumber(cell.field("cellType").value);
            } catch (_) {
                value = null;
            }
            // One unread cell makes the whole grid a failed read: a partial
            // grid would look like "no funky cell there".
            if (value == null || !Number.isFinite(value)) return null;
            row.push(value);
        }
        grid.push(row);
    }
    return grid;
}

function readBoardFields(board: any): Record<string, any> | null {
    return readAllInstanceFields(board);
}

function readRules(logic: Il2Cpp.Object): RulesState | null {
    const rules = fieldValue(logic, "gameRules");
    if (rules == null) return null;
    return {
        id: asText(fieldValue(rules, "id")),
        title: asText(fieldValue(rules, "title")),
        board_model_name: fieldNumber(rules, "boardModelName"),
        pvp_mode: fieldNumber(rules, "pvpMode"),
        rumble_type: fieldNumber(rules, "rumbleType"),
        board_size: fieldNumber(rules, "boardSize"),
        colors_count: fieldNumber(rules, "colorsCount"),
        moves_per_turn: fieldNumber(rules, "movesPerTurn"),
        additional_moves: fieldNumber(rules, "additionalMoves"),
        turns_per_game: fieldNumber(rules, "turnsPerGame"),
        time_per_turn: fieldNumber(rules, "timePerTurn"),
        is_timer: fieldBoolean(rules, "isTimer"),
        extra_move_enabled: fieldBoolean(rules, "extraMoveEnabled"),
        energy_mult: fieldNumber(rules, "energyMult"),
        // Score multiplier for every cell a special's blast or a merge swap
        // destroys (GameLogic.CalculateDestructionScoreAndMeter).
        special_combo_score_multiplier: fieldNumber(rules, "specialComboScoreMultiplier"),
        both_colors_charge_energy: fieldBoolean(rules, "bothColorsChargeEnergy"),
        explosion_on_match: fieldBoolean(rules, "explosionOnMatch"),
        destroy_row_on_horizontal_match: fieldBoolean(rules, "destroyRowOnHorizontalMatch"),
        destroy_column_on_vertical_match: fieldBoolean(rules, "destroyColumnOnVerticalMatch"),
        vertical_match_increase_multiplier: fieldBoolean(rules, "verticalMatchIncreaseMultiplier"),
        vertical_match_destroy_color: fieldBoolean(rules, "verticalMatchDestroyColor"),
        specials_auto_explode: fieldBoolean(rules, "specialsAutoExplode"),
        all_specials_lightning: fieldBoolean(rules, "allSpecialsLightning"),
        // "Every match creates a special piece" (Special O'Rama) and the
        // chance-based variant of the same idea.
        every_match_is_special: fieldBoolean(rules, "everyMatchIsSpecial"),
        match_creates_special_chance: fieldNumber(rules, "matchCreatesSpecialChance"),
        bigger_bomb_area: fieldBoolean(rules, "biggerBombArea"),
        ability_locked: fieldBoolean(rules, "abilityLocked"),
        reshuffle_every_turn: fieldBoolean(rules, "reshuffleEveryTurn"),
        solo_refill_mode: fieldBoolean(rules, "soloRefillMode"),
        solo_targets: numberList(fieldValue(rules, "soloTargets")),
        rumble_players_amount: fieldNumber(rules, "rumblePlayersAmount"),
        // Square (2x2) matching is a computed rule, not a stored field.
        is_square_match: getterBoolean(rules, "get_IsInSquareMatchMode"),
        color_combo_energy: intDictionaryValues(fieldValue(rules, "colorComboEnergy")),
        color_energy_override: intDictionaryValues(fieldValue(rules, "_colorEnergyOverride")),
        engine_fields: readAllRuleFields(rules),
    };
}

/** Seconds left in the current turn, or null when this mode has no clock.
 *
 *  One of the few values that has to come from a getter: nothing stores it.
 *  `TurnTimer.RemainingTime` computes `(timerDuration - stopwatch elapsed ms)
 *  / 1000` on every call, so the closest field (`timerDuration`) is the turn's
 *  whole budget and never counts down. The disassembly of
 *  `GameLogic::get_RemainingTime` (rva 0x573f0a0) shows both of its early
 *  exits are harmless -- a null `turnTimer` returns 0.0 and an untimed ruleset
 *  returns `timePerTurn` unchanged -- and the untimed case is filtered out
 *  here, because reporting the budget (1500) as a countdown would read as
 *  "twenty-five minutes left" to every caller.
 */
function readRemainingTime(logic: Il2Cpp.Object): number | null {
    const rules = fieldValue(logic, "gameRules");
    if (rules == null || fieldBoolean(rules, "isTimer") !== true) return null;
    // The getter dereferences gameRules; with a timer running the timer object
    // itself is the only other pointer it touches, and it null-checks that one.
    if (fieldValue(logic, "turnTimer") == null) return null;
    const seconds = getterNumber(logic, "get_RemainingTime");
    if (seconds == null || !Number.isFinite(seconds)) return null;
    return Math.max(0, seconds);
}

function readGameState(logic: Il2Cpp.Object, deep: boolean = false): GameStateBlock {
    // Field-first by design: a field read is a plain memory load, while every
    // method call runs engine code inside the live game. `deep` (manual dumps)
    // adds the ability's engine counters, see readAbilityEngineCounters.
    const players = listItems(fieldValue(logic, "players"), 8).map(
        (control) => readPlayer(control, deep),
    );
    const currentPlayerIndex = fieldNumber(logic, "currentPlayerIndex");
    const opponentIndex = players.length === 2 && currentPlayerIndex != null
        ? players.length - 1 - currentPlayerIndex
        : null;
    const chargingColors = players
        .filter((player) => player.index === currentPlayerIndex)
        .map((player) => player.energy_colors)[0];
    return {
        game_state: fieldNumber(logic, "currentGameState"),
        is_active: null,
        is_singleplayer_board: getterBoolean(logic, "get_IsSingleplayerBoard"),
        moves: fieldNumber(logic, "moves"),
        moves_made_this_turn: fieldNumber(logic, "<MovesMadeThisTurn>k__BackingField"),
        chain_reaction: fieldNumber(logic, "<ChainReaction>k__BackingField"),
        current_turn: fieldNumber(logic, "<Turns>k__BackingField"),
        turns: fieldNumber(logic, "<Turns>k__BackingField"),
        turns_total: fieldNumber(logic, "<TurnsTotal>k__BackingField"),
        current_round: getterNumber(logic, "get_CurrentRound"),
        rounds: getterNumber(logic, "get_Rounds"),
        rounds_total: getterNumber(logic, "get_RoundsTotal"),
        accumulated_move_score: null,
        accumulated_turn_score: fieldNumber(logic, "<AccumulatedTurnScore>k__BackingField"),
        remaining_time: readRemainingTime(logic),
        // A plain byte read (rva 0x573e628); the turn clock stops for popups
        // and reconnects, and a paused countdown must not be treated as time
        // running out.
        timer_paused: getterBoolean(logic, "get_TimerPaused"),
        current_player_index: currentPlayerIndex,
        opponent_index: opponentIndex,
        energy_charging_colors: chargingColors == null ? null : chargingColors,
        opponent_energy_charging_colors: null,
        players,
        rules: readRules(logic),
    };
}

/** Hash of the state fields that must trigger a resend; wall-clock-ish values
 *  (remaining time, accumulated score mid-cascade) are deliberately excluded so
 *  an unchanged turn does not churn the stream. */
function stateSignatureFor(state: GameStateBlock | null): string {
    if (state == null) return "00000000";
    const parts: (number | null)[] = [
        state.game_state, state.moves, state.moves_made_this_turn,
        state.current_turn, state.current_round, state.current_player_index,
    ];
    for (const player of state.players) {
        parts.push(
            player.index, player.score, player.turn_score, player.energy,
            player.energy_to_ability, player.rounds_won, player.score_multiplier,
            player.is_my_turn ? 1 : 0,
        );
    }
    let hash = 0x811c9dc5;
    for (const part of parts) {
        let value = Number(part == null ? 0xffff : part) >>> 0;
        for (let shift = 0; shift < 32; shift += 8) {
            hash ^= (value >>> shift) & 0xff;
            hash = Math.imul(hash, 0x01000193) >>> 0;
        }
    }
    return hash.toString(16).padStart(8, "0");
}

/** Everything in a snapshot that is not the 49 slots, cached per board state.
 *
 *  These six reads are what makes a snapshot expensive: `readBoardFields` and
 *  `readMutationFields` each walk every field of a whole class, `GetCell` is
 *  another 49 IL2CPP calls, and `extraData` decodes a dictionary. At a 100 ms
 *  poll (30 ms in trace mode) that ran ten to thirty times a second inside the
 *  game process, and on an emulator it is felt as stutter.
 *
 *  None of it can change without either the board changing or the turn moving
 *  on, so the cache key is exactly that: the slot signature plus the engine's
 *  own move counters. `colsToIncrease` clearing at `onMoveEnd` is the sharpest
 *  case and it is covered -- that transition changes `moves`/`MovesMadeThisTurn`
 *  even when the settled board looks identical. The age cap is a backstop for
 *  any field that moves on its own, and a manual dump never reads the cache.
 */
interface SnapshotExtras {
    board_fields: Record<string, any> | null;
    board_directions: Record<string, any> | null;
    cell_multipliers: number[] | null;
    /** CellModel.cellType per cell as [row][col]; null when not read. */
    cell_types: number[][] | null;
    mutation_fields: Record<string, any> | null;
    active_mutations: Record<string, any>[] | null;
    board_extra_data: Record<string, string> | null;
    board_extra_data_diag: Record<string, any> | null;
}
let cachedExtras: SnapshotExtras | null = null;
let cachedExtrasKey: string | null = null;
let cachedExtrasAt = 0;
const EXTRAS_MAX_AGE_MS = 1000;
// Board model 32 is ColumnManiaBoard, the only mode whose score is read out of
// CellModel.scoreMultiplier. Every other mode paid 49 GetCell calls per poll
// for a column of ones nothing looks at.
const COLUMN_MANIA_BOARD_MODEL = 32;
let cachedBoardModel: number | null = null;
let cachedBoardModelKey: string | null = null;

/** `gameRules.boardModelName`, read once per match rather than once per poll. */
function boardModelId(logic: any): number | null {
    let key: string | null = null;
    try {
        key = String(logic.handle);
    } catch (_) {
        key = null;
    }
    if (key != null && key === cachedBoardModelKey) return cachedBoardModel;
    let value: number | null = null;
    try {
        const rules = fieldValue(logic, "gameRules");
        value = rules == null ? null : fieldNumber(rules, "boardModelName");
    } catch (_) {
        value = null;
    }
    // An unread rule set is not an answer: leaving the key unset retries next
    // poll (two field reads) instead of pinning "unknown" for the whole match.
    if (value == null) return null;
    cachedBoardModelKey = key;
    cachedBoardModel = value;
    return value;
}

/** What the extras cache is keyed on besides the board: where the turn stands. */
function turnKeyFor(logic: any): string {
    const parts: (number | null)[] = [];
    for (const name of [
        "moves",
        "<MovesMadeThisTurn>k__BackingField",
        "<ChainReaction>k__BackingField",
        "<Turns>k__BackingField",
        "currentPlayerIndex",
    ]) {
        let value: number | null = null;
        try {
            value = fieldNumber(logic, name);
        } catch (_) {
            value = null;
        }
        parts.push(value);
    }
    return parts.join(",");
}

// The Floor Is Lava: the board the *view* listens to. LavaBackground (the
// MonoBehaviour that draws the broken ground) keeps `_board`, the
// FloorIsLavaBoard whose OnBreak/OnEruption/OnReset drive the screen. On
// 2026-09-18 the played board's ColumnsEruptionDictionary read empty through a
// whole match while the ground on screen was broken under several columns --
// the same "played board is not the one that carries the state" the jelly's
// extraData showed -- so the counter is read off the view's board as well.
const LAVA_VIEW_CLASS = "match3.board.SpeacialBoards.LavaBackground";
const LAVA_BOARD_CLASS = "FloorIsLavaBoard";
let lavaViewClass: Il2Cpp.Class | null | undefined = undefined;
let cachedLavaView: Il2Cpp.Object | null = null;
let cachedLavaViewFor: string | null = null;
let lavaViewChosenFor: string | null = null;

function resolveLavaViewClass(): Il2Cpp.Class | null {
    if (lavaViewClass !== undefined) return lavaViewClass;
    lavaViewClass = null;
    try {
        lavaViewClass = Il2Cpp.domain.assembly("Assembly-CSharp").image.class(LAVA_VIEW_CLASS);
    } catch (_) {
        lavaViewClass = null;
    }
    return lavaViewClass;
}

/** The LavaBackground showing this match, found without a heap walk if the
 *  played board is the one it subscribed to, and with one walk per board
 *  object otherwise. */
function lavaViewFor(board: any, diag: Record<string, any>): Il2Cpp.Object | null {
    const boardKey = String(board.handle);
    if (cachedLavaView != null && cachedLavaViewFor === boardKey) {
        diag.found_via = "cache";
        return cachedLavaView;
    }
    cachedLavaView = null;
    cachedLavaViewFor = null;
    const subscribed: Record<string, boolean> = {};
    for (const name of ["OnBreak", "OnEruption", "OnReset"]) {
        try {
            const handler = usable(fieldValue(board, name));
            subscribed[name] = handler != null;
            if (handler == null) continue;
            const target = usable(fieldValue(handler, "m_target"));
            if (target != null && String(target.class.name) === "LavaBackground") {
                cachedLavaView = target;
                cachedLavaViewFor = boardKey;
                diag.found_via = `delegate:${name}`;
                diag.played_board_subscribed = subscribed;
                return target;
            }
        } catch (_) {
            // try the next delegate
        }
    }
    diag.played_board_subscribed = subscribed;
    if (lavaViewChosenFor === boardKey) {
        diag.found_via = "none (walk already done for this board)";
        return null;
    }
    lavaViewChosenFor = boardKey;
    const klass = resolveLavaViewClass();
    if (klass == null) {
        diag.found_via = "none (LavaBackground class not resolved)";
        return null;
    }
    try {
        const instances = chooseInstances(klass, "LavaBackground");
        diag.view_instances = instances.length;
        for (let index = instances.length - 1; index >= 0; index--) {
            if (usable(fieldValue(instances[index], "_board")) != null) {
                cachedLavaView = instances[index];
                cachedLavaViewFor = boardKey;
                diag.found_via = "heap walk";
                return cachedLavaView;
            }
        }
    } catch (error) {
        diag.walk_error = String(error);
    }
    diag.found_via = "none";
    return null;
}

/** The lava counter as the view's board has it, plus what was compared. */
function readLavaView(board: any): Record<string, any> | null {
    let className = "";
    try {
        className = String(board.class.name);
    } catch (_) {
        return null;
    }
    if (className !== LAVA_BOARD_CLASS) return null;
    const diag: Record<string, any> = { played_board: String(board.handle) };
    try {
        const view = lavaViewFor(board, diag);
        if (view == null) return diag;
        const viewBoard = usable(fieldValue(view, "_board"));
        if (viewBoard == null) {
            diag.view_board = null;
            return diag;
        }
        diag.view_board = String(viewBoard.handle);
        diag.same_board = viewBoard.handle.equals(board.handle);
        const dictionary = fieldValue(viewBoard, "ColumnsEruptionDictionary");
        diag.columns = intDictionaryValues(dictionary);
        diag.columns_diag = intDictionaryDiag(dictionary);
        try {
            diag.extra_data = readStringDictionary(fieldValue(viewBoard, "extraData"), 32);
        } catch (_) {
            diag.extra_data = null;
        }
    } catch (error) {
        diag.error = String(error);
    }
    return diag;
}

function readSnapshotExtras(
    logic: any,
    board: any,
    rows: number,
    columns: number,
    signature: string,
    fresh: boolean,
): SnapshotExtras {
    const now = Date.now();
    let key: string | null = null;
    try {
        key = `${board.handle}|${signature}|${turnKeyFor(logic)}`;
    } catch (_) {
        key = null;
    }
    if (
        !fresh &&
        key != null &&
        cachedExtras != null &&
        key === cachedExtrasKey &&
        now - cachedExtrasAt < EXTRAS_MAX_AGE_MS
    ) {
        return cachedExtras;
    }
    // Every one of these is a bonus: a broken read must never cost us the board.
    let boardFields: Record<string, any> | null = null;
    try {
        boardFields = readBoardFields(board);
    } catch (_) {
        boardFields = null;
    }
    if (boardFields != null) {
        try {
            const lavaView = readLavaView(board);
            if (lavaView != null) {
                boardFields.lava_view = lavaView;
                // The view's board is the one the screen shows, so when it is a
                // different object its counter is the one the host should get.
                if (lavaView.same_board === false && lavaView.columns != null) {
                    boardFields.ColumnsEruptionDictionary__played =
                        boardFields.ColumnsEruptionDictionary ?? null;
                    boardFields.ColumnsEruptionDictionary = lavaView.columns;
                }
            }
        } catch (_) {
            // a bonus read; the board itself must not depend on it
        }
    }
    let boardDirections: Record<string, any> | null = null;
    try {
        boardDirections = readDirectionTables(board);
    } catch (_) {
        boardDirections = null;
    }
    let cellMultipliers: number[] | null = null;
    const model = boardModelId(logic);
    // An unreadable board model reads the multipliers anyway: the old cost is
    // better than silently dropping the mode's whole score model.
    if (model == null || model === COLUMN_MANIA_BOARD_MODEL) {
        try {
            cellMultipliers = readCellMultipliers(board, rows, columns);
        } catch (_) {
            cellMultipliers = null;
        }
    }
    // Funky Tiles keeps its marked cells nowhere but in CellModel.cellType
    // (Funky = 3) -- the markers are drawn over the board and have no slot.
    let cellTypes: number[][] | null = null;
    if (model != null && CELL_TYPE_BOARD_MODELS.has(model)) {
        try {
            cellTypes = readCellTypes(board, rows, columns);
        } catch (_) {
            cellTypes = null;
        }
    }
    // A 2026-08-19 Mutation Lab match proved the picked mutation is *not* on
    // PlayerModel: the only mutation field there is `mutationLabTargetInd`. The
    // engine's own names for it (`mutationsActivatedList`,
    // `activeTurnStartMutations`, `choseMutationThisMove`) have to belong to
    // some other object, and GameLogic owns the match, so it is swept too.
    let mutationFields: Record<string, any> | null = null;
    try {
        mutationFields = readMutationFields(logic);
    } catch (_) {
        mutationFields = null;
    }
    let activeMutations: Record<string, any>[] | null = null;
    try {
        activeMutations = readActiveMutations(logic);
    } catch (_) {
        activeMutations = null;
    }
    let boardExtraData: Record<string, string> | null = null;
    let boardExtraDataDiag: Record<string, any> | null = null;
    try {
        boardExtraDataDiag = {};
        boardExtraData = readStringDictionary(
            fieldValue(board, "extraData"),
            64,
            boardExtraDataDiag,
        );
    } catch (error) {
        boardExtraData = null;
        boardExtraDataDiag = { error: String(error) };
    }
    // The played board's dictionary sits empty for whole jelly matches (see
    // cachedExtraDataBoard); an empty read with a live jelly means the state
    // is on some other BoardModel instance, so read it from there instead.
    if (boardExtraData == null || Object.keys(boardExtraData).length === 0) {
        const fallback = extraDataFallbackBoard(board);
        if (fallback != null) {
            try {
                const values = readStringDictionary(
                    fieldValue(fallback, "extraData"),
                );
                if (values != null && Object.keys(values).length > 0) {
                    boardExtraData = values;
                }
            } catch (_) {
                // keep the main board's (empty) read
            }
        }
    }
    const extras: SnapshotExtras = {
        board_fields: boardFields,
        board_directions: boardDirections,
        cell_multipliers: cellMultipliers,
        cell_types: cellTypes,
        mutation_fields: mutationFields,
        active_mutations: activeMutations,
        board_extra_data: boardExtraData,
        board_extra_data_diag: boardExtraDataDiag,
    };
    cachedExtras = extras;
    cachedExtrasKey = key;
    cachedExtrasAt = now;
    return extras;
}

function buildSnapshot(reason: string, stable: boolean): Snapshot {
    const logic = resolveGameLogic();
    const board = boardObject(logic);
    let rows = 7;
    let columns = 7;
    try { rows = asNumber(board.field<number>("<Rows>k__BackingField").value); } catch (_) {}
    try { columns = asNumber(board.field<number>("<Columns>k__BackingField").value); } catch (_) {}
    // Supersize is 8x8. The reader is not tied to one size -- the host adapter
    // and the simulator both work off the dumped dimensions -- but a size the
    // host has no screen calibration for is refused there, not here, and a
    // non-square or absurd read still means the wrong object was resolved.
    if (rows !== columns || rows < 4 || rows > 12) {
        throw new Error(`active board is ${columns}x${rows}, expected a square 4..12`);
    }
    const getItem = board.method<Il2Cpp.Object>("get_Item", 2);
    const slots: RawSlot[] = [];
    for (let y = 0; y < rows; y++) {
        for (let x = 0; x < columns; x++) {
            const slot = getItem.invoke(x, y) as Il2Cpp.Object;
            if (slot == null || slot.handle.isNull()) {
                throw new Error(`BoardModel.get_Item(${x},${y}) returned null`);
            }
            slots.push(readSlot(slot, x, y));
        }
    }
    const signature = signatureFor(slots);
    // A manual dump is asked for by a person and answers once, so it always
    // reads the game rather than the cache.
    const extras = readSnapshotExtras(
        logic,
        board,
        rows,
        columns,
        signature,
        reason !== "stable_poll" && reason !== "trace_poll",
    );
    const boardExtraData = extras.board_extra_data;
    // The engine's own deserialiser only runs when someone is looking: a manual
    // dump always, and with Debug on (trace mode) once every half second on a
    // settled board. The plain poll has no business allocating inside the game,
    // and neither has a trace frame caught mid-cascade.
    const now = Date.now();
    // Manual dumps ONLY. The trace-mode half-second path used to run
    // `get_AllInfected` during live jelly matches, and that call allocates
    // through the engine's own deserialiser from this agent thread -- the
    // exact operation that can deadlock the il2cpp runtime against the game's
    // GC. The user's jelly matches were freezing (reported 2026-08-28); the
    // host decodes the zone from `extraData` by key hints without it
    // (board_source.jelly_zone_state), it just reports verified=false.
    //
    // Every manual dump decodes afresh; its answer is not reused for a later
    // dump of the "same" board. A jelly throw repaints the zone without moving
    // a piece, so board + turn is not a safe cache key (tried 2026-09-14, and
    // the host played a whole turn on a zone that was gone). What keeps these
    // calls rare now is the host: it dumps once per changed board, not every
    // 0.4 s.
    const deepJelly = reason === "manual_rpc";
    if (deepJelly) jellyDeepAfter = now + JELLY_DEEP_INTERVAL_MS;
    // Whether the jelly is live at all, off the dictionary that is read anyway:
    // without this the heap walk behind readJellyState runs in every mode.
    let jellyOnBoard = false;
    if (boardExtraData != null) {
        for (const key of Object.keys(boardExtraData)) {
            if (JELLY_EXTRA_DATA_HINT.test(key)) {
                jellyOnBoard = true;
                break;
            }
        }
    }
    let jelly: JellyState | null = null;
    try {
        jelly = readJellyState(deepJelly, jellyOnBoard);
    } catch (_) {
        jelly = null;
    }
    const lotusOnBoard = slots.some((slot) => slot.value === FROGGY_LOTUS_SLOT_VALUE);
    let state: GameStateBlock | null = null;
    let stateError: string | null = null;
    if (includeState) {
        try {
            state = readGameState(logic, deepJelly);
        } catch (error) {
            stateError = String(error);
        }
    }
    return {
        schema_version: 4,
        type: "board_snapshot",
        captured_at: new Date().toISOString(),
        reason,
        stable,
        rows,
        columns,
        game_logic: logic.handle.toString(),
        board_object: board.handle.toString(),
        board_fields: extras.board_fields,
        board_directions: extras.board_directions,
        cell_multipliers: extras.cell_multipliers,
        cell_types: extras.cell_types,
        mutation_fields: extras.mutation_fields,
        active_mutations: extras.active_mutations,
        board_extra_data: boardExtraData,
        board_extra_data_diag: extras.board_extra_data_diag,
        jelly,
        froggy: readFroggyState(lotusOnBoard),
        signature,
        state_signature: stateSignatureFor(state),
        slots,
        state,
        state_error: stateError,
        game_version: cachedGameVersion,
        enums: cachedEnumTables,
    };
}

function sendSnapshot(snapshot: Snapshot, force: boolean): boolean {
    // A turn can pass, energy can tick and the score can settle while the board
    // itself is untouched, so the state signature is a resend trigger too.
    //
    // And so is settling. With the trace on, the mid-cascade frame that landed
    // on the final arrangement has already been sent unstable; the settled
    // snapshot that follows carries the same two signatures, gets deduplicated
    // away, and the host is left holding a board that says "still moving"
    // forever -- with auto refusing to play on it, which is what "Auto
    // ukljucen" and nothing else looked like on 2026-08-21. `stable` is part of
    // what changed, so it belongs in the comparison.
    const unchanged = snapshot.signature === lastSentSignature
        && snapshot.state_signature === lastSentStateSignature
        && snapshot.stable === lastSentStable;
    if (!force && unchanged) return false;
    lastSentSignature = snapshot.signature;
    lastSentStateSignature = snapshot.state_signature;
    lastSentStable = snapshot.stable;
    send({ type: "board_snapshot", snapshot });
    return true;
}

function pollOnce(): void {
    try {
        const snapshot = buildSnapshot("stable_poll", false);
        lastError = null;
        consecutivePollErrors = 0;
        if (snapshot.signature !== candidateSignature) lastChangeTimestamp = Date.now();
        if (snapshot.signature === candidateSignature) {
            candidateCount += 1;
        } else {
            candidateSignature = snapshot.signature;
            candidateCount = 1;
        }
        if (candidateCount >= requiredStableSamples) {
            snapshot.stable = true;
            if (sendSnapshot(snapshot, false)) lastChangeTimestamp = Date.now();
        } else if (traceMode) {
            // Debug trace: the settled board hides how it got there. Every
            // *changed* mid-cascade frame is what shows which cells a special
            // actually cleared (empty slots, before the refill covers them),
            // how the energy meter climbs step by step and where the score
            // comes from. Deduplication by signature stays on, so an unchanged
            // board still costs nothing.
            snapshot.reason = "trace_poll";
            sendSnapshot(snapshot, false);
        }
    } catch (error) {
        const message = String(error);
        candidateSignature = null;
        candidateCount = 0;
        consecutivePollErrors += 1;
        if (message !== lastError) {
            lastError = message;
            send({ type: "error", stage: "poll", message });
        }
    }
}

/** The static match counter, read without walking the heap.
 *
 *  `GameLogic.GameCount` is a static Int64 the engine bumps for every match it
 *  starts, so it lives at a fixed address: reading it is a memory read, not a
 *  heap walk, and it is what makes idling free. */
function readGameCount(): number | null {
    if (gameLogicClass == null) return null;
    try {
        const field = gameLogicClass.tryField<any>("GameCount");
        return field == null ? null : asNumber(field.value);
    } catch (_) {
        return null;
    }
}

/** The engine's GameState for one logic instance, or null if unreadable.
 *
 *  The bridge's field accessor returns something that does not survive
 *  `asNumber` for this enum (it measured as -1/-3/-5/-7 on 2026-08-21), so a
 *  plain 32-bit read at the known offset is the reliable path and the field
 *  API is only the fallback. */
function readGameStateEnum(logic: Il2Cpp.Object): number | null {
    const plausible = (value: number | null): number | null =>
        value != null
        && Number.isInteger(value)
        && value >= GAME_STATE_IN_MATCH_MIN
        && value <= GAME_STATE_FINISHED_MAX
            ? value
            : null;
    try {
        // Signed: the in-match half of this enum is negative.
        const native = plausible(
            logic.handle.add(EXPECTED_OFFSETS["GameLogic.currentGameState"]).readS32()
        );
        if (native != null) return native;
    } catch (_) {
    }
    try {
        const field = logic.tryField<any>("currentGameState");
        return field == null ? null : plausible(asNumber(field.value));
    } catch (_) {
        return null;
    }
}

/** Is there a match to read right now?
 *
 *  Only called when the free counter says something may have changed, because
 *  it pays for one heap walk. */
function matchIsRunning(): boolean {
    let logic: Il2Cpp.Object;
    try {
        logic = resolveGameLogic();
    } catch (_) {
        return false;
    }
    if (isDeadLogic(logic)) return false;
    const state = readGameStateEnum(logic);
    // An unreadable state must not veto the match: the counter already said a
    // new one started, and refusing to play is worse than polling the lobby.
    if (state != null && state >= GAME_STATE_FINISHED_MIN) return false;
    if (quietSignature == null) return true;
    // Closed by the quiet timeout: only a board that has actually changed
    // since then is a live match rather than the leftover of a finished one.
    try {
        const moved = buildSnapshot("idle_recheck", false).signature !== quietSignature;
        if (moved) quietSignature = null;
        return moved;
    } catch (_) {
        return false;
    }
}

/** Did the engine's own state say the leftover match is over?
 *
 *  Read on its own, without the "unreadable means keep playing" leniency that
 *  `matchIsRunning` needs once the counter has already promised a new match.
 *  Anything short of a clear in-match state is treated as no match here. */
function stateSaysInMatch(): boolean {
    try {
        const logic = resolveGameLogic();
        // The logic the last match ended on keeps an in-match state after a
        // concede or an abandoned match; its state is no evidence of a match.
        // If play really resumed on it, the board moves, and that is caught
        // by matchIsRunning's signature test on the idle recheck instead.
        if (isEndedLogic(logic) || isDeadLogic(logic)) return false;
        const state = readGameStateEnum(logic);
        return (
            state != null
            && state <= GAME_STATE_IN_MATCH_MAX
            && state >= GAME_STATE_IN_MATCH_MIN
        );
    } catch (_) {
        return false;
    }
}

/** What a live match changes and a corpse does not. Field reads plus the one
 *  clock getter the snapshots already call; no walk, no snapshot. */
function liveFingerprint(logic: Il2Cpp.Object): string {
    let clock: number | null = null;
    try {
        const seconds = readRemainingTime(logic);
        clock = seconds == null ? null : Math.round(seconds * 10);
    } catch (_) {
        clock = null;
    }
    return JSON.stringify([
        fieldNumber(logic, "currentGameState"),
        fieldNumber(logic, "moves"),
        fieldNumber(logic, "<MovesMadeThisTurn>k__BackingField"),
        fieldNumber(logic, "<Turns>k__BackingField"),
        fieldNumber(logic, "currentPlayerIndex"),
        fieldNumber(logic, "<AccumulatedTurnScore>k__BackingField"),
        clock,
    ]);
}

/** Start watching the in-match logic the first tick found (see attachProbe). */
function startAttachProbe(): void {
    const logic = cachedGameLogic;
    if (logic == null) return;
    let print = "";
    try {
        print = liveFingerprint(logic);
    } catch (_) {
        print = "";
    }
    attachProbe = { key: logicKey(logic), print };
    send({
        type: "match_pending",
        reason: "attach_probe",
        note: "partija na heapu, cekam znak zivota (ili Auto / dugme za potez)",
        state: readGameStateEnum(logic),
    });
}

/** Has the probed logic shown life, or has another logic taken its place?
 *  Called right after stateSaysInMatch(), which leaves the logic cached. */
function attachProbeSaysLive(): boolean {
    const probe = attachProbe;
    const logic = cachedGameLogic;
    if (probe == null) return true;
    if (logic == null) return false;
    if (logicKey(logic) !== probe.key) return true;
    try {
        return liveFingerprint(logic) !== probe.print;
    } catch (_) {
        return false;
    }
}

function setMatchActive(active: boolean, reason: string): void {
    if (matchActive === active) return;
    matchActive = active;
    // Whatever opened the match (the counter, wake, a live probe) settles it.
    if (active) attachProbe = null;
    let endedKey: string | null = null;
    let dead = false;
    if (active) {
        // Play resumed on the very logic that was closed (a popup outlasted
        // the quiet timeout): it is a live match again, not a corpse.
        if (cachedGameLogic != null && isEndedLogic(cachedGameLogic)) endedLogicHandle = null;
    } else if (cachedGameLogic != null) {
        endedKey = logicKey(cachedGameLogic);
        dead = !SOFT_END_REASONS.has(reason);
        if (dead) {
            markLogicDead(endedKey);
        } else {
            try {
                endedLogicHandle = cachedGameLogic.handle.toString();
            } catch (_) {
                endedLogicHandle = null;
            }
        }
    }
    if (!active) {
        // The logic that just ended is the corpse the lobby will keep finding;
        // nothing to walk for until the counter rises or the backstop is due.
        idleChooseAfter = Date.now() + IDLE_WALK_INTERVAL_MS;
    }
    cachedGameLogic = active ? cachedGameLogic : null;
    // Consumed on end, and a stale one from the lobby (a concede replayed in
    // menus, a rematch screen) must not kill the next match at its first poll.
    concededAt = null;
    // The disposed match is the one that just closed (or last lobby's); the
    // next match is a fresh object and must not inherit the verdict.
    disposedHandle = null;
    disposedAt = null;
    candidateSignature = null;
    candidateCount = 0;
    consecutivePollErrors = 0;
    lastChangeTimestamp = Date.now();
    // A new match is a new board, new rules and a fresh chance for an ability
    // this one does have -- so the caches and the backoffs start over on both
    // edges, not only when a match ends.
    cachedExtras = null;
    cachedExtrasKey = null;
    cachedBoardModel = null;
    cachedBoardModelKey = null;
    // The heap-walk budgets belong to the match, not to this open/close edge:
    // reset only when a DIFFERENT GameLogic opens (see budgetMatchHandle).
    if (active) {
        let handle: string | null = null;
        try {
            handle = cachedGameLogic == null ? null : cachedGameLogic.handle.toString();
        } catch (_) {
            handle = null;
        }
        if (handle == null || handle !== budgetMatchHandle) {
            budgetMatchHandle = handle;
            froggyChooses = 0;
            froggyChooseAfter = 0;
            jellyChooses = 0;
            jellyChooseAfter = 0;
            inMatchResolveWalks = 0;
            inMatchResolveAfter = 0;
            cachedExtraDataBoard = null;
            extraDataScanned = false;
        }
    }
    heartbeatAfter = 0;
    if (active) {
        quietSignature = null;
        pendingMatchUntil = 0;
        pendingSince = null;
    } else {
        // Nothing about the finished match should leak into the next one.
        lastSentSignature = null;
        lastSentStateSignature = null;
        lastSentStable = null;
        cachedFroggy = null;
        cachedJelly = null;
        cachedJellyKeys = null;
        cachedLavaView = null;
        cachedLavaViewFor = null;
        lavaViewChosenFor = null;
        // A hook switch-off that arrived mid-match detaches now, between matches.
        if (ctorHookDetachPending) removeCtorHook();
    }
    send({
        type: "match_state",
        active,
        reason,
        game_count: lastGameCount,
        poll_milliseconds: active ? pollMilliseconds : idleMilliseconds,
        // For the host to persist: the logic this match ended on, and whether
        // the end is final (see deadLogicKeys / markDead).
        logic_key: endedKey,
        dead,
    });
    startPolling();
}

/** The free tick: no heap walk unless there is a reason to take one. */
function idleOnce(): void {
    const count = readGameCount();
    if (count == null) return;
    const previous = lastGameCount;
    lastGameCount = count;
    if (count <= 0) return;
    const now = Date.now();
    // A rising counter is a match that just started -- the cheap, exact signal.
    if (previous != null && count > previous) {
        pendingMatchUntil = now + PENDING_MATCH_MS;
        pendingSince = now;
        // A match just started: no pacing delay, and no waiting out the rest
        // of the state-check interval either -- check on this very tick.
        idleChooseAfter = 0;
        stateCheckAfter = 0;
        send({
            type: "match_pending",
            reason: "game_count",
            game_count: count,
            previous,
        });
    }
    // And so is a GameLogic the hook just watched being built. It fires before
    // the counter is even readable as changed, and it costs nothing to check.
    if (useCtorHook && constructedHandle != null) {
        const seen = constructedHandle.toString();
        if (seen !== constructedSeen) {
            constructedSeen = seen;
            if (previous != null) pendingMatchUntil = now + PENDING_MATCH_MS;
        }
    }
    // The first tick after attaching: the counter cannot rise for a match that
    // was already running when the agent arrived, so the engine's own state is
    // asked once -- strictly, with no "unreadable means yes" leniency, because
    // a finished match is still lying on the heap looking playable.
    if (previous == null) {
        // Not opened here any more: a corpse passes stateSaysInMatch just as
        // well. It becomes the probe the state check below watches.
        if (stateSaysInMatch()) startAttachProbe();
        stateCheckAfter = now + IDLE_STATE_CHECK_MS;
        return;
    }
    // The primary check: does the engine say a match is running? Strict on
    // purpose -- only a readable, in-match state counts -- because a finished
    // match stays on the heap looking playable, and its state is positive.
    if (now >= stateCheckAfter) {
        stateCheckAfter = now + IDLE_STATE_CHECK_MS;
        if (stateSaysInMatch()) {
            // Still the logic found at attach and nothing about it moved:
            // that is what a corpse looks like, so keep waiting.
            if (!attachProbeSaysLive()) return;
            const reason = attachProbe != null ? "vec u partiji" : "stanje igre";
            pendingMatchUntil = 0;
            pendingSince = null;
            setMatchActive(true, reason);
            return;
        }
        // A false here is also a lobby walk that was deferred, so the probe
        // stays: dropping it would let the next readable check open the very
        // corpse it was guarding against. Only an opened match clears it.
    }
    if (now < pendingMatchUntil) {
        if (matchIsRunning()) {
            pendingMatchUntil = 0;
            setMatchActive(true, "game_count");
        }
        return;
    }
    // The window closed without the match ever becoming readable. Silence here
    // is what "it did not pick up the match" looked like, so it says why.
    if (pendingSince != null) {
        pendingSince = null;
        let detail: Record<string, any> = {};
        try {
            const logic = resolveGameLogic();
            detail = {
                state: readGameStateEnum(logic),
                has_board: hasBoard(logic),
                simulation: isSimulation(logic),
            };
        } catch (error) {
            detail = { resolve_error: String(error) };
        }
        send({
            type: "match_pending_failed",
            game_count: count,
            waited_ms: PENDING_MATCH_MS,
            deferred_resolves: deferredResolves,
            ...detail,
        });
    }
    // A counter that has not moved is NOT evidence of a match. The engine
    // leaves the finished GameLogic on the heap with its board, its mode and
    // its score intact, so anything softer than "the counter rose" reads that
    // leftover as a live match and starts replaying the previous game --
    // measured on 2026-08-21, twice. The only exception is a match this agent
    // itself closed on the quiet timeout, which `quietSignature` makes
    // checkable: there, a board that has moved since really is play resuming.
    if (quietSignature == null) return;
    if (now < recheckAfter) return;
    recheckAfter = now + IDLE_RECHECK_MS;
    if (matchIsRunning()) setMatchActive(true, "partija se nastavila");
}

/** Has the active match ended? Cheap: the logic object is already cached. */
function matchEnded(): string | null {
    // The logic being read says it is over, or the host says it was over
    // before this agent was even attached. Checked on the CACHED object,
    // before any resolve: a resolve on a finished logic used to swap in an
    // older corpse and the finished state was never seen.
    if (cachedGameLogic != null) {
        if (isDeadLogic(cachedGameLogic)) return "partija iz prethodne sesije";
        const cachedState = readGameStateEnum(cachedGameLogic);
        if (cachedState != null && cachedState >= GAME_STATE_FINISHED_MIN) return "partija zavrsena";
    }
    // The concede hook is the exact signal: the engine said someone gave up,
    // and the leftover GameLogic will keep looking playable forever.
    if (concededAt != null) return "predaja";
    // The engine tore down the very logic we are reading: the match was left
    // (or ended without the state saying so). Checked before resolving, which
    // may swap the cache for a fresher object and lose the comparison.
    if (readingLogicDisposed()) return "partija napustena";
    if (consecutivePollErrors >= 10) return "nema table";
    let logic: Il2Cpp.Object;
    try {
        logic = resolveGameLogic();
    } catch (_) {
        return "GameLogic je nestao";
    }
    const state = readGameStateEnum(logic);
    if (state != null && state >= GAME_STATE_FINISHED_MIN) return "partija zavrsena";
    // The engine keeps the finished GameLogic alive with its last board intact,
    // so a board that has not moved at all is the backstop for an end that the
    // state field did not report.
    if (idleAfterQuietMs > 0 && Date.now() - lastChangeTimestamp > idleAfterQuietMs) {
        return "tabla se ne menja";
    }
    return null;
}

/** The board signature seen when a match was closed by the quiet timeout.
 *
 *  Reopening on the recheck must mean the board *moved*, not merely that a
 *  finished GameLogic is still lying on the heap in a playable-looking state
 *  -- which is exactly what the engine leaves behind (measured). */
let quietSignature: string | null = null;

function tick(): void {
    const started = Date.now();
    try {
        tickBody();
    } finally {
        lastTickMs = Date.now() - started;
        if (lastTickMs > maxTickMs) maxTickMs = lastTickMs;
        sendHeartbeat();
    }
}

/** Proof of life for the host's freeze watchdog, with what the agent was
 *  doing: tick cost and the last heap walk. Field reads and one send. */
function sendHeartbeat(): void {
    const now = Date.now();
    if (now < heartbeatAfter) return;
    heartbeatAfter = now + (matchActive ? HEARTBEAT_ACTIVE_MS : HEARTBEAT_IDLE_MS);
    send({
        type: "heartbeat",
        match_active: matchActive,
        tick_ms: lastTickMs,
        max_tick_ms: maxTickMs,
        poll_milliseconds: matchActive ? pollMilliseconds : idleMilliseconds,
        chooses: chooseCount,
        last_choose_why: lastChooseWhy,
        last_choose_ms: lastChooseMs,
        last_choose_ago_ms: lastChooseAt == null ? null : now - lastChooseAt,
        constructed: constructedCount,
        disposed: disposedCount,
        resolve_by_hook: resolveByHook,
        resolve_by_choose: resolveByChoose,
        deferred_resolves: deferredResolves,
    });
    maxTickMs = 0;
}

function tickBody(): void {
    if (!matchActive) {
        idleOnce();
        return;
    }
    pollOnce();
    // The counter is only read on the idle tick, so a match that never
    // reported its end (a concede this agent no longer hooks, a leftover in an
    // in-match state) would hide the next match's start for good. GameCount
    // is a static field read, exact and free: a rise during a match IS the
    // next match, so this one is over.
    const count = readGameCount();
    if (count != null && lastGameCount != null && count > lastGameCount) {
        quietSignature = null;
        setMatchActive(false, "nova partija je pocela");
        return;
    }
    const ended = matchEnded();
    if (ended == null) return;
    // An engine that says the game is over leaves a finished state behind,
    // and stateIsFinished keeps that logic out of every later resolve. Every
    // other end (concede, abandoned, quiet, unreadable) leaves the logic in an
    // in-match state, so reopening on it must mean the board actually moved:
    // that is what the signature is kept for.
    quietSignature = ended === "partija zavrsena" ? null : lastSentSignature;
    setMatchActive(false, ended);
}

function startPolling(): void {
    if (pollTimer != null) clearInterval(pollTimer);
    const interval = matchActive ? pollMilliseconds : idleMilliseconds;
    pollTimer = setInterval(() => Il2Cpp.perform(tick), interval);
}

function performAsync<T>(block: () => T): Promise<T> {
    return new Promise((resolve, reject) => {
        Il2Cpp.perform(() => {
            try { resolve(block()); } catch (error) { reject(error); }
        });
    });
}

// --- Match profile -----------------------------------------------------------
// What tools/capture_match.py reads with its own agent (spawn weights, refill
// and score overrides, gameColors, the engine RNG), read here by the agent the
// GUI is already attached with, so nothing has to be closed first. Same rule as
// the capture's profileReader: field loads and array/list/dictionary backing
// stores only, never a managed method, bounded by a node budget.

// Config subtrees that are catalogs, not this match's spawn tuning: they make
// up most of a capture's size and the host has them elsewhere.
const PROFILE_CONFIG_SKIP = new Set([
    "boardControl", "slotControl", "specialAbilities", "specialPieces",
    "boardAbilities", "entryTicket", "mutationLab",
]);
// Never walked: back-references into the match and the account's player data.
const PROFILE_REFERENCE_ONLY = new Set([
    "Match3Engine.GameLogic", "Match3Engine.PlayerControl", "Match3Engine.PlayerModel",
]);
const PROFILE_PRIMITIVES: Record<string, (handle: NativePointer) => number | boolean> = {
    "System.Int32": (h) => h.readS32(),
    "System.UInt32": (h) => h.readU32(),
    "System.Int16": (h) => h.readS16(),
    "System.UInt16": (h) => h.readU16(),
    "System.Byte": (h) => h.readU8(),
    "System.SByte": (h) => h.readS8(),
    "System.Boolean": (h) => h.readU8() !== 0,
    "System.Single": (h) => h.readFloat(),
    "System.Double": (h) => h.readDouble(),
    "System.Int64": (h) => Number(h.readS64()),
    "System.UInt64": (h) => Number(h.readU64()),
};

function profileReader(budget: number = 50000) {
    let remaining = budget;
    const issues: any[] = [];
    const active = new Set<string>();
    function problem(path: string, reason: string): any {
        issues.push({ path, reason });
        return { unresolved: reason };
    }
    function value(raw: any, path: string, depth = 0): any {
        if (--remaining < 0) return problem(path, "node budget");
        if (raw == null || typeof raw === "number" || typeof raw === "boolean" || typeof raw === "string") return raw;
        if (depth > 32) return problem(path, "depth budget");
        if (raw instanceof Int64 || raw instanceof UInt64) return raw.toNumber();
        if (raw.handle != null && raw.handle.isNull()) return null;
        if (raw instanceof Il2Cpp.String) return raw.content;
        if (raw instanceof Il2Cpp.Array) raw = raw.object;
        const klass = raw instanceof Il2Cpp.ValueType ? raw.type.class : raw.class;
        if (klass == null) return problem(path, "unknown runtime value");
        const type = String(klass.type.name);
        if (klass.isEnum) return value(raw.field("value__").value, path, depth + 1);
        // A boxed primitive (an `object`-typed field): the value sits after the
        // 0x10 object header.
        const primitive = PROFILE_PRIMITIVES[type];
        if (primitive != null && !(raw instanceof Il2Cpp.ValueType)) return primitive(raw.handle.add(0x10));
        if (type === "System.String") return asText(raw);
        const identity = type + ":" + raw.handle;
        if (active.has(identity)) return { reference_type: type };
        active.add(identity);
        try {
            if (type.endsWith("[]") || type.includes("[,]")) {
                const array = new Il2Cpp.Array(raw.handle);
                if (array.length > 4096) return problem(path, "array length " + array.length);
                const out: any[] = [];
                for (let i = 0; i < array.length; i++) out.push(value(array.get(i), path + "[" + i + "]", depth + 1));
                return out;
            }
            if (type.startsWith("System.Collections.Generic.List<")) {
                const size = Number(fieldValue(raw, "_size"));
                if (!Number.isInteger(size) || size < 0 || size > 4096) return problem(path, "invalid list size");
                return listItemsByField(raw, 4096).map((item, i) => value(item, path + "[" + i + "]", depth + 1));
            }
            if (type.startsWith("System.Collections.Generic.Dictionary<")) {
                let count = Number(fieldValue(raw, "_count"));
                if (!Number.isFinite(count)) count = Number(fieldValue(raw, "count"));
                if (!Number.isInteger(count) || count < 0 || count > 4096) return problem(path, "invalid dictionary count");
                if (count === 0) return { entries: [] };
                const entries = fieldValue(raw, "_entries") ?? fieldValue(raw, "entries");
                if (entries == null) return problem(path, "dictionary entries missing");
                const array = new Il2Cpp.Array(entries.handle);
                if (count > array.length) return problem(path, "dictionary count exceeds capacity");
                const out: any[] = [];
                for (let i = 0; i < count; i++) {
                    const entry = array.get(i) as any;
                    // Freed slots: hashCode < 0 (Mono) or next < -1 (CoreCLR).
                    if (Number(fieldValue(entry, "hashCode") ?? 0) < 0) continue;
                    if (Number(fieldValue(entry, "next") ?? 0) < -1) continue;
                    out.push({ key: value(entry.field("key").value, path + ".key" + i, depth + 1),
                               value: value(entry.field("value").value, path + ".value" + i, depth + 1) });
                }
                return { entries: out };
            }
            // Booster logics keep allowed/blocked piece types in sets
            // (SpecialPiecesLogic.AllowedMergeSwapWithType 0x5ae0844 reads two).
            // Mono: _slots up to _lastIndex, a freed slot has hashCode < 0;
            // CoreCLR: _entries up to _count, a freed one has next < -1.
            if (type.startsWith("System.Collections.Generic.HashSet<")) {
                const count = Number(fieldValue(raw, "_count") ?? fieldValue(raw, "count"));
                if (!Number.isInteger(count) || count < 0 || count > 4096) return problem(path, "invalid set count");
                if (count === 0) return { items: [] };
                const slots = fieldValue(raw, "_slots") ?? fieldValue(raw, "_entries") ?? fieldValue(raw, "entries");
                if (slots == null) return problem(path, "set slots missing");
                const array = new Il2Cpp.Array(slots.handle);
                const last = Number(fieldValue(raw, "_lastIndex") ?? count);
                if (!Number.isInteger(last) || last < 0 || last > array.length) return problem(path, "set index exceeds capacity");
                const out: any[] = [];
                for (let i = 0; i < last; i++) {
                    const slot = array.get(i) as any;
                    if (Number(fieldValue(slot, "hashCode") ?? 0) < 0) continue;
                    if (Number(fieldValue(slot, "next") ?? 0) < -1) continue;
                    out.push(value(slot.field("value").value, path + "[" + i + "]", depth + 1));
                }
                return { items: out };
            }
            if (!type.startsWith("Match3Engine.") && !type.startsWith("System.Nullable<") && !type.startsWith("FixMath.")
                && !type.startsWith("FroggyFuLotusPlacementPlanner")) {
                return problem(path, "unsupported type " + type);
            }
            if (PROFILE_REFERENCE_ONLY.has(type)) return { reference_type: type };
            return fields(raw, path, depth + 1);
        } catch (error) {
            return problem(path, String(error));
        } finally {
            active.delete(identity);
        }
    }
    function fields(object: any, path: string, depth = 0, skip?: Set<string>): any {
        const out: any = {};
        let klass = object instanceof Il2Cpp.ValueType ? object.type.class : object.class;
        while (klass != null && klass.type.name !== "System.Object" && klass.type.name !== "System.ValueType") {
            for (const f of klass.fields) {
                if (f.isStatic || f.isLiteral || (skip != null && skip.has(f.name))) continue;
                const typeName = String(f.type.name);
                if (typeName.startsWith("System.Action") || typeName.startsWith("System.Func") || typeName.includes("Callback")) continue;
                try { out[f.name] = value(object.field(f.name).value, path + "." + f.name, depth + 1); }
                catch (error) { out[f.name] = problem(path + "." + f.name, String(error)); }
            }
            klass = klass.parent;
        }
        return out;
    }
    return { value, fields, issues };
}

// Read once per GameLogic: rules, config and spawn tuning are fixed for the
// match. The RNG and the spawn engine's running state are re-read on demand.
let cachedProfileKey: string | null = null;
let cachedProfileStatic: Record<string, any> | null = null;
let mixyTraceArmed = false;
// "Snimaj svaki potez" (research_recorder.record): the whole booster state on
// every resting board, for porting boosters the profile does not cover yet.
// Off for the bot's own per-move reads, which stay as light as before.
let boosterDetailArmed = false;
let mixyTraceListeners: InvocationListener[] = [];
let mixyTraceError: string | null = null;
let mixyTraceAbility: NativePointer | null = null;
let mixyTraceLogic: NativePointer | null = null;
let mixyTracePending: Record<string, any> | null = null;
const mixyTraceHistory: Record<string, any>[] = [];
const mixyRefillHistory: Record<string, any>[] = [];
let jellyTraceListeners: InvocationListener[] = [];
let jellyTraceError: string | null = null;
let jellyTraceAbility: NativePointer | null = null;
let jellyTraceActive: Record<string, any> | null = null;
const jellyTraceHistory: Record<string, any>[] = [];

function mixyTraceCounter(logic: any): number {
    return ruleFieldValue(fieldValue(logic, "<Random>k__BackingField"), "<counter>k__BackingField");
}

function refillTraceGrid(board: any): any[][] {
    const rows = asNumber(fieldValue(board, "<Rows>k__BackingField"));
    const columns = asNumber(fieldValue(board, "<Columns>k__BackingField"));
    if (rows < 4 || rows > 12 || columns < 4 || columns > 12) throw new Error("invalid Mixy trace board");
    const slots = board.handle.add(EXPECTED_OFFSETS["BoardModel.slots"]).readPointer();
    const cells = slots.add(Il2Cpp.Array.headerSize);
    return Array.from({ length: rows }, (_, y) => Array.from({ length: columns }, (_, x) => {
        const pointer = cells.add((x * rows + y) * Process.pointerSize).readPointer();
        if (pointer.isNull()) return null;
        const slot = new Il2Cpp.Object(pointer);
        return [asNumber(readSlotField(slot, "color")), asNumber(readSlotField(slot, "value")),
            readBoolean(slot, "canBeMatched")];
    }));
}

function mixyTraceFrame(logic: any, ability: any, board: any): Record<string, any> {
    const rng = fieldValue(logic, "<Random>k__BackingField");
    return {
        rng_counter: ruleFieldValue(rng, "<counter>k__BackingField"),
        rng_index: ruleFieldValue(rng, "_index"),
        active_colors: intListValues(fieldValue(ability, "activeColors")),
        target_color: ruleFieldValue(ability, "TargetColor"),
        moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
        grid: refillTraceGrid(board),
    };
}

// ---- Swap trace ("Snimaj svaki potez") --------------------------------------
// What the engine does inside one played move, in order, each with the RNG
// counter: the merge outcome of a special+special swap, every special's area
// (GetAreaOfEffectByPiece), every destroy pass and every Lightning's picks.
// Read-only hooks; only the live board of the cached GameLogic is recorded,
// never the planner's or the hint search's copies.
let swapTraceListeners: InvocationListener[] = [];
let swapTraceError: string | null = null;
let swapTraceActive: Record<string, any> | null = null;
let swapTraceInSwap: number | null = null;
const swapTraceHistory: Record<string, any>[] = [];
const SWAP_TRACE_EVENT_LIMIT = 400;

function tracePoint(raw: NativePointer): number[] {
    // Match3Engine.Point {int x; int y} travels packed in one register.
    const value = uint64(raw.toString());
    return [value.and(0xffffffff).toNumber() | 0, value.shr(32).and(0xffffffff).toNumber() | 0];
}

function swapTraceGrid(board: any): any[][] {
    const rows = asNumber(fieldValue(board, "<Rows>k__BackingField"));
    const columns = asNumber(fieldValue(board, "<Columns>k__BackingField"));
    if (rows < 4 || rows > 12 || columns < 4 || columns > 12) throw new Error("invalid swap trace board");
    const slots = board.handle.add(EXPECTED_OFFSETS["BoardModel.slots"]).readPointer();
    const cells = slots.add(Il2Cpp.Array.headerSize);
    return Array.from({ length: rows }, (_, y) => Array.from({ length: columns }, (_, x) => {
        const pointer = cells.add((x * rows + y) * Process.pointerSize).readPointer();
        if (pointer.isNull()) return null;
        const slot = new Il2Cpp.Object(pointer);
        return [asNumber(readSlotField(slot, "color")), asNumber(readSlotField(slot, "color2")),
            asNumber(readSlotField(slot, "value"))];
    }));
}

function swapTraceEvent(type: string, fields: Record<string, any>): void {
    const trace = swapTraceActive;
    if (trace == null) return;
    if (trace.events.length >= SWAP_TRACE_EVENT_LIMIT) {
        trace.truncated = true;
        return;
    }
    trace.events.push({ type, ...fields });
}

function swapTraceCounter(): number | null {
    const trace = swapTraceActive;
    return trace == null ? null : mixyTraceCounter(trace.logic);
}

function liveBoard(board: NativePointer): boolean {
    const trace = swapTraceActive;
    return trace != null && trace.board.handle.equals(board);
}

function slotSummary(raw: NativePointer): any {
    if (raw.isNull()) return null;
    const slot = new Il2Cpp.Object(raw);
    return { color: asNumber(readSlotField(slot, "color")), color2: asNumber(readSlotField(slot, "color2")),
             value: asNumber(readSlotField(slot, "value")) };
}

function installSwapTrace(): void {
    if (swapTraceListeners.length || swapTraceError != null) return;
    const listeners: InvocationListener[] = [];
    try {
        const image = findAssemblyImage();
        const analyzer = image.class("Match3Engine.BoardAnalyzer");
        const address = (klass: any, name: string, count: number): NativePointer => {
            const pointer = klass.method(name, count).virtualAddress;
            if (pointer.isNull()) throw new Error("swap trace: " + name + " address missing");
            return pointer;
        };
        const swap = address(image.class("Match3Engine.GameLogic"), "ValidSwapPerformed", 5);
        const merge = address(analyzer, "GetMergeSwapOutcome", 4);
        const area = address(analyzer, "GetAreaOfEffectByPiece", 5);
        const destroy = address(analyzer, "GetAreaOfEffectDestructionSlots", 5);
        const fireworks = address(image.class("Match3Engine.BoardModel"), "GetFireworks", 4);
        listeners.push(Interceptor.attach(swap, {
            onEnter(args): void {
                if (!boosterDetailArmed || cachedGameLogic == null || !cachedGameLogic.handle.equals(args[0])) return;
                try {
                    const logic = new Il2Cpp.Object(args[0]);
                    const board = boardObject(logic);
                    swapTraceActive = {
                        logic, board, logic_key: String(args[0]), events: [],
                        position1: tracePoint(args[1]), position2: tracePoint(args[2]),
                        is_player_move: (args[3].toInt32() & 1) === 1,
                        before_rng_counter: mixyTraceCounter(logic),
                        moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
                        grid: swapTraceGrid(board),
                    };
                    swapTraceHistory.push(swapTraceActive);
                    if (swapTraceHistory.length > 4) swapTraceHistory.shift();
                    swapTraceInSwap = this.threadId;
                    this.swapTraceOpen = true;
                } catch (error) {
                    swapTraceError = String(error);
                }
            },
            onLeave(): void {
                if (this.swapTraceOpen) swapTraceInSwap = null;
            },
        }));
        listeners.push(Interceptor.attach(merge, {
            onEnter(args): void {
                // Hint and valid-move scans ask the same question of the live
                // board; only the call inside the played swap is the outcome.
                if (!liveBoard(args[0]) || swapTraceInSwap !== this.threadId) return;
                this.swapMerge = { source: tracePoint(args[1]), target: tracePoint(args[2]),
                                   is_after_swap: (args[3].toInt32() & 1) === 1, rng: swapTraceCounter() };
            },
            onLeave(result): void {
                const call = this.swapMerge;
                if (call == null) return;
                try {
                    call.outcome = result.isNull() ? null
                        : profileReader(2000).fields(new Il2Cpp.Object(result), "swap_trace.merge");
                    swapTraceEvent("merge_outcome", call);
                } catch (error) {
                    swapTraceEvent("merge_outcome", { ...call, unresolved: String(error) });
                }
            },
        }));
        listeners.push(Interceptor.attach(area, {
            onEnter(args): void {
                if (!liveBoard(args[1])) return;
                try {
                    this.swapArea = { piece: slotSummary(args[2]), position: tracePoint(args[3]),
                                      rng_before: swapTraceCounter() };
                } catch (error) {
                    this.swapArea = { unresolved: String(error) };
                }
            },
            onLeave(result): void {
                const call = this.swapArea;
                if (call == null) return;
                try {
                    call.cells = result.isNull() ? null : pointListValues(new Il2Cpp.Object(result), 128);
                    call.rng_after = swapTraceCounter();
                } catch (error) {
                    call.unresolved = String(error);
                }
                swapTraceEvent("piece_area", call);
            },
        }));
        listeners.push(Interceptor.attach(destroy, {
            onEnter(args): void {
                if (!liveBoard(args[0])) return;
                try {
                    this.swapDestroy = { positions: args[1].isNull() ? null
                                             : pointListValues(new Il2Cpp.Object(args[1]), 128),
                                         rng_before: swapTraceCounter() };
                } catch (error) {
                    this.swapDestroy = { unresolved: String(error) };
                }
            },
            onLeave(): void {
                const call = this.swapDestroy;
                if (call == null) return;
                call.rng_after = swapTraceCounter();
                swapTraceEvent("destroy_pass", call);
            },
        }));
        listeners.push(Interceptor.attach(fireworks, {
            onEnter(args): void {
                if (!liveBoard(args[0])) return;
                try {
                    this.swapFireworks = { amount: args[1].toInt32(), position: tracePoint(args[2]),
                                           ignore: args[3].isNull() ? null
                                               : pointListValues(new Il2Cpp.Object(args[3]), 128),
                                           rng_before: swapTraceCounter() };
                } catch (error) {
                    this.swapFireworks = { unresolved: String(error) };
                }
            },
            onLeave(result): void {
                const call = this.swapFireworks;
                if (call == null) return;
                try {
                    call.picks = result.isNull() ? null : pointListValues(new Il2Cpp.Object(result), 128);
                    call.rng_after = swapTraceCounter();
                } catch (error) {
                    call.unresolved = String(error);
                }
                swapTraceEvent("fireworks", call);
            },
        }));
        swapTraceListeners = listeners;
    } catch (error) {
        for (const listener of listeners) listener.detach();
        swapTraceError = String(error);
    }
}

function installJellyTrace(): void {
    if (jellyTraceListeners.length || jellyTraceError != null) return;
    const listeners: InvocationListener[] = [];
    try {
        const image = findAssemblyImage();
        const fresh = image.class("Match3Engine.JellySE").method("SetFreshJellies", 2).virtualAddress;
        const search = image.class("Match3Engine.JellySEPointsFinder").nested("ImprovedFinder")
            .method("ImprovedSearch", 5).virtualAddress;
        if (fresh.isNull() || search.isNull()) throw new Error("Jelly trace method address missing");
        listeners.push(Interceptor.attach(fresh, {
            onEnter(args): void {
                if (args[2].toInt32() !== 0 || !jellyTraceAbility?.equals(args[0])
                    || !cachedGameLogic?.handle.equals(args[1])) return;
                const logic = new Il2Cpp.Object(args[1]);
                try {
                    const trace = {
                        logic_key: String(args[1]), thread_id: this.threadId,
                        before_rng_counter: mixyTraceCounter(logic),
                        moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
                        grid: refillTraceGrid(boardObject(logic)),
                    };
                    jellyTraceActive = trace;
                    this.jellyTrace = { logic, trace };
                } catch (error) {
                    jellyTraceError = String(error);
                }
            },
            onLeave(): void {
                const current = this.jellyTrace;
                if (current == null) return;
                jellyTraceActive = null;
                try {
                    current.trace.after_rng_counter = mixyTraceCounter(current.logic);
                    jellyTraceHistory.push(current.trace);
                    if (jellyTraceHistory.length > 8) jellyTraceHistory.shift();
                } catch (error) {
                    jellyTraceError = String(error);
                }
            },
        }));
        listeners.push(Interceptor.attach(search, {
            onEnter(args): void {
                const trace = jellyTraceActive;
                if (trace == null || trace.thread_id !== this.threadId || trace.logic_key !== String(args[2])) return;
                try {
                    const logic = new Il2Cpp.Object(args[2]);
                    trace.search_rng_counter = mixyTraceCounter(logic);
                    trace.search_config = readAllInstanceFields(new Il2Cpp.Object(args[5]));
                    this.jellySearchTrace = trace;
                } catch (error) {
                    jellyTraceError = String(error);
                }
            },
            onLeave(result): void {
                const trace = this.jellySearchTrace;
                if (trace == null || result.isNull()) return;
                try {
                    const tuple = new Il2Cpp.Object(result);
                    trace.selected_points = pointListValues(
                        fieldValue(tuple, "m_Item1") ?? fieldValue(tuple, "Item1"));
                } catch (error) {
                    jellyTraceError = String(error);
                }
            },
        }));
        jellyTraceListeners = listeners;
    } catch (error) {
        for (const listener of listeners) listener.detach();
        jellyTraceError = String(error);
    }
}

function installMixyTrace(): void {
    if (mixyTraceListeners.length || mixyTraceError != null) return;
    const listeners: InvocationListener[] = [];
    try {
        const image = findAssemblyImage();
        const redeal = image.class("Match3Engine.MixyMeow").method("RandomizeActiveColors", 1).virtualAddress;
        const refill = image.class("Match3Engine.SpawningEngine").method("FillAllEmptySlots", 5).virtualAddress;
        if (redeal.isNull() || refill.isNull()) throw new Error("Mixy trace method address missing");
        listeners.push(Interceptor.attach(redeal, {
            onEnter(args): void {
                if (!mixyTraceArmed || !mixyTraceAbility?.equals(args[0]) || !mixyTraceLogic?.equals(args[1])) return;
                mixyTracePending = null;
                try {
                    const logic = new Il2Cpp.Object(args[1]);
                    const ability = new Il2Cpp.Object(args[0]);
                    this.mixyTrace = {
                        logic, ability, record: {
                            logic_key: String(args[1]),
                            before_redeal: mixyTraceFrame(logic, ability, boardObject(logic)),
                            preceding_refills: mixyRefillHistory.filter(
                                refill => refill.logic_key === String(args[1])).slice(-8),
                        },
                    };
                } catch (error) {
                    mixyTraceError = String(error);
                }
            },
            onLeave(): void {
                const trace = this.mixyTrace;
                if (trace == null) return;
                try {
                    trace.record.after_redeal = mixyTraceFrame(trace.logic, trace.ability, boardObject(trace.logic));
                    mixyTraceHistory.push(trace.record);
                    if (mixyTraceHistory.length > 8) mixyTraceHistory.shift();
                    mixyTracePending = trace.record;
                } catch (error) {
                    mixyTraceError = String(error);
                }
            },
        }));
        listeners.push(Interceptor.attach(refill, {
            onEnter(args): void {
                if (!mixyTraceLogic?.equals(args[1]) || mixyTraceAbility == null) return;
                try {
                    const logic = new Il2Cpp.Object(args[1]);
                    const board = boardObject(logic);
                    if (!board.handle.equals(args[2])) return;
                    this.mixyRefill = { logic, frame: {
                        logic_key: String(args[1]),
                        before_rng_counter: mixyTraceCounter(logic),
                        moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
                        chain_reaction: Boolean(args[4].toInt32()),
                    } };
                    const trace = mixyTracePending;
                    if (trace != null) {
                        mixyTracePending = null;
                        trace.before_refill = mixyTraceFrame(logic, new Il2Cpp.Object(mixyTraceAbility), board);
                    }
                } catch (error) {
                    mixyTraceError = String(error);
                }
            },
            onLeave(): void {
                const refill = this.mixyRefill;
                if (refill == null) return;
                try {
                    refill.frame.after_rng_counter = mixyTraceCounter(refill.logic);
                    mixyRefillHistory.push(refill.frame);
                    if (mixyRefillHistory.length > 16) mixyRefillHistory.shift();
                } catch (error) {
                    mixyTraceError = String(error);
                }
            },
        }));
        mixyTraceListeners = listeners;
    } catch (error) {
        for (const listener of listeners) listener.detach();
        mixyTraceError = String(error);
    }
}

// GameLogic.specialPiecesLogics (+0xf0) owns the live logic, including the
// Cleo overrides (+0xb8/+0xbc). Do not call GetSpecialPiecesLogic/getters:
// read Dictionary backing storage and preserve unresolved reads explicitly.
function readCleoPieceLogic(logic: any, reader: ReturnType<typeof profileReader>): any {
    const all = readPieceLogics(logic, reader, 32);
    if (all == null || !Array.isArray(all)) return all;
    return all.length === 0 ? null : all[0].fields;
}

// Every live SpecialPiecesLogic (CupidHeart 23, Cleo 32, ...) with its class
// and fields; `onlyKey` limits the read to one SlotValueType.
function readPieceLogics(logic: any, reader: ReturnType<typeof profileReader>, onlyKey?: number): any {
    try {
        const dictionary = fieldValue(logic, "specialPiecesLogics");
        if (dictionary == null) return null;
        const count = Number(fieldValue(dictionary, "_count") ?? fieldValue(dictionary, "count"));
        if (!Number.isInteger(count) || count < 0 || count > 4096) {
            return { unresolved: "invalid specialPiecesLogics count" };
        }
        if (count === 0) return [];
        const entries = fieldValue(dictionary, "_entries") ?? fieldValue(dictionary, "entries");
        if (entries == null) return { unresolved: "specialPiecesLogics entries missing" };
        const array = new Il2Cpp.Array(entries.handle);
        if (count > array.length) return { unresolved: "specialPiecesLogics count exceeds capacity" };
        const out: any[] = [];
        for (let i = 0; i < count; i++) {
            const entry = array.get(i);
            if (Number(fieldValue(entry, "hashCode") ?? 0) < 0 || Number(fieldValue(entry, "next") ?? 0) < -1) continue;
            const key = ruleFieldValue(entry, "key");
            if (onlyKey != null && key !== onlyKey) continue;
            const piece = fieldValue(entry, "value");
            if (piece == null) continue;
            const path = onlyKey === 32 ? "cleo_piece_logic" : "special_pieces_logics." + key;
            out.push({ key, class: String(piece.class.type.name), fields: reader.fields(piece, path) });
            if (onlyKey != null) break;
        }
        return out;
    } catch (error) {
        return { unresolved: String(error) };
    }
}

function readMatchProfile(withStatic: boolean): Record<string, any> {
    if (!matchActive) throw new Error("no active match");
    const logic = resolveGameLogic();
    const key = String(logic.handle);
    const reader = profileReader();
    const rng = fieldValue(logic, "<Random>k__BackingField");
    const counterBefore = fieldValue(rng, "<counter>k__BackingField");
    const result: Record<string, any> = {
        schema_version: 1,
        logic_key: key,
        rules_id: asText(fieldValue(fieldValue(logic, "gameRules"), "id")),
        rng: rng == null ? null : reader.fields(rng, "rng"),
        spawning: reader.value(fieldValue(logic, "spawningEngine"), "spawning"),
        // Dynamic reads: PieceUsesThisTurn 0x5ae429c reads board.extraData;
        // the loaded Cleo config/overrides can change during a match.
        cleo_piece_logic: readCleoPieceLogic(logic, reader),
        board_extra_data: reader.value(fieldValue(fieldValue(logic, "board"), "extraData"), "board_extra_data"),
        cleo_booster_fields: (() => {
            const local = listItemsByField(fieldValue(logic, "players")).find(
                (control: any) => ruleFieldValue(control, "<Type>k__BackingField") === 0);
            const ability = fieldValue(local, "ability");
            return ability != null && String(ability.class.type.name) === "Match3Engine.CleoCadabra"
                ? reader.fields(ability, "cleo_booster_fields") : null;
        })(),
        // Configuration and this activation's rolls (rolledPreferredColorThisActivation,
        // plannedLotusPositionsThisActivation, cachedSwapResolution). Field reads only;
        // animation timings, the planner object and the player reference add nothing.
        froggy_booster_fields: (() => {
            const local = listItemsByField(fieldValue(logic, "players")).find(
                (control: any) => ruleFieldValue(control, "<Type>k__BackingField") === 0);
            const ability = fieldValue(local, "ability");
            if (ability == null || String(ability.class.type.name) !== "Match3Engine.FroggyFu") return null;
            const skip = new Set<string>(["_froggyFuAttractionPlanner", "player"]);
            for (const field of ability.class.fields) {
                if (String(field.name).startsWith("anim")) skip.add(String(field.name));
            }
            return reader.fields(ability, "froggy_booster_fields", 0, skip);
        })(),
        // SpecialAbility.get_ActivatesThisTurn 0x5ad91c8: a plain Int32 on
        // PlayerModel, not an ability method invocation or a remaining-use estimate.
        cleo_activates_this_turn: (() => {
            const local = listItemsByField(fieldValue(logic, "players")).find(
                (control: any) => ruleFieldValue(control, "<Type>k__BackingField") === 0);
            const model = fieldValue(local, "model");
            return model == null ? null : ruleFieldValue(model, "specialAbilityUsedThisTurn");
        })(),
        state: reader.fields(logic, "state", 0, new Set(
            logic.class.fields.map((f: any) => String(f.name)).filter((name: string) => ![
                "moves", "currentPlayerIndex", "currentGameState", "<GameIndex>k__BackingField",
                "<ChainReaction>k__BackingField", "<Turns>k__BackingField", "<TurnsTotal>k__BackingField",
                "<MovesMadeThisTurn>k__BackingField",
            ].includes(name)),
        )),
        // Game numbers only, the same allow-list as the capture agent: the
        // account's ids and name live on PlayerModel too and are never read.
        players: listItemsByField(fieldValue(logic, "players")).map((control: any, i: number) => {
            const model = fieldValue(control, "model");
            return {
                player_type: ruleFieldValue(control, "<Type>k__BackingField"),
                model: model == null ? null : reader.fields(model, "players." + i, 0, new Set(
                    model.class.fields.map((f: any) => String(f.name)).filter((name: string) => ![
                        "index", "score", "spawnBonus", "slotType", "energy", "boardAbilities", "specialAbilityType",
                        "scoreMultiplier", "soloScoreTargetInd",
                    ].includes(name)),
                )),
            };
        }),
    };
    if (mixyTraceArmed) {
        const local = listItemsByField(fieldValue(logic, "players")).find(
            (control: any) => ruleFieldValue(control, "<Type>k__BackingField") === 0);
        const ability = fieldValue(local, "ability");
        mixyTraceLogic = logic.handle;
        mixyTraceAbility = ability != null && String(ability.class.type.name) === "Match3Engine.MixyMeow"
            ? ability.handle : null;
        if (mixyTraceAbility != null) installMixyTrace();
        jellyTraceAbility = ability != null && String(ability.class.type.name) === "Match3Engine.JellySE"
            ? ability.handle : null;
        if (jellyTraceAbility != null) installJellyTrace();
        result.mixy_redeal_trace = mixyTraceHistory.filter(trace => trace.logic_key === key);
        if (mixyTraceError != null) result.mixy_redeal_trace_error = mixyTraceError;
        result.jelly_renewal_trace = jellyTraceHistory.filter(trace => trace.logic_key === key);
        if (jellyTraceError != null) result.jelly_renewal_trace_error = jellyTraceError;
    }
    if (boosterDetailArmed) {
        // Own reader: a large booster must not use up the profile's node budget.
        const detail = profileReader();
        const local = listItemsByField(fieldValue(logic, "players")).find(
            (control: any) => ruleFieldValue(control, "<Type>k__BackingField") === 0);
        const ability = fieldValue(local, "ability");
        let abilityDetail: any = null;
        if (ability != null) {
            // The player link and animation timings say nothing about the board.
            const skip = new Set<string>(["player"]);
            for (const field of ability.class.fields) {
                if (String(field.name).startsWith("anim")) skip.add(String(field.name));
            }
            try {
                abilityDetail = { class: String(ability.class.type.name),
                                  fields: detail.fields(ability, "ability_detail", 0, skip) };
            } catch (error) {
                abilityDetail = { unresolved: String(error) };
            }
        }
        result.ability_detail = abilityDetail;
        result.special_pieces_logics = readPieceLogics(logic, detail);
        result.detail_issues = detail.issues;
        // The last move played on this GameLogic, as the engine resolved it.
        installSwapTrace();
        const last = [...swapTraceHistory].reverse().find(trace => trace.logic_key === key);
        if (last != null) {
            const { logic: _logic, board: _board, ...plain } = last;
            result.swap_trace = { ...plain, events: [...last.events] };
        }
        if (swapTraceError != null) result.swap_trace_error = swapTraceError;
    }
    const staticChanged = key !== cachedProfileKey;
    if (withStatic || staticChanged) {
        const config = fieldValue(logic, "<configData>k__BackingField");
        cachedProfileStatic = {
            rules: reader.value(fieldValue(logic, "gameRules"), "rules"),
            config: config == null ? null : reader.fields(config, "config", 0, PROFILE_CONFIG_SKIP),
        };
        cachedProfileKey = key;
        Object.assign(result, cachedProfileStatic);
    }
    result.issues = reader.issues;
    // The poll thread and this read share the game's thread through perform(),
    // so a move landing mid-read shows up as a moved RNG counter.
    result.consistent = counterBefore === fieldValue(rng, "<counter>k__BackingField");
    return result;
}

rpc.exports = {
    armMixyTrace(): Promise<void> {
        return performAsync(() => { mixyTraceArmed = true; });
    },
    /** "Snimaj svaki potez": add ability_detail and special_pieces_logics to matchProfile. */
    armBoosterDetail(on: boolean): Promise<void> {
        return performAsync(() => { boosterDetailArmed = Boolean(on); });
    },
    /** This match's spawn weights, refill/score overrides, gameColors and RNG.
     *
     *  `full` re-sends the per-match part (rules + config) even when it was
     *  already sent for this GameLogic; otherwise only the first call of a
     *  match carries it. Field reads only, see profileReader. */
    matchProfile(full?: boolean): Promise<any> {
        return performAsync(() => readMatchProfile(Boolean(full)));
    },
    /** What one heap walk actually costs, without opening the poll.
     *
     *  `resolveGameLogic` is the only expensive thing the agent does: outside
     *  a match nothing is cached, so every call pays a full
     *  `Il2Cpp.gc.choose` over the IL2CPP heap. This measures that cost in
     *  the lobby and in a match, plus the cost of one whole snapshot, so the
     *  idle poll interval is chosen from numbers rather than from a guess. */
    probe(withSnapshot?: boolean): Promise<any> {
        return performAsync(() => {
            const result: Record<string, any> = {
                ready,
                cached: cachedGameLogic != null,
                cached_valid: cachedGameLogic != null && hasBoard(cachedGameLogic),
            };
            // The candidate for a cheap "is a match running" gate. GameCount is
            // a *static* field, so reading it is a fixed-address memory read
            // with no heap walk at all -- if it ticks per match, the agent can
            // sit in the lobby for free and only walk the heap when it moves.
            const staticStart = Date.now();
            try {
                const field = gameLogicClass == null
                    ? null
                    : gameLogicClass.tryField<any>("GameCount");
                result.game_count = field == null ? null : asNumber(field.value);
            } catch (error) {
                result.game_count_error = String(error);
            }
            result.static_read_ms = Date.now() - staticStart;
            // Measured cold: whatever the previous call cached says nothing
            // about what an idle attach pays. The cache is restored afterwards
            // so a diagnostic call cannot cost the running match a heap walk.
            const previousCache = cachedGameLogic;
            cachedGameLogic = null;
            const chooseStart = Date.now();
            let instances: Il2Cpp.Object[] = [];
            try {
                instances = gameLogicClass == null ? [] : chooseInstances(gameLogicClass, "probe");
                result.choose_ms = Date.now() - chooseStart;
                result.instances = instances.length;
                const active = instances.filter(hasBoard);
                result.active = active.length;
                result.in_match = active.length > 0;
                if (active.length > 0) {
                    cachedGameLogic = active[active.length - 1];
                    // What the lobby instance looks like versus a live one.
                    // `hasBoard` alone says "match" in the lobby too, so the
                    // real discriminator has to come from these.
                    const logic = cachedGameLogic;
                    const readField = (name: string): any => {
                        try {
                            const field = logic.tryField<any>(name);
                            return field == null ? null : asNumber(field.value);
                        } catch (_) {
                            return null;
                        }
                    };
                    // Both readings: the field accessor is what measured as
                    // -1/-3/-5/-7, the native read at the known offset is what
                    // the match gate actually uses.
                    result.game_state_field = readField("currentGameState");
                    result.game_state = readGameStateEnum(logic);
                    result.moves = readField("moves");
                    result.turns = readField("<Turns>k__BackingField");
                    result.turns_total = readField("<TurnsTotal>k__BackingField");
                    result.current_player = readField("currentPlayerIndex");
                    result.game_index = readField("<GameIndex>k__BackingField");
                    try {
                        const players = logic.tryField<any>("players");
                        const value = players == null ? null : players.value;
                        result.players = value == null || value.isNull?.()
                            ? null
                            : asNumber(value.field("_size").value);
                    } catch (_) {
                        result.players = null;
                    }
                }
            } catch (error) {
                result.choose_ms = Date.now() - chooseStart;
                result.error = String(error);
                result.in_match = false;
            }
            if (withSnapshot && result.in_match) {
                const snapshotStart = Date.now();
                try {
                    const snapshot = buildSnapshot("probe", true);
                    result.snapshot_ms = Date.now() - snapshotStart;
                    result.rows = snapshot.rows;
                    result.columns = snapshot.columns;
                } catch (error) {
                    result.snapshot_ms = Date.now() - snapshotStart;
                    result.snapshot_error = String(error);
                }
            }
            result.polling = pollTimer != null;
            result.match_active = matchActive;
            result.ctor_hook = ctorHookState;
            result.ctor_hook_error = ctorHookError;
            result.constructed = constructedCount;
            result.resolve_by_hook = resolveByHook;
            result.resolve_by_choose = resolveByChoose;
            if (matchActive && previousCache != null) cachedGameLogic = previousCache;
            return result;
        });
    },
    dumpBoard(): Promise<Snapshot> {
        return performAsync(() => {
            const snapshot = buildSnapshot("manual_rpc", true);
            candidateSignature = snapshot.signature;
            candidateCount = requiredStableSamples;
            sendSnapshot(snapshot, true);
            return snapshot;
        });
    },
    status(): Promise<any> {
        return performAsync(() => ({
            ready,
            matchActive,
            ctorHook: ctorHookState,
            ctorHookError,
            concedeHook: concedeHookState,
            concedeHookError,
            disposeHook: disposeHookState,
            disposeHookError,
            disposed: disposedCount,
            disposedAgoMs: disposedAt == null ? null : Date.now() - disposedAt,
            endedLogicHandle,
            quietSignature,
            deadLogicKeys: Array.from(deadLogicKeys),
            constructed: constructedCount,
            resolveByHook,
            resolveByChoose,
            deferredResolves,
            gameCount: lastGameCount,
            quietMs: Date.now() - lastChangeTimestamp,
            gameLogicFound: (() => { try { resolveGameLogic(); return true; } catch (_) { return false; } })(),
            pollMilliseconds,
            idleMilliseconds,
            requiredStableSamples,
            candidateCount,
            lastSentSignature,
            lastSentStateSignature,
            lastError,
        }));
    },
    configure(
        pollMs: number,
        stableSamples: number,
        withState?: boolean,
        idleMs?: number,
        quietMs?: number,
        withCtorHook?: boolean,
    ): Promise<any> {
        return performAsync(() => {
            pollMilliseconds = Math.max(100, Math.min(10000, Number(pollMs) || 250));
            requiredStableSamples = Math.max(2, Math.min(20, Number(stableSamples) || 3));
            includeState = withState == null ? includeState : Boolean(withState);
            if (idleMs != null) idleMilliseconds = Math.max(200, Math.min(10000, Number(idleMs) || 1000));
            if (quietMs != null) idleAfterQuietMs = Math.max(0, Number(quietMs));
            if (withCtorHook != null) useCtorHook = Boolean(withCtorHook);
            // The concede hook is deliberately NOT installed (player's call,
            // 2026-09-15): it closed matches that were still on (09:02:29
            // "predaja" -> "partija se nastavila" 20 s later), every hook is
            // a suspect in the game freezes, and the host's "Predaja" button
            // is the exact signal. A missed concede is still closed by the
            // Dispose hook, the quiet timeout, or a rising GameCount.
            installDisposeHook();
            if (useCtorHook) {
                ctorHookDetachPending = false;
                installCtorHook();
            } else if (ctorHookListeners.length > 0) {
                // Already installed: stop trusting it at once (every reader
                // of the hook's pointers checks useCtorHook) and take the
                // listeners off -- right away between matches, at the end of
                // the match otherwise, since unhooking mid-match is riskier.
                removeCtorHook();
            }
            candidateSignature = null;
            candidateCount = 0;
            // null, not the current value: the next idle tick then treats this
            // as a fresh attach and checks once whether a match is already
            // running, which a counter that never rises would otherwise hide.
            lastGameCount = null;
            startPolling();
            return {
                pollMilliseconds,
                idleMilliseconds,
                idleAfterQuietMs,
                requiredStableSamples,
                includeState,
                traceMode,
                matchActive,
                ctorHook: ctorHookState,
                ctorHookError,
                concedeHook: concedeHookState,
                concedeHookError,
                disposeHook: disposeHookState,
                disposeHookError,
            };
        });
    },
    /** Pick up a match that is already in progress, on the host's say-so.
     *
     *  The idle path deliberately refuses to guess -- a finished match looks
     *  exactly like a running one on the heap. This is the other half of that
     *  decision: when the user asks for a move, the engine's own state is
     *  allowed to answer, because the user is looking at the screen and the
     *  agent is not. */
    wake(): Promise<any> {
        return performAsync(() => {
            // Someone is asking for a move right now: no pacing delay.
            idleChooseAfter = 0;
            lastGameCount = readGameCount();
            const detail: Record<string, any> = { game_count: lastGameCount };
            let logic: Il2Cpp.Object | null = null;
            try {
                logic = resolveGameLogic();
                detail.found = true;
            } catch (error) {
                detail.found = false;
                detail.resolve_error = String(error);
                // Nothing live, but maybe only because the host's dead list
                // says so: the user is looking at a match, so a logic the
                // engine still calls open is taken back (see the helper).
                const revived = reviveNewestDeadLogic();
                if (revived != null) {
                    logic = revived;
                    detail.found = true;
                    detail.revived = true;
                    send({
                        type: "error",
                        stage: "wake",
                        message:
                            "ozivljavam partiju koju je host ranije obelezio kao "
                            + "zavrsenu: korisnik trazi potez, a engine kaze da traje",
                    });
                }
            }
            if (logic != null) {
                detail.state = readGameStateEnum(logic);
                detail.state_raw = (() => {
                    try {
                        return logic.handle
                            .add(EXPECTED_OFFSETS["GameLogic.currentGameState"])
                            .readS32();
                    } catch (_) {
                        return null;
                    }
                })();
                detail.has_board = hasBoard(logic);
                detail.simulation = isSimulation(logic);
            }
            // Deliberately the lenient test, not the strict one the idle path
            // uses: the user is looking at the screen and has just asked for a
            // move, so an unreadable state is no reason to refuse. The idle
            // path stays strict because nobody is watching it.
            if (!matchActive && matchIsRunning()) setMatchActive(true, "rucno");
            detail.match_active = matchActive;
            return detail;
        });
    },
    /** The user says the match is over (a concede the engine did not report).
     *
     *  Goes through the same edge as a natural end, so the host gets the same
     *  `match_state` message and the idle tick takes over -- the next match is
     *  then picked up by the counter, exactly as after a normal finish. */
    /** Matches the host knows are over: GameLogic/board keys from its own
     *  record of earlier ends, in this same game process. A fresh agent has
     *  no memory of them and would take the last match's corpse for a running
     *  one; called before configure() so the first idle tick already knows.
     *  If the match currently being read is among them, it is closed. */
    markDead(keys: string[]): Promise<any> {
        return performAsync(() => {
            for (const key of keys || []) {
                if (typeof key === "string" && key.length > 0) markLogicDead(key);
            }
            if (matchActive && cachedGameLogic != null && isDeadLogic(cachedGameLogic)) {
                quietSignature = lastSentSignature;
                setMatchActive(false, "partija iz prethodne sesije");
            }
            return { dead: deadLogicKeys.size, match_active: matchActive };
        });
    },
    endMatch(reason?: string): Promise<any> {
        return performAsync(() => {
            const wasActive = matchActive;
            // The board the user is closing is the corpse's board: the idle
            // state check must not reopen the same match two seconds later
            // (it did -- the logic keeps its in-match state after a concede).
            quietSignature = lastSentSignature;
            setMatchActive(false, String(reason || "rucno prekinuta"));
            return { was_active: wasActive, match_active: matchActive, game_count: lastGameCount };
        });
    },
    setTrace(enabled: boolean, pollMs?: number): Promise<any> {
        return performAsync(() => {
            traceMode = Boolean(enabled);
            if (pollMs != null) {
                // Trace mode is a read-only observer, so the floor is set by
                // what is useful rather than by safety: a Froggy lotus destroys
                // its gathered blob and creates the special in between two
                // 100 ms polls, which is why that moment was caught only once
                // in eight recorded moves.
                pollMilliseconds = Math.max(20, Math.min(10000, Number(pollMs) || 250));
                startPolling();
            }
            return { traceMode, pollMilliseconds };
        });
    },
};

setImmediate(() => {
    Il2Cpp.perform(() => {
        try {
            initializeMetadata();
            // The hook is installed from `configure`, not here: if hooking ever
            // is what kills this game, a switch that only arrives after the
            // hook is already in place would be no switch at all.
            ready = true;
            // Polling deliberately does NOT start here. Attaching outside a
            // match used to mean a full `Il2Cpp.gc.choose` heap walk every
            // 100-250 ms in the lobby, where the game allocates hardest --
            // the suspected cause of the freezes when the reader was attached
            // before the match started. The host opens the poll explicitly
            // with `configure`, which it calls right after `ready` anyway, so
            // normal play is unchanged; a diagnostic host can now attach and
            // read nothing at all.
            send({
                type: "ready",
                application: Il2Cpp.application.identifier,
                version: Il2Cpp.application.version,
                unity: Il2Cpp.unityVersion,
                poll_milliseconds: pollMilliseconds,
                stable_samples: requiredStableSamples,
            });
        } catch (error) {
            lastError = String(error);
            send({ type: "error", stage: "initialize", message: lastError });
        }
    });
});
