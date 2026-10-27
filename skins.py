# -*- coding: utf-8 -*-
"""Скины строителя для кооператива. Рисуются кодом на том же холсте 36x64, что и обычный строитель.

В одиночной игре всегда играет «божественный строитель» (скин 0, его рисует main.py как раньше).
Скины видны только в кооперативе.
"""
import pygame

BLACK = (20, 20, 30)
WHITE = (255, 255, 255)
YELLOW = (255, 204, 64)
ORANGE = (255, 133, 51)
PINK = (255, 111, 168)
RED = (235, 64, 72)

SKINS = [
    dict(name="СТРОИТЕЛЬ", note="Тот самый. Каска, жилет, мечта.", col=(255, 204, 64),
         pants=(38, 72, 165), shoes=(30, 30, 36), shirt=(38, 92, 205), vest=ORANGE, buckle=YELLOW,
         arm=(238, 182, 140), face=(242, 190, 145), acc="hardhat",
         hat=YELLOW, brim=(232, 178, 38), knob=(255, 226, 110)),
    dict(name="ПРОРАБ", note="Орёт сверху, а не снизу. Усы — служебные.", col=(235, 90, 96),
         pants=(78, 82, 96), shoes=(40, 34, 30), shirt=(238, 240, 246), vest=None, buckle=None,
         arm=(238, 182, 140), face=(242, 190, 145), acc="foreman",
         hat=(226, 58, 66), brim=(170, 36, 48), knob=(255, 150, 150)),
    dict(name="СВАРЩИК", note="Искры, маска и ни одного шва ровно.", col=(255, 150, 60),
         pants=(54, 58, 70), shoes=(30, 30, 36), shirt=(74, 80, 96), vest=(255, 150, 50), buckle=(200, 205, 215),
         arm=(160, 104, 54), face=(242, 190, 145), acc="welder"),
    dict(name="ГОЛУБЬ", note="Сидит на стройке и всё видит. Особенно машины.", col=(170, 180, 205),
         pants=(240, 120, 130), shoes=(240, 120, 130), shirt=(150, 156, 172), vest=None, buckle=None,
         arm=(104, 110, 128), face=(150, 156, 172), acc="pigeon"),
    dict(name="РОБО-ПИСЮН", note="Гига-робот, но в масштабе 1:30.", col=(255, 90, 140),
         pants=(68, 76, 98), shoes=(40, 44, 58), shirt=(104, 116, 142), vest=(240, 200, 40), buckle=(255, 140, 60),
         arm=(120, 130, 152), face=(150, 160, 184), acc="robot"),
    dict(name="СОНЯ", note="Пижама, ночной колпак и пять минут ещё.", col=(130, 170, 255),
         pants=(96, 124, 214), shoes=(246, 246, 250), shirt=(130, 168, 238), vest=None, buckle=None,
         arm=(238, 182, 140), face=(242, 190, 145), acc="sleepy"),
    dict(name="МОНУМЕНТ", note="Сам себе стройка: розовый верх, блоки внизу.", col=(255, 111, 168),
         pants=(238, 177, 125), shoes=(201, 128, 82), shirt=(238, 177, 125), vest=None, buckle=None,
         arm=(238, 177, 125), face=(255, 111, 168), acc="monument"),
    dict(name="КОНУС", note="Оранжевый, заметный и очень устойчивый.", col=(255, 140, 50),
         pants=(64, 68, 82), shoes=(30, 30, 36), shirt=(210, 214, 226), vest=(176, 232, 60), buckle=(226, 230, 240),
         arm=(238, 182, 140), face=(242, 190, 145), acc="cone"),
]
SKIN_COUNT = len(SKINS)


def skin_name(i):
    return SKINS[i % SKIN_COUNT]["name"]


def _r(s, col, x, y, w, h):
    pygame.draw.rect(s, col, (x, y, w, h))


def _head_top(s, sk, x, y, bob, f, mode):
    """Головной убор / лицо. mode: walk | climb (вид со спины — без лица)."""
    acc = sk["acc"]
    if acc in ("hardhat", "foreman"):
        _r(s, sk["hat"], x + 3, y - 3 + bob, 22, 9)
        _r(s, sk["brim"], x, y + 4 + bob, 28, 4)
        _r(s, sk["knob"], x + 11, y - 6 + bob, 6, 5)
        if acc == "foreman" and mode == "walk":
            mx = x + (14 if f > 0 else 6)
            _r(s, (40, 30, 26), mx, y + 11 + bob, 9, 3)            # усы
    elif acc == "welder":
        mask, dk = (58, 62, 76), (36, 38, 48)
        _r(s, mask, x + 3, y - 4 + bob, 22, 19)
        _r(s, (84, 90, 108), x + 3, y - 4 + bob, 22, 4)
        _r(s, dk, x + 3, y + 11 + bob, 22, 4)
        pygame.draw.rect(s, BLACK, (x + 3, y - 4 + bob, 22, 19), 2)
        if mode == "walk":
            vx = x + (8 if f > 0 else 5)
            _r(s, (20, 22, 30), vx, y + 2 + bob, 15, 8)
            _r(s, (255, 170, 60), vx + 2, y + 4 + bob, 11, 3)
            _r(s, (255, 236, 160), vx + 5, y + 5 + bob, 4, 1)
            for k in range(3):
                _r(s, (255, 200, 90), x + (24 if f > 0 else 1) + (k if f > 0 else -k), y + 8 + bob + k * 3, 2, 1)
    elif acc == "pigeon":
        grey, dark, light = (150, 156, 172), (104, 110, 128), (196, 202, 214)
        pygame.draw.ellipse(s, grey, (x + 3, y - 3 + bob, 22, 19))
        pygame.draw.ellipse(s, light, (x + 6, y + 1 + bob, 14, 8))
        _r(s, (88, 170, 150), x + 8, y + 14 + bob, 12, 3)             # блестящая шея
        _r(s, (170, 110, 190), x + 11, y + 15 + bob, 6, 2)
        if mode == "walk":
            ex = x + (17 if f > 0 else 9)
            bx = x + (24 if f > 0 else 4)
            sg = 1 if f > 0 else -1
            pygame.draw.polygon(s, (255, 190, 70), [(bx, y + 6 + bob), (bx + 8 * sg, y + 9 + bob), (bx, y + 12 + bob)])
            pygame.draw.circle(s, (255, 130, 40), (ex, y + 6 + bob), 3)
            pygame.draw.circle(s, BLACK, (ex, y + 6 + bob), 1)
        else:
            _r(s, dark, x + 9, y + 2 + bob, 10, 8)
        pygame.draw.ellipse(s, BLACK, (x + 3, y - 3 + bob, 22, 19), 1)
    elif acc == "robot":
        pk, pk_dk, hi = (232, 92, 152), (168, 48, 100), (255, 176, 210)
        _r(s, pk, x + 3, y - 3 + bob, 22, 17)
        _r(s, hi, x + 3, y - 3 + bob, 22, 3)
        _r(s, pk_dk, x + 3, y + 11 + bob, 22, 3)
        pygame.draw.rect(s, BLACK, (x + 3, y - 3 + bob, 22, 17), 2)
        _r(s, (190, 196, 210), x + 13, y - 9 + bob, 2, 6)             # антенна
        pygame.draw.circle(s, (255, 70, 70), (x + 14, y - 10 + bob), 3)
        if mode == "walk":
            vx = x + (6 if f > 0 else 5)
            _r(s, (22, 24, 36), vx, y + 3 + bob, 17, 7)
            _r(s, (255, 60, 50), vx + (9 if f > 0 else 2), y + 5 + bob, 5, 3)
            _r(s, (255, 60, 50), vx + (2 if f > 0 else 9), y + 5 + bob, 5, 3)
    elif acc == "sleepy":
        cap, cap_dk = (206, 50, 72), (160, 30, 54)
        sg = -1 if f > 0 else 1                                       # колпак свисает назад
        pts = [(x + 3, y + 5 + bob), (x + 25, y + 5 + bob), (x + 14, y - 8 + bob)]
        pygame.draw.polygon(s, cap, pts)
        tip = (x + (14 + sg * 14), y + 14 + bob)
        pygame.draw.polygon(s, cap, [(x + 14 + sg * 3, y - 6 + bob), (x + 14 + sg * 12, y + 3 + bob), tip,
                                     (x + 14 + sg * 10, y + 8 + bob), (x + 14, y + 2 + bob)])
        pygame.draw.polygon(s, cap_dk, [(x + 3, y + 5 + bob), (x + 14, y - 8 + bob), (x + 8, y + 5 + bob)])
        pygame.draw.circle(s, (245, 245, 250), tip, 4)
        pygame.draw.rect(s, (245, 245, 250), (x + 2, y + 3 + bob, 24, 4), border_radius=2)
        if mode == "walk":
            ex = x + (17 if f > 0 else 8)
            pygame.draw.line(s, BLACK, (ex - 2, y + 9 + bob), (ex + 2, y + 9 + bob), 2)     # сонные глаза
    elif acc == "monument":
        pk, pk_dk = (255, 111, 168), (219, 76, 130)
        _r(s, pk, x + 3, y - 4 + bob, 22, 19)
        _r(s, (255, 235, 205), x + 3, y - 4 + bob, 22, 3)
        _r(s, pk_dk, x + 3, y + 10 + bob, 22, 5)
        pygame.draw.rect(s, BLACK, (x + 3, y - 4 + bob, 22, 19), 2)
        _r(s, WHITE, x + 6, y - 1 + bob, 4, 4)
        if mode == "walk":
            ex = x + (17 if f > 0 else 8)
            _r(s, BLACK, ex - 1, y + 5 + bob, 3, 4)
            _r(s, BLACK, ex + (6 if f > 0 else -6) - 1, y + 5 + bob, 3, 4)
    elif acc == "cone":
        cone, cone_dk = (255, 134, 44), (214, 98, 28)
        pygame.draw.polygon(s, cone, [(x + 6, y + 6 + bob), (x + 22, y + 6 + bob), (x + 14, y - 14 + bob)])
        pygame.draw.polygon(s, WHITE, [(x + 9, y - 1 + bob), (x + 19, y - 1 + bob), (x + 17, y - 6 + bob), (x + 11, y - 6 + bob)])
        pygame.draw.polygon(s, WHITE, [(x + 7, y + 4 + bob), (x + 21, y + 4 + bob), (x + 19, y + bob), (x + 9, y + bob)])
        pygame.draw.polygon(s, cone_dk, [(x + 22, y + 6 + bob), (x + 14, y - 14 + bob), (x + 18, y + 6 + bob)])
        pygame.draw.polygon(s, BLACK, [(x + 6, y + 6 + bob), (x + 22, y + 6 + bob), (x + 14, y - 14 + bob)], 1)
        _r(s, cone_dk, x + 3, y + 6 + bob, 22, 3)
        pygame.draw.rect(s, BLACK, (x + 3, y + 6 + bob, 22, 3), 1)


def _eyes(s, sk, x, y, bob, f):
    acc = sk["acc"]
    if acc in ("welder", "pigeon", "robot", "sleepy", "monument", "cone") and acc != "cone":
        return                                   # нарисованы вместе с головным убором
    eye_x = x + (17 if f > 0 else 8)
    pygame.draw.circle(s, BLACK, (eye_x, y + 9 + bob), 2)
    _r(s, BLACK, x + (13 if f > 0 else 7), y + 12 + bob, 6, 2)


def draw(s, idx, mode, f, leg, bob):
    """Рисует скин на холсте 36x64 (цветовой ключ уже залит). mode: walk | climb."""
    sk = SKINS[idx % SKIN_COUNT]
    x, y = 4, 10
    acc = sk["acc"]
    if mode == "climb":
        lg = 2 if f else -2
        _r(s, sk["pants"], x + 5, y + 28, 8, 11 - lg)
        _r(s, sk["pants"], x + 16, y + 28, 8, 11 + lg)
        _r(s, sk["shoes"], x + 3, y + 39 - max(0, -lg), 11, 4)
        _r(s, sk["shoes"], x + 15, y + 39 - max(0, lg), 11, 4)
        _r(s, sk["shirt"], x + 4, y + 16, 20, 14)
        if sk["vest"]:
            _r(s, sk["vest"], x + 4, y + 13, 20, 7)
        ay = 2 if f else 8
        _r(s, sk["arm"], x + 0, y + ay, 6, 14)
        _r(s, sk["arm"], x + 22, y + 10 - ay + 2, 6, 14)
        if acc != "pigeon":
            _r(s, sk["face"], x + 5, y + 2, 18, 13)
        _head_top(s, sk, x, y, 0, f, "climb")
        _body_extras(s, sk, x, y, 0, f, "climb")
        return
    _r(s, sk["pants"], x + 5, y + 28 + bob, 8, 11 - leg)
    _r(s, sk["pants"], x + 16, y + 28 + bob, 8, 11 + leg)
    _r(s, sk["shoes"], x + 3, y + 39 + bob - max(0, -leg), 11, 4)
    _r(s, sk["shoes"], x + 15, y + 39 + bob - max(0, leg), 11, 4)
    _r(s, sk["shirt"], x + 4, y + 16 + bob, 20, 14)
    if sk["vest"]:
        _r(s, sk["vest"], x + 4, y + 13 + bob, 20, 7)
        if sk["buckle"]:
            _r(s, sk["buckle"], x + 12, y + 19 + bob, 4, 6)
    arm_y = y + 15 + bob + leg
    if f > 0:
        _r(s, sk["arm"], x + 21, arm_y, 6, 11)
        _r(s, sk["arm"], x + 1, arm_y + 3, 6, 10)
    else:
        _r(s, sk["arm"], x + 1, arm_y, 6, 11)
        _r(s, sk["arm"], x + 21, arm_y + 3, 6, 10)
    _body_extras(s, sk, x, y, bob, f, "walk")
    if acc != "pigeon":
        _r(s, sk["face"], x + 5, y + 2 + bob, 18, 13)
    _eyes(s, sk, x, y, bob, f)
    _head_top(s, sk, x, y, bob, f, "walk")


def _body_extras(s, sk, x, y, bob, f, mode):
    acc = sk["acc"]
    if acc == "foreman":
        if mode == "walk":
            _r(s, (40, 56, 120), x + 12, y + 16 + bob, 4, 10)          # галстук
            _r(s, (40, 56, 120), x + 11, y + 16 + bob, 6, 3)
    elif acc == "welder":
        _r(s, (255, 150, 50), x + 4, y + 25 + bob, 20, 2)               # светоотражающая полоса
    elif acc == "pigeon":
        _r(s, (196, 202, 214), x + 8, y + 19 + bob, 12, 9)              # светлая грудка
        _r(s, (88, 170, 150), x + 8, y + 17 + bob, 12, 2)
    elif acc == "robot":
        pygame.draw.circle(s, (30, 32, 44), (x + 14, y + 22 + bob), 5)
        pygame.draw.circle(s, (255, 150, 60), (x + 14, y + 22 + bob), 3)
        _r(s, (68, 76, 98), x + 4, y + 28 + bob, 20, 2)
        pygame.draw.rect(s, BLACK, (x + 4, y + 16 + bob, 20, 14), 1)
    elif acc == "sleepy":
        for k in range(3):
            _r(s, (246, 246, 250), x + 4, y + 18 + bob + k * 4, 20, 1)   # полоски пижамы
        pygame.draw.circle(s, (255, 225, 120), (x + 18, y + 22 + bob), 2)   # звёздочка
    elif acc == "monument":
        pygame.draw.rect(s, BLACK, (x + 4, y + 16 + bob, 20, 14), 2)
        _r(s, (201, 128, 82), x + 4, y + 26 + bob, 20, 4)
        _r(s, WHITE, x + 7, y + 19 + bob, 4, 4)
        pygame.draw.rect(s, BLACK, (x + 5, y + 28 + bob, 8, 11), 1)
        pygame.draw.rect(s, BLACK, (x + 16, y + 28 + bob, 8, 11), 1)
    elif acc == "cone":
        for k in range(2):
            _r(s, (226, 230, 240), x + 4, y + 15 + bob + k * 4, 20, 1)
    elif acc == "hardhat":
        pass
