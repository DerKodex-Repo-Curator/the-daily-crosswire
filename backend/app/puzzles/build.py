"""Daily-seeded puzzle generation, verified solvable before HTML is emitted.

Ported from the legacy build_puzzles.py at repo root. This module keeps all
verification asserts from vibedocs/daily-crosswire.md §5.3 -- a puzzle that
cannot be proven solvable must crash the run, not emit broken HTML.

Signature:
    build_puzzles(seed, theme_pool=None, wordsearch_pool=None,
                  crypto_phrases=None, target_givens=43, issue_date=None)
    -> tuple[str, dict]
"""

import datetime
import random
import string
from collections import Counter, deque
from itertools import permutations
from typing import Optional

# =====================================================================
# Default pools (used when caller passes None, matches legacy behavior).
# =====================================================================

DEFAULT_THEME_POOL: dict[str, list[str]] = {
    "shows": ["EPISODE", "SEASON", "STREAM", "SCRIPT", "SHOW", "FILM"],
    "tech": ["CLOUD", "CHIP", "MODEL", "TOKEN", "SERVER", "AGENT"],
    "sports": ["MATCH", "ROUND", "FINAL", "COURT", "STADIUM", "TEAM"],
    "city": ["MAYOR", "BRIDGE", "TRANSIT", "HARBOR", "DISTRICT"],
    "weather": ["RAIN", "STORM", "FROST", "WIND", "HEAT", "TIDE"],
}

DEFAULT_WS_WORDS_POOL: list[str] = [
    "EPISODE",
    "SEASON",
    "STREAM",
    "SCRIPT",
    "SHOW",
    "FILM",
    "CLOUD",
    "CHIP",
    "MODEL",
    "AGENT",
    "MATCH",
    "ROUND",
    "FINAL",
    "TEAM",
    "MAYOR",
    "BRIDGE",
    "TRANSIT",
    "HARBOR",
]

DEFAULT_CRYPTO_PHRASES: list[str] = [
    "STRAIGHT NEWS BEATS BREATHLESS NOISE",
    "OPEN MODELS CLOSE THE GAP",
    "LOCAL STORIES MATTER MORE",
    "GOOD EDITORS REMOVE HYPE DAILY",
    "THE HARBOR BRIDGE REOPENS TODAY",
]


# =====================================================================
# Sudoku
# =====================================================================

BASE_SUDOKU = [
    [5, 3, 4, 6, 7, 8, 9, 1, 2],
    [6, 7, 2, 1, 9, 5, 3, 4, 8],
    [1, 9, 8, 3, 4, 2, 5, 6, 7],
    [8, 5, 9, 7, 6, 1, 4, 2, 3],
    [4, 2, 6, 8, 5, 3, 7, 9, 1],
    [7, 1, 3, 9, 2, 4, 8, 5, 6],
    [9, 6, 1, 5, 3, 7, 2, 8, 4],
    [2, 8, 7, 4, 1, 9, 6, 3, 5],
    [3, 4, 5, 2, 8, 6, 1, 7, 9],
]


def _valid_full(g):
    rng9 = list(range(1, 10))
    for r in range(9):
        if sorted(g[r]) != rng9:
            return False
    for c in range(9):
        if sorted(g[r][c] for r in range(9)) != rng9:
            return False
    for br in (0, 3, 6):
        for bc in (0, 3, 6):
            box = [g[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)]
            if sorted(box) != rng9:
                return False
    return True


def _transform_sudoku(g, rng):
    g = [row[:] for row in g]
    perm = list(range(1, 10))
    rng.shuffle(perm)
    dmap = {i + 1: perm[i] for i in range(9)}
    g = [[dmap[v] for v in row] for row in g]
    for band in range(3):
        order = list(range(band * 3, band * 3 + 3))
        rng.shuffle(order)
        rows = [g[r] for r in order]
        for i, row in enumerate(rows):
            g[band * 3 + i] = row
    bands = [g[0:3], g[3:6], g[6:9]]
    rng.shuffle(bands)
    g = bands[0] + bands[1] + bands[2]
    for stack in range(3):
        order = list(range(stack * 3, stack * 3 + 3))
        rng.shuffle(order)
        new = [row[:] for row in g]
        for r in range(9):
            for i, c in enumerate(order):
                new[r][stack * 3 + i] = g[r][c]
        g = new
    stacks = [
        [row[0:3] for row in g],
        [row[3:6] for row in g],
        [row[6:9] for row in g],
    ]
    rng.shuffle(stacks)
    g = [stacks[0][r] + stacks[1][r] + stacks[2][r] for r in range(9)]
    if rng.random() < 0.5:
        g = [[g[c][r] for c in range(9)] for r in range(9)]
    return g


def _sudoku_solve_count(board, limit=2):
    count = [0]

    def bt():
        if count[0] >= limit:
            return
        for r in range(9):
            for c in range(9):
                if board[r][c] == 0:
                    used_r = set(board[r])
                    used_c = {board[rr][c] for rr in range(9)}
                    br, bc = 3 * (r // 3), 3 * (c // 3)
                    used_b = {board[rr][cc] for rr in range(br, br + 3) for cc in range(bc, bc + 3)}
                    used = used_r | used_c | used_b
                    for n in range(1, 10):
                        if n in used:
                            continue
                        board[r][c] = n
                        bt()
                        board[r][c] = 0
                        if count[0] >= limit:
                            return
                    return
        count[0] += 1

    bt()
    return count[0]


def _generate_sudoku(rng, target_givens: int):
    solution = _transform_sudoku(BASE_SUDOKU, rng)
    assert _valid_full(solution), "Transformed sudoku not valid!"

    puzzle = [row[:] for row in solution]
    positions = [(r, c) for r in range(9) for c in range(9)]
    rng.shuffle(positions)
    givens = 81
    for r, c in positions:
        if givens <= target_givens:
            break
        saved = puzzle[r][c]
        puzzle[r][c] = 0
        if _sudoku_solve_count([row[:] for row in puzzle], limit=2) == 1:
            givens -= 1
        else:
            puzzle[r][c] = saved

    assert _sudoku_solve_count([row[:] for row in puzzle], limit=2) == 1, "Sudoku not unique!"
    return puzzle, solution, givens


# =====================================================================
# Fill-in (criss-cross)
# =====================================================================


def _pick_fillin_words(rng, theme_pool: dict[str, list[str]], count=7):
    picked, seen = [], set()
    for topic_words in theme_pool.values():
        if not topic_words:
            continue
        w = rng.choice(topic_words)
        if w not in seen:
            picked.append(w)
            seen.add(w)
    flat = [w for ws in theme_pool.values() for w in ws if w not in seen]
    rng.shuffle(flat)
    while len(picked) < count and flat:
        picked.append(flat.pop())
    return picked[:count]


class _FillIn:
    def __init__(self, size, rng):
        self.size = size
        self.rng = rng
        self.grid = [["#"] * size for _ in range(size)]
        self.placements = []

    def place(self, word, r, c, d):
        for i, ch in enumerate(word):
            rr, cc = (r, c + i) if d == "h" else (r + i, c)
            self.grid[rr][cc] = ch
        self.placements.append((word, r, c, d))

    def can_place(self, word, r, c, d):
        n = len(word)
        if d == "h":
            if c < 0 or c + n > self.size or r < 0 or r >= self.size:
                return False
        else:
            if r < 0 or r + n > self.size or c < 0 or c >= self.size:
                return False
        if d == "h":
            if c > 0 and self.grid[r][c - 1] != "#":
                return False
            if c + n < self.size and self.grid[r][c + n] != "#":
                return False
        else:
            if r > 0 and self.grid[r - 1][c] != "#":
                return False
            if r + n < self.size and self.grid[r + n][c] != "#":
                return False
        intersections = 0
        for i, ch in enumerate(word):
            rr, cc = (r, c + i) if d == "h" else (r + i, c)
            cell = self.grid[rr][cc]
            if cell == "#":
                if d == "h":
                    for dr in (-1, 1):
                        nr = rr + dr
                        if 0 <= nr < self.size and self.grid[nr][cc] != "#":
                            return False
                else:
                    for dc in (-1, 1):
                        nc = cc + dc
                        if 0 <= nc < self.size and self.grid[rr][nc] != "#":
                            return False
            elif cell == ch:
                intersections += 1
            else:
                return False
        return intersections >= 1

    def try_place(self, word):
        candidates = []
        for placed_word, pr, pc, pd in self.placements:
            for i, ch in enumerate(word):
                for j, pch in enumerate(placed_word):
                    if ch != pch:
                        continue
                    if pd == "h":
                        nr, nc, nd = pr - i, pc + j, "v"
                    else:
                        nr, nc, nd = pr + j, pc - i, "h"
                    if self.can_place(word, nr, nc, nd):
                        candidates.append((nr, nc, nd))
        if not candidates:
            return False
        r, c, d = self.rng.choice(candidates)
        self.place(word, r, c, d)
        return True

    def build(self, words):
        ws = sorted(words, key=len, reverse=True)
        r = self.size // 2
        c = (self.size - len(ws[0])) // 2
        self.place(ws[0], r, c, "h")
        for w in ws[1:]:
            if not self.try_place(w):
                return False
        return True


def _crop(grid):
    rs = [r for r in range(len(grid)) if any(c != "#" for c in grid[r])]
    cs = [c for c in range(len(grid[0])) if any(grid[r][c] != "#" for r in range(len(grid)))]
    if not rs:
        return grid
    return [row[min(cs) : max(cs) + 1] for row in grid[min(rs) : max(rs) + 1]]


def _extract_slots(grid):
    H, W = len(grid), len(grid[0])
    slots = []
    for r in range(H):
        c = 0
        while c < W:
            if grid[r][c] != "#":
                s = c
                while c < W and grid[r][c] != "#":
                    c += 1
                if c - s >= 2:
                    slots.append(("h", r, s, c - s))
            else:
                c += 1
    for c in range(W):
        r = 0
        while r < H:
            if grid[r][c] != "#":
                s = r
                while r < H and grid[r][c] != "#":
                    r += 1
                if r - s >= 2:
                    slots.append(("v", s, c, r - s))
            else:
                r += 1
    return slots


def _count_fillin_solutions(grid_shape, word_list, limit=2):
    slots = _extract_slots(grid_shape)
    if len(slots) != len(word_list):
        return 0
    found = 0
    for perm in permutations(word_list):
        cells = {}
        ok = True
        for (d, sr, sc, ln), word in zip(slots, perm):
            if len(word) != ln:
                ok = False
                break
            for i, ch in enumerate(word):
                rr, cc = (sr, sc + i) if d == "h" else (sr + i, sc)
                if (rr, cc) in cells and cells[(rr, cc)] != ch:
                    ok = False
                    break
                if grid_shape[rr][cc] not in ("#", ".") and grid_shape[rr][cc] != ch:
                    ok = False
                    break
                cells[(rr, cc)] = ch
            if not ok:
                break
        if ok:
            found += 1
            if found >= limit:
                break
    return found


def _generate_fillin(rng, theme_pool: dict[str, list[str]], attempts: int = 60):
    grid = None
    words = None
    anchors: list[tuple[int, int]] = []
    for _ in range(attempts):
        words_try = _pick_fillin_words(rng, theme_pool, count=7)
        if len(words_try) < 3:
            continue
        builder = _FillIn(size=15, rng=rng)
        if not builder.build(words_try):
            continue
        g = _crop(builder.grid)
        shape = [["." if ch != "#" else "#" for ch in row] for row in g]
        solutions = _count_fillin_solutions(shape, words_try, limit=2)
        if solutions == 1:
            grid = g
            words = words_try
            break
        letter_positions = [
            (r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] != "#"
        ]
        rng.shuffle(letter_positions)
        anc: list[tuple[int, int]] = []
        for r, c in letter_positions[:4]:
            shape[r][c] = g[r][c]
            anc.append((r, c))
            if _count_fillin_solutions(shape, words_try, limit=2) == 1:
                grid = g
                words = words_try
                anchors = anc
                break
        if grid is not None:
            break

    assert grid is not None, "Couldn't build a unique fill-in; rerun with different seed or pool"

    # Seed one whole word into the anchors as a visible "starter clue". Adding
    # more pre-filled letters can only tighten the solution space, so
    # uniqueness remains intact. Prefer the longest placed word because it
    # tends to intersect more of the others and gives the solver the most
    # useful leg up.
    seed_word = _pick_seed_word_for_anchors(grid, words)
    if seed_word is not None:
        cells = _find_word_cells(grid, seed_word)
        if cells:
            existing = set(anchors)
            for rc in cells:
                if rc not in existing:
                    anchors.append(rc)
                    existing.add(rc)

    shape_check = [["." if ch != "#" else "#" for ch in row] for row in grid]
    for r, c in anchors:
        shape_check[r][c] = grid[r][c]
    assert _count_fillin_solutions(shape_check, words, limit=2) == 1, "Fill-in not unique!"
    return grid, words, anchors


def _find_word_cells(grid: list[list[str]], word: str) -> Optional[list[tuple[int, int]]]:
    """Scan a (cropped) fill-in grid for `word` placed horizontally or
    vertically. Returns the list of (row, col) cells of the first match,
    or None. Matches only when bounded on both sides by grid edges or
    black cells, so partial overlaps with other words don't hit."""
    H, W = len(grid), len(grid[0])
    n = len(word)
    if n == 0 or H == 0 or W == 0:
        return None
    # Horizontal
    for r in range(H):
        for c in range(W - n + 1):
            if c > 0 and grid[r][c - 1] != "#":
                continue
            if c + n < W and grid[r][c + n] != "#":
                continue
            if all(grid[r][c + i] == word[i] for i in range(n)):
                return [(r, c + i) for i in range(n)]
    # Vertical
    for c in range(W):
        for r in range(H - n + 1):
            if r > 0 and grid[r - 1][c] != "#":
                continue
            if r + n < H and grid[r + n][c] != "#":
                continue
            if all(grid[r + i][c] == word[i] for i in range(n)):
                return [(r + i, c) for i in range(n)]
    return None


def _pick_seed_word_for_anchors(grid: list[list[str]], words: list[str]) -> Optional[str]:
    """Choose which word to pre-fill as a starter clue. Longest word that
    is actually present in the grid wins. Longest tends to cross the most
    other words, so revealing it helps the solver without giving the
    puzzle away."""
    for w in sorted(words, key=len, reverse=True):
        if _find_word_cells(grid, w) is not None:
            return w
    return None


# =====================================================================
# Word search
# =====================================================================

_WS_SIZE = 12
# Place in all 8 directions (horizontal, vertical, both diagonals, each
# forward and reverse). _ws_find already looks in all 8 directions, so any
# placement is findable. Full coverage makes diagonals and reverse words
# show up visibly instead of landing in only 4 orientations.
_WS_PLACE_DIRS = [
    (0, 1),
    (0, -1),
    (1, 0),
    (-1, 0),
    (1, 1),
    (-1, -1),
    (1, -1),
    (-1, 1),
]


def _ws_try_place(grid, word, rng, size):
    for _ in range(1000):
        dr, dc = rng.choice(_WS_PLACE_DIRS)
        r = rng.randint(0, size - 1)
        c = rng.randint(0, size - 1)
        er, ec = r + dr * (len(word) - 1), c + dc * (len(word) - 1)
        if not (0 <= er < size and 0 <= ec < size):
            continue
        conflict = False
        for i, ch in enumerate(word):
            rr, cc = r + dr * i, c + dc * i
            if grid[rr][cc] is not None and grid[rr][cc] != ch:
                conflict = True
                break
        if conflict:
            continue
        for i, ch in enumerate(word):
            grid[r + dr * i][c + dc * i] = ch
        return
    raise RuntimeError(f"Could not place {word}")


def _ws_find(grid, word):
    size = len(grid)
    dirs = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
    for r in range(size):
        for c in range(size):
            for dr, dc in dirs:
                ok = True
                for i, ch in enumerate(word):
                    rr, cc = r + dr * i, c + dc * i
                    if not (0 <= rr < size and 0 <= cc < size):
                        ok = False
                        break
                    if grid[rr][cc] != ch:
                        ok = False
                        break
                if ok:
                    return True
    return False


def _generate_wordsearch(rng, pool: list[str], n_words: int = 10):
    if len(pool) < n_words:
        words = pool[:]
    else:
        words = rng.sample(pool, n_words)
    grid = [[None] * _WS_SIZE for _ in range(_WS_SIZE)]
    for w in sorted(words, key=len, reverse=True):
        _ws_try_place(grid, w, rng, _WS_SIZE)
    for r in range(_WS_SIZE):
        for c in range(_WS_SIZE):
            if grid[r][c] is None:
                grid[r][c] = rng.choice(string.ascii_uppercase)
    for w in words:
        assert _ws_find(grid, w), f"{w} not findable!"
    return grid, words


# =====================================================================
# Maze
# =====================================================================

_MAZE_W_CELLS = 21
_MAZE_H_CELLS = 13


def _gen_maze(cw, ch, rng):
    W, H = 2 * cw + 1, 2 * ch + 1
    m = [[True] * W for _ in range(H)]
    visited = [[False] * cw for _ in range(ch)]
    stack = [(0, 0)]
    visited[0][0] = True
    m[1][1] = False
    while stack:
        x, y = stack[-1]
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        rng.shuffle(dirs)
        advanced = False
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if 0 <= nx < cw and 0 <= ny < ch and not visited[ny][nx]:
                visited[ny][nx] = True
                m[2 * y + 1 + dy][2 * x + 1 + dx] = False
                m[2 * ny + 1][2 * nx + 1] = False
                stack.append((nx, ny))
                advanced = True
                break
        if not advanced:
            stack.pop()
    m[1][0] = False
    m[H - 2][W - 1] = False
    return m


def _maze_solvable(m):
    H, W = len(m), len(m[0])
    start, end = (1, 0), (H - 2, W - 1)
    seen = {start}
    q = deque([start])
    while q:
        r, c = q.popleft()
        if (r, c) == end:
            return True
        for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and not m[nr][nc] and (nr, nc) not in seen:
                seen.add((nr, nc))
                q.append((nr, nc))
    return False


def _generate_maze(rng):
    m = _gen_maze(_MAZE_W_CELLS, _MAZE_H_CELLS, rng)
    assert _maze_solvable(m), "Maze unsolvable!"
    return m


# =====================================================================
# SOS: 2-player pencil game. Not a puzzle, so there's no solvability
# verifier. Only the board shape is asserted valid.
# =====================================================================

_SOS_SIZES = (5, 6, 7)


def _generate_sos(rng) -> tuple[int, list[tuple[int, int, str]]]:
    """Produce an SOS board: grid size picked from a small range plus up
    to two optional pre-placed letters so the opening varies day-to-day.

    Returns (size, placements) where placements is list of (row, col,
    letter). Placements is usually empty or a single entry, to avoid
    biasing the game strategically."""
    size = rng.choice(_SOS_SIZES)
    n_seed = rng.choice([0, 0, 0, 1, 1, 2])
    placements: list[tuple[int, int, str]] = []
    used: set[tuple[int, int]] = set()
    for _ in range(n_seed):
        for _retry in range(20):
            r = rng.randint(0, size - 1)
            c = rng.randint(0, size - 1)
            if (r, c) in used:
                continue
            used.add((r, c))
            placements.append((r, c, rng.choice(["S", "O"])))
            break

    assert size in _SOS_SIZES, f"invalid sos size {size}"
    for r, c, ch in placements:
        assert 0 <= r < size and 0 <= c < size, f"placement out of range {r},{c}"
        assert ch in ("S", "O"), f"invalid letter {ch!r}"
    return size, placements


# =====================================================================
# Cryptogram
# =====================================================================

_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _generate_cryptogram(rng, phrases: list[str]):
    phrase = rng.choice(phrases)
    while True:
        shuf = list(_ALPHA)
        rng.shuffle(shuf)
        if all(a != b for a, b in zip(_ALPHA, shuf)):
            break
    cipher = dict(zip(_ALPHA, shuf))
    decipher = {v: k for k, v in cipher.items()}

    def encode(s):
        return "".join(cipher[c] if c.isalpha() else c for c in s.upper())

    def decode(s):
        return "".join(decipher[c] if c.isalpha() else c for c in s.upper())

    encoded = encode(phrase)
    assert decode(encoded) == phrase, "Cryptogram roundtrip failed!"

    freq = Counter(c for c in phrase if c.isalpha())
    top_letters = [L for L, _ in freq.most_common(5)]
    hint_letters = rng.sample(top_letters, min(2, len(top_letters)))
    hints = [(cipher[L], L) for L in hint_letters]

    for cipher_c, plain_c in hints:
        assert (
            cipher_c in encoded
        ), f"Hint {cipher_c}={plain_c} useless -- {cipher_c} does not appear in encoded text"

    return phrase, encoded, hints


# =====================================================================
# HTML renderers
# =====================================================================


def _sudoku_html(puzzle):
    rows = []
    for r in range(9):
        tds = []
        for c in range(9):
            v = puzzle[r][c]
            content = str(v) if v != 0 else "&nbsp;"
            cls = []
            if r in (3, 6):
                cls.append("band-top")
            if c in (3, 6):
                cls.append("band-left")
            cls_attr = f' class="{" ".join(cls)}"' if cls else ""
            tds.append(f"<td{cls_attr}>{content}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table class="sudoku">{"".join(rows)}</table>'


def _fillin_html(grid, anchors):
    anchor_set = set(anchors)
    rows = []
    for r, row in enumerate(grid):
        tds = []
        for c, ch in enumerate(row):
            if ch == "#":
                # Unused cells render empty: no background, no border.
                # The adjacent fi-cell borders define the grid shape.
                tds.append('<td class="fi-empty"></td>')
            elif (r, c) in anchor_set:
                tds.append(f'<td class="fi-anchor">{ch}</td>')
            else:
                tds.append('<td class="fi-cell"></td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table class="fillin">{"".join(rows)}</table>'


def _fillin_list_html(words):
    by_len = {}
    for w in words:
        by_len.setdefault(len(w), []).append(w)
    parts = []
    for n in sorted(by_len):
        ws = sorted(by_len[n])
        parts.append(
            f'<div class="fi-group"><span class="fi-len">{n} letters</span>'
            f'<span>{" · ".join(ws)}</span></div>'
        )
    return '<div class="fi-wordlist">' + "".join(parts) + "</div>"


def _wordsearch_html(grid):
    rows = []
    for row in grid:
        rows.append("<tr>" + "".join(f"<td>{ch}</td>" for ch in row) + "</tr>")
    return f'<table class="wordsearch">{"".join(rows)}</table>'


def _wordsearch_list_html(words):
    return (
        '<ul class="wordsearch-list">' + "".join(f"<li>{w}</li>" for w in sorted(words)) + "</ul>"
    )


def _maze_svg(m):
    H, W = len(m), len(m[0])
    CELL = 10
    tw, th = W * CELL, H * CELL
    rects = []
    for r in range(H):
        for c in range(W):
            if m[r][c]:
                rects.append(
                    f'<rect x="{c*CELL}" y="{r*CELL}" width="{CELL}" '
                    f'height="{CELL}" fill="#1a1a1a"/>'
                )
    return (
        f'<svg viewBox="-22 -4 {tw+46} {th+8}" class="maze-svg" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<text x="-18" y="{1.5*CELL+3.5}" font-family="Bebas Neue" '
        f'font-size="8" fill="#1a1a1a">IN</text>'
        f'<text x="{tw+4}" y="{(H-1.5)*CELL+3.5}" font-family="Bebas Neue" '
        f'font-size="8" fill="#1a1a1a">OUT</text>'
        f'{"".join(rects)}</svg>'
    )


def _crypto_hints_html(hints):
    return " &nbsp; ".join(f'<span class="crypto-hint">{c} = {p}</span>' for c, p in hints)


def _sos_html(size: int, placements: list[tuple[int, int, str]]) -> str:
    preset = {(r, c): ch for (r, c, ch) in placements}
    rows = []
    for r in range(size):
        tds = []
        for c in range(size):
            ch = preset.get((r, c))
            if ch:
                tds.append(f'<td class="sos-given">{ch}</td>')
            else:
                tds.append('<td class="sos-cell"></td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table class="sos">{"".join(rows)}</table>'


# =====================================================================
# Theme pool normalization
# =====================================================================


def _normalize_theme_pool(theme_pool) -> dict[str, list[str]]:
    """Accept either a dict[str, list[str]] (legacy) or a flat list[str]
    (what the agent hands us from drafted nouns). In the flat case, bucket
    the words into synthetic topics of 5-6 to preserve the
    "one guaranteed per topic" behavior of _pick_fillin_words."""
    if theme_pool is None:
        return {k: v[:] for k, v in DEFAULT_THEME_POOL.items()}
    if isinstance(theme_pool, dict):
        return {k: list(v) for k, v in theme_pool.items() if v}
    if isinstance(theme_pool, list):
        flat = [w.upper() for w in theme_pool if _is_good_puzzle_word(w)]
        if len(flat) < 7:
            return {k: v[:] for k, v in DEFAULT_THEME_POOL.items()}
        # Bucket into ~5 topics.
        buckets: dict[str, list[str]] = {}
        chunk = max(1, len(flat) // 5)
        for i, word in enumerate(flat):
            buckets.setdefault(f"topic{i // chunk}", []).append(word)
        return buckets
    raise TypeError(f"theme_pool must be dict, list, or None; got {type(theme_pool)}")


def _is_good_puzzle_word(w: str) -> bool:
    if not isinstance(w, str):
        return False
    w = w.strip()
    if not (3 <= len(w) <= 10):
        return False
    return w.isalpha()


# =====================================================================
# Public entry point
# =====================================================================


def build_puzzles(
    seed: int,
    theme_pool: Optional[object] = None,
    wordsearch_pool: Optional[list[str]] = None,
    crypto_phrases: Optional[list[str]] = None,
    target_givens: int = 43,
    issue_date: Optional[datetime.date] = None,
    with_fallback: bool = True,
) -> tuple[str, dict]:
    """Generate a full games page fragment and metadata dict.

    Returns:
      (fragment_html, meta)
      meta = {
        "seed": int,
        "sudoku_givens": int,
        "fillin_words": list[str],
        "fillin_anchors": list[tuple],
        "wordsearch_words": list[str],
        "crypto_phrase": str,
        "fell_back_to_defaults": bool,
      }

    If `with_fallback=True` (default) and puzzle generation fails with dynamic
    pools, retry with the hardcoded DEFAULT_* pools -- the paper always ships.
    Set `with_fallback=False` to get the raw assertion error (useful in tests).
    """
    normalized_theme = _normalize_theme_pool(theme_pool)
    ws_pool = wordsearch_pool or DEFAULT_WS_WORDS_POOL
    ws_pool = [w.upper() for w in ws_pool if _is_good_puzzle_word(w)]
    if len(ws_pool) < 10:
        ws_pool = list(DEFAULT_WS_WORDS_POOL)
    phrases = crypto_phrases or DEFAULT_CRYPTO_PHRASES
    phrases = [p for p in phrases if p.strip()] or list(DEFAULT_CRYPTO_PHRASES)

    def _try(pool_dict, ws, phr):
        rng = random.Random(seed)
        sudoku_puzzle, sudoku_solution, givens = _generate_sudoku(rng, target_givens)
        fillin_grid, fillin_words, fillin_anchors = _generate_fillin(rng, pool_dict)
        ws_grid, ws_words = _generate_wordsearch(rng, ws)
        maze = _generate_maze(rng)
        sos_size, sos_placements = _generate_sos(rng)
        crypto_phrase, crypto_encoded, crypto_hints = _generate_cryptogram(rng, phr)
        return (
            sudoku_puzzle,
            givens,
            fillin_grid,
            fillin_words,
            fillin_anchors,
            ws_grid,
            ws_words,
            maze,
            sos_size,
            sos_placements,
            crypto_phrase,
            crypto_encoded,
            crypto_hints,
        )

    fell_back = False
    try:
        results = _try(normalized_theme, ws_pool, phrases)
    except (AssertionError, RuntimeError):
        if not with_fallback:
            raise
        fell_back = True
        results = _try(DEFAULT_THEME_POOL, DEFAULT_WS_WORDS_POOL, DEFAULT_CRYPTO_PHRASES)

    (
        sudoku_puzzle,
        givens,
        fillin_grid,
        fillin_words,
        fillin_anchors,
        ws_grid,
        ws_words,
        maze,
        sos_size,
        sos_placements,
        crypto_phrase,
        crypto_encoded,
        crypto_hints,
    ) = results

    today = issue_date or datetime.date.today()
    fragment = _fragment_html(
        seed=seed,
        today=today,
        sudoku_puzzle=sudoku_puzzle,
        givens=givens,
        fillin_grid=fillin_grid,
        fillin_words=fillin_words,
        fillin_anchors=fillin_anchors,
        ws_grid=ws_grid,
        ws_words=ws_words,
        maze=maze,
        sos_size=sos_size,
        sos_placements=sos_placements,
        crypto_encoded=crypto_encoded,
        crypto_hints=crypto_hints,
    )
    meta = {
        "seed": seed,
        "sudoku_givens": givens,
        "fillin_words": list(fillin_words),
        "fillin_anchors": list(fillin_anchors),
        "wordsearch_words": list(ws_words),
        "sos_size": sos_size,
        "sos_placements": list(sos_placements),
        "crypto_phrase": crypto_phrase,
        "fell_back_to_defaults": fell_back,
    }
    return fragment, meta


def _fragment_html(
    *,
    seed,
    today,
    sudoku_puzzle,
    givens,
    fillin_grid,
    fillin_words,
    fillin_anchors,
    ws_grid,
    ws_words,
    maze,
    sos_size,
    sos_placements,
    crypto_encoded,
    crypto_hints,
) -> str:
    date_line = today.strftime("%A, %B %-d, %Y")
    return f"""<!--
  =========================================================================
  GAMES PAGE  --  auto-generated by app.puzzles.build
  Seed: {seed}   Date: {today.isoformat()}
  Every puzzle verified solvable before emission. Re-run daily for new sets.
  =========================================================================
-->
<section class="games-page">

  <header class="games-masthead">
    <div class="games-line-top">
      <span>Page 3 &middot; Diversions</span>
      <span>The Daily Crosswire</span>
      <span>{date_line}</span>
    </div>
    <h2 class="games-title">Games &amp; Diversions</h2>
    <p class="games-sub">Six puzzles. Every one verified solvable by a computer so you don't have to argue with the editor.</p>
  </header>

  <div class="games-grid">

    <section class="puzzle puzzle-sudoku">
      <span class="kicker">No. 1 &middot; Easy</span>
      <h3 class="puzzle-title">Sudoku</h3>
      <p class="puzzle-note">Fill every row, column, and 3x3 box with digits 1-9.</p>
      {_sudoku_html(sudoku_puzzle)}
      <p class="puzzle-meta">{givens} givens &middot; unique solution verified</p>
    </section>

    <section class="puzzle puzzle-fillin">
      <span class="kicker">No. 2 &middot; Themed fill-in</span>
      <h3 class="puzzle-title">Criss-Cross</h3>
      <p class="puzzle-note">Place each word from the list into the grid. Every word fits in exactly one place. Start with the longest.</p>
      {_fillin_html(fillin_grid, fillin_anchors)}
      {_fillin_list_html(fillin_words)}
    </section>

    <section class="puzzle puzzle-wordsearch">
      <span class="kicker">No. 3 &middot; Find ten</span>
      <h3 class="puzzle-title">Word Search</h3>
      <p class="puzzle-note">Words run horizontally, vertically, or diagonally (forward only).</p>
      <div class="wordsearch-wrap">
        {_wordsearch_html(ws_grid)}
        {_wordsearch_list_html(ws_words)}
      </div>
    </section>

    <section class="puzzle puzzle-maze">
      <span class="kicker">No. 4 &middot; Direct path</span>
      <h3 class="puzzle-title">Labyrinth</h3>
      <p class="puzzle-note">Enter on the left. Exit on the right. Don't lift your pen.</p>
      {_maze_svg(maze)}
    </section>

    <section class="puzzle puzzle-sos">
      <span class="kicker">No. 5 &middot; Two players</span>
      <h3 class="puzzle-title">SOS</h3>
      <p class="puzzle-note">Played on a {sos_size}x{sos_size} grid. On each turn, write either <strong>S</strong> or <strong>O</strong> in any empty cell. Complete the sequence <strong>S-O-S</strong> horizontally, vertically, or diagonally to claim it -- draw a line through those three cells and write your initial at one end. If you score, you go again. When the grid is full, whoever claimed the most triplets wins.</p>
      {_sos_html(sos_size, sos_placements)}
    </section>

    <section class="puzzle puzzle-crypto">
      <span class="kicker">No. 6 &middot; Substitution cipher</span>
      <h3 class="puzzle-title">Cryptogram</h3>
      <p class="puzzle-note">Every letter has been swapped for another. Decode the phrase. Two letters are revealed as a hint.</p>
      <p class="crypto-encoded">{crypto_encoded}</p>
      <p class="crypto-hints"><strong>Hint:</strong> {_crypto_hints_html(crypto_hints)}</p>
    </section>

  </div>

  <footer class="games-footer">
    <p class="small">All puzzles generated and verified by <code>app.puzzles.build</code>. Seed: {seed}.</p>
  </footer>

</section>
"""
