# -*- coding: utf-8 -*-
"""Кооператив по Wi-Fi: логика (профиль, хост/клиент, лобби, снимки мира, события).

Схема:
  * Хост считает весь мир (враги, голуби, предметы, босс) и рассылает снимки ~30 раз в секунду.
  * Каждый игрок сам считает физику своего героя (прыжки не лагают) и шлёт хосту позицию.
  * Всё, что решает судьбу (урон, подбор, смерть, победа), решает хост.
Подмешивается в Game (main.py). Рисование экранов — в coopui.py.
"""
import json
import os
import random
import time

import pygame

import netplay
import skins

SEND_HZ = 30.0
RESPAWN_TIME = 8.0
MODE_ORDER = ("classic", "gen", "battle")
MODE_NAMES = {"classic": "КЛАССИКА", "gen": "ГЕНЕРАЦИЯ", "battle": "БИТВА ЗА ПИСЮН"}
NICK_MAX = 12
DEFAULT_NICK = "Строитель"
COOP_UI_STATES = ("coop", "create", "joining")


# ---------------------------------------------------------------------------
# профиль (ник и скин сохраняются при выходе)
# ---------------------------------------------------------------------------
def profile_path():
    p = os.environ.get("PISUN_PROFILE")
    if p:
        return p
    base = os.environ.get("ANDROID_PRIVATE") or os.environ.get("ANDROID_ARGUMENT") or os.path.expanduser("~")
    return os.path.join(base, "pisun_profile.json")


def clean_nick(s):
    s = "".join(ch for ch in str(s) if ch.isalnum() or ch in " _-.")
    s = " ".join(s.split())[:NICK_MAX].strip()
    return s


def load_profile():
    d = {"nick": DEFAULT_NICK, "skin": 0, "ip": ""}
    try:
        with open(profile_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        nick = clean_nick(raw.get("nick", ""))
        if nick:
            d["nick"] = nick
        d["skin"] = int(raw.get("skin", 0)) % skins.SKIN_COUNT
        d["ip"] = str(raw.get("ip", ""))[:40]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return d


def save_profile(d):
    try:
        with open(profile_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


def _r1(v):
    return round(v, 1)


class CoopMixin:
    # значения по умолчанию на уровне класса: Game.__init__ обращается к ним раньше coop_init()
    role = None                 # None (одиночная) | "host" | "client"
    bc = False                  # True, пока хост считает «мир»: звуки/частицы улетают всем
    _shake = 0.0
    _shake_amp = 5.0
    net_shake = 0.0
    net_amp = 0.0
    coop_lobby = False
    pvp = False

    # ---------- тряска экрана: события боя, видимые всем ----------
    @property
    def shake(self):
        return self._shake

    @shake.setter
    def shake(self, v):
        if self.bc and v > self._shake:
            self.net_shake = max(self.net_shake, v)
        self._shake = v

    @property
    def shake_amp(self):
        return self._shake_amp

    @shake_amp.setter
    def shake_amp(self, v):
        if self.bc:
            self.net_amp = max(self.net_amp, v)
        self._shake_amp = v

    # ---------- создание ----------
    def coop_init(self):
        self.profile = load_profile()
        self.server = None
        self.link = None
        self.announcer = None
        self.browser = None
        self.players = {}
        self.my_pid = 0
        self.roster = []
        self.coop_cfg = {"mode": "classic", "pvp": True}
        self.coop_phase = "lobby"          # lobby | game
        self.coop_menu = False
        self.coop_msg = ""
        self.coop_msg_t = 0.0
        self.sel_key = None
        self.srv_scroll = 0
        self.kb = None
        self.fx_out = []
        self.gid = 0
        self.snap_seq = 0
        self.rx_seq = -1
        self.send_t = 0.0
        self.snap_t = 0.0
        self.pk_dirty = True
        self.pk_sent_t = 0.0
        self.sup_dirty = True
        self.last_tap_t = 0.0
        self.join_t = 0.0
        self.join_target = None
        self.lobby_lvl = None
        self.my_ip = ""
        self.pending_msgs = []
        self.ka_t = 0.0
        self.sup_sent_t = 0.0

    # ---------- вспомогательное ----------
    def set_msg(self, text, secs=5.0):
        self.coop_msg = text
        self.coop_msg_t = time.time() + secs
        self.dirty = True

    def start_browser(self):
        if self.browser is None:
            self.browser = netplay.Browser()

    def stop_browser(self):
        if self.browser is not None:
            self.browser.close()
            self.browser = None

    def servers(self):
        if self.browser is None:
            return []
        self.browser.poll()
        return self.browser.servers()

    def save_prof(self):
        save_profile(self.profile)

    def alive_players(self):
        return [p for p in self.players.values() if not p.dead]

    def nearest_player(self, x, y):
        best, bd = None, 1e18
        for p in self.players.values():
            if p.dead:
                continue
            d = (p.rect.centerx - x) ** 2 + (p.rect.centery - y) ** 2
            if d < bd:
                bd, best = d, p
        return best if best is not None else self.player

    def focus_player(self):
        """За кем следит камера: за собой, а если выбыл — за живым напарником."""
        if not self.player.dead:
            return self.player
        for q in self.players.values():
            if not q.dead:
                return q
        return self.player

    def lead_col(self):
        """Колонка самого продвинутого живого игрока (для сюжетных триггеров)."""
        cols = [q.rect.centerx // 36 for q in self.alive_players()]
        return max(cols) if cols else self.player.rect.centerx // 36

    # ---------- сетевая отправка ----------
    def net_send(self, pid, msg):
        if self.role == "host" and self.server is not None:
            self.server.send(pid, msg)

    def net_broadcast(self, msg, droppable=False):
        if self.role == "host" and self.server is not None:
            self.server.broadcast(msg, droppable)

    def net_to_host(self, msg, droppable=False):
        if self.role == "client" and self.link is not None:
            self.link.send(msg, droppable)

    # ---------- лобби / запуск ----------
    def lobby_level(self):
        if self.lobby_lvl is None:
            import levelgen
            L = levelgen.Level("lobby")
            L.cols, L.rows, L.ground_row = 56, 15, 13
            L.solids = [(-8, 13, 72, 2, "ground", 0),
                        (14, 11, 3, 2, "crate", 0), (30, 12, 1, 1, "crate", 0), (31, 11, 1, 2, "crate", 0)]
            L.oneway = [(5, 10, 5, "scaf", 0), (19, 9, 6, "scaf", 0), (11, 7, 4, "scaf", 0),
                        (27, 9, 4, "scaf", 0), (35, 10, 5, "scaf", 0)]
            L.decor = [("prop", "lamp", 3, 13), ("prop", "cone", 12, 13), ("prop", "barrel", 17, 13),
                       ("prop", "lamp", 26, 13), ("prop", "sign", 8, 13), ("prop", "cone", 33, 13),
                       ("prop", "barrel", 21, 13)]
            L.districts = [(0, "ЛОББИ", 0)]
            L.zone_tx = 40
            L.spawn = (4.0, 11)
            self.lobby_lvl = L
        return self.lobby_lvl

    def enter_lobby(self):
        """Все (хост и клиенты) собираются в комнате-лобби."""
        self.coop_lobby = True
        self.coop_phase = "lobby"
        self.coop_menu = False
        self.pvp = bool(self.coop_cfg.get("pvp", True))
        L = self.lobby_level()
        if L is not self.lvl:
            self.setup_level(L)
        self.reset_game()
        self.build_controls(*self.win_size)
        self.set_state("play")

    def coop_host_create(self):
        try:
            self.server = netplay.HostServer()
        except OSError:
            self.set_msg("Не удалось открыть порт. Закрой другую копию игры.")
            return False
        self.announcer = netplay.Announcer()
        self.stop_browser()
        self.role = "host"
        self.my_pid = 0
        self.roster = [{"pid": 0, "nick": self.profile["nick"], "skin": self.profile["skin"]}]
        self.my_ip = netplay.local_ip()
        self.rx_seq = -1
        self.enter_lobby()
        return True

    def coop_host_start(self):
        """Хост нажал СТАРТ."""
        if self.role != "host" or not self.coop_lobby:
            return
        mode = self.coop_cfg["mode"]
        seed = random.randrange(1, 1000000) if mode == "gen" else 0
        self.gid += 1
        self.coop_phase = "game"
        self.net_broadcast({"t": "start", "mode": mode, "seed": seed, "pvp": self.coop_cfg["pvp"],
                            "roster": self.roster, "gid": self.gid})
        self.pending = ("coop", mode, seed)
        self.set_state("loading")

    def coop_start_level(self, mode, seed):
        self.coop_lobby = False
        self.coop_menu = False
        self.pvp = bool(self.coop_cfg.get("pvp", True))
        self.pk_dirty = True
        self.sup_dirty = True
        self.rx_seq = -1
        self.snap_seq = 0
        self.start_level(mode, seed or None)

    def coop_to_lobby(self):
        """Хост возвращает всех в лобби."""
        if self.role != "host":
            return
        self.gid += 1
        self.net_broadcast({"t": "lobby", "gid": self.gid, "cfg": self.coop_cfg})
        self.enter_lobby()

    def coop_set_cfg(self, **kw):
        self.coop_cfg.update(kw)
        self.pvp = bool(self.coop_cfg.get("pvp", True))
        if self.role == "host":
            self.net_broadcast({"t": "cfg", "cfg": self.coop_cfg})
        self.dirty = True

    def coop_join(self, ip, port):
        self.stop_browser()
        hello = {"t": "hello", "v": netplay.PROTO, "nick": self.profile["nick"], "skin": self.profile["skin"]}
        self.link = netplay.ClientLink(ip, port, hello)
        self.join_target = (ip, port)
        self.join_t = time.time()
        self.set_state("joining")

    def coop_leave(self, msg=""):
        """Выйти из кооператива в главное меню (или в окно КО-ОП, если есть сообщение)."""
        was_host = self.role == "host"
        if self.server is not None:
            for pid in list(self.server.conns):
                self.server.send(pid, {"t": "bye"})
            self.server.close()
            self.server = None
        if self.announcer is not None:
            self.announcer.close()
            self.announcer = None
        if self.link is not None:
            self.link.close()
            self.link = None
        self.role = None
        self.coop_lobby = False
        self.coop_menu = False
        self.kb = None
        self.players = {}
        self.roster = []
        self.bc = False
        self.pvp = False
        if self.mode != "classic" or self.lvl is not self.classic:
            self.setup_level(self.classic)
        self.reset_game()
        self.build_controls(*self.win_size)
        if msg:
            self.set_msg(msg)
            self.start_browser()
            self.set_state("coop")
        else:
            self.set_state("menu")
        return was_host

    # ---------- главный сетевой цикл (раз в кадр) ----------
    def net_pump(self, dt):
        if self.state in COOP_UI_STATES and self.browser is not None:
            self.browser.poll()
        if self.role is not None:
            self.ka_t += dt                      # «я жив»: чтобы связь не рвалась на экранах без игры
            if self.ka_t > 2.0:
                self.ka_t = 0.0
                if self.role == "host":
                    self.net_broadcast({"t": "ping"})
                else:
                    self.net_to_host({"t": "ping"})
        if self.role == "host" and self.server is not None:
            for ev in self.server.poll():
                self.host_event(ev)
            self.announcer.tick(dt, self.host_info())
        elif self.role == "client" or self.state == "joining":
            self.client_pump()

    def host_info(self):
        return {"g": "pisun", "v": netplay.PROTO, "port": self.server.port,
                "name": self.profile["nick"], "mode": self.coop_cfg["mode"],
                "pl": len(self.roster), "max": netplay.MAX_PLAYERS,
                "st": "lobby" if self.coop_phase == "lobby" else "play", "pvp": bool(self.coop_cfg["pvp"])}

    # ---------- хост: события ----------
    def host_event(self, ev):
        kind = ev[0]
        if kind == "hello":
            self.host_hello(ev[1], ev[2])
        elif kind == "msg":
            self.host_msg(ev[1], ev[2])
        elif kind == "leave":
            self.host_leave(ev[1])

    def host_hello(self, conn, m):
        def deny(why):
            conn.send({"t": "deny", "why": why})
            conn.flush_close()
        if m.get("v") != netplay.PROTO:
            return deny("Разные версии игры. Обнови приложение.")
        if self.coop_phase != "lobby" or not self.coop_lobby:
            return deny("Игра уже идёт. Дождись, пока хост вернёт всех в лобби.")
        if len(self.roster) >= netplay.MAX_PLAYERS:
            return deny("На сервере нет мест.")
        used = {r["pid"] for r in self.roster}
        pid = next(i for i in range(1, 64) if i not in used)
        nick = clean_nick(m.get("nick", "")) or DEFAULT_NICK
        try:
            skin = int(m.get("skin", 0)) % skins.SKIN_COUNT
        except (TypeError, ValueError):
            skin = 0
        self.server.admit(conn, pid)
        self.roster.append({"pid": pid, "nick": nick, "skin": skin})
        L = self.lvl
        q = self.make_remote_player(pid, nick, skin)
        self.players[pid] = q
        self.server.send(pid, {"t": "welcome", "pid": pid, "roster": self.roster, "cfg": self.coop_cfg,
                               "gid": self.gid})
        self.net_broadcast({"t": "roster", "roster": self.roster})
        self.float_text(q.rect.centerx, q.rect.top - 20, nick + " зашёл", (150, 255, 170))
        self.dirty = True

    def host_leave(self, pid):
        self.roster = [r for r in self.roster if r["pid"] != pid]
        q = self.players.pop(pid, None)
        if q is not None:
            self.float_text(q.rect.centerx, q.rect.top - 20, q.nick + " вышел", (255, 190, 150))
        self.net_broadcast({"t": "roster", "roster": self.roster})
        self.dirty = True

    def host_msg(self, pid, m):
        t = m.get("t")
        q = self.players.get(pid)
        if q is None:
            return
        if t == "st":
            if m.get("g") != self.gid or m.get("e", 0) != q.epoch:
                return
            q.rect.x = int(m.get("x", q.rect.x))
            q.rect.y = int(m.get("y", q.rect.y))
            q.vel.x = float(m.get("vx", 0))
            q.vel.y = float(m.get("vy", 0))
            q.facing = 1 if m.get("f", 1) >= 0 else -1
            q.anim = float(m.get("a", 0))
            q.on_ground = bool(m.get("og", 0))
            q.climb = 1 if m.get("c") else None
            q.net_t = time.time()
            if q.invuln > 50:                # первый пакет после загрузки уровня: клиент готов
                q.invuln = 1.0
        elif t == "tap":
            bt = self.battle
            if bt is not None and time.time() - self.last_tap_t > 0.25:
                self.last_tap_t = time.time()
                bt.tap_dialog()
        elif t == "build":
            bt = self.battle
            if bt is not None and bt.can_build_for(q):
                self.bc = True
                try:
                    bt.start_build(q)
                finally:
                    self.bc = False
        elif t == "throw":
            bt = self.battle
            if bt is not None and self.state == "play":
                self.bc = True
                try:
                    bt.throw(q)
                finally:
                    self.bc = False
        elif t == "bye":
            self.server.conns[pid]._fail("вышел")

    # ---------- клиент: события ----------
    def client_pump(self):
        link = self.link
        if link is None:
            return
        msgs = link.poll()
        if link.dead and self.role != "client":
            if self.state == "joining":
                err = link.error or "нет ответа"
                self.link.close(bye=False)
                self.link = None
                self.start_browser()
                self.set_msg("Не удалось подключиться: " + err)
                self.set_state("coop")
            return
        if link.dead and self.role == "client":
            self.coop_leave("Связь с хостом потеряна.")
            return
        if self.state == "joining" and time.time() - self.join_t > 9.0:
            self.link.close(bye=False)
            self.link = None
            self.start_browser()
            self.set_msg("Хост не ответил.")
            self.set_state("coop")
            return
        # из снимков применяем только последний; события (fx) — из всех
        last_snap = None
        for m in msgs:
            if m.get("t") == "s":
                if last_snap is not None:
                    self.fx_apply(last_snap.get("fx"))
                last_snap = m
            else:
                if last_snap is not None:
                    self.apply_snapshot(last_snap)
                    last_snap = None
                self.client_msg(m)
                if self.link is None:
                    return
        if last_snap is not None:
            self.apply_snapshot(last_snap)

    def client_msg(self, m):
        t = m.get("t")
        if t == "welcome":
            self.role = "client"
            self.my_pid = int(m["pid"])
            self.roster = m.get("roster", [])
            self.coop_cfg = m.get("cfg", self.coop_cfg)
            self.gid = int(m.get("gid", 0))
            self.rx_seq = -1
            self.enter_lobby()
        elif t == "deny":
            why = m.get("why", "Отказ.")
            if self.link is not None:
                self.link.close(bye=False)
                self.link = None
            self.start_browser()
            self.set_msg(why)
            self.set_state("coop")
        elif t == "roster":
            self.sync_roster(m.get("roster", []))
        elif t == "cfg":
            self.coop_cfg = m.get("cfg", self.coop_cfg)
            self.pvp = bool(self.coop_cfg.get("pvp", True))
            self.dirty = True
        elif t == "start":
            self.gid = int(m.get("gid", 0))
            self.roster = m.get("roster", self.roster)
            self.coop_cfg["mode"] = m.get("mode", "classic")
            self.coop_cfg["pvp"] = bool(m.get("pvp", True))
            self.coop_phase = "game"
            self.pending = ("coop", m.get("mode", "classic"), int(m.get("seed", 0)))
            self.set_state("loading")
        elif t == "lobby":
            self.gid = int(m.get("gid", self.gid))
            self.coop_cfg = m.get("cfg", self.coop_cfg)
            self.enter_lobby()
        elif t == "hurt":
            if self.state == "play":
                self.local_hurt_fx(float(m.get("sx", self.player.rect.centerx)), fx=False)
        elif t == "bounce":
            self.player.vel.y = -400
        elif t == "respawn":
            self.apply_respawn(m)
        elif t == "state":
            self.apply_state_msg(m)
        elif t == "retry":
            self.apply_retry_msg(m)
        elif t == "bsay":
            if self.battle is not None:
                self.battle.net_say(m)
        elif t == "bye":
            self.coop_leave("Хост закрыл игру.")

    def sync_roster(self, roster):
        self.roster = roster
        ids = {r["pid"] for r in roster}
        for pid in list(self.players):
            if pid not in ids:
                del self.players[pid]
        for r in roster:
            q = self.players.get(r["pid"])
            if q is None:
                if r["pid"] == self.my_pid:
                    continue
                self.players[r["pid"]] = self.make_remote_player(r["pid"], r["nick"], r["skin"])
            else:
                q.nick, q.skin = r["nick"], r["skin"]
        self.dirty = True

    def apply_respawn(self, m):
        p = self.player
        p.rect.topleft = (int(m["x"]), int(m["y"]))
        p.vel.update(0, 0)
        p.climb = None
        p.dead = False
        p.invuln = float(m.get("inv", 2.0))
        p.epoch = int(m.get("e", p.epoch))
        p.dx, p.dy = float(p.rect.x), float(p.rect.y)
        self.camera_x = self.camera_x  # камера доедет сама
        if m.get("fx", 1):
            self.play("hurt")

    def apply_state_msg(self, m):
        st = m.get("st")
        self.score = m.get("sc", self.score)
        self.bolts = m.get("bo", self.bolts)
        self.bricks_collected = m.get("bk", self.bricks_collected)
        self.elapsed = m.get("el", self.elapsed)
        bt = self.battle
        if bt is not None:
            bt.net_result(m)
        if st in ("win", "gameover", "bwin"):
            if st == "win":
                self.win_timer = 0.0
                self.flash_timer = 0.0
                self.firework_timer = 0.0
                bx, by, cell = self._bo
                self.burst(bx + cell * 2, by - 10, [(255, 204, 64), (255, 111, 168), (255, 255, 255), (65, 205, 105)],
                           45, 380, 1.0, 6)
            self.set_state(st)

    def apply_retry_msg(self, m):
        """Хост начал заново: бой с боссом — с места боя, остальное — с начала карты."""
        self.gid = int(m.get("gid", self.gid))
        self.rx_seq = -1
        self.pk_dirty = True
        bt = self.battle
        if bt is not None and m.get("boss") and bt.can_retry():
            bt.net_retry()
        else:
            self.reset_game()
        self.set_state("play")

    def coop_retry(self):
        """Хост: «ещё раз» после поражения."""
        if self.role != "host":
            return
        self.gid += 1
        bt = self.battle
        boss = bt is not None and bt.can_retry()
        self.rx_seq = -1
        self.snap_seq = 0
        self.pk_dirty = True
        self.sup_dirty = True
        if boss:
            bt.retry_boss()
        else:
            self.reset_game()
        self.net_broadcast({"t": "retry", "gid": self.gid, "boss": 1 if boss else 0})
        self.set_state("play")

    # ---------- игроки ----------
    def make_remote_player(self, pid, nick, skin):
        sx, sy = self.lvl.spawn
        q = self.PlayerCls(int(sx * 36) + 30 * (len(self.players) % 6), int(sy * 36), pid, nick, skin, True)
        q.invuln = 99.0
        return q

    # ---------- события-эффекты (звуки, частицы, тексты), которые видят все ----------
    def fx_emit(self, ev):
        if len(self.fx_out) < 100:
            self.fx_out.append(ev)

    def fx_apply(self, evs):
        if not evs:
            return
        for e in evs:
            k = e[0]
            if k == "s":
                self.play(e[1])
            elif k == "b":
                self.burst(e[1], e[2], [tuple(c) for c in e[3]], e[4], e[5], e[6], e[7], e[8])
            elif k == "f":
                self.float_text(e[1], e[2], e[3], tuple(e[4]))
            elif k == "m" and self.battle is not None:
                self.battle.music(e[1], bool(e[2]), net=False)
            elif k == "ms" and self.battle is not None:
                self.battle.stop_music(net=False)
            elif k == "t" and self.battle is not None:
                self.battle.tint = e[1]
                self.battle.tint_col = tuple(e[2])
            elif k == "bm" and self.battle is not None:
                self.battle.add_boom(e[1], e[2], e[3], e[4], e[5], net=False)
            elif k == "ft":
                self.flash_text = e[1]
                self.flash_timer = e[2]

    # ---------- снимок мира ----------
    def make_snapshot(self):
        self.snap_seq += 1
        s = {"t": "s", "g": self.gid, "n": self.snap_seq, "el": round(self.elapsed, 2),
             "sc": self.score, "bo": self.bolts, "bk": self.bricks_collected}
        pl = []
        for q in self.players.values():
            fl = (1 if q.dead else 0) | (2 if q.invuln > 0 else 0) | (4 if q.on_ground else 0) | (8 if q.climb else 0)
            pl.append([q.pid, q.rect.x, q.rect.y, int(q.vel.x), int(q.vel.y), 1 if q.facing > 0 else -1,
                       round(q.anim, 2), fl, q.hp, q.gren, round(q.respawn_t, 1) if q.dead else 0])
        s["pl"] = pl
        if self.enemies:
            s["en"] = [[en.rect.x, en.dir, en.hp] for en in self.enemies]
        if self.pigeons:
            s["pg"] = [[int(pg.x), int(pg.y), pg.face, pg.state, round(pg.anim, 1), 1 if pg.flash > 0 else 0,
                        pg.hp] for pg in self.pigeons]
        if self.poops:
            s["po"] = [[int(po[0]), int(po[1])] for po in self.poops]
        s["cp"] = sorted(self.checkpoints_hit)
        now = time.time()
        if self.battle is not None and (self.sup_dirty or now - self.sup_sent_t > 4.0):
            self.sup_dirty = False
            self.sup_sent_t = now
            self.pk_dirty = True
            s["ps"] = [[pk.kind, round(pk.base.x, 1), round(pk.base.y, 1)] for pk in self.battle.supply]
        if self.pk_dirty or now - self.pk_sent_t > 1.5:
            self.pk_dirty = False
            self.pk_sent_t = now
            s["tk"] = [i for i, pk in enumerate(self.pickups) if pk.taken]
        if self.battle is not None:
            s["b"] = self.battle.net_state()
        if self.net_shake > 0:
            s["sh"] = [round(self.net_shake, 2), round(self.net_amp, 1)]
            self.net_shake = 0.0
            self.net_amp = 0.0
        if self.fx_out:
            s["fx"] = self.fx_out
            self.fx_out = []
        return s

    def apply_snapshot(self, s):
        if s.get("g") != self.gid or s.get("n", 0) <= self.rx_seq or self.state not in ("play", "win", "gameover", "bwin"):
            if s.get("g") == self.gid:
                self.fx_apply(s.get("fx"))
            return
        self.rx_seq = s["n"]
        self.fx_apply(s.get("fx"))
        if self.state != "play":
            return
        el = s.get("el", self.elapsed)
        if abs(el - self.elapsed) > 0.5:
            self.elapsed = el
        else:
            self.elapsed += (el - self.elapsed) * 0.25
        self.score = s.get("sc", self.score)
        self.bolts = s.get("bo", self.bolts)
        self.bricks_collected = s.get("bk", self.bricks_collected)
        now = time.time()
        for e in s.get("pl", ()):
            q = self.players.get(e[0])
            if q is None:
                continue
            fl = e[7]
            q.hp = e[8]
            q.gren = e[9]
            if len(e) > 10:
                q.respawn_t = e[10]
            if q is self.player:
                if fl & 1 and not q.dead:
                    q.dead = True
                    q.climb = None
                    self.float_text(q.rect.centerx, q.rect.top - 12, "Ты выбыл!", (235, 64, 72))
                continue
            q.rect.x, q.rect.y = e[1], e[2]
            q.vel.x, q.vel.y = e[3], e[4]
            q.facing = e[5]
            q.anim = e[6]
            q.dead = bool(fl & 1)
            q.invuln = 0.3 if fl & 2 else 0.0
            q.on_ground = bool(fl & 4)
            q.climb = 1 if fl & 8 else None
            q.net_t = now
        en = s.get("en")
        if en is not None:
            for obj, e in zip(self.enemies, en):
                obj.rect.x, obj.dir = e[0], e[1]
                obj.hp = e[2]
                obj.alive = e[2] > 0
        pg = s.get("pg")
        if pg is not None:
            for obj, e in zip(self.pigeons, pg):
                obj.tx, obj.ty = e[0], e[1]
                obj.face, obj.state, obj.anim = e[2], e[3], e[4]
                obj.flash = 0.3 if e[5] else 0.0
                obj.hp = e[6]
                obj.alive = e[6] > 0
                if not getattr(obj, "seen", False):
                    obj.x, obj.y = obj.tx, obj.ty
                    obj.seen = True
        po = s.get("po")
        self.poops = [[e[0], e[1], 0.0] for e in po] if po else []
        cp = s.get("cp")
        if cp is not None:
            new = set(cp)
            if new - self.checkpoints_hit:
                self.play("check")
            self.checkpoints_hit = new
        tk = s.get("tk")
        if tk is not None:
            tks = set(tk)
            for i, pk in enumerate(self.pickups):
                pk.taken = i in tks
        bt = self.battle
        ps = s.get("ps")
        if ps is not None and bt is not None:
            bt.net_supply(ps)
        sh = s.get("sh")
        if sh:
            self._shake = max(self._shake, sh[0])
            self._shake_amp = sh[1]
        if bt is not None and s.get("b") is not None:
            bt.net_apply(s["b"])

    # ---------- состояние для экранов итогов ----------
    def state_payload(self, st):
        m = {"t": "state", "st": st, "sc": self.score, "bo": self.bolts, "bk": self.bricks_collected,
             "el": round(self.elapsed, 1)}
        if self.battle is not None:
            m.update(self.battle.net_result_payload())
        return m

    def coop_state_changed(self, st):
        """Хост сообщает всем о победе / поражении."""
        if self.role != "host" or st not in ("win", "gameover", "bwin"):
            return
        self.net_broadcast(self.make_snapshot(), droppable=False)
        self.net_broadcast(self.state_payload(st))

    # ---------- отправка своего состояния и снимков ----------
    def net_tick(self, dt):
        """Вызывается из update(): шлём состояние со скоростью SEND_HZ."""
        if self.role is None:
            return
        self.send_t += dt
        if self.send_t < 1.0 / SEND_HZ:
            return
        self.send_t = 0.0
        if self.role == "host":
            if self.state == "play":
                s = self.make_snapshot()
                self.net_broadcast(s, droppable=True)
        elif self.role == "client" and self.state == "play":
            p = self.player
            if not p.dead:
                self.net_to_host({"t": "st", "g": self.gid, "e": p.epoch, "x": p.rect.x, "y": p.rect.y,
                                  "vx": int(p.vel.x), "vy": int(p.vel.y), "f": p.facing,
                                  "a": round(p.anim, 2), "og": 1 if p.on_ground else 0,
                                  "c": 1 if p.climb is not None else 0}, droppable=True)
