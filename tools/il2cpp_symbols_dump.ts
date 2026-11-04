/*
 * Read-only IL2CPP symbol dumper for Match Masters.
 *
 * This agent never reads game state and never calls a managed method. It only
 * asks the IL2CPP runtime for its own metadata: which classes exist, what
 * fields they have (and at which offset), and where every method's compiled
 * code starts inside libil2cpp.so.
 *
 * That last number is the whole point. `global-metadata.dat` is v39 and has no
 * public offline parser, so the name -> address mapping cannot be recovered
 * from the APK alone. The live runtime hands it over for free, and once it is
 * written down the actual disassembly happens offline against the shipped
 * .so (tools/il2cpp_disasm.py) with the game closed.
 *
 * Two rules carried over from the board agent:
 *  - never invoke a managed method (get_Count crashed the process on attach);
 *    every property here is metadata, served by the runtime's C API.
 *  - stream results in chunks. A full method index is ~400k entries and a
 *    single send() of that size stalls the bridge.
 */

import "frida-il2cpp-bridge";

type FieldInfo = {
    name: string;
    type: string;
    offset: number;
    is_static: boolean;
    is_literal: boolean;
    /** Value of a const/enum member, when the runtime exposes it cheaply. */
    literal: string | null;
    /** Numeric value of an enum member, read from its `value__` field. */
    literal_value: number | null;
};

type MethodInfo = {
    name: string;
    rva: string;
    va: string;
    return_type: string;
    parameters: { name: string; type: string }[];
    is_static: boolean;
    modifier: string | null;
};

type ClassInfo = {
    image: string;
    namespace: string;
    name: string;
    full_name: string;
    parent: string | null;
    is_enum: boolean;
    instance_size: number;
    fields: FieldInfo[];
    methods: MethodInfo[];
};

// `Match3Engine.` is the engine namespace: one class per booster plus
// GameLogic/BoardModel. The rest catch helpers living outside it.
const DEFAULT_PATTERNS = [
    "Ability",
    "Booster",
    "Powerup",
    "SpecialPiece",
    "^Match3Engine\\.",
    "MutationLab",
];

let moduleBase: NativePointer = ptr(0);
let moduleSize = 0;

/** True for an address that really is an offset inside libil2cpp.so.
 *
 * Some methods report a virtual address below the module base (runtime stubs,
 * generic shared code), and `va - base` then wraps into a huge unsigned value.
 * One such entry landed in the index as 0xffff8828d7500000 and turned the
 * "largest gap" statistic into nonsense. */
function plausibleRva(rva: NativePointer): boolean {
    if (rva.isNull()) return false;
    const value = rva.toUInt32();
    return rva.compare(ptr(moduleSize)) < 0 && value > 0;
}
let ready = false;
let lastError: string | null = null;

function safeText(value: any): string {
    try {
        const text = String(value);
        return text.length > 400 ? text.slice(0, 400) + "..." : text;
    } catch (_) {
        return "?";
    }
}

/** Every metadata read is wrapped: a malformed class must not kill the dump. */
function attempt<T>(block: () => T, fallback: T): T {
    try {
        return block();
    } catch (_) {
        return fallback;
    }
}

function describeClass(klass: Il2Cpp.Class): ClassInfo {
    const fields: FieldInfo[] = [];
    for (const field of attempt(() => klass.fields, [] as Il2Cpp.Field[])) {
        fields.push({
            name: attempt(() => field.name, "?"),
            type: attempt(() => field.type.name, "?"),
            offset: attempt(() => field.offset, -1),
            is_static: attempt(() => field.isStatic, false),
            is_literal: attempt(() => field.isLiteral, false),
            // Enum members carry their numeric value here, which is what turns
            // "SlotValue 28" in a board dump into a name.
            literal: attempt(
                () => (field.isLiteral ? safeText(field.value) : null),
                null,
            ),
            // `String(value)` on an enum member prints its *name*, so the
            // number has to be dug out of the underlying `value__` field.
            // Assuming "declaration order == value" holds for SlotValueType
            // but is not a rule, and a wrong colour id is a silent wrong answer.
            literal_value: attempt(
                () =>
                    field.isLiteral
                        ? Number((field.value as any).field("value__").value)
                        : null,
                null,
            ),
        });
    }

    const methods: MethodInfo[] = [];
    for (const method of attempt(() => klass.methods, [] as Il2Cpp.Method[])) {
        const va = attempt(() => method.virtualAddress, ptr(0));
        if (va.isNull()) continue; // abstract / not compiled into this build
        const methodRva = attempt(() => method.relativeVirtualAddress, ptr(0));
        if (!plausibleRva(methodRva)) continue;
        methods.push({
            name: attempt(() => method.name, "?"),
            rva: "0x" + methodRva.toString(16),
            va: "0x" + va.toString(16),
            return_type: attempt(() => method.returnType.name, "?"),
            parameters: attempt(
                () => method.parameters.map(p => ({ name: p.name, type: p.type.name })),
                [],
            ),
            is_static: attempt(() => method.isStatic, false),
            modifier: attempt(() => method.modifier ?? null, null),
        });
    }

    return {
        image: attempt(() => klass.image.name, "?"),
        namespace: attempt(() => klass.namespace, ""),
        name: attempt(() => klass.name, "?"),
        full_name: attempt(() => klass.type.name, "?"),
        parent: attempt(() => (klass.parent ? klass.parent.type.name : null), null),
        is_enum: attempt(() => klass.isEnum, false),
        instance_size: attempt(() => klass.instanceSize, -1),
        fields,
        methods,
    };
}

function eachClass(visit: (klass: Il2Cpp.Class) => void): void {
    for (const assembly of Il2Cpp.domain.assemblies) {
        const image = attempt(() => assembly.image, null as any);
        if (image == null) continue;
        for (const klass of attempt(() => image.classes, [] as Il2Cpp.Class[])) {
            try {
                visit(klass);
            } catch (error) {
                // One bad class is a skipped class, not a failed dump.
                send({ type: "class_error", message: safeText(error) });
            }
        }
    }
}


// ---------------------------------------------------------------------------
// Ability configuration
//
// The code says *how* a booster decides; these are the numbers it decides with.
// They arrive from the server into `LogicModel.Instance.specialAbilities` and
// sit there for the whole session, so one read is enough.
//
// Still no managed calls: a List<T> is read as its `_items` array plus `_size`,
// which is a memory read, and a boxed value is read straight off its object.
// ---------------------------------------------------------------------------

function findMatch3Image(): Il2Cpp.Image {
    for (const name of ["Match3Engine", "Match3Engine.dll"]) {
        const assembly = Il2Cpp.domain.tryAssembly(name);
        if (assembly != null) return assembly.image;
    }
    for (const assembly of Il2Cpp.domain.assemblies) {
        try {
            assembly.image.class("Match3Engine.LogicModel");
            return assembly.image;
        } catch (_) {
        }
    }
    throw new Error("assembly containing Match3Engine.LogicModel was not found");
}

/** A non-null object, or null. The bridge wraps NULL too, and reading a field
 *  off such a wrapper takes the whole game process down. */
function live(value: any): Il2Cpp.Object | null {
    if (value == null) return null;
    if (typeof value.isNull === "function" && value.isNull()) return null;
    if (value.handle != null && value.handle.isNull()) return null;
    return value as Il2Cpp.Object;
}

function fieldOf(object: Il2Cpp.Object | null, name: string): any {
    if (object == null) return null;
    return attempt(() => object.field(name).value, null);
}

function textOf(value: any): string | null {
    const raw = live(value);
    if (raw == null) return null;
    return attempt(() => new Il2Cpp.String(raw.handle).content, null);
}

/** Elements of a `List<T>`, read through `_items` / `_size`. */
function listItems(object: any): any[] {
    const target = live(object);
    if (target == null) return [];
    const items = live(fieldOf(target, "_items"));
    const size = attempt(() => Number(fieldOf(target, "_size")), 0) || 0;
    if (items == null || size <= 0) return [];
    const array = items as unknown as Il2Cpp.Array;
    const length = attempt(() => array.length, 0);
    const out: any[] = [];
    for (let i = 0; i < Math.min(size, length); i++) {
        out.push(attempt(() => array.get(i), null));
    }
    return out;
}

function arrayItems(value: any): any[] {
    const array = live(value) as unknown as Il2Cpp.Array | null;
    if (array == null) return [];
    const length = attempt(() => array.length, 0);
    const out: any[] = [];
    for (let i = 0; i < length; i++) out.push(attempt(() => array.get(i), null));
    return out;
}

/** A boxed `System.Object` param value, turned into JSON.
 *
 * The type has to be read off the box because the field is declared as
 * `object`: the same `key` holds an int for one booster and a list of lists
 * for another. */
function describeValue(value: any, depth: number = 0): any {
    if (value == null) return null;
    if (typeof value === "number" || typeof value === "boolean" || typeof value === "string") {
        return value;
    }
    const object = live(value);
    if (object == null) return null;
    const typeName = attempt(() => object.class.type.name, "?");
    const handle = object.handle;

    switch (typeName) {
        case "System.Int32": return attempt(() => handle.add(0x10).readS32(), null);
        case "System.UInt32": return attempt(() => handle.add(0x10).readU32(), null);
        case "System.Int64": return attempt(() => Number(handle.add(0x10).readS64()), null);
        case "System.Int16": return attempt(() => handle.add(0x10).readS16(), null);
        case "System.Byte": return attempt(() => handle.add(0x10).readU8(), null);
        case "System.SByte": return attempt(() => handle.add(0x10).readS8(), null);
        case "System.Boolean": return attempt(() => handle.add(0x10).readU8() !== 0, null);
        case "System.Single": return attempt(() => handle.add(0x10).readFloat(), null);
        case "System.Double": return attempt(() => handle.add(0x10).readDouble(), null);
        case "System.String": return textOf(object);
    }
    if (depth >= 4) return "<" + typeName + ">";
    if (typeName.indexOf("System.Collections.Generic.List<") === 0) {
        return listItems(object).map(item => describeValue(item, depth + 1));
    }
    if (typeName.slice(-2) === "[]") {
        return arrayItems(object).map(item => describeValue(item, depth + 1));
    }
    return "<" + typeName + ">";
}

/** `List<SpecialAbilityModelParam>` -> plain key/value object. */
function readParams(listObject: any): Record<string, any> {
    const out: Record<string, any> = {};
    for (const entry of listItems(listObject)) {
        const item = live(entry);
        if (item == null) continue;
        const key = textOf(attempt(() => item.field("<key>k__BackingField").value, null));
        if (key == null) continue;
        out[key] = describeValue(attempt(() => item.field("<value>k__BackingField").value, null));
    }
    return out;
}

/** An enum-typed field, as its raw number.
 *
 * `field(name).value` hands back a wrapper for enum fields, and `Number()` of
 * that is NaN -- which JSON then writes as `null`, so every booster came out
 * with `"type": null`. Reading the bytes at the field offset avoids the
 * wrapper entirely. */
function enumNumber(object: Il2Cpp.Object, name: string, bytes: number): number | null {
    return attempt(() => {
        const offset = object.class.field(name).offset;
        const address = object.handle.add(offset);
        return bytes === 1 ? address.readU8() : address.readS32();
    }, null);
}

/** The booster instances actually in play, with their *effective* config.
 *
 * `UFOBeamSEPowerUpVariant1::ReadIntListParam` reads a param out of
 * `Config.additionalParams` and nowhere else -- it never looks at
 * `conditionalOverrides`. So whatever merging happens must already have been
 * written into `additionalParams` of the instance's own Config by the time the
 * booster runs. Comparing this against the catalogue read from
 * `LogicModel.specialAbilities` is what settles which numbers really apply.
 */
function readLiveAbilities(): any[] {
    const image = findMatch3Image();
    const gameLogicClass = image.class("Match3Engine.GameLogic");
    const instances = Il2Cpp.gc.choose(gameLogicClass);
    const out: any[] = [];

    for (const logic of instances) {
        const players = live(fieldOf(logic, "players"));
        if (players == null) continue;
        const entries = listItems(players);
        if (entries.length === 0) continue;

        for (let index = 0; index < entries.length; index++) {
            const player = live(entries[index]);
            if (player == null) continue;
            const ability = live(fieldOf(player, "ability"));
            if (ability == null) {
                out.push({ player_index: index, ability: null });
                continue;
            }
            const config = live(fieldOf(ability, "<Config>k__BackingField"));
            const variant = live(fieldOf(ability, "<ActiveVariant>k__BackingField"));
            out.push({
                player_index: index,
                type: enumNumber(ability, "<Type>k__BackingField", 4),
                steps: attempt(() => Number(fieldOf(ability, "<Steps>k__BackingField")), null),
                variant_class: variant == null
                    ? null
                    : attempt(() => variant.class.type.name, null),
                config_title: config == null
                    ? null
                    : textOf(attempt(() => config.field("title").value, null)),
                // The effective table. If the merge happened, the override keys
                // show up here even though the catalogue keeps them separate.
                effective_params: config == null
                    ? {}
                    : attempt(() => readParams(config.field("additionalParams").value), {}),
                catalogue_conditional_overrides: config == null
                    ? 0
                    : attempt(() => listItems(config.field("conditionalOverrides").value).length, 0),
            });
        }
        if (out.length > 0) break; // the active match is enough
    }
    return out;
}

/** Every booster piece logic alive in the match, with its resolved tuning.
 *
 * The booster's `additionalParams` describe the *activation*; how the piece it
 * leaves on the board behaves is tuned separately, in
 * `SpecialPieceModel.pieceParams` -- a Dictionary keyed by variant. Decoding
 * that dictionary offline is guesswork about .NET internals, but the live
 * `SpecialPiecesLogic` instance has already resolved it into a flat
 * `pieceParams` list, plus fields like `paintableColors` the engine derived
 * from it. So read the instance, not the model.
 */
/** First field of `object` that exists under any of `names`. */
function anyField(object: Il2Cpp.Object | null, names: string[]): any {
    for (const name of names) {
        const value = attempt(() => object!.field(name).value, undefined);
        if (value !== undefined) return value;
    }
    return null;
}

/** `Dictionary<string, V>` as key/value pairs, read straight out of `entries`.
 *
 * Field naming differs between the Mono corlib Unity ships and CoreCLR
 * (`entries` vs `_entries`), and the Entry struct's own offsets are read from
 * its class rather than assumed -- guessing either one gives plausible garbage
 * instead of an error.
 */
function dictionaryPairs(dict: any): [string, any][] {
    const target = live(dict);
    if (target == null) return [];
    const entries = live(anyField(target, ["_entries", "entries"]));
    if (entries == null) return [];
    const count = Number(anyField(target, ["_count", "count"]) ?? 0) || 0;
    if (count <= 0) return [];

    const array = entries as unknown as Il2Cpp.Array;
    const stride = attempt(() => array.elementSize, 0);
    const entryClass = attempt(() => array.elementType.class, null as any);
    if (!stride || entryClass == null) return [];

    // Field offsets on a value type include the object header the struct does
    // not have when it sits inline in an array.
    const offsetOf = (name: string): number | null =>
        attempt(() => entryClass.field(name).offset - Il2Cpp.Object.headerSize, null);
    const keyOffset = offsetOf("key");
    const valueOffset = offsetOf("value");
    const hashOffset = offsetOf("hashCode");
    const nextOffset = offsetOf("next");
    if (keyOffset == null || valueOffset == null) return [];

    const base = array.handle.add(Il2Cpp.Array.headerSize);
    const pairs: [string, any][] = [];
    for (let i = 0; i < count; i++) {
        const slot = base.add(i * stride);
        // Free slots: Mono marks them with hashCode < 0, CoreCLR with next < -1.
        if (hashOffset != null && attempt(() => slot.add(hashOffset).readS32(), 0) < 0) continue;
        if (nextOffset != null && attempt(() => slot.add(nextOffset).readS32(), 0) < -1) continue;
        const keyPointer = attempt(() => slot.add(keyOffset).readPointer(), null);
        if (keyPointer == null || keyPointer.isNull()) continue;
        const key = attempt(() => new Il2Cpp.String(keyPointer).content, null);
        if (key == null) continue;
        const valuePointer = attempt(() => slot.add(valueOffset).readPointer(), null);
        pairs.push([
            key,
            valuePointer == null || valuePointer.isNull() ? null : new Il2Cpp.Object(valuePointer),
        ]);
    }
    return pairs;
}

/** `LogicModel.specialPieces`: how each booster's board piece is tuned. */
function readSpecialPieces(logicModel: Il2Cpp.Object): any[] {
    const out: any[] = [];
    for (const entry of listItems(fieldOf(logicModel, "specialPieces"))) {
        const model = live(entry);
        if (model == null) continue;
        const variants: Record<string, any> = {};
        for (const [key, value] of dictionaryPairs(fieldOf(model, "pieceParams"))) {
            variants[key] = readParams(value);
        }
        out.push({
            slot_type: enumNumber(model, "slotType", 4),
            no_energy_on_piece_swaps: attempt(
                () => Boolean(fieldOf(model, "noEnergyOnPieceSwaps")),
                null,
            ),
            allow_energy_after_refill: attempt(
                () => Boolean(fieldOf(model, "allowEnergyAfterRefill")),
                null,
            ),
            free_piece_swaps: attempt(() => Boolean(fieldOf(model, "freePieceSwaps")), null),
            piece_params: variants,
        });
    }
    return out;
}

function readPieceLogics(): any[] {
    const image = findMatch3Image();
    const base = image.class("Match3Engine.SpecialPiecesLogic");

    // gc.choose matches an exact class, so every subclass has to be asked for
    // separately.
    const classes: Il2Cpp.Class[] = [base];
    for (const klass of attempt(() => image.classes, [] as Il2Cpp.Class[])) {
        const parent = attempt(() => (klass.parent ? klass.parent.type.name : null), null);
        if (parent === "Match3Engine.SpecialPiecesLogic") classes.push(klass);
    }

    const out: any[] = [];
    for (const klass of classes) {
        const instances = attempt(() => Il2Cpp.gc.choose(klass), [] as Il2Cpp.Object[]);
        for (const instance of instances) {
            const logic = live(instance);
            if (logic == null) continue;
            const entry: any = {
                class: attempt(() => klass.type.name, "?"),
                piece_type: enumNumber(logic, "<PieceType>k__BackingField", 4),
                logic_origin: enumNumber(logic, "LogicOrigin", 4),
                allow_merge_swap_with_blue: attempt(
                    () => Boolean(fieldOf(logic, "allowMergeSwapWithBlue")),
                    null,
                ),
                allow_merge_swap_with_red: attempt(
                    () => Boolean(fieldOf(logic, "allowMergeSwapWithRed")),
                    null,
                ),
                activate_merge_counterpart: attempt(
                    () => Boolean(fieldOf(logic, "activateMergeCounterpart")),
                    null,
                ),
                paintable_colors: attempt(
                    () => listItems(fieldOf(logic, "paintableColors")).map(Number),
                    [],
                ),
                merge_swap_only_with: attempt(
                    () => listItems(fieldOf(logic, "allowMergeSwapOnlyWithTypes")).map(Number),
                    [],
                ),
                merge_swap_except_with: attempt(
                    () => listItems(fieldOf(logic, "allowMergeSwapExceptWithTypes")).map(Number),
                    [],
                ),
                piece_params: attempt(() => readParams(fieldOf(logic, "pieceParams")), {}),
            };
            // Whatever the subclass added on top of the shared base -- for Cleo
            // that is the whole cloning model.
            entry.own_fields = attempt(() => readOwnFields(logic, klass), {});
            out.push(entry);
        }
    }
    return out;
}

/** Scalar and small-list fields declared by `klass` itself, not inherited. */
function readOwnFields(object: Il2Cpp.Object, klass: Il2Cpp.Class): Record<string, any> {
    const out: Record<string, any> = {};
    for (const field of attempt(() => klass.fields, [] as Il2Cpp.Field[])) {
        if (attempt(() => field.isStatic, true)) continue;
        const name = attempt(() => field.name, null);
        if (name == null) continue;
        const typeName = attempt(() => field.type.name, "");
        const raw = attempt(() => object.field(name).value, null);
        if (typeName.indexOf("System.Collections.Generic.List<") === 0) {
            out[name] = listItems(raw).map(item => describeValue(item, 1));
        } else if (typeof raw === "object" && raw !== null) {
            out[name] = describeValue(raw);
        } else {
            out[name] = raw;
        }
    }
    return out;
}

/** Only Dictionary<SlotColor,Int32>. Inline entries, never managed getters. */
function readColorWeights(value: any): any {
    const dict = live(value);
    if (dict == null) return null;
    const name = dict.class.type.name;
    if (name !== "System.Collections.Generic.Dictionary<Match3Engine.SlotColor,System.Int32>") {
        return { unresolved_type: name };
    }
    const array = live(anyField(dict, ["_entries", "entries"])) as unknown as Il2Cpp.Array | null;
    const count = Number(anyField(dict, ["_count", "count"]) ?? 0);
    if (count === 0) return {};
    if (array == null || count < 0 || count > 256 || count > array.length) {
        return { error: "invalid color dictionary bounds", count };
    }
    const klass = array.elementType.class;
    const offset = (field: string) => klass.field(field).offset - Il2Cpp.Object.headerSize;
    const keyField = klass.field("key");
    const keyType = keyField.type.class.field("value__").type.name;
    const base = array.handle.add(Il2Cpp.Array.headerSize);
    const result: Record<string, number> = {};
    for (let i = 0; i < count; i++) {
        const entry = base.add(i * array.elementSize);
        if (attempt(() => entry.add(offset("hashCode")).readS32(), 0) < 0) continue;
        if (attempt(() => entry.add(offset("next")).readS32(), 0) < -1) continue;
        const keyPtr = entry.add(offset("key"));
        const key = keyType === "System.Byte" ? keyPtr.readU8() : keyPtr.readS32();
        result[String(key)] = entry.add(offset("value")).readS32();
    }
    return result;
}

function readAbility(model: Il2Cpp.Object): any {
    return {
        type: enumNumber(model, "type", 4),
        index: attempt(() => Number(model.field("index").value), null),
        name: textOf(attempt(() => model.field("name").value, null)),
        title: textOf(attempt(() => model.field("title").value, null)),
        technical_desc: textOf(attempt(() => model.field("technicalDesc").value, null)),
        cost: attempt(() => Number(model.field("cost").value), null),
        color: enumNumber(model, "color", 1),
        max_booster_spend_per_game: attempt(
            () => Number(model.field("maxBoosterSpendPerGame").value),
            null,
        ),
        energy_tile_weight_change_on_activation: attempt(
            () => listItems(model.field("energyTileWeightChangeOnActivation").value),
            [],
        ),
        // The interesting part: the per-booster tuning table.
        additional_params: attempt(() => readParams(model.field("additionalParams").value), {}),
        powerups: attempt(
            () =>
                listItems(model.field("powerups").value).map(entry => {
                    const item = live(entry);
                    return item == null
                        ? null
                        : textOf(attempt(() => item.field("id").value, null));
                }),
            [],
        ),
        // Same booster, different numbers per mode / pvp / powerup variant.
        conditional_overrides: attempt(
            () =>
                listItems(model.field("conditionalOverrides").value).map(entry => {
                    const segment = live(entry);
                    if (segment == null) return null;
                    const text = (field: string) =>
                        textOf(attempt(() => segment.field(field).value, null));
                    return {
                        pvp_mode: text("pvpMode"),
                        rules_id: text("rulesId"),
                        mode_id: text("modeId"),
                        powerup_id: text("powerupId"),
                        overrides: attempt(() => readParams(segment.field("overrides").value), {}),
                    };
                }),
            [],
        ),
    };
}

function performAsync<T>(block: () => T): Promise<T> {
    return new Promise((resolve, reject) => {
        Il2Cpp.perform(() => {
            try { resolve(block()); } catch (error) { reject(error); }
        });
    });
}

/** Bounded, field-only serializer for portable simulator profiles. */
function profileReader() {
    let remaining = 50000;
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
        if (raw.handle?.isNull()) return null;
        if (raw instanceof Il2Cpp.String) return raw.content;
        if (raw instanceof Il2Cpp.Array) raw = raw.object;
        if (raw instanceof Int64 || raw instanceof UInt64) return raw.toNumber();
        const klass = raw instanceof Il2Cpp.ValueType ? raw.type.class : raw.class;
        if (klass == null) return problem(path, "unknown runtime value");
        const type = klass.type.name;
        if (klass.isEnum) return value(raw.field("value__").value, path, depth + 1);
        if (["System.Int64", "System.UInt64"].includes(type)) return Number(raw.handle.add(0x10).readS64());
        if (["System.String", "System.Int32", "System.UInt32", "System.Int16", "System.Byte", "System.SByte", "System.Boolean", "System.Single", "System.Double"].includes(type)) return describeValue(raw);
        const identity = type + ":" + raw.handle;
        if (active.has(identity)) return { reference_type: type };
        active.add(identity);
        try {
            if (type.includes("[]") || type.includes("[,]")) {
                const array = new Il2Cpp.Array(raw.handle);
                if (array.length > 4096) return problem(path, "array length " + array.length);
                const out: any[] = [];
                for (let i = 0; i < array.length; i++) out.push(value(array.get(i), path + "[" + i + "]", depth + 1));
                return out;
            }
            if (type.startsWith("System.Collections.Generic.List<")) {
                const size = Number(fieldOf(raw, "_size"));
                if (!Number.isInteger(size) || size < 0 || size > 4096) return problem(path, "invalid list size");
                return listItems(raw).map((item, i) => value(item, path + "[" + i + "]", depth + 1));
            }
            if (type.startsWith("System.Collections.Generic.Dictionary<")) {
                const count = Number(anyField(raw, ["_count", "count"]));
                if (!Number.isInteger(count) || count < 0 || count > 4096) return problem(path, "invalid dictionary count");
                if (count === 0) return { entries: [] };
                const entries = live(anyField(raw, ["_entries", "entries"]));
                if (entries == null) return problem(path, "dictionary entries missing");
                const array = new Il2Cpp.Array(entries.handle);
                if (count > array.length) return problem(path, "dictionary count exceeds capacity");
                const out: any[] = [];
                for (let i = 0; i < count; i++) {
                    const entry = array.get(i) as Il2Cpp.ValueType;
                    if (Number(attempt(() => entry.field("hashCode").value, 0)) < 0) continue;
                    if (Number(attempt(() => entry.field("next").value, 0)) < -1) continue;
                    out.push({ key: value(entry.field("key").value, path + ".key" + i, depth + 1),
                               value: value(entry.field("value").value, path + ".value" + i, depth + 1) });
                }
                return { entries: out };
            }
            if (!type.startsWith("Match3Engine.") && !type.startsWith("System.Nullable<") && !type.startsWith("FixMath.")) return problem(path, "unsupported type " + type);
            if (["Match3Engine.GameLogic", "Match3Engine.PlayerControl", "Match3Engine.PlayerModel"].includes(type)) return { reference_type: type };
            return fields(raw, path, depth + 1);
        } catch (error) { return problem(path, String(error)); }
        finally { active.delete(identity); }
    }
    function fields(object: any, path: string, depth = 0, only?: string[]): any {
        const out: any = {};
        let klass = object instanceof Il2Cpp.ValueType ? object.type.class : object.class;
        const skip = new Set(["logic", "parentGame", "player", "OriginBooster", "TypeOfSlotColor"]);
        while (klass != null && klass.type.name !== "System.Object" && klass.type.name !== "System.ValueType") {
            for (const f of klass.fields) {
                if (f.isStatic || skip.has(f.name) || (only && !only.includes(f.name))) continue;
                if (f.type.name.startsWith("System.Action") || f.type.name.startsWith("System.Func") || f.type.name.includes("Callback")) continue;
                try { out[f.name] = value(object.field(f.name).value, path + "." + f.name, depth + 1); }
                catch (error) { out[f.name] = problem(path + "." + f.name, String(error)); }
            }
            klass = klass.parent;
        }
        return out;
    }
    return { value, fields, issues };
}

rpc.exports = {
    captureMatchProfile(): Promise<any> {
        return performAsync(() => {
            const image = findMatch3Image();
            const currentConfig = live(image.class("Match3Engine.LogicModel").field("Instance").value);
            if (currentConfig == null) throw new Error("Udji u aktivnu partiju");
            // One discovery scan. Never take the first object from the heap:
            // old games and booster simulation clones can survive there.
            const discovered = Il2Cpp.gc.choose(image.class("Match3Engine.GameLogic"));
            const candidates = discovered.filter(logic => {
                const config = live(fieldOf(logic, "<configData>k__BackingField"));
                const board = live(fieldOf(logic, "board"));
                const state = enumNumber(logic, "currentGameState", 4);
                return config?.handle.equals(currentConfig.handle) && board != null
                    && fieldOf(logic, "isAISimulation") === false && [-3, -4, -5, -7].includes(state!)
                    && listItems(fieldOf(logic, "players")).length > 0;
            });
            const headers = candidates.map(logic => ({
                game_index: describeValue(fieldOf(logic, "<GameIndex>k__BackingField")),
                state: enumNumber(logic, "currentGameState", 4),
                rules_id: textOf(fieldOf(live(fieldOf(logic, "gameRules")), "id")),
            }));
            if (candidates.length !== 1) throw new Error("Nije jednoznacna aktivna partija: " + JSON.stringify({
                candidates: headers, discovered: discovered.slice(0, 16).map(logic => ({
                    state: enumNumber(logic, "currentGameState", 4),
                    ai: fieldOf(logic, "isAISimulation"),
                    board: live(fieldOf(logic, "board")) != null,
                    players: listItems(fieldOf(logic, "players")).length,
                    current_config: live(fieldOf(logic, "<configData>k__BackingField"))?.handle.equals(currentConfig.handle),
                })) }));
            const logic = candidates[0];
            const rng = live(fieldOf(logic, "<Random>k__BackingField"));
            const counter = fieldOf(rng, "<counter>k__BackingField");
            const beforeState = enumNumber(logic, "currentGameState", 4);
            const beforeMoves = fieldOf(logic, "moves");
            const reader = profileReader();
            const board = live(fieldOf(logic, "board"))!;
            const rows = Number(fieldOf(board, "<Rows>k__BackingField"));
            const columns = Number(fieldOf(board, "<Columns>k__BackingField"));
            if (rows < 4 || rows > 12 || columns < 4 || columns > 12) throw new Error("Neispravne dimenzije table");
            const slots = live(fieldOf(board, "<slots>k__BackingField"));
            if (slots == null) throw new Error("Nema slots matrice");
            const array = new Il2Cpp.Array(slots.handle);
            if (array.length !== rows * columns) throw new Error("Pogresna velicina slots matrice");
            const flat: any[] = [];
            for (let x = 0; x < columns; x++) for (let y = 0; y < rows; y++) {
                // C# slots[x,y], verified against BoardModel.get_Item ARM64.
                const slot = array.get(x * rows + y);
                if (slot == null) throw new Error("Null slot");
                flat.push({ ...reader.fields(slot, "slots[" + x + "," + y + "]"), x, y });
            }
            const players = listItems(fieldOf(logic, "players")).map((control, i) => {
                const model = live(fieldOf(control, "model"));
                const ability = live(fieldOf(control, "ability"));
                return {
                    player_type: enumNumber(control, "<Type>k__BackingField", 4),
                    model: model == null ? null : reader.fields(model, "players." + i, 0,
                        ["index", "score", "health", "turnScore", "roundsWon", "scoreMultiplier", "slotType", "specialAbilityType", "activeSpecialAbilityType", "energy", "powerup", "boardAbilities", "limitedPerksCounts", "specialAbilityUsed", "specialAbilityUsedThisTurn", "isAbilityUsedThisMove", "soloScoreTargetInd", "mutationLabTargetInd"]),
                    energy_colors: reader.value(fieldOf(control, "energyColors"), "players." + i + ".energyColors"),
                    ability: ability == null ? null : reader.fields(ability, "players." + i + ".ability"),
                    board_abilities: reader.value(fieldOf(control, "BoardAbilities"), "players." + i + ".boardAbilities"),
                };
            });
            const result = {
                schema_version: 1, selection: { strategy: "unique current-config non-AI nonterminal GameLogic; host verifies repeated reads", candidates: headers },
                rules: reader.value(fieldOf(logic, "gameRules"), "rules"),
                config: reader.value(currentConfig, "config"),
                spawning: reader.value(fieldOf(logic, "spawningEngine"), "spawning"),
                rng: rng == null ? null : reader.fields(rng, "rng"),
                board: { rows, columns, storage_order: "x*rows+y", slots: flat,
                         fields: reader.fields(board, "board", 0, ["extraData", "<cells>k__BackingField", "arenaConfig", "BoardPiecesLogic", "boardSpecialPaintableColors"]) },
                state: reader.fields(logic, "state", 0, ["moves", "currentPlayerIndex", "currentGameState", "<GameIndex>k__BackingField", "<ChainReaction>k__BackingField", "<Turns>k__BackingField", "<TurnsTotal>k__BackingField", "<MovesMadeThisTurn>k__BackingField", "passiveAbility", "noEnergyThisMove", "noEnergyUntilRefill", "allowEnergyEvenIfAbilityUsedThisMove", "mutationsActivatedList", "mutationsEarned"]),
                players, piece_logics: reader.value(fieldOf(logic, "specialPiecesLogics"), "piece_logics"),
                issues: reader.issues,
            };
            if (counter !== fieldOf(rng, "<counter>k__BackingField") || beforeState !== enumNumber(logic, "currentGameState", 4) || beforeMoves !== fieldOf(logic, "moves")) throw new Error("Partija se promenila tokom citanja; ne povlaci poteze i probaj ponovo");
            return result;
        });
    },
    /** Scalar tuning from the server model. No heap walk or managed calls. */
    dumpEngineConfig(): Promise<any> {
        return performAsync(() => {
            const image = findMatch3Image();
            const model = live(image.class("Match3Engine.LogicModel").field("Instance").value);
            if (model == null) throw new Error("LogicModel.Instance je null");
            const spawn = live(fieldOf(model, "spawnEngine"));
            const initial = live(fieldOf(spawn, "initialSpawnParams"));
            return {
                scope: "LogicModel.Instance only; no GameLogic heap walk; unresolved objects are type placeholders, not decoded values",
                logic_model: readOwnFields(model, model.class),
                spawning_config: spawn == null ? null : readOwnFields(spawn, spawn.class),
                initial_spawn: initial == null ? null : readOwnFields(initial, initial.class),
                color_weights: readColorWeights(fieldOf(spawn, "gemsWeights")),
                initial_color_weights: readColorWeights(fieldOf(initial, "gemsWeights")),
                initial_match_color_weights: readColorWeights(fieldOf(initial, "possibleMatchesColorWeights")),
            };
        });
    },
    /**
     * Full description (fields + methods + offsets) of every class whose full
     * name matches one of the regex patterns.
     */
    dumpClasses(patterns?: string[], chunkSize?: number): Promise<any> {
        return performAsync(() => {
            const source = patterns && patterns.length ? patterns : DEFAULT_PATTERNS;
            const regexes = source.map(p => new RegExp(p, "i"));
            const limit = Math.max(1, Math.min(500, Number(chunkSize) || 40));

            let buffer: ClassInfo[] = [];
            let total = 0;
            const flush = () => {
                if (buffer.length === 0) return;
                send({ type: "classes", items: buffer });
                buffer = [];
            };

            eachClass(klass => {
                const fullName = attempt(() => klass.type.name, "");
                if (!regexes.some(rx => rx.test(fullName))) return;
                buffer.push(describeClass(klass));
                total += 1;
                if (buffer.length >= limit) flush();
            });
            flush();

            send({ type: "classes_done", total });
            return { total, patterns: source };
        });
    },

    /**
     * Compact `rva -> Class::Method` index over the whole image. The
     * disassembler needs it twice: to know where a function ends (the next
     * entry) and to name `bl` targets.
     */
    dumpIndex(chunkSize?: number): Promise<any> {
        return performAsync(() => {
            const limit = Math.max(100, Math.min(20000, Number(chunkSize) || 5000));
            let buffer: [string, string][] = [];
            let total = 0;
            const flush = () => {
                if (buffer.length === 0) return;
                send({ type: "index", items: buffer });
                buffer = [];
            };

            eachClass(klass => {
                const owner = attempt(() => klass.type.name, "?");
                for (const method of attempt(() => klass.methods, [] as Il2Cpp.Method[])) {
                    const rva = attempt(() => method.relativeVirtualAddress, ptr(0));
                    if (!plausibleRva(rva)) continue;
                    buffer.push([
                        "0x" + rva.toString(16),
                        owner + "::" + attempt(() => method.name, "?"),
                    ]);
                    total += 1;
                    if (buffer.length >= limit) flush();
                }
            });
            flush();

            send({ type: "index_done", total });
            return { total };
        });
    },


    /**
     * Every booster's configuration, read out of `LogicModel.Instance`.
     * Requires a live match: the model is populated by the server on join.
     */
    dumpAbilities(chunkSize?: number): Promise<any> {
        return performAsync(() => {
            const image = findMatch3Image();
            const logicModel = live(image.class("Match3Engine.LogicModel").field("Instance").value);
            if (logicModel == null) {
                throw new Error("LogicModel.Instance je null - udji u partiju pa probaj ponovo");
            }
            const abilitiesModel = live(fieldOf(logicModel, "specialAbilities"));
            if (abilitiesModel == null) {
                throw new Error("LogicModel.specialAbilities je null");
            }
            const models = arrayItems(fieldOf(abilitiesModel, "abilities"));

            const limit = Math.max(1, Math.min(50, Number(chunkSize) || 5));
            let buffer: any[] = [];
            let total = 0;
            const flush = () => {
                if (buffer.length === 0) return;
                send({ type: "abilities", items: buffer });
                buffer = [];
            };
            for (const entry of models) {
                const model = live(entry);
                if (model == null) continue;
                buffer.push(readAbility(model));
                total += 1;
                if (buffer.length >= limit) flush();
            }
            flush();
            send({ type: "abilities_done", total });
            return { total };
        });
    },


    /** Boosters as they exist in the running match, not as catalogue entries. */
    dumpLiveAbilities(): Promise<any> {
        return performAsync(() => {
            const items = readLiveAbilities();
            send({ type: "live_abilities", items });
            send({ type: "live_abilities_done", total: items.length });
            return { total: items.length };
        });
    },


    /** Booster piece tuning: the catalogue from LogicModel plus whatever piece
     *  logics happen to be alive in this match. */
    dumpPieceLogics(): Promise<any> {
        return performAsync(() => {
            const image = findMatch3Image();
            const logicModel = live(image.class("Match3Engine.LogicModel").field("Instance").value);
            const catalogue = logicModel == null ? [] : readSpecialPieces(logicModel);
            const items = readPieceLogics();
            send({ type: "piece_catalogue", items: catalogue });
            send({ type: "piece_logics", items });
            send({ type: "piece_logics_done", total: items.length });
            return { total: items.length, catalogue: catalogue.length };
        });
    },

    status(): Promise<any> {
        return performAsync(() => ({
            ready,
            module_base: "0x" + moduleBase.toString(16),
            module_name: Il2Cpp.module.name,
            module_size: Il2Cpp.module.size,
            application: Il2Cpp.application.identifier,
            version: Il2Cpp.application.version,
            unity: Il2Cpp.unityVersion,
            last_error: lastError,
        }));
    },
};

setImmediate(() => {
    Il2Cpp.perform(() => {
        try {
            moduleBase = Il2Cpp.module.base;
            moduleSize = Il2Cpp.module.size;
            ready = true;
            send({
                type: "ready",
                application: Il2Cpp.application.identifier,
                version: Il2Cpp.application.version,
                unity: Il2Cpp.unityVersion,
                module_name: Il2Cpp.module.name,
                module_base: "0x" + moduleBase.toString(16),
                module_size: Il2Cpp.module.size,
            });
        } catch (error) {
            lastError = safeText(error);
            send({ type: "error", stage: "initialize", message: lastError });
        }
    });
});
