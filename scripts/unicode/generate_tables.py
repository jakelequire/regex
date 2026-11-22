"""Generate src/unicode/tables.cryo from the Unicode Character Database.

Usage:
    python scripts/unicode/fetch_ucd.py <ucd-directory>
    python scripts/unicode/generate_tables.py <ucd-directory> src/unicode/tables.cryo

The output holds every class table the pattern syntax can name, as
inclusive (start, end) scalar ranges concatenated into one array, plus the
sorted name indexes that resolve a normalized property name to a table, and
the simple case folding equivalence classes.

Names are normalized exactly as `regex::unicode::normalize_name` does at run
time (case, spaces, underscores and hyphens ignored, a leading "is" dropped);
the generator refuses to write tables in which two different properties of
one kind normalize to the same name.
"""

import collections
import pathlib
import sys

UNICODE_VERSION = "17.0.0"
MAX_SCALAR = 0x10FFFF


def fail(message: str) -> None:
    print(f"generate_tables: {message}", file=sys.stderr)
    sys.exit(1)


def data_lines(path: pathlib.Path):
    """Yield the semicolon-separated fields of each data line, comments cut."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            yield [field.strip() for field in line.split(";")]


def parse_codepoints(text: str) -> range:
    if ".." in text:
        low, high = text.split("..")
        return range(int(low, 16), int(high, 16) + 1)
    value = int(text, 16)
    return range(value, value + 1)


def to_ranges(points) -> list:
    """Canonical sorted, merged, inclusive ranges over a set of scalars."""
    ordered = sorted(set(points))
    ranges = []
    for point in ordered:
        if ranges and ranges[-1][1] + 1 == point:
            ranges[-1][1] = point
        else:
            ranges.append([point, point])
    return [(low, high) for low, high in ranges]


def normalize(name: str) -> str:
    out = "".join(c.lower() for c in name if c not in " _-")
    if out.startswith("is") and len(out) > 2:
        out = out[2:]
    return out


def check_version(ucd: pathlib.Path) -> None:
    header = (ucd / "Scripts.txt").read_text(encoding="utf-8").splitlines()[0]
    if UNICODE_VERSION not in header:
        fail(f"Scripts.txt is not Unicode {UNICODE_VERSION}: {header!r}")


def read_general_categories(ucd: pathlib.Path) -> dict:
    """Map each scalar to its two-letter General_Category; absent is Cn."""
    categories = {}
    pending_first = None
    for fields in data_lines(ucd / "UnicodeData.txt"):
        point = int(fields[0], 16)
        name, category = fields[1], fields[2]
        if name.endswith(", First>"):
            pending_first = point
            continue
        if name.endswith(", Last>"):
            for value in range(pending_first, point + 1):
                categories[value] = category
            pending_first = None
            continue
        categories[point] = category
    return categories


def read_property_file(path: pathlib.Path, into: dict) -> None:
    """Binary-property files: `code ; Property`. Lines with a value field
    (non-binary properties sharing the file) are skipped."""
    for fields in data_lines(path):
        if len(fields) != 2:
            continue
        into.setdefault(fields[1], set()).update(parse_codepoints(fields[0]))


def read_aliases(ucd: pathlib.Path):
    property_aliases = {}
    for fields in data_lines(ucd / "PropertyAliases.txt"):
        property_aliases[fields[1]] = fields
    value_aliases = collections.defaultdict(list)
    for fields in data_lines(ucd / "PropertyValueAliases.txt"):
        value_aliases[fields[0]].append(fields[1:])
    return property_aliases, value_aliases


def read_case_folding(ucd: pathlib.Path) -> list:
    """Simple case folding equivalence classes, each a sorted list."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for fields in data_lines(ucd / "CaseFolding.txt"):
        if fields[1] not in ("C", "S"):
            continue
        source = int(fields[0], 16)
        target = int(fields[2], 16)
        a, b = find(source), find(target)
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups = collections.defaultdict(list)
    for point in list(parent):
        groups[find(point)].append(point)
    return [sorted(group) for group in groups.values() if len(group) > 1]


class Tables:
    def __init__(self):
        self.ranges = []      # flattened start/end pairs
        self.starts = []      # per table: index into `ranges` of its first pair
        self.lengths = []     # per table: number of pairs
        self.by_points = {}   # dedupe identical tables

    def add(self, points) -> int:
        ranges = tuple(to_ranges(points))
        if ranges in self.by_points:
            return self.by_points[ranges]
        identifier = len(self.starts)
        self.starts.append(len(self.ranges) // 2)
        self.lengths.append(len(ranges))
        for low, high in ranges:
            self.ranges.extend((low, high))
        self.by_points[ranges] = identifier
        return identifier


def add_names(index: dict, names, table: int, kind: str) -> None:
    for name in names:
        key = normalize(name)
        if not key:
            continue
        previous = index.get(key)
        if previous is not None and previous != table:
            fail(f"{kind} name {name!r} normalizes to {key!r}, which already names another table")
        index[key] = table


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    ucd = pathlib.Path(sys.argv[1])
    output = pathlib.Path(sys.argv[2])
    check_version(ucd)

    categories = read_general_categories(ucd)
    property_aliases, value_aliases = read_aliases(ucd)

    by_category = collections.defaultdict(set)
    for point in range(MAX_SCALAR + 1):
        by_category[categories.get(point, "Cn")].add(point)

    tables = Tables()

    # General_Category: every value, including the groupings the alias file
    # describes in its comments (L, LC, M, N, P, S, Z, C).
    groupings = {
        "L": ["Lu", "Ll", "Lt", "Lm", "Lo"],
        "LC": ["Lu", "Ll", "Lt"],
        "M": ["Mn", "Mc", "Me"],
        "N": ["Nd", "Nl", "No"],
        "P": ["Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po"],
        "S": ["Sm", "Sc", "Sk", "So"],
        "Z": ["Zs", "Zl", "Zp"],
        "C": ["Cc", "Cf", "Cs", "Co", "Cn"],
    }
    general_category_names = {}
    for fields in value_aliases["gc"]:
        short = fields[0]
        if short in groupings:
            points = set()
            for member in groupings[short]:
                points |= by_category[member]
        else:
            points = by_category[short]
        add_names(general_category_names, fields, tables.add(points), "General_Category")

    # Script and Script_Extensions share one name index; each entry names
    # both tables.
    scripts = {}
    for fields in data_lines(ucd / "Scripts.txt"):
        scripts.setdefault(fields[1], set()).update(parse_codepoints(fields[0]))
    short_to_long = {}
    for fields in value_aliases["sc"]:
        short_to_long[fields[0]] = fields[1]
    extensions = {}
    for fields in data_lines(ucd / "ScriptExtensions.txt"):
        for point in parse_codepoints(fields[0]):
            extensions[point] = [short_to_long[s] for s in fields[1].split()]
    script_names = {}
    script_entries = []
    for fields in value_aliases["sc"]:
        long_name = fields[1]
        points = scripts.get(long_name, set())
        extended = {p for p in points if p not in extensions}
        extended |= {p for p, names in extensions.items() if long_name in names}
        entry = len(script_entries)
        script_entries.append((tables.add(points), tables.add(extended)))
        add_names(script_names, fields, entry, "Script")

    # Binary properties with data in the files read here.
    booleans = {}
    read_property_file(ucd / "PropList.txt", booleans)
    read_property_file(ucd / "DerivedCoreProperties.txt", booleans)
    read_property_file(ucd / "emoji-data.txt", booleans)
    boolean_names = {}
    for long_name, points in sorted(booleans.items()):
        aliases = property_aliases.get(long_name, [long_name])
        add_names(boolean_names, aliases, tables.add(points), "binary property")
    # The three properties UTS #18 adds beside the database's own.
    add_names(boolean_names, ["Any"], tables.add(range(MAX_SCALAR + 1)), "binary property")
    add_names(boolean_names, ["ASCII"], tables.add(range(0x80)), "binary property")
    assigned = set(range(MAX_SCALAR + 1)) - by_category["Cn"]
    add_names(boolean_names, ["Assigned"], tables.add(assigned), "binary property")

    # The classes the escapes \d \s \w name, Unicode-aware.
    perl_digit = tables.add(by_category["Nd"])
    perl_space = tables.add(booleans["White_Space"])
    word = set(booleans["Alphabetic"])
    for member in groupings["M"] + ["Nd", "Pc"]:
        word |= by_category[member]
    word |= booleans["Join_Control"]
    perl_word = tables.add(word)

    folding = read_case_folding(ucd)
    fold_keys, fold_offsets, fold_values = [], [], []
    members = []
    for group in folding:
        for point in group:
            members.append((point, [other for other in group if other != point]))
    members.sort()
    for point, others in members:
        fold_keys.append(point)
        fold_offsets.append(len(fold_values))
        fold_values.extend(others)
    fold_offsets.append(len(fold_values))

    write_output(output, tables, general_category_names, script_names,
                 script_entries, boolean_names, perl_digit, perl_space,
                 perl_word, fold_keys, fold_offsets, fold_values)
    print(f"wrote {output}: {len(tables.starts)} tables, "
          f"{len(tables.ranges) // 2} ranges, {len(fold_keys)} folding keys")
    return 0


def write_array(out, name: str, element: str, values, per_line: int = 12) -> None:
    out.append(f"private const {name}: [{element}; {max(len(values), 1)}] = [")
    if not values:
        values = [0]
    for i in range(0, len(values), per_line):
        chunk = values[i:i + per_line]
        if element == "u32":
            out.append("    " + ", ".join(f"0x{v:X}" for v in chunk) + ",")
        else:
            out.append("    " + ", ".join(f"\"{v}\"" for v in chunk) + ",")
    out.append("];")
    out.append("")


def write_output(path, tables, general_category_names, script_names,
                 script_entries, boolean_names, perl_digit, perl_space,
                 perl_word, fold_keys, fold_offsets, fold_values) -> None:
    out = []
    out.append("///! Unicode character data, generated by scripts/unicode/generate_tables.py")
    out.append(f"///! from the Unicode Character Database, version {UNICODE_VERSION}.")
    out.append("///! Do not edit; regenerate instead.")
    out.append("")
    out.append("namespace regex::unicode::tables;")
    out.append("")
    out.append("import std::core::slice::{ Slice };")
    out.append("")
    out.append(f"internal const UNICODE_VERSION: string = \"{UNICODE_VERSION}\";")
    out.append("")
    out.append(f"internal const TABLE_COUNT: i64 = {len(tables.starts)};")
    out.append(f"internal const PERL_DIGIT: i64 = {perl_digit};")
    out.append(f"internal const PERL_SPACE: i64 = {perl_space};")
    out.append(f"internal const PERL_WORD: i64 = {perl_word};")
    out.append("")

    out.append("/// Every table's ranges, as inclusive start/end pairs, back to back.")
    write_array(out, "RANGES", "u32", tables.ranges)
    out.append("/// Index of each table's first pair in `RANGES`.")
    write_array(out, "TABLE_STARTS", "u32", tables.starts)
    out.append("/// Number of pairs in each table.")
    write_array(out, "TABLE_LENGTHS", "u32", tables.lengths)

    for label, index in (("GENERAL_CATEGORY", general_category_names),
                         ("SCRIPT", script_names),
                         ("BOOLEAN", boolean_names)):
        keys = sorted(index)
        out.append(f"/// Normalized names, sorted bytewise, and the entry each names.")
        write_array(out, f"{label}_NAMES", "string", keys, per_line=6)
        write_array(out, f"{label}_ENTRIES", "u32", [index[k] for k in keys])
    write_array(out, "SCRIPT_TABLES", "u32", [entry[0] for entry in script_entries])
    write_array(out, "SCRIPT_EXTENSION_TABLES", "u32", [entry[1] for entry in script_entries])

    out.append("/// Simple case folding: each key's equivalents are")
    out.append("/// `FOLD_VALUES[FOLD_OFFSETS[i] .. FOLD_OFFSETS[i + 1]]`.")
    write_array(out, "FOLD_KEYS", "u32", fold_keys)
    write_array(out, "FOLD_OFFSETS", "u32", fold_offsets)
    write_array(out, "FOLD_VALUES", "u32", fold_values)

    out.append(f"""/// The ranges of table `id`, flattened as start/end pairs.
internal function table(id: i64) -> &Slice<u32> {{
    const start: i64 = TABLE_STARTS[id] as i64;
    return Slice::from_raw(&RANGES[start * 2], TABLE_LENGTHS[id] as i64 * 2);
}}

/// Which index a property-name lookup searches.
internal type enum NameIndex {{
    GeneralCategory;
    Script;
    Boolean;
}}

internal function name_count(index: NameIndex) -> i64 {{
    return match (index) {{
        NameIndex::GeneralCategory => {{ {len(general_category_names)} }}
        NameIndex::Script          => {{ {len(script_names)} }}
        NameIndex::Boolean         => {{ {len(boolean_names)} }}
    }};
}}

internal function name_at(index: NameIndex, position: i64) -> string {{
    return match (index) {{
        NameIndex::GeneralCategory => {{ GENERAL_CATEGORY_NAMES[position] }}
        NameIndex::Script          => {{ SCRIPT_NAMES[position] }}
        NameIndex::Boolean         => {{ BOOLEAN_NAMES[position] }}
    }};
}}

/// The entry the name at `position` names: a table for the general
/// category and boolean indexes, a script for the script index.
internal function entry_at(index: NameIndex, position: i64) -> i64 {{
    return match (index) {{
        NameIndex::GeneralCategory => {{ GENERAL_CATEGORY_ENTRIES[position] as i64 }}
        NameIndex::Script          => {{ SCRIPT_ENTRIES[position] as i64 }}
        NameIndex::Boolean         => {{ BOOLEAN_ENTRIES[position] as i64 }}
    }};
}}

internal function script_table(script: i64) -> i64 {{
    return SCRIPT_TABLES[script] as i64;
}}

internal function script_extension_table(script: i64) -> i64 {{
    return SCRIPT_EXTENSION_TABLES[script] as i64;
}}

internal const FOLD_KEY_COUNT: i64 = {len(fold_keys)};

internal function fold_keys() -> &Slice<u32> {{
    return Slice::from_raw(&FOLD_KEYS[0], FOLD_KEY_COUNT);
}}

/// The scalars that fold together with `fold_keys()[position]`, itself excluded.
internal function fold_equivalents(position: i64) -> &Slice<u32> {{
    const start: i64 = FOLD_OFFSETS[position] as i64;
    const end: i64 = FOLD_OFFSETS[position + 1] as i64;
    return Slice::from_raw(&FOLD_VALUES[start], end - start);
}}
""")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
