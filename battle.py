# -*- coding: utf-8 -*-
"""Режим «Битва за Писюн»: сюжет, катсцены, диалоги, босс-робот, гранаты.

Файл подключается основной игрой (game.py). Здесь вся логика режима; игра только
вызывает хуки: Battle.update / draw_world / draw_lights / draw_overlay и т.д.
"""
import math
import random
import time
from array import array

import pygame

TILE = 36
BUILD_SHAPE = [
    ".XXX.",
    "XXXXX",
    ".XXX.",
    ".XXX.",
    ".XXX.",
    "XX.XX",
    "XX.XX",
]
CELLS = sum(r.count("X") for r in BUILD_SHAPE)       # 25

WHITE = (255, 255, 255)
BLACK = (20, 20, 30)
YELLOW = (255, 204, 64)
ORANGE = (255, 133, 51)
PINK = (255, 111, 168)
RED = (235, 64, 72)
GREEN = (65, 205, 105)
LIGHT = (210, 225, 255)
SKIN = (238, 177, 125)
SKIN_DK = (201, 128, 82)

BOSS_CELL = 36                    # размер клетки босса (монумент на стройке — 30)
BOSS_W, BOSS_H = 5 * BOSS_CELL, 7 * BOSS_CELL
GRENADE_CAP = 9
GRENADE_START = 3


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# Синтез звуков (чистый питон, свой генератор случайных чисел, чтобы не трогать общий)
# ---------------------------------------------------------------------------
def _mix_params():
    try:
        init = pygame.mixer.get_init()
        if not init or init[1] != -16:
            return None
        return (init[0] or 22050), init[2]
    except Exception:
        return None


def _to_sound(buf, channels):
    arr = array("h")
    app = arr.append
    for v in buf:
        iv = int((-1.0 if v < -1.0 else 1.0 if v > 1.0 else v) * 32767)
        for _ in range(channels):
            app(iv)
    return pygame.mixer.Sound(buffer=arr.tobytes())


def snd_boom(rate, dur, vol=0.8, thump=70.0, grit=0.35, seed=1):
    """Взрыв: низкий удар + шум, который становится глуше."""
    rnd = random.Random(seed)
    n = int(rate * dur)
    out = [0.0] * n
    lp = 0.0
    ph = 0.0
    for i in range(n):
        t = i / n
        env = (1.0 - t) ** 2.0
        lp += (rnd.uniform(-1, 1) - lp) * (0.04 + 0.5 * (1 - t) * grit)
        f = thump * (1.0 - 0.65 * t)
        ph += 2 * math.pi * f / rate
        th = math.sin(ph) * math.exp(-2.5 * t)
        att = min(1.0, i / (rate * 0.004))
        out[i] = (lp * 1.7 * env + th * 0.95) * env * vol * att
    return out


def snd_noise(rate, dur, vol=0.5, cutoff=0.4, seed=2, decay=2.0, rise=0.0):
    rnd = random.Random(seed)
    n = int(rate * dur)
    out = [0.0] * n
    lp = 0.0
    for i in range(n):
        t = i / n
        env = ((1 - t) ** decay) * (1 + rise * t)
        lp += (rnd.uniform(-1, 1) - lp) * cutoff
        out[i] = lp * env * vol
    return out


def snd_sweep(rate, dur, f0, f1, vol=0.4, wave="sq", decay=1.0):
    n = int(rate * dur)
    out = [0.0] * n
    ph = 0.0
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        ph += f / rate
        x = ph % 1.0
        if wave == "sq":
            v = 1.0 if x < 0.5 else -1.0
        elif wave == "saw":
            v = 2 * x - 1
        else:
            v = math.sin(2 * math.pi * x)
        out[i] = v * vol * ((1 - t) ** decay) * min(1.0, i / (rate * 0.003))
    return out


def snd_add(a, b, at=0.0, rate=22050, gain=1.0):
    """Подмешивает b в a со сдвигом at секунд (a растёт, если надо)."""
    off = int(at * rate)
    need = off + len(b)
    if len(a) < need:
        a.extend([0.0] * (need - len(a)))
    for i, v in enumerate(b):
        a[off + i] += v * gain
    return a


class SoundJobs:
    """Тяжёлые звуки (музыка) собираются по кусочкам между кадрами, чтобы игра не подвисала."""

    def __init__(self):
        self.jobs = []

    def add(self, gen, done):
        self.jobs.append((gen, done))

    def pump(self, budget=0.0014):
        if not self.jobs:
            return
        t0 = time.perf_counter()
        while self.jobs and time.perf_counter() - t0 < budget:
            gen, done = self.jobs[0]
            try:
                next(gen)
            except StopIteration as e:
                self.jobs.pop(0)
                try:
                    done(e.value)
                except Exception:
                    pass
            except Exception:
                self.jobs.pop(0)


def _music_epic(rate, channels):
    """Эпичная тема стройки: арпеджио Am-F-C-E, бас и подушка, нарастает. ~9.6 c."""
    notes = {"A2": 110.0, "F2": 87.3, "C3": 130.8, "E2": 82.4, "A3": 220.0, "F3": 174.6, "C4": 261.6, "E3": 164.8,
             "G#3": 207.7, "B3": 246.9, "D4": 293.7, "E4": 329.6, "G4": 392.0, "A4": 440.0, "C5": 523.3,
             "F4": 349.2, "B4": 493.9, "D5": 587.3, "E5": 659.3, "A5": 880.0, "G#4": 415.3, "F5": 698.5}
    chords = [("A2", ["A3", "C4", "E4", "A4"]), ("F2", ["F3", "A3", "C4", "F4"]),
              ("C3", ["C4", "E4", "G4", "C5"]), ("E2", ["G#3", "B3", "E4", "G#4"])]
    bar = 1.6
    step = bar / 8
    total = bar * 6
    n = int(rate * (total + 0.8))
    out = [0.0] * n
    pos = 0
    for b in range(6):
        root, arp = chords[b % 4] if b < 4 else (chords[2] if b == 4 else chords[3])
        gain = 0.45 + 0.55 * b / 5
        # бас
        f = notes[root]
        for k in range(2):
            t0 = b * bar + k * bar / 2
            m = int(rate * (bar / 2))
            i0 = int(t0 * rate)
            ph = 0.0
            for i in range(m):
                if not i & 1023:
                    yield
                ph += f / rate
                x = ph % 1.0
                v = (2 * x - 1) * 0.5 + (1.0 if x < 0.5 else -1.0) * 0.18
                env = min(1.0, i / (rate * 0.01)) * (1 - i / m) ** 0.7
                out[i0 + i] += v * env * 0.26 * gain
            yield
        # арпеджио (вверх-вниз)
        seq = [arp[0], arp[1], arp[2], arp[3], arp[2], arp[1], arp[2], arp[3]]
        for k, nm in enumerate(seq):
            f = notes[nm]
            i0 = int((b * bar + k * step) * rate)
            m = int(rate * step * 1.7)
            ph = 0.0
            for i in range(m):
                if not i & 1023:
                    yield
                ph += f / rate
                x = ph % 1.0
                v = 1.0 if x < 0.5 else -1.0
                env = min(1.0, i / (rate * 0.004)) * (1 - i / m) ** 1.6
                if i0 + i < n:
                    out[i0 + i] += v * env * 0.15 * gain
            yield
        # подушка
        for nm in arp[:3]:
            f = notes[nm] * 0.5
            i0 = int(b * bar * rate)
            m = int(rate * bar)
            ph = 0.0
            for i in range(0, m):
                if not i & 1023:
                    yield
                ph += f / rate
                x = ph % 1.0
                v = abs(4 * x - 2) - 1
                env = min(1.0, i / (rate * 0.15)) * min(1.0, (m - i) / (rate * 0.2))
                if i0 + i < n:
                    out[i0 + i] += v * env * 0.05 * gain
            yield
    # финальный удар
    i0 = int(total * rate)
    for nm, g in (("A3", 0.18), ("E4", 0.14), ("A4", 0.12), ("C5", 0.1)):
        f = notes[nm]
        m = n - i0
        ph = 0.0
        for i in range(m):
            if not i & 1023:
                yield
            ph += f / rate
            x = ph % 1.0
            v = (2 * x - 1)
            out[i0 + i] += v * g * (1 - i / m) ** 1.2
        yield
    return _to_sound(out, channels)


def _music_boss(rate, channels):
    """Боевая петля: бас-рифф и ударные, 8 долей по 0.36 с."""
    beat = 0.36
    total = beat * 8
    n = int(rate * total)
    out = [0.0] * n
    rnd = random.Random(11)
    riff = [55.0, 55.0, 65.4, 55.0, 73.4, 55.0, 65.4, 49.0]
    for k, f in enumerate(riff):
        i0 = int(k * beat * rate)
        m = int(rate * beat * 0.9)
        ph = 0.0
        for i in range(m):
            if not i & 1023:
                yield
            ph += f / rate
            x = ph % 1.0
            v = (2 * x - 1) * 0.6 + (1.0 if x < 0.5 else -1.0) * 0.25
            env = min(1.0, i / (rate * 0.006)) * (1 - i / m) ** 0.8
            out[i0 + i] += v * env * 0.34
        yield
        if k % 2 == 0:                       # бочка
            m = int(rate * 0.14)
            ph = 0.0
            for i in range(m):
                if not i & 1023:
                    yield
                t = i / m
                ph += (120 - 80 * t) / rate
                out[i0 + i] += math.sin(2 * math.pi * ph) * (1 - t) ** 1.5 * 0.5
        else:                                # малый / хэт
            m = int(rate * 0.1)
            lp = 0.0
            for i in range(m):
                if not i & 1023:
                    yield
                t = i / m
                lp += (rnd.uniform(-1, 1) - lp) * 0.6
                out[i0 + i] += lp * (1 - t) ** 2 * 0.28
        # хэт на «и»
        j0 = i0 + int(rate * beat * 0.5)
        m = int(rate * 0.04)
        for i in range(m):
            if not i & 1023:
                yield
            if j0 + i < n:
                out[j0 + i] += rnd.uniform(-1, 1) * (1 - i / m) * 0.12
        yield
    # лёгкая «тревога» сверху
    for k in (0, 4):
        i0 = int(k * beat * rate)
        m = int(rate * beat * 3.6)
        ph = 0.0
        for i in range(m):
            if not i & 1023:
                yield
            f = 440.0 + 20 * math.sin(i / rate * 6)
            ph += f / rate
            x = ph % 1.0
            out[i0 + i] += (1.0 if x < 0.5 else -1.0) * 0.04 * (1 - i / m)
        yield
    return _to_sound(out, channels)


def build_battle_sounds(game):
    """Быстрые звуки — сразу; музыка — по кусочкам в фоне. Возвращает SoundJobs."""
    jobs = SoundJobs()
    mp = _mix_params()
    if mp is None:
        return jobs
    rate, ch = mp
    snd = game.sounds
    if "b_boom" in snd:
        return jobs
    try:
        snd["b_boom"] = _to_sound(snd_boom(rate, 2.2, 0.85, 62.0, 0.5, 1), ch)
        snd["b_pop"] = _to_sound(snd_boom(rate, 0.55, 0.65, 120.0, 0.9, 2), ch)
        snd["b_big"] = _to_sound(snd_boom(rate, 3.2, 0.95, 50.0, 0.7, 3), ch)
        snd["b_slam"] = _to_sound(snd_boom(rate, 0.9, 0.9, 80.0, 0.5, 4), ch)
        snd["b_quake"] = _to_sound(snd_noise(rate, 2.6, 0.55, 0.05, 5, 0.6, 0.0), ch)
        snd["b_blip"] = _to_sound(snd_sweep(rate, 0.05, 520, 500, 0.22, "sq", 1.2), ch)
        snd["b_throw"] = _to_sound(snd_sweep(rate, 0.16, 300, 700, 0.25, "sq", 1.0), ch)
        snd["b_laser_c"] = _to_sound(snd_sweep(rate, 0.95, 200, 1500, 0.25, "saw", 0.2), ch)
        snd["b_laser"] = _to_sound(snd_sweep(rate, 0.85, 900, 700, 0.30, "sq", 0.15), ch)
        snd["b_missile"] = _to_sound(snd_noise(rate, 0.35, 0.35, 0.3, 6, 1.2), ch)
        snd["b_roar"] = _to_sound(snd_sweep(rate, 1.4, 220, 55, 0.5, "saw", 0.6), ch)
        snd["b_clang"] = _to_sound(snd_sweep(rate, 0.18, 880, 330, 0.35, "sq", 1.4), ch)
        snd["b_warn"] = _to_sound(snd_sweep(rate, 0.25, 900, 900, 0.18, "sq", 0.8), ch)
        snd["b_robot"] = _to_sound(snd_sweep(rate, 0.9, 80, 400, 0.35, "saw", 0.4), ch)
        for k in range(6):                   # «клац» блока: высота растёт
            base = 180.0 * (2 ** (k / 6.0))
            b = snd_sweep(rate, 0.16, base * 2, base, 0.38, "sq", 1.6)
            snd_add(b, snd_noise(rate, 0.07, 0.35, 0.5, 7 + k, 2.5), 0.0, rate)
            snd["b_clunk%d" % k] = _to_sound(b, ch)
        fan = []
        for k, f in enumerate((523, 659, 784, 1046, 1318, 1568)):
            snd_add(fan, snd_sweep(rate, 0.5, f, f, 0.2, "sq", 0.9), k * 0.09, rate)
        snd["b_fanfare"] = _to_sound(fan, ch)
    except Exception:
        pass
    jobs.add(_music_epic(rate, ch), lambda s: snd.__setitem__("b_music_epic", s) if s else None)
    jobs.add(_music_boss(rate, ch), lambda s: snd.__setitem__("b_music_boss", s) if s else None)
    return jobs


# ---------------------------------------------------------------------------
# Диалоговое окно в стиле Undertale
# ---------------------------------------------------------------------------
class Dialogue:
    """Реплики в стиле Undertale. blocking=True — ждёт тапа, False — сама листается и не мешает играть."""
    SPEED = 34.0            # символов в секунду

    def __init__(self, lines, on_done=None, blocking=True, name=""):
        self.lines = [("* " + s) for s in lines]
        self.i = 0
        self.shown = 0.0
        self.on_done = on_done
        self.blocking = blocking
        self.name = name
        self.last_blip = 0
        self.done = False
        self.wait = 0.0
        self.cache = None
        self.uid = 0

    @property
    def text(self):
        return self.lines[self.i]

    def complete(self):
        return int(self.shown) >= len(self.text)

    def update(self, dt, blip, auto=True):
        if self.done:
            return
        if self.complete():
            if not self.blocking and auto:
                self.wait += dt
                if self.wait > 1.1 + len(self.text) * 0.018:
                    self.tap()
            return
        self.shown = min(len(self.text), self.shown + self.SPEED * dt)
        k = int(self.shown)
        if k != self.last_blip:
            self.last_blip = k
            if self.blocking and k % 2 == 0 and k > 0 and self.text[k - 1] not in " .,!?…":
                blip()

    def tap(self):
        """True, если диалог закончился."""
        if self.done:
            return True
        if not self.complete():
            self.shown = len(self.text)
            return False
        self.i += 1
        self.shown = 0.0
        self.last_blip = 0
        self.wait = 0.0
        self.cache = None
        if self.i >= len(self.lines):
            self.done = True
            if self.on_done:
                self.on_done()
            return True
        return False


# ---------------------------------------------------------------------------
# Спрайты босса (рисуются один раз)
# ---------------------------------------------------------------------------
_SPR = {}


def _cell_robot(s, x, y, r, c, cell):
    ch_c = (r, c)
    if r <= 1 and not (r == 1 and c in (0, 4)):          # розовая броня головы
        base, dark, hi = (232, 92, 152), (168, 48, 100), (255, 176, 210)
    elif r == 1:                                          # плечевые шарниры
        base, dark, hi = (120, 130, 152), (74, 82, 102), (168, 178, 198)
    elif r <= 4:                                          # стальной корпус
        base, dark, hi = (104, 116, 142), (68, 76, 98), (152, 164, 190)
    else:                                                 # силовые капсулы
        base, dark, hi = (84, 90, 112), (54, 58, 76), (126, 134, 156)
    pygame.draw.rect(s, base, (x, y, cell, cell))
    pygame.draw.rect(s, hi, (x, y, cell, 4))
    pygame.draw.rect(s, dark, (x, y + cell - 7, cell, 7))
    pygame.draw.rect(s, dark, (x, y, 3, cell))
    for (ax, ay) in ((6, 6), (cell - 7, 6), (6, cell - 8), (cell - 7, cell - 8)):
        pygame.draw.circle(s, hi, (x + ax, y + ay), 2)
        pygame.draw.circle(s, dark, (x + ax, y + ay), 2, 1)
    if r == 1 and c in (0, 4):
        pygame.draw.circle(s, dark, (x + cell // 2, y + cell // 2), 11)
        pygame.draw.circle(s, (176, 186, 206), (x + cell // 2, y + cell // 2), 7)
        pygame.draw.circle(s, dark, (x + cell // 2, y + cell // 2), 7, 2)
    if r == 4 and 1 <= c <= 3:                            # предупреждающая полоса на поясе
        for k in range(-cell, cell, 12):
            pygame.draw.polygon(s, (240, 200, 40), [(x + k, y + cell - 8), (x + k + 7, y + cell - 8),
                                                    (x + k + 14, y + cell - 1), (x + k + 7, y + cell - 1)])
    if r == 6 and c in (0, 1, 3, 4):
        pygame.draw.ellipse(s, (36, 38, 50), (x + 6, y + cell - 12, cell - 12, 10))
    pygame.draw.rect(s, BLACK, (x, y, cell, cell), 2)


def boss_sprites():
    if _SPR:
        return _SPR
    cell = BOSS_CELL
    W, H = BOSS_W, BOSS_H
    mono = pygame.Surface((W, H), pygame.SRCALPHA)
    rob = pygame.Surface((W, H + 40), pygame.SRCALPHA)
    oy = 40
    for r, row in enumerate(BUILD_SHAPE):
        for c, ch in enumerate(row):
            if ch != "X":
                continue
            x, y = c * cell, r * cell
            base = PINK if r <= 1 else SKIN
            dark = (219, 76, 130) if r <= 1 else SKIN_DK
            pygame.draw.rect(mono, base, (x, y, cell, cell))
            pygame.draw.rect(mono, dark, (x, y + cell - 6, cell, 6))
            pygame.draw.rect(mono, (255, 235, 205), (x, y, cell, 5))
            pygame.draw.rect(mono, BLACK, (x, y, cell, cell), 2)
            pygame.draw.rect(mono, WHITE, (x + 7, y + 7, 5, 5))
            _cell_robot(rob, x, y + oy, r, c, cell)
    # визор головы и грудной реактор (светящиеся части рисуются поверх динамически)
    pygame.draw.rect(rob, (22, 24, 36), (cell + 4, oy + cell + 8, 3 * cell - 8, 22), border_radius=4)
    pygame.draw.rect(rob, BLACK, (cell + 4, oy + cell + 8, 3 * cell - 8, 22), 2, border_radius=4)
    pygame.draw.circle(rob, (30, 32, 44), (W // 2, oy + 3 * cell + cell // 2), 16)
    pygame.draw.circle(rob, BLACK, (W // 2, oy + 3 * cell + cell // 2), 16, 2)
    for k in (-1, 1):                                      # вентиляция груди
        for j in range(3):
            pygame.draw.line(rob, (40, 44, 58), (W // 2 + k * 30 - 8, oy + 2 * cell + 10 + j * 8),
                             (W // 2 + k * 30 + 8, oy + 2 * cell + 10 + j * 8), 2)
    pygame.draw.line(rob, (150, 156, 170), (W // 2, oy), (W // 2, 8), 3)       # антенна
    pygame.draw.circle(rob, (90, 20, 24), (W // 2, 7), 5)
    hit = rob.copy()
    hit.fill((120, 120, 120, 0), special_flags=pygame.BLEND_RGB_ADD)
    _SPR["mono"] = mono.convert_alpha()
    _SPR["rob"] = rob.convert_alpha()
    _SPR["hit"] = hit.convert_alpha()
    _SPR["oy"] = oy
    return _SPR


def _bar(scr, col, a, b, w):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d * w / 2, dx / d * w / 2
    pygame.draw.polygon(scr, col, [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny),
                                   (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)])
    pygame.draw.circle(scr, col, (int(a[0]), int(a[1])), int(w / 2))
    pygame.draw.circle(scr, col, (int(b[0]), int(b[1])), int(w / 2))


# ---------------------------------------------------------------------------
# Снаряды и опасные зоны
# ---------------------------------------------------------------------------
class Grenade:
    G = 1150.0

    def __init__(self, x, y, vx, vy, owner=0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.owner = owner
        self.t = 0.0
        self.fuse = 2.1
        self.dead = False
        self.spin = 0.0

    def update(self, dt, bt):
        g = bt.g
        self.t += dt
        self.spin += dt * 9
        self.vy += self.G * dt
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        r = pygame.Rect(int(nx) - 6, int(ny) - 6, 12, 12)
        boss = bt.boss
        hit = False
        if boss is not None and boss.alive_for_hits():
            for pr in boss.parts():
                if pr.colliderect(r):
                    hit = True
                    break
        if not hit and g.solid_hit(r):
            hit = True
        self.x, self.y = nx, ny
        if hit or self.t >= self.fuse or ny > g.world_h + 60:
            self.dead = True
            if ny <= g.world_h + 40:
                bt.explode(self.x, self.y, 92, from_player=True)
        elif int(self.t * 40) % 3 == 0 and not g.lite:
            g.burst(self.x, self.y, [(255, 210, 120), (255, 150, 60)], 1, 40, 0.25, 2, 0)


class Missile:
    def __init__(self, x, y, side):
        self.x, self.y = x, y
        self.vx, self.vy = side * 150.0, -280.0
        self.t = 0.0
        self.life = 3.6
        self.dead = False
        self.ang = -math.pi / 2
        self.speed = 120.0
        self.trail = 0.0

    def update(self, dt, bt):
        g = bt.g
        p = g.nearest_player(self.x, self.y)
        self.t += dt
        if self.t < 0.5:
            self.vx *= (1 - 1.6 * dt)
            self.vy *= (1 - 0.8 * dt)
            self.ang = math.atan2(self.vy, self.vx)
        else:
            tx, ty = p.rect.centerx, p.rect.centery
            want = math.atan2(ty - self.y, tx - self.x)
            diff = (want - self.ang + math.pi) % (2 * math.pi) - math.pi
            turn = 2.1 * dt
            self.ang += clamp(diff, -turn, turn)
            self.speed = min(300.0, self.speed + 340 * dt)
            self.vx, self.vy = math.cos(self.ang) * self.speed, math.sin(self.ang) * self.speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.trail -= dt
        if self.trail <= 0 and not g.lite:
            self.trail = 0.05
            g.burst(self.x, self.y, [(210, 210, 220), (255, 170, 80)], 1, 30, 0.35, 3, -50)
        r = pygame.Rect(int(self.x) - 7, int(self.y) - 7, 14, 14)
        touch = False
        for q in g.alive_players():
            if r.colliderect(q.rect.inflate(6, 6)):
                touch = True
                break
        if touch or g.solid_hit(r) or self.t > self.life:
            self.dead = True
            bt.explode(self.x, self.y, 58, from_player=False)


class Shockwave:
    def __init__(self, x, direction, y):
        self.x, self.dir, self.y = x, direction, y
        self.t = 0.0
        self.life = 2.3
        self.dead = False

    def rect(self):
        return pygame.Rect(int(self.x) - 20, int(self.y) - 50, 40, 50)

    def update(self, dt, bt):
        self.t += dt
        self.x += self.dir * (330 + 40 * self.t) * dt
        if self.t > self.life or self.x < -50 or self.x > bt.g.world_w + 50:
            self.dead = True
            return
        if bt.g.state == "play":
            rc = self.rect()
            for q in bt.g.alive_players():
                if rc.colliderect(q.rect):
                    bt.g.damage_player(self.x - self.dir * 40, q)


# ---------------------------------------------------------------------------
# Босс
# ---------------------------------------------------------------------------
class Arm:
    def __init__(self, side):
        self.side = side
        self.tip = [0.0, 0.0]
        self.target = [0.0, 0.0]
        self.speed = 600.0
        self.open = 0.5
        self.danger = False
        self.elbow = [0.0, 0.0]
        self.vis = 1.0


class Boss:
    L1 = L2 = 150.0

    def __init__(self, bt, x, y):
        self.bt = bt
        self.g = bt.g
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.n = max(1, len(bt.g.players))        # здоровье босса растёт вместе с числом игроков
        self.max_hp = 120 * self.n
        self.hp = self.max_hp
        self.tid = None                           # на кого сейчас охотится босс
        self.retarget_t = 0.0
        self.state = "intro"
        self.t = 0.0
        self.cool = 1.4
        self.last = ""
        self.hit_flash = 0.0
        self.arms = [Arm(-1), Arm(1)]
        self.eye = 0.0
        self.lock = [x, y]
        self.sub = 0
        self.dir = 1
        self.beam = None          # (x0, y0, x1, y1)
        self.beam_hot = False
        self.sweep = 1
        self.atk_arms = []
        self.fired = 0
        self.fire_t = 0.0
        self.spark_t = 0.0
        self.stage_done = {0.75: False, 0.5: False, 0.25: False}
        self.anim = 0.0
        self.lock_ang = 0.0
        self.sub_t = 0.0
        for a in self.arms:
            s = self.shoulder(a)
            a.tip = [s[0] + a.side * 60, s[1] + 130]
            a.target = list(a.tip)

    # --- геометрия
    def shoulder(self, arm):
        return (self.x + arm.side * 90, self.y - BOSS_H / 2 + 54)

    def parts(self):
        x, y = self.x, self.y
        top = y - BOSS_H / 2
        return [pygame.Rect(int(x - 54), int(top + 4), 108, 176),
                pygame.Rect(int(x - 90), int(top + 36), 180, 36),
                pygame.Rect(int(x - 90), int(top + 180), 72, 72),
                pygame.Rect(int(x + 18), int(top + 180), 72, 72)]

    def body_rect(self):
        return pygame.Rect(int(self.x - 90), int(self.y - BOSS_H / 2), 180, BOSS_H)

    def alive_for_hits(self):
        return self.state not in ("dying", "gone")

    def tp(self):
        """Текущая цель босса (живой игрок)."""
        q = self.g.players.get(self.tid)
        if q is None or q.dead:
            q = self.retarget()
        return q

    def retarget(self):
        g = self.g
        al = g.alive_players()
        if not al:
            return g.player
        if len(al) == 1:
            q = al[0]
        else:
            near = g.nearest_player(self.x, self.y)
            q = near if random.random() < 0.55 else random.choice(al)
        self.tid = q.pid
        self.retarget_t = 0.0
        return q

    def phase_idx(self):
        f = self.hp / self.max_hp
        return 0 if f > 0.6 else (1 if f > 0.3 else 2)

    @property
    def rate(self):
        return (1.0, 1.15, 1.35)[self.phase_idx()]

    # --- урон
    def hurt(self, dmg):
        if self.state in ("dying", "gone", "intro"):
            return 0
        if self.state == "stuck":
            dmg *= 2
        self.hp = max(0, self.hp - dmg)
        self.hit_flash = 0.14
        self.bt.stats["dmg"] += dmg
        self.g.play("b_clang")
        for thr in (0.75, 0.5, 0.25):
            if not self.stage_done[thr] and self.hp / self.max_hp <= thr:
                self.stage_done[thr] = True
                self.bt.on_boss_stage(thr)
        if self.hp <= 0:
            self.state = "dying"
            self.t = 0.0
            self.beam = None
            for a in self.arms:
                a.danger = False
        return dmg

    # --- движение
    def hover(self, dt, tx, ty, sp=200.0, spy=230.0, acc=720.0):
        dx, dy = tx - self.x, ty - self.y
        dvx = clamp(dx * 2.4, -sp, sp)
        dvy = clamp(dy * 2.4, -spy, spy)
        self.vx += clamp(dvx - self.vx, -acc * dt, acc * dt)
        self.vy += clamp(dvy - self.vy, -acc * dt, acc * dt)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.x = clamp(self.x, 100, self.g.world_w - 100)
        self.y = clamp(self.y, BOSS_H / 2 + 40, self.g.ground_y - BOSS_H / 2 + 4)

    def home_y(self):
        p = self.tp()
        return max(BOSS_H / 2 + 60, min(self.g.ground_y - 196, p.rect.bottom - 196))

    def idle_target(self):
        p = self.tp()
        off = 230 if self.x >= p.rect.centerx else -230
        return p.rect.centerx + off, self.home_y() + math.sin(self.anim * 2.0) * 10

    # --- IK рук
    def solve_arm(self, arm, dt):
        S = self.shoulder(arm)
        tx, ty = arm.target
        dx, dy = tx - arm.tip[0], ty - arm.tip[1]
        d = math.hypot(dx, dy)
        step = arm.speed * dt
        if d > step and d > 0:
            arm.tip[0] += dx / d * step
            arm.tip[1] += dy / d * step
        else:
            arm.tip[0], arm.tip[1] = tx, ty
        ax, ay = arm.tip[0] - S[0], arm.tip[1] - S[1]
        dd = math.hypot(ax, ay)
        mx = (self.L1 + self.L2) * 0.995
        if dd > mx:
            arm.tip[0] = S[0] + ax / dd * mx
            arm.tip[1] = S[1] + ay / dd * mx
            ax, ay, dd = ax / dd * mx, ay / dd * mx, mx
        dd = max(dd, 30.0)
        a = dd / 2
        h = math.sqrt(max(0.0, self.L1 ** 2 - a * a))
        ux, uy = ax / dd, ay / dd
        px, py = -uy, ux
        if px * arm.side * 1.0 - py * 0.6 < -px * arm.side * 1.0 + py * 0.6:
            px, py = -px, -py
        arm.elbow = [S[0] + ux * a + px * h, S[1] + uy * a + py * h]

    def arm_idle(self, arm):
        S = self.shoulder(arm)
        arm.target = [S[0] + arm.side * (50 + math.sin(self.anim * 1.6 + arm.side) * 16),
                      S[1] + 140 + math.cos(self.anim * 1.3 + arm.side) * 12]
        arm.speed = 420.0
        arm.open = 0.5 + 0.2 * math.sin(self.anim * 2.1)
        arm.danger = False

    def claw_rect(self, arm, w=64, h=64):
        return pygame.Rect(int(arm.tip[0] - w / 2), int(arm.tip[1] - h / 2), w, h)

    # --- выбор атаки
    def pick_attack(self):
        g = self.g
        p = self.tp()
        ph = self.phase_idx()
        on_ground = p.rect.bottom >= g.ground_y - 8
        near_ground = p.rect.bottom >= g.ground_y - 100
        opts = [("smash", 3.0), ("missiles", 2.0), ("laser", 1.0 + ph)]
        if on_ground:
            opts.append(("rake", 2.2))
        if ph >= 1 and near_ground:
            opts.append(("slam", 2.0 + ph))
        opts = [o for o in opts if o[0] != self.last] or opts
        names = [o[0] for o in opts]
        weights = [o[1] for o in opts]
        name = random.choices(names, weights)[0]
        self.start(name)

    def start(self, name):
        g = self.g
        p = self.retarget()
        self.state = name
        self.last = name
        self.t = 0.0
        self.sub = 0
        self.fired = 0
        self.fire_t = 0.0
        self.beam = None
        self.beam_hot = False
        ph = self.phase_idx()
        if name == "smash":
            self.lock = [p.rect.centerx, p.rect.bottom]
            first = self.arms[1] if p.rect.centerx >= self.x else self.arms[0]
            self.atk_arms = [(first, 0)]
            if ph >= 2 or (ph == 1 and random.random() < 0.4):
                other = self.arms[0] if first.side > 0 else self.arms[1]
                self.atk_arms.append((other, -first.side * 150))
            g.play("b_warn")
        elif name == "rake":
            self.dir = 1 if p.rect.centerx >= self.x else -1
            self.atk_arms = [(self.arms[1] if self.dir > 0 else self.arms[0], 0)]
            g.play("b_warn")
        elif name == "laser":
            self.sweep = random.choice((-1, 1))
            g.play("b_laser_c")
        elif name == "missiles":
            g.play("b_warn")
        elif name == "slam":
            self.lock = [p.rect.centerx, g.ground_y]
            g.play("b_roar")

    def finish(self, cool=None):
        self.state = "idle"
        self.t = 0.0
        ph = self.phase_idx()
        self.cool = cool if cool is not None else (2.1, 1.6, 1.1)[ph] + random.random() * 0.6
        self.beam = None
        self.beam_hot = False
        for a in self.arms:
            a.danger = False

    # --- главное обновление
    def update(self, dt):
        g = self.g
        p = self.tp()
        self.t += dt
        self.anim += dt
        self.retarget_t += dt
        self.hit_flash = max(0.0, self.hit_flash - dt)
        st = self.state
        rate = self.rate
        for a in self.arms:
            a.danger = a.danger if st in ("smash", "rake") else False
        calm = True

        if st == "intro":
            self.eye = min(1.0, self.t / 0.8)
            tx, ty = self.x, self.y
            self.hover(dt, tx, ty)
            if self.t > 1.5:
                self.finish(0.6)
        elif st == "idle":
            if self.retarget_t > 3.5:
                p = self.retarget()
            tx, ty = self.idle_target()
            far = abs(p.rect.centerx - self.x)
            sp = 190 * rate + (330 if far > 700 else 0)
            self.hover(dt, tx, ty, sp)
            self.cool -= dt
            self.eye += (0.5 - self.eye) * min(1, dt * 4)
            if self.cool <= 0:
                self.pick_attack()
        elif st == "smash":
            calm = False
            self.st_smash(dt, rate)
        elif st == "rake":
            calm = False
            self.st_rake(dt, rate)
        elif st == "laser":
            calm = False
            self.st_laser(dt, rate)
        elif st == "missiles":
            calm = False
            self.st_missiles(dt, rate)
        elif st == "slam":
            calm = False
            self.st_slam(dt, rate)
        elif st == "stuck":
            calm = False
            self.st_stuck(dt)
        elif st == "dying":
            calm = False
            self.st_dying(dt)

        if calm:
            for a in self.arms:
                self.arm_idle(a)
        for a in self.arms:
            self.solve_arm(a, dt)

        # контакт с телом и клешнями
        if st not in ("dying", "gone", "intro", "inert", "rake") and g.state == "play":
            parts = self.parts()
            for q in g.alive_players():
                pr = q.rect
                for r in parts:
                    if r.colliderect(pr):
                        g.damage_player(self.x, q)
                        break
                for a in self.arms:
                    if a.danger and self.claw_rect(a).colliderect(pr):
                        g.damage_player(a.tip[0], q)
        # лазер
        if self.beam_hot and self.beam and g.state == "play":
            x0, y0, x1, y1 = self.beam
            n = max(2, int(math.hypot(x1 - x0, y1 - y0) // 18))
            for q in g.alive_players():
                pr = q.rect.inflate(8, 8)
                for k in range(n + 1):
                    px = x0 + (x1 - x0) * k / n
                    py = y0 + (y1 - y0) * k / n
                    if pr.collidepoint(px, py):
                        g.damage_player(px, q)
                        break

    # --- атаки
    def st_smash(self, dt, rate):
        g = self.g
        wind = 1.0 / rate
        t = self.t
        arm0 = self.atk_arms[0][0]
        if t < wind:
            if t < wind - 0.55:
                tq = self.tp()
                self.lock = [tq.rect.centerx, tq.rect.bottom]
            self.eye += (1.0 - self.eye) * min(1, dt * 6)
            self.hover(dt, self.lock[0] - arm0.side * 90, self.lock[1] - 205, 380, 260, 1000)
            for arm, off in self.atk_arms:
                S = self.shoulder(arm)
                arm.target = [S[0] + arm.side * 20, S[1] - 190]
                arm.speed = 800
                arm.open = 1.0
            self.arm_other_idle()
        else:
            tt = t - wind
            if self.sub == 0:
                self.sub = 1
                g.play("b_missile")
                for arm, off in self.atk_arms:
                    arm.danger = True
            if self.sub == 1:
                done = True
                for arm, off in self.atk_arms:
                    arm.target = [self.lock[0] + off, self.lock[1] - 8]
                    arm.speed = 2100
                    arm.open = 0.9
                    if math.hypot(arm.tip[0] - arm.target[0], arm.tip[1] - arm.target[1]) > 26:
                        done = False
                if done or tt > 0.45:
                    self.sub = 2
                    self.sub_t = self.t
                    for arm, off in self.atk_arms:
                        self.bt.impact(arm.tip[0], self.lock[1], 84, 0.3)
                        arm.danger = False
                    g.play("b_slam")
                    g.shake = max(g.shake, 0.3)
                    g.shake_amp = 7
            elif self.sub == 2:
                for arm, off in self.atk_arms:
                    arm.open = 0.2
                if self.t - self.sub_t > 0.6:
                    self.finish()
            self.arm_other_idle()

    def arm_other_idle(self):
        used = [a for a, _ in self.atk_arms]
        for a in self.arms:
            if a not in used:
                self.arm_idle(a)

    def st_rake(self, dt, rate):
        g = self.g
        p = self.tp()
        lane = g.ground_y
        wind = 0.95 / rate
        arm = self.atk_arms[0][0]
        d = self.dir
        t = self.t
        if t < wind:
            self.eye += (1.0 - self.eye) * min(1, dt * 6)
            self.hover(dt, p.rect.centerx - d * 340, lane - 196, 420, 260, 1000)
            arm.target = [self.x + d * 165, lane - 24]
            arm.speed = 1500
            arm.open = 1.0
            self.arm_other_idle()
        else:
            dur = 1.1
            tt = t - wind
            if tt < dur:
                arm.danger = True
                sp = 420 * math.sqrt(rate)
                self.vx += clamp(d * sp - self.vx, -1400 * dt, 1400 * dt)
                self.x += self.vx * dt
                self.x = clamp(self.x, 100, g.world_w - 100)
                self.y += clamp(lane - 196 - self.y, -300 * dt, 300 * dt)
                arm.target = [self.x + d * 165, lane - 24]
                arm.speed = 4000
                arm.open = 0.9
                self.spark_t -= dt
                if self.spark_t <= 0:
                    self.spark_t = 0.05
                    g.burst(arm.tip[0], lane - 4, [YELLOW, ORANGE, WHITE], 3, 180, 0.3, 3, 400)
                if int(tt * 10) != int((tt - dt) * 10):
                    g.shake = max(g.shake, 0.08)
                    g.shake_amp = 3
            else:
                arm.danger = False
                self.vx *= max(0.0, 1 - 4 * dt)
                self.x += self.vx * dt
                if tt > dur + 0.5:
                    self.finish()
            self.arm_other_idle()

    def eye_origin(self):
        return self.x, self.y - BOSS_H / 2 + 54

    def st_laser(self, dt, rate):
        g = self.g
        p = self.tp()
        charge = 1.2 / rate
        fire = 0.9
        ph = self.phase_idx()
        t = self.t
        ox, oy = self.eye_origin()
        if t < charge:
            self.eye = 1.0
            side = 1 if self.x >= p.rect.centerx else -1
            self.hover(dt, p.rect.centerx + side * 250, self.home_y() - 40, 260, 260)
            ox, oy = self.eye_origin()
            if t < charge - 0.65:
                self.lock_ang = math.atan2(p.rect.centery - oy, p.rect.centerx - ox)
            ln = 1300
            self.beam = (ox, oy, ox + math.cos(self.lock_ang) * ln, oy + math.sin(self.lock_ang) * ln)
            self.beam_hot = False
            self.arm_idle_all()
        elif t < charge + fire * (2 if ph >= 2 else 1):
            if self.sub == 0:
                self.sub = 1
                g.play("b_laser")
            u = (t - charge) / fire
            seg = int(u)
            frac = u - seg
            sw = self.sweep if seg % 2 == 0 else -self.sweep
            ang = self.lock_ang + sw * (-0.2 + 0.4 * frac)
            self.vx *= max(0.0, 1 - 3 * dt)
            self.x += self.vx * dt
            ln = 1300
            ex, ey = ox, oy
            for k in range(1, int(ln // 24) + 1):
                px = ox + math.cos(ang) * 24 * k
                py = oy + math.sin(ang) * 24 * k
                ex, ey = px, py
                if py > g.ground_y or g.solid_hit(pygame.Rect(int(px) - 6, int(py) - 6, 12, 12)):
                    break
            self.beam = (ox, oy, ex, ey)
            self.beam_hot = True
            self.arm_idle_all()
            if int(t * 12) != int((t - dt) * 12):
                g.burst(ex, ey, [(255, 120, 90), WHITE], 3, 160, 0.3, 3, 300)
        else:
            self.beam = None
            self.beam_hot = False
            self.arm_idle_all()
            if t > charge + fire * (2 if ph >= 2 else 1) + 0.45:
                self.finish()

    def arm_idle_all(self):
        for a in self.arms:
            self.arm_idle(a)

    def st_missiles(self, dt, rate):
        g = self.g
        ph = self.phase_idx()
        total = (4, 6, 8)[ph]
        wind = 0.7 / rate
        t = self.t
        self.eye += (0.8 - self.eye) * min(1, dt * 5)
        if t < wind:
            self.hover(dt, self.x, self.home_y() - 30, 160, 200)
        else:
            self.hover(dt, self.idle_target()[0], self.home_y() - 20, 120, 200)
            self.fire_t -= dt
            if self.fired < total and self.fire_t <= 0:
                self.fire_t = 0.24 / rate
                arm = self.arms[self.fired % 2]
                S = self.shoulder(arm)
                self.bt.missiles.append(Missile(S[0] + arm.side * 20, S[1] - 10, arm.side))
                self.fired += 1
                g.play("b_missile")
            if self.fired >= total and self.fire_t < -0.5:
                self.finish()
        for a in self.arms:
            S = self.shoulder(a)
            a.target = [S[0] + a.side * 70, S[1] - 90]
            a.speed = 600
            a.open = 1.0
            a.danger = False

    def st_slam(self, dt, rate):
        g = self.g
        p = self.tp()
        t = self.t
        floor_c = g.ground_y - BOSS_H / 2 + 4
        up = 1.0 / rate
        if t < up:
            self.hover(dt, p.rect.centerx, max(BOSS_H / 2 + 50, g.ground_y - 560), 300, 520, 1500)
            self.lock = [p.rect.centerx, g.ground_y]
            self.eye = 1.0
        elif self.sub == 0 and t < up + 0.5 / rate:
            self.vx *= max(0.0, 1 - 6 * dt)
            self.x += self.vx * dt
            self.vy = 0.0
        elif self.sub in (0, 1):
            if self.sub == 0:
                self.sub = 1
                g.play("b_missile")
            self.vy = 1700.0
            self.x += clamp(self.lock[0] - self.x, -400 * dt, 400 * dt)
            self.y += self.vy * dt
            if self.y >= floor_c:
                self.y = floor_c
                self.vy = 0.0
                self.sub = 2
                self.bt.slam_impact(self.x)
                self.state = "stuck"
                self.t = 0.0
        for a in self.arms:
            S = self.shoulder(a)
            a.target = [S[0] + a.side * 60, S[1] - 130]
            a.speed = 900
            a.open = 1.0

    def st_stuck(self, dt):
        g = self.g
        self.eye = 0.2 + 0.2 * math.sin(self.t * 14)
        self.vx = self.vy = 0.0
        self.spark_t -= dt
        if self.spark_t <= 0:
            self.spark_t = 0.12
            g.burst(self.x + random.randint(-60, 60), self.y - 60, [(200, 200, 210), ORANGE, YELLOW], 3, 150, 0.5, 3, 300)
        for a in self.arms:
            S = self.shoulder(a)
            a.target = [S[0] + a.side * 90, g.ground_y - 14]
            a.speed = 700
            a.open = 0.1
        if self.t > 1.7:
            self.finish(0.5)

    def st_dying(self, dt):
        g = self.g
        self.eye = 0.5 + 0.5 * math.sin(self.t * 30)
        self.hit_flash = 0.05 if int(self.t * 16) % 2 == 0 else 0.0
        self.vx *= max(0.0, 1 - 3 * dt)
        self.x += self.vx * dt
        self.y += (30 + self.t * 20) * dt
        self.y = min(self.y, g.ground_y - BOSS_H / 2 + 4)
        for a in self.arms:
            S = self.shoulder(a)
            a.target = [S[0] + a.side * 55, S[1] + 210]
            a.speed = 300
            a.open = 0.0
            a.danger = False
        self.spark_t -= dt
        if self.spark_t <= 0:
            self.spark_t = max(0.07, 0.3 - self.t * 0.1)
            bx = self.x + random.randint(-80, 80)
            by = self.y + random.randint(-120, 110)
            self.bt.small_boom(bx, by)

    # --- рисование
    def draw(self, scr, cam, cy, convert=1.0):
        spr = boss_sprites()
        x, y = self.x - cam, self.y - cy
        oy = spr["oy"]
        top = int(y - BOSS_H / 2)
        # язык пламени двигателей
        if self.state not in ("dying", "stuck") and convert >= 1.0:
            for sx in (-54, 54):
                fl = 28 + int(18 * math.sin(self.anim * 40 + sx)) + (14 if abs(self.vx) > 150 else 0)
                bx = int(x + sx)
                by = int(y + BOSS_H / 2 - 4)
                pygame.draw.polygon(scr, (255, 120, 40), [(bx - 14, by), (bx + 14, by), (bx, by + fl + 10)])
                pygame.draw.polygon(scr, (255, 214, 110), [(bx - 8, by), (bx + 8, by), (bx, by + fl)])
                pygame.draw.polygon(scr, (255, 255, 230), [(bx - 3, by), (bx + 3, by), (bx, by + fl // 2)])
        # руки сзади тела (плечевая часть) и спереди (клешни) — рисуем после тела
        if convert < 1.0:
            scr.blit(spr["mono"], (int(x - BOSS_W / 2), top))
            h = int((BOSS_H + oy) * convert)
            if h > 0:
                area = pygame.Rect(0, BOSS_H + oy - h, BOSS_W, h)
                scr.blit(spr["rob"], (int(x - BOSS_W / 2), top - oy + area.y), area)
                ly = top - oy + area.y
                pygame.draw.line(scr, (255, 200, 140), (int(x - BOSS_W / 2), ly), (int(x + BOSS_W / 2), ly), 3)
        else:
            img = spr["hit"] if self.hit_flash > 0 else spr["rob"]
            scr.blit(img, (int(x - BOSS_W / 2), top - oy))
        self.draw_face(scr, x, y, convert)
        if convert >= 1.0:
            for a in self.arms:
                self.draw_arm(scr, a, cam, cy)

    def draw_face(self, scr, x, y, convert):
        if convert < 0.7:
            return
        ph = self.phase_idx()
        e = clamp(self.eye, 0.0, 1.0)
        ey = int(y - BOSS_H / 2 + 54)
        base = ((255, 50, 40), (255, 130, 40), (255, 240, 200))[ph]
        glow = int(120 + 135 * e)
        col = (min(255, base[0]), min(255, int(base[1] * (0.5 + 0.5 * e))), min(255, int(base[2] * (0.5 + 0.5 * e))))
        for s in (-1, 1):
            cx = int(x + s * 30)
            pts = [(cx - s * 20, ey - 8), (cx + s * 10, ey - 1), (cx + s * 10, ey + 7), (cx - s * 20, ey + 3)]
            pygame.draw.polygon(scr, col, pts)
            pygame.draw.polygon(scr, (255, 255, 255) if e > 0.7 else (255, 210, 190),
                                [(cx - s * 12, ey - 3), (cx + s * 4, ey), (cx + s * 4, ey + 3), (cx - s * 12, ey + 1)])
        # реактор
        ry = int(y - BOSS_H / 2 + 3 * BOSS_CELL + BOSS_CELL // 2)
        pulse = 0.5 + 0.5 * math.sin(self.anim * (4 + 3 * ph))
        rc = (255, int(110 + 100 * pulse), int(50 + 60 * pulse))
        pygame.draw.circle(scr, rc, (int(x), ry), 11)
        pygame.draw.circle(scr, (255, 245, 210), (int(x), ry), 5)
        # антенна
        if int(self.anim * 3) % 2 == 0:
            pygame.draw.circle(scr, (255, 70, 70), (int(x), int(y - BOSS_H / 2) - 33), 5)

    def draw_arm(self, scr, a, cam, cy):
        S = self.shoulder(a)
        s = (S[0] - cam, S[1] - cy)
        e = (a.elbow[0] - cam, a.elbow[1] - cy)
        t = (a.tip[0] - cam, a.tip[1] - cy)
        dark, mid, hi = (44, 48, 62), (112, 122, 146), (176, 186, 206)
        _bar(scr, BLACK, s, e, 30)
        _bar(scr, mid, s, e, 22)
        _bar(scr, hi, (s[0] - 2, s[1] - 3), (e[0] - 2, e[1] - 3), 6)
        _bar(scr, BLACK, e, t, 26)
        _bar(scr, mid, e, t, 18)
        _bar(scr, hi, (e[0] - 2, e[1] - 3), (t[0] - 2, t[1] - 3), 5)
        # гидроцилиндр
        mx, my = (s[0] + e[0]) / 2, (s[1] + e[1]) / 2
        pygame.draw.line(scr, (210, 160, 70), (s[0] + a.side * 10, s[1] + 8), (mx + a.side * 14, my), 4)
        for p_, r_ in ((s, 18), (e, 15)):
            pygame.draw.circle(scr, BLACK, (int(p_[0]), int(p_[1])), r_ + 2)
            pygame.draw.circle(scr, (96, 104, 128), (int(p_[0]), int(p_[1])), r_)
            pygame.draw.circle(scr, (186, 194, 212), (int(p_[0]), int(p_[1])), r_ // 3)
        # клешня
        th = math.atan2(t[1] - e[1], t[0] - e[0])
        op = a.open
        claw_col = (255, 110, 90) if a.danger else (150, 160, 184)
        for sgn in (-1, 1):
            ang = th + sgn * (0.12 + 0.62 * op)
            ar = (math.cos(ang), math.sin(ang))
            ap = (-ar[1], ar[0])
            b1 = (t[0] - ap[0] * sgn * 6 * 0, t[1])
            pts = [(t[0] + ap[0] * sgn * 9, t[1] + ap[1] * sgn * 9),
                   (t[0] + ar[0] * 30 + ap[0] * sgn * 13, t[1] + ar[1] * 30 + ap[1] * sgn * 13),
                   (t[0] + ar[0] * 56, t[1] + ar[1] * 56),
                   (t[0] + ar[0] * 32 - ap[0] * sgn * 4, t[1] + ar[1] * 32 - ap[1] * sgn * 4),
                   (t[0] - ap[0] * sgn * 6, t[1] - ap[1] * sgn * 6)]
            pygame.draw.polygon(scr, BLACK, pts, 0)
            inner = [(t[0] + (px - t[0]) * 0.8 + 0, t[1] + (py - t[1]) * 0.8) for px, py in pts]
            pygame.draw.polygon(scr, claw_col, inner, 0)
        pygame.draw.circle(scr, BLACK, (int(t[0]), int(t[1])), 13)
        pygame.draw.circle(scr, claw_col, (int(t[0]), int(t[1])), 10)


# ---------------------------------------------------------------------------
# Ночной фон, свет, спрайты предметов
# ---------------------------------------------------------------------------
SCREEN_H = 540
BASE_W = 960
CAM_PAD = 280
LOCK_PHASES = ("intro", "build", "built", "quake", "transform", "dying")
ALL_CTL = ("left", "right", "jump", "run", "up", "down", "grenade")
_GLOW = {}


def glow_sprite(r, col, level=4):
    key = (r, col, level)
    s = _GLOW.get(key)
    if s is None:
        s = pygame.Surface((r * 2, r * 2)).convert()
        s.fill((0, 0, 0))
        steps = 30
        k0 = level / 4.0
        for i in range(steps, 0, -1):
            k = i / steps
            f = (1.0 - k) ** 1.4 * k0
            c = (min(255, int(col[0] * f)), min(255, int(col[1] * f)), min(255, int(col[2] * f)))
            pygame.draw.circle(s, c, (r, r), max(1, int(r * k)))
        _GLOW[key] = s
    return s


def add_glow(scr, x, y, r, col, level=4):
    if x + r < 0 or x - r > scr.get_width() or y + r < 0 or y - r > scr.get_height():
        return
    scr.blit(glow_sprite(r, col, level), (int(x - r), int(y - r)), special_flags=pygame.BLEND_RGB_ADD)


def pickup_sprite(g, kind):
    key = ("bp", kind)
    s = g._spr.get(key)
    if s is None:
        if kind == "grenade":
            s = g._new_sprite(34, 38)
            pygame.draw.circle(s, BLACK, (17, 23), 13)
            pygame.draw.circle(s, (86, 112, 64), (17, 23), 11)
            pygame.draw.circle(s, (120, 150, 90), (14, 19), 4)
            for k in (-1, 0, 1):
                pygame.draw.line(s, (60, 80, 44), (8, 23 + k * 5), (26, 23 + k * 5), 1)
            pygame.draw.rect(s, BLACK, (13, 6, 8, 8))
            pygame.draw.rect(s, (200, 200, 210), (14, 7, 6, 6))
            pygame.draw.line(s, YELLOW, (21, 8), (27, 3), 2)
            pygame.draw.circle(s, ORANGE, (28, 3), 2)
        else:
            s = g._new_sprite(34, 30)
            pygame.draw.rect(s, BLACK, (3, 5, 28, 22), border_radius=4)
            pygame.draw.rect(s, (246, 246, 250), (5, 7, 24, 18), border_radius=3)
            pygame.draw.rect(s, RED, (14, 9, 6, 14))
            pygame.draw.rect(s, RED, (10, 13, 14, 6))
            pygame.draw.rect(s, BLACK, (12, 2, 10, 4), 2)
        g._spr[key] = s
    return s


def _night_cloud(surf, x, y, scale, col):
    w, h = int(74 * scale), int(22 * scale)
    pygame.draw.ellipse(surf, col, (x, y, w, h))
    pygame.draw.ellipse(surf, col, (x + int(16 * scale), y - int(12 * scale), int(44 * scale), int(26 * scale)))
    pygame.draw.ellipse(surf, col, (x + int(38 * scale), y - int(6 * scale), int(40 * scale), int(22 * scale)))


def build_night_assets(g):
    """Фон ночного города: небо, звёзды, луна в ночном колпаке, дальние дома, краны, холмы, тучи."""
    W = g.W
    A = {"W": W}
    sky = pygame.Surface((W, SCREEN_H)).convert()
    top, bot = (4, 6, 26), (34, 40, 92)
    for y in range(0, SCREEN_H, 6):
        t = y / SCREEN_H
        pygame.draw.rect(sky, tuple(int(top[i] + (bot[i] - top[i]) * (t ** 1.2)) for i in range(3)), (0, y, W, 6))
    A["sky"] = sky
    rnd = random.Random(7)
    sa = g._new_sprite(W + 80, 340)
    sb = g._new_sprite(W + 80, 340)
    for i in range(120):
        x, y = rnd.randrange(W + 80), rnd.randrange(330)
        col = rnd.choice(((255, 255, 255), (200, 212, 255), (255, 240, 200)))
        sz = 2 if rnd.random() < 0.25 else 1
        pygame.draw.rect(sa, col, (x, y, sz, sz))
        if i % 3:
            pygame.draw.rect(sb, col, (x, y, sz, sz))
    A["stars"] = (sa, sb)
    # луна в ночном колпаке
    m = g._new_sprite(120, 124)
    cx, cy = 52, 70
    pygame.draw.circle(m, (232, 234, 210), (cx, cy), 32)
    pygame.draw.circle(m, (246, 246, 226), (cx - 4, cy - 4), 27)
    for (dx, dy, rr) in ((-12, 8, 6), (10, -6, 4), (14, 14, 5)):
        pygame.draw.circle(m, (214, 218, 192), (cx + dx, cy + dy), rr)
    pygame.draw.arc(m, BLACK, (cx - 18, cy - 4, 14, 8), math.pi * 1.1, math.pi * 1.9, 2)
    pygame.draw.arc(m, BLACK, (cx + 4, cy - 4, 14, 8), math.pi * 1.1, math.pi * 1.9, 2)
    pygame.draw.arc(m, BLACK, (cx - 8, cy + 8, 16, 10), math.pi * 1.1, math.pi * 1.9, 2)
    pygame.draw.polygon(m, (200, 50, 70), [(cx - 32, cy - 14), (cx + 8, cy - 40), (cx + 36, cy - 12), (cx + 60, cy + 6), (cx + 44, cy - 2)])
    pygame.draw.polygon(m, (160, 30, 54), [(cx - 32, cy - 14), (cx + 8, cy - 40), (cx + 14, cy - 34)])
    pygame.draw.rect(m, (245, 245, 250), (cx - 34, cy - 20, 70, 9), border_radius=4)
    pygame.draw.circle(m, (245, 245, 250), (cx + 60, cy + 6), 7)
    A["moon"] = m
    A["moon_c"] = (cx, cy)
    # дальние дома (период 300)
    s = g._new_sprite(2300, 200)
    for i in range(8):
        bx = i * 300
        bh = 90 + (i * 53) % 90
        pygame.draw.rect(s, (24, 30, 68), (bx, SCREEN_H - 72 - bh - g.bld_y0, 120, bh))
        pygame.draw.rect(s, (34, 42, 88), (bx, SCREEN_H - 72 - bh - g.bld_y0, 120, 4))
        for wy in range(SCREEN_H - 60 - bh, SCREEN_H - 90, 26):
            for wx in range(bx + 12, bx + 105, 24):
                lit = rnd.random() < 0.3
                pygame.draw.rect(s, (255, 214, 120) if lit else (36, 46, 96), (wx, wy - g.bld_y0, 12, 14))
    A["bld"] = s
    s = g._new_sprite(1800, 270)
    for i in range(3):
        sx = i * 620 + 240 + 70
        c = (20, 26, 58)
        pygame.draw.rect(s, c, (sx, 10, 8, 250))
        pygame.draw.rect(s, c, (sx - 70, 2, 210, 8))
        pygame.draw.line(s, c, (sx + 120, 10), (sx + 120, 65), 3)
        pygame.draw.rect(s, c, (sx + 106, 65, 28, 22))
        pygame.draw.circle(s, (255, 60, 60), (sx - 66, 0), 3)
    A["crane"] = s
    s = g._new_sprite(1900, 110)
    for i in range(7):
        pygame.draw.ellipse(s, (14, 38, 58), (i * 260, 0, 300, 110))
    A["hill"] = s
    P = W + 260
    A["cloud_period"] = P
    strip = g._new_sprite(P, 220)
    for i in range(7):
        b = (i * 360 + 80) % P
        cy2 = 52 + (i * 41) % 130
        sc = 1.0 + (i % 3) * 0.25
        _night_cloud(strip, b, cy2, sc, (36, 44, 98))
        _night_cloud(strip, b - P, cy2, sc, (36, 44, 98))
    A["cloud"] = strip
    return A


def wrap_text(font, text, width):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        t = w if not cur else cur + " " + w
        if not cur or font.size(t)[0] <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class Boom:
    __slots__ = ("x", "y", "r", "t", "dur", "kind")

    def __init__(self, x, y, r, dur, kind="fire"):
        self.x, self.y, self.r, self.t, self.dur, self.kind = x, y, r, 0.0, dur, kind


# ---------------------------------------------------------------------------
# Контроллер режима
# ---------------------------------------------------------------------------
JOKES_SUB = [
    "Город спасён. Правда, он об этом не просил.",
    "Страховая уже пишет письмо. Начинается оно со слов «Вы серьёзно?».",
    "Соседи вызвали полицию. Полиция вызвала подкрепление. Подкрепление ушло домой.",
    "Писюн побеждён. Но говорят, у него остались братья.",
]
JOKES_NEWS = [
    "СВОДКА: этой ночью строитель построил писюна, испугался и победил его. Пострадавших нет, кроме репутации писюна.",
    "ОТ РЕДАКЦИИ: проект «Новый писюн» заморожен. Блоки сданы в металлолом. Прораб в отпуске. Навсегда.",
    "ЭКСПЕРТЫ СЧИТАЮТ: гигантский робот в форме писюна — это не лучшая идея. Но и не худшая за этот год.",
]
RANKS = [
    (900, "S", "ГЛАВНЫЙ ПО ПИСЮНАМ", (255, 214, 90)),
    (700, "A", "ПРОРАБ-ЛЕГЕНДА", (120, 255, 150)),
    (450, "B", "СТРОИТЕЛЬ С ХАРАКТЕРОМ", (130, 200, 255)),
    (-9999, "C", "ВЫЖИЛ — И НА ТОМ СПАСИБО", (255, 150, 130)),
]


class Battle:
    def __init__(self, game):
        self.g = game
        if getattr(game, "bjobs", None) is None:
            game.bjobs = build_battle_sounds(game)
        self.jobs = game.bjobs
        try:
            pygame.mixer.set_num_channels(20)
        except Exception:
            pass
        self.A = None
        self._portrait = None
        self._cells = {}
        self._sleeper = None
        self.stands = None
        self.reset()

    # ------------------------------------------------------------ состояние
    def reset(self):
        g = self.g
        L = g.lvl
        self.phase = "intro"
        self.t = 0.0
        self.total = 0.0
        self.boss_time = 0.0
        self.dlg = None
        self.toast = None
        self.toast_q = []
        self.boss = None
        self.grenades, self.missiles, self.shocks, self.booms = [], [], [], []
        self.uid = 0                              # номера реплик (для синхронизации по сети)
        self.dmap = {}
        self.builder_pid = 0
        self.nplayers = 1
        self.flash = 0.0
        self.tint = 0.0
        self.tint_col = (255, 150, 60)
        self.convert = 0.0
        self.placed, self.landed, self.flying = set(), {}, []
        self.build_seq, self.build_i = [], 0
        self.supply = []
        self.stats = dict(dmg=0, thrown=0, hits=0, hurt=0, dodged=0, meds=0, attempts=1,
                          missiles=0, blocks=0)
        self.want_music = None
        self.title_t = -1.0
        self.sleeping = g.role is None            # в кооперативе героя в кровати не показываем
        self.woke = False
        self.talked = False
        self.excl = 0.0
        self.q_talked = False
        self.roared = False
        self.res = None
        self.res_t = 0.0
        self._fan = False
        self._slam_snd = False
        self.bar_disp = 1.0
        self.firework_t = 0.0
        self.boss_started = False
        self.intro_toasts = []
        self.zone_hint_t = 0.0
        self.fired = set()
        self.trig = self._make_triggers(L)
        self.btn = pygame.Rect(0, 0, 300, 72)
        W = g.W
        self.btn.center = (W // 2, 330)
        g.safe = True
        g.shake_amp = 5.0
        p = g.player
        g.camera_x = clamp(p.rect.centerx - W // 2, -CAM_PAD, g.world_w - W + CAM_PAD)
        g.camera_y = float(g.cam_max_y)
        g.flash_timer = 0.0

    def _make_triggers(self, L):
        tr = []
        if L.spikes:
            tr.append((min(c for c, _ in L.spikes) - 5, "spike", ["Шипы... Кто-то очень не любит прохожих."]))
        arm = sorted(tx for (tx, ty, tw, th, st, pal) in L.solids if st == "armor")
        if arm:
            tr.append((arm[0] - 3, "armor", ["Бронированное здание. Кто-то тут явно готовился к чему-то плохому."]))
        if len(L.districts) > 1:
            tr.append((L.districts[1][0] + 2, "d1", ["Деловой центр. Ночью тут пусто и жутковато."]))
        tr.append((int(L.zone_tx * 0.5), "half", ["БУМ! Опять! Оно всё ещё там... и, кажется, нервничает."]))
        if len(L.districts) > 2:
            tr.append((L.districts[2][0] + 2, "d2", ["Промзона. Шипов тут — как на ёжике."]))
        tr.append((L.zone_tx - 18, "near", ["Вижу площадку! Фундамент на месте. Осталось собрать блоки."]))
        return sorted(tr)

    @property
    def locked(self):
        return self.phase in LOCK_PHASES or (self.dlg is not None and self.dlg.blocking)

    def hidden(self):
        if self.locked:
            return ALL_CTL
        if self.phase == "explore":
            return ("grenade",)
        return ()

    def say(self, lines, on_done=None, blocking=True):
        d = Dialogue(lines, on_done, blocking)
        self.uid += 1
        d.uid = self.uid
        self.dmap[d.uid] = d
        if self.g.role == "host":
            self.g.net_broadcast({"t": "bsay", "id": d.uid, "lines": list(lines), "blk": 1 if blocking else 0})
        if blocking:
            self.dlg = d
        else:
            if self.toast is None:
                self.toast = d
            else:
                self.toast_q.append(d)

    def blip(self):
        self.g.play("b_blip", net=False)

    def set_tint(self, v, col):
        self.tint = v
        self.tint_col = col
        g = self.g
        if g.bc:
            g.fx_emit(("t", v, list(col)))

    def add_boom(self, x, y, r, dur, kind="fire", net=True):
        self.booms.append(Boom(x, y, r, dur, kind))
        g = self.g
        if net and g.bc:
            g.fx_emit(("bm", int(x), int(y), int(r), dur, kind))

    def hurt_fx(self):
        """Красная вспышка экрана — только у того, кому больно."""
        self.tint = 0.35
        self.tint_col = (255, 40, 40)

    def music(self, name, loop=False, net=True):
        g = self.g
        if net and g.bc:
            g.fx_emit(("m", name, 1 if loop else 0))
        s = g.sounds.get(name)
        if s is None:
            self.want_music = (name, loop)
            return
        self.want_music = None
        if g.sound_on:
            try:
                s.play(-1 if loop else 0)
            except Exception:
                pass

    def stop_music(self, net=True):
        if net and self.g.bc:
            self.g.fx_emit(("ms",))
        for n in ("b_music_epic", "b_music_boss"):
            s = self.g.sounds.get(n)
            if s is not None:
                try:
                    s.stop()
                except Exception:
                    pass
        self.want_music = None

    def on_state(self, state):
        try:
            if state == "pause":
                pygame.mixer.pause()
            elif state == "play":
                pygame.mixer.unpause()
            elif state == "bwin":
                self.stop_music()
            else:
                pygame.mixer.stop()
        except Exception:
            pass

    # ------------------------------------------------------------ события игры
    def on_hurt(self, p=None):
        self.stats["hurt"] += 1

    def on_brick(self, cx, cy):
        g = self.g
        n = g.bricks_collected
        g.score += 100
        self.stats["blocks"] = n
        g.burst(cx, cy, [YELLOW, ORANGE, (255, 230, 150)], 16, 240, 0.55)
        g.play("collect")
        g.float_text(cx, cy - 18, "+1 блок (%d/%d)" % (n, CELLS))
        if n == 12:
            self.say(["Уже полрюкзака блоков. А грохот — всё ближе."], blocking=False)
        elif n >= CELLS:
            g.flash_msg("ВСЕ БЛОКИ СОБРАНЫ! БЕГИТЕ НА СТРОЙПЛОЩАДКУ >>" if g.role else
                        "ВСЕ БЛОКИ СОБРАНЫ! БЕГИ НА СТРОЙПЛОЩАДКУ >>", 4.0)
            self.say(["Все блоки собраны! Теперь — на стройплощадку."], blocking=False)

    def add_grenades(self, p, n, cx, cy):
        g = self.g
        if p.gren >= GRENADE_CAP:
            return False
        p.gren = min(GRENADE_CAP, p.gren + n)
        g.burst(cx, cy, [(160, 200, 120), YELLOW, WHITE], 12, 200, 0.5)
        g.float_text(cx, cy - 16, "+%d гранаты" % n, (170, 220, 130))
        g.play("collect")
        return True

    def on_medkit(self, p, cx, cy):
        g = self.g
        if p.hp >= 5:
            return False
        p.hp = min(5, p.hp + 3)
        self.stats["meds"] += 1
        g.burst(cx, cy, [WHITE, PINK, GREEN], 16, 220, 0.55)
        g.float_text(cx, cy - 16, "+3 HP", GREEN)
        g.play("heart")
        return True

    # ------------------------------------------------------------ главный апдейт
    def update(self, dt):
        g = self.g
        self.total += dt
        self.t += dt
        self.jobs.pump(0.004 if self.phase in ("intro", "explore") else 0.0016)
        if self.want_music is not None:
            nm, lp = self.want_music
            if nm in g.sounds:
                self.music(nm, lp)
        for q in g.players.values():
            q.throw_cd = max(0.0, q.throw_cd - dt)
        self.tint = max(0.0, self.tint - dt * 1.4)
        if self.dlg is not None:
            self.dlg.update(dt, self.blip)
            if self.dlg.done:
                self.dlg = None
        if self.toast is not None:
            self.toast.update(dt, lambda: None)
            if self.toast.done:
                self.toast = self.toast_q.pop(0) if self.toast_q else None
        getattr(self, "ph_" + self.phase)(dt)
        self.update_fx(dt)
        self.update_supply(dt)
        g.safe = self.locked or self.phase == "intro"
        if g.shake <= 0:
            g.shake_amp = 5.0

    # --- интро: сон, грохот, пробуждение
    def ph_intro(self, dt):
        g = self.g
        p = g.player
        t = self.t
        coop = g.role is not None
        t_boom, t_talk = (0.8, 2.2) if coop else (1.5, 3.0)
        self.flash = 0.0
        if t >= t_boom and not self.woke:
            self.woke = True
            self.sleeping = False
            g.play("b_boom")
            g.shake = 1.6
            g.shake_amp = 8.0
            self.set_tint(0.8, (255, 170, 80))
            if not coop:
                self.excl = 1.3
                p.vel.y = -320
                p.facing = 1
        if self.woke:
            self.excl = max(0.0, self.excl - dt)
        if t >= t_talk and not self.talked:
            self.talked = True
            if coop:
                self.say(["БА-БАХ!!! Что это было?!",
                          "Надо глянуть. И заодно собрать блоки: писюн сам себя не построит."],
                         on_done=self.start_explore)
            else:
                self.say(["БА-БАХ!!! Что это было?!",
                          "Три часа ночи, а какая-то громадина грохочет на весь город.",
                          "Надо глянуть. И заодно собрать блоки: писюн сам себя не построит."],
                         on_done=self.start_explore)

    def start_explore(self):
        g = self.g
        self.phase = "explore"
        self.t = 0.0
        g.flash_msg("СОБИРАЙТЕ БЛОКИ — ИЗ НИХ ВЫРАСТЕТ НОВЫЙ ПИСЮН" if g.role else
                    "СОБИРАЙ БЛОКИ — ИЗ НИХ ВЫРАСТЕТ НОВЫЙ ПИСЮН", 4.5)

    # --- исследование ночного города
    def ph_explore(self, dt):
        g = self.g
        col = g.lead_col()
        for (c, key, lines) in self.trig:
            if key in self.fired or col < c:
                continue
            self.fired.add(key)
            if key == "half":
                g.play("b_boom")
                g.shake = 0.9
                g.shake_amp = 6.0
                self.set_tint(0.35, (255, 170, 80))
            if self.dlg is None:
                self.say(lines, blocking=False)
            break
        self.zone_hint_t = max(0.0, self.zone_hint_t - dt)
        at_zone = any(q.rect.centerx >= g.zone_x for q in g.alive_players())
        if at_zone and g.bricks_collected < CELLS and self.zone_hint_t <= 0 and self.dlg is None:
            self.zone_hint_t = 7.0
            self.say(["Не хватает блоков: %d из %d. Монумент так не построишь." % (g.bricks_collected, CELLS)],
                     blocking=False)

    def can_build_for(self, q):
        g = self.g
        return (self.phase == "explore" and self.dlg is None and g.bricks_collected >= CELLS
                and q is not None and not q.dead and q.rect.centerx >= g.zone_x and g.state == "play")

    def can_build(self):
        return self.can_build_for(self.g.player)

    def tap_dialog(self):
        """Реплику героя листает любой игрок."""
        if self.dlg is not None and self.dlg.blocking:
            self.dlg.tap()
            if self.dlg.done:
                self.dlg = None

    def start_build(self, p=None):
        g = self.g
        p = p or g.player
        self.builder_pid = p.pid
        self.phase = "build"
        self.t = 0.0
        p.vel.x = 0
        p.facing = 1
        order = g.build_order()
        seq = []
        tt, iv = 1.2, 0.52
        for (r, c) in order:
            seq.append((tt, r, c))
            tt += iv
            iv = max(0.1, iv * 0.87)
        self.build_seq = seq
        self.build_i = 0
        self.flying = []
        self.placed = set()
        self.landed = {}
        self.toast = None
        self.toast_q = []
        self.music("b_music_epic")
        g.flash_msg("", 0.0)

    def ph_build(self, dt):
        g = self.g
        p = g.players.get(self.builder_pid) or g.player
        bx, by, cell = g._bo
        t = self.t
        while self.build_i < len(self.build_seq) and self.build_seq[self.build_i][0] <= t:
            st, r, c = self.build_seq[self.build_i]
            self.build_i += 1
            sx = p.rect.centerx + random.uniform(-8, 8)
            sy = p.rect.top - 12
            ex = bx + c * cell + cell / 2
            ey = by + r * cell + cell / 2
            dur = max(0.36, 0.7 - 0.012 * self.build_i * 3)
            self.flying.append([sx, sy, ex, ey, dur, r, c, 0.0])
            g.play("b_throw")
        for f in self.flying[:]:
            f[7] += dt / f[4]
            if f[7] >= 1.0:
                self.flying.remove(f)
                r, c = f[5], f[6]
                self.placed.add((r, c))
                self.landed[(r, c)] = t
                g.play("b_clunk%d" % min(5, 6 - r))
                g.burst(f[2], f[3], [(255, 235, 170), WHITE, SKIN, YELLOW], 9, 230, 0.45, 3, 500)
                if r >= 5:
                    g.burst(f[2], f[3] + 16, [(150, 140, 130)], 4, 90, 0.5, 4, 40)
                g.shake = max(g.shake, 0.08)
                g.shake_amp = 2.5
        if self.build_i >= len(self.build_seq) and not self.flying:
            self.phase = "built"
            self.t = 0.0
            self.firework_t = 0.0
            self.flash = 0.0
            g.play("b_fanfare")
            self.set_tint(0.7, (255, 240, 200))
            g.burst(bx + cell * 2.5, by + 40, [YELLOW, PINK, WHITE, GREEN], 50, 380, 1.0, 6)

    def ph_built(self, dt):
        g = self.g
        bx, by, cell = g._bo
        self.firework_t -= dt
        if self.firework_t <= 0 and self.t < 3.2:
            self.firework_t = random.uniform(0.25, 0.5)
            fx = bx + random.randint(-120, cell * 5 + 120)
            fy = by - random.randint(10, 150)
            cols = random.choice([[YELLOW, ORANGE], [PINK, WHITE], [GREEN, YELLOW], [(120, 200, 255), WHITE]])
            g.burst(fx, fy, cols, 24, 300, 0.9, 5, 320)
            g.play("collect")
        if self.t > 3.8:
            self.phase = "quake"
            self.t = 0.0
            self.q_talked = False
            self.stop_music()
            g.play("b_quake")

    # --- тряска и вопрос героя
    def ph_quake(self, dt):
        g = self.g
        bx, by, cell = g._bo
        amp = 3.0 + 5.0 * min(1.0, self.t / 2.2)
        if self.dlg is not None:
            amp = 4.0
        g.shake = max(g.shake, 0.12)
        g.shake_amp = amp
        if random.random() < dt * 14:
            g.burst(bx + random.randint(-80, cell * 5 + 80), by - 80 + random.randint(0, 60),
                    [(150, 140, 130), (110, 104, 100)], 3, 60, 0.9, 4, 300)
        if self.t >= 1.8 and not self.q_talked:
            self.q_talked = True
            self.say(["Эй... Земля трясётся.",
                      "Это не я! Я просто построил писюна!",
                      "...или я что-то напутал в чертежах?"],
                     on_done=self.start_transform)

    def start_transform(self):
        g = self.g
        bx, by, cell = g._bo
        self.phase = "transform"
        self.t = 0.0
        self.convert = 0.0
        self.roared = False
        self.boss = Boss(self, bx + BOSS_W / 2, by + BOSS_H / 2)
        self.boss.state = "inert"
        g.play("b_robot")
        g.play("b_quake")

    def ph_transform(self, dt):
        g = self.g
        bx, by, cell = g._bo
        t = self.t
        self.convert = clamp((t - 0.4) / 3.0, 0.0, 1.0)
        g.shake = max(g.shake, 0.12)
        g.shake_amp = 5.0 + 3.0 * self.convert
        wy = by + BOSS_H * (1.0 - self.convert)
        if 0.0 < self.convert < 1.0 and random.random() < dt * 40:
            g.burst(bx + random.randint(0, BOSS_W), wy, [(255, 220, 140), WHITE, (160, 200, 255)], 3, 200, 0.4, 3, 200)
        if random.random() < dt * 10:
            g.burst(bx + random.randint(-10, BOSS_W + 10), by + random.randint(0, BOSS_H),
                    [(200, 200, 210), (140, 140, 150)], 2, 70, 0.8, 5, -80)
        if t > 3.6 and not self.roared:
            self.roared = True
            g.play("b_roar")
            g.shake = 1.0
            g.shake_amp = 11.0
            self.set_tint(0.6, (255, 255, 255))
        self.boss.update(dt)
        if t > 4.6:
            self.begin_boss()

    def begin_boss(self):
        g = self.g
        self.phase = "boss"
        self.t = 0.0
        self.convert = 1.0
        self.boss.state = "intro"
        self.boss.t = 0.0
        self.boss_started = True
        self.nplayers = max(1, len(g.players))
        for q in g.players.values():
            q.gren = GRENADE_START
        self.title_t = 0.0
        self.spawn_supplies(first=True)
        self.music("b_music_boss", True)
        if g.role is not None:
            self.intro_toasts = [["ОН ЖИВОЙ?! Гранаты по всему городу — наш единственный шанс!"],
                                 ["Кнопка ГРАНАТА целится сама. Держитесь от него подальше. Босс крепче — вас же больше!"]]
        else:
            self.intro_toasts = [["ОН ЖИВОЙ?! Гранаты по всему городу — мой единственный шанс!"],
                                 ["Кнопка ГРАНАТА целится сама. Главное — держись от него подальше."]]

    # --- босс
    def ph_boss(self, dt):
        g = self.g
        self.boss_time += dt
        b = self.boss
        b.update(dt)
        if b.state == "dying":
            self.phase = "dying"
            self.t = 0.0
            g.play("b_roar")
            self.stop_music()
        if self.title_t >= 0:
            self.title_t += dt
        if self.intro_toasts and self.title_t > 3.2:
            for ln in self.intro_toasts:
                self.say(ln, blocking=False)
            self.intro_toasts = []

    def ph_dying(self, dt):
        b = self.boss
        b.update(dt)
        self.g.shake = max(self.g.shake, 0.1)
        self.g.shake_amp = 3.0 + b.t * 2.0
        if b.t > 2.9:
            self.finish_fight()

    def on_boss_stage(self, thr):
        g = self.g
        msgs = {0.75: "Есть! Он дымится! Бросай ещё!",
                0.5: "Пополам! Он злится — осторожнее!",
                0.25: "Он сдаёт! Добивай!"}
        self.say([msgs[thr]], blocking=False)
        self.spawn_supplies(first=False)
        g.shake = max(g.shake, 0.5)
        g.shake_amp = 7.0

    def finish_fight(self):
        g = self.g
        b = self.boss
        st = self.stats
        st["time"] = self.total
        st["boss_time"] = self.boss_time
        g.score += 2000
        acc = (st["hits"] / st["thrown"]) if st["thrown"] else 0.0
        pts = (1000 - st["hurt"] / max(1, self.nplayers) * 55 - max(0.0, self.boss_time - 100) * 2.5
               + acc * 150 - (st["attempts"] - 1) * 120)
        for (lim, letter, title, col) in RANKS:
            if pts >= lim:
                self.res = dict(letter=letter, title=title, col=col, pts=int(pts), acc=acc)
                break
        r = random.Random(g.score + int(self.total))
        self.res["sub"] = r.choice(JOKES_SUB)
        self.res["news"] = r.choice(JOKES_NEWS)
        # взрыв
        bx, by = b.x, b.y
        g.play("b_big")
        g.burst(bx, by, [WHITE, YELLOW, ORANGE, (255, 120, 60)], 90, 620, 1.5, 8, 200)
        g.burst(bx, by, [(190, 196, 210), PINK, SKIN, (110, 118, 140)], 70, 520, 1.8, 6, 700)
        self.add_boom(bx, by, 260, 1.2)
        self.boss = None
        self.res_t = 0.0
        self.flash = 1.0
        self.phase = "flash"
        g.safe = True
        g.set_state("bwin")

    def ph_flash(self, dt):
        pass

    # --- прогресс экрана итогов
    def update_result(self, dt):
        g = self.g
        self.res_t += dt
        r = self.res_t
        if r < 0.12:
            self.flash = r / 0.12
        elif r < 1.4:
            self.flash = 1.0
        else:
            self.flash = max(0.0, 1.0 - (r - 1.4) / 4.4)
        if r > 3.0 and not self._fan:
            self._fan = True
            g.play("b_fanfare")
        self.update_fx(dt)

    # ------------------------------------------------------------ снаряды и эффекты
    def update_fx(self, dt):
        for gr in self.grenades:
            gr.update(dt, self)
        self.grenades = [x for x in self.grenades if not x.dead]
        for m in self.missiles:
            m.update(dt, self)
        self.missiles = [x for x in self.missiles if not x.dead]
        for sh in self.shocks:
            sh.update(dt, self)
        self.shocks = [x for x in self.shocks if not x.dead]
        for b in self.booms:
            b.t += dt
        self.booms = [b for b in self.booms if b.t < b.dur]

    def explode(self, x, y, radius, from_player):
        g = self.g
        g.play("b_pop" if radius < 70 else "b_boom")
        g.shake = max(g.shake, 0.18)
        g.shake_amp = max(g.shake_amp, 4.0 if radius < 70 else 6.0)
        g.burst(x, y, [WHITE, YELLOW, ORANGE, (255, 120, 60)], 22, 340, 0.7, 6, 300)
        g.burst(x, y, [(90, 90, 100), (60, 60, 70)], 8, 120, 1.0, 7, -60)
        self.add_boom(x, y, radius * 1.1, 0.5)
        if from_player:
            b = self.boss
            if b is None or not b.alive_for_hits():
                return
            direct = False
            near = False
            for pr in b.parts():
                if pr.inflate(16, 16).collidepoint(x, y):
                    direct = True
                    break
                cx = clamp(x, pr.left, pr.right)
                cy = clamp(y, pr.top, pr.bottom)
                if (cx - x) ** 2 + (cy - y) ** 2 <= radius * radius:
                    near = True
            dmg = 4 if direct else (2 if near else 0)
            if dmg:
                d = b.hurt(dmg)
                if d:
                    self.stats["hits"] += 1
                    g.score += 150
                    g.float_text(x, y - 30, "-%d" % d, (255, 220, 100))
        else:
            hit = False
            if g.state == "play":
                for q in g.alive_players():
                    cx = clamp(x, q.rect.left, q.rect.right)
                    cy = clamp(y, q.rect.top, q.rect.bottom)
                    if (cx - x) ** 2 + (cy - y) ** 2 <= radius * radius:
                        g.damage_player(x, q)
                        hit = True
                        if g.state != "play":
                            break
            if not hit:
                self.stats["dodged"] += 1

    def impact(self, x, y, r, dur):
        g = self.g
        g.burst(x, y, [(200, 190, 170), (150, 140, 130), YELLOW], 14, 260, 0.6, 5, 500)
        self.add_boom(x, y, r * 1.2, 0.45, "ring")
        if g.state == "play":
            for q in g.alive_players():
                if q.rect.bottom >= y - 30 and abs(q.rect.centerx - x) < r:
                    g.damage_player(x, q)

    def slam_impact(self, x):
        g = self.g
        g.play("b_slam")
        g.shake = 0.7
        g.shake_amp = 10.0
        g.burst(x, g.ground_y - 6, [(200, 190, 170), (150, 140, 130), YELLOW, ORANGE], 40, 420, 0.9, 6, 600)
        self.add_boom(x, g.ground_y - 8, 230, 0.6, "ring")
        for d in (-1, 1):
            self.shocks.append(Shockwave(x + d * 70, d, g.ground_y))
        if g.state == "play":
            for q in g.alive_players():
                if q.rect.bottom >= g.ground_y - 30 and abs(q.rect.centerx - x) < 120:
                    g.damage_player(x, q)

    def small_boom(self, x, y):
        g = self.g
        if random.random() < 0.6:
            g.play("b_pop")
        g.burst(x, y, [WHITE, YELLOW, ORANGE], 10, 260, 0.6, 5, 200)
        self.add_boom(x, y, random.randint(40, 70), 0.4)

    # ------------------------------------------------------------ гранаты игрока
    def solve_throw(self, ox, oy):
        g = self.g
        b = self.boss
        G = Grenade.G
        d = math.hypot(b.x - ox, b.y - oy)
        if d > 1150:
            return None
        T0 = clamp(d / 720.0, 0.4, 1.2)
        best = None
        for k in (1.0, 1.35, 0.8, 1.7):
            T = T0 * k
            tx = b.x + b.vx * T
            ty = b.y + b.vy * T - 10
            vx = (tx - ox) / T
            vy = (ty - oy - 0.5 * G * T * T) / T
            if vx * vx + vy * vy > 1500.0 ** 2:
                continue
            if best is None:
                best = (vx, vy)
            ok = True
            r = pygame.Rect(0, 0, 12, 12)
            n = int(T / 0.05)
            for i in range(2, n):
                tt = i * 0.05
                r.center = (int(ox + vx * tt), int(oy + vy * tt + 0.5 * G * tt * tt))
                if g.solid_hit(r):
                    ok = False
                    break
            if ok:
                return (vx, vy)
        return best

    def throw(self, p=None):
        g = self.g
        p = p or g.player
        b = self.boss
        if self.phase != "boss" or b is None or b.state in ("dying", "gone", "inert") or g.state != "play" or p.dead:
            return
        if p.throw_cd > 0:
            return
        if p.gren <= 0:
            g.float_text(p.rect.centerx, p.rect.top - 14, "НЕТ ГРАНАТ!", RED)
            p.throw_cd = 0.4
            return
        ox, oy = p.rect.centerx, p.rect.top + 6
        sol = self.solve_throw(ox, oy)
        if sol is None:
            g.float_text(p.rect.centerx, p.rect.top - 14, "СЛИШКОМ ДАЛЕКО!", ORANGE)
            p.throw_cd = 0.3
            return
        p.gren -= 1
        self.stats["thrown"] += 1
        p.throw_cd = 0.8
        p.facing = 1 if sol[0] >= 0 else -1
        self.grenades.append(Grenade(ox, oy, sol[0], sol[1], p.pid))
        g.play("b_throw")

    # ------------------------------------------------------------ припасы по городу
    def _stand_list(self):
        if self.stands is None:
            try:
                import levelgen
                self.stands = levelgen.reachable_stands(self.g.lvl)
            except Exception:
                self.stands = []
        return self.stands

    def spawn_supplies(self, first):
        """Гранаты и аптечки по всему городу. Взятые появляются снова через некоторое время."""
        g = self.g
        L = g.lvl
        rnd = random.Random(L.seed + (1 if first else len(self.supply) + 7))
        stands = self._stand_list()
        spikes = set(L.spikes)
        ok = [(c, r) for (c, r) in stands if 3 <= c <= L.zone_tx + 28 and (c, r) not in spikes
              and (c - 1, r) not in spikes and (c + 1, r) not in spikes]
        taken_cols = [int(pk.base.x // TILE) for pk in self.supply]
        n = max(1, len(g.players))
        if first:
            want_g, want_m, gap = 26 + 9 * (n - 1), 9 + 3 * (n - 1), max(5, 8 - (n - 1))
        else:
            want_g, want_m, gap = 4 + (n - 1) * 2, 2 + (n - 1), max(6, 10 - (n - 1))
        p = g.focus_player()
        pc = p.rect.centerx // TILE
        rnd.shuffle(ok)
        made_g = made_m = 0
        for (c, r) in ok:
            if made_g >= want_g and made_m >= want_m:
                break
            if any(abs(c - tc) < gap for tc in taken_cols):
                continue
            if not first and abs(c - pc) > 40:
                continue
            kind = "grenade" if (made_g < want_g and (made_m >= want_m or made_g <= made_m * 3)) else "medkit"
            if kind == "medkit" and made_m >= want_m:
                continue
            pk = g.make_pickup(kind, c, r - 0.8)
            self.supply.append(pk)
            g.pickups.append(pk)
            taken_cols.append(c)
            if kind == "grenade":
                made_g += 1
            else:
                made_m += 1
            if abs(pk.base.x - p.rect.centerx) < g.W:
                g.burst(pk.base.x, pk.base.y, [WHITE, YELLOW, (170, 220, 130)], 10, 160, 0.6, 4, -40)
        g.sup_dirty = True
        # у стройплощадки — стартовый запас
        bx = g._bo[0]
        if first:
            for k, off in enumerate((-260, -120, 330, 470)):
                c = int((bx + off) // TILE)
                pk = g.make_pickup("grenade" if k % 2 == 0 else "medkit", c, g.ground_y / TILE - 0.8)
                self.supply.append(pk)
                g.pickups.append(pk)

    def update_supply(self, dt):
        if not self.supply or self.phase not in ("boss", "dying"):
            return
        g = self.g
        xs = [q.rect.centerx for q in g.alive_players()] or [g.player.rect.centerx]
        for pk in self.supply:
            if pk.taken:
                if pk.taken_at is None:
                    pk.taken_at = self.total
                elif (self.total - pk.taken_at > (26.0 if pk.kind == "grenade" else 40.0)
                      and all(abs(pk.base.x - x) > 260 for x in xs)):
                    pk.taken = False
                    pk.taken_at = None
                    g.pk_dirty = True
                    g.burst(pk.base.x, pk.base.y, [WHITE, YELLOW], 8, 140, 0.5, 4, -40)

    # ------------------------------------------------------------ повтор боя после поражения
    def can_retry(self):
        return self.boss_started

    def retry_boss(self):
        g = self.g
        bx, by, cell = g._bo
        self.stats["attempts"] += 1
        self.grenades, self.missiles, self.shocks, self.booms = [], [], [], []
        g.particles = []
        g.floaters = []
        g.poops = []
        self.nplayers = max(1, len(g.players))
        for i, q in enumerate(g.players.values()):
            q.hp = 5
            q.dead = False
            q.gren = GRENADE_START
            q.throw_cd = 0.0
            x = int(bx - 260) + 30 * (i % 4) - q.rect.w // 2
            g.teleport(q, x, int(g.ground_y) - q.rect.h, 2.0, fx=False)
        p = g.player
        g.camera_x = clamp(p.rect.centerx - g.W // 2, -CAM_PAD, g.world_w - g.W + CAM_PAD)
        g.camera_y = float(g.cam_max_y)
        self.boss = Boss(self, bx + BOSS_W / 2, by + BOSS_H / 2)
        self.boss.state = "intro"
        self.convert = 1.0
        self.phase = "boss"
        self.t = 0.0
        self.title_t = -1.0
        for pk in self.supply:
            pk.taken = False
            pk.taken_at = None
        g.pk_dirty = True
        self.dlg = None
        self.toast, self.toast_q = None, []
        g.safe = False
        g.flash_msg("", 0.0)
        self.stop_music(net=False)
        self.music("b_music_boss", True, net=False)
        self.say(["Ещё раз. Он большой, но не бессмертный."], blocking=False)

    def net_retry(self):
        """Клиент: хост начал бой заново."""
        g = self.g
        self.stats["attempts"] += 1
        self.grenades, self.missiles, self.shocks, self.booms = [], [], [], []
        g.particles = []
        g.floaters = []
        g.poops = []
        self.boss = None
        self.convert = 1.0
        self.phase = "boss"
        self.t = 0.0
        self.title_t = -1.0
        self.dlg = None
        self.toast, self.toast_q = None, []
        g.flash_msg("", 0.0)
        self.stop_music(net=False)
        self.music("b_music_boss", True, net=False)
        p = g.player
        g.camera_x = clamp(p.rect.centerx - g.W // 2, -CAM_PAD, g.world_w - g.W + CAM_PAD)
        g.camera_y = float(g.cam_max_y)

    # ------------------------------------------------------------ ввод
    def touch(self, x, y):
        """True, если касание поглощено (диалог / кнопка ПОСТРОИТЬ)."""
        g = self.g
        if self.dlg is not None and self.dlg.blocking:
            if g.role == "client":
                d = self.dlg
                if not d.complete():
                    d.shown = len(d.text)
                g.net_to_host({"t": "tap"})
            else:
                self.tap_dialog()
            return True
        if self.can_build():
            lx, ly = g.to_logical(x, y)
            if self.btn.inflate(24, 24).collidepoint(lx, ly):
                if g.role == "client":
                    g.net_to_host({"t": "build"})
                else:
                    g.bc = g.role == "host"
                    try:
                        self.start_build()
                    finally:
                        g.bc = False
                return True
        return False

    def camera_target(self, p):
        g = self.g
        W = g.W
        ph = self.phase
        lo, hi = -CAM_PAD, g.world_w - W + CAM_PAD
        ty = clamp(p.rect.centery - 330, 0, g.cam_max_y)
        if ph in ("build", "built", "quake", "transform"):
            bx, by, cell = g._bo
            return clamp(bx + BOSS_W / 2 - W / 2 + 50, lo, hi), clamp(g.ground_y - 400, 0, g.cam_max_y), 2.6
        if ph in ("boss", "dying") and self.boss is not None:
            b = self.boss
            bias = clamp((b.x - p.rect.centerx) * 0.3, -W * 0.22, W * 0.22)
            if ph == "dying":
                return clamp(b.x - W / 2, lo, hi), ty, 3.0
            return clamp(p.rect.centerx - W / 2 + bias, lo, hi), ty, 7.0
        return clamp(p.rect.centerx - W // 2, lo, hi), ty, 7.0

    # ------------------------------------------------------------ сеть (кооператив)
    def net_state(self):
        """Хост: всё, что нужно клиентам, чтобы нарисовать бой. Кладётся в каждый снимок мира."""
        g = self.g
        s = {"ph": self.phase, "t": round(self.t, 2), "tot": round(self.total, 1), "bt": round(self.boss_time, 1),
             "cv": round(self.convert, 3), "ti": round(self.title_t, 2), "bs": 1 if self.boss_started else 0}
        if self.dlg is not None:
            d = self.dlg
            s["dl"] = [d.uid, d.i, int(d.shown)]
        if self.toast is not None:
            d = self.toast
            s["tt"] = [d.uid, d.i, int(d.shown)]
        if self.phase == "build":
            s["pc"] = sorted(r * 10 + c for (r, c) in self.placed)
            s["fy"] = [[int(f[0]), int(f[1]), int(f[2]), int(f[3]), round(f[4], 2), f[5], f[6], round(f[7], 2)]
                       for f in self.flying]
        b = self.boss
        if b is not None:
            s["bo"] = {"x": round(b.x, 1), "y": round(b.y, 1), "vx": int(b.vx), "vy": int(b.vy), "hp": b.hp,
                       "mx": b.max_hp, "st": b.state, "t": round(b.t, 2), "ey": round(b.eye, 2),
                       "hf": round(b.hit_flash, 2), "ar": [[round(a.tip[0]), round(a.tip[1]), round(a.elbow[0]),
                                                           round(a.elbow[1]), round(a.open, 2), 1 if a.danger else 0]
                                                          for a in b.arms],
                       "bm": [int(v) for v in b.beam] if b.beam else None, "bh": 1 if b.beam_hot else 0,
                       "lk": [int(b.lock[0]), int(b.lock[1])], "sb": b.sub, "dr": b.dir, "an": round(b.anim, 2)}
        if self.grenades:
            s["gr"] = [[int(x.x), int(x.y), int(x.vx), int(x.vy), round(x.t, 2)] for x in self.grenades]
        if self.missiles:
            s["mi"] = [[int(x.x), int(x.y), int(x.vx), int(x.vy), round(x.ang, 2)] for x in self.missiles]
        if self.shocks:
            s["sk"] = [[int(x.x), x.dir, round(x.t, 2)] for x in self.shocks]
        return s

    def net_say(self, m):
        """Клиент: пришла новая реплика (реплики идут по надёжному каналу, не в снимках)."""
        d = Dialogue(m.get("lines", []), None, bool(m.get("blk", 1)))
        d.uid = int(m.get("id", 0))
        self.dmap[d.uid] = d
        for k in [k for k in self.dmap if k < d.uid - 10]:
            del self.dmap[k]

    def _sync_dlg(self, cur, info):
        if not info:
            return None
        d = self.dmap.get(info[0])
        if d is None:
            return cur
        if d.i != info[1]:
            d.i = info[1]
            d.shown = float(info[2])
            d.cache = None
            d.last_blip = int(d.shown)
        else:
            d.shown = max(d.shown, float(info[2]))
        if d.i >= len(d.lines):
            return None
        return d

    def net_apply(self, s):
        """Клиент: применить состояние боя из снимка."""
        g = self.g
        self.phase = s.get("ph", self.phase)
        self.t = s.get("t", self.t)
        self.total = s.get("tot", self.total)
        self.boss_time = s.get("bt", self.boss_time)
        self.convert = s.get("cv", self.convert)
        self.title_t = s.get("ti", self.title_t)
        self.boss_started = bool(s.get("bs", 0))
        self.sleeping = False
        self.dlg = self._sync_dlg(self.dlg, s.get("dl"))
        self.toast = self._sync_dlg(self.toast, s.get("tt"))
        pc = s.get("pc")
        if pc is not None:
            new = {(v // 10, v % 10) for v in pc}
            for cell in new - self.placed:
                self.landed[cell] = self.t
            self.placed = new
        fy = s.get("fy")
        self.flying = [list(map(float, f)) for f in fy] if fy else []
        for f in self.flying:
            f[5], f[6] = int(f[5]), int(f[6])
        bo = s.get("bo")
        if bo is None:
            self.boss = None
        else:
            b = self.boss
            if b is None:
                b = Boss(self, bo["x"], bo["y"])
                self.boss = b
                b.tx, b.ty = bo["x"], bo["y"]
            b.tx, b.ty = bo["x"], bo["y"]
            if abs(b.x - b.tx) > 400 or abs(b.y - b.ty) > 400:
                b.x, b.y = b.tx, b.ty
            b.vx, b.vy = bo["vx"], bo["vy"]
            b.hp, b.max_hp = bo["hp"], bo["mx"]
            b.n = max(1, b.max_hp // 120)
            b.state, b.t, b.eye, b.hit_flash = bo["st"], bo["t"], bo["ey"], bo["hf"]
            b.beam = tuple(bo["bm"]) if bo["bm"] else None
            b.beam_hot = bool(bo["bh"])
            b.lock = list(bo["lk"])
            b.sub, b.dir, b.anim = bo["sb"], bo["dr"], bo["an"]
            for a, e in zip(b.arms, bo["ar"]):
                a.ttip = (e[0], e[1])
                a.telb = (e[2], e[3])
                if not hasattr(a, "seen"):
                    a.seen = True
                    a.tip = [float(e[0]), float(e[1])]
                    a.elbow = [float(e[2]), float(e[3])]
                a.open = e[4]
                a.danger = bool(e[5])
        gr = s.get("gr")
        self.grenades = []
        for e in gr or ():
            o = Grenade(e[0], e[1], e[2], e[3])
            o.t = e[4]
            self.grenades.append(o)
        mi = s.get("mi")
        self.missiles = []
        for e in mi or ():
            o = Missile(e[0], e[1], 1)
            o.x, o.y, o.vx, o.vy, o.ang = e[0], e[1], e[2], e[3], e[4]
            o.t = 1.0
            self.missiles.append(o)
        sk = s.get("sk")
        self.shocks = []
        for e in sk or ():
            o = Shockwave(e[0], e[1], g.ground_y)
            o.t = e[2]
            self.shocks.append(o)

    def net_supply(self, ps):
        """Клиент: список гранат/аптечек на карте (одинаковый порядок с хостом; координаты в пикселях)."""
        g = self.g
        cur = [(pk.kind, round(pk.base.x, 1), round(pk.base.y, 1)) for pk in self.supply]
        want = [(e[0], float(e[1]), float(e[2])) for e in ps]
        if cur == want:
            return
        if self.supply:
            ids = {id(pk) for pk in self.supply}
            g.pickups = [pk for pk in g.pickups if id(pk) not in ids]
        self.supply = []
        for kind, x, y in want:
            pk = g.make_pickup(kind, 0, 0)
            pk.base.update(x, y)
            pk.rect.center = (int(x), int(y))
            self.supply.append(pk)
            g.pickups.append(pk)

    def net_result_payload(self):
        m = {"stats": dict(self.stats), "bst": 1 if self.boss_started else 0}
        if self.res is not None:
            r = dict(self.res)
            r["col"] = list(r["col"])
            m["res"] = r
        return m

    def net_result(self, m):
        """Клиент: пришли итоги боя / поражения."""
        st = m.get("stats")
        if st:
            self.stats.update(st)
        self.boss_started = bool(m.get("bst", self.boss_started))
        r = m.get("res")
        if r:
            r = dict(r)
            r["col"] = tuple(r["col"])
            self.res = r
            self.boss = None
            self.res_t = 0.0
            self.flash = 1.0
            self.phase = "flash"
            self._fan = False
            self._slam_snd = False
            self.grenades, self.missiles, self.shocks = [], [], []
            self.stop_music(net=False)

    def _type_dialog(self, d, dt):
        if d is None or d.done or d.i >= len(d.lines):
            return
        if not d.complete():
            d.shown = min(len(d.text), d.shown + d.SPEED * dt)
            k = int(d.shown)
            if k != d.last_blip:
                d.last_blip = k
                if d.blocking and k % 2 == 0 and k > 0 and d.text[k - 1] not in " .,!?…":
                    self.blip()

    def client_update(self, dt):
        """Клиент: только то, что оживляет картинку между снимками хоста."""
        g = self.g
        self.total += dt
        self.t += dt
        self.jobs.pump(0.004 if self.phase in ("intro", "explore") else 0.0016)
        if self.want_music is not None:
            nm, lp = self.want_music
            if nm in g.sounds:
                self.music(nm, lp, net=False)
        self.tint = max(0.0, self.tint - dt * 1.4)
        self._type_dialog(self.dlg, dt)
        self._type_dialog(self.toast, dt)
        k = min(1.0, dt * 26.0)
        b = self.boss
        if b is not None:
            b.anim += dt
            b.hit_flash = max(0.0, b.hit_flash - dt)
            b.x += (b.tx - b.x) * k
            b.y += (b.ty - b.y) * k
            for a in b.arms:
                tt = getattr(a, "ttip", None)
                if tt is not None:
                    a.tip[0] += (tt[0] - a.tip[0]) * k
                    a.tip[1] += (tt[1] - a.tip[1]) * k
                    a.elbow[0] += (a.telb[0] - a.elbow[0]) * k
                    a.elbow[1] += (a.telb[1] - a.elbow[1]) * k
        for gr in self.grenades:
            gr.t += dt
            gr.spin += dt * 9
            gr.vy += gr.G * dt
            gr.x += gr.vx * dt
            gr.y += gr.vy * dt
        for m in self.missiles:
            m.x += m.vx * dt
            m.y += m.vy * dt
        for sh in self.shocks:
            sh.t += dt
            sh.x += sh.dir * (330 + 40 * sh.t) * dt
        for f in self.flying:
            f[7] = min(1.0, f[7] + dt / max(0.05, f[4]))
        for bm in self.booms:
            bm.t += dt
        self.booms = [x for x in self.booms if x.t < x.dur]

    # ------------------------------------------------------------ рисование
    def ensure_assets(self):
        g = self.g
        if self.A is None or self.A["W"] != g.W:
            self.A = build_night_assets(g)
            self.btn.center = (g.W // 2, 330)
            self._ov = None
            self._portrait = None

    def fill_alpha(self, color, a):
        """Полноэкранная заливка с прозрачностью (один переиспользуемый буфер)."""
        if a <= 0.004:
            return
        s = self.g.screen
        if a >= 0.996:
            s.fill(color)
            return
        ov = getattr(self, "_ov", None)
        if ov is None or ov.get_size() != s.get_size():
            ov = pygame.Surface(s.get_size()).convert()
            self._ov = ov
        ov.fill(color)
        ov.set_alpha(int(255 * a))
        s.blit(ov, (0, 0))

    def draw_bg(self, cam, cy):
        g = self.g
        self.ensure_assets()
        A = self.A
        s = g.screen
        W = g.W
        gdy = 0 if cy is None else g.ground_y - 468 - cy
        s.blit(A["sky"], (0, 0))
        st = A["stars"][int(g.time_global * 1.4) % 2]
        s.blit(st, (-(int(cam * 0.03) % 80), int(gdy * 0.15)))
        mc = A["moon_c"]
        s.blit(A["moon"], (W - 170 - int(cam * 0.03) % 40 - mc[0], 90 - mc[1] + int(gdy * 0.1)))
        if not g.lite:
            P = A["cloud_period"]
            sx = (-int(cam * 0.30)) % P - 130
            cdy = int(gdy * 0.25)
            s.blit(A["cloud"], (sx, cdy))
            s.blit(A["cloud"], (sx - P, cdy))
            off = int(cam * 0.45)
            s.blit(A["bld"], (-(off % 300) - 60, g.bld_y0 + int(gdy * 0.7)))
            s.blit(A["crane"], (-(off % 620) - 70, 140 + int(gdy * 0.6)))
        off2 = int(cam * 0.6)
        s.blit(A["hill"], (-(off2 % 260) - 80, SCREEN_H - 120 + int(gdy * 0.85)))

    def cell_surf(self, r):
        k = 0 if r <= 1 else 1
        s = self._cells.get(k)
        if s is None:
            cell = BOSS_CELL
            s = pygame.Surface((cell, cell)).convert()
            base = PINK if k == 0 else SKIN
            dark = (219, 76, 130) if k == 0 else SKIN_DK
            s.fill(base)
            pygame.draw.rect(s, dark, (0, cell - 6, cell, 6))
            pygame.draw.rect(s, (255, 235, 205), (0, 0, cell, 5))
            pygame.draw.rect(s, BLACK, (0, 0, cell, cell), 2)
            pygame.draw.rect(s, WHITE, (7, 7, 5, 5))
            self._cells[k] = s
        return s

    def draw_zone(self, cam, cy):
        g = self.g
        s = g.screen
        zx = g.zone_x0 - cam
        if zx > g.W or zx + g.zone_w < 0:
            return
        bx, by, cell = g._bo
        s.blit(g.zone_surf, (zx, g.zone_y0 - cy))
        sign_x = g.zone_x - cam + 66
        gyc = g.ground_y - cy
        g.text(s, "СТРОЙКА ПИСЮНА", 17, sign_x + 119, gyc - 300, YELLOW, center=True, bold=True)
        ph = self.phase
        if ph in ("intro", "explore"):
            n = g.bricks_collected
            g.text(s, "БЛОКОВ: %d/%d" % (n, CELLS), 15, sign_x + 119, gyc - 278,
                   GREEN if n >= CELLS else WHITE, center=True)
        elif ph == "build":
            g.text(s, "ГОТОВО: %d%%" % int(len(self.placed) / CELLS * 100), 15, sign_x + 119, gyc - 278, YELLOW, center=True)
        elif ph in ("built", "quake", "transform"):
            g.text(s, "ГОТОВО: 100%", 15, sign_x + 119, gyc - 278, GREEN, center=True)
        if ph in ("intro", "explore", "build"):
            tg = g.time_global
            gh = getattr(self, "_ghost", None)
            if gh is None:
                gh = pygame.Surface((cell - 4, cell - 4)).convert()
                gh.fill((30, 36, 58))
                self._ghost = gh
            for r, row in enumerate(BUILD_SHAPE):
                for c, ch in enumerate(row):
                    if ch != "X":
                        continue
                    x = bx + c * cell - cam
                    y = by + r * cell - cy
                    if (r, c) in self.placed:
                        s.blit(self.cell_surf(r), (x, y))
                        if self.t - self.landed.get((r, c), -9) < 0.09:
                            pygame.draw.rect(s, WHITE, (x, y, cell, cell))
                    else:
                        gh.set_alpha(90 + int(math.sin(tg * 3 + r + c) * 25))
                        s.blit(gh, (x + 2, y + 2))
                        pygame.draw.rect(s, (60, 72, 110), (x + 2, y + 2, cell - 4, cell - 4), 1)
        elif ph in ("built", "quake"):
            jx = jy = 0
            if ph == "quake":
                jx, jy = random.randint(-2, 2), random.randint(-1, 1)
            s.blit(boss_sprites()["mono"], (bx - cam + jx, by - cy + jy))
            if ph == "quake" and int(self.t * 12) % 2 == 0:
                pygame.draw.rect(s, (255, 90, 70), (bx - cam + cell, by - cy + cell + 12, cell * 3, 4))

    def draw_sleeper(self, cam, cy):
        g = self.g
        s = g.screen
        x = 2 * TILE + TILE // 2 - cam
        y = g.ground_y - cy
        if x < -120 or x > g.W + 120:
            return
        if self._sleeper is None:
            spr = g.player_spr(1, 0, 0)
            t = pygame.Surface((36, 64), pygame.SRCALPHA)
            t.blit(spr, (0, 0))
            self._sleeper = pygame.transform.rotate(t, 90).convert_alpha()
        s.blit(self._sleeper, (x - 40, y - 62))
        pygame.draw.rect(s, (62, 84, 150), (x - 8, y - 50, 56, 24), border_radius=5)
        pygame.draw.rect(s, (92, 116, 190), (x - 8, y - 50, 56, 7), border_radius=4)
        pygame.draw.rect(s, BLACK, (x - 8, y - 50, 56, 24), 2, border_radius=5)
        for k in range(3):
            u = (self.t * 0.7 + k / 3.0) % 1.0
            g.text(s, "Z" if k == 0 else "z", 14 + k * 5, x - 28 + u * 34, y - 86 - u * 52, (200, 215, 255), bold=True)

    def draw_hero(self, cam, cy):
        g = self.g
        if self.sleeping:
            self.draw_sleeper(cam, cy)
            return
        if g.role is None and self.phase in ("intro", "explore") and g.player.rect.centerx < 700:
            x = 2 * TILE + TILE // 2 - cam
            y = g.ground_y - cy
            pygame.draw.rect(g.screen, (62, 84, 150), (x - 8, y - 33, 52, 10), border_radius=4)
            pygame.draw.rect(g.screen, BLACK, (x - 8, y - 33, 52, 10), 2, border_radius=4)
        g.draw_players(cam, cy)
        if self.excl > 0:
            r = g.player.rect
            g.text(g.screen, "!", 44, r.centerx - cam, r.top - 34 - cy, YELLOW, center=True, bold=True)

    def draw_boss(self, cam, cy):
        b = self.boss
        if b is None:
            return
        b.draw(self.g.screen, cam, cy, self.convert if self.phase == "transform" else 1.0)

    def draw_telegraph(self, cam, cy):
        b = self.boss
        if b is None or self.phase != "boss":
            return
        g = self.g
        s = g.screen
        st = b.state
        gy = int(g.ground_y - cy)
        pulse = 0.5 + 0.5 * math.sin(g.time_global * 20)
        if st == "smash" and b.t < 1.0 / b.rate:
            x = int(b.lock[0] - cam)
            w = 80 + int(8 * pulse)
            col = (255, 70, 60)
            pygame.draw.ellipse(s, col, (x - w, int(b.lock[1] - cy) - 8, 2 * w, 16), 3)
            pygame.draw.line(s, col, (x - 14, int(b.lock[1] - cy) - 4), (x + 14, int(b.lock[1] - cy) + 4), 3)
            pygame.draw.line(s, col, (x - 14, int(b.lock[1] - cy) + 4), (x + 14, int(b.lock[1] - cy) - 4), 3)
        elif st == "rake" and b.t < 0.95 / b.rate + 0.9:
            x0 = int(b.x - cam)
            for k in range(0, 18):
                xx = x0 + b.dir * (180 + k * 36)
                pygame.draw.rect(s, (255, 90, 70) if (k + int(g.time_global * 14)) % 2 else (255, 190, 90),
                                 (xx - 12, gy - 6, 24, 6))
        elif st == "slam" and b.sub == 0:
            x = int(b.lock[0] - cam)
            for k in range(7):
                pygame.draw.rect(s, (255, 70, 60), (x - 3, gy - 26 - k * 40, 6, 20))
            pygame.draw.ellipse(s, (255, 70, 60), (x - 110, gy - 10, 220, 20), 3)
        elif st == "laser" and b.beam and not b.beam_hot:
            x0, y0, x1, y1 = b.beam
            n = 40
            for k in range(0, n, 2):
                a = (x0 + (x1 - x0) * k / n - cam, y0 + (y1 - y0) * k / n - cy)
                c = (x0 + (x1 - x0) * (k + 1) / n - cam, y0 + (y1 - y0) * (k + 1) / n - cy)
                pygame.draw.line(s, (255, 60, 60), a, c, 2)

    def draw_fx(self, cam, cy):
        g = self.g
        s = g.screen
        b = self.boss
        if b is not None and b.beam and b.beam_hot:
            x0, y0, x1, y1 = b.beam
            a = (x0 - cam, y0 - cy)
            c = (x1 - cam, y1 - cy)
            pygame.draw.line(s, (255, 60, 50), a, c, 26)
            pygame.draw.line(s, (255, 170, 120), a, c, 14)
            pygame.draw.line(s, (255, 255, 240), a, c, 6)
            pygame.draw.circle(s, (255, 230, 200), (int(c[0]), int(c[1])), 14 + int(4 * math.sin(g.time_global * 40)))
        for sh in self.shocks:
            x = int(sh.x - cam)
            gyc = int(g.ground_y - cy)
            if -40 < x < g.W + 40:
                pts = [(x - 24, gyc), (x - 10 + sh.dir * 8, gyc - 30), (x + sh.dir * 14, gyc - 56), (x + 12 + sh.dir * 8, gyc - 28), (x + 24, gyc)]
                pygame.draw.polygon(s, (255, 90, 60), pts)
                pygame.draw.polygon(s, (255, 220, 120), [(x - 12, gyc), (x + sh.dir * 8, gyc - 36), (x + 12, gyc)])
                pygame.draw.polygon(s, BLACK, pts, 2)
        for m in self.missiles:
            x, y = m.x - cam, m.y - cy
            if x < -40 or x > g.W + 40:
                continue
            ca, sa = math.cos(m.ang), math.sin(m.ang)

            def P(dx, dy, x=x, y=y, ca=ca, sa=sa):
                return (x + dx * ca - dy * sa, y + dx * sa + dy * ca)
            pygame.draw.polygon(s, (255, 150, 60), [P(-12, -4), P(-28 - random.random() * 8, 0), P(-12, 4)])
            pygame.draw.polygon(s, (226, 230, 240), [P(-14, -5), P(8, -5), P(16, 0), P(8, 5), P(-14, 5)])
            pygame.draw.polygon(s, (230, 60, 60), [P(8, -5), P(16, 0), P(8, 5)])
            pygame.draw.polygon(s, (120, 126, 146), [P(-14, -5), P(-20, -10), P(-8, -5)])
            pygame.draw.polygon(s, (120, 126, 146), [P(-14, 5), P(-20, 10), P(-8, 5)])
            pygame.draw.polygon(s, BLACK, [P(-14, -5), P(8, -5), P(16, 0), P(8, 5), P(-14, 5)], 1)
        for gr in self.grenades:
            x, y = int(gr.x - cam), int(gr.y - cy)
            pygame.draw.circle(s, BLACK, (x, y), 9)
            pygame.draw.circle(s, (90, 118, 66), (x, y), 7)
            pygame.draw.circle(s, (150, 180, 110), (x - 2, y - 3), 2)
            fx = x + int(math.cos(gr.spin) * 8)
            fy = y - 8 + int(math.sin(gr.spin) * 2)
            if int(gr.t * 14) % 2 == 0:
                pygame.draw.circle(s, YELLOW, (fx, fy), 3)
        for bm in self.booms:
            u = bm.t / bm.dur
            x, y = int(bm.x - cam), int(bm.y - cy)
            if bm.kind == "ring":
                rw = int(bm.r * (0.2 + 0.9 * u))
                rh = max(4, int(rw * 0.22))
                pygame.draw.ellipse(s, (255, 230, 170) if u < 0.5 else (170, 150, 130),
                                    (x - rw, y - rh, 2 * rw, 2 * rh), max(2, int(5 * (1 - u))))
                continue
            rr = int(bm.r * (0.3 + 0.8 * (u ** 0.55)))
            if u < 0.22:
                pygame.draw.circle(s, (255, 250, 220), (x, y), rr)
            elif u < 0.6:
                pygame.draw.circle(s, (255, 150, 50), (x, y), rr)
                pygame.draw.circle(s, (255, 220, 110), (x, y), int(rr * 0.6 * (1 - u)) + 2)
            else:
                pygame.draw.circle(s, (90, 76, 76), (x, y), rr, max(2, int(6 * (1 - u))))
            if u < 0.5:
                pygame.draw.circle(s, (255, 255, 255), (x, y), int(rr * 1.2), 2)

    def draw_lights(self, cam, cy):
        g = self.g
        s = g.screen
        if not self.sleeping:
            for q in g.players.values():
                if not q.dead:
                    add_glow(s, q.rect.centerx - cam, q.rect.centery - cy, 150, (78, 70, 52))
        else:
            add_glow(s, 90 - cam + 0, g.ground_y - 30 - cy, 100, (50, 44, 30), 3)
        if g.lite:
            return
        b = self.boss
        if b is not None and self.phase != "transform":
            bxx, byy = b.x - cam, b.y - cy
            add_glow(s, bxx, byy - 40, 210, (86, 34, 20))
            ex, ey = b.eye_origin()
            add_glow(s, ex - cam, ey - cy, 90, (140, 30, 24), 4 if b.eye > 0.5 else 2)
            for a in b.arms:
                if a.danger:
                    add_glow(s, a.tip[0] - cam, a.tip[1] - cy, 70, (120, 40, 26))
            if b.beam and b.beam_hot:
                x0, y0, x1, y1 = b.beam
                for k in range(0, 9):
                    add_glow(s, x0 + (x1 - x0) * k / 8 - cam, y0 + (y1 - y0) * k / 8 - cy, 70, (110, 26, 20), 3)
        if self.phase == "transform" and self.boss is not None:
            bx, by, cell = g._bo
            add_glow(s, bx + BOSS_W / 2 - cam, by + BOSS_H * (1 - self.convert) - cy, 150, (120, 110, 80))
        if self.phase in ("built", "quake"):
            bx, by, cell = g._bo
            k = 3 + int(math.sin(g.time_global * 6) > 0)
            add_glow(s, bx + BOSS_W / 2 - cam, by + BOSS_H / 2 - cy, 230, (110, 90, 40) if self.phase == "built" else (100, 30, 20), k)
        for bm in self.booms:
            u = bm.t / bm.dur
            if bm.kind == "fire" and u < 0.8:
                add_glow(s, bm.x - cam, bm.y - cy, int(bm.r * 2.2), (150, 90, 36), 4 if u < 0.4 else 2)
        for gr in self.grenades:
            add_glow(s, gr.x - cam, gr.y - cy, 46, (70, 60, 26), 3)
        for m in self.missiles:
            add_glow(s, m.x - cam, m.y - cy, 60, (110, 60, 22), 3)
        for sh in self.shocks:
            add_glow(s, sh.x - cam, g.ground_y - 30 - cy, 70, (110, 44, 24), 3)
        for pk in self.supply:
            if not pk.taken and abs(pk.base.x - cam - g.W / 2) < g.W / 2 + 80:
                col = (50, 70, 30) if pk.kind == "grenade" else (24, 70, 36)
                add_glow(s, pk.base.x - cam, pk.base.y - cy, 46, col, 3)
        for pk in g.pickups:
            if pk.kind == "brick" and not pk.taken and abs(pk.base.x - cam - g.W / 2) < g.W / 2 + 60:
                add_glow(s, pk.base.x - cam, pk.base.y - cy, 44, (74, 50, 16), 3)

    # --- оверлеи, HUD, диалоги
    def draw_overlay(self):
        g = self.g
        s = g.screen
        ph = self.phase
        if ph == "intro" and self.t < 0.9:
            self.fill_alpha((0, 0, 0), 1.0 - self.t / 0.9)
        if self.tint > 0:
            self.fill_alpha(self.tint_col, min(0.55, self.tint * 0.6))
        W = g.W
        if ph == "built" and 0.2 < self.t < 3.6:
            u = min(1.0, (self.t - 0.2) / 0.4)
            y = 112 - int((1 - u) * 30)
            g.text(s, "ПИСЮН ПОСТРОЕН!", 62, W // 2, y, YELLOW, center=True, bold=True)
            if self.t > 0.9:
                g.text(s, "Выглядит внушительно. Пока.", 22, W // 2, y + 56, WHITE, center=True)
        if ph == "boss" and 0.0 <= self.title_t < 3.4:
            u = min(1.0, self.title_t / 0.35)
            y = 150 - int((1 - u) * 40)
            g.text(s, "ГИГА-ПИСЮН", 74, W // 2, y, (255, 84, 70), center=True, bold=True)
            if self.title_t > 0.5:
                g.text(s, "построен лично вами", 22, W // 2, y + 56, WHITE, center=True)
        if self.flash > 0 and ph != "flash":
            self.fill_alpha((255, 255, 255), self.flash)

    def draw_hud(self):
        g = self.g
        s = g.screen
        dx = g.W - BASE_W
        ph = self.phase
        v = 2 if ph in ("transform", "boss", "dying", "flash") else 1
        s.blit(g.hud_base_b[(g.state == "play", v)], (0, 0))
        hp = g.player.hp
        for i in range(5):
            spr, c = g.heart_spr(10, PINK if i < hp else (90, 95, 110))
            s.blit(spr, (28 + i * 30 - c, 24 - c))
        if v == 1:
            g.text(s, "%d/%d" % (g.bricks_collected, CELLS), 20, 220, 13, WHITE, bold=True)
            s.blit(g.bar_img(g.bricks_collected), (300, 17))
            g.text(s, "БЛОКИ", 13, 300 + 190 + 8, 16, WHITE, bold=True)
        else:
            g.text(s, "БИТВА ЗА ПИСЮН", 17, 220, 14, (255, 130, 110), bold=True)
        gx = 590 + dx
        pygame.draw.circle(s, BLACK, (gx, 27), 11)
        pygame.draw.circle(s, (96, 124, 70), (gx, 27), 9)
        pygame.draw.circle(s, (160, 190, 120), (gx - 3, 24), 3)
        pygame.draw.rect(s, (200, 200, 210), (gx - 3, 11, 7, 6))
        pygame.draw.line(s, YELLOW, (gx + 3, 11), (gx + 9, 6), 2)
        ng = g.player.gren
        g.text(s, "%d" % ng, 19, 606 + dx, 13, LIGHT if ng > 0 else RED, bold=True)
        g.text(s, "ОЧКИ %d" % g.score, 19, 680 + dx, 13, YELLOW, bold=True)
        mm, ss = divmod(int(self.total), 60)
        g.text(s, "%02d:%02d" % (mm, ss), 19, 818 + dx, 13, WHITE, bold=True)
        if g.flash_timer > 0 and g.flash_text:
            g.text(s, g.flash_text, 22, g.W // 2, 88 if self.boss is None else 104, (120, 255, 150), center=True, bold=True)
        b = self.boss
        if b is not None and ph in ("boss", "dying"):
            self.draw_boss_bar(b)
        if g.show_fps:
            tag = "FPS %d" % int(g.clock.get_fps()) + ("  LITE" if g.lite else "")
            g.text(s, tag, 15, 8, 54, (255, 255, 120), bold=True)
        if self.can_build():
            self.draw_build_button()
        elif ph == "explore" and g.bricks_collected >= CELLS and g.player.rect.centerx < g.zone_x:
            dist = max(0, int((g.zone_x - g.player.rect.centerx) / TILE))
            g.text(s, "До стройплощадки: %d м" % dist, 18, g.W // 2, 62, (255, 230, 150), center=True, bold=True)

    def draw_build_button(self):
        g = self.g
        s = g.screen
        r = self.btn
        pulse = 0.5 + 0.5 * math.sin(g.time_global * 6)
        down = g.ui_is_down(r.inflate(24, 24))
        grow = r.inflate(int(8 * pulse), int(6 * pulse))
        col = (255, 196, 64) if not down else (255, 235, 150)
        pygame.draw.rect(s, (40, 26, 8), grow.inflate(10, 10), border_radius=18)
        pygame.draw.rect(s, col, grow, border_radius=16)
        pygame.draw.rect(s, WHITE, grow, 4, border_radius=16)
        g.text(s, "ПОСТРОИТЬ", 40, r.centerx, r.centery - 2, BLACK, center=True, bold=True, shadow=False)

    def draw_boss_bar(self, b):
        g = self.g
        s = g.screen
        w = min(560, g.W - 340)
        x = (g.W - w) // 2
        y = 56
        self.bar_disp += (b.hp / b.max_hp - self.bar_disp) * 0.12
        frac = clamp(b.hp / b.max_hp, 0.0, 1.0)
        pygame.draw.rect(s, (14, 16, 28), (x - 4, y - 4, w + 8, 26), border_radius=6)
        pygame.draw.rect(s, (88, 40, 40), (x, y, int(w * clamp(self.bar_disp, 0, 1)), 18))
        col = (230, 64, 56) if frac > 0.6 else ((255, 140, 50) if frac > 0.3 else (255, 220, 90))
        pygame.draw.rect(s, col, (x, y, int(w * frac), 18))
        for thr in (0.6, 0.3):
            pygame.draw.rect(s, (14, 16, 28), (x + int(w * thr) - 1, y, 3, 18))
        pygame.draw.rect(s, WHITE, (x - 4, y - 4, w + 8, 26), 2, border_radius=6)
        g.text(s, "ГИГА-ПИСЮН" + (("  ×%d" % b.n) if b.n > 1 else ""), 14, g.W // 2, y + 9, WHITE, center=True, bold=True)

    def _wrap_cache(self, d, font, width):
        if d.cache is None or d.cache[0] != width:
            pieces = wrap_text(font, d.text, width)
            out, pos = [], 0
            for pc in pieces:
                out.append((pos, pc))
                pos += len(pc) + 1
            d.cache = (width, out)
        return d.cache[1]

    def portrait(self):
        if self._portrait is None:
            g = self.g
            spr = g.player_spr(1, 0, 0)
            crop = pygame.Surface((32, 32))
            crop.fill((28, 34, 60))
            crop.blit(spr, (0, 0), pygame.Rect(2, 2, 32, 32))
            self._portrait = pygame.transform.scale(crop, (96, 96)).convert()
        return self._portrait

    def draw_dialogue(self):
        g = self.g
        d = self.dlg if (self.dlg is not None and self.dlg.blocking) else self.toast
        if d is None:
            return
        s = g.screen
        W = g.W
        big = d.blocking
        if big:
            rect = pygame.Rect(24, 58, W - 48, 148)
            size, lh = 25, 34
        else:
            size, lh = 18, 24
            f0 = g.font(size, True)
            wmax = min(700, W - 60)
            tw = max(f0.size(pc)[0] for pc in wrap_text(f0, d.text, wmax - 44))
            wd = min(wmax, tw + 44)
            nl = len(wrap_text(f0, d.text, wmax - 44))
            rect = pygame.Rect((W - wd) // 2, 124, wd, 20 + nl * lh)
        pygame.draw.rect(s, (0, 0, 0), rect)
        pygame.draw.rect(s, WHITE, rect, 4 if big else 3)
        tx = rect.x + 20
        if big:
            s.blit(self.portrait(), (rect.x + 18, rect.y + 26))
            pygame.draw.rect(s, WHITE, (rect.x + 16, rect.y + 24, 100, 100), 3)
            tx = rect.x + 140
        font = g.font(size, True)
        pieces = self._wrap_cache(d, font, rect.right - tx - 22)
        indent = font.size("* ")[0]
        n = int(d.shown)
        ty = rect.y + (22 if big else 10)
        for k, (st, pc) in enumerate(pieces):
            m = clamp(n - st, 0, len(pc))
            if m <= 0:
                break
            img = font.render(pc[:m], True, WHITE)
            s.blit(img, (tx + (indent if k else 0), ty + k * lh))
        if d.blocking and d.complete() and int(g.time_global * 3) % 2 == 0:
            pygame.draw.polygon(s, WHITE, [(rect.right - 40, rect.bottom - 30), (rect.right - 22, rect.bottom - 30),
                                           (rect.right - 31, rect.bottom - 17)])

    def draw_world(self, hud=True, overlays=True):
        g = self.g
        s = g.screen
        amp = g.shake_amp
        if g.shake > 0 and not g.lite:
            sx = int(random.uniform(-amp, amp))
            sy = int(random.uniform(-amp, amp) * 0.8)
        else:
            sx = sy = 0
        cam = int(g.camera_x) + sx
        cy = int(g.camera_y) + sy
        g.cy = cy
        self.ensure_assets()
        self.draw_bg(cam, cy)
        self.draw_zone(cam, cy)
        g.draw_checkpoints(cam, cy)
        g.draw_level(cam, cy)
        g.draw_moving_platforms(cam, cy)
        g.draw_pickups(cam, cy)
        self.draw_telegraph(cam, cy)
        self.draw_boss(cam, cy)
        for f in self.flying:
            u = f[7]
            x = f[0] + (f[2] - f[0]) * u
            y = f[1] + (f[3] - f[1]) * u - 4 * (70 + abs(f[2] - f[0]) * 0.12) * u * (1 - u)
            s.blit(self.cell_surf(f[5]), (int(x - cam - BOSS_CELL // 2), int(y - cy - BOSS_CELL // 2)))
        self.draw_hero(cam, cy)
        self.draw_fx(cam, cy)
        for pt in g.particles:
            pt.draw(s, cam, cy)
        for f in g.floaters:
            f.draw(s, cam, g)
        self.draw_lights(cam, cy)
        quiet = g.state == "gameover"
        if overlays and not quiet:
            self.draw_overlay()
        if hud:
            self.draw_hud()
            if not quiet:
                self.draw_dialogue()
            if g.role is not None:
                g.draw_coop_overlay()

    # --- экран итогов
    def draw_result(self):
        g = self.g
        s = g.screen
        W = g.W
        cx = W // 2
        r = self.res_t
        res = self.res
        st = self.stats
        self.draw_world(hud=False, overlays=False)
        self.fill_alpha((6, 8, 20), clamp((r - 1.8) / 2.5, 0, 1) * 0.72)
        if r > 2.6:
            g.text(s, "ВЫ ОДОЛЕЛИ ПИСЮН.", 58, cx, 62, WHITE, center=True, bold=True)
        if r > 3.4:
            f = g.font(18)
            for k, ln in enumerate(wrap_text(f, res["sub"], W - 180)):
                g.text(s, ln, 18, cx, 112 + k * 24, (200, 214, 245), center=True)
        mm, ss = divmod(int(st.get("boss_time", 0)), 60)
        m2, s2 = divmod(int(st.get("time", 0)), 60)
        acc = int(res["acc"] * 100)
        rows = [
            ("Время битвы с писюном", "%02d:%02d" % (mm, ss)),
            ("Всего за эту ночь", "%02d:%02d" % (m2, s2)),
            ("Блоков собрано", "%d/%d" % (st.get("blocks", CELLS), CELLS)),
            ("Гранат брошено", "%d" % st["thrown"]),
            ("Попаданий в писюна", "%d (%d%%)" % (st["hits"], acc)),
            ("Ракет увёрнуто", "%d" % st["dodged"]),
            ("Ударов получено", "%d" % st["hurt"]),
            ("Аптечек использовано", "%d" % st["meds"]),
        ]
        if st["attempts"] > 1:
            rows.append(("Попыток", "%d" % st["attempts"]))
        x0 = cx - 340
        for i, (lab, val) in enumerate(rows):
            if r < 3.8 + i * 0.26:
                break
            y = 160 + i * 29
            g.text(s, lab, 18, x0, y, (190, 202, 232))
            img = g.render(val, 18, WHITE, True)
            s.blit(g.render(val, 18, (0, 0, 0), True), (x0 + 372 - img.get_width() + 2, y + 2))
            s.blit(img, (x0 + 372 - img.get_width(), y))
        if r > 6.0:
            rx = cx + 205
            pygame.draw.rect(s, (14, 18, 36), (rx - 120, 154, 240, 246), border_radius=14)
            pygame.draw.rect(s, res["col"], (rx - 120, 154, 240, 246), 3, border_radius=14)
            g.text(s, "РАНГ", 16, rx, 172, (190, 202, 232), center=True, bold=True)
            if r > 6.15 and not self._slam_snd:
                self._slam_snd = True
                g.play("b_slam")
                g.shake = 0.3
                g.shake_amp = 5.0
            g.text(s, res["letter"], 120, rx, 244, res["col"], center=True, bold=True)
            f = g.font(16, True)
            for k, ln in enumerate(wrap_text(f, res["title"], 214)):
                g.text(s, ln, 16, rx, 318 + k * 20, res["col"], center=True, bold=True)
            g.text(s, "ОЧКИ: %d" % (g.score), 20, rx, 372, YELLOW, center=True, bold=True)
        if r > 7.0:
            f = g.font(16)
            for k, ln in enumerate(wrap_text(f, res["news"], W - 150)):
                g.text(s, ln, 16, cx, 418 + k * 22, (176, 190, 226), center=True)
        if r > 7.5:
            if g.role is not None:
                g.coop_end_buttons(cx, 468, "bwin")
            else:
                g.ui_button((cx - 245, 468, 230, 50), "ЕЩЁ РАЗ", "restart", 22, GREEN)
                g.ui_button((cx + 15, 468, 230, 50), "МЕНЮ", "menu", 22, LIGHT)
        if self.flash > 0:
            self.fill_alpha((255, 255, 255), self.flash)

    def gameover_lines(self):
        if self.boss_started:
            b = self.boss
            left = int(100 * b.hp / b.max_hp) if b is not None else 0
            return ("ПИСЮН ПОБЕДИЛ...", "Гигант остался целым на %d%%. Строители — не очень." % left if self.g.role
                    else "Гигант остался целым на %d%%. Строитель — не очень." % left,
                    "Бросков: %d  |  Попаданий: %d  |  Очки: %d" % (self.stats["thrown"], self.stats["hits"], self.g.score))
        return ("НОЧЬ ПОБЕДИЛА...", "Строитель так и не дошёл до стройплощадки.",
                "Блоков собрано: %d/%d   |   Очки: %d" % (self.g.bricks_collected, CELLS, self.g.score))
