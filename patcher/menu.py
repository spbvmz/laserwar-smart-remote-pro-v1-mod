"""Menu tree of the Devices section: registers, value rows, command lists."""
from __future__ import annotations

TEXT_PITCH = 13  # 7 visible rows of 26..123

# Control point registers (word sessions C0|reg)
REG_CAPTURE, REG_NEG_DELAY, REG_NEG_CMD = 0, 2, 4
REG_BF_CAPTURE, REG_BF_NEG_DELAY, REG_BF_NEG_CMD = 6, 8, 10
REG_BF_HOLD, REG_BF_ACCEL, REG_BF_POS_CMD, REG_BF_POS_DELAY, REG_BF_POS_COUNT = 12, 14, 16, 18, 20
REG_CP_HP, REG_CP_OWNER, REG_CP_HP_DELAY, REG_CP_HP_RATE = 22, 24, 26, 28
REG_CP_NEG_DELAY, REG_CP_NEG_CMD, REG_CP_POS_CMD, REG_CP_POS_DELAY, REG_CP_POS_COUNT = 30, 32, 34, 36, 38
REG_SOUND, REG_START_DELAY, REG_SCENARIO = 40, 42, 44

# Smart medkit 2.0. Same protocol as the official configurator: Identify BF 3F 80 (medkit replies
# 3F 21 ver), then A3 addr v per byte (reply A4 addr v), words low byte first, then finish BF 65 DA.
REG_FAK_CMD_HEALTH, REG_FAK_GAME_MODE, REG_FAK_SETS, REG_FAK_HITS = 21, 24, 25, 26
REG_FAK_CMD_AMMO, REG_FAK_ROUND, REG_FAK_HOLD, REG_FAK_EMIT = 37, 40, 42, 43
REG_FAK_CMD_ENERGY, REG_FAK_PERIOD, REG_FAK_AUTO = 53, 56, 58
FAK_OFF = 255
# Smart medic (identify reply 3F 20 ver): medkit protocol; hold is written as one byte, a word
# write to 22 would have its high byte overwritten by command byte 0
REG_MED_SETS, REG_MED_HOLD, REG_MED_CMD, REG_MED_HITS = 21, 22, 23, 26
# Command post (identify reply 3F 12 ver): medkit protocol; times in s, 255 = off
REG_CP2_INTERVAL, REG_CP2_REGEN, REG_CP2_POWER, REG_CP2_RAD, REG_CP2_HITS = 162, 164, 165, 166, 167
REG_CP2_ROUND, REG_CP2_RESTORE, REG_CP2_AMMO, REG_CP2_HITS2, REG_CP2_RESTORE2 = 169, 171, 172, 174, 176
REG_CP2_CMD_CAPT, REG_CP2_CMD_FAK, REG_CP2_CMD_2X2 = 177, 180, 183
# device of a write: point word session, medkit byte / word / 3-byte command session
DEV_POINT, DEV_FAK, DEV_FAK_WORD, DEV_FAK_CMD = 0, 1, 2, 3
FAK_WRITE_IDENTIFY = True  # False: medkit sessions without Identify

# key: (ru, en, byte, step, max, default, group base byte, register, min sent, group size, radix,
#       max sent, device)
# OK on any row of a group sends Horner(bytes[base:base+size], radix) clamped to [min sent, max sent]
# as a session of 'device'.
VALUES: dict[str, tuple] = {}
NO_CAP = 0xFFFF


def time_rows(key: str, byte: int, reg: int, vmin: int, sec_step: int, dmin: int, dsec: int) -> None:
    VALUES[f"{key}_min"] = ("Минуты:", "Minutes:", byte, 1, 59, dmin, byte, reg, vmin, 2, 60, NO_CAP, 0)
    VALUES[f"{key}_sec"] = ("Секунды:", "Seconds:", byte + 1, sec_step, 60 - sec_step, dsec,
                            byte, reg, vmin, 2, 60, NO_CAP, 0)


def digit_rows(key: str, byte: int, n: int, reg: int, vmin: int, default: int,
               top: int = 9, cap: int = NO_CAP, dev: int = DEV_POINT) -> None:
    names = [("Тысячи:", "Thousands:"), ("Сотни:", "Hundreds:"),
             ("Десятки:", "Tens:"), ("Единицы:", "Units:")][-n:]
    for i, (ru, en) in enumerate(names):
        d = default // 10 ** (n - 1 - i) % 10
        VALUES[f"{key}_{i}"] = (ru, en, byte + i, 1, top if i == 0 else 9, d, byte, reg, vmin, n, 10,
                                cap, dev)


def single_row(key: str, ru: str, en: str, byte: int, vmax: int, default: int, reg: int, vmin: int) -> None:
    VALUES[key] = (ru, en, byte, 1, vmax, default, byte, reg, vmin, 1, 10, NO_CAP, 0)


time_rows("cap", 0, REG_CAPTURE, 10, 5, 0, 30)
time_rows("start", 2, REG_START_DELAY, 1, 5, 0, 5)
single_row("neg_delay", "Задержка:", "Delay:", 4, 9, 0, REG_NEG_DELAY, 0)
time_rows("bf_cap", 5, REG_BF_CAPTURE, 10, 5, 0, 30)
single_row("bf_neg_delay", "Задержка:", "Delay:", 7, 9, 0, REG_BF_NEG_DELAY, 0)
time_rows("bf_hold", 8, REG_BF_HOLD, 10, 5, 5, 0)
digit_rows("bf_accel", 10, 3, REG_BF_ACCEL, 1, 100)
time_rows("bf_pos", 13, REG_BF_POS_DELAY, 0, 1, 0, 0)
single_row("bf_pos_count", "Количество:", "Count:", 15, 30, 1, REG_BF_POS_COUNT, 1)
digit_rows("cp_hp", 16, 4, REG_CP_HP, 1, 100)
time_rows("cp_hpd", 20, REG_CP_HP_DELAY, 0, 5, 0, 5)
digit_rows("cp_rate", 22, 3, REG_CP_HP_RATE, 1, 1)
single_row("cp_neg_delay", "Задержка:", "Delay:", 25, 9, 0, REG_CP_NEG_DELAY, 0)
time_rows("cp_pos", 26, REG_CP_POS_DELAY, 0, 1, 0, 0)
single_row("cp_pos_count", "Количество:", "Count:", 28, 30, 1, REG_CP_POS_COUNT, 1)
digit_rows("fak_sets", 29, 3, REG_FAK_SETS, 1, 10, top=2, cap=250, dev=DEV_FAK)
digit_rows("fak_hold", 32, 3, REG_FAK_HOLD, 1, 1, top=2, cap=240, dev=DEV_FAK)
digit_rows("fak_hits", 35, 3, REG_FAK_HITS, 1, 3, top=2, cap=250, dev=DEV_FAK)
digit_rows("fak_emit", 38, 2, REG_FAK_EMIT, 1, 1, top=6, cap=60, dev=DEV_FAK)
digit_rows("fak_period", 40, 4, REG_FAK_PERIOD, 1, 10, top=1, cap=1800, dev=DEV_FAK_WORD)
digit_rows("med_sets", 44, 3, REG_MED_SETS, 1, 100, top=2, cap=254, dev=DEV_FAK)
digit_rows("med_hold", 47, 3, REG_MED_HOLD, 0, 5, top=2, cap=240, dev=DEV_FAK)
digit_rows("med_hits", 50, 3, REG_MED_HITS, 1, 2, top=2, cap=250, dev=DEV_FAK)
digit_rows("cp2_power", 53, 3, REG_CP2_POWER, 1, 1, top=1, cap=100, dev=DEV_FAK)
digit_rows("cp2_rad", 56, 3, REG_CP2_RAD, 10, 10, top=2, cap=254, dev=DEV_FAK)
# 1..10000 as 4 rows, thousands 0..10: a 5-row value page reboots the remote
digit_rows("cp2_hits", 59, 4, REG_CP2_HITS, 1, 1, top=10, cap=10000, dev=DEV_FAK_WORD)
digit_rows("cp2_restore", 63, 3, REG_CP2_RESTORE, 1, 1, top=2, cap=254, dev=DEV_FAK)
digit_rows("cp2_ammo", 66, 4, REG_CP2_AMMO, 1, 1, top=10, cap=10000, dev=DEV_FAK_WORD)
digit_rows("cp2_hits2", 70, 4, REG_CP2_HITS2, 1, 1, top=10, cap=10000, dev=DEV_FAK_WORD)
digit_rows("cp2_restore2", 74, 3, REG_CP2_RESTORE2, 1, 1, top=2, cap=254, dev=DEV_FAK)
digit_rows("cp2_regen", 77, 3, REG_CP2_REGEN, 1, 1, top=2, cap=254, dev=DEV_FAK)


def page(ru: str, en: str, icon: str, *children: tuple, small: bool = False, pitch: int | None = None) -> tuple:
    """small: stock small font (Settings page); pitch: row pitch px (default: stock submenu)."""
    return ("page", ru, en, icon, list(children), {"small": small, "pitch": pitch})


def text_page(ru: str, en: str, icon: str, lines: list[str]) -> tuple:
    """Static text: icon-less flag-1 rows with a shared no-op OK handler, small font."""
    return page(ru, en, icon, *(("text", line) for line in lines), small=True, pitch=TEXT_PITCH)


def value(key: str) -> tuple:
    return ("value", key)


def action(ru: str, en: str, reg: int, val: int, dev: int = DEV_POINT) -> tuple:
    return ("action", ru, en, reg, val, dev)


REG_TARGET = 0xFF  # action register taken from RAM: set by the link that opened the shared page


def link(ru: str, en: str, icon: str, target: tuple, reg: int) -> tuple:
    """Submenu row opening the shared page 'target'; its REG_TARGET actions write to 'reg'."""
    return ("link", ru, en, icon, target, reg)


def pulse(ru: str, en: str, cmd: int, arg: int) -> tuple:
    return (ru, en, arg | (cmd << 8))


PULSE_GROUPS = [
    ("Здоровье", "Health", [
        *(pulse(f"Здоровье +{n}", f"Health +{n}", 0x80, n) for n in (1, 5, 10, 50, 100)),
        pulse("Полное здоровье", "Full health", 0x83, 0x0D),
        pulse("Двойная жизнь", "Double life", 0x83, 0x22),
        pulse("Бинт", "Bandage", 0x83, 0x23),
    ]),
    ("Патроны", "Ammo", [
        *(pulse(f"Патроны +{n}", f"Ammo +{n}", 0x81, n) for n in (10, 50, 100)),
        *(pulse(f"Магазины +{n}", f"Clips +{n}", 0x8A, n) for n in (1, 2, 5, 10)),
        pulse("Полный боекомплект", "Full ammo", 0x83, 0x06),
    ]),
    ("Радиация", "Radiation", [
        pulse(f"Радиация -{n}", f"Radiation -{n}", 0xA0, n) for n in (1, 2, 5, 10, 25, 50, 75, 100)
    ]),
    ("Аномалия", "Anomaly", [
        pulse(f"Аномалия +{n}", f"Anomaly +{n}", 0xA1, n) for n in (1, 2, 5, 10, 25, 50, 75, 100)
    ]),
    ("Игра", "Game", [
        pulse("Admin kill", "Admin kill", 0x83, 0x00),
        pulse("Пауза", "Pause", 0x83, 0x01),
        pulse("Респаун", "Respawn", 0x83, 0x04),
        pulse("Старт игры", "Start game", 0x83, 0x05),
        pulse("Старт с задержкой", "Delayed start", 0x83, 0x0C),
        pulse("Смена команды", "Change team", 0x83, 0x09),
    ]),
    ("Эффекты", "Effects", [
        pulse("Оглушение", "Stun", 0x83, 0x16),
        pulse("Разоружение", "Disarm", 0x83, 0x17),
        pulse("Увеличение урона", "Damage up", 0x83, 0x20),
        pulse("Вампиризм выкл", "Vampirism off", 0x83, 0xFC),
        pulse("Вампиризм вкл", "Vampirism on", 0x83, 0xFD),
    ]),
    ("Команды", "Teams", [
        *(pulse(f"Команда: {ru}", f"Team {en}", 0xA9, i)
          for i, (ru, en) in enumerate((("красные", "red"), ("синие", "blue"),
                                        ("жёлтые", "yellow"), ("зелёные", "green")))),
        *(pulse(f"Возрождение {ru}", f"Respawn {en}", 0xB4, i)
          for i, (ru, en) in enumerate((("красных", "red"), ("синих", "blue"),
                                        ("жёлтых", "yellow"), ("зелёных", "green")))),
    ]),
    ("Пресеты", "Presets", [pulse(f"Пресет {n}", f"Preset {n}", 0xA8, n) for n in range(1, 9)]),
    ("Прочее", "Other", [
        pulse("Огонь по своим выкл", "Friendly fire off", 0xC4, 0x00),
        pulse("Огонь по своим вкл", "Friendly fire on", 0xC4, 0xFF),
        pulse("Wi-Fi выкл", "Wi-Fi off", 0x83, 0xFA),
        pulse("Wi-Fi вкл", "Wi-Fi on", 0x83, 0xFB),
    ]),
]


PULSE_LIST = page("Команды", "Commands", "icon_irbase", *(
    page(g_ru, g_en, "icon_irbase", *(action(a_ru, a_en, REG_TARGET, val) for a_ru, a_en, val in items))
    for g_ru, g_en, items in PULSE_GROUPS
))


def pulse_menu(ru: str, en: str, reg: int) -> tuple:
    """Command menu for impulse register 'reg' (b0 = arg, b1 = cmd): one shared copy of the list."""
    return link(ru, en, "icon_irbase", PULSE_LIST, reg)


# command names by (cmd, arg); device lists match the ones offered by the official configurator
CMD_NAMES = {(val >> 8, val & 0xFF): (ru, en) for _g, _e, items in PULSE_GROUPS for ru, en, val in items}
CMD_NAMES.update({
    **{(0x8B, a): (f"Адреналин {cc}", f"Adrenaline {cc}") for a, cc in ((0, 1), (2, 4), (6, 15), (14, 75))},
    (0x83, 0xF8): ("ИК-мощность 49%", "IR power 49%"),
    (0x83, 0xF9): ("ИК-мощность 99%", "IR power 99%"),
    (0xA8, 0x07): ("Пресет Зомби", "Preset Zombie"),
})
ARGS_N = (1, 2, 5, 10, 25, 50, 75, 100)
FAK_GAME = [(0x83, 0x04), (0x83, 0x05), (0x83, 0x0C)]
FAK_RESPAWN = [(0xB4, i) for i in range(4)]
FAK_MISC = [(0x83, a) for a in (0xFA, 0xFB, 0xFC, 0xFD)]
FAK_HEALTH_CMDS = [
    ("Игра", "Game", FAK_GAME + [(0x83, 0x0D)]),
    ("Возрождение", "Respawn", FAK_RESPAWN),
    ("Аномалия", "Anomaly", [(0xA1, n) for n in ARGS_N]),
    ("Радиация", "Radiation", [(0xA0, n) for n in ARGS_N]),
    ("Прочее", "Other", FAK_MISC),
]
FAK_AMMO_CMDS = [(0x81, n) for n in (10, 50, 100)] + [(0x83, 0x06)] + [(0x8A, n) for n in (1, 2, 5, 10)]
FAK_ENERGY_CMDS = [
    ("Здоровье", "Health", [(0x80, n) for n in (1, 5, 10, 50, 100)] + [(0x83, 0x0D), (0x83, 0x22)]),
    ("Игра", "Game", FAK_GAME),
    ("Эффекты", "Effects", [(0x83, a) for a in (0x16, 0x17, 0x20, 0xF8, 0xF9)]),
    ("Адреналин", "Adrenaline", [(0x8B, a) for a in (0, 2, 6, 14)]),
    ("Команды", "Teams", [(0xA9, i) for i in range(4)] + FAK_RESPAWN),
    ("Аномалия", "Anomaly", [(0xA1, n) for n in ARGS_N]),
    ("Радиация", "Radiation", [(0xA0, n) for n in ARGS_N]),
    ("Прочее", "Other", [(0xC4, 0x00), (0xC4, 0xFF)] + FAK_MISC + [(0xA8, 0x07)]),
]
MED_CMDS = [
    ("Здоровье", "Health", [(0x80, n) for n in (1, 5, 10, 50, 100)]),
    ("Патроны", "Cartridges", [(0x81, n) for n in (10, 50, 100)]),
    ("Магазины", "Clips", [(0x8A, n) for n in (1, 2, 5, 10)]),
    ("Адреналин", "Adrenaline", [(0x8B, a) for a in (0, 2, 6, 14)]),
    ("Аномалия", "Anomaly", [(0xA1, n) for n in ARGS_N]),
    ("Прочее", "Other", [(0x83, a) for a in (0x04, 0x05, 0x06, 0x0D, 0x23)]),
]


CP2_CMDS = [
    ("Игра", "Game", [(0x83, 0x05), (0x83, 0x0C), (0xB4, 0x00)]),
    ("Аномалия", "Anomaly", [(0xA1, n) for n in ARGS_N]),
    ("Радиация", "Radiation", [(0xA0, n) for n in ARGS_N]),
    ("Прочее", "Other", FAK_MISC),
]
CP2_FAK_CMDS = FAK_GAME
CP2_NAMES = {(0xB4, 0x00): ("Возрождение владельцев", "Respawn owners")}


def fak_cmds(reg: int, cmds: list, names: dict | None = None) -> list[tuple]:
    names = {**CMD_NAMES, **(names or {})}
    return [action(*names[c], reg, c[0] | c[1] << 8, dev=DEV_FAK_CMD) for c in cmds]


def fak_cmd_menu(ru: str, en: str, reg: int, groups: list, names: dict | None = None) -> tuple:
    return page(ru, en, "icon_irbase", *(
        page(g_ru, g_en, "icon_irbase", *fak_cmds(reg, cmds, names)) for g_ru, g_en, cmds in groups
    ))


ENERGY_LIST = fak_cmd_menu("Команда Энергия", "Energy command", REG_TARGET, FAK_ENERGY_CMDS)
CP2_LIST = fak_cmd_menu("Команда", "Command", REG_TARGET, CP2_CMDS, CP2_NAMES)


FAK_ROUND = [("1 мин", "1 min", 60), ("5 мин", "5 min", 300), ("10 мин", "10 min", 600),
             ("15 мин", "15 min", 900), ("30 мин", "30 min", 1800), ("45 мин", "45 min", 2700),
             ("1 ч", "1 h", 3600), ("1 ч 30 мин", "1 h 30 min", 5400), ("2 ч", "2 h", 7200),
             ("3 ч", "3 h", 10800), ("4 ч", "4 h", 14400), ("Без ограничений", "Unlimited", 0xFFFF)]
CP2_ROUND = [("2 мин", "2 min", 120), ("5 мин", "5 min", 300), ("10 мин", "10 min", 600),
             ("15 мин", "15 min", 900), ("30 мин", "30 min", 1800), ("1 ч", "1 h", 3600), ("2 ч", "2 h", 7200)]
CP2_INTERVAL = [("Отключено", "Disabled", 0xFFFF), ("10 с", "10 s", 10), ("20 с", "20 s", 20),
                ("30 с", "30 s", 30), ("1 мин", "1 min", 60), ("2 мин", "2 min", 120), ("5 мин", "5 min", 300),
                ("10 мин", "10 min", 600), ("15 мин", "15 min", 900), ("25 мин", "25 min", 1500),
                ("30 мин", "30 min", 1800), ("1 ч", "1 h", 3600), ("2 ч", "2 h", 7200), ("5 ч", "5 h", 18000),
                ("10 ч", "10 h", 36000)]

INFO_LINES = [
    "Lasertag MOD",
    "Версия: MOD 1.04",
    "Build: 27.10.2026",
    "База: Официальная",
    "прошивка v1.14",
    "Автор: @spbvmz",
    "Поддержка:",
    "t.me/lasertagpult",
    "О прошивке:",
    "Оптимизированный мод",
    "прошивки с поддержкой",
    "настройки игровых",
    "девайсов. Без рекламы и",
    "скрытых подписок.",
    "Дисклеймер:",
    "предоставляется",
    "бесплатно и без",
    "каких-либо гарантий.",
    "Установка производится",
    "на ваш страх и риск.",
]

TREE = page(
    "Девайсы", "Devices", "icon_service",
    text_page("INFO", "INFO", "icon_info", INFO_LINES),
    page(
        "Настройка", "Settings", "icon_service",
        page(
            "Сценарий", "Scenario", "icon_irbase",
            action("Захват точки", "Point capture", REG_SCENARIO, 1),
            action("Battlefield", "Battlefield", REG_SCENARIO, 2),
            action("Пункт управления", "Command post", REG_SCENARIO, 3),
        ),
        page("Задержка старта", "Start delay", "icon_time", value("start_min"), value("start_sec")),
        page(
            "Локализация звуков", "Sound language", "icon_service",
            action("Русский", "Russian", REG_SOUND, 0),
            action("Английский", "English", REG_SOUND, 1),
        ),
    ),
    page(
        "Точка", "Point", "icon_irbase",
        page(
            "Захват точки", "Point capture", "icon_roundtime",
            page("Время захвата", "Capture time", "icon_time", value("cap_min"), value("cap_sec")),
            page("Задержка отр. имп.", "Neg. pulse delay", "icon_time", value("neg_delay")),
            pulse_menu("Команда отр. импульса", "Neg. pulse command", REG_NEG_CMD),
        ),
        page(
            "Точка Battlefield", "Battlefield point", "icon_roundtime",
            page("Время захвата", "Capture time", "icon_time", value("bf_cap_min"), value("bf_cap_sec")),
            page("Задержка отр. имп.", "Neg. pulse delay", "icon_time", value("bf_neg_delay")),
            pulse_menu("Команда отр. импульса", "Neg. pulse command", REG_BF_NEG_CMD),
            page("Время удержания", "Hold time", "icon_time", value("bf_hold_min"), value("bf_hold_sec")),
            page("Ускорение захвата", "Capture boost", "icon_time",
                 *(value(f"bf_accel_{i}") for i in range(3))),
            pulse_menu("Команда пол. импульса", "Pos. pulse command", REG_BF_POS_CMD),
            page("Задержка пол. имп.", "Pos. pulse delay", "icon_time", value("bf_pos_min"), value("bf_pos_sec")),
            page("Кол-во пол. имп.", "Pos. pulse count", "icon_time", value("bf_pos_count")),
        ),
        page(
            "Пункт управления", "Command post", "icon_roundtime",
            page("Очки прочности", "Hit points", "icon_time", *(value(f"cp_hp_{i}") for i in range(4))),
            page(
                "Владелец", "Owner", "icon_irbase",
                *(action(ru, en, REG_CP_OWNER, i) for i, (ru, en) in enumerate((
                    ("Нейтральный", "Neutral"), ("Красные", "Red"), ("Синие", "Blue"),
                    ("Жёлтые", "Yellow"), ("Зелёные", "Green")))),
            ),
            page("Задержка восстан.", "Restore delay", "icon_time", value("cp_hpd_min"), value("cp_hpd_sec")),
            page("Скорость восстан.", "Restore rate", "icon_time", *(value(f"cp_rate_{i}") for i in range(3))),
            page("Задержка отр. имп.", "Neg. pulse delay", "icon_time", value("cp_neg_delay")),
            pulse_menu("Команда отр. импульса", "Neg. pulse command", REG_CP_NEG_CMD),
            pulse_menu("Команда пол. импульса", "Pos. pulse command", REG_CP_POS_CMD),
            page("Задержка пол. имп.", "Pos. pulse delay", "icon_time", value("cp_pos_min"), value("cp_pos_sec")),
            page("Кол-во пол. имп.", "Pos. pulse count", "icon_time", value("cp_pos_count")),
        ),
    ),
    page(
        "Умная аптечка 2.0", "Smart medkit 2.0", "icon_irbase",
        page("Кол-во комплектов", "Medkit sets", "icon_time",
             action("Выкл", "Off", REG_FAK_SETS, FAK_OFF, dev=DEV_FAK),
             *(value(f"fak_sets_{i}") for i in range(3))),
        page("Время удержания", "Hold time", "icon_time",
             action("Выкл", "Off", REG_FAK_HOLD, 0, dev=DEV_FAK),
             *(value(f"fak_hold_{i}") for i in range(3))),
        page("Попаданий на компл.", "Hits per set", "icon_time",
             action("Выкл", "Off", REG_FAK_HITS, FAK_OFF, dev=DEV_FAK),
             *(value(f"fak_hits_{i}") for i in range(3))),
        page(
            "Игровой режим", "Game mode", "icon_irbase",
            action("Здоровье", "Health", REG_FAK_GAME_MODE, 0, dev=DEV_FAK),
            action("Боезапас", "Ammo", REG_FAK_GAME_MODE, 1, dev=DEV_FAK),
            page(
                "Энергия", "Energy", "icon_irbase",
                action("Вкл режим", "Enable mode", REG_FAK_GAME_MODE, 2, dev=DEV_FAK),
                link("Команда", "Command", "icon_irbase", ENERGY_LIST, REG_FAK_CMD_ENERGY),
                page("Период", "Period", "icon_time",
                     *(value(f"fak_period_{i}") for i in range(4))),
                page("Активация", "Activation", "icon_irbase",
                     action("Нажатие", "Button press", REG_FAK_AUTO, 0, dev=DEV_FAK),
                     action("Автоматически", "Automatic", REG_FAK_AUTO, 1, dev=DEV_FAK)),
            ),
        ),
        page("Время раунда", "Round time", "icon_roundtime",
             *(action(ru, en, REG_FAK_ROUND, v, dev=DEV_FAK_WORD) for ru, en, v in FAK_ROUND)),
        fak_cmd_menu("Команда Здоровье", "Health command", REG_FAK_CMD_HEALTH, FAK_HEALTH_CMDS),
        page("Команда Боезапас", "Ammo command", "icon_irbase",
             *fak_cmds(REG_FAK_CMD_AMMO, FAK_AMMO_CMDS)),
        link("Команда Энергия", "Energy command", "icon_irbase", ENERGY_LIST, REG_FAK_CMD_ENERGY),
        page("Длит. излучения", "Emission time", "icon_time",
             *(value(f"fak_emit_{i}") for i in range(2))),
    ),
    page(
        "Умный медик", "Smart medic", "icon_irbase",
        page("Кол-во комплектов", "Medkit sets", "icon_time",
             action("Выкл", "Off", REG_MED_SETS, FAK_OFF, dev=DEV_FAK),
             *(value(f"med_sets_{i}") for i in range(3))),
        page("Время срабатывания", "Trigger time", "icon_time",
             *(value(f"med_hold_{i}") for i in range(3))),
        page("Попаданий на компл.", "Hits per set", "icon_time",
             action("Выкл", "Off", REG_MED_HITS, FAK_OFF, dev=DEV_FAK),
             *(value(f"med_hits_{i}") for i in range(3))),
        fak_cmd_menu("Команда", "Command", REG_MED_CMD, MED_CMDS),
    ),
    page(
        "Командный пункт", "Command post", "icon_irbase",
        page(
            "Захват базы", "Base capture", "icon_roundtime",
            page("Сила выброса", "Emission power", "icon_time", *(value(f"cp2_power_{i}") for i in range(3))),
            page("Время между выбр.", "Emission interval", "icon_time",
                 action("Выкл", "Off", REG_CP2_RAD, FAK_OFF, dev=DEV_FAK),
                 *(value(f"cp2_rad_{i}") for i in range(3))),
            page("Выстрелов для захв.", "Hits to capture", "icon_time",
                 *(value(f"cp2_hits_{i}") for i in range(4))),
            page("Время раунда", "Round time", "icon_roundtime",
                 *(action(ru, en, REG_CP2_ROUND, v, dev=DEV_FAK_WORD) for ru, en, v in CP2_ROUND)),
            page("Самовосстановление", "Self-restore", "icon_time",
                 action("Выкл", "Off", REG_CP2_RESTORE, FAK_OFF, dev=DEV_FAK),
                 *(value(f"cp2_restore_{i}") for i in range(3))),
            page("Интервал команды", "Command interval", "icon_roundtime",
                 *(action(ru, en, REG_CP2_INTERVAL, v, dev=DEV_FAK_WORD) for ru, en, v in CP2_INTERVAL)),
            link("Команда при захвате", "Capture command", "icon_irbase", CP2_LIST, REG_CP2_CMD_CAPT),
        ),
        page(
            "Противостояние", "2x2", "icon_roundtime",
            page("Кол-во боезапаса", "Ammo count", "icon_time", *(value(f"cp2_ammo_{i}") for i in range(4))),
            page("Выстрелов для уничт.", "Hits to destroy", "icon_time",
                 *(value(f"cp2_hits2_{i}") for i in range(4))),
            page("Самовосстановление", "Self-restore", "icon_time",
                 action("Выкл", "Off", REG_CP2_RESTORE2, FAK_OFF, dev=DEV_FAK),
                 *(value(f"cp2_restore2_{i}") for i in range(3))),
            link("Команда", "Command", "icon_irbase", CP2_LIST, REG_CP2_CMD_2X2),
        ),
        page(
            "Аптечка", "Medkit", "icon_roundtime",
            page("Время регенерации", "Regen time", "icon_time",
                 action("Выкл", "Off", REG_CP2_REGEN, FAK_OFF, dev=DEV_FAK),
                 *(value(f"cp2_regen_{i}") for i in range(3))),
            page("Команда", "Command", "icon_irbase", *fak_cmds(REG_CP2_CMD_FAK, CP2_FAK_CMDS)),
        ),
    ),
)
ACTION_ICON = "icon_roundtime"
VALUE_ICON = "icon_time"


def sub_page(kid: tuple) -> tuple | None:
    """Page opened by a row: its own page or the shared page of a link."""
    return kid if kid[0] == "page" else kid[4] if kid[0] == "link" else None


def tree_pages(node: tuple) -> list[tuple]:
    """Every page once (shared pages at their first link), depth-first."""
    out: list[tuple] = []

    def rec(pg: tuple) -> None:
        if any(q is pg for q in out):
            return
        out.append(pg)
        for kid in pg[4]:
            sub = sub_page(kid)
            if sub is not None:
                rec(sub)

    rec(node)
    return out


def tree_items(kind: str) -> list[tuple]:
    return [kid for pg in tree_pages(TREE) for kid in pg[4] if kid[0] == kind]


def path_actions(node: tuple = None, target: int | None = None) -> list[tuple]:
    """Actions as reachable from the menu: shared lists once per link, REG_TARGET resolved."""
    out = []
    for kid in (node or TREE)[4]:
        if kid[0] == "action":
            reg = target if kid[3] == REG_TARGET else kid[3]
            out.append(("action", kid[1], kid[2], reg, kid[4], kid[5]))
        elif kid[0] == "page":
            out.extend(path_actions(kid, target))
        elif kid[0] == "link":
            out.extend(path_actions(kid[4], kid[5]))
    return out
