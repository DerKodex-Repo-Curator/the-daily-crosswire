"""Tests for the puzzle generator. Covers determinism, solvability, and the
fallback to default pools when a dynamic theme pool is too sparse."""

import pytest

from app.puzzles.build import (
    DEFAULT_THEME_POOL,
    build_puzzles,
    _sudoku_solve_count,
    _count_fillin_solutions,
    _ws_find,
    _maze_solvable,
)
from app.puzzles.nouns import extract_theme_pool

SEED = 20260418


def test_build_puzzles_with_defaults_is_deterministic():
    frag1, meta1 = build_puzzles(seed=SEED)
    frag2, meta2 = build_puzzles(seed=SEED)
    assert frag1 == frag2
    assert meta1 == meta2


def test_build_puzzles_different_seeds_produce_different_output():
    frag1, _ = build_puzzles(seed=SEED)
    frag2, _ = build_puzzles(seed=SEED + 1)
    assert frag1 != frag2


def test_fragment_contains_all_six_puzzle_sections():
    frag, _ = build_puzzles(seed=SEED)
    for expected in (
        "puzzle-sudoku",
        "puzzle-fillin",
        "puzzle-wordsearch",
        "puzzle-maze",
        "puzzle-sos",
        "puzzle-crypto",
    ):
        assert expected in frag, f"missing section: {expected}"


def test_all_puzzles_verified_solvable_in_meta():
    """Build, then cross-check solvability via the internal verifiers."""
    from app.puzzles import build as bmod

    import random

    rng = random.Random(SEED)
    sudoku_puzzle, _, givens = bmod._generate_sudoku(rng, target_givens=54)
    assert _sudoku_solve_count([r[:] for r in sudoku_puzzle], limit=2) == 1
    assert givens >= 17  # theoretical minimum for unique sudoku

    grid, words, anchors = bmod._generate_fillin(rng, DEFAULT_THEME_POOL)
    shape = [["." if ch != "#" else "#" for ch in row] for row in grid]
    for r, c in anchors:
        shape[r][c] = grid[r][c]
    assert _count_fillin_solutions(shape, words, limit=2) == 1

    ws_grid, ws_words = bmod._generate_wordsearch(rng, list(DEFAULT_THEME_POOL["tech"]) * 3)
    for w in ws_words:
        assert _ws_find(ws_grid, w)

    maze = bmod._generate_maze(rng)
    assert _maze_solvable(maze)


def test_dynamic_theme_pool_from_agent_drafts():
    drafts = [
        {
            "rendered_title": "Chipworks releases new reasoning model",
            "body": "Chipworks announced a new model today. The system supports a reasoning mode called Thinker. Users running Python and Rust should see benefits in code tasks.",
            "topic_name": "Tech",
        },
        {
            "rendered_title": "Harborside ships holiday console bundle",
            "body": "Harborside launched a holiday bundle today. The Forest, Depths, and Skyline titles each received updated editions. Retailers report strong preorder numbers for the console and its handheld mode.",
            "topic_name": "Games",
        },
    ]
    topic_names = ["Tech", "Games"]
    pool = extract_theme_pool(drafts, topic_names)
    # Topic shorthand and capitalized proper nouns should dominate.
    assert "CHIPWORKS" in pool or "THINKER" in pool or "MODEL" in pool
    assert "HARBORSIDE" in pool or "FOREST" in pool or "SKYLINE" in pool


def test_build_puzzles_accepts_flat_list_theme_pool():
    """The agent hands us a flat list from the noun extractor. The builder
    should bucket it internally and still produce valid puzzles."""
    flat_pool = [
        "CHIPWORKS",
        "MODEL",
        "AGENT",
        "SERVER",
        "TOKEN",
        "CLOUD",
        "SWITCH",
        "PIXEL",
        "QUEST",
        "STEAM",
        "MOUSE",
        "EPISODE",
        "SEASON",
        "STREAM",
        "SHOW",
        "MATCH",
        "ROUND",
        "FINAL",
        "TEAM",
        "HARBOR",
        "BRIDGE",
        "TRANSIT",
        "MAYOR",
    ]
    frag, meta = build_puzzles(seed=SEED, theme_pool=flat_pool)
    assert frag
    assert len(meta["fillin_words"]) >= 5


def test_build_puzzles_falls_back_on_unbuildable_pool():
    """A pathological pool (too few usable words) should trigger the
    fallback to DEFAULT_THEME_POOL instead of raising."""
    frag, meta = build_puzzles(
        seed=SEED,
        theme_pool=["AB", "CD"],  # all too short -> normalization will use defaults
    )
    assert frag
    # Either the normalizer fell back preemptively (good) or the builder did.
    # Either way the fill-in words come from DEFAULT_THEME_POOL.
    default_words = {w for topic in DEFAULT_THEME_POOL.values() for w in topic}
    assert set(meta["fillin_words"]).issubset(default_words)


def test_build_puzzles_normalizer_is_defensive():
    """A too-small pool trips the normalizer's preemptive fallback to
    DEFAULT_THEME_POOL, so even with_fallback=False the run succeeds."""
    frag, meta = build_puzzles(
        seed=SEED,
        theme_pool=["AB", "CD", "EF"],  # too-short words, normalizer rejects
        with_fallback=False,
    )
    assert frag
    default_words = {w for topic in DEFAULT_THEME_POOL.values() for w in topic}
    assert set(meta["fillin_words"]).issubset(default_words)
