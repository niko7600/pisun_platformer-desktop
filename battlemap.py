# -*- coding: utf-8 -*-
"""Предначертанная карта режима «Битва за Писюн».

Карта одна и та же при каждом запуске (фиксированный сид и фиксированный порядок сегментов),
но собрана из тех же проверенных деталей, что и генерация: леса, дома, лифт, мост, каркас.
Враги и гайки убраны, зато много шипов и бронированных зданий. Последний участок — площадь
с площадкой стройки, где потом пройдёт битва с боссом.
Модуль не зависит от pygame.
"""
import levelgen
from levelgen import (Builder, SEGS, TILE, DISTRICTS, analyze, _pick_bricks)

BATTLE_SEED = 20261020


# ---------------------------------------------------------------------------
# Новые сегменты
# ---------------------------------------------------------------------------
def seg_start(b, x, d):
    """Койка героя, лампа и первое знакомство с шипами."""
    g = b.g
    b.prop("cot", 2)
    b.prop("lamp", 6)
    b.prop("sign", 9)
    for c in (13, 14):
        b.spike(c)
    b.plank(12, g - 2, 5, "pallet")
    b.brick(14, g - 2, 1)
    b.prop("cone", 11)
    return 19


def seg_armor(b, x, d, w=6, h=5):
    """Бронированное здание: стальные плиты, щели-бойницы. Лестница слева, на крыше шипы и блоки."""
    g = b.g
    left = x + 1
    roof = g - h
    b.solid(left, roof, w, h, "armor")
    b.ladder(x, roof, g)
    b.plank(x, roof, 1, "ledge")
    b.brick(left + 1, roof, 2 if h >= 7 else 1)
    if w >= 6:
        b.L.spikes.append((left + 3, roof))
        b.L.spikes.append((left + 4, roof))
        b.brick(left + w - 1, roof, 2 if h >= 6 else 1)
    else:
        b.brick(left + w - 1, roof, 1)
    b.spike(left + w + 2)
    b.spike(left + w + 3)
    b.prop("cone", left + w + 1)
    return left + w + 5


def seg_spikefield(b, x, d):
    """Шиповое поле: три группы шипов, через две из них — доски с блоками."""
    g = b.g
    c = x + 2
    for i, gw in enumerate((2, 3, 2, 3)):
        for k in range(gw):
            b.spike(c + k)
        if i in (0, 2, 3):
            b.plank(c - 1, g - 2, gw + 2, "pallet")
            if i != 2:
                b.brick(c + gw // 2, g - 2, 1)
        c += gw + 3
    b.prop("sign", x + 1)
    return c


def seg_spikehop(b, x, d):
    """Короткий прыжок через шипы, блок висит над ними."""
    g = b.g
    a = x + 2
    for k in range(3):
        b.spike(a + k)
    b.brick(a + 1, g - 1.4, 1, node=(a - 1, g))
    b.prop("cone", a - 1)
    b.prop("barrel", a + 4)
    return a + 5


# ---------------------------------------------------------------------------
PLAN = (
    # район 0: СТРОЙПЛОЩАДКА
    ("start", 0.0, {}),
    ("spikes", 0.35, {}),
    ("scaffold", 0.35, {}),
    ("armor", 0.4, dict(w=6, h=4)),
    ("spikefield", 0.5, {}),
    # район 1: ДЕЛОВОЙ ЦЕНТР
    ("skyline", 0.6, {}),
    ("armor", 0.6, dict(w=6, h=8)),
    ("elevator", 0.5, {}),
    ("spikehop", 0.6, {}),
    ("frame", 0.6, {}),
    # район 2: ПРОМЗОНА
    ("pit_moving", 0.7, {}),
    ("spikefield", 0.8, {}),
    ("armor", 0.8, dict(w=7, h=5)),
    ("scaffold", 0.9, {}),
    ("spikes", 0.9, {}),
)
DISTRICT_AT = (0, 5, 10)               # номера сегментов, с которых начинается район
CHECKPOINT_AFTER = (3, 6, 9, 12)

ALL_SEGS = dict(SEGS)
ALL_SEGS.update({"start": seg_start, "armor": seg_armor, "spikefield": seg_spikefield,
                 "spikehop": seg_spikehop})


def _arena_scaffold(b, lo, hi):
    """Двухэтажные леса на площади: убежище от атак по земле."""
    g = b.g
    spans = [(lo, hi), (lo, hi), (lo + 1, hi - 1)]
    for i in (1, 2):
        slo, shi = spans[i]
        row = g - 3 * i
        b.plank(slo, row, shi - slo + 1, "scaf")
    b.ladder(lo, g - 3, g)
    b.ladder(hi - 1, g - 6, g - 3)
    b.deco("scaf", [list(s) for s in spans], 2, g)


def build_battle_level():
    b = Builder(BATTLE_SEED)
    r, L, g = b.rng, b.L, b.g
    L.mode = "battle"
    L.spawn = (4.4, g - 2)
    x = 0
    cur = -1
    for i, (name, d, kw) in enumerate(PLAN):
        pal = 0
        for k, st in enumerate(DISTRICT_AT):
            if i >= st:
                pal = k
        if pal != cur:
            L.districts.append((x, DISTRICTS[pal], pal))
            cur = pal
        b.pal = pal
        b.d = d
        x = ALL_SEGS[name](b, x, d, **kw) if kw else ALL_SEGS[name](b, x, d)
        if i in CHECKPOINT_AFTER:
            L.checkpoints.append(x)
        x += 1 if name == "start" else r.choice((2, 2, 3))
    # площадь с площадкой стройки
    b.pal = 2
    L.zone_tx = x + 10
    L.cols = L.zone_tx + 34
    _pick_bricks(b)
    L.bolts = []
    L.foremen = []
    L.pigeons = []
    if len(L.hearts) < 5:
        for cp in L.checkpoints:
            if len(L.hearts) >= 5:
                break
            b.heart(cp + 1, g)
    # декорации площади
    _arena_scaffold(b, L.zone_tx - 12, L.zone_tx - 4)
    _arena_scaffold(b, L.zone_tx + 14, L.zone_tx + 22)
    for c in (L.zone_tx - 14, L.zone_tx + 25, L.zone_tx + 30):
        b.prop("cone", c)
    b.prop("lamp", L.zone_tx - 2)
    b.prop("lamp", L.zone_tx + 12)
    b.prop("barrel", L.zone_tx + 27)
    # земля: всё, кроме ям
    pos = -8
    for (a, bb) in sorted(b.gaps):
        if a > pos:
            b.solid(pos, g, a - pos, levelgen.ROWS - g, "ground", 0)
        pos = bb
    b.solid(pos, g, L.cols + 8 - pos, levelgen.ROWS - g, "ground", 2)
    L.seed = BATTLE_SEED
    L.report = analyze(L)
    return L


if __name__ == "__main__":
    L = build_battle_level()
    print("cols", L.cols, "bricks", len(L.bricks), "hearts", len(L.hearts), "spikes", len(L.spikes),
          "ladders", len(L.ladders), "moving", len(L.moving), "cp", L.checkpoints, "zone", L.zone_tx)
    print(L.report)
