# -*- coding: utf-8 -*-
"""Сеть для кооператива по Wi-Fi.

  * Поиск серверов: хост раз в секунду рассылает маленький UDP-пакет-«визитку»
    (broadcast), а меню КО-ОП слушает порт и собирает список.
  * Сама игра: обычный TCP. Сообщение = 4 байта длины + JSON.

Всё работает без потоков в главном цикле: сокеты неблокирующие, их «прокачивают»
раз в кадр. Единственный поток — подключение клиента (чтобы меню не зависало).
Модуль не зависит от pygame.
"""
import json
import socket
import struct
import threading
import time

DISC_PORT = 47310          # UDP: визитки серверов
GAME_PORT = 47311          # TCP: игра (если занят — пробуем следующие)
PROTO = 1                  # версия протокола: разные версии друг друга не видят
MAX_PLAYERS = 6
MAX_FRAME = 1 << 20
SERVER_TTL = 3.6           # сервер пропадает из списка, если визитки нет столько секунд


def local_ip():
    """IP этого устройства в локальной сети (без отправки пакетов)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def broadcast_targets():
    t = ["255.255.255.255"]
    ip = local_ip()
    parts = ip.split(".")
    if len(parts) == 4 and not ip.startswith("127."):
        t.append(".".join(parts[:3] + ["255"]))
    t.append("127.0.0.1")                 # игра на одном устройстве (и для проверок)
    return t


class Conn:
    """TCP-соединение: неблокирующее, с буферами. pump() возвращает пришедшие сообщения."""

    def __init__(self, sock, addr=None):
        sock.setblocking(False)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.sock = sock
        self.addr = addr
        self.rbuf = bytearray()
        self.wbuf = bytearray()
        self.closed = False
        self.reason = ""
        self.born = time.time()
        self.last_rx = time.time()
        self.pid = None
        self.hello = None

    def send(self, msg, droppable=False):
        """droppable — можно выбросить, если соединение не успевает (снимки мира)."""
        if self.closed:
            return False
        if droppable and len(self.wbuf) > 120000:
            return False
        data = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.wbuf += struct.pack(">I", len(data))
        self.wbuf += data
        return True

    def _fail(self, why):
        if not self.closed:
            self.closed = True
            self.reason = why
            try:
                self.sock.close()
            except OSError:
                pass

    def pump(self):
        out = []
        if not self.closed and self.wbuf:
            try:
                while self.wbuf:
                    n = self.sock.send(self.wbuf)
                    if n <= 0:
                        break
                    del self.wbuf[:n]
            except (BlockingIOError, InterruptedError):
                pass
            except OSError as e:
                self._fail(str(e))
        if not self.closed:
            try:
                while True:
                    chunk = self.sock.recv(65536)
                    if not chunk:
                        self._fail("соединение закрыто")
                        break
                    self.rbuf += chunk
                    self.last_rx = time.time()
                    if len(chunk) < 65536:
                        break
            except (BlockingIOError, InterruptedError):
                pass
            except OSError as e:
                self._fail(str(e))
        buf = self.rbuf
        while len(buf) >= 4:
            n = struct.unpack(">I", buf[:4])[0]
            if n > MAX_FRAME:
                self._fail("слишком большое сообщение")
                break
            if len(buf) < 4 + n:
                break
            raw = bytes(buf[4:4 + n])
            del buf[:4 + n]
            try:
                out.append(json.loads(raw.decode("utf-8")))
            except ValueError:
                pass
        return out

    def flush_close(self):
        """Отправить, что накопилось, и закрыть (для сообщений «до свидания»)."""
        try:
            self.sock.setblocking(True)
            self.sock.settimeout(0.3)
            if self.wbuf:
                self.sock.sendall(bytes(self.wbuf))
        except OSError:
            pass
        self.wbuf.clear()
        self._fail("закрыто")


class HostServer:
    """Принимает подключения. События poll(): ('hello', conn, msg) | ('msg', pid, msg) | ('leave', pid)."""

    def __init__(self):
        self.lsock = None
        self.port = GAME_PORT
        for port in range(GAME_PORT, GAME_PORT + 12):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", port))
                s.listen(8)
                s.setblocking(False)
                self.lsock = s
                self.port = port
                break
            except OSError:
                s.close()
        if self.lsock is None:
            raise OSError("все порты заняты")
        self.pending = []          # соединения, от которых ещё не было hello
        self.conns = {}            # pid -> Conn

    def admit(self, conn, pid):
        conn.pid = pid
        if conn in self.pending:
            self.pending.remove(conn)
        self.conns[pid] = conn

    def poll(self):
        ev = []
        try:
            while True:
                s, addr = self.lsock.accept()
                self.pending.append(Conn(s, addr))
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            pass
        now = time.time()
        for c in list(self.pending):
            for m in c.pump():
                if m.get("t") == "hello" and c.hello is None:
                    c.hello = m
                    ev.append(("hello", c, m))
            if c.closed or (c.hello is None and now - c.born > 6.0):
                if c in self.pending:
                    self.pending.remove(c)
                c._fail("нет hello")
        for pid, c in list(self.conns.items()):
            for m in c.pump():
                ev.append(("msg", pid, m))
            if c.closed or now - c.last_rx > 9.0:
                c._fail(c.reason or "таймаут")
                del self.conns[pid]
                ev.append(("leave", pid))
        return ev

    def send(self, pid, msg, droppable=False):
        c = self.conns.get(pid)
        if c is not None:
            c.send(msg, droppable)

    def broadcast(self, msg, droppable=False, skip=None):
        for pid, c in self.conns.items():
            if pid != skip:
                c.send(msg, droppable)

    def close(self):
        for c in list(self.conns.values()) + self.pending:
            try:
                c.flush_close()
            except OSError:
                pass
        self.conns.clear()
        self.pending = []
        if self.lsock is not None:
            try:
                self.lsock.close()
            except OSError:
                pass
            self.lsock = None


class ClientLink:
    """Подключение клиента к хосту. Соединение открывается в потоке, остальное — в главном цикле."""

    def __init__(self, ip, port, hello):
        self.ip, self.port = ip, port
        self.hello = hello
        self.state = "connecting"      # connecting | ok | failed
        self.error = ""
        self.conn = None
        self._sock = None
        self.t0 = time.time()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._sock = socket.create_connection((self.ip, self.port), timeout=4.0)
            self.state = "ok"
        except OSError as e:
            self.error = str(e)
            self.state = "failed"

    def poll(self):
        """Сообщения от хоста. Пустой список, пока соединяемся."""
        if self.conn is None:
            if self.state == "ok" and self._sock is not None:
                self.conn = Conn(self._sock)
                self.conn.send(self.hello)
            return []
        return self.conn.pump()

    @property
    def dead(self):
        if self.state == "failed":
            return True
        c = self.conn
        if c is None:
            return False
        return c.closed or time.time() - c.last_rx > 9.0

    def send(self, msg, droppable=False):
        if self.conn is not None:
            self.conn.send(msg, droppable)

    def close(self, bye=True):
        c = self.conn
        if c is not None:
            if bye:
                c.send({"t": "bye"})
            c.flush_close()
        elif self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self.state = "failed"


class Announcer:
    """Хост: рассылает визитку сервера."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        self.sock.setblocking(False)
        self.targets = broadcast_targets()
        self.timer = 0.0

    def tick(self, dt, info):
        self.timer -= dt
        if self.timer > 0:
            return
        self.timer = 1.0
        data = json.dumps(info, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        for tgt in self.targets:
            try:
                self.sock.sendto(data, (tgt, DISC_PORT))
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    """Меню КО-ОП: слушает визитки и ведёт список серверов."""

    def __init__(self):
        self.ok = False
        self.found = {}
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            s.bind(("", DISC_PORT))
            s.setblocking(False)
            self.ok = True
        except OSError:
            pass
        self.sock = s

    def poll(self):
        if not self.ok:
            return
        for _ in range(64):
            try:
                data, addr = self.sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                d = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("g") != "pisun" or d.get("v") != PROTO:
                continue
            try:
                port = int(d.get("port", GAME_PORT))
            except (TypeError, ValueError):
                continue
            d["ip"] = addr[0]
            d["port"] = port
            d["seen"] = time.time()
            self.found[(addr[0], port)] = d

    def servers(self):
        now = time.time()
        for k in [k for k, v in self.found.items() if now - v["seen"] > SERVER_TTL]:
            del self.found[k]
        return sorted(self.found.values(), key=lambda d: (d.get("name", ""), d["ip"]))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
        self.ok = False
