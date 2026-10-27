# -*- coding: utf-8 -*-
"""Отрисовка сгенерированного города в кэш-полосы (рисуется один раз при загрузке уровня)."""
import math
import pygame

TILE = 36
STRIP_W = 768          # ширина одной полосы кэша, px
PAD = 340              # запас по краям мира
KEY = (255, 0, 255)
BLACK = (20, 20, 30)
WHITE = (255, 255, 255)
RED = (235, 64, 72)
YELLOW = (255, 204, 64)
ORANGE = (255, 133, 51)

# палитры районов: 0 — стройплощадка, 1 — деловой центр, 2 — промзона
PALS = (
    dict(wall=(196, 112, 80), wall_dk=(150, 82, 56), wall_lt=(222, 146, 108), win_on=(255, 228, 150),
         win_off=(86, 104, 134), frame=(110, 62, 44), roof=(120, 70, 50), trim=(232, 178, 128),
         block=(208, 162, 112), soil=(140, 98, 64), soil_dk=(122, 84, 55), edge=(100, 68, 44),
         top=(96, 178, 92), top_dk=(70, 140, 66), glass=False),
    dict(wall=(96, 132, 176), wall_dk=(66, 96, 138), wall_lt=(132, 168, 210), win_on=(196, 232, 255),
         win_off=(44, 70, 108), frame=(40, 58, 90), roof=(205, 214, 228), trim=(240, 246, 252),
         block=(172, 180, 196), soil=(104, 108, 124), soil_dk=(88, 92, 108), edge=(66, 70, 86),
         top=(158, 164, 178), top_dk=(126, 132, 148), glass=True),
    dict(wall=(142, 144, 152), wall_dk=(104, 106, 114), wall_lt=(172, 174, 182), win_on=(255, 208, 96),
         win_off=(58, 62, 74), frame=(52, 54, 62), roof=(84, 86, 94), trim=(240, 200, 40),
         block=(152, 154, 162), soil=(92, 94, 104), soil_dk=(78, 80, 90), edge=(58, 60, 70),
         top=(118, 124, 134), top_dk=(92, 98, 108), glass=False),
)
STEEL = (150, 158, 172)
STEEL_DK = (96, 102, 116)
ORANGE_STEEL = (230, 145, 60)
ORANGE_DK = (170, 100, 40)


class _P:
    """Рисовалка с переводом мировых координат в координаты полосы."""
    __slots__ = ("s", "ox", "oy", "x0", "x1")

    def rect(self, col, x, y, w, h, width=0):
        pygame.draw.rect(self.s, col, (x + self.ox, y + self.oy, w, h), width)

    def line(self, col, a, b, width=1):
        pygame.draw.line(self.s, col, (a[0] + self.ox, a[1] + self.oy), (b[0] + self.ox, b[1] + self.oy), width)

    def poly(self, col, pts, width=0):
        pygame.draw.polygon(self.s, col, [(x + self.ox, y + self.oy) for x, y in pts], width)

    def circle(self, col, c, r, width=0):
        pygame.draw.circle(self.s, col, (int(c[0] + self.ox), int(c[1] + self.oy)), r, width)


class _Canvas:
    def __init__(self, strips, y0):
        self.strips = strips
        self.y0 = y0
        self.p = _P()

    def each(self, xa, xb, fn, *args):
        p = self.p
        for sx0, surf in self.strips:
            if xb >= sx0 and xa <= sx0 + STRIP_W:
                p.s = surf
                p.ox = -sx0
                p.oy = -self.y0
                p.x0 = sx0
                p.x1 = sx0 + STRIP_W
                fn(p, *args)


def _hash(a, b):
    return ((a * 73856093) ^ (b * 19349663)) & 0x7FFFFFFF


# ---------------------------------------------------------------------------
# твёрдые блоки
# ---------------------------------------------------------------------------
def _district_pal(L, tx):
    pal = 0
    for (st, _n, pl) in L.districts:
        if tx >= st:
            pal = pl
    return pal


def _ground(p, L, tx, ty, tw, th):
    g = L.ground_row
    c0 = max(tx, p.x0 // TILE - 1)
    c1 = min(tx + tw - 1, p.x1 // TILE + 1)
    for c in range(c0, c1 + 1):
        pl = PALS[_district_pal(L, c)]
        for r in range(ty, ty + th):
            x, y = c * TILE, r * TILE
            hsh = _hash(c, r)
            if r == g:
                if pl["glass"]:
                    p.rect(pl["top"], x, y, TILE, 10)
                    p.rect(pl["top_dk"], x, y + 8, TILE, 3)
                    p.rect(pl["soil"], x, y + 10, TILE, TILE - 10)
                    if c % 2 == 0:
                        p.rect(pl["top_dk"], x, y, 2, 10)
                elif pl["top"][0] > 110 and pl["top"][1] < 130:
                    p.rect(pl["top"], x, y, TILE, 10)
                    p.rect(pl["top_dk"], x, y + 8, TILE, 3)
                    p.rect(pl["soil"], x, y + 10, TILE, TILE - 10)
                    if c % 3 == 0:
                        p.rect(YELLOW, x + 6, y + 3, 14, 3)
                else:
                    p.rect(pl["top"], x, y, TILE, 10)
                    p.rect(pl["top_dk"], x, y + 8, TILE, 3)
                    p.rect(pl["soil"], x, y + 10, TILE, TILE - 10)
            else:
                p.rect(pl["soil_dk"], x, y, TILE, TILE)
            p.rect(pl["edge"], x, y, TILE, TILE, 1)
            if hsh % 5 == 0:
                p.rect(pl["edge"], x + 7 + hsh % 17, y + 16, 7, 4)


def _building(p, L, tx, ty, tw, th, pal, mode=0):
    """mode: 0 — всё сразу (день); 1 — без окон (ночная основа); 2 — только окна (поверх затемнения)."""
    pl = PALS[pal]
    x, y, w, h = tx * TILE, ty * TILE, tw * TILE, th * TILE
    if x + w < p.x0 - 8 or x > p.x1 + 8:
        return
    if mode == 2:
        _building_windows(p, L, tx, ty, tw, th, pal, x, y)
        return
    p.rect(pl["wall"], x, y, w, h)
    p.rect(pl["wall_lt"], x, y, 4, h)
    p.rect(pl["wall_dk"], x + w - 7, y, 7, h)
    grounded = (ty + th) == L.ground_row
    door_c = tw // 2
    for r in range(1, th):
        p.rect(pl["wall_dk"], x, y + r * TILE - 2, w, 3)
    for r in range(1, th):
        for c in range(tw):
            wx, wy = x + c * TILE, y + r * TILE
            if wx + TILE < p.x0 or wx > p.x1:
                continue
            if grounded and r == th - 1 and c == door_c:
                p.rect(BLACK, wx + 8, wy + 8, 20, 28)
                p.rect((90, 62, 44), wx + 10, wy + 10, 16, 26)
                p.circle(YELLOW, (wx + 23, wy + 24), 2)
                continue
            if mode == 1:
                continue
            lit = _hash(tx + c, ty + r) % 3 != 0
            if pl["glass"]:
                p.rect(pl["win_on"] if lit else pl["win_off"], wx + 5, wy + 6, 26, 20)
                p.rect(pl["frame"], wx + 5, wy + 6, 26, 20, 2)
                if lit:
                    p.line(WHITE, (wx + 9, wy + 22), (wx + 18, wy + 10), 2)
            else:
                p.rect(pl["win_on"] if lit else pl["win_off"], wx + 9, wy + 8, 18, 16)
                p.rect(pl["frame"], wx + 9, wy + 8, 18, 16, 2)
                p.line(pl["frame"], (wx + 18, wy + 8), (wx + 18, wy + 24), 2)
                if pal == 2 and c == 0:
                    p.rect((120, 84, 70), wx + 2, wy + 2, 4, TILE - 2)
    # парапет и карниз
    p.rect(pl["roof"], x - 3, y - 2, w + 6, 11)
    p.rect(pl["trim"], x - 3, y - 2, w + 6, 3)
    p.rect(BLACK, x - 3, y - 2, w + 6, 11, 2)
    if pal == 2:
        for k in range(0, w, 14):
            p.poly((240, 200, 40), [(x + k, y + 9), (x + k + 7, y + 9), (x + k + 14, y + 16), (x + k + 7, y + 16)])
    p.rect(BLACK, x, y, w, h, 2)


def _building_windows(p, L, tx, ty, tw, th, pal, x, y):
    """Ночные окна: часть горит тёплым светом, часть тёмная. Рисуется после затемнения."""
    pl = PALS[pal]
    grounded = (ty + th) == L.ground_row
    door_c = tw // 2
    for r in range(1, th):
        for c in range(tw):
            wx, wy = x + c * TILE, y + r * TILE
            if wx + TILE < p.x0 or wx > p.x1:
                continue
            if grounded and r == th - 1 and c == door_c:
                p.rect((26, 20, 24), wx + 8, wy + 8, 20, 28)
                p.rect((120, 84, 56), wx + 10, wy + 10, 16, 26)
                p.circle((255, 226, 120), (wx + 23, wy + 24), 2)
                continue
            lit = _hash(tx + c, ty + r) % 3 != 0
            on = (255, 226, 140) if not pl["glass"] else (196, 232, 255)
            off = (28, 36, 62)
            fr = (24, 30, 52)
            if pl["glass"]:
                p.rect(on if lit else off, wx + 5, wy + 6, 26, 20)
                p.rect(fr, wx + 5, wy + 6, 26, 20, 2)
                if lit:
                    p.line((255, 255, 255), (wx + 9, wy + 22), (wx + 18, wy + 10), 2)
            else:
                p.rect(on if lit else off, wx + 9, wy + 8, 18, 16)
                p.rect(fr, wx + 9, wy + 8, 18, 16, 2)
                p.line(fr, (wx + 18, wy + 8), (wx + 18, wy + 24), 2)


def _armor(p, L, tx, ty, tw, th, pal, mode=0):
    """Бронированное здание: клёпаные стальные плиты, бойницы, полосатый карниз, блок-люк."""
    x, y, w, h = tx * TILE, ty * TILE, tw * TILE, th * TILE
    if x + w < p.x0 - 8 or x > p.x1 + 8:
        return
    if mode == 2:
        # светящиеся бойницы и сигнальная лампа
        for r in range(1, th):
            for c in range(tw):
                wx, wy = x + c * TILE, y + r * TILE
                if wx + TILE < p.x0 or wx > p.x1:
                    continue
                if (L.ground_row == ty + th) and r == th - 1 and c == tw // 2:
                    continue
                if (c + r + tx) % 2 == 0:
                    p.rect((255, 150, 60), wx + 6, wy + 13, TILE - 12, 5)
                    p.rect((255, 220, 140), wx + 8, wy + 14, TILE - 16, 2)
        p.circle((255, 70, 60), (x + w // 2, y - 8), 4)
        return
    base, dk, lt = (96, 104, 120), (62, 68, 82), (132, 140, 156)
    p.rect(base, x, y, w, h)
    for r in range(th):
        for c in range(tw):
            px, py = x + c * TILE, y + r * TILE
            if px + TILE < p.x0 or px > p.x1:
                continue
            p.rect(lt, px, py, TILE, 3)
            p.rect(dk, px, py + TILE - 4, TILE, 4)
            p.rect(dk, px, py, 2, TILE)
            for (ax, ay) in ((5, 7), (TILE - 7, 7), (5, TILE - 9), (TILE - 7, TILE - 9)):
                p.circle((176, 184, 198), (px + ax, py + ay), 2)
                p.circle((50, 54, 66), (px + ax, py + ay), 2, 1)
    grounded = (ty + th) == L.ground_row
    for r in range(1, th):
        for c in range(tw):
            wx, wy = x + c * TILE, y + r * TILE
            if wx + TILE < p.x0 or wx > p.x1:
                continue
            if grounded and r == th - 1 and c == tw // 2:
                p.rect((36, 40, 50), wx + 4, wy + 6, TILE - 8, TILE - 6)
                p.rect((74, 80, 94), wx + 7, wy + 9, TILE - 14, TILE - 12)
                p.line((36, 40, 50), (wx + 7, wy + 9), (wx + TILE - 7, wy + TILE - 3), 3)
                p.line((36, 40, 50), (wx + TILE - 7, wy + 9), (wx + 7, wy + TILE - 3), 3)
                continue
            p.rect((24, 26, 34), wx + 5, wy + 12, TILE - 10, 8)
            if (c + r + tx) % 2 != 0:
                p.rect((40, 44, 56), wx + 7, wy + 14, TILE - 14, 4)
    # диагональные распорки на боках
    p.line(dk, (x + 2, y + 6), (x + w - 3, y + h - 6), 2)
    # полосатый карниз
    p.rect((46, 50, 62), x - 4, y - 4, w + 8, 14)
    for k in range(0, w + 8, 16):
        p.poly((240, 200, 40), [(x - 4 + k, y - 4), (x + 4 + k, y - 4), (x + 12 + k, y + 10), (x + 4 + k, y + 10)])
    p.rect(BLACK, x - 4, y - 4, w + 8, 14, 2)
    p.rect(BLACK, x, y, w, h, 2)


def _block(p, tx, ty, tw, th, pal):
    pl = PALS[pal]
    for r in range(ty, ty + th):
        for c in range(tx, tx + tw):
            x, y = c * TILE, r * TILE
            if x + TILE < p.x0 or x > p.x1:
                continue
            p.rect(pl["block"], x, y, TILE, TILE)
            p.rect(pl["wall_lt"], x, y, TILE, 5)
            p.rect(pl["wall_dk"], x, y + TILE - 7, TILE, 7)
            p.rect(pl["edge"], x, y, TILE, TILE, 2)
            p.circle(pl["edge"], (x + 6, y + 8), 2)
            p.circle(pl["edge"], (x + TILE - 6, y + 8), 2)


def _crate(p, tx, ty, tw, th):
    for r in range(ty, ty + th):
        x, y = tx * TILE, r * TILE
        p.rect((176, 124, 66), x, y, TILE, TILE)
        p.rect((146, 98, 48), x, y + TILE - 9, TILE, 9)
        p.rect((120, 78, 38), x, y, TILE, TILE, 2)
        p.line((130, 86, 42), (x + 3, y + 3), (x + TILE - 4, y + TILE - 4), 3)
        p.line((130, 86, 42), (x + TILE - 4, y + 3), (x + 3, y + TILE - 4), 3)


def _chimney(p, tx, ty, tw, th):
    x, y = tx * TILE, ty * TILE
    p.rect((168, 84, 62), x + 4, y + 8, TILE - 8, th * TILE - 8)
    for k in range(y + 14, y + th * TILE, 12):
        p.rect((130, 62, 46), x + 4, k, TILE - 8, 2)
    p.rect((74, 74, 86), x, y, TILE, 10)
    p.rect(BLACK, x, y, TILE, 10, 2)
    p.rect(BLACK, x + 4, y + 8, TILE - 8, th * TILE - 8, 2)


# ---------------------------------------------------------------------------
# тонкие платформы, лестницы
# ---------------------------------------------------------------------------
def _plank(p, tx, ty, tw, style, pal):
    pl = PALS[pal]
    x, y, w = tx * TILE, ty * TILE, tw * TILE
    if x + w < p.x0 or x > p.x1:
        return
    if style == "slab":
        p.rect((172, 174, 184), x, y, w, 5)
        p.rect((138, 140, 150), x, y + 5, w, 8)
        p.rect(BLACK, x, y, w, 13, 2)
        for k in range(x + 10, x + w - 6, 24):
            p.line((90, 70, 60), (k, y + 13), (k, y + 20), 2)
    elif style == "pallet":
        p.rect((214, 174, 104), x, y, w, 12)
        for k in range(x + 12, x + w, 18):
            p.rect((150, 112, 60), k, y, 3, 12)
        p.rect(BLACK, x, y, w, 12, 2)
    elif style == "ledge":
        p.rect((124, 130, 146), x, y, w, 7)
        for k in range(x + 3, x + w - 2, 6):
            p.rect(STEEL_DK, k, y + 1, 2, 5)
        p.rect(BLACK, x, y, w, 8, 2)
    elif style == "balcony":
        p.rect((124, 130, 146), x, y, w, 8)
        p.rect(BLACK, x, y, w, 8, 2)
        p.line(STEEL, (x, y - 24), (x + w, y - 24), 3)
        for k in range(x + 2, x + w, TILE // 2):
            p.line(STEEL, (k, y - 24), (k, y), 2)
    else:  # scaf
        p.rect((178, 126, 68), x, y, w, 9)
        p.rect((122, 80, 40), x, y + 9, w, 3)
        for k in range(x + 18, x + w, 36):
            p.line((120, 80, 40), (k, y), (k, y + 9), 1)
        p.rect(BLACK, x, y, w, 12, 2)
        p.rect(ORANGE_DK, x, y, 4, 12)
        p.rect(ORANGE_DK, x + w - 4, y, 4, 12)


def _ladder(p, tx, ty0, ty1):
    x = tx * TILE
    if x + TILE < p.x0 or x > p.x1:
        return
    y0, y1 = ty0 * TILE - 14, ty1 * TILE
    p.rect(STEEL_DK, x + 7, y0, 5, y1 - y0)
    p.rect(STEEL_DK, x + TILE - 12, y0, 5, y1 - y0)
    p.rect(STEEL, x + 8, y0, 3, y1 - y0)
    p.rect(STEEL, x + TILE - 11, y0, 3, y1 - y0)
    for k in range(y0 + 12, y1, 10):
        p.rect((196, 202, 214), x + 9, k, TILE - 18, 3)
        p.rect(STEEL_DK, x + 9, k + 3, TILE - 18, 1)


# ---------------------------------------------------------------------------
# декорации
# ---------------------------------------------------------------------------
def _pole(p, x, y0, y1):
    p.rect(ORANGE_DK, x - 1, y0, 8, y1 - y0)
    p.rect(ORANGE_STEEL, x, y0, 5, y1 - y0)
    p.rect(BLACK, x - 1, y0, 8, y1 - y0, 1)


def _scaffold(p, spans, n, g):
    for i in range(n, 0, -1):
        lo, hi = spans[i]
        xl, xr = lo * TILE + 3, (hi + 1) * TILE - 9
        yt, yb = (g - 3 * i) * TILE, g * TILE
        if xr < p.x0 or xl > p.x1:
            continue
        _pole(p, xl, yt - 6, yb)
        _pole(p, xr, yt - 6, yb)
        yy = (g - 3 * (i - 1)) * TILE
        p.line(ORANGE_DK, (xl + 5, yt + 12), (xr, yy), 3)
        p.line(ORANGE_DK, (xr, yt + 12), (xl + 5, yy), 3)
        p.line(ORANGE_STEEL, (xl + 5, yt + 12), (xr, yy), 1)
        p.line(ORANGE_STEEL, (xr, yt + 12), (xl + 5, yy), 1)
        # сетка-ограждение между этажами
        for k in range(1, 3):
            yk = yt + k * TILE
            p.line((120, 124, 136), (xl + 5, yk), (xr, yk), 1)
    lo, hi = spans[n]
    topy = (g - 3 * n) * TILE
    p.rect(RED, lo * TILE + 12, topy - 28, 54, 16)
    p.rect(WHITE, lo * TILE + 12, topy - 28, 54, 16, 2)


def _frame(p, lo, hi, n, g):
    top = (g - 4 * n) * TILE
    bot = g * TILE
    cols = (lo, (lo + hi) // 2, hi)
    for c in cols:
        x = c * TILE + 9
        if x + 18 < p.x0 or x > p.x1:
            continue
        p.rect((170, 172, 182), x, top, 18, bot - top)
        p.rect((132, 134, 146), x + 12, top, 6, bot - top)
        p.rect(BLACK, x, top, 18, bot - top, 2)
        for k in range(3):
            p.line((120, 80, 60), (x + 4 + k * 5, top), (x + 4 + k * 5, top - 14 - (k % 2) * 6), 2)
    # зелёная сетка на верхнем этаже
    x0 = lo * TILE + 18
    x1 = hi * TILE + 18
    p.rect((70, 150, 90), x0 + 20, top + 14, 60, 30)
    for k in range(0, 60, 8):
        p.line((50, 120, 70), (x0 + 20 + k, top + 14), (x0 + 20 + k, top + 44), 1)
    # кран
    cx = hi * TILE + TILE * 2 - 4
    p.rect((230, 190, 60), cx, top - 120, 7, bot - top + 120)
    p.rect((230, 190, 60), cx - 90, top - 124, 130, 7)
    p.line(STEEL_DK, (cx - 70, top - 117), (cx - 70, top - 70), 2)
    p.rect(STEEL_DK, cx - 80, top - 70, 20, 14)


def _bridge(p, x, gw, br, g):
    xa, xb = x * TILE, (x + gw + 2) * TILE
    if xb < p.x0 or xa > p.x1:
        return
    yt = br * TILE
    for c in (x, x + gw + 1):
        _pole(p, c * TILE + 3, yt, g * TILE)
        _pole(p, c * TILE + TILE - 9, yt, g * TILE)
    for k in range(0, gw + 2, 2):
        a = (x + k) * TILE + 18
        b = (x + k + 1) * TILE + 18
        c2 = (x + k + 2) * TILE + 18
        p.line(ORANGE_DK, (a, yt + 12), (b, yt + 52), 3)
        p.line(ORANGE_DK, (b, yt + 52), (c2, yt + 12), 3)
    p.rect(ORANGE_STEEL, xa, yt + 12, xb - xa, 4)
    p.rect(BLACK, xa, yt + 12, xb - xa, 4, 1)
    # перила
    p.line(ORANGE_STEEL, (xa, yt - 26), (xb, yt - 26), 3)
    for k in range(xa + 4, xb, TILE * 2):
        p.line(ORANGE_STEEL, (k, yt - 26), (k, yt), 2)


def _rails(p, x, rr, g):
    xa = x * TILE
    if xa + 3 * TILE < p.x0 or xa > p.x1:
        return
    for dx in (5, 3 * TILE - 6):
        p.rect(STEEL_DK, xa + dx - 1, rr * TILE - 10, 5, (g - rr) * TILE + 10)
        p.rect(STEEL, xa + dx, rr * TILE - 10, 3, (g - rr) * TILE + 10)
    p.rect((70, 76, 92), xa - 2, rr * TILE - 26, 3 * TILE + 4, 18)
    p.rect(BLACK, xa - 2, rr * TILE - 26, 3 * TILE + 4, 18, 2)
    p.circle(YELLOW, (xa + int(1.5 * TILE), rr * TILE - 17), 5)


def _void(p, L, a, b):
    x, y = a * TILE, L.ground_row * TILE
    w, h = (b - a) * TILE, (L.rows - L.ground_row) * TILE
    if x + w < p.x0 or x > p.x1:
        return
    p.rect((20, 22, 36), x, y, w, h)
    p.rect((34, 38, 58), x, y + h - 14, w, 14)
    for k in range(a, b):
        p.rect((12, 14, 24), k * TILE + 4, y + 10, 5, h - 10)
    # полосатые края ямы
    for (ex, wd) in ((x - 4, 8), (x + w - 4, 8)):
        for k in range(0, 4):
            p.rect(YELLOW if k % 2 == 0 else BLACK, ex, y + k * 9, wd, 9)


def _crane_hook(p, L, col):
    x = col * TILE + TILE // 2
    top = (L.ground_row - 8) * TILE
    hy = (L.ground_row - 4) * TILE
    if x < p.x0 - 40 or x > p.x1 + 40:
        return
    p.rect(ORANGE_STEEL, x - 4, top - 90, 8, 90)
    p.rect(ORANGE_STEEL, x - 70, top - 94, 160, 8)
    p.line(STEEL_DK, (x, top), (x, hy), 3)
    p.poly((200, 60, 60), [(x - 10, hy), (x + 10, hy), (x + 6, hy + 14), (x - 6, hy + 14)])


def _prop(p, name, col, row):
    x = col * TILE + TILE // 2
    y = row * TILE
    if x < p.x0 - 60 or x > p.x1 + 60:
        return
    if name == "cone":
        p.poly(ORANGE, [(x - 10, y), (x, y - 26), (x + 10, y)])
        p.rect(WHITE, x - 6, y - 13, 12, 5)
        p.rect(BLACK, x - 12, y - 3, 24, 4)
    elif name == "cot":
        # койка героя: каркас, матрас, подушка (одеяло рисует игра поверх спящего героя)
        p.rect((80, 86, 100), x - 40, y - 14, 5, 14)
        p.rect((80, 86, 100), x + 36, y - 14, 5, 14)
        p.rect((90, 70, 54), x - 44, y - 24, 90, 10)
        p.rect((220, 226, 238), x - 40, y - 34, 24, 12)
        p.rect(BLACK, x - 40, y - 34, 24, 12, 2)
        p.rect((60, 66, 84), x - 18, y - 29, 62, 5)
        p.rect(BLACK, x - 44, y - 24, 90, 10, 2)
    elif name == "barrel":
        p.rect((190, 66, 54), x - 11, y - 30, 22, 30)
        p.rect((140, 44, 36), x - 11, y - 22, 22, 4)
        p.rect((140, 44, 36), x - 11, y - 10, 22, 4)
        p.rect(BLACK, x - 11, y - 30, 22, 30, 2)
    elif name == "sign":
        p.rect((90, 95, 110), x - 3, y - 54, 6, 54)
        p.poly(YELLOW, [(x - 18, y - 36), (x, y - 70), (x + 18, y - 36)])
        p.poly(BLACK, [(x - 18, y - 36), (x, y - 70), (x + 18, y - 36)], 3)
        p.rect(BLACK, x - 2, y - 60, 4, 12)
        p.rect(BLACK, x - 2, y - 44, 4, 4)
    elif name == "lamp":
        p.rect((80, 86, 100), x - 3, y - 96, 6, 96)
        p.rect((80, 86, 100), x - 3, y - 96, 26, 5)
        p.circle((255, 236, 160), (x + 20, y - 88), 7)
        p.circle(BLACK, (x + 20, y - 88), 7, 2)
    elif name == "ac":
        p.rect((205, 210, 220), x - 24, y - 24, 48, 24)
        p.rect(BLACK, x - 24, y - 24, 48, 24, 2)
        p.circle(STEEL_DK, (x - 10, y - 12), 8, 2)
        p.line(STEEL_DK, (x - 16, y - 12), (x - 4, y - 12), 1)
        p.rect(STEEL, x + 6, y - 20, 14, 3)
        p.rect(STEEL, x + 6, y - 14, 14, 3)
    elif name == "antenna":
        p.line((70, 74, 86), (x, y), (x, y - 70), 3)
        p.line((70, 74, 86), (x - 16, y - 54), (x + 16, y - 54), 3)
        p.line((70, 74, 86), (x - 11, y - 38), (x + 11, y - 38), 3)
        p.circle(RED, (x, y - 72), 3)
    elif name == "tank":
        p.line((80, 60, 40), (x - 16, y), (x - 12, y - 24), 3)
        p.line((80, 60, 40), (x + 16, y), (x + 12, y - 24), 3)
        p.rect((172, 122, 82), x - 20, y - 56, 40, 34)
        p.poly((130, 90, 60), [(x - 22, y - 56), (x, y - 70), (x + 22, y - 56)])
        p.rect(BLACK, x - 20, y - 56, 40, 34, 2)
        p.rect((120, 84, 56), x - 20, y - 44, 40, 3)


# ---------------------------------------------------------------------------
NIGHT_MUL = (112, 128, 196)          # множитель цвета для ночи (почти синий, но читаемо)


def darken(surf, mul=NIGHT_MUL):
    """Затемняет поверхность с цветовым ключом, сохраняя прозрачность."""
    surf.set_colorkey(None)
    surf.fill(mul, special_flags=pygame.BLEND_RGB_MULT)
    t = pygame.Surface((1, 1))
    t.fill(KEY)
    t.fill(mul, special_flags=pygame.BLEND_RGB_MULT)
    surf.set_colorkey(t.get_at((0, 0))[:3], pygame.RLEACCEL)
    return surf


def build_strips(L, spikes, new_sprite, night=False):
    """Возвращает (strips, y0): strips — [(x0_мира, Surface)], y0 — мировая y верха полос."""
    top_row = L.ground_row
    for (tx, ty, tw, th, *_r) in L.solids:
        top_row = min(top_row, ty)
    for (tx, ty, tw, *_r) in L.oneway:
        top_row = min(top_row, ty - 1)
    for (tx, ty0, ty1, *_r) in L.ladders:
        top_row = min(top_row, ty0 - 1)
    for it in L.decor:
        if it[0] == "frame":
            top_row = min(top_row, it[4] - 4 * it[3] - 4)
        elif it[0] == "scaf":
            top_row = min(top_row, it[3] - 3 * it[2] - 3)
        elif it[0] == "crane_hook":
            top_row = min(top_row, it[2] - 11)
    y0 = max(0, (top_row - 3) * TILE)
    H = L.world_h - y0
    nstrips = (L.world_w + 2 * PAD) // STRIP_W + 1
    strips = []
    for k in range(nstrips):
        strips.append((-PAD + k * STRIP_W, new_sprite(STRIP_W, H)))
    cv = _Canvas(strips, y0)
    T = TILE

    def span(tx, tw):
        return tx * T - 8, (tx + tw) * T + 8

    # 1) задние декорации
    for it in L.decor:
        k = it[0]
        if k == "void":
            cv.each(it[1] * T - 8, it[2] * T + 8, _void, L, it[1], it[2])
        elif k == "scaf":
            _k, spans, n, g = it
            cv.each(spans[0][0] * T, (spans[0][1] + 1) * T, _scaffold, spans, n, g)
        elif k == "frame":
            _k, lo, hi, n, g = it
            cv.each(lo * T - 20, (hi + 4) * T + 40, _frame, lo, hi, n, g)
        elif k == "bridge":
            _k, x, gw, br, g = it
            cv.each(x * T, (x + gw + 2) * T, _bridge, x, gw, br, g)
        elif k == "rails":
            cv.each(it[1] * T, (it[1] + 3) * T, _rails, it[1], it[2], it[3])
        elif k == "crane_hook":
            cv.each(it[1] * T - 80, it[1] * T + 90, _crane_hook, L, it[1])
    # 2) земля и постройки
    for (tx, ty, tw, th, style, pal) in L.solids:
        if style == "ground":
            cv.each(tx * T, (tx + tw) * T, _ground, L, tx, ty, tw, th)
    for (tx, ty, tw, th, style, pal) in L.solids:
        a, b = span(tx, tw)
        if style == "bld":
            cv.each(a, b, _building, L, tx, ty, tw, th, pal, 1 if night else 0)
        elif style == "armor":
            cv.each(a, b, _armor, L, tx, ty, tw, th, pal, 1 if night else 0)
        elif style == "block":
            cv.each(a, b, _block, tx, ty, tw, th, pal)
        elif style == "crate":
            cv.each(a, b, _crate, tx, ty, tw, th)
        elif style == "chimney":
            cv.each(a, b, _chimney, tx, ty, tw, th)
    # 3) доски, лестницы, шипы, реквизит
    for (tx, ty, tw, style, pal) in L.oneway:
        a, b = span(tx, tw)
        cv.each(a, b, _plank, tx, ty, tw, style, pal)
    for (tx, ty0, ty1, pal) in L.ladders:
        cv.each(tx * T - 8, (tx + 1) * T + 8, _ladder, tx, ty0, ty1)
    for it in L.decor:
        if it[0] == "prop":
            cv.each(it[2] * T - 40, it[2] * T + 80, _prop, it[1], it[2], it[3])

    def _spikes(p):
        for sp in spikes:
            if sp.right < p.x0 - 4 or sp.left > p.x1 + 4:
                continue
            for i in range(4):
                x = sp.left + i * 8
                top, bot = sp.top, sp.bottom
                p.poly((205, 212, 222), [(x, bot), (x + 4, top), (x + 8, bot)])
                p.poly((140, 148, 160), [(x + 4, top), (x + 8, bot), (x + 4, bot)])
    cv.each(-PAD, L.world_w + PAD, _spikes)

    def _fences(p):
        for wx in (0, L.world_w):
            x = wx
            if x + 40 < p.x0 or x - 40 > p.x1:
                continue
            g = L.ground_row * T
            p.rect((120, 124, 135), x - 4, g - 92, 8, 92)
            for kk, by in enumerate((g - 88, g - 58)):
                for j in range(3):
                    col = RED if (j + kk) % 2 == 0 else WHITE
                    p.rect(col, x - 18 + j * 12, by, 12, 14)
                p.rect(BLACK, x - 18, by, 36, 14, 2)
    cv.each(-60, 60, _fences)
    cv.each(L.world_w - 60, L.world_w + 60, _fences)
    if night:
        for _x0, surf in strips:
            darken(surf)
        # светящиеся детали поверх затемнения
        for (tx, ty, tw, th, style, pal) in L.solids:
            a, b = span(tx, tw)
            if style == "bld":
                cv.each(a, b, _building, L, tx, ty, tw, th, pal, 2)
            elif style == "armor":
                cv.each(a, b, _armor, L, tx, ty, tw, th, pal, 2)
        for it in L.decor:
            if it[0] == "prop" and it[1] == "lamp":
                cv.each(it[2] * T - 40, it[2] * T + 80, _lamp_glow, it[2], it[3])
    return strips, y0


def _lamp_glow(p, col, row):
    x = col * TILE + TILE // 2
    y = row * TILE
    if x < p.x0 - 60 or x > p.x1 + 60:
        return
    p.circle((255, 246, 196), (x + 20, y - 88), 7)
    p.circle((255, 214, 120), (x + 20, y - 88), 10, 2)
