"""Generate tests/differential_cases.cryo: random patterns checked against
Python's `re`, a backtracking engine with the same leftmost-first semantics.

Usage: python scripts/testgen/generate_differential.py [count] [seed]

Each case records the first match of a random pattern in a random
haystack and the span of every group, as `re.search` reports them. The
generator only draws from constructs on which the two engines agree:
ASCII haystacks (so Unicode tables play no part), no `$` (which `re`
also lets match before a final newline), no iteration (`re` lets an
empty match follow a non-empty one directly; this library does not), and
no `\\B` against an empty haystack (`re` refuses to match it there; this
library matches it).

One difference is kept and marked rather than avoided: when the last pass
through a repetition matches empty, `re` reports that empty pass as the
group's span, while an automaton reports the last non-empty pass. The
expected text writes `~` for the span of a repeated group whose reference
span is empty, and the test does not check it.
"""

import random
import re
import sys

ALPHABET = "abcAB1 _-\n"


class Generator:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.next_group = 1
        self.repeated_groups = set()

    def reset(self) -> None:
        self.next_group = 1
        self.repeated_groups = set()

    def literal(self) -> str:
        c = self.rng.choice("abcAB1 _-")
        return "\\-" if c == "-" else c

    def char_class(self) -> str:
        r = self.rng.random()
        if r < 0.2:
            return self.rng.choice(["\\d", "\\w", "\\s", "\\D", "\\W", "\\S"])
        items = []
        for _ in range(self.rng.randint(1, 3)):
            if self.rng.random() < 0.3:
                items.append(self.rng.choice(["a-c", "A-B", "0-9", "\\d", "\\s", "\\w"]))
            else:
                items.append(self.rng.choice("abcAB1 _"))
        negate = "^" if self.rng.random() < 0.25 else ""
        return "[" + negate + "".join(items) + "]"

    def atom(self, depth: int) -> str:
        r = self.rng.random()
        if depth > 0 and r < 0.25:
            kind = self.rng.random()
            if kind < 0.6:
                # Groups are numbered by their opening parenthesis.
                self.next_group += 1
                inner = self.alternation(depth - 1)
                return "(" + inner + ")"
            inner = self.alternation(depth - 1)
            if kind < 0.8:
                return "(?:" + inner + ")"
            return "(?i:" + inner + ")"
        if r < 0.45:
            return self.char_class()
        if r < 0.55:
            return "."
        if r < 0.58:
            return "^"
        if r < 0.61:
            return "\\b"
        if r < 0.63:
            return "\\B"
        return self.literal()

    def repeated(self, depth: int) -> str:
        first_group = self.next_group
        atom = self.atom(depth)
        r = self.rng.random()
        if r < 0.55 or atom in ("^", "\\b", "\\B"):
            return atom
        op = self.rng.choice(["*", "+", "?", "{2}", "{1,3}", "{0,2}", "{2,}", "{,2}"])
        if op != "?":
            self.repeated_groups.update(range(first_group, self.next_group))
        lazy = "?" if self.rng.random() < 0.3 else ""
        return atom + op + lazy

    def concat(self, depth: int) -> str:
        length = 0 if self.rng.random() < 0.08 else self.rng.randint(1, 4)
        return "".join(self.repeated(depth) for _ in range(length))

    def alternation(self, depth: int) -> str:
        branches = [self.concat(depth) for _ in range(self.rng.randint(1, 3))]
        return "|".join(branches)

    def haystack(self) -> str:
        return "".join(self.rng.choice(ALPHABET) for _ in range(self.rng.randint(0, 10)))


def cryo_string(text: str) -> str:
    out = []
    for c in text:
        if c == "\\":
            out.append("\\\\")
        elif c == "\"":
            out.append("\\\"")
        elif c == "\n":
            out.append("\\n")
        else:
            out.append(c)
    return "\"" + "".join(out) + "\""


def expected(pattern: str, haystack: str, repeated_groups) -> str:
    found = re.search(pattern, haystack)
    if found is None:
        return "none"
    parts = []
    for index in range(len(found.regs)):
        start, end = found.span(index)
        if start < 0:
            parts.append("-")
        elif start == end and index in repeated_groups:
            parts.append("~")
        else:
            parts.append(f"{start}-{end}")
    return " ".join(parts)


def _valid(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def main() -> int:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261102
    rng = random.Random(seed)
    generator = Generator(rng)
    cases = []
    seen = set()
    while len(cases) < count:
        generator.reset()
        pattern = generator.alternation(2)
        if not _valid(pattern):
            continue
        # The group numbering the generator tracked must be the pattern's.
        assert re.compile(pattern).groups == generator.next_group - 1, pattern
        for _ in range(3):
            haystack = generator.haystack()
            if (pattern, haystack) in seen:
                continue
            if haystack == "" and "\\B" in pattern:
                continue
            seen.add((pattern, haystack))
            cases.append((pattern, haystack, expected(pattern, haystack, generator.repeated_groups)))
    cases = cases[:count]

    out = []
    out.append("///! Differential cases: the first match of random patterns, as Python's")
    out.append("///! `re` reports it. Generated by scripts/testgen/generate_differential.py;")
    out.append("///! do not edit, regenerate instead.")
    out.append("")
    out.append("![config(testing)]")
    out.append("namespace RegexTests::DifferentialCases;")
    out.append("")
    out.append("internal type struct Case {")
    out.append("    pattern: string;")
    out.append("    haystack: string;")
    out.append("    expected: string;")
    out.append("}")
    out.append("")
    out.append(f"internal const CASE_COUNT: i64 = {len(cases)};")
    out.append("")
    out.append(f"internal const CASES: [Case; {len(cases)}] = [")
    for pattern, haystack, result in cases:
        out.append(f"    Case {{ pattern: {cryo_string(pattern)}, haystack: {cryo_string(haystack)}, expected: \"{result}\" }},")
    out.append("];")
    out.append("")
    with open("tests/differential_cases.cryo", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(out))
    print(f"wrote {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
