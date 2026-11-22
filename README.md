# regex

Regular expressions for Cryo, with full Unicode support and a guarantee:
**every search runs in time linear in the haystack**. A pattern from an
untrusted source cannot make a search take exponential time, because the
features that would need backtracking (backreferences, look-around, atomic
groups) are refused with a clear error instead of being half-supported.

```cryo
import regex::{ Regex };
import std::collections::str::{ Str };
import std::collections::string::{ String };

const dates: Regex = Regex::new(Str::new("(?<year>\\d{4})-(?<month>\\d{2})-(?<day>\\d{2})")).unwrap();
for (captures in dates.captures_all(Str::new("2026-11-02 and 2026-12-15"))) {
    // captures.name(Str::new("year")).unwrap().as_str() is "2026"
}
const swapped: String = dates.replace_all(Str::new("2026-11-02"), Str::new("${day}/${month}/${year}"));
// swapped is "02/11/2026"
```

## Installing

regex is a Cryo library with no dependencies of its own. Add it to the
`[dependencies]` of your project's `cryoconfig`, from git:

```ini
[dependencies]
regex = { git = "https://github.com/jakelequire/regex.git", tag = "v0.1.0" }
```

and run `cryo fetch`, which resolves the tag and writes `cryoconfig.lock`.
Versions are the repository's tags (`v0.1.0`, ...). To work against a local
checkout instead, name its directory:

```ini
[dependencies]
regex = { path = "../regex" }
```

The library's namespace is `regex`: `import regex::{ Regex };` for text, and
`import regex::bytes::{ Regex };` for haystacks of bytes that need not be
UTF-8 (`&Slice<u8>`).

## Using it

A complete program that lists the words of a sentence, then rewrites it:

```cryo
namespace Example;

import regex::{ Regex, RegexBuilder };
import std::collections::str::{ Str };
import std::collections::string::{ String };
import std::fmt;

function main() -> i32 {
    const text: Str = Str::new("The quick brown fox");

    // Every match, left to right.
    const words: Regex = Regex::new(Str::new("\\w+")).unwrap();
    for (word in words.find_all(text)) {
        fmt::println(f"{word.start()}..{word.end()}: {word}");
    }

    // Options a pattern could also set inline, here `(?i)`.
    const fox: Regex = RegexBuilder::new(Str::new("FOX")).case_insensitive(true).build().unwrap();
    const replaced: String = fox.replace_all(text, Str::new("dog"));
    fmt::println(f"{replaced}");

    // A pattern that cannot be compiled says why, and where.
    match (Regex::new(Str::new("a{3,2}"))) {
        Result::Ok(_) => { }
        Result::Err(error) => { fmt::println(f"{error}"); }
    }
    return 0;
}
```

### API at a glance

| | |
|---|---|
| `Regex::new(pattern)` | compile with default options; `Result<Regex, Error>` |
| `RegexBuilder::new(pattern).case_insensitive(true).build()` | compile with options: `case_insensitive`, `multi_line`, `dot_matches_new_line`, `swap_greed`, `ignore_whitespace`, `unicode`, `size_limit`, `nest_limit` |
| `expression.is_match(h)` / `is_match_at(h, i)` | does it match anywhere? (stops at the first match) |
| `expression.find(h)` / `find_at(h, i)` | the leftmost match, a `Match` with `start()`, `end()`, `as_str()` |
| `expression.find_all(h)` | every non-overlapping match |
| `expression.captures(h)` / `captures_at(h, i)` / `captures_all(h)` | groups by number (`get(i)`) or name (`name(n)`) |
| `expression.replace(h, r)` / `replace_all` / `replace_at_most(h, n, r)` | substitution with `$1`, `${1}`, `$name`, `${name}`, `$$` |
| `expression.split(h)` / `split_at_most(h, n)` | the text between matches |
| `Regex::escape(text)` | a pattern matching `text` literally |
| `captures_length()`, `capture_name(i)`, `capture_index(name)` | group metadata |

`Error` reports a kind (`error.kind()`, an `ErrorKind`) and the span of the
pattern at fault; printing it underlines the span:

```
regex parse error:
    ab[z-a]
       ^^^
error: invalid character class range: the start is after the end
```

A `Regex` may be shared between threads: each search borrows the regex's
scratch memory when it is free and makes its own when another search holds it.

## Syntax

| | |
|---|---|
| `.` | any character except `\n` (any at all with `s`) |
| `[abc]` `[^abc]` `[a-z]` | classes; `]` first is literal, `-` first or last is literal |
| `[a-z&&[^aeiou]]` `[\w--\d]` `[\pL~~\p{Greek}]` | nested classes with intersection, difference, symmetric difference |
| `[[:alpha:]]` `[[:^digit:]]` | POSIX classes (ASCII) |
| `\d` `\w` `\s` and `\D` `\W` `\S` | digit, word character, whitespace (Unicode unless `u` is off) |
| `\h` `\v` `\H` `\V` | horizontal and vertical whitespace |
| `\p{L}` `\pL` `\p{Greek}` `\p{Script=Greek}` `\p{gc:Lu}` `\p{scx=Hira}` `\p{Alphabetic}` `\P{..}` `\p{^..}` | Unicode properties: General_Category, Script, Script_Extensions, binary properties, `Any`, `ASCII`, `Assigned`; names match loosely (`\p{IsGreek}`, `\p{ greek }`) |
| `\N` | any character except `\n` |
| `x*` `x+` `x?` `x{n}` `x{n,}` `x{,m}` `x{n,m}` | repetition, greedy; add `?` for lazy. A `{` that is not a well-formed count is a literal |
| `xy` `x\|y` | sequence, alternation (leftmost first) |
| `(x)` `(?<name>x)` `(?P<name>x)` `(?'name'x)` `(?:x)` | groups: capturing, named, non-capturing |
| `(?flags)` `(?flags:x)` `(?i-m)` | set or clear flags for the rest of the group, or within one |
| `(?#comment)` | a comment |
| `^` `$` | start and end of the haystack, or of a line with `m` |
| `\A` `\z` `\Z` | start, end, end or before a final `\n` |
| `\b` `\B` | word boundary, not a word boundary |
| `\Q...\E` | literal text |
| `\n` `\t` `\r` `\f` `\a` `\e` `\0` `\cX` `\xHH` `\x{H..}` `\o{O..}` `\N{U+H..}` | character escapes; escaped punctuation is literal |

Flags: `i` case-insensitive (Unicode simple case folding), `m` multi-line,
`s` dot matches newline, `x` verbose (whitespace and `#` comments ignored
outside classes), `U` swap greed, `u` Unicode (on by default).

Refused with a dedicated error: backreferences (`\1`, `\k<n>`, `(?P=n)`),
look-around (`(?=` `(?!` `(?<=` `(?<!`), atomic groups and possessive
repetitions (`(?>` `a*+`), recursion and conditionals (`(?R)` `(?1)` `(?(`
`(?|`), and the escapes `\K` `\G` `\X` `\R` `\C`.

## Semantics worth knowing

- **Leftmost-first.** A match is the one a backtracking engine would report:
  alternatives are preferred in order, greedy repetitions take as much as
  they can.
- **`$` is the end of the haystack**, not "the end or before a final
  newline": `^\d+$` does not accept `"123\n"`. Use `\Z` for the other meaning,
  or `m` for lines.
- **Text regexes match only UTF-8 and only between scalars.** A pattern that
  could match bytes that are not UTF-8 (`(?-u:\xFF)`, `(?-u:.)`) is refused
  for `regex::Regex`; use `regex::bytes` for those.
- **Iteration skips an empty match that directly follows a match**:
  replacing `x*` with `-` in `abxd` gives `-a-b-d-`.
- **A repetition whose last pass matched empty** reports the group's span
  from the last non-empty pass, where a backtracking engine reports the
  empty one. Only that capture span differs, never the match.
- **Case-insensitive matching uses simple case folding** (one character to
  one character): `(?i)k` matches `K` and the Kelvin sign, `(?i)ß` matches
  `ẞ`, but `ß` does not match `ss`.
- **Unicode data is version 17.0.0.** `\w` is Alphabetic, marks, decimal
  numbers, connector punctuation and Join_Control (UTS #18); `\d` is
  Decimal_Number; `\s` is White_Space.

## Performance

Matching is a Pike VM, the linear-time simulation of the compiled
automaton, plus a prefilter that skips to where a match can begin: the next
occurrence of a required literal prefix (with `memchr`), or the next byte a
match can start with. On a 2 MiB English haystack (`build/regex-bench`):

| pattern | throughput |
|---|---|
| `Moriarty` (absent literal) | ~25-35 GiB/s |
| `\p{Greek}+` | ~1 GiB/s |
| `\d{4}-\d{2}-\d{2}` | ~190 MiB/s |
| `Sherlock` | ~150 MiB/s |
| `Sherlock\|Holmes` | ~50 MiB/s |
| `\w+@\w+\.com`, `[a-z]+ing`, `\b\w+\b` | ~5-9 MiB/s |

The last row is the Pike VM's own speed, where most positions can start a
match. A lazy DFA, which answers most searches without simulating threads,
is the next piece of work and is what will lift that row.

## Layout

| | |
|---|---|
| `src/lib.cryo` | the facade: `regex::{ Regex, RegexBuilder, Match, Captures, Error, ErrorKind, ... }` |
| `src/text.cryo`, `src/bytes.cryo` | the two front ends; `bytes` holds the implementation, `text` presents it over `Str` |
| `src/syntax/` | the parser (pattern to a normalized syntax tree, flags applied) and class sets |
| `src/compiler.cryo`, `src/automaton.cryo` | Thompson construction to a byte automaton; Unicode classes become minimal UTF-8 automata |
| `src/search.cryo`, `src/prefilter.cryo`, `src/engine.cryo` | the Pike VM, candidate skipping, and the shared search driver |
| `src/unicode/` | property lookup; `tables.cryo` is generated |
| `scripts/unicode/` | `fetch_ucd.py` and `generate_tables.py`, which write `src/unicode/tables.cryo` |
| `scripts/testgen/` | `generate_differential.py`, which writes `tests/differential_cases.cryo` |

Parsing and compiling keep explicit stacks instead of recursing, so no
pattern, however deeply nested, can exhaust the call stack; the nest limit
bounds memory, not safety.

## Development

```sh
cryo test                 # every test
cryo build                # the demo and the benchmark
./build/regex-demo        # a tour of the library
./build/regex-bench       # throughput
```

The generated files are rewritten by the scripts beside them:

```sh
python scripts/unicode/fetch_ucd.py ucd && python scripts/unicode/generate_tables.py ucd src/unicode/tables.cryo
python scripts/testgen/generate_differential.py 3000
```

The differential cases are 3,000 random patterns whose first match and group
spans were recorded from Python's `re`, a backtracking engine with the same
leftmost-first semantics; the generator documents the few constructs on
which the two engines legitimately differ and stays clear of them.

## License

Apache License 2.0; see [LICENSE](LICENSE).
