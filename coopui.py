# -*- coding: utf-8 -*-
"""Экраны кооператива: меню КО-ОП (серверы, ник, скин), создание игры, лобби, клавиатура, меню в игре.

Подмешивается в Game (main.py). Здесь только интерфейс; сеть и правила — в coop.py.
"""
import math
import time

import pygame

import battle
import coop
import netplay
import skins

WHITE = (255, 255, 255)
BLACK = (20, 20, 30)
YELLOW = (255, 204, 64)
ORANGE = (255, 133, 51)
PINK = (255, 111, 168)
RED = (235, 64, 72)
GREEN = (65, 205, 105)
LIGHT = (210, 225, 255)
BLUE = (92, 170, 255)
GREY = (96, 104, 128)
PANEL = (12, 16, 36)

MODE_COL = {"classic": GREEN, "gen": YELLOW, "battle": (255, 96, 84)}
MODE_DESC = {
    "classic": "Наша карта. Вместе собираете 25 кирпичей и строите монумент.",
    "gen": "Каждый раз новый город: башни, лифты, мосты и лестницы.",
    "battle": "Ночь, босс-робот и гранаты. Чем вас больше, тем крепче босс.",
}

RU_ROWS = ["йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю"]
EN_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
NUM_ROWS = ["1234567890", "._-:"]
SH = "sh"
BS = "bs"


class CoopUIMixin:
    _night_A = None
    _panels = None
    _skin_prev = None
    create_note = ""

    # ------------------------------------------------------------------ общее
    def night_assets(self):
        A = self._night_A
        if A is None or A["W"] != self.W:
            A = battle.build_night_assets(self)
            self._night_A = A
        return A

    def draw_night_bg(self, cam=None, cy=None):
        """Ночной город: фон меню КО-ОП, лобби и экранов ожидания."""
        A = self.night_assets()
        s = self.screen
        W = self.W
        t = self.time_global
        if cam is None:
            cam = int(t * 18)
        gdy = 0 if cy is None else self.ground_y - 468 - cy
        s.blit(A["sky"], (0, 0))
        s.blit(A["stars"][int(t * 1.4) % 2], (-(int(cam * 0.03) % 80), int(gdy * 0.15)))
        mc = A["moon_c"]
        s.blit(A["moon"], (W - 170 - int(cam * 0.03) % 40 - mc[0], 90 - mc[1] + int(gdy * 0.1)))
        if not self.lite:
            P = A["cloud_period"]
            sx = (-int(cam * 0.30)) % P - 130
            cdy = int(gdy * 0.25)
            s.blit(A["cloud"], (sx, cdy))
            s.blit(A["cloud"], (sx - P, cdy))
            off = int(cam * 0.45)
            s.blit(A["bld"], (-(off % 300) - 60, self.bld_y0 + int(gdy * 0.7)))
            s.blit(A["crane"], (-(off % 620) - 70, 140 + int(gdy * 0.6)))
        off2 = int(cam * 0.6)
        s.blit(A["hill"], (-(off2 % 260) - 80, 540 - 120 + int(gdy * 0.85)))

    def panel(self, rect, border=BLUE, alpha=205, fill=PANEL, width=3):
        rect = pygame.Rect(rect)
        if self._panels is None:
            self._panels = {}
        key = (rect.w, rect.h, fill, alpha)
        surf = self._panels.get(key)
        if surf is None:
            surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(surf, (*fill, alpha), surf.get_rect(), border_radius=14)
            surf = surf.convert_alpha()
            self._panels[key] = surf
        self.screen.blit(surf, rect.topleft)
        if border is not None:
            pygame.draw.rect(self.screen, border, rect, width, border_radius=14)

    def ui_button_off(self, rect, label, size=20):
        """Неактивная кнопка: серая, на нажатия не реагирует."""
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.screen, (24, 28, 46), rect, border_radius=12)
        pygame.draw.rect(self.screen, (64, 70, 92), rect, 3, border_radius=12)
        img = self.render(label, size, (88, 94, 116), True)
        self.screen.blit(img, img.get_rect(center=rect.center))

    def checkbox(self, rect, checked, action, color=GREEN):
        rect = pygame.Rect(rect)
        self.ui_buttons.append((rect, action))
        down = self.ui_is_down(rect)
        pygame.draw.rect(self.screen, (30, 36, 58) if not down else (60, 70, 100), rect, border_radius=8)
        pygame.draw.rect(self.screen, color, rect, 3, border_radius=8)
        if checked:
            x, y, w, h = rect
            pts = [(x + w * 0.2, y + h * 0.52), (x + w * 0.42, y + h * 0.74), (x + w * 0.8, y + h * 0.26)]
            pygame.draw.lines(self.screen, color, False, pts, 5)

    def skin_preview(self, skin, phase, scale=3):
        if self._skin_prev is None:
            self._skin_prev = {}
        key = (skin, phase, scale)
        img = self._skin_prev.get(key)
        if img is None:
            leg = (0, 5, 0, -5)[phase % 4]
            bob = (0, 1, 0, 1)[phase % 4]
            spr = self.player_spr(1, leg, bob, skin)
            img = pygame.transform.scale(spr, (spr.get_width() * scale, spr.get_height() * scale))
            self._skin_prev[key] = img
        return img

    def skin_col(self, skin):
        return skins.SKINS[skin % skins.SKIN_COUNT]["col"]

    def mode_label(self, mode):
        return coop.MODE_NAMES.get(mode, mode)

    # ------------------------------------------------------------------ вход/выход
    def coop_open(self):
        self.coop_msg = ""
        self.sel_key = None
        self.srv_scroll = 0
        self.kb = None
        self.start_browser()
        self.set_state("coop")

    def coop_back(self):
        st = self.state
        if st == "coop":
            self.stop_browser()
            self.save_prof()
            self.set_state("menu")
        elif st == "create":
            self.set_state("coop")
        elif st == "joining":
            if self.link is not None:
                self.link.close(bye=False)
                self.link = None
            self.start_browser()
            self.set_state("coop")

    def selected_server(self):
        if self.sel_key is None:
            return None
        for d in self.servers():
            if (d["ip"], d["port"]) == self.sel_key:
                return d
        return None

    # ------------------------------------------------------------------ действия кнопок
    def coop_action(self, act):
        """True, если действие кооператива обработано."""
        if not isinstance(act, str):
            return False
        if act.startswith("kb:"):
            self.kb_action(act)
            return True
        if act == "coop_open":
            self.coop_open()
        elif act == "coop_back":
            self.coop_back()
        elif act == "skin_prev":
            self.profile["skin"] = (self.profile["skin"] - 1) % skins.SKIN_COUNT
            self.save_prof()
        elif act == "skin_next":
            self.profile["skin"] = (self.profile["skin"] + 1) % skins.SKIN_COUNT
            self.save_prof()
        elif act == "nick_edit":
            self.kb_open("nick", self.profile["nick"], "ru")
        elif act == "coop_ip":
            self.kb_open("ip", self.profile.get("ip", ""), "num")
        elif act.startswith("srv:"):
            lst = self.servers()
            try:
                d = lst[int(act[4:])]
            except (ValueError, IndexError):
                return True
            self.sel_key = (d["ip"], d["port"])
        elif act == "srv_up":
            self.srv_scroll = max(0, self.srv_scroll - 1)
        elif act == "srv_down":
            self.srv_scroll += 1
        elif act == "coop_create":
            self.set_state("create")
        elif act.startswith("mode:"):
            self.coop_set_cfg(mode=act[5:])
        elif act == "pvp_toggle":
            self.coop_set_cfg(pvp=not self.coop_cfg.get("pvp", True))
        elif act == "coop_make":
            self.save_prof()
            self.coop_host_create()
        elif act == "coop_join":
            d = self.selected_server()
            if d is None:
                self.set_msg("Выбери сервер в списке.")
            elif d.get("st") != "lobby":
                self.set_msg("Игра уже идёт. Дождись, пока хост вернёт всех в лобби.")
            elif d.get("pl", 0) >= d.get("max", netplay.MAX_PLAYERS):
                self.set_msg("На сервере нет мест.")
            else:
                self.save_prof()
                self.coop_join(d["ip"], d["port"])
        elif act == "lobby_mode":
            i = coop.MODE_ORDER.index(self.coop_cfg.get("mode", "classic"))
            self.coop_set_cfg(mode=coop.MODE_ORDER[(i + 1) % len(coop.MODE_ORDER)])
        elif act == "lobby_pvp":
            self.coop_set_cfg(pvp=not self.coop_cfg.get("pvp", True))
        elif act == "lobby_start":
            self.coop_host_start()
        elif act == "coop_resume":
            self.coop_menu = False
        elif act == "coop_leave":
            self.coop_leave()
        elif act == "coop_lobby":
            self.coop_menu = False
            self.coop_to_lobby()
        elif act == "coop_retry":
            self.coop_retry()
        else:
            return False
        return True

    # ------------------------------------------------------------------ экран КО-ОП
    def draw_coop(self):
        self.draw_night_bg()
        s = self.screen
        W = self.W
        self.text(s, "КО-ОП", 40, 24, 10, BLUE, bold=True)
        self.text(s, "играем вместе по Wi-Fi", 17, 168, 30, LIGHT)

        # --- профиль: герой и ник
        skin = self.profile["skin"]
        col = self.skin_col(skin)
        self.panel((24, 64, 300, 346), border=col)
        self.text(s, "ТВОЙ ГЕРОЙ", 15, 174, 76, LIGHT, center=True, bold=True)
        box = pygame.Rect(104, 92, 140, 196)
        pygame.draw.rect(s, (22, 28, 54), box, border_radius=10)
        pygame.draw.rect(s, col, box, 2, border_radius=10)
        phase = int(self.time_global * 6) % 4
        img = self.skin_preview(skin, phase)
        pygame.draw.ellipse(s, (10, 12, 26), (box.centerx - 40, box.bottom - 30, 80, 16))
        s.blit(img, img.get_rect(midbottom=(box.centerx, box.bottom - 12)))
        self.ui_button((38, 160, 54, 56), "<", "skin_prev", 30, col)
        self.ui_button((256, 160, 54, 56), ">", "skin_next", 30, col)
        self.text(s, "%d / %d" % (skin + 1, skins.SKIN_COUNT), 13, box.centerx, box.y + 12, GREY, center=True)
        self.text(s, skins.skin_name(skin), 21, 174, 298, col, center=True, bold=True)
        f = self.font(14, False)
        for k, ln in enumerate(battle.wrap_text(f, skins.SKINS[skin]["note"], 270)[:2]):
            self.text(s, ln, 14, 174, 320 + k * 17, LIGHT, center=True)
        self.text(s, "НИК  (нажми, чтобы изменить)", 12, 38, 354, GREY)
        self.ui_button((36, 370, 276, 34), self.profile["nick"], "nick_edit", 18, YELLOW)

        # --- список серверов
        px, pw = 340, W - 364
        self.panel((px, 64, pw, 346), border=BLUE)
        self.text(s, "СЕРВЕРЫ В ЭТОЙ СЕТИ", 16, px + 16, 74, LIGHT, bold=True)
        dots = "." * (1 + int(self.time_global * 2) % 3)
        self.text(s, "поиск" + dots, 14, px + pw - 16 - self.font(14).size("поиск...")[0], 77, GREY)
        lst = self.servers()
        if self.sel_key is not None and not any((d["ip"], d["port"]) == self.sel_key for d in lst):
            self.sel_key = None
        rows = 5
        need_scroll = len(lst) > rows
        self.srv_scroll = max(0, min(self.srv_scroll, max(0, len(lst) - rows)))
        rw = pw - 24 - (46 if need_scroll else 0)
        if not lst:
            cy = 200
            if self.browser is not None and not self.browser.ok:
                self.text(s, "Не удалось слушать сеть.", 20, px + pw // 2, cy, ORANGE, center=True, bold=True)
                self.text(s, "Подключись вручную: кнопка «ПО IP».", 16, px + pw // 2, cy + 32, LIGHT, center=True)
            else:
                self.text(s, "Ищем игры в этой Wi-Fi сети" + dots, 20, px + pw // 2, cy, WHITE, center=True, bold=True)
                self.text(s, "Попроси друга нажать «СОЗДАТЬ ИГРУ» — она появится здесь.", 16, px + pw // 2, cy + 34,
                          LIGHT, center=True)
                self.text(s, "Не находит? Оба устройства в одной Wi-Fi? Или жми «ПО IP».", 14, px + pw // 2, cy + 62,
                          GREY, center=True)
        for k in range(rows):
            i = self.srv_scroll + k
            if i >= len(lst):
                break
            d = lst[i]
            r = pygame.Rect(px + 12, 102 + k * 60, rw, 54)
            sel = (d["ip"], d["port"]) == self.sel_key
            mc = MODE_COL.get(d.get("mode"), LIGHT)
            self.ui_buttons.append((r, "srv:%d" % i))
            down = self.ui_is_down(r)
            pygame.draw.rect(s, (46, 60, 104) if (sel or down) else (24, 30, 56), r, border_radius=10)
            pygame.draw.rect(s, mc if sel else (70, 82, 124), r, 3 if sel else 2, border_radius=10)
            pygame.draw.rect(s, mc, (r.x + 8, r.y + 10, 8, r.h - 20), border_radius=3)
            self.text(s, d.get("name", "?"), 20, r.x + 26, r.y + 6, WHITE, bold=True)
            n, mx = d.get("pl", 1), d.get("max", netplay.MAX_PLAYERS)
            info = "%s · %d/%d · PvP %s" % (self.mode_label(d.get("mode")), n, mx, "вкл" if d.get("pvp", True) else "выкл")
            self.text(s, info, 14, r.x + 26, r.y + 31, mc)
            lobby = d.get("st") == "lobby"
            tag = "ЛОББИ" if lobby else "В ИГРЕ"
            tc = GREEN if lobby else ORANGE
            ti = self.render(tag, 15, tc, True)
            s.blit(ti, (r.right - 14 - ti.get_width(), r.y + 8))
            ipi = self.render(d["ip"], 12, GREY, False)
            s.blit(ipi, (r.right - 14 - ipi.get_width(), r.y + 32))
        if need_scroll:
            bx = px + pw - 12 - 40
            self.ui_button((bx, 102, 40, 120), "", "srv_up", 18, LIGHT)
            self.ui_button((bx, 232, 40, 120), "", "srv_down", 18, LIGHT)
            pygame.draw.polygon(s, LIGHT, [(bx + 20, 150), (bx + 9, 172), (bx + 31, 172)])
            pygame.draw.polygon(s, LIGHT, [(bx + 20, 304), (bx + 9, 282), (bx + 31, 282)])

        # --- нижний ряд кнопок
        self.ui_button((24, 422, 300, 56), "НАЗАД", "coop_back", 22, LIGHT)
        avail = pw - 20
        w1, w2 = int(avail * 0.36), int(avail * 0.40)
        w3 = avail - w1 - w2
        self.ui_button((px, 422, w1, 56), "СОЗДАТЬ ИГРУ", "coop_create", 21, GREEN)
        ok = self.sel_key is not None
        if ok:
            self.ui_button((px + w1 + 10, 422, w2, 56), "ПРИСОЕДИНИТЬСЯ", "coop_join", 20, BLUE)
        else:
            self.ui_button_off((px + w1 + 10, 422, w2, 56), "ПРИСОЕДИНИТЬСЯ", 20)
        self.ui_button((px + w1 + w2 + 20, 422, w3, 56), "ПО IP", "coop_ip", 20, LIGHT)
        if time.time() < self.coop_msg_t and self.coop_msg:
            self.text(s, self.coop_msg, 18, W // 2, 500, (255, 170, 120), center=True, bold=True)
        elif not ok and lst:
            self.text(s, "Нажми на сервер в списке, чтобы выбрать его", 15, W // 2, 500, LIGHT, center=True)
        if self.kb is not None:
            self.draw_keyboard()

    # ------------------------------------------------------------------ создание игры
    def draw_create(self):
        self.draw_night_bg()
        s = self.screen
        W = self.W
        self.text(s, "СОЗДАТЬ ИГРУ", 38, 24, 10, GREEN, bold=True)
        self.text(s, "выбери режим — его увидят все в списке серверов", 16, 24, 54, LIGHT)
        cur = self.coop_cfg.get("mode", "classic")
        gap = 14
        cw = (W - 48 - 2 * gap) // 3
        f = self.font(15, False)
        for k, mode in enumerate(coop.MODE_ORDER):
            r = pygame.Rect(24 + k * (cw + gap), 84, cw, 190)
            mc = MODE_COL[mode]
            sel = mode == cur
            self.ui_buttons.append((r, "mode:" + mode))
            down = self.ui_is_down(r)
            self.panel(r, border=mc if sel else (70, 82, 124), alpha=230 if sel else 190,
                       fill=(30, 40, 78) if (sel or down) else PANEL, width=4 if sel else 2)
            self.text(s, self.mode_label(mode), 22 if mode != "battle" else 19, r.centerx, r.y + 30, mc, center=True,
                      bold=True)
            for j, ln in enumerate(battle.wrap_text(f, MODE_DESC[mode], cw - 28)[:5]):
                self.text(s, ln, 15, r.centerx, r.y + 70 + j * 22, WHITE if sel else LIGHT, center=True)
            if sel:
                pts = [(r.centerx - 14, r.bottom - 26), (r.centerx - 4, r.bottom - 14), (r.centerx + 16, r.bottom - 38)]
                pygame.draw.lines(s, mc, False, pts, 5)
            else:
                self.text(s, "нажми, чтобы выбрать", 12, r.centerx, r.bottom - 22, GREY, center=True)
        # PvP
        pv = self.coop_cfg.get("pvp", True)
        r = pygame.Rect(24, 290, W - 48, 62)
        self.panel(r, border=(70, 82, 124), alpha=190, width=2)
        self.checkbox((r.x + 14, r.y + 10, 42, 42), pv, "pvp_toggle", ORANGE)
        self.text(s, "PvP: прыжок на голову отнимает 1 HP", 20, r.x + 72, r.y + 8, WHITE, bold=True)
        self.text(s, "Выключи галочку, если хотите играть дружно, без подлянок.", 15, r.x + 72, r.y + 35, LIGHT)
        self.ui_buttons.append((r, "pvp_toggle"))
        # заметки
        self.text(s, "Здоровье врагов в кооперативе удвоено. Здоровье босса = обычное × число игроков.", 15, W // 2,
                  372, LIGHT, center=True)
        self.text(s, "Мест: до %d игроков. Все начнут в лобби — хост нажмёт СТАРТ." % netplay.MAX_PLAYERS, 15, W // 2,
                  396, LIGHT, center=True)
        self.ui_button((24, 430, 200, 56), "НАЗАД", "coop_back", 22, LIGHT)
        self.ui_button((240, 430, W - 264, 56), "СОЗДАТЬ", "coop_make", 26, GREEN)
        if time.time() < self.coop_msg_t and self.coop_msg:
            self.text(s, self.coop_msg, 18, W // 2, 506, (255, 170, 120), center=True, bold=True)

    # ------------------------------------------------------------------ подключение
    def draw_joining(self):
        self.draw_night_bg()
        s = self.screen
        W = self.W
        r = pygame.Rect(W // 2 - 260, 150, 520, 200)
        self.panel(r, border=BLUE)
        dots = "." * (1 + int(self.time_global * 3) % 3)
        self.text(s, "ПОДКЛЮЧАЕМСЯ" + dots, 32, W // 2, r.y + 52, BLUE, center=True, bold=True)
        tgt = self.join_target
        if tgt:
            self.text(s, "хост: %s" % tgt[0], 18, W // 2, r.y + 100, LIGHT, center=True)
        self.text(s, "Заходим в лобби — там можно побегать, пока хост не начнёт.", 15, W // 2, r.y + 134, GREY, center=True)
        self.ui_button((W // 2 - 110, r.y + 214, 220, 50), "ОТМЕНА", "coop_back", 20, LIGHT)

    # ------------------------------------------------------------------ лобби и общий оверлей
    def draw_coop_overlay(self):
        """Поверх мира в кооперативе: лобби, список напарников, меню."""
        if self.coop_lobby:
            self.draw_lobby_ui()
        else:
            self.draw_team_hud()
        if self.coop_menu:
            self.draw_coop_menu()

    def draw_lobby_ui(self):
        s = self.screen
        W = self.W
        host = self.role == "host"
        # шапка
        self.panel((10, 8, 330, 90), border=BLUE, alpha=190)
        self.text(s, "ЛОББИ", 26, 24, 12, BLUE, bold=True)
        mode = self.coop_cfg.get("mode", "classic")
        self.text(s, self.mode_label(mode), 16, 24, 46, MODE_COL.get(mode, LIGHT), bold=True)
        pv = self.coop_cfg.get("pvp", True)
        self.text(s, "PvP: " + ("ВКЛ" if pv else "ВЫКЛ"), 15, 24, 70, ORANGE if pv else GREEN, bold=True)
        if host:
            self.text(s, "IP: %s" % (self.my_ip or "?"), 14, 150, 72, LIGHT)
        # список игроков
        n = len(self.roster)
        pw = 250
        px = W - pw - 60
        self.panel((px, 8, pw, 48 + 26 * max(1, n)), border=GREEN, alpha=190)
        self.text(s, "ИГРОКИ  %d/%d" % (n, netplay.MAX_PLAYERS), 15, px + 14, 14, GREEN, bold=True)
        for i, r in enumerate(self.roster):
            y = 42 + i * 26
            col = self.skin_col(r.get("skin", 0))
            pygame.draw.rect(s, col, (px + 14, y + 4, 12, 12), border_radius=3)
            pygame.draw.rect(s, BLACK, (px + 14, y + 4, 12, 12), 1, border_radius=3)
            me = r["pid"] == self.my_pid
            tag = r["nick"] + ("  (ты)" if me else "") + ("  ★" if r["pid"] == 0 else "")
            self.text(s, tag, 16, px + 34, y, YELLOW if me else WHITE, bold=me)
        # управление хоста
        cx = W // 2
        if host:
            self.ui_button((10, 106, 160, 36), "РЕЖИМ", "lobby_mode", 16, MODE_COL.get(mode, LIGHT))
            self.ui_button((178, 106, 160, 36), "PvP", "lobby_pvp", 16, ORANGE if pv else GREEN)
            self.ui_button((cx - 120, 466, 240, 58), "СТАРТ", "lobby_start", 30, GREEN, icon="play")
            self.text(s, "Бегай и прыгай, пока все собираются", 15, cx, 450, LIGHT, center=True)
        else:
            self.text(s, "Ждём, пока хост нажмёт СТАРТ", 22, cx, 478, WHITE, center=True, bold=True)
            self.text(s, "Пока можно побегать и попрыгать", 15, cx, 506, LIGHT, center=True)

    def draw_team_hud(self):
        s = self.screen
        W = self.W
        me = self.player
        y = 54
        for q in self.players.values():
            if q is me:
                continue
            col = self.skin_col(q.skin)
            pygame.draw.rect(s, col, (10, y + 3, 11, 11), border_radius=3)
            pygame.draw.rect(s, BLACK, (10, y + 3, 11, 11), 1, border_radius=3)
            self.text(s, q.nick, 14, 26, y, WHITE, bold=True)
            nw = self.font(14, True).size(q.nick)[0]
            if q.dead:
                self.text(s, "выбыл", 13, 26 + nw + 8, y + 1, RED, bold=True)
            else:
                for i in range(5):
                    spr, c = self.heart_spr(4, PINK if i < q.hp else (90, 95, 110))
                    s.blit(spr, (26 + nw + 10 + i * 11 - c, y + 8 - c))
            y += 19
        if me.dead:
            cx = W // 2
            sec = max(0, int(math.ceil(me.respawn_t)))
            self.text(s, "ТЫ ВЫБЫЛ", 34, cx, 120, RED, center=True, bold=True)
            if sec > 0:
                self.text(s, "Возрождение через %d с" % sec, 20, cx, 156, WHITE, center=True)
            fp = self.focus_player()
            if fp is not me and fp.nick:
                self.text(s, "Смотришь за: " + fp.nick, 16, cx, 184, LIGHT, center=True)

    def draw_coop_menu(self):
        s = self.screen
        W = self.W
        self.ui_buttons = []
        self.overlay((6, 8, 20), 170)
        cx = W // 2
        host = self.role == "host"
        self.panel((cx - 200, 70, 400, 400), border=BLUE, alpha=235)
        self.text(s, "МЕНЮ КО-ОПА", 30, cx, 104, BLUE, center=True, bold=True)
        self.text(s, "Мир не останавливается!", 15, cx, 138, LIGHT, center=True)
        self.ui_button((cx - 170, 164, 340, 54), "ПРОДОЛЖИТЬ", "coop_resume", 24, GREEN, icon="play")
        self.ui_button((cx - 170, 230, 165, 46), self.sound_label(), "sound", 17, LIGHT)
        if host and not self.coop_lobby:
            self.ui_button((cx + 5, 230, 165, 46), "В ЛОББИ", "coop_lobby", 18, YELLOW)
        else:
            self.ui_button((cx + 5, 230, 165, 46), self.fps_label(), "fps", 17, LIGHT)
        self.ui_button((cx - 170, 292, 340, 50), "ЗАКРЫТЬ ИГРУ" if host else "ВЫЙТИ ИЗ ИГРЫ", "coop_leave", 20, RED)
        self.text(s, "хост закрывает игру для всех" if host else "хост и остальные продолжат без тебя", 14, cx, 362,
                  GREY, center=True)

    def coop_end_buttons(self, cx, y, kind):
        """Кнопки на экранах победы / поражения в кооперативе."""
        if self.role == "host":
            if kind == "gameover":
                self.ui_button((cx - 282, y, 180, 52), "ЕЩЁ РАЗ", "coop_retry", 20, GREEN)
                self.ui_button((cx - 90, y, 180, 52), "В ЛОББИ", "coop_lobby", 20, YELLOW)
                self.ui_button((cx + 102, y, 180, 52), "ВЫЙТИ", "coop_leave", 20, LIGHT)
            else:
                self.ui_button((cx - 245, y, 230, 52), "В ЛОББИ", "coop_lobby", 22, GREEN)
                self.ui_button((cx + 15, y, 230, 52), "ВЫЙТИ", "coop_leave", 22, LIGHT)
        else:
            self.text(self.screen, "Ждём решения хоста...", 17, cx, y + 6, LIGHT, center=True, bold=True)
            self.ui_button((cx - 100, y + 24, 200, 42), "ВЫЙТИ", "coop_leave", 19, LIGHT)

    # ------------------------------------------------------------------ экранная клавиатура
    def kb_open(self, target, text, lay):
        self.kb = {"t": target, "text": text, "lay": lay, "shift": not text and lay != "num", "caret": 0.0}
        self.dirty = True

    def kb_limit(self):
        return coop.NICK_MAX if self.kb["t"] == "nick" else 21

    def kb_allowed(self, ch):
        if self.kb["t"] == "ip":
            return ch.isdigit() or ch in ".:"
        return ch.isalnum() or ch in " _-."

    def kb_add(self, ch):
        kb = self.kb
        if not self.kb_allowed(ch) or len(kb["text"]) >= self.kb_limit():
            return
        if ch == " " and (not kb["text"] or kb["text"].endswith(" ")):
            return
        kb["text"] += ch
        if kb["shift"] and kb["lay"] != "num":
            kb["shift"] = False
        self.dirty = True

    def kb_textinput(self, text):
        for ch in text:
            self.kb_add(ch)

    def kb_keydown(self, e):
        k = e.key
        if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.kb_confirm()
        elif k == pygame.K_BACKSPACE:
            self.kb["text"] = self.kb["text"][:-1]
            self.dirty = True
        elif k in (pygame.K_ESCAPE, getattr(pygame, "K_AC_BACK", -1)):
            self.kb = None
            self.dirty = True

    def kb_action(self, act):
        kb = self.kb
        if kb is None:
            return
        parts = act.split(":", 2)
        cmd = parts[1]
        if cmd == "c":
            ch = parts[2]
            if kb["shift"] and kb["lay"] != "num":
                ch = ch.upper()
            self.kb_add(ch)
        elif cmd == "sp":
            self.kb_add(" ")
        elif cmd == "bs":
            kb["text"] = kb["text"][:-1]
            if not kb["text"] and kb["lay"] != "num":
                kb["shift"] = True
        elif cmd == "sh":
            kb["shift"] = not kb["shift"]
        elif cmd == "lay":
            kb["lay"] = parts[2]
        elif cmd == "ok":
            self.kb_confirm()
        elif cmd == "x":
            self.kb = None
        self.dirty = True

    def kb_confirm(self):
        kb = self.kb
        if kb is None:
            return
        self.kb = None
        text = kb["text"].strip()
        if kb["t"] == "nick":
            nick = coop.clean_nick(text) or coop.DEFAULT_NICK
            self.profile["nick"] = nick
            self.save_prof()
        else:
            if not text:
                return
            ip, _, port = text.partition(":")
            try:
                port = int(port) if port else netplay.GAME_PORT
            except ValueError:
                port = netplay.GAME_PORT
            if ip.count(".") != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in ip.split(".")):
                self.set_msg("Это не похоже на IP-адрес. Пример: 192.168.1.5")
                return
            self.profile["ip"] = text
            self.save_prof()
            self.coop_join(ip, port)
        self.dirty = True

    def kb_rows(self):
        kb = self.kb
        lay = kb["lay"]
        rows = []
        if lay == "ru":
            src = RU_ROWS
        elif lay == "en":
            src = EN_ROWS
        else:
            src = ["1234567890", "._-" if kb["t"] == "nick" else ".:"]
        up = kb["shift"] and lay != "num"
        for i, row in enumerate(src):
            keys = [("kb:c:" + ch, ch.upper() if up else ch, 1.0) for ch in row]
            if lay != "num" and i == len(src) - 1:
                keys = [("kb:sh", SH, 1.5)] + keys + [("kb:bs", BS, 1.5)]
            elif lay == "num" and i == len(src) - 1:
                keys = keys + [("kb:bs", BS, 2.0)]
            rows.append(keys)
        bottom = []
        if kb["t"] == "nick":
            if lay == "ru":
                sw = [("num", "123"), ("en", "EN")]
            elif lay == "en":
                sw = [("num", "123"), ("ru", "РУС")]
            else:
                sw = [("ru", "РУС"), ("en", "EN")]
            bottom.append(("kb:lay:" + sw[0][0], sw[0][1], 1.5))
            bottom.append(("kb:lay:" + sw[1][0], sw[1][1], 1.5))
            bottom.append(("kb:sp", "пробел", 6.0))
            bottom.append(("kb:ok", "OK", 3.0))
        else:
            bottom.append(("kb:x", "ОТМЕНА", 4.0))
            bottom.append(("kb:ok", "ПОДКЛЮЧИТЬСЯ", 8.0))
        rows.append(bottom)
        return rows

    def draw_keyboard(self):
        kb = self.kb
        s = self.screen
        W = self.W
        self.ui_buttons = []
        self.overlay((4, 6, 18), 215)
        title = "ТВОЙ НИК" if kb["t"] == "nick" else "IP-АДРЕС ХОСТА (можно с портом: 192.168.1.5:47311)"
        self.text(s, title, 18, W // 2, 196, LIGHT, center=True, bold=True)
        fr = pygame.Rect(24, 216, W - 48, 62)
        pygame.draw.rect(s, (20, 26, 52), fr, border_radius=12)
        pygame.draw.rect(s, YELLOW, fr, 3, border_radius=12)
        txt = kb["text"]
        if txt:
            img = self.render(txt, 32, WHITE, True)
            tw = img.get_width()
        else:
            img = self.render("введи " + ("ник" if kb["t"] == "nick" else "адрес"), 26, GREY, True)
            tw = 0
        s.blit(img, img.get_rect(midleft=(fr.x + 18, fr.centery)))
        if int(time.time() * 2) % 2 == 0:
            pygame.draw.rect(s, YELLOW, (fr.x + 18 + tw + 3, fr.centery - 18, 3, 36))
        cnt = "%d/%d" % (len(txt), self.kb_limit())
        ci = self.render(cnt, 14, GREY, False)
        s.blit(ci, (fr.right - 14 - ci.get_width(), fr.bottom - 22))
        rows = self.kb_rows()
        unit = (W - 28) / 12.0
        rh = 54
        y0 = 540 - len(rows) * (rh + 4) - 6
        if y0 < 286:
            y0 = 286
        for ri, row in enumerate(rows):
            total = sum(k[2] for k in row)
            x = 14 + (W - 28 - total * unit) / 2.0
            y = y0 + ri * (rh + 4)
            for act, label, w in row:
                r = pygame.Rect(int(x) + 2, y, int(w * unit) - 4, rh)
                x += w * unit
                self.ui_buttons.append((r, act))
                down = self.ui_is_down(r)
                special = act in ("kb:sh", "kb:bs", "kb:ok", "kb:x") or act.startswith("kb:lay")
                active = act == "kb:sh" and kb["shift"]
                base = (60, 74, 120) if down else ((44, 54, 92) if special else (28, 34, 62))
                if active:
                    base = (92, 110, 170)
                pygame.draw.rect(s, base, r, border_radius=9)
                bc = GREEN if act == "kb:ok" else (YELLOW if active else (96, 108, 156))
                pygame.draw.rect(s, bc, r, 2, border_radius=9)
                c = r.center
                if act == "kb:sh":
                    col = YELLOW if active else LIGHT
                    pygame.draw.polygon(s, col, [(c[0], c[1] - 13), (c[0] + 14, c[1] + 1), (c[0] + 6, c[1] + 1),
                                                 (c[0] + 6, c[1] + 12), (c[0] - 6, c[1] + 12), (c[0] - 6, c[1] + 1),
                                                 (c[0] - 14, c[1] + 1)])
                elif act == "kb:bs":
                    pts = [(c[0] - 18, c[1]), (c[0] - 6, c[1] - 12), (c[0] + 16, c[1] - 12), (c[0] + 16, c[1] + 12),
                           (c[0] - 6, c[1] + 12)]
                    pygame.draw.polygon(s, LIGHT, pts, 3)
                    pygame.draw.line(s, LIGHT, (c[0] - 2, c[1] - 6), (c[0] + 9, c[1] + 6), 3)
                    pygame.draw.line(s, LIGHT, (c[0] - 2, c[1] + 6), (c[0] + 9, c[1] - 6), 3)
                else:
                    size = (24 if label.isalnum() else 34) if len(label) <= 2 else (17 if len(label) < 8 else 15)
                    li = self.render(label, size, GREEN if act == "kb:ok" else WHITE, True)
                    s.blit(li, li.get_rect(center=c))
