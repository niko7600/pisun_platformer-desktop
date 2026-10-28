#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПИКСЕЛЬНЫЙ ПИСЮН: СТРОЙКА ВЕКА — мобильная версия (оптимизированная)
--------------------------------------------------------------------
Шуточный 2D-платформер на чистом pygame, без внешних картинок и звуков.
Вся графика рисуется кодом, звуки синтезируются.

Цель:
  Собери все 25 кирпичей. Каждый становится блоком монумента на стройке
  в конце уровня. Когда монумент готов — дойди до стройки.

Управление (экранные кнопки, настоящий мультитач):
  Слева   — две кнопки: влево / вправо (палец можно скользить между ними)
  Справа  — большая кнопка ПРЫЖОК (ещё раз в воздухе — двойной прыжок)
            и кнопка БЕГ (включает/выключает ускорение)
  Сверху справа — пауза. Кнопка «Назад» на Android тоже ставит паузу.
  Каждый палец отслеживается отдельно по finger_id, поэтому можно держать
  движение и прыгать одновременно, без залипаний.

Три режима (выбираются в меню):
  КЛАССИКА   — наша исходная карта
  ГЕНЕРАЦИЯ  — каждый раз новый процедурно собранный город: высокие здания,
               леса, краны, лифты и мосты, рабочие лестницы (кнопки ВВЕРХ/ВНИЗ),
               голуби-враги (сидячие пикируют, летающие роняют бомбочки).
               Каждая карта проверяется на проходимость до старта.
  БИТВА ЗА ПИСЮН — ночь, заранее заданная карта без врагов, но с шипами и
               бронированными зданиями. Собираешь 25 блоков, жмёшь ПОСТРОИТЬ,
               смотришь катсцену — и писюн оживает гигантским роботом. Дальше бой:
               кнопка ГРАНАТА (бросок целится сама), гранаты и аптечки по городу,
               шкала здоровья босса, взрыв, белая вспышка и итоги боя.
  Файлы рядом: levelgen.py (генератор карт), citydraw.py (рисование города),
               battlemap.py (карта битвы), battle.py (сюжет, босс, катсцены, звуки).

КО-ОП по Wi-Fi (до 6 игроков): кнопка КО-ОП в меню. Телефоны и компьютеры
играют вместе — протокол один и тот же.

Запуск на компьютере:
  pip install pygame        (нужен pygame 2.x / pygame-ce, SDL2)
  python main.py            (python main.py --fullscreen — сразу на весь экран)

На компьютере игра открывается в окне, F11 — полный экран. Клавиши: ←→ / A D —
ход, Пробел (Z, K) — прыжок, Shift — бег, ↑ / W — лестница (в Генерации) или
прыжок, ↓ / S — вниз по лестнице, G (F, X) — граната, E / Enter — «ПОСТРОИТЬ»
и реплики, Esc / P — пауза. Мышью тоже можно (как один «палец»).

Что сделано для скорости:
  * земля, платформы, шипы, ограждения, стройка, небо и интерфейс рисуются
    один раз в кэш и дальше только копируются, а не рисуются заново;
  * спрайты игрока, врагов, кирпичей, сердец и платформ кэшируются;
  * меню, пауза, справка и «игра окончена» перерисовываются только когда
    что-то изменилось (нажатие, смена экрана), а не 60 раз в секунду;
  * картинку на весь экран растягивает видеокарта (pygame.SCALED), если
    формат экрана подходит; иначе — запасной программный режим;
  * ширина кадра подстраивается под формат экрана — без чёрных полос;
  * физика идёт по реальному времени: если кадры медленные, игра не
    превращается в «замедленную съёмку»;
  * на очень слабом телефоне игра сама отключает дальний фон и лишние эффекты.

Настройки (константы ниже в файле):
  GPU_SCALING — аппаратное масштабирование. Если картинка пропала или
                нажатия «съехали» — поставь False.
  SHOW_FPS    — счётчик кадров. Его можно включить и в меню (кнопка FPS).

Проверка без окна (для разработчиков):
  python main.py --smoke-test
"""

import math
import os
from itertools import chain
import random
import sys
from array import array

for _s in (sys.stdout, sys.stderr):                  # Windows-консоль (cp1252) не должна падать на русском тексте
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if "--smoke-test" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# Касание не должно дублироваться синтетическими событиями мыши.
os.environ.setdefault("SDL_TOUCH_MOUSE_EVENTS", "0")

import pygame

import levelgen
import citydraw
import battle
import battlemap
import skins
import coop
import coopui

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------
BASE_W, SCREEN_H = 960, 540            # базовое логическое разрешение игры
MIN_W, MAX_W = 960, 1400               # ширина кадра подстраивается под экран
TILE = 36
LEVEL_TILES_W = 100
WORLD_W = LEVEL_TILES_W * TILE
WORLD_H = SCREEN_H
FPS = 60
MAX_STEP = 1 / 30                      # максимальный шаг физики
CAM_PAD = 280                          # камера выходит за края мира (кнопки)
LEVEL_PAD = 340                        # запас по краям кэша уровня
KEY = (255, 0, 255)                    # цвет прозрачности кэш-поверхностей

GPU_SCALING = True                     # аппаратное масштабирование (pygame.SCALED)
SHOW_FPS = False                       # счётчик fps по умолчанию

GRAVITY = 1550.0
MOVE_SPEED = 265.0
RUN_SPEED = 355.0
JUMP_VEL = 625.0
CLIMB_SPEED = 150.0                    # скорость лазания по лестнице, px/с

IS_ANDROID = ("ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ
              or hasattr(sys, "getandroidapilevel"))


def _ev(*names):
    return tuple(getattr(pygame, n) for n in names if hasattr(pygame, n))


PAUSE_EVENTS = _ev("APP_WILLENTERBACKGROUND", "APP_DIDENTERBACKGROUND",
                   "WINDOWFOCUSLOST", "WINDOWMINIMIZED", "WINDOWHIDDEN")
EXPOSE_EVENTS = _ev("WINDOWEXPOSED", "WINDOWRESTORED", "WINDOWSHOWN",
                    "WINDOWFOCUSGAINED", "APP_DIDENTERFOREGROUND")
RESIZE_EVENTS = _ev("VIDEORESIZE", "WINDOWRESIZED", "WINDOWSIZECHANGED")
BACK_KEYS = _ev("K_ESCAPE", "K_AC_BACK")
# Клавиатура (компьютер): клавиша -> экранная кнопка. «Вверх» (W/↑) в Генерации лазает по лестнице,
# в остальных режимах работает как прыжок.
KEY_BUTTONS = {
    pygame.K_LEFT: "left", pygame.K_a: "left",
    pygame.K_RIGHT: "right", pygame.K_d: "right",
    pygame.K_UP: "up", pygame.K_w: "up",
    pygame.K_DOWN: "down", pygame.K_s: "down",
    pygame.K_SPACE: "jump", pygame.K_z: "jump", pygame.K_k: "jump",
    pygame.K_g: "grenade", pygame.K_f: "grenade", pygame.K_x: "grenade",
}
KEY_RUN = (pygame.K_LSHIFT, pygame.K_RSHIFT)
KEY_ACT = (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER)

# Монумент: 5 клеток в ширину, 7 в высоту, всего ровно 25 блоков.
BUILD_SHAPE = [
    ".XXX.",
    "XXXXX",
    ".XXX.",
    ".XXX.",
    ".XXX.",
    "XX.XX",
    "XX.XX",
]
BUILD_CELLS_TOTAL = sum(row.count("X") for row in BUILD_SHAPE)  # 25

# Цвета
SKY_TOP = (64, 145, 220)
SKY_BOT = (170, 225, 255)
WHITE = (255, 255, 255)
BLACK = (20, 20, 30)
DARK = (27, 31, 48)
YELLOW = (255, 204, 64)
ORANGE = (255, 133, 51)
PINK = (255, 111, 168)
SKIN_BLOCK = (238, 177, 125)
SKIN_DARK = (201, 128, 82)
RED = (235, 64, 72)
GREEN = (65, 205, 105)
BLUE = (52, 105, 220)
LIGHT = (210, 225, 255)
BAR_COLOR = (10, 12, 20)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * t


def tile_rect(x, y, w=1, h=1):
    return pygame.Rect(int(x * TILE), int(y * TILE), int(w * TILE), int(h * TILE))


def choose_logical_width(pw, ph):
    """Ширина логического кадра под формат экрана (высота всегда 540)."""
    if ph <= 0:
        return BASE_W
    w = int(round(SCREEN_H * pw / ph / 2.0)) * 2
    return int(clamp(w, MIN_W, MAX_W))


# ---------------------------------------------------------------------------
# Шрифты, звуки, окно
# ---------------------------------------------------------------------------
_FONT_FALLBACKS = [
    "/system/fonts/Roboto-Regular.ttf",
    "/system/fonts/NotoSans-Regular.ttf",
    "/system/fonts/DroidSans.ttf",
]


def find_font_path():
    """Системный шрифт с кириллицей; None — тогда берём встроенный шрифт pygame."""
    try:
        p = pygame.font.match_font("arial,dejavusans,liberationsans,freesans,notosans,roboto")
        if p:
            return p
    except Exception:
        pass
    for p in _FONT_FALLBACKS:
        if os.path.exists(p):
            return p
    return None


def make_sound(notes, volume=0.22):
    """notes: список (частота_Гц, длительность_сек). Возвращает pygame Sound или None."""
    try:
        init = pygame.mixer.get_init()
        if not init:
            return None
        rate, fmt, channels = init
        rate = rate or 22050
        if fmt != -16:
            return None
        samples = array("h")
        for freq, dur in notes:
            n = max(1, int(rate * dur))
            for i in range(n):
                env = 1.0 - i / n
                wobble = 1.0 + 0.18 * math.sin(2 * math.pi * 6 * i / rate)
                val = math.sin(2 * math.pi * freq * i / rate) * wobble
                val += 0.25 * math.sin(4 * math.pi * freq * i / rate)
                v = int(clamp(val * env * volume, -1, 1) * 32767)
                for _ in range(channels):
                    samples.append(v)
        return pygame.mixer.Sound(buffer=samples.tobytes())
    except Exception:
        return None


def open_window(fullscreen, logical_w):
    """Открывает окно. Возвращает (surface, gpu_scaled).

    gpu_scaled=True: поверхность имеет логический размер (logical_w x 540),
    а растягивает её на экран видеокарта. Чтобы координаты касаний гарантированно
    совпали, этот режим включается на весь экран только если формат экрана
    совпадает с логическим кадром (то есть полос нет)."""
    if GPU_SCALING and hasattr(pygame, "SCALED"):
        ok = True
        if fullscreen:
            try:
                dw, dh = pygame.display.get_desktop_sizes()[0]
                ok = abs((logical_w / SCREEN_H) / (dw / dh) - 1.0) < 0.015
            except Exception:
                ok = False
        if ok:
            try:
                flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
                surf = pygame.display.set_mode((logical_w, SCREEN_H), flags)
                if surf.get_size() == (logical_w, SCREEN_H):
                    return surf, True
            except pygame.error:
                pass
    if fullscreen:
        return pygame.display.set_mode((0, 0), pygame.FULLSCREEN), False
    return pygame.display.set_mode((logical_w, SCREEN_H), pygame.RESIZABLE), False


# ---------------------------------------------------------------------------
# Игровые сущности
# ---------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, size=4, gravity=700):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.life = self.max_life = float(life)
        self.color = color
        self.size = size
        self.gravity = gravity

    def update(self, dt):
        self.life -= dt
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        return self.life > 0

    def draw(self, surf, cam, cy=0):
        a = clamp(self.life / self.max_life, 0, 1)
        s = max(1, int(self.size * a))
        surf.fill(self.color, (int(self.x - cam - s // 2), int(self.y - cy - s // 2), s, s))


class FloatingText:
    def __init__(self, x, y, text, color=YELLOW):
        self.x, self.y = float(x), float(y)
        self.text = text
        self.color = color
        self.life = 1.15

    def update(self, dt):
        self.life -= dt
        self.y -= 42 * dt
        return self.life > 0

    def draw(self, surf, cam, game):
        img = game.render(self.text, 17, self.color, True)
        shadow = game.render(self.text, 17, BLACK, True)
        pos = (self.x - cam - img.get_width() // 2, self.y - game.cy)
        surf.blit(shadow, (pos[0] + 2, pos[1] + 2))
        surf.blit(img, pos)


class MovingPlatform:
    def __init__(self, x, y, w_tiles, axis, distance, speed, phase=0.0):
        self.rect = pygame.Rect(int(x * TILE), int(y * TILE), int(w_tiles * TILE), 18)
        self.sx = float(self.rect.x)
        self.sy = float(self.rect.y)
        self.axis = axis            # 'x' или 'y'
        self.distance = distance    # пиксели
        self.speed = speed
        self.phase = phase
        self.dx = 0.0
        self.dy = 0.0

    def update(self, t):
        offset = (math.sin(t * self.speed + self.phase) * 0.5 + 0.5) * self.distance
        if self.axis == "x":
            nx, ny = self.sx + offset, self.sy
        else:
            nx, ny = self.sx, self.sy + offset
        self.dx = nx - self.rect.x
        self.dy = int(ny) - self.rect.y          # целое смещение: пассажира везём ровно на столько же
        self.rect.x, self.rect.y = int(nx), int(ny)


class Enemy:
    def __init__(self, x_tile, y_bottom_tile, min_x_tile, max_x_tile, speed=62):
        self.rect = pygame.Rect(int(x_tile * TILE), int(y_bottom_tile * TILE) - 38, 34, 38)
        self.min_x = min_x_tile * TILE
        self.max_x = max_x_tile * TILE
        self.speed = speed
        self.dir = 1
        self.alive = True
        self.anim = random.random() * 10
        self.hp = self.max_hp = 1           # в кооперативе у врагов вдвое больше здоровья
        self.inv = 0.0                      # после неубойного прыжка враг ненадолго неуязвим

    def update(self, dt):
        if not self.alive:
            return
        self.inv = max(0.0, self.inv - dt)
        self.anim += dt * 8
        self.rect.x += int(self.dir * self.speed * dt)
        if self.rect.left < self.min_x:
            self.rect.left = int(self.min_x)
            self.dir = 1
        if self.rect.right > self.max_x:
            self.rect.right = int(self.max_x)
            self.dir = -1


class Ladder:
    """Лестница. grab — зона захвата (чуть выше верха, чтобы схватиться стоя на площадке)."""

    def __init__(self, tx, ty0, ty1):
        self.top_y = ty0 * TILE
        self.bottom_y = ty1 * TILE
        self.cx = tx * TILE + TILE // 2
        self.grab = pygame.Rect(tx * TILE + 4, self.top_y - 8, TILE - 8, self.bottom_y - self.top_y + 8)


class Pigeon:
    """Голубь. 'perch' — сидит на крыше и пикирует на игрока; 'patrol' — летает цепочкой и сбрасывает помёт."""
    W, H = 30, 22

    def __init__(self, spec):
        self.kind = spec["kind"]
        self.alive = True
        self.rect = pygame.Rect(0, 0, self.W, self.H)
        self.anim = random.random() * 6.0
        self.t = 0.0
        self.face = 1
        self.state = "idle"
        self.timer = 0.0
        self.cool = random.uniform(0.4, 1.4)
        self.flash = 0.0
        self.vx = self.vy = 0.0
        self.hp = self.max_hp = 1
        self.inv = 0.0
        self.tx = self.ty = 0.0
        if self.kind == "perch":
            self.hx = spec["x"] * TILE + TILE / 2
            self.hy = spec["row"] * TILE - self.H / 2
            self.x, self.y = self.hx, self.hy
            self.face = spec.get("face", 1)
        else:
            self.px0 = spec["x0"] * TILE
            self.px1 = spec["x1"] * TILE
            self.base_y = spec["row"] * TILE
            self.amp = spec["amp"] * TILE
            self.speed = spec["speed"]
            self.lag = spec["lag"]
            self.phase = spec["phase"]
            self.poop_cd = random.uniform(1.2, 2.6)
            self.x, self.y = self.px0, self.base_y
            self.pos_patrol(0.0)
        self.sync()

    def sync(self):
        self.rect.center = (int(self.x), int(self.y))

    def pos_patrol(self, t):
        length = max(1.0, self.px1 - self.px0)
        u = (self.speed * (t + self.phase * 3.0 - self.lag)) % (2 * length)
        if u < length:
            self.x, self.face = self.px0 + u, 1
        else:
            self.x, self.face = self.px0 + 2 * length - u, -1
        self.y = self.base_y + math.sin(t * 2.3 + self.phase - self.lag * 1.6) * self.amp

    def update(self, dt, game):
        if not self.alive:
            return
        self.t += dt
        self.inv = max(0.0, self.inv - dt)
        p = game.nearest_player(self.x, self.y)
        if self.flash > 0:
            self.flash -= dt
        if self.kind == "patrol":
            self.anim += dt * 11
            self.pos_patrol(self.t)
            self.poop_cd -= dt
            if self.poop_cd <= 0 and game.state == "play":
                dx = p.rect.centerx - self.x
                dy = p.rect.centery - self.y
                if abs(dx) < 30 and 40 < dy < 380:
                    game.poops.append([self.x, self.y + 10, 0.0])
                    self.poop_cd = random.uniform(3.0, 4.6)
                    self.flash = 0.3
            self.sync()
            return
        # сидящий голубь
        dx = p.rect.centerx - self.x
        dy = p.rect.centery - self.y
        if self.state == "idle":
            self.anim += dt * 3.0
            self.cool = max(0.0, self.cool - dt)
            if abs(dx) < 420:
                self.face = 1 if dx > 0 else -1
            if self.cool <= 0 and abs(dx) < 300 and -60 < dy < 320 and game.state == "play":
                if game.los(self.x, self.y, p.rect.centerx, p.rect.centery):
                    self.state = "alert"
                    self.timer = 0.5
                else:
                    self.cool = 0.25               # между ними стена — не нападаем
        elif self.state == "alert":
            self.timer -= dt
            self.anim += dt * 16
            self.face = 1 if dx > 0 else -1
            if self.timer <= 0:
                tx, ty = p.rect.centerx, p.rect.centery
                vx, vy = tx - self.x, ty - self.y
                d = math.hypot(vx, vy) or 1.0
                self.vx, self.vy = vx / d * 340, vy / d * 340
                self.state = "dive"
                self.timer = 1.3
        elif self.state == "dive":
            self.anim += dt * 14
            self.timer -= dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.sync()
            if self.timer <= 0 or (self.timer < 1.15 and game.solid_hit(self.rect)):
                self.state = "return"
        elif self.state == "return":
            self.anim += dt * 12
            vx, vy = self.hx - self.x, self.hy - self.y
            d = math.hypot(vx, vy)
            if d < 8:
                self.x, self.y = self.hx, self.hy
                self.state = "idle"
                self.cool = random.uniform(2.4, 3.6)
            else:
                self.face = 1 if vx > 0 else -1
                self.x += vx / d * 190 * dt
                self.y += vy / d * 190 * dt
        self.sync()


class Pickup:
    def __init__(self, kind, x_tile, y_tile):
        self.kind = kind            # 'brick' | 'bolt' | 'heart'
        self.base = pygame.Vector2(x_tile * TILE + TILE // 2, y_tile * TILE + TILE // 2)
        self.rect = pygame.Rect(0, 0, 28, 28)
        self.rect.center = (int(self.base.x), int(self.base.y))
        self.taken = False
        self.taken_at = None
        self.phase = random.random() * math.tau


class Player:
    def __init__(self, x, y, pid=0, nick="", skin=0, remote=False):
        self.pid = pid                  # номер игрока (0 — хост / одиночная игра)
        self.nick = nick
        self.skin = skin
        self.remote = remote            # герой другого игрока: физику считает его устройство
        self.dead = False
        self.respawn_t = 0.0
        self.gren = 0
        self.throw_cd = 0.0
        self.epoch = 0                  # растёт при телепорте: старые пакеты позиции игнорируются
        self.dx, self.dy = float(x), float(y)   # сглаженная позиция для рисования чужих героев
        self.net_t = 0.0
        self.rect = pygame.Rect(x, y, 28, 42)
        self.vel = pygame.Vector2(0, 0)
        self.facing = 1
        self.on_ground = False
        self.standing_on = None
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.jumps_used = 0
        self.invuln = 0.0
        self.hp = 5
        self.anim = 0.0
        self.dead_spin = 0.0
        self.climb = None          # Ladder, по которой лезем
        self.drop = 0.0            # игнорировать тонкие платформы (спрыгнуть вниз)
        self.on_oneway = False
        self.cy_acc = 0.0


class Control:
    """Экранная кнопка. Геометрия и зона нажатия — в пикселях реального экрана."""

    def __init__(self, name, shape, geom, hit, dpad=False):
        self.name = name
        self.shape = shape          # "rect" | "circle"
        self.geom = geom            # Rect  или  (cx, cy, r)
        self.hit = hit              # Rect  или  радиус зоны нажатия
        self.dpad = dpad
        if shape == "rect":
            self.pos = geom.topleft
        else:
            cx, cy, r = geom
            self.pos = (int(cx - r), int(cy - r))

    def contains(self, x, y, grow=1.0):
        if self.shape == "rect":
            r = self.hit
            if grow != 1.0:
                r = r.inflate(int(r.w * (grow - 1)), int(r.h * (grow - 1)))
            return r.collidepoint(x, y)
        cx, cy, _ = self.geom
        rad = self.hit * grow
        return (x - cx) ** 2 + (y - cy) ** 2 <= rad * rad


# ---------------------------------------------------------------------------
# Уровень: платформы, шипы, объекты. Координаты — в тайлах.
# ---------------------------------------------------------------------------
SOLID_TILES = [
    # земля (с ямами). Крайние сегменты продлены за края мира,
    # чтобы при сдвинутой камере не было пустоты.
    (-8, 13, 26, 2), (21, 13, 19, 2), (43, 13, 22, 2), (68, 13, 40, 2),
    # сегмент A
    (4, 10, 4, 1), (9, 8, 4, 1), (13, 10, 4, 1),
    # сегмент B
    (23, 10, 4, 1), (28, 8, 4, 1), (33, 10, 4, 1), (36, 7, 3, 1),
    (40, 11, 3, 2),
    # сегмент C
    (45, 10, 4, 1), (50, 8, 4, 1), (55, 10, 4, 1), (59, 7, 4, 1),
    (63, 11, 2, 2),
    # сегмент D (подход к стройке)
    (70, 10, 4, 1), (75, 8, 4, 1), (80, 10, 3, 1),
]
SPIKE_TILES = [(35, 13), (58, 13), (78, 13)]

MOVING_DEFS = [
    (18.0, 11.3, 3, "x", 95, 1.15, 0.0),
    (39.7, 11.3, 3, "x", 105, 1.30, 2.0),
    (64.7, 11.3, 3, "x", 105, 1.45, 4.0),
    (82.3, 10.6, 3, "y", 105, 1.10, 1.0),
]

BRICK_POS = [
    # A (5)
    (5, 9.2), (10, 7.2), (14, 9.2), (16, 12.2), (7, 12.2),
    # B (7)
    (24, 9.2), (29, 7.2), (34, 9.2), (37, 6.2), (26, 12.2), (31, 12.2), (38, 12.2),
    # C (7)
    (46, 9.2), (51, 7.2), (56, 9.2), (60, 6.2), (48, 12.2), (54, 12.2), (62, 12.2),
    # D (6)
    (71, 9.2), (76, 7.2), (81, 9.2), (73, 12.2), (79, 12.2), (84, 12.2),
]
assert len(BRICK_POS) == BUILD_CELLS_TOTAL, "Кирпичей должно быть ровно по числу блоков монумента!"

BOLT_POS = [(6, 12.2), (11, 7.2), (30, 12.2), (52, 12.2), (57, 9.2),
            (61, 12.2), (72, 12.2), (77, 12.2), (82, 6.2), (88, 12.2)]
HEART_POS = [(29, 7.2), (60, 6.2), (82, 5.2)]
ENEMY_DEFS = [
    (13, 13, 12.3, 16.8, 62), (27, 13, 24.5, 31.5, 72), (51, 13, 47.5, 57.5, 82),
    (74, 13, 70.5, 79.5, 76), (52, 8, 50.3, 53.6, 55),
]
CHECKPOINT_TILES = [22, 44, 68]
BUILD_ZONE_X = 86 * TILE

def classic_level():
    """Классическая карта в общем формате уровня (как и сгенерированная)."""
    L = levelgen.Level("classic")
    L.cols, L.rows, L.ground_row = LEVEL_TILES_W, 15, 13
    L.solids = [(tx, ty, tw, th, "auto", 0) for (tx, ty, tw, th) in SOLID_TILES]
    L.spikes = list(SPIKE_TILES)
    L.moving = list(MOVING_DEFS)
    L.bricks = list(BRICK_POS)
    L.bolts = list(BOLT_POS)
    L.hearts = list(HEART_POS)
    L.foremen = list(ENEMY_DEFS)
    L.checkpoints = list(CHECKPOINT_TILES)
    L.zone_tx = 86
    L.spawn = (1.2, 11)
    return L


CONTROL_ORDER = ("pause", "jump", "run", "grenade", "up", "down", "left", "right")


# ---------------------------------------------------------------------------
# Игра
# ---------------------------------------------------------------------------
class Game(coop.CoopMixin, coopui.CoopUIMixin):
    PlayerCls = Player

    def __init__(self, window, fullscreen=True, logical_w=None, gpu_scaled=False):
        self.coop_init()
        self.window = window                       # реальный экран
        self.gpu_scaled = gpu_scaled
        self.auto_width = not gpu_scaled           # ширина кадра по формату окна
        self.W = int(logical_w) if logical_w else BASE_W
        self.pause_rect = pygame.Rect(self.W - 54, 6, 44, 36)
        self.screen = window                       # холст; layout() поставит нужный
        self.direct = False
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = "menu"       # menu | help | play | pause | win | gameover
        self.sound_on = True
        self.fullscreen = fullscreen
        self.show_fps = SHOW_FPS
        self.lite = False
        self._ema = 1 / 60
        self._slow = 0
        self.dirty = True
        self.idle = 0.0
        self.time_global = 0.0

        self.fonts = {}
        self.font_path = find_font_path()
        self._text_cache = {}
        self._overlays = {}
        self._spr = {}
        self.snap = None
        self.menu_bg = None
        self.help_bg = None

        # ввод: каждый палец — отдельно, по finger_id
        self.fingers = {}      # id -> (x, y) в пикселях экрана
        self.finger_btn = {}   # id -> имя игровой кнопки | None
        self.ui_press = {}     # id -> действие меню | None
        self.ui_buttons = []   # [(Rect в логических координатах, действие)]
        self.run_on = False
        self.controls = {}
        self.ctl_imgs = {}
        self.bars = []
        self.view = pygame.Rect(0, 0, 1, 1)
        self.view_surf = None
        self.view_sx = self.view_sy = 1.0
        self.win_size = window.get_size()

        self.sounds = {
            "jump": make_sound([(420, 0.07), (640, 0.07)]),
            "double": make_sound([(560, 0.06), (880, 0.08)]),
            "collect": make_sound([(880, 0.06), (1320, 0.09)]),
            "bolt": make_sound([(1180, 0.05), (1560, 0.06)], 0.16),
            "hurt": make_sound([(220, 0.10), (140, 0.14)]),
            "stomp": make_sound([(300, 0.06), (180, 0.09)]),
            "check": make_sound([(660, 0.07), (990, 0.10)]),
            "heart": make_sound([(740, 0.07), (1110, 0.10)]),
            "win": make_sound([(523, 0.13), (659, 0.13), (784, 0.13),
                               (1046, 0.22), (1318, 0.30)], 0.24),
        }

        self.ghost = pygame.Surface((26, 26)).convert()
        self.ghost.fill((30, 36, 58))

        self.cy = 0
        self.camera_y = 0.0
        self.mode = "classic"
        self.seed = 0
        self.pending = None
        self.battle = None            # режим «Битва за Писюн» (battle.py)
        self.bjobs = None
        self.night = False
        self.safe = False
        self.shake_amp = 5.0
        self._battle_lvl = None
        self.hud_base_b = {}
        self.lvl = None
        self.strips = None
        self.level = None
        self.classic = classic_level()
        self.setup_level(self.classic)
        self.reset_game()
        self.build_width_caches()
        self.layout()

    # ---------- ресурсы/утилиты ----------
    def make_pickup(self, kind, x_tile, y_tile):
        return Pickup(kind, x_tile, y_tile)

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            try:
                if self.font_path:
                    f = pygame.font.Font(self.font_path, size)
                    f.set_bold(bold)
                else:
                    f = pygame.font.Font(None, int(size * 1.4))
            except Exception:
                f = pygame.font.Font(None, int(size * 1.4))
            self.fonts[key] = f
        return self.fonts[key]

    def render(self, txt, size, color, bold=False):
        key = (txt, size, color, bold)
        img = self._text_cache.get(key)
        if img is None:
            if len(self._text_cache) > 400:
                self._text_cache.clear()
            img = self.font(size, bold).render(txt, True, color)
            self._text_cache[key] = img
        return img

    def play(self, name, net=True):
        if self.bc and net:
            self.fx_emit(("s", name))
        s = self.sounds.get(name)
        if self.sound_on and s is not None:
            try:
                s.play()
            except Exception:
                pass

    def text(self, surf, txt, size, x, y, color=WHITE, center=False, bold=False, shadow=True):
        img = self.render(txt, size, color, bold)
        r = img.get_rect()
        if center:
            r.center = (int(x), int(y))
        else:
            r.topleft = (int(x), int(y))
        if shadow:
            surf.blit(self.render(txt, size, (0, 0, 0), bold), (r.x + 2, r.y + 2))
        surf.blit(img, r)
        return r

    def overlay(self, color, alpha):
        key = (color, alpha)
        ov = self._overlays.get(key)
        if ov is None:
            ov = pygame.Surface((self.W, SCREEN_H), pygame.SRCALPHA)
            ov.fill((*color, alpha))
            ov = ov.convert_alpha()
            self._overlays[key] = ov
        self.screen.blit(ov, (0, 0))

    def burst(self, x, y, colors, n=16, speed=260, life=0.6, size=5, gravity=700):
        if self.bc:
            self.fx_emit(("b", int(x), int(y), [list(c) for c in colors], n, speed, life, size, gravity))
        if self.lite:
            if len(self.particles) > 70:
                return
            n = max(3, n // 2)
        for _ in range(n):
            a = random.random() * math.tau
            v = random.uniform(speed * 0.25, speed)
            self.particles.append(Particle(
                x, y, math.cos(a) * v, math.sin(a) * v - 90,
                random.uniform(life * 0.5, life), random.choice(colors),
                random.randint(2, size), gravity))

    def flash_msg(self, text, secs):
        """Большая подсказка по центру экрана (в кооперативе её видят все)."""
        self.flash_text = text
        self.flash_timer = secs
        if self.bc:
            self.fx_emit(("ft", text, secs))

    def float_text(self, x, y, txt, color=YELLOW):
        if self.bc:
            self.fx_emit(("f", int(x), int(y), txt, list(color)))
        self.floaters.append(FloatingText(x, y, txt, color))

    def _new_sprite(self, w, h):
        s = pygame.Surface((int(w), int(h))).convert()
        s.fill(KEY)
        # RLE: пустые (прозрачные) участки при копировании пропускаются целыми кусками
        s.set_colorkey(KEY, pygame.RLEACCEL)
        return s

    # ---------- кэши статичной графики ----------
    def build_static_caches(self):
        """Кэши, которые не зависят от ширины кадра. Строятся один раз."""
        self.build_level_cache()
        self.build_zone_cache()
        self.build_sky_layers()
        self._bo = self.build_origin()

    def build_level_cache(self):
        """Вся земля, платформы-леса, шипы и ограждения — одной картинкой."""
        if self.mode in ("gen", "battle", "lobby"):
            self.strips, self.lvl_y0 = citydraw.build_strips(self.lvl, self.spikes, self._new_sprite,
                                                             night=self.night)
            self.level = None
            return
        self.strips = None
        gy = 13 * TILE
        self.lvl_y0 = min(min(r.top for r in self.solids), gy - 92)
        y0 = self.lvl_y0
        surf = self._new_sprite(WORLD_W + 2 * LEVEL_PAD, WORLD_H - y0)
        s = surf
        for r in self.solids:
            is_ground = r.height >= TILE * 2 - 4 and r.bottom >= WORLD_H - 4
            tx0, tx1 = r.left // TILE, (r.right - 1) // TILE
            ty0, ty1 = r.top // TILE, (r.bottom - 1) // TILE
            for ty in range(ty0, ty1 + 1):
                for tx in range(tx0, tx1 + 1):
                    x, y = tx * TILE + LEVEL_PAD, ty * TILE - y0
                    hsh = (tx * 73856093) ^ (ty * 19349663)
                    if is_ground:
                        if ty == 13:
                            pygame.draw.rect(s, (96, 178, 92), (x, y, TILE, 10))
                            pygame.draw.rect(s, (70, 140, 66), (x, y + 8, TILE, 3))
                            pygame.draw.rect(s, (140, 98, 64), (x, y + 10, TILE, TILE - 10))
                        else:
                            pygame.draw.rect(s, (122, 84, 55), (x, y, TILE, TILE))
                        pygame.draw.rect(s, (100, 68, 44), (x, y, TILE, TILE), 1)
                        if hsh % 5 == 0:
                            pygame.draw.rect(s, (105, 70, 46), (x + 7 + hsh % 17, y + 16, 7, 4))
                    else:
                        pygame.draw.rect(s, (176, 124, 66), (x, y, TILE, TILE))
                        pygame.draw.rect(s, (146, 98, 48), (x, y + TILE - 9, TILE, 9))
                        pygame.draw.rect(s, (120, 78, 38), (x, y, TILE, TILE), 2)
                        pygame.draw.circle(s, (90, 60, 30), (x + 6, y + 7), 2)
                        pygame.draw.circle(s, (90, 60, 30), (x + TILE - 6, y + 7), 2)
                        if hsh % 4 == 0:
                            pygame.draw.line(s, (130, 86, 42), (x + 5, y + 20), (x + 24, y + 16), 2)
        for sp in self.spikes:
            for i in range(4):
                x = sp.left + LEVEL_PAD + i * 8
                top, bot = sp.top - y0, sp.bottom - y0
                pygame.draw.polygon(s, (205, 212, 222), [(x, bot), (x + 4, top), (x + 8, bot)])
                pygame.draw.polygon(s, (140, 148, 160), [(x + 4, top), (x + 8, bot), (x + 4, bot)])
        # полосатые заграждения на краях уровня
        for wx in (0, WORLD_W):
            x = wx + LEVEL_PAD
            g = gy - y0
            pygame.draw.rect(s, (120, 124, 135), (x - 4, g - 92, 8, 92))
            for k, by in enumerate((g - 88, g - 58)):
                for j in range(3):
                    col = RED if (j + k) % 2 == 0 else WHITE
                    pygame.draw.rect(s, col, (x - 18 + j * 12, by, 12, 14))
                pygame.draw.rect(s, BLACK, (x - 18, by, 36, 14), 2)
        self.level = surf

    def build_zone_cache(self):
        """Неподвижные части стройки: фундамент, леса, конусы, табличка."""
        bx, by, cell = self.build_origin()
        gy = self.ground_y
        ZX = self.zone_x
        self.zone_x0 = ZX - 70
        self.zone_y0 = gy - 328
        self.zone_w = TILE * 15
        zh = gy + 4 - self.zone_y0
        s = self._new_sprite(self.zone_w, zh)
        ox, oy = -self.zone_x0, -self.zone_y0
        pygame.draw.rect(s, (150, 155, 165), (ZX - 10 + ox, gy - 8 + oy, TILE * 13, 10))
        pygame.draw.rect(s, BLACK, (ZX - 10 + ox, gy - 8 + oy, TILE * 13, 10), 2)
        for lx in (bx - 34, bx + cell * 5 + 14):
            pygame.draw.rect(s, (120, 124, 135), (lx + ox, by - 46 + oy, 8, gy - by + 46))
            pygame.draw.rect(s, (95, 99, 110), (lx - 5 + ox, by - 46 + oy, 18, 7))
        pygame.draw.rect(s, (120, 124, 135), (bx - 39 + ox, by - 46 + oy, cell * 5 + 84, 8))
        for cx in (ZX + 30, ZX + TILE * 11):
            x = cx + ox
            pygame.draw.polygon(s, ORANGE, [(x, gy + oy), (x + 10, gy - 24 + oy), (x + 20, gy + oy)])
            pygame.draw.rect(s, WHITE, (x + 4, gy - 14 + oy, 12, 5))
        sign_x = ZX + 66 + ox
        pygame.draw.rect(s, (40, 44, 62), (sign_x, gy - 318 + oy, 238, 54))
        pygame.draw.rect(s, YELLOW, (sign_x, gy - 318 + oy, 238, 54), 3)
        for tx in (sign_x + 14, sign_x + 238 - 30):
            pygame.draw.polygon(s, YELLOW, [(tx, gy - 292 + oy), (tx + 8, gy - 308 + oy), (tx + 16, gy - 292 + oy)])
            pygame.draw.line(s, BLACK, (tx + 8, gy - 302 + oy), (tx + 8, gy - 297 + oy), 2)
        pygame.draw.rect(s, (90, 95, 110), (sign_x + 50, gy - 82 + oy, 6, 82))
        pygame.draw.rect(s, (90, 95, 110), (sign_x + 182, gy - 82 + oy, 6, 82))
        if self.night:
            citydraw.darken(s)
        self.zone_surf = s

    def build_sky_layers(self):
        """Параллакс-слои фона, нарисованные заранее длинными полосами."""
        # солнце в каске
        spr = self._new_sprite(84, 90)
        cx, cy = 42, 46
        pygame.draw.circle(spr, (255, 226, 120), (cx, cy), 34)
        pygame.draw.circle(spr, (255, 240, 170), (cx, cy), 27)
        pygame.draw.rect(spr, YELLOW, (cx - 30, cy - 38, 60, 16))
        pygame.draw.rect(spr, (230, 175, 40), (cx - 36, cy - 24, 72, 6))
        pygame.draw.circle(spr, BLACK, (cx - 10, cy + 2), 3)
        pygame.draw.circle(spr, BLACK, (cx + 10, cy + 2), 3)
        pygame.draw.arc(spr, BLACK, (cx - 12, cy + 4, 24, 14), math.pi * 1.08, math.pi * 1.92, 2)
        self.sun_spr = spr
        self.sun_c = (cx, cy)

        # дальние дома (параллакс 0.45), период 300
        self.bld_y0 = 288
        s = self._new_sprite(2300, 200)
        for i in range(8):
            bx = i * 300
            bh = 90 + (i * 53) % 90
            pygame.draw.rect(s, (126, 168, 208), (bx, SCREEN_H - 72 - bh - self.bld_y0, 120, bh))
            for wy in range(SCREEN_H - 60 - bh, SCREEN_H - 90, 26):
                for wx in range(bx + 12, bx + 105, 24):
                    pygame.draw.rect(s, (190, 225, 245), (wx, wy - self.bld_y0, 12, 14))
        self.bld_strip = s

        # краны (тот же параллакс), период 620
        s = self._new_sprite(1800, 270)
        for i in range(3):
            sx = i * 620 + 240 + 70
            pygame.draw.rect(s, (230, 145, 60), (sx, 10, 8, 250))
            pygame.draw.rect(s, (230, 145, 60), (sx - 70, 2, 210, 8))
            pygame.draw.line(s, (170, 100, 40), (sx + 120, 10), (sx + 120, 65), 3)
            pygame.draw.rect(s, (150, 150, 160), (sx + 106, 65, 28, 22))
        self.crane_strip = s

        # холмы (параллакс 0.6), период 260
        s = self._new_sprite(1900, 110)
        for i in range(7):
            pygame.draw.ellipse(s, (104, 190, 130), (i * 260, 0, 300, 110))
        self.hill_strip = s

    def build_width_caches(self):
        """Кэши, которые зависят от ширины кадра."""
        W = self.W
        sky = pygame.Surface((W, SCREEN_H)).convert()
        for y in range(0, SCREEN_H, 6):
            t = y / SCREEN_H
            col = tuple(int(lerp(SKY_TOP[i], SKY_BOT[i], t)) for i in range(3))
            pygame.draw.rect(sky, col, (0, y, W, 6))
        self.sky = sky

        # облака (параллакс 0.3): одна полоса длиной в период, два блита
        P = W + 260
        self.cloud_period = P
        strip = self._new_sprite(P, 220)
        for i in range(9):
            b = (i * 340 + 80) % P
            cy = 52 + (i * 41) % 130
            scale = 1.0 + (i % 3) * 0.25
            self._cloud(strip, b, cy, scale)
            self._cloud(strip, b - P, cy, scale)
        self.cloud_strip = strip
        self.build_hud_base()

    def _cloud(self, surf, x, y, scale=1.0):
        c = (255, 255, 255)
        w, h = int(74 * scale), int(22 * scale)
        pygame.draw.ellipse(surf, c, (x, y, w, h))
        pygame.draw.ellipse(surf, c, (x + int(16 * scale), y - int(12 * scale), int(44 * scale), int(26 * scale)))
        pygame.draw.ellipse(surf, c, (x + int(38 * scale), y - int(6 * scale), int(40 * scale), int(22 * scale)))

    def build_hud_base(self):
        """Панель HUD с неподвижными значками (с кнопкой паузы и без неё)."""
        W = self.W
        dx = W - BASE_W
        self.hud_base = {}
        for play in (False, True):
            s = pygame.Surface((W, 48), pygame.SRCALPHA)
            s.fill((18, 22, 38, 175))
            pygame.draw.rect(s, (224, 122, 58), (190, 13, 22, 22))
            pygame.draw.rect(s, BLACK, (190, 13, 22, 22), 2)
            pygame.draw.line(s, (178, 84, 38), (190, 24), (212, 24), 3)
            gx, gy = 590 + dx, 24
            pts = [(gx + math.cos(math.pi / 3 * i) * 10, gy + math.sin(math.pi / 3 * i) * 10) for i in range(6)]
            pygame.draw.polygon(s, (196, 205, 218), pts)
            pygame.draw.polygon(s, BLACK, pts, 2)
            pygame.draw.circle(s, (90, 98, 112), (gx, gy), 4)
            if play:
                r = self.pause_rect
                pygame.draw.rect(s, (52, 58, 78), r, border_radius=8)
                pygame.draw.rect(s, WHITE, r, 2, border_radius=8)
                pygame.draw.rect(s, WHITE, (r.x + 14, r.y + 9, 6, 18))
                pygame.draw.rect(s, WHITE, (r.x + 25, r.y + 9, 6, 18))
            self.hud_base[play] = s.convert_alpha()
        # варианты панели для боя: v1 — с иконкой блоков, v2 — без неё (идёт бой с боссом); гайки не нужны
        self.hud_base_b = {}
        for play in (False, True):
            for v in (1, 2):
                s = pygame.Surface((W, 48), pygame.SRCALPHA)
                s.fill((18, 22, 38, 175))
                if v == 1:
                    pygame.draw.rect(s, (224, 122, 58), (190, 13, 22, 22))
                    pygame.draw.rect(s, BLACK, (190, 13, 22, 22), 2)
                    pygame.draw.line(s, (178, 84, 38), (190, 24), (212, 24), 3)
                if play:
                    r = self.pause_rect
                    pygame.draw.rect(s, (52, 58, 78), r, border_radius=8)
                    pygame.draw.rect(s, WHITE, r, 2, border_radius=8)
                    pygame.draw.rect(s, WHITE, (r.x + 14, r.y + 9, 6, 18))
                    pygame.draw.rect(s, WHITE, (r.x + 25, r.y + 9, 6, 18))
                self.hud_base_b[(play, v)] = s.convert_alpha()

    def set_logical_width(self, w):
        self.W = int(w)
        self.pause_rect = pygame.Rect(self.W - 54, 6, 44, 36)
        self.menu_bg = self.help_bg = self.snap = None
        self._night_A = None
        self.coop_bg = None
        self._overlays.clear()
        self.build_width_caches()

    # ---------- кэшируемые спрайты ----------
    def bar_img(self, n):
        key = ("bar", n)
        img = self._spr.get(key)
        if img is None:
            bw = 190
            img = pygame.Surface((bw, 14)).convert()
            img.fill((52, 58, 78))
            fill = int(bw * n / BUILD_CELLS_TOTAL)
            pygame.draw.rect(img, PINK if n >= BUILD_CELLS_TOTAL else YELLOW, (0, 0, fill, 14))
            pygame.draw.rect(img, WHITE, (0, 0, bw, 14), 2)
            self._spr[key] = img
        return img

    def heart_spr(self, size, color):
        key = ("h", size, color)
        v = self._spr.get(key)
        if v is None:
            c = size + 2
            s = self._new_sprite(2 * c, 2 * c + 8)
            cx = cy = c
            pygame.draw.rect(s, color, (cx - size, cy - size // 2, size, size))
            pygame.draw.rect(s, color, (cx, cy - size // 2, size, size))
            pygame.draw.polygon(s, color, [(cx - size, cy + size // 3),
                                           (cx + size, cy + size // 3), (cx, cy + size + 4)])
            pygame.draw.rect(s, WHITE, (cx - size + 3, cy - size // 2 + 2, 5, 5))
            v = (s, c)
            self._spr[key] = v
        return v

    def draw_heart(self, cx, cy, size, color):
        spr, c = self.heart_spr(size, color)
        self.screen.blit(spr, (cx - c, cy - c))

    def brick_spr(self, glow):
        key = ("brick", glow)
        s = self._spr.get(key)
        if s is None:
            o = 8
            s = self._new_sprite(28 + 2 * o, 28 + 2 * o)
            g = glow
            pygame.draw.rect(s, (255, 225, 120), (o - g, o - g, 28 + g * 2, 28 + g * 2))
            pygame.draw.rect(s, (224, 122, 58), (o, o, 28, 28))
            pygame.draw.rect(s, (178, 84, 38), (o, o + 12, 28, 4))
            pygame.draw.rect(s, (178, 84, 38), (o + 12, o, 4, 12))
            pygame.draw.rect(s, (178, 84, 38), (o + 6, o + 16, 4, 12))
            pygame.draw.rect(s, BLACK, (o, o, 28, 28), 2)
            self._spr[key] = s
        return s

    def platform_spr(self, w, h):
        key = ("mp", w, h, self.night)
        s = self._spr.get(key)
        if s is None:
            # +8 справа: последняя заклёпка оригинала выступает за край платформы
            s = self._new_sprite(w + 8, h + 46)
            y0 = 46
            pygame.draw.rect(s, (238, 178, 76), (0, y0, w, h))
            pygame.draw.rect(s, (190, 130, 40), (0, y0 + h - 6, w, 6))
            pygame.draw.rect(s, BLACK, (0, y0, w, h), 2)
            for i in range(0, w, 26):
                pygame.draw.circle(s, (120, 80, 30), (8 + i, y0 + 6), 2)
            pygame.draw.line(s, (90, 90, 100), (8, y0), (8, y0 - 46), 2)
            pygame.draw.line(s, (90, 90, 100), (w - 8, y0), (w - 8, y0 - 46), 2)
            if self.night:
                citydraw.darken(s, (150, 160, 215))
            self._spr[key] = s
        return s

    def enemy_spr(self, leg, face):
        key = ("e", leg, face)
        s = self._spr.get(key)
        if s is None:
            s = self._new_sprite(44, 54)
            x, y = 4, 8
            pygame.draw.rect(s, (35, 35, 45), (x + 5, y + 30, 9, 8 + leg))
            pygame.draw.rect(s, (35, 35, 45), (x + 20, y + 30, 9, 8 - leg))
            pygame.draw.rect(s, (240, 110, 45), (x + 3, y + 14, 28, 18))
            pygame.draw.rect(s, (255, 215, 70), (x + 14, y + 14, 6, 18))
            pygame.draw.rect(s, (238, 182, 140), (x + 6, y + 2, 22, 15))
            pygame.draw.rect(s, RED, (x + 4, y - 4, 26, 9))
            pygame.draw.rect(s, (190, 40, 55), (x + 1, y + 3, 32, 4))
            pygame.draw.line(s, BLACK, (x + 9, y + 9), (x + 14, y + 12), 2)
            pygame.draw.line(s, BLACK, (x + 25, y + 9), (x + 20, y + 12), 2)
            pygame.draw.rect(s, (90, 60, 40), (x + 11, y + 15, 12, 3))
            eye_x = 3 * face
            pygame.draw.circle(s, BLACK, (x + 12 + eye_x, y + 12), 2)
            pygame.draw.circle(s, BLACK, (x + 22 + eye_x, y + 12), 2)
            self._spr[key] = s
        return s

    def player_spr(self, f, leg, bob, skin=0):
        key = ("p", f, leg, bob, skin)
        s = self._spr.get(key)
        if s is None and skin:
            s = self._new_sprite(36, 64)
            skins.draw(s, skin, "walk", f, leg, bob)
            self._spr[key] = s
        elif s is None:
            s = self._new_sprite(36, 64)
            x, y = 4, 10
            pygame.draw.rect(s, (38, 72, 165), (x + 5, y + 28 + bob, 8, 11 - leg))
            pygame.draw.rect(s, (38, 72, 165), (x + 16, y + 28 + bob, 8, 11 + leg))
            pygame.draw.rect(s, (30, 30, 36), (x + 3, y + 39 + bob - max(0, -leg), 11, 4))
            pygame.draw.rect(s, (30, 30, 36), (x + 15, y + 39 + bob - max(0, leg), 11, 4))
            pygame.draw.rect(s, (38, 92, 205), (x + 4, y + 16 + bob, 20, 14))
            pygame.draw.rect(s, ORANGE, (x + 4, y + 13 + bob, 20, 7))
            pygame.draw.rect(s, YELLOW, (x + 12, y + 19 + bob, 4, 6))
            arm_y = y + 15 + bob + leg
            if f > 0:
                pygame.draw.rect(s, (238, 182, 140), (x + 21, arm_y, 6, 11))
                pygame.draw.rect(s, (238, 182, 140), (x + 1, arm_y + 3, 6, 10))
            else:
                pygame.draw.rect(s, (238, 182, 140), (x + 1, arm_y, 6, 11))
                pygame.draw.rect(s, (238, 182, 140), (x + 21, arm_y + 3, 6, 10))
            pygame.draw.rect(s, (242, 190, 145), (x + 5, y + 2 + bob, 18, 13))
            eye_x = x + (17 if f > 0 else 8)
            pygame.draw.circle(s, BLACK, (eye_x, y + 9 + bob), 2)
            pygame.draw.rect(s, BLACK, (x + (13 if f > 0 else 7), y + 12 + bob, 6, 2))
            pygame.draw.rect(s, YELLOW, (x + 3, y - 3 + bob, 22, 9))
            pygame.draw.rect(s, (232, 178, 38), (x, y + 4 + bob, 28, 4))
            pygame.draw.rect(s, (255, 226, 110), (x + 11, y - 6 + bob, 6, 5))
            self._spr[key] = s
        return s

    def pigeon_spr(self, frame, face):
        key = ("pg", frame, face)
        s = self._spr.get(key)
        if s is None:
            s = self._new_sprite(46, 36)
            grey, dark, light = (150, 156, 172), (104, 110, 128), (196, 202, 214)
            sit = frame >= 3
            by = 12 if sit else 10
            pygame.draw.polygon(s, dark, [(4, by + 4), (14, by + 2), (14, by + 12), (2, by + 10)])
            pygame.draw.ellipse(s, grey, (9, by, 26, 17))
            pygame.draw.ellipse(s, light, (14, by + 8, 16, 8))
            pygame.draw.circle(s, grey, (35, by + 2), 7)
            pygame.draw.rect(s, (88, 170, 150), (29, by + 5, 8, 4))
            pygame.draw.polygon(s, (255, 190, 70), [(41, by + 1), (46, by + 3), (41, by + 5)])
            pygame.draw.circle(s, (255, 130, 40), (37, by), 2)
            pygame.draw.circle(s, BLACK, (37, by), 1)
            if sit:
                pygame.draw.ellipse(s, dark, (12, by + 2, 18, 11))
                pygame.draw.line(s, (240, 120, 130), (20, by + 16), (20, by + 21), 2)
                pygame.draw.line(s, (240, 120, 130), (26, by + 16), (26, by + 21), 2)
                if frame == 4:
                    pygame.draw.circle(s, WHITE, (35, by - 6), 1)
            else:
                wy = {0: -11, 1: -3, 2: 7}[frame % 3]
                pygame.draw.polygon(s, dark, [(14, by + 4), (28, by + 4), (24, by + wy), (10, by + wy + 2)])
                pygame.draw.polygon(s, (120, 126, 144), [(18, by + 4), (28, by + 4), (26, by + wy + 3)])
            pygame.draw.ellipse(s, BLACK, (9, by, 26, 17), 1)
            if face < 0:
                f = pygame.transform.flip(s, True, False)
                f.set_colorkey(KEY, pygame.RLEACCEL)
                s = f
            self._spr[key] = s
        return s

    def player_climb_spr(self, f, skin=0):
        key = ("pc", f, skin)
        s = self._spr.get(key)
        if s is None and skin:
            s = self._new_sprite(36, 64)
            skins.draw(s, skin, "climb", f, 0, 0)
            self._spr[key] = s
        elif s is None:
            s = self._new_sprite(36, 64)
            x, y = 4, 10
            lg = 2 if f else -2
            pygame.draw.rect(s, (38, 72, 165), (x + 5, y + 28, 8, 11 - lg))
            pygame.draw.rect(s, (38, 72, 165), (x + 16, y + 28, 8, 11 + lg))
            pygame.draw.rect(s, (30, 30, 36), (x + 3, y + 39 - max(0, -lg), 11, 4))
            pygame.draw.rect(s, (30, 30, 36), (x + 15, y + 39 - max(0, lg), 11, 4))
            pygame.draw.rect(s, (38, 92, 205), (x + 4, y + 16, 20, 14))
            pygame.draw.rect(s, ORANGE, (x + 4, y + 13, 20, 7))
            ay = 2 if f else 8
            pygame.draw.rect(s, (238, 182, 140), (x + 0, y + ay, 6, 14))
            pygame.draw.rect(s, (238, 182, 140), (x + 22, y + 10 - ay + 2, 6, 14))
            pygame.draw.rect(s, (242, 190, 145), (x + 5, y + 2, 18, 13))
            pygame.draw.rect(s, YELLOW, (x + 3, y - 3, 22, 9))
            pygame.draw.rect(s, (232, 178, 38), (x, y + 4, 28, 4))
            pygame.draw.rect(s, (255, 226, 110), (x + 11, y - 6, 6, 5))
            self._spr[key] = s
        return s

    # ---------- экран, масштаб, раскладка кнопок ----------
    def sync_window(self):
        surf = pygame.display.get_surface()
        if surf is not None and (surf is not self.window or surf.get_size() != self.win_size):
            self.window = surf
            self.layout()

    def layout(self):
        W, H = self.window.get_size()
        self.win_size = (W, H)
        if self.auto_width:
            want = choose_logical_width(W, H)
            if want != self.W:
                self.set_logical_width(want)
        LW = self.W
        sc = min(W / LW, H / SCREEN_H)
        vw, vh = max(1, int(LW * sc)), max(1, int(SCREEN_H * sc))
        self.view = pygame.Rect((W - vw) // 2, (H - vh) // 2, vw, vh)
        self.view_sx = vw / LW
        self.view_sy = vh / SCREEN_H
        v = self.view
        self.bars = []
        if v.left > 0:
            self.bars += [pygame.Rect(0, 0, v.left, H), pygame.Rect(v.right, 0, W - v.right, H)]
        if v.top > 0:
            self.bars += [pygame.Rect(0, 0, W, v.top), pygame.Rect(0, v.bottom, W, H - v.bottom)]
        self.window.fill(BAR_COLOR)
        # если масштаб 1:1 — рисуем сразу на экран, без промежуточного холста и растяжения
        self.direct = (vw, vh) == (LW, SCREEN_H)
        self.view_surf = None
        if self.direct:
            try:
                self.screen = self.window.subsurface(self.view)
            except ValueError:
                self.direct = False
        if not self.direct:
            self.screen = pygame.Surface((LW, SCREEN_H)).convert()
            try:
                self.view_surf = self.window.subsurface(self.view)
            except ValueError:
                self.view_surf = None
        self.build_controls(W, H)
        self.dirty = True

    def to_logical(self, x, y):
        return (x - self.view.x) / self.view_sx, (y - self.view.y) / self.view_sy

    def to_screen(self, lx, ly):
        return self.view.x + lx * self.view_sx, self.view.y + ly * self.view_sy

    def build_controls(self, W, H):
        u = min(H, W * 0.5625)          # базовая единица: размер кнопок от экрана
        mx = 0.07 * u                   # отступ от краёв (запас под вырезы экрана)
        bottom = H - 0.075 * u
        bw = 0.23 * u                   # сторона кнопки ◀ ▶
        gap = 0.04 * u
        top = bottom - bw
        lx, rx = mx, mx + bw + gap
        mid = lx + bw + gap / 2
        zone_top = top - 0.10 * u       # зона нажатия шире и выше самой кнопки
        left_hit = pygame.Rect(0, int(zone_top), int(mid), int(H - zone_top))
        right_hit = pygame.Rect(int(mid), int(zone_top), int(rx + bw + 0.07 * u - mid), int(H - zone_top))

        rj = 0.155 * u                  # ПРЫЖОК
        jcx, jcy = W - mx - rj, bottom - rj
        rr = 0.10 * u                   # БЕГ — выше-левее прыжка, зоны не пересекаются
        rcx, rcy = jcx - 0.25 * u, jcy - 0.215 * u

        x0, y0 = self.to_screen(self.pause_rect.x, self.pause_rect.y)
        pr = pygame.Rect(int(x0), int(y0), int(self.pause_rect.w * self.view_sx),
                         int(self.pause_rect.h * self.view_sy))
        pause_hit = pr.inflate(int(pr.w * 0.6), int(pr.h * 0.6))

        self.controls = {
            "left": Control("left", "rect", pygame.Rect(int(lx), int(top), int(bw), int(bw)), left_hit, dpad=True),
            "right": Control("right", "rect", pygame.Rect(int(rx), int(top), int(bw), int(bw)), right_hit, dpad=True),
            "jump": Control("jump", "circle", (jcx, jcy, rj), rj * 1.2),
            "run": Control("run", "circle", (rcx, rcy, rr), rr * 1.25),
            "pause": Control("pause", "rect", pr, pause_hit),
        }
        if self.mode in ("gen", "battle"):          # лестницы: ▲ / ▼ столбиком справа от ◀▶
            sw = 0.15 * u
            ux = rx + bw + 0.10 * u
            dn = pygame.Rect(int(ux), int(bottom - sw), int(sw), int(sw))
            up = pygame.Rect(int(ux), int(bottom - 2 * sw - 0.03 * u), int(sw), int(sw))
            midy = (up.bottom + dn.top) // 2
            pad = int(0.025 * u)
            up_hit = pygame.Rect(up.left - pad, up.top - int(0.05 * u), up.w + 2 * pad, midy - up.top + int(0.05 * u))
            dn_hit = pygame.Rect(dn.left - pad, midy, dn.w + 2 * pad, int(H - midy))
            self.controls["up"] = Control("up", "rect", up, up_hit)
            self.controls["down"] = Control("down", "rect", dn, dn_hit)
        if self.mode == "battle":                   # ГРАНАТА: слева-снизу от кнопки прыжка
            rg = 0.115 * u
            self.controls["grenade"] = Control("grenade", "circle", (jcx - 0.36 * u, jcy + 0.045 * u, rg), rg * 1.2)
        side = int(bw)
        self.ctl_imgs = {
            "left": (self._btn_img(side, "rect", "left", False), self._btn_img(side, "rect", "left", True)),
            "right": (self._btn_img(side, "rect", "right", False), self._btn_img(side, "rect", "right", True)),
            "jump": (self._btn_img(int(rj * 2), "circle", "jump", False), self._btn_img(int(rj * 2), "circle", "jump", True)),
            "run": (self._btn_img(int(rr * 2), "circle", "run", False), self._btn_img(int(rr * 2), "circle", "run", True)),
        }
        if self.mode in ("gen", "battle"):
            sws = int(0.15 * u)
            self.ctl_imgs["up"] = (self._btn_img(sws, "rect", "up", False), self._btn_img(sws, "rect", "up", True))
            self.ctl_imgs["down"] = (self._btn_img(sws, "rect", "down", False), self._btn_img(sws, "rect", "down", True))
        if self.mode == "battle":
            sg = int(0.23 * u)
            self.ctl_imgs["grenade"] = (self._btn_img(sg, "circle", "grenade", False),
                                        self._btn_img(sg, "circle", "grenade", True))

    def _btn_img(self, size, shape, icon, hot):
        w = h = size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if icon == "run":
            fill = (65, 205, 105, 175) if hot else (255, 255, 255, 70)
        else:
            fill = (255, 204, 64, 170) if hot else (255, 255, 255, 70)
        edge = (255, 255, 255, 200)
        lw = max(2, w // 36)
        if shape == "circle":
            pygame.draw.circle(surf, fill, (w // 2, h // 2), w // 2)
            pygame.draw.circle(surf, edge, (w // 2, h // 2), w // 2, lw)
        else:
            rad = w // 6
            pygame.draw.rect(surf, fill, (0, 0, w, h), border_radius=rad)
            pygame.draw.rect(surf, edge, (0, 0, w, h), lw, border_radius=rad)
        ic = (255, 255, 255, 240)
        if icon == "left":
            pygame.draw.polygon(surf, ic, [(w * 0.62, h * 0.27), (w * 0.62, h * 0.73), (w * 0.28, h * 0.5)])
        elif icon == "right":
            pygame.draw.polygon(surf, ic, [(w * 0.38, h * 0.27), (w * 0.38, h * 0.73), (w * 0.72, h * 0.5)])
        elif icon == "up":
            pygame.draw.polygon(surf, ic, [(w * 0.27, h * 0.66), (w * 0.73, h * 0.66), (w * 0.5, h * 0.3)])
        elif icon == "down":
            pygame.draw.polygon(surf, ic, [(w * 0.27, h * 0.34), (w * 0.73, h * 0.34), (w * 0.5, h * 0.7)])
        elif icon == "jump":
            pygame.draw.polygon(surf, ic, [(w * 0.5, h * 0.22), (w * 0.76, h * 0.52), (w * 0.24, h * 0.52)])
            pygame.draw.rect(surf, ic, (w * 0.41, h * 0.5, w * 0.18, h * 0.28))
        elif icon == "grenade":
            pygame.draw.circle(surf, ic, (int(w * 0.5), int(h * 0.58)), int(w * 0.25))
            pygame.draw.circle(surf, (0, 0, 0, 120), (int(w * 0.5), int(h * 0.58)), int(w * 0.25), max(2, w // 30))
            pygame.draw.rect(surf, ic, (int(w * 0.42), int(h * 0.2), int(w * 0.16), int(h * 0.14)))
            pygame.draw.line(surf, ic, (int(w * 0.58), int(h * 0.22)), (int(w * 0.72), int(h * 0.12)), max(2, w // 22))
        elif icon == "run":
            img = self.font(max(12, int(w * 0.34)), True).render("БЕГ", True, (255, 255, 255))
            surf.blit(img, img.get_rect(center=(w // 2, h // 2)))
        return surf.convert_alpha()

    def toggle_fullscreen(self):
        if IS_ANDROID:
            return
        self.fullscreen = not self.fullscreen
        lw = self.W
        if self.fullscreen:
            try:
                dw, dh = pygame.display.get_desktop_sizes()[0]
                lw = choose_logical_width(dw, dh)
            except Exception:
                pass
        window, scaled = open_window(self.fullscreen, lw)
        self.gpu_scaled = scaled
        self.auto_width = not scaled
        if scaled and lw != self.W:
            self.set_logical_width(lw)
        self.window = window
        self.fingers.clear()
        self.finger_btn.clear()
        self.ui_press.clear()
        self.layout()

    # ---------- состояние ----------
    @staticmethod
    def _index(rects):
        """Колонка тайлов -> номера прямоугольников, которые её пересекают (быстрый поиск рядом с игроком)."""
        idx = {}
        for i, r in enumerate(rects):
            for c in range(r.left // TILE, (r.right - 1) // TILE + 1):
                idx.setdefault(c, []).append(i)
        return idx

    def setup_level(self, L):
        """Переключает игру на уровень L: геометрия, индексы столкновений, кэши картинок."""
        self.lvl = L
        self.mode = L.mode
        self.night = (L.mode in ("battle", "lobby"))
        self.world_w, self.world_h = L.world_w, L.world_h
        self.ground_y = L.ground_y
        self.zone_x = L.zone_tx * TILE
        self.solids = [tile_rect(tx, ty, tw, th) for (tx, ty, tw, th, *_r) in L.solids]
        self.spikes = [pygame.Rect(sx * TILE + 3, sy * TILE - 14, TILE - 6, 14) for (sx, sy) in L.spikes]
        self.oneways = [pygame.Rect(tx * TILE, ty * TILE, tw * TILE, 12) for (tx, ty, tw, *_r) in L.oneway]
        self.ladders = [Ladder(tx, t0, t1) for (tx, t0, t1, *_r) in L.ladders]
        self.checkpoints = [(tx * TILE, L.ground_y) for tx in L.checkpoints]
        self.sol_idx = self._index(self.solids)
        self.ow_idx = self._index(self.oneways)
        self.n_static = len(self.solids)
        self.cam_max_y = max(0, self.world_h - SCREEN_H)
        self.dist_idx = -1
        self.build_static_caches()

    def near_solids(self, rect):
        c0, c1 = (rect.left - TILE) // TILE, (rect.right + TILE) // TILE
        got = set()
        for c in range(c0, c1 + 1):
            lst = self.sol_idx.get(c)
            if lst:
                got.update(lst)
        sol = self.solids
        return [sol[i] for i in sorted(got)]

    def near_oneways(self, rect):
        if not self.oneways:
            return ()
        c0, c1 = (rect.left - TILE) // TILE, (rect.right + TILE) // TILE
        got = set()
        for c in range(c0, c1 + 1):
            lst = self.ow_idx.get(c)
            if lst:
                got.update(lst)
        ow = self.oneways
        return [ow[i] for i in sorted(got)]

    def los(self, x0, y0, x1, y1):
        """Есть ли прямая видимость между двумя точками (без твёрдых блоков на пути)."""
        n = int(math.hypot(x1 - x0, y1 - y0) // 14) + 1
        r = pygame.Rect(0, 0, 10, 10)
        for i in range(1, n):
            k = i / n
            r.center = (int(x0 + (x1 - x0) * k), int(y0 + (y1 - y0) * k))
            if self.solid_hit(r):
                return False
        return True

    def solid_hit(self, rect):
        for s in self.near_solids(rect):
            if rect.colliderect(s):
                return True
        return False

    def reset_game(self):
        L = self.lvl
        self.platforms = [MovingPlatform(*d) for d in L.moving]
        self.plat_rects = [mp.rect for mp in self.platforms]
        self.enemies = [Enemy(*d) for d in L.foremen]
        self.pickups = ([Pickup("brick", x, y) for x, y in L.bricks] +
                        [Pickup("bolt", x, y) for x, y in L.bolts] +
                        [Pickup("heart", x, y) for x, y in L.hearts])
        self.pigeons = [Pigeon(sp) for sp in L.pigeons]
        hpm = 2 if self.role is not None else 1          # кооператив: здоровье врагов удвоено
        for obj in chain(self.enemies, self.pigeons):
            obj.hp = obj.max_hp = hpm
        self.poops = []
        self.make_players(int(L.spawn[0] * TILE), int(L.spawn[1] * TILE))
        self.spawn_point = pygame.Vector2(self.player.rect.x, self.player.rect.y)
        self.checkpoints_hit = set()
        self.particles = []
        self.floaters = []
        self.fireworks = []
        self.camera_x = -float(CAM_PAD)
        self.camera_y = float(self.cam_max_y)
        self.cy = int(self.camera_y)
        self.dist_idx = -1
        self.elapsed = 0.0
        self.score = 0
        self.bolts = 0
        self.bricks_collected = 0
        self.built_at = {}
        self.shake = 0.0
        self.win_timer = 0.0
        self.firework_timer = 0.0
        self.flash_text = ""
        self.flash_timer = 0.0
        self.run_on = False
        self.safe = False
        self.shake_amp = 5.0
        self.battle = battle.Battle(self) if self.mode == "battle" else None
        self.pk_dirty = True
        self.sup_dirty = True
        self.fx_out = []
        self.net_shake = self.net_amp = 0.0

    def make_players(self, sx, sy):
        """Одиночная игра — один герой. Кооператив — все из списка roster, рядом друг с другом."""
        self.players = {}
        if self.role is None or not self.roster:
            self.player = Player(sx, sy)
            self.players[0] = self.player
            self.my_pid = 0
            return
        n = len(self.roster)
        for i, r in enumerate(self.roster):
            me = r["pid"] == self.my_pid
            q = Player(sx + 34 * i, sy, r["pid"], r["nick"], r["skin"], remote=not me)
            if not me:
                q.invuln = 99.0                  # пока устройство игрока не загрузило уровень, его герой неуязвим
            self.players[r["pid"]] = q
            if me:
                self.player = q
        if getattr(self, "player", None) is None or self.my_pid not in self.players:
            self.player = Player(sx, sy)
            self.players[self.my_pid] = self.player

    def start_level(self, mode, seed=None):
        """Загрузка карты: классическая, свежесгенерированная или «Битва за Писюн»."""
        if mode == "battle":
            if self._battle_lvl is None:
                self._battle_lvl = battlemap.build_battle_level()
            L = self._battle_lvl
            if self.bjobs is None:
                self.bjobs = battle.build_battle_sounds(self)
        elif mode == "gen":
            if seed is None:
                seed = random.randrange(1, 1000000)
            try:
                L = levelgen.generate(seed)
            except Exception:                       # крайне маловероятно: откат на классику
                L, mode = self.classic, "classic"
            else:
                self.seed = seed
        else:
            L = self.classic
        if L is not self.lvl:
            self.setup_level(L)
        self.reset_game()
        self.build_controls(*self.win_size)
        self.set_state("play")

    def process_pending(self):
        pend, self.pending = self.pending, None
        if pend is not None and pend[0] == "coop":
            self.coop_start_level(pend[1], pend[2])
        elif pend is not None:
            self.start_level(*pend)
        elif self.state == "loading":
            self.set_state("menu")

    def set_state(self, state):
        self.state = state
        self.ui_buttons = []
        self.snap = None
        self.dirty = True
        for k in self.finger_btn:
            self.finger_btn[k] = None
        for k in self.ui_press:
            self.ui_press[k] = None
        if self.battle is not None:
            self.battle.on_state(state)
        if self.role == "host":
            self.coop_state_changed(state)

    @staticmethod
    def build_order():
        cells = []
        for r, row in enumerate(BUILD_SHAPE):
            for c, ch in enumerate(row):
                if ch == "X":
                    cells.append((r, c))
        cells.sort(key=lambda rc: (-rc[0], rc[1]))
        return cells

    def build_origin(self):
        cell = 36 if self.mode == "battle" else 30
        w = len(BUILD_SHAPE[0]) * cell
        cx = self.zone_x + TILE * 6.2
        x = int(cx - w // 2)
        y = int(self.ground_y - len(BUILD_SHAPE) * cell)
        return x, y, cell

    # ---------- ввод: события касаний ----------
    def handle_events(self):
        for e in pygame.event.get():
            t = e.type
            if t == pygame.QUIT:
                self.running = False
            elif t == pygame.FINGERDOWN:
                W, H = self.win_size
                self.touch_down(e.finger_id, e.x * W, e.y * H)
            elif t == pygame.FINGERMOTION:
                W, H = self.win_size
                self.touch_move(e.finger_id, e.x * W, e.y * H)
            elif t == pygame.FINGERUP:
                W, H = self.win_size
                self.touch_up(e.finger_id, e.x * W, e.y * H)
            elif t == pygame.MOUSEBUTTONDOWN:      # мышь — для проверки на компьютере
                if e.button == 1 and not getattr(e, "touch", False):
                    self.touch_down("mouse", *e.pos)
            elif t == pygame.MOUSEMOTION:
                if e.buttons[0] and not getattr(e, "touch", False) and "mouse" in self.fingers:
                    self.touch_move("mouse", *e.pos)
            elif t == pygame.MOUSEBUTTONUP:
                if e.button == 1 and not getattr(e, "touch", False) and "mouse" in self.fingers:
                    self.touch_up("mouse", *e.pos)
            elif t == pygame.KEYDOWN:
                if self.kb is not None:
                    self.kb_keydown(e)
                elif e.key in BACK_KEYS or (e.key == pygame.K_p and self.state in ("play", "pause")):
                    self.on_back()
                elif e.key == pygame.K_F11 and not IS_ANDROID:
                    self.toggle_fullscreen()
                else:
                    self.key_control(e.key, True)
            elif t == pygame.KEYUP:
                self.key_control(e.key, False)
            elif t == getattr(pygame, "TEXTINPUT", -1):
                if self.kb is not None:
                    self.kb_textinput(e.text)
            elif t in PAUSE_EVENTS:
                self.on_background()
            elif t in EXPOSE_EVENTS:
                self.dirty = True
            elif t in RESIZE_EVENTS:
                self.sync_window()

    def key_control(self, key, down):
        """Клавиатура на компьютере: каждая клавиша — «виртуальный палец» на экранной кнопке."""
        fid = "key:%d" % key
        if not down:
            if key in KEY_RUN:
                self.run_on = False
            name = self.finger_btn.pop(fid, None)
            if name:
                self.release(name)
            return
        if self.state != "play" or self.coop_menu or self.kb is not None or fid in self.finger_btn:
            return
        bt = self.battle
        if key in KEY_RUN:
            self.run_on = True
            self.finger_btn[fid] = None
            return
        if key in KEY_ACT or key == pygame.K_SPACE:
            if bt is not None:
                if key == pygame.K_SPACE:
                    if bt.touch(0, 0):                 # пробел листает реплики
                        return
                elif bt.touch(*self.to_screen(*bt.btn.center)):      # E / Enter: реплика или ПОСТРОИТЬ
                    return
            if key != pygame.K_SPACE:
                return
        name = KEY_BUTTONS.get(key)
        if name == "up" and self.mode != "gen":
            name = "jump"
        if name is None or (bt is not None and name in bt.hidden()):
            return
        self.finger_btn[fid] = name
        self.press(name)

    def on_back(self):
        if self.kb is not None:
            self.kb = None
            self.dirty = True
        elif self.state == "play":
            if self.role is not None:               # в кооперативе мир не останавливается
                self.coop_menu = not self.coop_menu
                self.dirty = True
            else:
                self.set_state("pause")
        elif self.state == "pause":
            self.set_state("play")
        elif self.state == "menu":
            self.running = False
        elif self.state in coop.COOP_UI_STATES:
            self.coop_back()
        elif self.role is not None:
            self.coop_leave()
        else:
            self.set_state("menu")

    def on_background(self):
        """Окно потеряло фокус / приложение свернули: пауза и сброс всех пальцев."""
        if self.state == "play" and self.role is None:
            self.set_state("pause")
        self.fingers.clear()
        self.finger_btn.clear()
        self.ui_press.clear()

    def held(self, name):
        return any(v == name for v in self.finger_btn.values())

    def control_at(self, x, y):
        ctl = self.controls
        for n in CONTROL_ORDER:
            c = ctl.get(n)
            if c is not None and c.contains(x, y):
                return n
        return None

    def dpad_at(self, x, y):
        for n in ("left", "right"):
            if self.controls[n].contains(x, y):
                return n
        return None

    def ui_action_at(self, x, y):
        lx, ly = self.to_logical(x, y)
        for rect, act in reversed(self.ui_buttons):
            if rect.inflate(10, 10).collidepoint(lx, ly):
                return act
        return None

    def ui_is_down(self, rect):
        for (x, y) in self.fingers.values():
            lx, ly = self.to_logical(x, y)
            if rect.collidepoint(lx, ly):
                return True
        return False

    def touch_down(self, fid, x, y):
        self.fingers[fid] = (x, y)
        if self.state == "play":
            if self.coop_menu or self.kb is not None or (self.role is not None and self.ui_action_at(x, y) is not None):
                self.finger_btn[fid] = None             # окно кооператива поверх игры: касание — в меню
                self.ui_press[fid] = self.ui_action_at(x, y)
                self.dirty = True
                return
            name = self.control_at(x, y)
            bt = self.battle
            if bt is not None and name != "pause":
                if bt.touch(x, y):                 # реплика героя / кнопка ПОСТРОИТЬ
                    self.finger_btn[fid] = None
                    return
                if name in bt.hidden():
                    name = None
            self.finger_btn[fid] = name
            if name:
                self.press(name)
        else:
            self.finger_btn[fid] = None
            self.ui_press[fid] = self.ui_action_at(x, y)
            self.dirty = True
            if self.state == "bwin" and self.battle is not None and 3.0 < self.battle.res_t < 7.5:
                self.battle.res_t = 7.6           # тап по итогам — показать всё сразу

    def touch_move(self, fid, x, y):
        self.fingers[fid] = (x, y)
        if self.state != "play":
            if fid in self.ui_press:
                self.dirty = True
            return
        if self.ui_press.get(fid) is not None:
            return
        old = self.finger_btn.get(fid)
        if old is None or self.controls[old].dpad:
            # крестовина: палец свободно скользит между ◀ и ▶
            new = self.dpad_at(x, y)
            if new is None and old is not None and self.controls[old].contains(x, y, 1.6):
                new = old                      # небольшой дрейф пальца не отпускает кнопку
            if new != old:
                self.finger_btn[fid] = new
                if old:
                    self.release(old)
                if new:
                    self.press(new)
        elif not self.controls[old].contains(x, y, 1.4):
            # палец, начавший на кнопке действия, ушёл далеко — отпускаем
            self.finger_btn[fid] = None
            self.release(old)

    def touch_up(self, fid, x, y):
        self.fingers.pop(fid, None)
        name = self.finger_btn.pop(fid, None)
        act = self.ui_press.pop(fid, None)
        if name:
            self.release(name)
        if self.state != "play":
            self.dirty = True
        if act is not None and self.ui_action_at(x, y) == act:
            self.do_action(act)

    def press(self, name):
        if name == "jump":
            self.player.jump_buffer = 0.13
        elif name == "run":
            self.run_on = not self.run_on
        elif name == "pause":
            if self.role is not None:
                self.coop_menu = True
                self.dirty = True
            else:
                self.set_state("pause")
        elif name == "grenade" and self.battle is not None:
            if self.role == "client":
                self.net_to_host({"t": "throw"})
            else:
                self.bc = self.role == "host"
                try:
                    self.battle.throw(self.player)
                finally:
                    self.bc = False

    def release(self, name):
        if name == "jump" and self.state == "play" and not self.held("jump"):
            if self.player.vel.y < -250:
                self.player.vel.y = -250       # короткий прыжок при отпускании

    def do_action(self, act):
        if self.coop_action(act):
            self.dirty = True
            return
        if act in ("start", "start_gen", "new_gen", "start_battle"):
            self.pending = ("classic" if act == "start" else "battle" if act == "start_battle" else "gen", None)
            self.set_state("loading")
        elif act in ("restart", "new_battle"):
            self.reset_game()
            self.set_state("play")
        elif act == "retry":                       # после поражения от босса — прямо в бой, без прохода карты
            if self.battle is not None and self.battle.can_retry():
                self.battle.retry_boss()
            else:
                self.reset_game()
            self.set_state("play")
        elif act == "help":
            self.set_state("help")
        elif act == "menu":
            self.set_state("menu")
        elif act == "resume":
            self.set_state("play")
        elif act == "sound":
            self.sound_on = not self.sound_on
        elif act == "fps":
            self.show_fps = not self.show_fps
        elif act == "fullscreen":
            self.toggle_fullscreen()
        self.dirty = True

    # ---------- игровой процесс ----------
    def local_hurt_fx(self, source_x, fx=True):
        """Удар по герою ЭТОГО устройства: отброс, неуязвимость, эффекты (fx=False — их уже прислал хост)."""
        p = self.player
        p.climb = None
        p.invuln = 1.4 if self.battle is None else 1.9
        self._shake = 0.30
        p.vel.x = -290 if p.rect.centerx < source_x else 290
        p.vel.y = -330
        if self.battle is not None:
            self.battle.hurt_fx()
        if fx:
            self.burst(p.rect.centerx, p.rect.centery, [RED, WHITE, ORANGE], 14, 240, 0.5)
            self.play("hurt")

    def damage_player(self, source_x, p=None):
        """Отнимает 1 HP. Возвращает True, если удар прошёл."""
        p = p or self.player
        if p.invuln > 0 or self.state != "play" or self.safe or p.dead or self.coop_lobby:
            return False
        p.hp -= 1
        p.invuln = 1.4 if self.battle is None else 1.9
        if self.battle is not None:
            self.battle.on_hurt(p)
        if p is self.player:
            self.local_hurt_fx(source_x)
        else:
            self.net_send(p.pid, {"t": "hurt", "sx": source_x})
            self.burst(p.rect.centerx, p.rect.centery, [RED, WHITE, ORANGE], 14, 240, 0.5)
            self.play("hurt")
        if p.hp <= 0:
            self.player_down(p)
        return True

    def player_down(self, p):
        """HP кончилось. Последний игрок — конец игры; иначе выбывает и возродится через несколько секунд."""
        p.hp = 0
        if not [q for q in self.players.values() if q is not p and not q.dead]:
            self.set_state("gameover")
            self.play("hurt")
            return
        p.dead = True
        p.respawn_t = coop.RESPAWN_TIME
        p.climb = None
        p.vel.update(0, 0)
        self.burst(p.rect.centerx, p.rect.centery, [RED, WHITE, ORANGE, PINK], 24, 300, 0.7)
        self.float_text(p.rect.centerx, p.rect.top - 14, (p.nick or "Игрок") + " выбыл!", RED)

    def bounce(self, q):
        """Отскок после прыжка на врага или на голову другого игрока."""
        q.vel.y = -400
        if q is not self.player:
            self.net_send(q.pid, {"t": "bounce"})

    def respawn_pos(self, q):
        bt = self.battle
        if bt is not None and bt.phase in ("boss", "dying"):
            bx, by, cell = self._bo
            return int(bx - 260 + 24 * (q.pid % 4)), int(self.ground_y - q.rect.h)
        sp = self.spawn_point
        return int(sp.x) + 20 * (q.pid % 4), int(sp.y)

    def teleport(self, q, x, y, inv, fx=True):
        q.climb = None
        q.rect.topleft = (x, y)
        q.vel.update(0, 0)
        q.invuln = inv
        q.epoch += 1
        q.dx, q.dy = float(x), float(y)
        if q is not self.player:
            self.net_send(q.pid, {"t": "respawn", "x": x, "y": y, "e": q.epoch, "inv": inv, "fx": 1 if fx else 0})

    def revive(self, q, hp=3):
        x, y = self.respawn_pos(q)
        q.dead = False
        q.hp = hp
        self.teleport(q, x, y, 2.5)
        self.burst(q.rect.centerx, q.rect.centery, [WHITE, GREEN, YELLOW], 20, 260, 0.7)
        self.float_text(q.rect.centerx, q.rect.top - 14, (q.nick or "Игрок") + " вернулся!", GREEN)
        self.play("heart")

    def respawn_at_checkpoint(self, p=None):
        p = p or self.player
        if self.role is None:
            self.poops = []
        p.hp -= 1
        if p is self.player:
            self._shake = 0.3
        if p.hp <= 0:
            self.player_down(p)
            self.play("hurt")
            return
        self.teleport(p, int(self.spawn_point.x), int(self.spawn_point.y), 2.0, fx=False)
        self.play("hurt")
        self.float_text(p.rect.centerx, p.rect.top - 10, "Ай! -1 HP", RED)

    def collect(self, pk, p=None):
        """Игрок p подобрал предмет. True — предмет забран."""
        p = p or self.player
        cx, cy = pk.rect.center
        bt = self.battle
        if pk.kind == "brick" and bt is not None:
            self.bricks_collected += 1
            bt.on_brick(cx, cy)
        elif pk.kind == "grenade":
            if bt is None or not bt.add_grenades(p, 2, cx, cy):
                return False
        elif pk.kind == "medkit":
            if bt is None or not bt.on_medkit(p, cx, cy):
                return False
        elif pk.kind == "brick":
            self.bricks_collected += 1
            order = self.build_order()
            cell_rc = order[self.bricks_collected - 1]
            self.built_at[cell_rc] = self.elapsed
            self.score += 100
            self.burst(cx, cy, [YELLOW, ORANGE, (255, 230, 150)], 18, 250, 0.6)
            self.play("collect")
            if self.bricks_collected >= BUILD_CELLS_TOTAL:
                self.float_text(cx, cy - 18, "ВСЕ КИРПИЧИ СОБРАНЫ! ИДИ К СТРОЙКЕ >>", GREEN)
                self.flash_msg("МОНУМЕНТ ГОТОВ! БЕГИ НА СТРОЙКУ >>", 3.0)
            else:
                self.float_text(cx, cy - 18, f"+1 блок к писюну ({self.bricks_collected}/{BUILD_CELLS_TOTAL})")
        elif pk.kind == "bolt":
            self.bolts += 1
            self.score += 50
            self.burst(cx, cy, [(210, 220, 235), YELLOW], 10, 180, 0.45, 4)
            self.float_text(cx, cy - 16, "+гайка", (210, 225, 255))
            self.play("bolt")
        elif pk.kind == "heart":
            if p.hp >= 5:
                return False
            p.hp = min(5, p.hp + 1)
            self.score += 30
            self.burst(cx, cy, [PINK, RED, WHITE], 14, 200, 0.55)
            self.float_text(cx, cy - 16, "+1 HP", PINK)
            self.play("heart")
        return True

    def move_player(self, dt):
        p = self.player
        # --- прыжки
        p.jump_buffer = max(0, p.jump_buffer - dt)
        p.coyote = max(0, p.coyote - dt)
        if p.on_ground:
            p.coyote = 0.11
            p.jumps_used = 0
        if p.jump_buffer > 0:
            if p.on_ground or p.coyote > 0:
                p.vel.y = -JUMP_VEL
                p.jumps_used = 1
                p.jump_buffer = 0
                p.on_ground = False
                self.play("jump")
                self.burst(p.rect.centerx, p.rect.bottom, [WHITE, (200, 220, 255)], 6, 120, 0.3, 3)
            elif p.jumps_used < 2:
                p.vel.y = -JUMP_VEL * 0.88
                p.jumps_used = 2
                p.jump_buffer = 0
                self.play("double")
                self.burst(p.rect.centerx, p.rect.bottom, [YELLOW, WHITE], 12, 170, 0.4, 4, 0)

        # --- гравитация
        p.vel.y = min(950, p.vel.y + GRAVITY * dt)
        p.invuln = max(0, p.invuln - dt)

        near = self.near_solids(p.rect)
        near_ow = self.near_oneways(p.rect)
        plats = self.plat_rects
        nn = len(near)

        p.rect.x += int(p.vel.x * dt)
        for i, s in enumerate(chain(near, plats)):
            if p.rect.colliderect(s):
                if i >= nn and (p.standing_on is self.platforms[i - nn]
                                or min(p.rect.bottom, s.bottom) - max(p.rect.top, s.top) <= 6):
                    continue           # платформа тонкая: касание верхом/низом — это не боковой удар
                if p.vel.x > 0:
                    p.rect.right = s.left
                elif p.vel.x < 0:
                    p.rect.left = s.right

        was_ground = p.on_ground
        p.on_ground = False
        p.standing_on = None
        old_bottom = p.rect.bottom
        p.rect.y += int(p.vel.y * dt)
        pl_h = p.rect.h
        for i, s in enumerate(chain(near, plats)):
            if p.rect.colliderect(s):
                if i >= nn:                # движущаяся платформа: садимся только сверху, бьёмся головой только снизу
                    if p.vel.y > 0 and old_bottom > s.top + 8:
                        continue
                    if p.vel.y < 0 and old_bottom - pl_h < s.bottom - 8:
                        continue
                if p.vel.y > 0:
                    p.rect.bottom = s.top
                    p.vel.y = 0
                    p.on_ground = True
                    if i >= nn:
                        p.standing_on = self.platforms[i - nn]
                elif p.vel.y < 0:
                    p.rect.top = s.bottom
                    p.vel.y = 0
        p.on_oneway = False
        if near_ow and p.vel.y >= 0 and p.drop <= 0:
            for o in near_ow:
                if p.rect.colliderect(o) and old_bottom <= o.top + 1:
                    p.rect.bottom = o.top
                    p.vel.y = 0
                    p.on_ground = True
                    p.on_oneway = True
                    break
        if p.on_ground and not was_ground:
            self.burst(p.rect.centerx, p.rect.bottom, [(200, 190, 170)], 5, 90, 0.25, 3)

        p.rect.x = clamp(p.rect.x, 0, self.world_w - p.rect.w)

    def try_grab(self, p, climb_in):
        for ld in self.ladders:
            if ld.grab.colliderect(p.rect) and abs(p.rect.centerx - ld.cx) < 18:
                if climb_in > 0 and p.rect.bottom >= ld.bottom_y - 1:
                    continue
                if climb_in < 0 and p.rect.bottom <= ld.top_y + 1:
                    continue
                return ld
        return None

    def update_climb(self, dt, axis, climb_in):
        """Лазание по лестнице. Возвращает True, если игрок остался на лестнице (обычная физика пропускается)."""
        p = self.player
        if p.climb is None and climb_in != 0:
            ld = self.try_grab(p, climb_in)
            if ld is not None:
                p.climb = ld
                p.vel.update(0, 0)
                p.on_ground = False
                p.standing_on = None
                p.jumps_used = 0
                p.cy_acc = 0.0
        ld = p.climb
        if ld is None:
            return False
        if p.jump_buffer > 0:                      # прыжок с лестницы
            p.climb = None
            p.jump_buffer = 0
            p.vel.y = -JUMP_VEL * 0.85
            p.jumps_used = 1
            self.play("jump")
            return False
        if axis != 0 and climb_in == 0:            # шаг в сторону — сошли
            p.climb = None
            return False
        dxs = ld.cx - p.rect.centerx
        p.rect.x += int(clamp(dxs, -8, 8))
        p.vel.update(0, 0)
        p.coyote = 0
        p.cy_acc += climb_in * CLIMB_SPEED * dt
        step = int(p.cy_acc)
        p.cy_acc -= step
        p.rect.y += step
        p.anim += abs(climb_in) * dt * 9
        if p.rect.bottom <= ld.top_y:              # долезли до верха
            p.rect.bottom = ld.top_y
            p.climb = None
            p.on_ground = True
            p.vel.y = 0
            return False
        if p.rect.bottom >= ld.bottom_y:           # спустились до низа
            p.rect.bottom = ld.bottom_y
            p.climb = None
            p.on_ground = True
            p.vel.y = 0
            return False
        p.invuln = max(0, p.invuln - dt)
        return True

    def update_poops(self, dt):
        alive = [q for q in self.players.values() if not q.dead]
        keep = []
        for po in self.poops:
            po[2] += 900.0 * dt
            po[1] += po[2] * dt
            r = pygame.Rect(int(po[0]) - 4, int(po[1]) - 5, 8, 10)
            hit = False
            if self.state == "play":
                for q in alive:
                    if not q.dead and r.colliderect(q.rect):
                        self.damage_player(po[0], q)
                        hit = True
                        break
            if not hit:
                if po[1] > self.world_h or self.solid_hit(r):
                    hit = True
                else:
                    for o in self.near_oneways(r):
                        if r.colliderect(o):
                            hit = True
                            break
            if hit:
                self.burst(po[0], po[1], [(240, 240, 236), (150, 190, 150)], 7, 120, 0.35, 4, 500)
            else:
                keep.append(po)
        self.poops = keep

    # ---------- ввод и физика героя ЭТОГО устройства ----------
    def local_input_step(self, dt):
        p = self.player
        if p.dead:
            p.vel.update(0, 0)
            return
        if p.standing_on is not None:
            p.rect.x += int(p.standing_on.dx)
            p.rect.y += int(p.standing_on.dy)
        bt = self.battle
        lk = bt is not None and bt.locked          # катсцены и реплики: герой не слушается
        axis = 0 if lk else (1 if self.held("right") else 0) - (1 if self.held("left") else 0)
        speed = RUN_SPEED if self.run_on else MOVE_SPEED
        p.vel.x = axis * speed
        if axis:
            p.facing = axis
            p.anim += dt * (11 if self.run_on else 8)
        else:
            p.anim = 0
        climb_in = 0 if lk else (1 if self.held("down") else 0) - (1 if self.held("up") else 0)
        p.drop = max(0.0, p.drop - dt)
        if (climb_in > 0 and p.on_oneway and p.climb is None and p.on_ground
                and self.try_grab(p, climb_in) is None):
            p.drop = 0.3
            p.on_ground = False
            p.on_oneway = False
            p.coyote = 0
        if not self.update_climb(dt, axis, climb_in):
            self.move_player(dt)

    def smooth_players(self, dt):
        """Чужие герои приходят по сети 30 раз в секунду — рисуем их плавно."""
        k = min(1.0, dt * 16.0)
        for q in self.players.values():
            if q is self.player:
                continue
            if abs(q.rect.x - q.dx) > 160 or abs(q.rect.y - q.dy) > 160:
                q.dx, q.dy = float(q.rect.x), float(q.rect.y)
            else:
                q.dx += (q.rect.x - q.dx) * k
                q.dy += (q.rect.y - q.dy) * k

    def stomp_foe(self, foe, q, pts, name, part_cols, part_n=18):
        """Игрок q прыгнул на врага/голубя: -1 HP врагу; в кооперативе у врагов 2 HP."""
        self.bounce(q)
        if foe.inv > 0:
            return
        foe.hp -= 1
        cx, top = foe.rect.centerx, foe.rect.top
        if foe.hp > 0:
            foe.inv = 0.55
            self.burst(cx, top, part_cols, 8, 200, 0.4)
            self.float_text(cx, top - 12, "-1", WHITE)
            self.score += 50
            self.play("stomp")
            return
        foe.alive = False
        self.score += pts
        if isinstance(foe, Pigeon):
            self.burst(foe.rect.centerx, foe.rect.centery, [(225, 225, 232), (150, 156, 170), WHITE], part_n, 240, 0.6, 4, 400)
            self.float_text(cx, top - 12, "Голубь пал! +%d" % pts, (200, 215, 240))
        else:
            self.burst(cx, top, [RED, ORANGE, WHITE], part_n, 260, 0.55)
            self.float_text(cx, top - 12, "Прораб повержен! +%d" % pts, ORANGE)
        self.play("stomp")

    def pvp_step(self):
        """Прыжок на голову другого игрока отнимает у него 1 HP."""
        if not self.pvp or self.safe or self.coop_lobby or len(self.players) < 2:
            return
        pl = [q for q in self.players.values() if not q.dead]
        for a in pl:
            if a.vel.y <= 130 or a.dead:
                continue
            for b in pl:
                if b is a or b.dead or not a.rect.colliderect(b.rect):
                    continue
                if (a.rect.bottom - b.rect.top) < 22 and a.rect.centery < b.rect.centery:
                    self.bounce(a)
                    if b.invuln <= 0:
                        self.float_text(b.rect.centerx, b.rect.top - 24, "-1 HP", ORANGE)
                        self.damage_player(a.rect.centerx, b)
                    break

    def sim_world(self, dt):
        """Мир считает хост (или одиночная игра): враги, голуби, предметы, урон, победа, босс."""
        bt = self.battle
        host = self.role == "host"
        players = list(self.players.values())
        for q in players:
            if q.dead:
                if host or self.role is None:
                    q.respawn_t -= dt
                    if q.respawn_t <= 0:
                        self.revive(q)
                continue
            if q is not self.player:
                if q.rect.top > self.world_h + 40:
                    self.respawn_at_checkpoint(q)
                    if self.state != "play":
                        return
        alive = [q for q in self.players.values() if not q.dead]

        # --- враги
        for en in self.enemies:
            en.update(dt)
            if not en.alive:
                continue
            for q in alive:
                if q.dead or not q.rect.colliderect(en.rect):
                    continue
                if q.vel.y > 130 and (q.rect.bottom - en.rect.top) < 22:
                    self.stomp_foe(en, q, 150, "enemy", [RED, ORANGE, WHITE])
                    if not en.alive:
                        break
                else:
                    self.damage_player(en.rect.centerx, q)
            if self.state != "play":
                return

        for pg in self.pigeons:
            pg.update(dt, self)
            if not pg.alive:
                continue
            for q in alive:
                if q.dead or not q.rect.colliderect(pg.rect):
                    continue
                if q.vel.y > 130 and (q.rect.bottom - pg.rect.top) < 22:
                    self.stomp_foe(pg, q, 200, "pigeon", [(225, 225, 232), WHITE])
                    if not pg.alive:
                        break
                else:
                    self.damage_player(pg.rect.centerx, q)
            if self.state != "play":
                return
        if self.poops:
            self.update_poops(dt)
            if self.state != "play":
                return

        for sp in self.spikes:
            for q in alive:
                if not q.dead and q.rect.colliderect(sp):
                    self.damage_player(sp.centerx, q)
            if self.state != "play":
                return

        if len(players) > 1:
            self.pvp_step()
            if self.state != "play":
                return

        alive = [q for q in alive if not q.dead]
        for i, (cxp, _cyp) in enumerate(self.checkpoints):
            if i in self.checkpoints_hit:
                continue
            for q in alive:
                if q.rect.centerx > cxp:
                    self.checkpoints_hit.add(i)
                    self.spawn_point.update(cxp, self.ground_y - 2 * TILE)
                    self.float_text(q.rect.centerx, q.rect.top - 26, "Контрольная точка!", GREEN)
                    self.play("check")
                    break

        # --- подбор предметов (проверяем только те, что рядом с кем-то из игроков)
        if alive:
            xs = [q.rect.centerx for q in alive]
            el = self.elapsed
            for pk in self.pickups:
                if pk.taken:
                    continue
                bx = pk.base.x
                for q, qx in zip(alive, xs):
                    if abs(bx - qx) > 60:
                        continue
                    pk.rect.center = (int(bx), int(pk.base.y + math.sin(el * 3 + pk.phase) * 4))
                    if q.rect.colliderect(pk.rect):
                        if self.collect(pk, q):
                            pk.taken = True
                            self.pk_dirty = True
                        break

        if bt is not None:
            bt.update(dt)
            if self.state != "play":
                return
        elif self.bricks_collected >= BUILD_CELLS_TOTAL and not self.coop_lobby:
            for q in alive:
                if q.rect.centerx >= self.zone_x:
                    self.set_state("win")
                    self.flash_timer = 0.0
                    self.win_timer = 0.0
                    self.score += max(0, 600 - int(self.elapsed) * 2)
                    self.play("win")
                    bx, by, cell = self._bo
                    self.burst(bx + cell * 2, by - 10, [YELLOW, PINK, WHITE, GREEN], 45, 380, 1.0, 6)
                    break

    def update_camera(self, dt):
        p = self.focus_player()
        bt = self.battle
        if bt is not None:
            target, ty_, spd = bt.camera_target(p)
        else:
            target = clamp(p.rect.centerx - self.W // 2, -CAM_PAD, self.world_w - self.W + CAM_PAD)
            spd = 7
        self.camera_x = lerp(self.camera_x, target, min(1, dt * spd))
        if self.cam_max_y:
            if bt is None:
                ty_ = clamp(p.rect.centery - 330, 0, self.cam_max_y)
            self.camera_y = lerp(self.camera_y, ty_, min(1, dt * 6))
            col = p.rect.centerx // TILE
            di = 0
            for k, (st, _nm, _pl) in enumerate(self.lvl.districts):
                if col >= st:
                    di = k
            if di != self.dist_idx:
                self.dist_idx = di
                if bt is None or bt.phase == "explore":
                    self.flash_text = "РАЙОН: " + self.lvl.districts[di][1]
                    self.flash_timer = 3.0
        self.shake = max(0, self.shake - dt)
        if self.flash_timer > 0:
            self.flash_timer -= dt

    def update_play(self, dt):
        if self.role == "client":
            return self.update_play_client(dt)
        self.elapsed += dt
        for mp in self.platforms:
            mp.update(self.elapsed)
        p = self.player
        self.local_input_step(dt)                  # физика своего героя: звуки прыжков слышит только он
        if not p.dead and p.rect.top > self.world_h + 40:
            self.respawn_at_checkpoint(p)
            if self.state != "play":
                return
        if self.role == "host":
            for q in self.players.values():
                if q is not p:
                    q.invuln = max(0.0, q.invuln - dt)
            self.smooth_players(dt)
        if not self.coop_lobby:
            self.bc = self.role == "host"          # всё, что происходит в мире, видят и слышат все
            try:
                self.sim_world(dt)
            finally:
                self.bc = False
            if self.state != "play":
                return
        self.update_camera(dt)

    def update_play_client(self, dt):
        """Клиент: считает только своего героя; мир, враги и босс приходят от хоста."""
        self.elapsed += dt
        for mp in self.platforms:
            mp.update(self.elapsed)
        self.local_input_step(dt)
        self.smooth_players(dt)
        if not self.coop_lobby:
            for en in self.enemies:
                en.update(dt)
            k = min(1.0, dt * 22.0)
            for pg in self.pigeons:
                if pg.alive and getattr(pg, "seen", False):
                    pg.x += (pg.tx - pg.x) * k
                    pg.y += (pg.ty - pg.y) * k
                    pg.sync()
            bt = self.battle
            if bt is not None:
                bt.client_update(dt)
        self.update_camera(dt)

    def update(self, dt):
        self.time_global += dt
        if self.state == "play":
            self.update_play(dt)
        elif self.state == "bwin":
            self.battle.update_result(dt)
        elif self.state == "win":
            self.win_timer += dt
            self.firework_timer -= dt
            if self.firework_timer <= 0:
                self.firework_timer = random.uniform(0.35, 0.8)
                bx, by, cell = self._bo
                fx = bx + random.randint(-90, cell * 5 + 90)
                fy = by - random.randint(10, 130)
                cols = random.choice([[YELLOW, ORANGE], [PINK, WHITE], [GREEN, YELLOW], [(120, 200, 255), WHITE]])
                self.fireworks.append((fx, fy, cols, 0.9))
                self.burst(fx, fy, cols, 26, 300, 0.9, 5, 320)
            target = clamp(self.zone_x - 140, -CAM_PAD, self.world_w - self.W + CAM_PAD)
            self.camera_x = lerp(self.camera_x, target, min(1, dt * 2.5))
            if self.cam_max_y:
                self.camera_y = lerp(self.camera_y, self.cam_max_y, min(1, dt * 2.5))
        if self.role is not None:
            self.net_tick(dt)

        self.particles = [pt for pt in self.particles if pt.update(dt)]
        self.floaters = [f for f in self.floaters if f.update(dt)]

    # -----------------------------------------------------------------------
    # Отрисовка мира (на логический холст W x 540)
    # -----------------------------------------------------------------------
    def draw_background(self, cam, cy=None, night=None):
        if night is None:
            night = self.night
        if night:
            if self.battle is not None:
                return self.battle.draw_bg(cam, cy)
            return self.draw_night_bg(cam, cy)
        s = self.screen
        W = self.W
        # вертикальный параллакс: чем выше камера, тем ниже уезжают дальние слои
        gdy = 0 if cy is None else self.ground_y - 468 - cy
        s.blit(self.sky, (0, 0))
        sun_x = W - 130 - int(cam * 0.05) % 40
        s.blit(self.sun_spr, (sun_x - self.sun_c[0], 74 - self.sun_c[1] + int(gdy * 0.1)))
        if not self.lite:
            P = self.cloud_period
            sx = (-int(cam * 0.30)) % P - 130
            cdy = int(gdy * 0.25)
            s.blit(self.cloud_strip, (sx, cdy))
            s.blit(self.cloud_strip, (sx - P, cdy))
            off = int(cam * 0.45)
            s.blit(self.bld_strip, (-(off % 300) - 60, self.bld_y0 + int(gdy * 0.7)))
            s.blit(self.crane_strip, (-(off % 620) - 70, 140 + int(gdy * 0.6)))
        off2 = int(cam * 0.6)
        s.blit(self.hill_strip, (-(off2 % 260) - 80, SCREEN_H - 120 + int(gdy * 0.85)))

    def draw_level(self, cam, cy=0):
        if self.strips is None:
            self.screen.blit(self.level, (0, self.lvl_y0 - cy),
                             (cam + LEVEL_PAD, 0, self.W, self.level.get_height()))
            return
        s = self.screen
        y = self.lvl_y0 - cy
        W = self.W
        sw = citydraw.STRIP_W
        for sx0, surf in self.strips:
            if sx0 + sw > cam and sx0 < cam + W:
                s.blit(surf, (sx0 - cam, y))

    def draw_moving_platforms(self, cam, cy=0):
        s = self.screen
        for mp in self.platforms:
            r = mp.rect
            if r.right < cam - 10 or r.left > cam + self.W + 10:
                continue
            s.blit(self.platform_spr(r.w, r.h), (r.x - cam, r.y - 46 - cy))

    def draw_checkpoints(self, cam, cy=0):
        for i, (cxp, gyp) in enumerate(self.checkpoints):
            x = cxp - cam
            if x < -60 or x > self.W + 60:
                continue
            base_y = gyp - cy
            active = i in self.checkpoints_hit
            pygame.draw.rect(self.screen, (110, 110, 120), (x + 16, base_y - 74, 5, 74))
            col = GREEN if active else (170, 175, 185)
            wave = int(math.sin(self.time_global * 4 + i) * 2)
            pygame.draw.polygon(self.screen, col,
                                [(x + 21, base_y - 74), (x + 47, base_y - 66 + wave), (x + 21, base_y - 56)])
            if active:
                pygame.draw.lines(self.screen, WHITE, False,
                                  [(x + 25, base_y - 65), (x + 29, base_y - 61), (x + 36, base_y - 69)], 3)

    def draw_build_zone(self, cam, cy=0):
        s = self.screen
        zx = self.zone_x0 - cam
        if zx > self.W or zx + self.zone_w < 0:
            return
        bx, by, cell = self._bo
        s.blit(self.zone_surf, (zx, self.zone_y0 - cy))
        sign_x = self.zone_x - cam + 66
        gyc = self.ground_y - cy
        self.text(s, "СТРОЙКА ПИСЮНА", 17, sign_x + 119, gyc - 300, YELLOW, center=True, bold=True)
        pct = int(self.bricks_collected / BUILD_CELLS_TOTAL * 100)
        self.text(s, f"ГОТОВО: {pct}%  ({self.bricks_collected}/{BUILD_CELLS_TOTAL})",
                  15, sign_x + 119, gyc - 278, WHITE, center=True)

        order = self.build_order()
        built_set = set(order[:self.bricks_collected])
        tg = self.time_global
        for r, row in enumerate(BUILD_SHAPE):
            for c, ch in enumerate(row):
                if ch != "X":
                    continue
                x = bx + c * cell - cam
                y = by + r * cell - cy
                if (r, c) in built_set:
                    t = clamp((self.elapsed - self.built_at.get((r, c), 0)) * 4, 0.15, 1.0)
                    sz = int(cell * t)
                    ox, oy = x + (cell - sz) // 2, y + (cell - sz) // 2
                    top_rows = r <= 1
                    base = PINK if top_rows else SKIN_BLOCK
                    dark = (219, 76, 130) if top_rows else SKIN_DARK
                    pygame.draw.rect(s, base, (ox, oy, sz, sz))
                    pygame.draw.rect(s, dark, (ox, oy + sz - max(3, sz // 6), sz, max(3, sz // 6)))
                    pygame.draw.rect(s, (255, 235, 205), (ox, oy, sz, max(3, sz // 7)))
                    pygame.draw.rect(s, BLACK, (ox, oy, sz, sz), 2)
                    if sz >= 18:
                        pygame.draw.rect(s, (255, 255, 255), (ox + 6, oy + 6, 5, 5))
                else:
                    pulse = 90 + int(math.sin(tg * 3 + r + c) * 25)
                    self.ghost.set_alpha(pulse)
                    s.blit(self.ghost, (x + 2, y + 2))
                    pygame.draw.rect(s, (35, 42, 66), (x + 2, y + 2, cell - 4, cell - 4), 1)
        if self.bricks_collected >= BUILD_CELLS_TOTAL:
            for i in range(5):
                sx = bx - cam + (i * 41 + int(tg * 30)) % (cell * 5)
                sy = by - 14 - (i * 23) % 30 - cy
                pygame.draw.circle(s, YELLOW, (int(sx), int(sy)), 3)

    def draw_pickups(self, cam, cy=0):
        s = self.screen
        W = self.W
        el = self.elapsed
        tg = self.time_global
        for pk in self.pickups:
            if pk.taken:
                continue
            x = int(pk.base.x) - 14 - cam
            if x < -50 or x > W + 50:
                continue
            y = int(pk.base.y + math.sin(el * 3 + pk.phase) * 4) - 14 - cy
            if y < -50 or y > SCREEN_H + 50:
                continue
            kind = pk.kind
            if kind == "brick":
                glow = 4 + int(math.sin(tg * 5 + pk.phase) * 2)
                s.blit(self.brick_spr(glow), (x - 8, y - 8))
            elif kind == "bolt":
                bx, by = x + 14, y + 14
                pts = [(bx + math.cos(math.pi / 3 * i + el) * 11,
                        by + math.sin(math.pi / 3 * i + el) * 11) for i in range(6)]
                pygame.draw.polygon(s, (196, 205, 218), pts)
                pygame.draw.polygon(s, BLACK, pts, 2)
                pygame.draw.circle(s, (90, 98, 112), (bx, by), 5)
            elif kind == "grenade":
                s.blit(battle.pickup_sprite(self, "grenade"), (x - 3, y - 6))
            elif kind == "medkit":
                s.blit(battle.pickup_sprite(self, "medkit"), (x - 3, y - 2))
            else:
                self.draw_heart(x + 14, y + 14, 13, PINK)

    def draw_enemy(self, en, cam, cy=0):
        if not en.alive:
            return
        r = en.rect
        if r.right < cam - 10 or r.left > cam + self.W + 10:
            return
        leg = int(math.sin(en.anim) * 4)
        face = 1 if en.dir > 0 else -1
        self.screen.blit(self.enemy_spr(leg, face), (r.x - cam - 4, r.y - 8 - cy))
        if en.max_hp > 1:
            self.draw_pips(r.centerx - cam, r.y - 16 - cy, en.hp, en.max_hp)

    def draw_pigeon(self, pg, cam, cy):
        if not pg.alive:
            return
        r = pg.rect
        if r.right < cam - 20 or r.left > cam + self.W + 20:
            return
        sy = r.y - cy
        if sy < -60 or sy > SCREEN_H + 60:
            return
        if pg.kind == "perch" and pg.state == "idle":
            frame = 3 + (1 if int(pg.anim * 1.4) % 4 == 0 else 0)
        elif pg.state == "alert":
            frame = 4
        else:
            frame = int(pg.anim) % 3
        spr = self.pigeon_spr(frame, pg.face)
        shake = int(math.sin(pg.anim * 3) * 2) if pg.state == "alert" else 0
        self.screen.blit(spr, (r.x - cam - 8 + shake, sy - 8))
        if pg.max_hp > 1 and pg.hp < pg.max_hp:
            self.draw_pips(r.centerx - cam, sy - (34 if pg.state == "alert" else 16), pg.hp, pg.max_hp)
        if pg.state == "alert":
            x = r.centerx - cam
            pygame.draw.rect(self.screen, RED, (x - 2, sy - 28, 5, 12))
            pygame.draw.rect(self.screen, RED, (x - 2, sy - 13, 5, 5))
        elif pg.flash > 0:
            x = r.centerx - cam
            pygame.draw.rect(self.screen, WHITE, (x - 2, sy - 22, 4, 4))

    def draw_poops(self, cam, cy):
        s = self.screen
        for po in self.poops:
            x, y = int(po[0] - cam), int(po[1] - cy)
            if -10 < x < self.W + 10 and -10 < y < SCREEN_H + 10:
                pygame.draw.ellipse(s, (238, 238, 232), (x - 4, y - 6, 8, 12))
                pygame.draw.rect(s, (160, 200, 150), (x - 2, y + 1, 4, 3))
                pygame.draw.ellipse(s, BLACK, (x - 4, y - 6, 8, 12), 1)

    def draw_pips(self, x, y, hp, mx):
        """Полоска здоровья врага из квадратиков."""
        w = 7
        x0 = int(x - mx * (w + 2) / 2 + 1)
        for i in range(mx):
            r = pygame.Rect(x0 + i * (w + 2), int(y), w, 6)
            if i < hp:
                pygame.draw.rect(self.screen, (235, 64, 72), r)
            else:
                pygame.draw.rect(self.screen, (60, 30, 36), r)
            pygame.draw.rect(self.screen, BLACK, r, 1)

    def draw_one_player(self, q, cam, cy, me):
        if q.dead:
            return
        coop = self.role is not None
        r = q.rect
        px, py = (r.x, r.y) if (me or not coop) else (int(q.dx), int(q.dy))
        sx, sy = px - cam - 4, py - 10 - cy
        if sx < -60 or sx > self.W + 60:
            return
        blink = (q.invuln > 0 and int(self.time_global * 14) % 2 == 0 and self.state == "play"
                 and not self.coop_lobby)
        if not blink:
            if q.climb is not None:
                self.screen.blit(self.player_climb_spr(int(q.anim) % 2, q.skin), (sx, sy))
            else:
                moving = abs(q.vel.x) > 10 and q.on_ground
                leg = int(math.sin(q.anim) * 5) if moving else 0
                bob = 1 if (moving and int(q.anim) % 2) else 0
                self.screen.blit(self.player_spr(q.facing, leg, bob, q.skin), (sx, sy))
        if coop and q.nick:
            col = skins.SKINS[q.skin % skins.SKIN_COUNT]["col"] if not me else (255, 236, 140)
            cx = px + r.w // 2 - cam
            ty = sy - 12
            self.text(self.screen, q.nick, 14, cx, ty, col, center=True, bold=True)
            if me:
                pygame.draw.polygon(self.screen, (255, 236, 140), [(cx - 5, ty + 9), (cx + 5, ty + 9), (cx, ty + 14)])

    def draw_players(self, cam, cy=0):
        me = self.player
        for q in self.players.values():
            if q is not me:
                self.draw_one_player(q, cam, cy, False)
        self.draw_one_player(me, cam, cy, True)

    draw_player = draw_players

    def draw_hud(self):
        s = self.screen
        dx = self.W - BASE_W
        s.blit(self.hud_base[self.state == "play"], (0, 0))
        hp = self.player.hp
        for i in range(5):
            spr, c = self.heart_spr(10, PINK if i < hp else (90, 95, 110))
            s.blit(spr, (28 + i * 30 - c, 24 - c))
        self.text(s, f"{self.bricks_collected}/{BUILD_CELLS_TOTAL}", 20, 220, 13, WHITE, bold=True)
        s.blit(self.bar_img(self.bricks_collected), (300, 17))
        self.text(s, "ПИСЮН", 13, 300 + 190 + 8, 16, WHITE, bold=True)
        self.text(s, f"{self.bolts}", 19, 606 + dx, 13, LIGHT, bold=True)
        self.text(s, f"ОЧКИ {self.score}", 19, 680 + dx, 13, YELLOW, bold=True)
        mm, ss = divmod(int(self.elapsed), 60)
        self.text(s, f"{mm:02d}:{ss:02d}", 19, 818 + dx, 13, WHITE, bold=True)
        if self.flash_timer > 0:
            self.text(s, self.flash_text, 24, self.W // 2, 78, (120, 255, 150), center=True, bold=True)
        if self.show_fps:
            tag = f"FPS {int(self.clock.get_fps())}" + ("  LITE" if self.lite else "")
            self.text(s, tag, 15, (self.W - 130) if self.role is not None else 8, 54, (255, 255, 120), bold=True)

    # ---------- меню и оверлеи ----------
    def ui_button(self, rect, label, action, size=20, color=GREEN, icon=None):
        rect = pygame.Rect(rect)
        self.ui_buttons.append((rect, action))
        down = self.ui_is_down(rect)
        fill = color if down else (30, 36, 58)
        fg = DARK if down else color
        pygame.draw.rect(self.screen, fill, rect, border_radius=12)
        pygame.draw.rect(self.screen, color, rect, 3, border_radius=12)
        img = self.render(label, size, fg, True)
        r = img.get_rect(center=rect.center)
        if icon == "play":
            r.x += 14
            h = size
            pygame.draw.polygon(self.screen, fg, [(r.x - 26, rect.centery - h // 2),
                                                  (r.x - 26, rect.centery + h // 2),
                                                  (r.x - 8, rect.centery)])
        self.screen.blit(img, r)

    def sound_label(self):
        return "ЗВУК: ВКЛ" if self.sound_on else "ЗВУК: ВЫКЛ"

    def fs_label(self):
        return "В ОКНЕ" if self.fullscreen else "ПОЛНЫЙ ЭКРАН"

    def fps_label(self):
        return "FPS: ВКЛ" if self.show_fps else "FPS: ВЫКЛ"

    def draw_menu_monument(self, cx, cy, cell=17):
        rows = BUILD_SHAPE
        ox = cx - len(rows[0]) * cell // 2
        oy = cy - len(rows) * cell // 2
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch != "X":
                    continue
                base = PINK if r <= 1 else SKIN_BLOCK
                dark = (219, 76, 130) if r <= 1 else SKIN_DARK
                x, y = ox + c * cell, oy + r * cell
                pygame.draw.rect(self.screen, base, (x, y, cell, cell))
                pygame.draw.rect(self.screen, dark, (x, y + cell - 4, cell, 4))
                pygame.draw.rect(self.screen, BLACK, (x, y, cell, cell), 2)
        pygame.draw.rect(self.screen, BLACK, (ox + cell, oy + cell * 2, cell * 3, 9))
        pygame.draw.rect(self.screen, (40, 45, 60), (ox + cell + 3, oy + cell * 2 + 2, cell - 4, 5))
        pygame.draw.rect(self.screen, (40, 45, 60), (ox + cell * 3 + 3, oy + cell * 2 + 2, cell - 4, 5))

    def _build_menu_bg(self):
        s = self.screen
        W = self.W
        self.draw_background(400, night=False)
        pygame.draw.rect(s, (140, 98, 64), (0, SCREEN_H - 54, W, 54))
        pygame.draw.rect(s, (96, 178, 92), (0, SCREEN_H - 54, W, 10))
        mx = W - 230
        self.draw_menu_monument(mx, 285, 20)
        self.text(s, "ОН ЖДЁТ СВОИХ КИРПИЧЕЙ", 15, mx, 366, WHITE, center=True, bold=True)
        self.text(s, "ПИКСЕЛЬНЫЙ", 58, 72, 64, YELLOW, bold=True)
        self.text(s, "ПИСЮН", 92, 70, 118, PINK, bold=True)
        self.text(s, "— СТРОЙКА ВЕКА —", 25, 74, 224, WHITE, bold=True)
        self.text(s, "Шуточный платформер про великого строителя,", 19, 74, 282, WHITE)
        self.text(s, "25 кирпичей и один очень амбициозный проект.", 19, 74, 308, WHITE)
        self.menu_bg = s.copy()

    def draw_menu(self):
        if self.menu_bg is None:
            self._build_menu_bg()
        self.screen.blit(self.menu_bg, (0, 0))
        self.ui_button((74, 334, 210, 60), "КЛАССИКА", "start", 22, GREEN, icon="play")
        self.ui_button((294, 334, 210, 60), "ГЕНЕРАЦИЯ", "start_gen", 22, YELLOW)
        self.text(self.screen, "наша карта", 14, 179, 401, LIGHT, center=True)
        self.text(self.screen, "новый город каждый раз", 14, 399, 401, LIGHT, center=True)
        self.ui_button((74, 426, 430, 76), "БИТВА ЗА ПИСЮН", "start_battle", 28, (255, 96, 84))
        self.text(self.screen, "НОВОЕ · ночь · босс · гранаты", 14, 289, 484, (255, 190, 180), center=True)
        gx = self.W - 445
        self.ui_button((gx, 382, 430, 46), "КО-ОП  ·  ПО WI-FI", "coop_open", 21, (92, 170, 255))
        self.ui_button((gx, 440, 210, 42), "КАК ИГРАТЬ", "help", 18, LIGHT)
        self.ui_button((gx + 220, 440, 210, 42), self.sound_label(), "sound", 18, LIGHT)
        if IS_ANDROID:
            self.ui_button((gx, 490, 430, 38), self.fps_label(), "fps", 16, LIGHT)
        else:
            self.ui_button((gx, 490, 210, 38), self.fs_label(), "fullscreen", 16, LIGHT)
            self.ui_button((gx + 220, 490, 210, 38), self.fps_label(), "fps", 16, LIGHT)

    def _build_help_bg(self):
        s = self.screen
        W = self.W
        hx = (W - BASE_W) // 2
        self.draw_background(300, night=False)
        pygame.draw.rect(s, (140, 98, 64), (0, SCREEN_H - 54, W, 54))
        box = pygame.Rect(150 + hx, 30, 660, 482)
        pygame.draw.rect(s, (24, 29, 48), box)
        pygame.draw.rect(s, YELLOW, box, 3)
        self.text(s, "КАК СТРОИТЬ ПИСЮНА", 32, W // 2, 62, YELLOW, center=True, bold=True)
        lines = [
            ("ЦЕЛЬ", "Собери 25 кирпичей — каждый станет блоком монумента."),
            ("", "Потом дойди до стройки в конце уровня."),
            ("ДВИЖЕНИЕ", "Две кнопки слева, палец можно скользить"),
            ("ПРЫЖОК", "Большая кнопка справа, в воздухе — двойной"),
            ("БЕГ", "Кнопка БЕГ включает и выключает ускорение"),
            ("МУЛЬТИТАЧ", "Бегай и прыгай одновременно, двумя пальцами"),
            ("ВРАГИ", "Прорабов топчи сверху, сбоку не трогай!"),
            ("ОПАСНО", "Шипы и ямы отнимают здоровье, сердечки лечат"),
            ("ПРОЧЕЕ", "Флажки — контрольные точки, гайки — очки"),
            ("ЛЕСТНИЦЫ", "В Генерации: ВВЕРХ/ВНИЗ у лестницы, прыжок — слезть"),
            ("ГОЛУБИ", "Сидят и пикируют сверху, а летающие роняют бомбочки"),
            ("ГЕНЕРАЦИЯ", "Каждый раз новый город: башни, лифты, мосты"),
            ("БИТВА", "Ночью собери блоки, построй писюна — и дерись с ним:"),
            ("", "кнопка ГРАНАТА целится сама, гранаты и аптечки — по городу"),
            ("КО-ОП", "Кнопка КО-ОП: создай игру или зайди в чужую по Wi-Fi."),
            ("", "До 6 игроков. Враги — 2 HP, у босса HP × число игроков."),
        ]
        if not IS_ANDROID:
            lines.append(("КЛАВИШИ", "←→/AD ход · Пробел прыжок · Shift бег · G граната · E строить · Esc пауза"))
        y = 94
        for head, body in lines:
            if head:
                self.text(s, head, 16, 180 + hx, y, PINK, bold=True)
            self.text(s, body, 16, 310 + hx, y, WHITE)
            y += 20
        self.help_bg = s.copy()

    def draw_loading(self):
        if self.menu_bg is None:
            self._build_menu_bg()
        self.screen.blit(self.menu_bg, (0, 0))
        self.overlay((10, 12, 24), 190)
        cx = self.W // 2
        self.text(self.screen, "СТРОИМ ГОРОД...", 40, cx, 240, YELLOW, center=True, bold=True)
        self.text(self.screen, "Прорабы уже расставлены, голуби — тоже.", 18, cx, 290, WHITE, center=True)

    def draw_help(self):
        if self.help_bg is None:
            self._build_help_bg()
        self.screen.blit(self.help_bg, (0, 0))
        self.ui_button((self.W // 2 - 110, 446, 220, 46), "НАЗАД", "menu", 20, GREEN)

    def _take_snapshot(self, color, alpha):
        """Мир с затемнением — рисуется один раз при входе в паузу / «игра окончена»."""
        self.draw_world()
        self.overlay(color, alpha)
        self.snap = self.screen.copy()

    def draw_pause(self):
        if self.snap is None:
            self._take_snapshot((10, 12, 24), 165)
        self.screen.blit(self.snap, (0, 0))
        cx = self.W // 2
        self.text(self.screen, "ПАУЗА", 52, cx, 150, YELLOW, center=True, bold=True)
        self.text(self.screen, "Стройка подождёт. Писюн — нет.", 19, cx, 205, WHITE, center=True)
        if self.mode == "gen":
            self.text(self.screen, f"Генерация · карта №{self.seed}", 15, cx, 232, LIGHT, center=True)
        elif self.mode == "battle":
            self.text(self.screen, "Битва за Писюн · ночь", 15, cx, 232, LIGHT, center=True)
        self.ui_button((cx - 170, 250, 340, 56), "ПРОДОЛЖИТЬ", "resume", 24, GREEN, icon="play")
        self.ui_button((cx - 170, 320, 165, 48), "ЗАНОВО", "restart", 19, YELLOW)
        self.ui_button((cx + 5, 320, 165, 48), "В МЕНЮ", "menu", 19, LIGHT)
        self.ui_button((cx - 170, 382, 165, 48), self.sound_label(), "sound", 19, LIGHT)
        if IS_ANDROID:
            self.ui_button((cx + 5, 382, 165, 48), self.fps_label(), "fps", 17, LIGHT)
        else:
            self.ui_button((cx + 5, 382, 165, 48), self.fs_label(), "fullscreen", 17, LIGHT)
            self.ui_button((cx - 170, 440, 340, 44), self.fps_label(), "fps", 17, LIGHT)

    def draw_win(self):
        self.draw_world()
        self.overlay((12, 16, 30), 105)
        cx = self.W // 2
        self.text(self.screen, "ПИСЮН ПОСТРОЕН!", 54, cx, 92, YELLOW, center=True, bold=True)
        self.text(self.screen, "Монумент века возвышается над стройкой.", 21, cx, 148, WHITE, center=True)
        self.text(self.screen, "Прорабы плачут. Строитель доволен. Соседи в шоке.", 18, cx, 178, LIGHT, center=True)
        mm, ss = divmod(int(self.elapsed), 60)
        stats = [
            f"Время строительства: {mm:02d}:{ss:02d}",
            f"Гаек собрано: {self.bolts}/{len(self.lvl.bolts)}",
            f"Итоговые очки: {self.score}",
            f"Здоровья осталось: {self.player.hp}/5",
        ]
        y = 228
        for line in stats:
            self.text(self.screen, line, 21, cx, y, WHITE, center=True)
            y += 34
        bx, by, cell = self._bo
        cam = int(self.camera_x)
        pygame.draw.rect(self.screen, (212, 175, 55), (bx + cell - cam, self.ground_y - 34 - self.cy, cell * 3, 24))
        pygame.draw.rect(self.screen, BLACK, (bx + cell - cam, self.ground_y - 34 - self.cy, cell * 3, 24), 2)
        self.text(self.screen, "* ПИСЮН ВЕКА *", 14, bx + cell * 2 + 15 - cam, self.ground_y - 30 - self.cy, BLACK, center=True, bold=True)
        if self.role is not None:
            self.coop_end_buttons(cx, 392, "win")
        else:
            self.ui_button((cx - 255, 392, 320, 54), "ПОСТРОИТЬ ЕЩЁ ОДИН", "new_gen" if self.mode == "gen" else "restart", 20, GREEN)
            self.ui_button((cx + 85, 392, 170, 54), "МЕНЮ", "menu", 20, LIGHT)

    def draw_gameover(self):
        if self.snap is None:
            self._take_snapshot((30, 8, 14), 175)
        self.screen.blit(self.snap, (0, 0))
        cx = self.W // 2
        if self.battle is not None:
            t1, t2, t3 = self.battle.gameover_lines()
            self.text(self.screen, t1, 50, cx, 170, RED, center=True, bold=True)
            self.text(self.screen, t2, 20, cx, 232, WHITE, center=True)
            self.text(self.screen, t3, 19, cx, 272, YELLOW, center=True)
        else:
            self.text(self.screen, "СТРОЙКА ВСТАЛА...", 50, cx, 170, RED, center=True, bold=True)
            self.text(self.screen, "Строитель устал, а писюн остался недостроенным.", 20, cx, 232, WHITE, center=True)
            self.text(self.screen, f"Кирпичей успело лечь: {self.bricks_collected}/{BUILD_CELLS_TOTAL}   |   Очки: {self.score}",
                      19, cx, 272, YELLOW, center=True)
        if self.role is not None:
            self.coop_end_buttons(cx, 322, "gameover")
        else:
            self.ui_button((cx - 230, 322, 220, 56), "ЗАНОВО" if self.battle is None else "ЕЩЁ РАЗ", "retry", 22, GREEN)
            self.ui_button((cx + 10, 322, 220, 56), "МЕНЮ", "menu", 22, LIGHT)

    def draw_world(self):
        if self.battle is not None:
            return self.battle.draw_world()
        shake_x = int(random.uniform(-5, 5)) if (self.shake > 0 and not self.lite) else 0
        cam = int(self.camera_x) + shake_x
        cy = int(self.camera_y)
        self.cy = cy
        self.draw_background(cam, cy)
        self.draw_build_zone(cam, cy)
        self.draw_checkpoints(cam, cy)
        self.draw_level(cam, cy)
        self.draw_moving_platforms(cam, cy)
        self.draw_pickups(cam, cy)
        for en in self.enemies:
            self.draw_enemy(en, cam, cy)
        for pg in self.pigeons:
            self.draw_pigeon(pg, cam, cy)
        if self.poops:
            self.draw_poops(cam, cy)
        self.draw_players(cam, cy)
        scr = self.screen
        for pt in self.particles:
            pt.draw(scr, cam, cy)
        for f in self.floaters:
            f.draw(scr, cam, self)
        if not self.coop_lobby:
            self.draw_hud()
        if self.role is not None:
            self.draw_coop_overlay()

    def draw(self):
        self.ui_buttons = []
        st = self.state
        if st == "menu":
            self.draw_menu()
        elif st == "help":
            self.draw_help()
        elif st == "play":
            self.draw_world()
        elif st == "pause":
            self.draw_pause()
        elif st == "win":
            self.draw_win()
        elif st == "bwin":
            self.battle.draw_result()
        elif st == "gameover":
            self.draw_gameover()
        elif st == "loading":
            self.draw_loading()
        elif st == "coop":
            self.draw_coop()
        elif st == "create":
            self.draw_create()
        elif st == "joining":
            self.draw_joining()
        self.present()
        self.dirty = False
        self.idle = 0.0

    def present(self):
        """Растягиваем холст на экран (если нужно) и рисуем сенсорные кнопки поверх."""
        if not self.direct:
            for b in self.bars:
                self.window.fill(BAR_COLOR, b)
            if self.view_surf is not None:
                try:
                    pygame.transform.scale(self.screen, self.view.size, self.view_surf)
                except (ValueError, TypeError, pygame.error):
                    self.window.blit(pygame.transform.scale(self.screen, self.view.size), self.view.topleft)
            else:
                self.window.blit(pygame.transform.scale(self.screen, self.view.size), self.view.topleft)
        if self.state == "play":
            win = self.window
            hid = self.battle.hidden() if self.battle is not None else ()
            for name, (off, on) in self.ctl_imgs.items():
                if name in hid:
                    continue
                hot = self.run_on if name == "run" else self.held(name)
                win.blit(on if hot else off, self.controls[name].pos)
            if self.battle is not None and "grenade" in self.controls and "grenade" not in hid:
                cx_, cy_, rg_ = self.controls["grenade"].geom
                n_ = self.player.gren
                badge = self.font(max(14, int(rg_ * 0.7)), True).render(str(n_), True, (255, 255, 255) if n_ else (255, 120, 110))
                win.blit(badge, (int(cx_ + rg_ * 0.45), int(cy_ + rg_ * 0.25)))
        pygame.display.flip()

    # ---------- адаптация к слабому телефону ----------
    def track_speed(self, dt_real):
        self._ema += (dt_real - self._ema) * 0.05
        if not self.lite and self._ema > 0.026:   # реально меньше ~38 кадров/с
            self._slow += 1
            if self._slow > 150:
                self.lite = True
        else:
            self._slow = max(0, self._slow - 2)

    # ---------- главный цикл ----------
    def run(self):
        while self.running:
            static = self.state not in ("play", "win", "bwin")
            dt_real = self.clock.tick(30 if static else FPS) / 1000.0
            self.sync_window()
            self.handle_events()
            if not self.running:
                break
            self.net_pump(dt_real)
            if self.state in ("play", "win", "bwin"):
                dt = min(dt_real, 0.1)
                if self.state == "play":
                    self.track_speed(dt_real)
                n = max(1, int(math.ceil(dt / MAX_STEP)))
                step = dt / n
                for _ in range(n):
                    self.update(step)
                    if self.state not in ("play", "win", "bwin"):
                        break
                self.draw()
            else:
                self.idle += dt_real
                lim = 0.08 if self.state in coop.COOP_UI_STATES else 0.5
                if self.dirty or self.idle > lim:
                    self.draw()
                if self.state == "loading":
                    self.process_pending()
        pygame.quit()


# ---------------------------------------------------------------------------
# Самопроверка без окна
# ---------------------------------------------------------------------------
def run_smoke_test():
    """Телепорт по кирпичам + проверка мультитача синтетическими событиями."""
    pygame.init()
    pygame.mixer.init()
    window = pygame.display.set_mode((1280, 720))

    # 1) прохождение
    game = Game(window, fullscreen=False)
    assert game.W == 960 and not game.direct
    game.set_state("play")
    for pk in [p for p in game.pickups if p.kind == "brick"]:
        game.player.rect.center = (int(pk.base.x), int(pk.base.y))
        game.player.vel.update(0, 0)
        game.update(1 / 60)
    assert game.bricks_collected == BUILD_CELLS_TOTAL, game.bricks_collected
    collected = game.bricks_collected
    game.player.rect.x = BUILD_ZONE_X + 60
    game.player.rect.y = 10 * TILE
    game.player.vel.update(0, 0)
    for _ in range(90):
        game.update(1 / 60)
        game.draw()
    assert game.state == "win", game.state

    # статичные экраны рисуются из кэша
    for st in ("menu", "help"):
        game.set_state(st)
        game.draw()
    game.reset_game()
    game.set_state("play")
    game.update(1 / 60)
    for st in ("pause", "gameover"):
        game.set_state(st)
        game.draw()
        assert game.snap is not None

    # 2) мультитач
    t = Game(window, fullscreen=False)
    W, H = t.win_size

    def touch(kind, fid, x, y):
        pygame.event.post(pygame.event.Event(kind, finger_id=fid, touch_id=0,
                                             x=x / W, y=y / H, dx=0.0, dy=0.0, pressure=1.0))
        t.handle_events()

    def center(name):
        c = t.controls[name]
        return c.geom.center if c.shape == "rect" else c.geom[:2]

    t.draw()
    start = [r for r, a in t.ui_buttons if a == "start"][0]
    touch(pygame.FINGERDOWN, 1, *t.to_screen(*start.center))
    touch(pygame.FINGERUP, 1, *t.to_screen(*start.center))
    assert t.state == "loading", t.state
    t.draw()
    t.process_pending()
    assert t.state == "play" and t.mode == "classic", t.state
    for _ in range(40):
        t.update(1 / 60)
    assert t.player.on_ground

    x0 = t.player.rect.x
    touch(pygame.FINGERDOWN, 10, *center("right"))
    touch(pygame.FINGERDOWN, 11, *center("jump"))
    assert t.held("right") and t.held("jump")
    for _ in range(12):
        t.update(1 / 60)
    assert t.player.rect.x > x0 and not t.player.on_ground, "идти и прыгать одновременно"
    touch(pygame.FINGERUP, 10, *center("right"))
    assert not t.held("right") and t.held("jump")

    touch(pygame.FINGERDOWN, 12, *center("run"))
    touch(pygame.FINGERUP, 12, *center("run"))
    assert t.run_on

    touch(pygame.FINGERDOWN, 13, *center("left"))
    assert t.held("left")
    touch(pygame.FINGERMOTION, 13, *center("right"))
    assert t.held("right") and not t.held("left"), "скольжение ◀ -> ▶"
    touch(pygame.FINGERUP, 13, *center("right"))
    touch(pygame.FINGERUP, 11, *center("jump"))
    assert not any(t.finger_btn.values()), "после отпускания ничего не залипло"

    touch(pygame.FINGERDOWN, 14, *t.to_screen(*t.pause_rect.center))
    assert t.state == "pause", t.state
    touch(pygame.FINGERUP, 14, *t.to_screen(*t.pause_rect.center))

    # 3) широкий экран телефона: кадр подстраивается, чёрных полос нет
    wide = pygame.display.set_mode((2340, 1080))
    w = Game(wide, fullscreen=False)
    assert w.W == 1170 and w.view.size == (2340, 1080) and not w.bars, (w.W, w.view)
    w.set_state("play")
    for _ in range(30):
        w.update(1 / 60)
        w.draw()

    # 4) масштаб 1:1 — рисуем сразу на экран
    small = pygame.display.set_mode((960, 540))
    d = Game(small, fullscreen=False)
    assert d.direct
    d.set_state("play")
    d.update(1 / 60)
    d.draw()

    # 5) режим «Генерация»: меню -> загрузка -> лестница -> голуби
    gm = Game(window, fullscreen=False)
    gm.draw()
    btn = [r for r, a in gm.ui_buttons if a == "start_gen"][0]
    gm.touch_down(1, *gm.to_screen(*btn.center))
    gm.touch_up(1, *gm.to_screen(*btn.center))
    assert gm.state == "loading", gm.state
    gm.draw()
    gm.process_pending()
    assert gm.state == "play" and gm.mode == "gen" and gm.seed, (gm.state, gm.mode)
    assert gm.ladders and gm.pigeons and "up" in gm.controls and "down" in gm.controls
    assert sum(1 for pk in gm.pickups if pk.kind == "brick") == BUILD_CELLS_TOTAL
    ld = gm.ladders[0]
    gm.player.rect.midbottom = (ld.cx, ld.bottom_y)
    gm.player.vel.update(0, 0)
    for _ in range(3):
        gm.update(1 / 60)
    c = gm.controls["up"]
    gm.touch_down(5, *c.geom.center)
    assert gm.held("up")
    for _ in range(90):
        gm.update(1 / 60)
    assert gm.player.climb is not None or gm.player.rect.bottom <= ld.bottom_y - 40, "лезем по лестнице"
    gm.touch_up(5, *c.geom.center)
    for _ in range(60):
        gm.update(1 / 60)
        gm.draw()
    gm.set_state("pause")
    gm.draw()
    gm.start_level("classic")
    assert gm.mode == "classic" and "up" not in gm.controls and gm.state == "play"

    # 6) режим «Битва за Писюн»: интро -> блоки -> стройка -> тряска -> робот -> бой -> финал
    bm = Game(window, fullscreen=False)
    bm.draw()
    btn = [r for r, a in bm.ui_buttons if a == "start_battle"][0]
    bm.touch_down(1, *bm.to_screen(*btn.center))
    bm.touch_up(1, *bm.to_screen(*btn.center))
    assert bm.state == "loading", bm.state
    bm.draw()
    bm.process_pending()
    assert bm.state == "play" and bm.mode == "battle" and bm.night and bm.battle is not None
    assert "grenade" in bm.controls and "up" in bm.controls
    bt = bm.battle

    def run(n, draw=True):
        for _ in range(n):
            bm.update(1 / 60)
            if draw:
                bm.draw()

    def talk():
        for _ in range(40):
            run(20, False)
            if bt.dlg is not None:
                bt.dlg.shown = len(bt.dlg.text)
                bt.touch(10, 10)
            if bt.phase not in ("intro", "quake"):
                break
    run(60)
    while bt.phase == "intro":
        run(30, False)
        if bt.dlg is not None:
            bt.dlg.shown = len(bt.dlg.text)
            bt.touch(10, 10)
    assert bt.phase == "explore", bt.phase
    for pk in [q for q in bm.pickups if q.kind == "brick"]:
        bm.player.rect.center = (int(pk.base.x), int(pk.base.y))
        bm.player.vel.update(0, 0)
        run(2, False)
    assert bm.bricks_collected == BUILD_CELLS_TOTAL
    bm.player.rect.midbottom = (bm.zone_x + 20, bm.ground_y)
    bm.player.vel.update(0, 0)
    run(30)
    assert bt.can_build()
    bt.touch(*bm.to_screen(*bt.btn.center))
    assert bt.phase == "build"
    while bt.phase != "quake":
        run(3)
    while bt.phase != "transform":
        run(20, False)
        if bt.dlg is not None:
            bt.dlg.shown = len(bt.dlg.text)
            bt.touch(10, 10)
    while bt.phase != "boss":
        run(3)
    assert bt.boss is not None and bm.player.gren == 3 and bt.supply
    t_fight = 0
    for t_fight in range(150 * 60):                 # бой: бросаем гранаты, пока босс не упадёт
        if bt.phase != "boss":
            break
        bm.player.hp = 5
        bm.player.rect.midbottom = (int(bt.boss.x - 340), bm.ground_y)
        if bm.player.gren <= 0:
            bm.player.gren = 3
        if bm.player.throw_cd <= 0 and bt.boss.state != "intro":
            bm.press("grenade")
        run(1, False)
    assert bt.phase in ("dying", "flash"), (bt.phase, bt.boss.hp, t_fight)
    print(f"  бой с ботом-метателем: {t_fight / 60:.1f} с")
    while bm.state == "play":
        run(2, False)
    assert bm.state == "bwin"
    for _ in range(60 * 10):
        run(1, _ % 3 == 0)
    assert any(a == "restart" for _r, a in bm.ui_buttons), "кнопки итогов"
    bm.set_state("pause")
    bm.draw()
    bm.start_level("classic")
    assert bm.mode == "classic" and bm.battle is None and not bm.night and "grenade" not in bm.controls

    print(f"SMOKE TEST OK: кирпичей={collected}/{BUILD_CELLS_TOTAL}, "
          f"мультитач=OK, широкий экран W={w.W}, прямой режим=OK, генерация=OK, битва=OK")
    pygame.quit()


def main():
    if "--smoke-test" in sys.argv:
        run_smoke_test()
        return
    try:
        pygame.mixer.pre_init(22050, -16, 1, 1024)
    except Exception:
        pass
    pygame.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    pygame.display.set_caption("Пиксельный Писюн — Стройка Века")
    if not IS_ANDROID:                                    # иконка окна на компьютере
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            pygame.display.set_icon(pygame.image.load(os.path.join(base, "icon.png")))
        except Exception:
            pass
    try:
        dw, dh = pygame.display.get_desktop_sizes()[0]
    except Exception:
        info = pygame.display.Info()
        dw, dh = info.current_w, info.current_h
    lw = choose_logical_width(dw, dh)
    fs = IS_ANDROID or "--fullscreen" in sys.argv        # на компьютере — окно (F11 — на весь экран)
    window, scaled = open_window(fs, lw)
    Game(window, fullscreen=fs, logical_w=lw, gpu_scaled=scaled).run()


if __name__ == "__main__":
    main()
