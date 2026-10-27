# -*- coding: utf-8 -*-
"""Процедурная генерация города для режима «Генерация» + проверка проходимости.

Модуль не зависит от pygame: уровень — это обычные списки в тайлах (1 тайл = TILE px).
Классический уровень собирается в основном файле в тот же контейнер Level.
"""
import random

TILE = 36
ROWS = 36            # высота мира в тайлах (в классике — 15)
GROUND_ROW = 34      # строка верхней поверхности земли (в классике — 13)

# названия районов и номера палитр
DISTRICTS = ("СТРОЙПЛОЩАДКА", "ДЕЛОВОЙ ЦЕНТР", "ПРОМЗОНА")


class Level:
    """Всё, что нужно игре, чтобы построить и нарисовать уровень."""

    def __init__(self, mode="classic"):
        self.mode = mode
        self.seed = 0
        self.cols = 100
        self.rows = 15
        self.ground_row = 13
        self.solids = []      # (tx, ty, tw, th, style, pal)
        self.oneway = []      # (tx, ty, tw, style, pal)   тонкая доска сверху строки ty
        self.ladders = []     # (tx, ty0, ty1, pal)        ty0 — верх (поверхность), ty1 — низ
        self.spikes = []      # (tx, ty)                   шип стоит на поверхности тайла
        self.moving = []      # как MOVING_DEFS
        self.bricks = []      # (x_tile, y_tile)
        self.bolts = []
        self.hearts = []
        self.foremen = []     # как ENEMY_DEFS
        self.pigeons = []     # словари, см. Pigeon в основном файле
        self.checkpoints = [] # tx
        self.zone_tx = 86
        self.decor = []       # декорации для кэша картинки
        self.districts = []   # (tx_start, name, pal)
        self.spawn = (1.2, 11)
        self.links = []       # ((c, r), (c, r)) — явные переходы (лифты, платформы)
        self.brick_nodes = [] # (tx, row) — где стоять, чтобы взять кирпич

    @property
    def world_w(self):
        return self.cols * TILE

    @property
    def world_h(self):
        return self.rows * TILE

    @property
    def ground_y(self):
        return self.ground_row * TILE


# ---------------------------------------------------------------------------
# Проверка проходимости (консервативная модель прыжков на сетке тайлов)
# ---------------------------------------------------------------------------
def _max_dc(dr):
    """Максимальный горизонтальный прыжок (в тайлах) при подъёме на dr тайлов (dr<0 — вниз)."""
    if dr >= 0:
        return 5 - dr           # 0->5, 1->4, 2->3, 3->2
    return 5


def build_graph(L, with_stand=False):
    solid, one, lad = set(), set(), set()
    for (tx, ty, tw, th, *_r) in L.solids:
        for c in range(tx, tx + tw):
            for r in range(ty, ty + th):
                solid.add((c, r))
    for (tx, ty, tw, *_r) in L.oneway:
        for c in range(tx, tx + tw):
            one.add((c, ty))
    for (tx, ty0, ty1, *_r) in L.ladders:
        for r in range(ty0, ty1 + 1):
            lad.add((tx, r))
    rows = L.rows

    def stand(c, r):
        if (c, r) not in solid and (c, r) not in one:
            return False
        return (c, r - 1) not in solid and (c, r - 2) not in solid

    nodes = set()
    for (c, r) in list(solid) + list(one):
        if stand(c, r):
            nodes.add((c, r))
    stand_nodes = set(nodes)
    nodes |= lad

    adj = {}

    def edge(a, b):
        adj.setdefault(a, set()).add(b)

    for (c, r) in stand_nodes:
        # ходьба
        for c2 in (c - 1, c + 1):
            if (c2, r) in stand_nodes:
                edge((c, r), (c2, r))
            elif (c2, r) in lad:
                edge((c, r), (c2, r))
            elif (c2, r) not in solid and (c2, r - 1) not in solid and (c2, r - 2) not in solid:
                # шаг в пустоту: падаем вниз
                rr = r + 1
                while rr < rows:
                    if (c2, rr) in solid:
                        break
                    if (c2, rr) in one:
                        break
                    rr += 1
                if rr < rows and (c2, rr) in stand_nodes:
                    edge((c, r), (c2, rr))
        # прыжки
        for dr in range(3, -13, -1):
            r2 = r - dr
            if r2 >= rows:
                continue
            mdc = _max_dc(dr)
            for dc in range(-mdc, mdc + 1):
                if dc == 0 and dr <= 0:
                    continue
                c2 = c + dc
                if (c2, r2) not in stand_nodes:
                    continue
                top = min(r, r2) - 4
                ok = True
                lo, hi = (c, c2) if c <= c2 else (c2, c)
                for k in range(lo, hi + 1):
                    if k == c2:
                        rng_rows = range(r2 - 2, r2)
                    elif k == c:
                        rng_rows = range(top, r)
                    else:
                        rng_rows = range(top, top + 2)
                    for rr in rng_rows:
                        if (k, rr) in solid:
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    edge((c, r), (c2, r2))
    # лестницы
    for (c, r) in lad:
        if (c, r + 1) in lad:
            edge((c, r), (c, r + 1))
            edge((c, r + 1), (c, r))
        for c2 in (c - 1, c + 1):
            if (c2, r) in stand_nodes:
                edge((c, r), (c2, r))
                edge((c2, r), (c, r))
    for a, b in L.links:
        edge(a, b)
        edge(b, a)
    if with_stand:
        return nodes, adj, stand_nodes
    return nodes, adj


def reachable_stands(L):
    """Все поверхности (c, r), на которые игрок может встать, начав со спавна. Для раскладки предметов."""
    nodes, adj, stand = build_graph(L, with_stand=True)
    start = (int(L.spawn[0] + 0.5), L.ground_row)
    seen = {start}
    stack = [start]
    while stack:
        a = stack.pop()
        for b in adj.get(a, ()):
            if b not in seen:
                seen.add(b)
                stack.append(b)
    return sorted(n for n in seen if n in stand)


def analyze(L, start=None, goal=None):
    """Возвращает словарь с результатом проверки уровня."""
    nodes, adj = build_graph(L)
    if start is None:
        start = (int(L.spawn[0] + 0.5), L.ground_row)
    if goal is None:
        goal = (L.zone_tx + 2, L.ground_row)
    res = {"ok": True, "problems": []}
    if start not in nodes:
        res["ok"] = False
        res["problems"].append(("start_invalid", start))
        return res
    seen = {start}
    stack = [start]
    while stack:
        a = stack.pop()
        for b in adj.get(a, ()):
            if b not in seen:
                seen.add(b)
                stack.append(b)
    if goal not in seen:
        res["ok"] = False
        res["problems"].append(("goal_unreachable", goal))
    for bn in L.brick_nodes:
        if tuple(bn) not in seen:
            res["ok"] = False
            res["problems"].append(("brick_unreachable", tuple(bn)))
    # soft-lock: из любой достижимой точки можно дойти до цели
    radj = {}
    for a, bs in adj.items():
        for b in bs:
            radj.setdefault(b, set()).add(a)
    back = {goal}
    stack = [goal]
    while stack:
        a = stack.pop()
        for b in radj.get(a, ()):
            if b not in back:
                back.add(b)
                stack.append(b)
    traps = [n for n in seen if n not in back]
    if traps:
        res["ok"] = False
        res["problems"].append(("trap", sorted(traps)[:6], len(traps)))
    res["reachable"] = len(seen)
    return res


# ---------------------------------------------------------------------------
# Строитель уровня: примитивы
# ---------------------------------------------------------------------------
class Builder:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        L = Level("gen")
        L.rows = ROWS
        L.ground_row = GROUND_ROW
        L.spawn = (1.2, GROUND_ROW - 2)
        self.L = L
        self.g = GROUND_ROW
        self.gaps = []
        self.slots = []        # возможные места кирпичей
        self.pal = 0
        self.d = 0.0

    # --- геометрия
    def solid(self, tx, ty, tw, th, style, pal=None):
        self.L.solids.append((tx, ty, tw, th, style, self.pal if pal is None else pal))

    def plank(self, tx, ty, tw, style, pal=None):
        self.L.oneway.append((tx, ty, tw, style, self.pal if pal is None else pal))

    def ladder(self, tx, ty0, ty1):
        self.L.ladders.append((tx, ty0, ty1, self.pal))

    def spike(self, tx):
        self.L.spikes.append((tx, self.g))

    def gap(self, a, b):
        self.gaps.append((a, b))

    def deco(self, *item):
        self.L.decor.append(item)

    def prop(self, name, col, row=None):
        self.deco("prop", name, col, self.g if row is None else row)

    # --- предметы
    def bolt(self, x, y):
        self.L.bolts.append((x, y))

    def bolts_on(self, c0, c1, row):
        """Ряд гаек над поверхностью row, колонки c0..c1."""
        for c in range(c0, c1 + 1):
            self.bolt(c, row - 0.8)

    def bolt_arc(self, x0, x1, row, height, n=5):
        """Дуга из гаек: показывает траекторию прыжка."""
        for i in range(n):
            t = i / (n - 1) if n > 1 else 0.5
            x = x0 + (x1 - x0) * t
            y = row - 0.8 - height * 4 * t * (1 - t)
            self.bolt(x, y)

    def heart(self, x, row):
        self.L.hearts.append((x, row - 0.8))

    def brick(self, x, row, tier, node=None):
        """Место под кирпич. tier: 0 — на земле, 1 — средняя высота, 2 — награда за подъём."""
        self.slots.append({"x": x, "row": row, "tier": tier,
                           "node": node if node is not None else (int(round(x)), row)})

    # --- враги
    def foreman(self, x0, x1, row, speed):
        if x1 - x0 < 3:
            return
        self.L.foremen.append((x0 + 0.5, row, x0, x1, speed))

    def perch(self, col, row, face=1):
        self.L.pigeons.append({"kind": "perch", "x": col, "row": row, "face": face})

    def flock(self, x0, x1, row_f, n=3, speed=70, amp=0.5):
        """Стая голубей: летят цепочкой туда-сюда с небольшим сдвигом по высоте и времени."""
        phase = self.rng.random() * 6.0
        for k in range(n):
            self.L.pigeons.append({"kind": "patrol", "x0": x0, "x1": x1,
                                   "row": row_f + (0.0 if k == 0 else 0.45 * (k % 2 * 2 - 1) * ((k + 1) // 2)),
                                   "amp": amp, "speed": speed, "lag": 0.55 * k, "phase": phase})


# ---------------------------------------------------------------------------
# Сегменты уровня. Каждый получает колонку x (свободная земля слева) и сложность d (0..1),
# строит конструкцию и возвращает колонку, с которой снова начинается свободная земля.
# ---------------------------------------------------------------------------
def seg_flat(b, x, d):
    r, g = b.rng, b.g
    w = r.randint(5, 9)
    roll = r.random()
    if d > 0.12 and roll < 0.40 + 0.4 * d:
        b.foreman(x + 1, x + w - 1, g, 58 + int(30 * d) + r.randint(0, 14))
        b.prop("cone", x + 1)
        b.prop("barrel", x + w - 2)
        b.brick(x + w // 2, g, 0)
        b.brick(x + 2, g, 0)
        b.bolts_on(x + 3, x + w - 3, g)
    elif roll < 0.85:
        cx = x + r.randint(2, w - 3)
        hh = 1 if r.random() < 0.7 else 2
        b.solid(cx, g - hh, 1, hh, "crate")
        b.bolt_arc(cx - 2, cx + 2, g - hh, 1.6, 5)
        b.brick(cx, g - hh, 0)
        b.brick(x + w - 2, g, 0)
        b.prop("cone", x + 1)
    else:
        b.prop("sign", x + 2)
        b.prop("barrel", x + w - 2)
        b.bolts_on(x + 1, x + w - 2, g)
        b.brick(x + w // 2, g, 0)
        b.brick(x + 1, g, 0)
    return x + w


def seg_stairs(b, x, d):
    r, g = b.rng, b.g
    k = r.randint(3, 4)
    c = x + 1
    for i in range(1, k):
        b.solid(c, g - i, 2, i, "block")
        b.bolt(c + 0.5, g - i - 0.8)
        if i == 2:
            b.brick(c + 1, g - i, 0)
        c += 2
    b.solid(c, g - k, 3, k, "block")
    top_row = g - k
    b.brick(c + 1, top_row, 1 if k >= 4 else 0)
    b.bolt(c, top_row - 0.8)
    b.bolt(c + 2, top_row - 0.8)
    plate_c = c
    c += 3
    for i in range(k - 1, 0, -1):
        b.solid(c, g - i, 2, i, "block")
        c += 2
    if d > 0.4 and r.random() < 0.5:
        b.perch(plate_c + 2, top_row, -1)
    else:
        b.prop("cone", plate_c + 1, top_row)
    return c + 1


def seg_pit(b, x, d):
    r, g = b.rng, b.g
    gw = r.choice([2, 3, 3, 4]) if d < 0.5 else r.choice([3, 4, 4, 5])
    a = x + 2
    b.gap(a, a + gw)
    b.deco("void", a, a + gw)
    if gw >= 4:
        pc = a + (1 if gw == 5 else gw // 2 - 1)
        pw = 3 if gw == 5 else 2
        b.plank(pc, g - 1, pw, "pallet")
        b.brick(pc + pw // 2, g - 1, 1)
    else:
        b.brick(a + gw // 2, g - 2.6, 1, node=(a - 1, g))
    b.brick(a + gw + 1, g, 0)
    b.bolt_arc(a - 1, a + gw, g, 2.0, 5)
    b.prop("cone", a - 1)
    return a + gw + 2


def seg_pit_moving(b, x, d):
    r, g = b.rng, b.g
    gw = r.randint(6, 7)
    a = x + 2
    b.gap(a, a + gw)
    b.deco("void", a, a + gw)
    b.L.moving.append((a - 1, g - 1.7, 3, "x", (gw - 1) * TILE, round(1.0 + r.random() * 0.25, 2),
                       round(r.random() * 6.0, 2)))
    b.L.links.append(((a - 1, g), (a + gw, g)))
    b.L.links.append(((a - 2, g), (a + gw + 1, g)))
    b.bolt_arc(a, a + gw - 1, g - 2.2, 0.6, 6)
    b.brick(a + gw // 2, g - 2.0, 1, node=(a - 1, g))
    b.deco("crane_hook", a + gw // 2, g)
    b.brick(a + gw + 1, g, 0)
    return a + gw + 2


def seg_spikes(b, x, d):
    r, g = b.rng, b.g
    w = r.randint(10, 12)
    c = x + 2
    first = 2
    while c < x + w - 3:
        pw = 2 + (1 if d > 0.5 and r.random() < 0.4 else 0)
        for k in range(pw):
            b.spike(c + k)
        if r.random() < 0.65:
            b.plank(c - 1, g - 2, pw + 2, "pallet")
            b.bolts_on(c - 1, c + pw, g - 2)
            if first > 0:
                b.brick(c + pw // 2, g - 2, 1)
                first -= 1
        else:
            b.bolt_arc(c - 1, c + pw, g, 2.2, 5)
        c += pw + r.randint(3, 5)
    for k in range(first):
        b.brick(x + w - 2 - 2 * k, g, 0)
    b.prop("sign", x + 1)
    return x + w


def seg_scaffold(b, x, d):
    """Высокие строительные леса: этажи через 3 тайла, лестницы зигзагом, награда наверху."""
    r, g = b.rng, b.g
    n = r.randint(2, min(6, 3 + int(d * 3)))
    w0 = r.randint(7, 9)
    lo, hi = x + 1, x + w0
    spans = [(lo, hi)]
    for i in range(1, n + 1):
        plo, phi = spans[-1]
        nlo = plo + (1 if (phi - plo > 5 and r.random() < 0.5) else 0)
        nhi = phi - (1 if (phi - nlo > 5 and r.random() < 0.5) else 0)
        spans.append((nlo, nhi))
    for i in range(1, n + 1):
        slo, shi = spans[i]
        row = g - 3 * i
        b.plank(slo, row, shi - slo + 1, "scaf")
        col = slo if i % 2 == 1 else shi
        b.ladder(col, row, g - 3 * (i - 1))
        if i < n:
            b.bolts_on(slo + 1, shi - 1, row)
    b.deco("scaf", [list(s) for s in spans], n, g)
    top = g - 3 * n
    tlo, thi = spans[n]
    mid = (tlo + thi) // 2
    b.brick(mid, top, 2)
    b.brick(mid + 1, top, 2)
    if n >= 3:
        b.heart(mid - 1, g - 3 * (n - 1))
        b.brick(spans[n - 1][0] + 2, g - 3 * (n - 1), 1)
    ladder_col = tlo if n % 2 == 1 else thi
    far = thi - 1 if ladder_col == tlo else tlo + 1
    if d > 0.22:
        b.perch(far, top, -1 if far > mid else 1)
    if n >= 4 and d > 0.5:
        other = tlo + 1 if far != tlo + 1 else thi - 1
        b.perch(other, top, 1 if other < mid else -1)
    if n >= 3 and d > 0.3 and r.random() < 0.7:
        slo, shi = spans[2]
        b.foreman(slo + 1, shi - 1, g - 6, 54 + r.randint(0, 20))
    b.prop("cone", lo - 1)
    return hi + 2


def seg_building(b, x, d):
    """Обычный дом: лестница-пожарка по стене, на крыше награда, дымоход или голубь."""
    r, g = b.rng, b.g
    w = r.randint(4, 6)
    h = r.randint(4, 5 + int(d * 5))
    left = x + 1
    roof = g - h
    b.solid(left, roof, w, h, "bld")
    b.ladder(x, roof, g)
    b.plank(x, roof, 1, "ledge")
    cols = list(range(left, left + w))
    use_chimney = w >= 5 and r.random() < 0.45
    if use_chimney:
        cc = left + r.randint(2, w - 2)
        b.solid(cc, roof - 2, 1, 2, "chimney")
        b.brick(left + w - 1, roof, 2 if h >= 7 else 1)
        b.bolt_arc(left, left + w - 1, roof, 3.0, 5)
    else:
        b.brick(left + w // 2, roof, 2 if h >= 7 else 1)
        b.prop(r.choice(("ac", "antenna", "tank")), left + 1, roof)
        if w >= 5 and d > 0.15 and r.random() < 0.5:
            b.foreman(left + 1, left + w - 1, roof, 52 + r.randint(0, 18))
        elif d > 0.2:
            b.perch(left + w - 1, roof, -1)
    b.brick(x, roof, 1)
    if h >= 7:
        by = roof + 3
        b.plank(left + w, by, 2, "balcony")
        b.heart(left + w, by)
    b.deco("windows", left, roof, w, h)
    return left + w + 2


def seg_skyline(b, x, d):
    """Крыши подряд через переулки: прыгаешь с дома на дом, голуби патрулируют над ними."""
    r, g = b.rng, b.g
    n = r.randint(2, 3 if d < 0.75 else 4)
    h = r.randint(5, 7)
    c = x + 1
    roofs = []
    first_left = c
    for i in range(n):
        w = r.randint(3, 4)
        if i > 0:
            h = max(4, min(11, h + r.choice((-3, -2, -1, 0, 1, 2))))
        roof = g - h
        b.solid(c, roof, w, h, "bld")
        b.deco("windows", c, roof, w, h)
        if i == 0:
            b.ladder(x, roof, g)
            b.plank(x, roof, 1, "ledge")
        roofs.append((c, w, roof))
        b.brick(c + w // 2, roof, 2 if h >= 8 else 1)
        if i < n - 1:
            lad = c + w
            b.ladder(lad, roof, g)
            b.plank(lad, roof, 1, "ledge")
            if d > 0.4 and r.random() < 0.55:
                b.spike(lad + 1)
                b.spike(lad + 2)
            c = lad + 3
        else:
            c = c + w
    for i in range(n - 1):
        c0, w0, r0 = roofs[i]
        c1, w1, r1 = roofs[i + 1]
        b.bolt_arc(c0 + w0, c1, min(r0, r1), 2.4, 4)
    top_row = min(rr for _, _, rr in roofs)
    if d > 0.28:
        b.flock(first_left + 1, c - 1, top_row - 3.4, 2 if d < 0.6 else 3, 64 + int(d * 30))
    else:
        b.perch(roofs[-1][0] + roofs[-1][1] - 1, roofs[-1][2], -1)
    return c + 2


def seg_frame(b, x, d):
    """Бетонный каркас новостройки: перекрытия через 4 тайла, лестницы внутри, прорабы на этажах."""
    r, g = b.rng, b.g
    w = r.randint(7, 9)
    n = r.randint(2, 3 + (1 if d > 0.5 else 0))
    lo, hi = x + 1, x + w
    for i in range(1, n + 1):
        row = g - 4 * i
        b.plank(lo, row, w, "slab")
        col = lo + 1 if i % 2 == 1 else hi - 1
        b.ladder(col, row, g - 4 * (i - 1))
        if i < n:
            b.bolts_on(lo + 1, hi - 1, row)
    b.deco("frame", lo, hi, n, g)
    top = g - 4 * n
    b.brick(lo + w // 2, top, 2)
    if n >= 3:
        b.brick(lo + w // 2 + 2, top, 2)
        b.heart(lo + 2, g - 4 * (n - 1))
    else:
        b.brick(lo + 2, g - 4, 1)
        b.heart(hi - 1, g - 4)
    if d > 0.18:
        b.foreman(lo + 2, hi - 1, g - 4, 56 + r.randint(0, 20))
    if n >= 3 and d > 0.4:
        b.foreman(lo + 1, hi - 2, g - 8, 60 + r.randint(0, 20))
    if d > 0.35:
        b.perch(hi - 1 if n % 2 == 1 else lo + 1, top, -1 if n % 2 == 1 else 1)
    b.prop("barrel", lo - 1)
    return hi + 2


def seg_elevator(b, x, d):
    """Грузовой подъёмник: платформа едет вдоль стены до крыши с наградой."""
    r, g = b.rng, b.g
    wt = r.randint(4, 6)
    h = r.randint(6, 9)
    rr = g - h
    tc = x + 4
    b.solid(tc, rr, wt, h, "bld")
    b.deco("windows", tc, rr, wt, h)
    dist = (g - rr) * TILE - 70      # внизу платформа не доходит до земли на рост игрока: не давит стоящего под ней
    b.L.moving.append((x + 1, rr + 8 / TILE, 3, "y", dist, round(0.85 + r.random() * 0.25, 2),
                       round(r.random() * 6.0, 2)))
    for c in range(x, x + 4):
        b.L.links.append(((c, g), (tc, rr)))
    b.deco("rails", x + 1, rr, g)
    b.brick(tc + 1, rr, 2)
    b.brick(tc + 2, rr, 2)
    b.heart(tc + wt - 1, rr)
    if d > 0.3:
        b.perch(tc + wt - 1, rr, -1)
    elif wt >= 5:
        b.foreman(tc + 1, tc + wt - 1, rr, 52)
    b.bolts_on(x + 1, x + 3, g - 1)
    return tc + wt + 2


def seg_bridge(b, x, d):
    """Длинный мост из лесов над пропастью. Лестницы на обоих концах, над мостом летают голуби."""
    r, g = b.rng, b.g
    gw = r.randint(8, 11)
    br = g - 4
    b.gap(x + 1, x + gw + 1)
    b.deco("void", x + 1, x + gw + 1)
    b.plank(x, br, gw + 2, "scaf")
    b.ladder(x, br, g)
    b.ladder(x + gw + 1, br, g)
    b.deco("bridge", x, gw, br, g)
    b.brick(x + gw // 3 + 1, br, 1)
    b.brick(x + 2 * gw // 3 + 1, br, 1)
    if d > 0.3:
        b.heart(x + gw // 2 + 1, br)
    b.bolts_on(x + 2, x + gw - 1, br)
    if d > 0.2:
        b.flock(x + 1, x + gw, br - 3.6, 2 if d < 0.6 else 3, 68 + int(d * 26))
    b.prop("cone", x - 1)
    return x + gw + 3


SEGS = {
    "flat": seg_flat, "stairs": seg_stairs, "pit": seg_pit, "pit_moving": seg_pit_moving,
    "spikes": seg_spikes, "scaffold": seg_scaffold, "building": seg_building,
    "skyline": seg_skyline, "frame": seg_frame, "elevator": seg_elevator, "bridge": seg_bridge,
}
BIG = ("scaffold", "skyline", "frame", "elevator", "bridge", "pit_moving")
TALL = ("scaffold", "skyline", "frame", "elevator")
MIN_D = {"flat": 0.0, "stairs": 0.0, "pit": 0.0, "building": 0.0, "spikes": 0.12,
         "scaffold": 0.08, "skyline": 0.15, "pit_moving": 0.2, "elevator": 0.25,
         "frame": 0.3, "bridge": 0.35}


def make_plan(rng, n):
    """Список сегментов: ритм «напряжение — передышка», без повторов подряд, с высотными акцентами."""
    plan = ["flat"]
    used = {}
    for i in range(1, n):
        d = i / (n - 1)
        prev = plan[-1]
        prev_big = prev in BIG
        prev2_big = len(plan) >= 2 and plan[-2] in BIG
        names, weights = [], []
        for t in SEGS:
            if t == prev or MIN_D[t] > d + 1e-9:
                continue
            is_big = t in BIG
            if is_big and prev_big and prev2_big:
                continue
            wt = 1.35 if is_big else 1.0
            if prev_big and not is_big:
                wt *= 1.7
            if prev_big and is_big:
                wt *= 0.45
            if t == "flat":
                wt *= 0.6
            wt /= (1.0 + used.get(t, 0)) ** 1.4
            names.append(t)
            weights.append(wt)
        t = rng.choices(names, weights)[0]
        used[t] = used.get(t, 0) + 1
        plan.append(t)
    # минимум три высотных объекта в забеге
    tall = [i for i, t in enumerate(plan) if t in TALL]
    cand = [i for i, t in enumerate(plan) if i > 1 and t not in BIG and t != "flat"]
    rng.shuffle(cand)
    while len(tall) < 3 and cand:
        i = cand.pop()
        if plan[i - 1] in BIG and plan[min(i + 1, len(plan) - 1)] in BIG:
            continue
        plan[i] = rng.choice(("scaffold", "skyline"))
        tall.append(i)
    # финал спокойный
    if plan[-1] in BIG:
        plan[-1] = "stairs"
    return plan


def _pick_bricks(b):
    r = b.rng
    tiers = {0: [], 1: [], 2: []}
    for s in b.slots:
        tiers[s["tier"]].append(s)
    for t in tiers.values():
        r.shuffle(t)
    chosen = tiers[2][:12]
    rest2 = tiers[2][12:]
    need = 25 - len(chosen)
    keep0 = min(5, len(tiers[0]))
    n1 = max(0, min(len(tiers[1]), need - keep0))
    chosen += tiers[1][:n1]
    need = 25 - len(chosen)
    chosen += tiers[0][:need]
    need = 25 - len(chosen)
    if need > 0:
        extra = tiers[1][n1:] + rest2
        chosen += extra[:need]
    ids = {id(s) for s in chosen}
    for s in b.slots:
        if id(s) in ids:
            b.L.bricks.append((s["x"], s["row"] - 0.8))
            b.L.brick_nodes.append(s["node"])
        else:
            b.bolt(s["x"], s["row"] - 0.8)
    return len(chosen)


def _generate_once(seed):
    b = Builder(seed)
    r, L, g = b.rng, b.L, b.g
    n = r.randint(9, 11)
    plan = make_plan(r, n)
    x = 7
    b.prop("sign", 2)
    b.prop("cone", 4)
    b.bolts_on(4, 5, g)
    cur_pal = -1
    i = 0
    while i < len(plan):
        t = plan[i]
        frac = i / max(1, n)
        pal = 0 if frac < 0.34 else (1 if frac < 0.67 else 2)
        if pal != cur_pal:
            L.districts.append((x, DISTRICTS[pal], pal))
            cur_pal = pal
        b.pal = pal
        d = min(1.0, i / max(1, n - 1))
        b.d = d
        x = SEGS[t](b, x, d)
        if i in (3, 6, 9):
            L.checkpoints.append(x)
        x += r.choice((1, 2, 2, 3))
        if i == 2 and r.random() < 0.7:
            b.prop("lamp", x - 1)
        i += 1
        if i == len(plan) and len(b.slots) < 27 and len(plan) < 16:
            plan.append(r.choice(("flat", "stairs", "building", "pit")))
    # финишная прямая и стройка
    b.pal = 2
    b.bolts_on(x + 1, x + 3, g)
    L.zone_tx = x + 5
    L.cols = L.zone_tx + 14
    _pick_bricks(b)
    if len(L.hearts) < 3:
        for cp in L.checkpoints[:3 - len(L.hearts)]:
            b.heart(cp + 1, g)
    # земля: всё, кроме ям
    pos = -8
    for (a, bb) in sorted(b.gaps):
        if a > pos:
            b.solid(pos, g, a - pos, ROWS - g, "ground", 0)
        pos = bb
    b.solid(pos, g, L.cols + 8 - pos, ROWS - g, "ground", 2)
    return L


def generate(seed, tries=14):
    """Генерирует уровень по сиду; при неудачной проверке пробует соседние варианты."""
    last = None
    for attempt in range(tries):
        sub = seed if attempt == 0 else seed * 1009 + attempt * 7919
        L = _generate_once(sub)
        res = analyze(L)
        L.seed = seed
        L.attempt = attempt
        L.report = res
        last = L
        if res["ok"] and len(L.bricks) == 25:
            return L
    return last
