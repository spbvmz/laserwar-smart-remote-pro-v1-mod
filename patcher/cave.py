"""
Adds the Devices («Девайсы») section to the main menu of Smart PRO Remote v1.14.

The stock image is left as is except for a few patch points; all new code and data go to the
free flash area after the firmware (the cave):
  nav_limit  0x0138  cmp r0,#2 -> #8        menu nesting depth
  nav_lit    0x03A4  nav array -> our RAM   (8 x 12 bytes)
  hook       0xA9B0  BL svc -> BL tick      main loop hook that sends IR frames
  main_page  0xCA20  items -> cave copy (15 stock items + Devices), count 16
  ver_bl     0x1A72  'Информация' shows version '14-mod'
Offsets are from APP_BASE (the bootloader sits below it). Pointers in menu tables are absolute;
the added code uses only PC-relative BL/ADR/B.

Row kinds: value rows (flag 2) change a number with +/- and write it on OK; action rows (flag 1)
write a fixed value on OK; submenu rows (flag 0) open a page. Every write is one IR session sent
from the main loop, one frame per FRAME_MS + gap.

RAM above the initial MSP (ram_base): state +0x00, nav stack +0x20, packets +0xC0,
shared-list target +0xEC, page cursors +0xF0, then values (VALUES_SIZE bytes) and their u16 mark.
"""
from __future__ import annotations

import struct
from types import SimpleNamespace

from .menu import *  # noqa: F401,F403
from .thumb import (
    FLASH,
    FRAME_MS,
    MAGIC,
    STOCK_SIZE,
    TRAILER_LEN,
    ThumbEmu,
    decode_bl,
    encode_b,
    encode_bcond,
    encode_bl,
    encode_ldr_lit,
    sign_image,
)

APP_BASE = 0x08009800
NAV_DEPTH = 8
VALUES_MARK = 0xA55B
VALUES_SIZE = 0x80  # value bytes after the page cursors; the u16 init mark follows them
NSLOTS = 9  # frames per session; a slot with byte 0 == 0 is skipped
REC = 20
RAM_SIZE = 0x400  # our RAM budget above the initial MSP; page cursors are last
MAIN_COUNT = 15
TEXT_STRUCT = 0x20000140  # stock value-text draw struct
TEMPLATE_HEADER = 0x7B7B1A04

PROFILES = {
    "1.14": dict(
        ram_base=0x20001410,
        cave=0xE200,
        wrapper=0x018A,
        svc=0x2710,
        hook=0xA9B0,
        gettick=0x3D9E,
        enter=0x07F0,  # (r0=event*, r1=page, r2=&cursor)
        keys=0x081C,  # (r0=page, r1=&cursor)
        nav_limit=0x0138,
        nav_lit=0x03A4,
        nav_ram_stock=0x20000C10,
        main_page=0xCA20,
        main_items=0xAB58,
        template=0xCA84,  # 'Для улицы' page: header / font words
        icon_service=0xAC48,
        icon_irbase=0xB89C,
        icon_roundtime=0xAC0C,
        icon_time=0xCAFC,
        icon_info=0xAC5C,
        settings_page=0xCB9C,  # small font, icon-less rows, pitch 20
        measure=0x37C8,  # (r0=str, r1=font) -> text width px
        prep=0x36E0,  # (0x20000144, 0x20000146, [0x2000014E])
        itoa=0x349A,  # (r0=value u8, r1=buf) -> digits+1, writes NUL
        draw=0x39C0,  # (r0=TEXT_STRUCT)
        text_buf=0x20000FB8,
        ver_bl=0x1A72,  # 'Информация': BL itoa for the minor version number
        ver_minor=14,
        ver_text_sp=12,  # [sp+12] = text pointer of the following draw
        tx_miles=0x25FE,  # 2 bytes + E8/XOR -> tx_submit(sp, 24)
        tx_submit=0x5474,  # (r0 = buffer, r1 = bit count)
        tx_wait=0x26EC,  # wrapper tail: tx_wait(byte [tx_cfg + 2])
        tx_cfg=0x20000138,
    ),
}

ICON_NAMES = {
    "icon_service": "Сервис",
    "icon_irbase": "ИК-база",
    "icon_roundtime": "Время игры",
    "icon_time": "Время:",
    "icon_info": "Информация",  # main menu record ('i' icon)
}
SMALL_FONT_H = 10
TEXT_MAX_W = 116  # x0 4 .. right edge 123 - 2 (scrollbar) - 2 (selected): wider rows marquee-scroll
TEXT_STOCK_PITCH = 0x14  # stock Settings page

def load_profile(name: str) -> SimpleNamespace:
    p = SimpleNamespace(name=name, **PROFILES[name])
    p.state = p.ram_base
    p.nav_ram = p.ram_base + 0x20
    p.pkt = p.ram_base + 0xC0  # NSLOTS x 4 bytes, up to the cursors
    p.target = p.ram_base + 0xEC  # u8 register for REG_TARGET actions, after the packet slots
    p.cursors = p.ram_base + 0xF0
    p.values = p.cursors + 4 * len(tree_pages(TREE))
    p.values_mark = p.values + VALUES_SIZE
    p.ram_end = p.values_mark + 2
    return p


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def encode_adr(rd: int, from_off: int, target_off: int) -> bytes:
    base = (from_off + 4) & ~3
    if target_off < base or (target_off - base) % 4:
        raise ValueError(f"ADR bad align/range {from_off:#x}->{target_off:#x}")
    imm8 = (target_off - base) // 4
    if imm8 > 0xFF:
        raise ValueError(f"ADR imm too large: {imm8}")
    return struct.pack("<H", 0xA000 | ((rd & 7) << 8) | imm8)


def word_session(reg: int, val: int) -> list[bytes]:
    return [
        bytes([0xBF, 0x3F]),
        bytes([0xC0 | reg, val & 0xFF]),
        bytes([0xC0 | (reg + 1), (val >> 8) & 0xFF]),
        bytes([0xFF, 0x55]),
    ]


def cstr(text: str) -> bytes:
    return text.encode("cp1251") + b"\x00"


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def read_str(img: bytes, ptr: int) -> str:
    off = ptr - APP_BASE
    end = img.index(b"\x00", off)
    return img[off:end].decode("cp1251")


def check_profile(p: SimpleNamespace, stock: bytes) -> None:
    expect(decode_bl(stock, p.hook) == p.svc, f"hook {p.hook:#x}: no BL {p.svc:#x}")
    expect(struct.unpack_from("<H", stock, p.nav_limit)[0] == 0x2802, "nav limit mismatch")
    expect(u32(stock, p.nav_lit) == p.nav_ram_stock, "nav literal mismatch")
    expect(u32(stock, p.main_page + 4) == APP_BASE + p.main_items, "main items ptr mismatch")
    expect(u32(stock, p.main_page + 8) == MAIN_COUNT, "main count mismatch")
    tmpl = struct.unpack_from("<5I", stock, p.template)
    expect(tmpl[0] == TEMPLATE_HEADER and tmpl[4] == 0x17, "submenu template mismatch")
    for key, name in ICON_NAMES.items():
        got = read_str(stock, u32(stock, getattr(p, key)))
        expect(got == name, f"{key}: '{got}' != '{name}'")
        expect(u32(stock, getattr(p, key) + 8) != 0, f"{key}: no icon")
    info = p.icon_info - p.main_items
    expect(0 <= info < MAIN_COUNT * REC and info % REC == 0 and u32(stock, p.icon_info + 16) == 1,
           "icon_info: not a main menu action record")
    sp = struct.unpack_from("<5I", stock, p.settings_page)
    expect(sp[0] == 0x7B7B3206 and sp[4] == TEXT_STOCK_PITCH, "Settings page mismatch")
    expect(all(u32(stock, sp[1] - APP_BASE + k * REC + 8) == 0 for k in range(sp[2])),
           "Settings rows not icon-less")
    glyph = u32(stock, sp[3] - APP_BASE + 4 * ord("A"))  # font = 256 glyph ptrs; glyph {w, h, columns}
    expect(glyph and stock[glyph - APP_BASE + 1] == SMALL_FONT_H, "small font height mismatch")
    if hasattr(p, "ver_bl"):
        expect(
            struct.unpack_from("<H", stock, p.ver_bl - 2)[0] == 0x2000 | p.ver_minor
            and decode_bl(stock, p.ver_bl) == p.itoa
            and struct.unpack_from("<H", stock, p.ver_bl + 4)[0] == 0xA800 | p.ver_text_sp // 4
            and decode_bl(stock, p.ver_bl + 6) == p.draw,
            "version draw pattern mismatch",
        )
    if hasattr(p, "tx_submit"):
        w = p.wrapper
        expect(
            decode_bl(stock, w + 2) == p.tx_miles
            and u32(stock, ((w + 6 + 4) & ~3) + (stock[w + 6] << 2)) == p.tx_cfg
            and struct.unpack_from("<H", stock, w + 8)[0] == 0x7880
            and decode_bl(stock, w + 10) == p.tx_wait
            and decode_bl(stock, p.tx_miles + 0x24) == p.tx_submit
            and struct.unpack_from("<H", stock, p.tx_miles + 0x20)[0] == 0x2118,
            "IR wrapper / Miles pattern mismatch",
        )


def build_cave(p: SimpleNamespace, stock: bytes, gap_ms: int) -> tuple[bytes, dict]:
    period = FRAME_MS + gap_ms
    code = bytearray()
    fix: list[tuple[str, int, str]] = []
    lab: dict[str, int] = {}
    pool: dict[int, str] = {}
    nlit = [0]
    pages = tree_pages(TREE)
    expect(p.pkt + 4 * NSLOTS <= p.target < p.cursors, "target byte overlaps packets/cursors")
    shared = [kid[4] for pg in pages for kid in pg[4] if kid[0] == "link"]
    for pg in pages:
        kinds = {"page" if kid[0] == "link" else kid[0] for kid in pg[4]}
        # stock menu faults drawing a value row among submenu rows
        expect(not {"page", "value"} <= kinds, f"page '{pg[1]}' mixes submenus and value rows")
        # a value page with 5 rows reboots the remote; 4 rows are tested
        expect("value" not in kinds or len(pg[4]) <= 4, f"value page '{pg[1]}' has more than 4 rows")
        expect("text" not in kinds or kinds == {"text"}, f"page '{pg[1]}' mixes text and other rows")
        regs = {kid[3] == REG_TARGET for kid in pg[4] if kid[0] == "action"}
        expect(len(regs) <= 1, f"page '{pg[1]}' mixes REG_TARGET and fixed actions")
    for top in shared:
        inner = tree_pages(top)
        expect(not any(kid[0] == "link" for q in inner for kid in q[4]), "link inside a shared page")
        expect(all(kid[3] == REG_TARGET for q in inner for kid in q[4] if kid[0] == "action"),
               f"shared page '{top[1]}' has fixed-register actions")
        outside = [q for q in pages if not any(q is r for r in inner)]
        expect(not any(sub_page(kid) is r for q in outside for kid in q[4] if kid[0] == "page"
                       for r in inner), f"shared page '{top[1]}' also opened as a plain submenu")
    for pg in pages:
        if not any(any(pg is r for r in tree_pages(top)) for top in shared):
            expect(all(kid[3] != REG_TARGET for kid in pg[4] if kid[0] == "action"),
                   f"page '{pg[1]}': REG_TARGET action outside a shared list")
    small_font = u32(stock, p.settings_page + 12)

    def here() -> int:
        return p.cave + len(code)

    def emit(hw: int) -> None:
        code.extend(struct.pack("<H", hw & 0xFFFF))

    def ph(kind: str, label: str) -> None:
        fix.append((kind, here(), label))
        code.extend(b"\x00\x00")

    def bl(target: int) -> None:
        code.extend(encode_bl(here(), target))

    def align4() -> None:
        while len(code) % 4:
            emit(0xBF00)

    def ldr(rd: int, val: int) -> None:
        if val not in pool:
            pool[val] = f"lit#{nlit[0]}"
            nlit[0] += 1
        ph(f"ldr{rd}", pool[val])

    def flush() -> None:
        align4()
        for val, name in pool.items():
            lab[name] = here()
            code.extend(struct.pack("<I", val))
        pool.clear()

    def func(name: str) -> None:
        align4()
        lab[name] = here()

    # tx_frame(r0 = slot): byte 0 == 0 -> skip; byte 3 == 1 -> raw 24 bits (bytes 0..2 as is),
    # else stock 2-byte Miles (third byte E8/XOR)
    func("tx_frame")
    emit(0xB510)  # push {r4, lr}
    emit(0x7801)  # ldrb r1, [r0, #0]
    emit(0x2900)  # cmp r1, #0
    ph("beq", "tf_out")
    if hasattr(p, "tx_submit"):
        emit(0x78C1)  # ldrb r1, [r0, #3]
        emit(0x2900)  # cmp r1, #0
        ph("beq", "tf_stock")
        emit(0x2118)  # movs r1, #24
        bl(p.tx_submit)
        ldr(0, p.tx_cfg)
        emit(0x7880)  # ldrb r0, [r0, #2]
        bl(p.tx_wait)
        ph("b", "tf_out")
        lab["tf_stock"] = here()
    bl(p.wrapper)
    lab["tf_out"] = here()
    emit(0xBD10)  # pop {r4, pc}
    flush()

    # cave_tick: replaces BL svc in the main loop
    lab["tick"] = here()
    emit(0xB5F0)  # push {r4-r7, lr}
    bl(p.svc)
    ldr(4, p.state)
    emit(0x6820)  # ldr r0, [r4, #0]   magic
    ldr(1, MAGIC)
    emit(0x4288)  # cmp r0, r1
    ph("bne", "out")
    bl(p.gettick)
    emit(0x68A1)  # ldr r1, [r4, #8]   due
    emit(0x1A42)  # subs r2, r0, r1
    ph("bmi", "out")
    emit(0x6865)  # ldr r5, [r4, #4]   step
    emit(0x2D00 | NSLOTS)  # cmp r5, #NSLOTS
    ph("bcs", "clear")
    ldr(2, period)
    emit(0x1880)  # adds r0, r0, r2
    emit(0x60A0)  # str r0, [r4, #8]   due = now + period
    emit(0x1C68)  # adds r0, r5, #1
    emit(0x6060)  # str r0, [r4, #4]
    emit(0x2800 | NSLOTS)  # cmp r0, #NSLOTS
    ph("bcc", "send")
    lab["clear"] = here()
    emit(0x2000)  # movs r0, #0
    emit(0x6020)  # str r0, [r4, #0]   magic = 0
    emit(0x2D00 | NSLOTS)  # cmp r5, #NSLOTS
    ph("bcs", "out")
    lab["send"] = here()
    emit(0x68E0)  # ldr r0, [r4, #12]  packet set
    emit(0x00A9)  # lsls r1, r5, #2
    emit(0x1840)  # adds r0, r0, r1
    bl(lab["tx_frame"])
    lab["out"] = here()
    emit(0xBDF0)  # pop {r4-r7, pc}
    flush()

    # press_common(r0 = packet set)
    func("press_common")
    emit(0xB510)  # push {r4, lr}
    emit(0x0004)  # movs r4, r0
    bl(p.gettick)
    ldr(1, p.state)
    emit(0x60CC)  # str r4, [r1, #12]  packet set
    emit(0x6088)  # str r0, [r1, #8]   due = now
    emit(0x2200)  # movs r2, #0
    emit(0x604A)  # str r2, [r1, #4]   step = 0
    ldr(2, MAGIC)
    emit(0x600A)  # str r2, [r1, #0]   magic
    emit(0xBD10)  # pop {r4, pc}
    flush()

    # values_ready() -> r0 = &values; first use after power-on sets defaults
    func("values_ready")
    emit(0xB500)  # push {lr}
    ldr(0, p.values)
    ldr(1, p.values_mark)
    emit(0x8809)  # ldrh r1, [r1, #0]
    ldr(2, VALUES_MARK)
    emit(0x4291)  # cmp r1, r2
    ph("bne", "vr_init")
    emit(0xBD00)  # pop {pc}
    lab["vr_init"] = here()
    for _ru, _en, byte, _step, _max, default, *_ in VALUES.values():
        emit(0x2100 | default)  # movs r1, #default
        if byte < 32:
            emit(0x7000 | byte << 6 | 0x01)  # strb r1, [r0, #byte]
        else:
            emit(0x2300 | byte)  # movs r3, #byte
            emit(0x18C3)  # adds r3, r0, r3
            emit(0x7019)  # strb r1, [r3, #0]
    ldr(3, p.values_mark)
    emit(0x801A)  # strh r2, [r3, #0]
    emit(0xBD00)  # pop {pc}
    flush()

    # send_word(r0 = register, r1 = u16): packets into pkt RAM, arm session
    func("send_word")
    emit(0xB510)  # push {r4, lr}
    ldr(4, p.pkt)
    ldr(2, 0xBF | (0x3F << 8))
    emit(0x6022)  # str r2, [r4, #0]   BF 3F
    ldr(2, 0xFF | (0x55 << 8))
    emit(0x60E2)  # str r2, [r4, #12]  FF 55
    emit(0x22C0)  # movs r2, #0xC0
    emit(0x4302)  # orrs r2, r0        C0|reg
    emit(0x060B)  # lsls r3, r1, #24
    emit(0x0C1B)  # lsrs r3, r3, #16
    emit(0x4313)  # orrs r3, r2
    emit(0x6063)  # str r3, [r4, #4]   C0|reg, lo
    emit(0x3201)  # adds r2, #1
    emit(0x0A0B)  # lsrs r3, r1, #8
    emit(0x061B)  # lsls r3, r3, #24
    emit(0x0C1B)  # lsrs r3, r3, #16
    emit(0x4313)  # orrs r3, r2
    emit(0x60A3)  # str r3, [r4, #8]   C0|reg+1, hi
    emit(0x2200)  # movs r2, #0
    for s in range(4, NSLOTS):
        emit(0x6000 | s << 6 | 4 << 3 | 2)  # str r2, [r4, #4*s]  skipped slot
    emit(0x0020)  # movs r0, r4
    bl(lab["press_common"])
    emit(0xBD10)  # pop {r4, pc}
    flush()

    # send_fak(r0 = address, r1 = value, r2 = device): medkit write as in the configurator:
    # BF 3F (Identify), one skipped slot (the medkit misses frames while it answers 3F 21),
    # raw A3 addr byte frames, each twice, BF 65 (finish config -> BF 65 DA), then skipped slots.
    # DEV_FAK: A3 a v; DEV_FAK_WORD: A3 a lo, A3 a+1 hi;
    # DEV_FAK_CMD (value = c0 | c1 << 8): A3 a c0, A3 a+1 c1, A3 a+2 c2 (c2 = c0 >= B0 ? c0^c1 : E8)
    def str_r(rt: int, slot: int) -> None:
        emit(0x6000 | slot << 6 | 4 << 3 | rt)  # str rt, [r4, #4*slot]

    def fin(rt: int, slot: int) -> None:
        ldr(rt, 0xBF | (0x65 << 8))
        str_r(rt, slot)  # BF 65

    func("send_fak")
    emit(0xB570)  # push {r4-r6, lr}
    ldr(4, p.pkt)
    emit(0x2300)  # movs r3, #0
    for s in range(1, NSLOTS):
        str_r(3, s)  # skipped slot
    if FAK_WRITE_IDENTIFY:
        ldr(3, 0xBF | (0x3F << 8))
    str_r(3, 0)  # BF 3F or skipped
    emit(0x0600)  # lsls r0, r0, #24
    emit(0x0C00)  # lsrs r0, r0, #16   addr << 8
    ldr(3, 0x010000A3)
    emit(0x4318)  # orrs r0, r3        A3 addr 00, raw
    emit(0x060B)  # lsls r3, r1, #24
    emit(0x0A1B)  # lsrs r3, r3, #8    lo << 16
    emit(0x4303)  # orrs r3, r0
    str_r(3, 2)
    str_r(3, 3)
    emit(0x2A01)  # cmp r2, #1
    ph("bne", "fk_multi")
    fin(5, 4)
    ph("b", "fk_go")
    lab["fk_multi"] = here()
    emit(0x2601)  # movs r6, #1
    emit(0x0236)  # lsls r6, r6, #8    address + 1
    emit(0x1980)  # adds r0, r0, r6
    emit(0x0A0B)  # lsrs r3, r1, #8
    emit(0x061B)  # lsls r3, r3, #24
    emit(0x0A1B)  # lsrs r3, r3, #8    hi << 16
    emit(0x4303)  # orrs r3, r0
    str_r(3, 4)
    str_r(3, 5)
    emit(0x2A03)  # cmp r2, #3
    ph("beq", "fk_cmd")
    fin(5, 6)
    ph("b", "fk_go")
    lab["fk_cmd"] = here()
    emit(0x1980)  # adds r0, r0, r6
    emit(0x060B)  # lsls r3, r1, #24
    emit(0x0E1B)  # lsrs r3, r3, #24   c0
    emit(0x25E8)  # movs r5, #0xE8
    emit(0x2BB0)  # cmp r3, #0xB0
    ph("bcc", "fk_c2")
    emit(0x0A0D)  # lsrs r5, r1, #8    c1
    emit(0x405D)  # eors r5, r3
    emit(0x062D)  # lsls r5, r5, #24
    emit(0x0E2D)  # lsrs r5, r5, #24
    lab["fk_c2"] = here()
    emit(0x042D)  # lsls r5, r5, #16
    emit(0x4305)  # orrs r5, r0
    str_r(5, 6)
    str_r(5, 7)
    fin(3, 8)
    lab["fk_go"] = here()
    emit(0x0020)  # movs r0, r4
    bl(lab["press_common"])
    emit(0xBD70)  # pop {r4-r6, pc}
    flush()

    # value item handler (flag 2): r0 = &event (0 '+', 1 '-', 2 draw) or NULL (OK),
    # r1 = descriptor {byte, step, max, group base, register, min sent, group size, radix}
    func("val_common")
    emit(0xB5F0)  # push {r4-r7, lr}
    emit(0x0006)  # movs r6, r0   event
    emit(0x000D)  # movs r5, r1   descriptor
    bl(lab["values_ready"])
    emit(0x0007)  # movs r7, r0   values
    emit(0x7829)  # ldrb r1, [r5, #0]
    emit(0x187C)  # adds r4, r7, r1  &value
    emit(0x2E00)  # cmp r6, #0
    ph("beq", "v_send")
    emit(0x7830)  # ldrb r0, [r6]
    emit(0x2802)  # cmp r0, #2
    ph("beq", "v_draw")
    emit(0x2801)  # cmp r0, #1
    ph("beq", "v_dec")
    emit(0x2800)  # cmp r0, #0
    ph("bne", "v_out")
    emit(0x7820)  # ldrb r0, [r4]
    emit(0x7869)  # ldrb r1, [r5, #1]  step
    emit(0x1840)  # adds r0, r0, r1
    emit(0x78A9)  # ldrb r1, [r5, #2]  max
    emit(0x4288)  # cmp r0, r1
    ph("bhi", "v_out")
    emit(0x7020)  # strb r0, [r4]
    ph("b", "v_out")
    lab["v_dec"] = here()
    emit(0x7820)  # ldrb r0, [r4]
    emit(0x7869)  # ldrb r1, [r5, #1]  step
    emit(0x4288)  # cmp r0, r1
    ph("bcc", "v_out")
    emit(0x1A40)  # subs r0, r0, r1
    emit(0x7020)  # strb r0, [r4]
    ph("b", "v_out")
    lab["v_draw"] = here()
    ldr(0, TEXT_STRUCT)
    emit(0x7B82)  # ldrb r2, [r0, #14]
    ldr(1, TEXT_STRUCT + 6)
    ldr(0, TEXT_STRUCT + 4)
    bl(p.prep)
    ldr(0, p.text_buf)
    emit(0x2120)  # movs r1, #' '
    emit(0x7001)  # strb r1, [r0]
    emit(0x1C41)  # adds r1, r0, #1
    emit(0x7820)  # ldrb r0, [r4]
    bl(p.itoa)
    ldr(0, TEXT_STRUCT)
    bl(p.draw)
    ph("b", "v_out")
    lab["v_send"] = here()
    emit(0x78E9)  # ldrb r1, [r5, #3]  group base
    emit(0x1879)  # adds r1, r7, r1
    emit(0x79AA)  # ldrb r2, [r5, #6]  group size
    emit(0x79EB)  # ldrb r3, [r5, #7]  radix
    emit(0x2000)  # movs r0, #0
    lab["v_loop"] = here()
    emit(0x4358)  # muls r0, r3
    emit(0x780E)  # ldrb r6, [r1, #0]
    emit(0x1980)  # adds r0, r0, r6
    emit(0x3101)  # adds r1, #1
    emit(0x3A01)  # subs r2, #1
    ph("bne", "v_loop")
    emit(0x7969)  # ldrb r1, [r5, #5]  min sent
    emit(0x4288)  # cmp r0, r1
    ph("bcs", "v_min_ok")
    emit(0x0008)  # movs r0, r1
    lab["v_min_ok"] = here()
    emit(0x8929)  # ldrh r1, [r5, #8]  max sent
    emit(0x4288)  # cmp r0, r1
    ph("bls", "v_cap_ok")
    emit(0x0008)  # movs r0, r1
    lab["v_cap_ok"] = here()
    emit(0x0001)  # movs r1, r0
    emit(0x7AAA)  # ldrb r2, [r5, #10] device
    emit(0x7928)  # ldrb r0, [r5, #4]  register
    emit(0x2A00)  # cmp r2, #0
    ph("beq", "v_word")
    bl(lab["send_fak"])
    ph("b", "v_out")
    lab["v_word"] = here()
    bl(lab["send_word"])
    lab["v_out"] = here()
    emit(0xBDF0)  # pop {r4-r7, pc}
    flush()

    for key, (_ru, _en, byte, step, vmax, _d, base, reg, vmin, size, radix, cap, dev) in VALUES.items():
        func(f"val:{key}")
        code.extend(encode_adr(1, here(), here() + 4))
        code.extend(encode_b(here(), lab["val_common"]))
        code.extend(bytes([byte, step, vmax, base, reg, vmin, size, radix]))
        code.extend(struct.pack("<HBB", cap, dev, 0))

    if tree_items("text"):
        func("noop")  # OK on a text row
        emit(0x4770)  # bx lr

    # action item handler (flag 1, called on OK): r1 = entry {register, device, u16 value};
    # one copy per action page keeps every stub's B within range
    k = 0
    for i, pg in enumerate(pages):
        acts = [kid for kid in pg[4] if kid[0] == "action"]
        if not acts:
            continue
        func(f"act_common{i}")
        emit(0xB500)  # push {lr}
        if acts[0][3] == REG_TARGET:
            ldr(0, p.target)
            emit(0x7800)  # ldrb r0, [r0, #0]  register set by the opening link
        else:
            emit(0x7808)  # ldrb r0, [r1, #0]
        if any(kid[5] for kid in acts):
            emit(0x784A)  # ldrb r2, [r1, #1]  device
            emit(0x8849)  # ldrh r1, [r1, #2]
            emit(0x2A00)  # cmp r2, #0
            ph("beq", f"act_word{i}")
            bl(lab["send_fak"])
            emit(0xBD00)  # pop {pc}
            lab[f"act_word{i}"] = here()
        else:
            emit(0x8849)  # ldrh r1, [r1, #2]
        bl(lab["send_word"])
        emit(0xBD00)  # pop {pc}
        flush()
        for _kind, _ru, _en, reg, val, dev in acts:
            func(f"act{k}")
            code.extend(encode_adr(1, here(), here() + 4))
            code.extend(encode_b(here(), lab[f"act_common{i}"]))
            code.extend(struct.pack("<BBH", reg, dev, val))
            k += 1

    # screen handlers: clone of stock submenu handler, page struct right after
    # {x0 y0 x1 y1 bytes, items, count, font, pitch} (header/font/pitch from a stock submenu page)
    tmpl = struct.unpack_from("<5I", stock, p.template)
    ptrs: list[tuple[int, str]] = []  # (code index, label) -> APP_BASE + label
    # link row handler right before the shared page's screen: target register -> RAM, then fall
    # into the screen (r0 = event kept); stock calls it on entry, every poll and Back, so the
    # register always follows the row that opened the list
    links = tree_items("link")
    for i, pg in enumerate(pages):
        count = len(pg[4])
        cursor = p.cursors + 4 * i
        for n, kid in enumerate(links):
            if kid[4] is pg:
                func(f"tramp{n}")
                ldr(1, p.target)
                emit(0x2200 | kid[5])  # movs r2, #reg
                emit(0x700A)  # strb r2, [r1, #0]
                ph("b", f"screen{i}")
        func(f"screen{i}")
        emit(0xB580)  # push {r7, lr}
        ldr(2, cursor)
        emit(0x6813)  # ldr r3, [r2]
        emit(0x2B00 | count)  # cmp r3, #count
        ph("bcc", f"cur_ok{i}")
        emit(0x2300)  # movs r3, #0
        emit(0x6013)  # str r3, [r2]
        lab[f"cur_ok{i}"] = here()
        ph("adr1", f"page{i}")
        bl(p.enter)
        ldr(1, cursor)
        ph("adr0", f"page{i}")
        bl(p.keys)
        emit(0xBD80)  # pop {r7, pc}
        flush()
        lab[f"page{i}"] = here()
        ptrs.append((len(code) + 4, f"items{i}"))
        opts = pg[5]
        font = small_font if opts["small"] else tmpl[3]
        code.extend(struct.pack("<5I", tmpl[0], 0, count, font, opts["pitch"] or tmpl[4]))

    # 'Информация': replaces BL itoa(minor); the next stock draw shows "<minor>-mod"
    if hasattr(p, "ver_bl"):
        func("ver_minor")
        ph("ldr0", "ver_ptr")
        emit(0x9000 | p.ver_text_sp // 4)  # str r0, [sp, #ver_text_sp]
        emit(0x4770)  # bx lr
        align4()
        lab["ver_ptr"] = here()
        ptrs.append((len(code), "ver_str"))
        code.extend(b"\x00" * 4)
        lab["ver_str"] = here()
        code.extend(cstr(f"{p.ver_minor}-mod"))
        while len(code) % 4:
            code.append(0)

    texts: list[str] = []

    def rec(ru: str, en: str, icon_rec: int | None, handler: str, flag: int) -> None:
        at = len(code)
        icon = 0 if icon_rec is None else u32(stock, icon_rec + 8)
        code.extend(struct.pack("<5I", 0, 0, icon, 0, flag))
        for t, k in ((ru, 0), (en, 4)):
            if t not in texts:
                texts.append(t)
            ptrs.append((at + k, f"str:{t}"))
        ptrs.append((at + 12, handler))

    lab["items_main"] = here()
    code.extend(stock[p.main_items : p.main_items + MAIN_COUNT * REC])
    rec(TREE[1], TREE[2], getattr(p, TREE[3]), "screen0", 0)
    actions = tree_items("action")
    for i, pg in enumerate(pages):
        lab[f"items{i}"] = here()
        for kid in pg[4]:
            if kid[0] == "page":
                j = next(n for n, q in enumerate(pages) if q is kid)
                rec(kid[1], kid[2], getattr(p, kid[3]), f"screen{j}", 0)
            elif kid[0] == "value":
                ru, en = VALUES[kid[1]][:2]
                rec(ru, en, getattr(p, VALUE_ICON), f"val:{kid[1]}", 2)
            elif kid[0] == "link":
                n = next(m for m, q in enumerate(links) if q is kid)
                rec(kid[1], kid[2], getattr(p, kid[3]), f"tramp{n}", 0)
            elif kid[0] == "text":
                rec(kid[1], kid[1], None, "noop", 1)
            else:
                k = next(n for n, q in enumerate(actions) if q is kid)
                rec(kid[1], kid[2], getattr(p, ACTION_ICON), f"act{k}", 1)

    for t in texts:
        lab[f"str:{t}"] = here()
        code.extend(cstr(t))
        while len(code) % 4:
            code.append(0)

    for at, label in ptrs:
        val = APP_BASE + lab[label]
        if label.startswith(("screen", "val:", "act", "noop", "tramp")):
            val |= 1
        struct.pack_into("<I", code, at, val)

    conds = {"beq": 0, "bne": 1, "bcs": 2, "bcc": 3, "bmi": 4, "bhi": 8, "bls": 9}
    for kind, at, label in fix:
        tgt = lab[label]
        if kind.startswith("ldr"):
            enc = encode_ldr_lit(int(kind[3]), at, tgt)
        elif kind.startswith("adr"):
            enc = encode_adr(int(kind[3]), at, tgt)
        elif kind == "b":
            enc = encode_b(at, tgt)
        else:
            enc = encode_bcond(at, tgt, conds[kind])
        code[at - p.cave : at - p.cave + 2] = enc

    return bytes(code), {"labels": lab, "period_ms": period, "gap_ms": gap_ms}


def build_image(p: SimpleNamespace, stock: bytes, gap_ms: int) -> tuple[bytearray, dict]:
    check_profile(p, stock)
    expect(p.ram_end <= p.ram_base + RAM_SIZE, f"values end {p.ram_end:#x} past RAM budget")
    expect(all(row[2] < VALUES_SIZE for row in VALUES.values()), "value bytes past VALUES_SIZE")
    image = bytearray(stock)
    cave, meta = build_cave(p, stock, gap_ms)
    lab = meta["labels"]
    cave_end = p.cave + len(cave)
    expect(cave_end <= STOCK_SIZE - TRAILER_LEN, "cave too large")
    expect(all(b == 0xFF for b in stock[p.cave:cave_end]), "cave region not free")
    image[p.cave:cave_end] = cave

    struct.pack_into("<H", image, p.nav_limit, 0x2800 | NAV_DEPTH)
    struct.pack_into("<I", image, p.nav_lit, p.nav_ram)

    image[p.hook : p.hook + 4] = encode_bl(p.hook, lab["tick"])
    expect(decode_bl(bytes(image), p.hook) == lab["tick"], "main loop hook encode mismatch")

    if hasattr(p, "ver_bl"):
        image[p.ver_bl : p.ver_bl + 4] = encode_bl(p.ver_bl, lab["ver_minor"])
        expect(decode_bl(bytes(image), p.ver_bl) == lab["ver_minor"], "version BL encode mismatch")

    struct.pack_into("<I", image, p.main_page + 4, APP_BASE + lab["items_main"])
    struct.pack_into("<I", image, p.main_page + 8, MAIN_COUNT + 1)

    meta["cave_end"] = cave_end
    meta["sig"] = sign_image(image)
    return image, meta


def page_items(img: bytes, page_off: int) -> list[tuple[str, str, int, int]]:
    items = u32(img, page_off + 4) - APP_BASE
    count = u32(img, page_off + 8)
    out = []
    for k in range(count):
        ru, en, _icon, handler, flag = struct.unpack_from("<5I", img, items + k * REC)
        out.append((read_str(img, ru), read_str(img, en), handler, flag))
    return out


def verify(p: SimpleNamespace, image: bytes, stock: bytes, meta: dict) -> list[str]:
    lab = meta["labels"]
    period = meta["period_ms"]
    pages = tree_pages(TREE)
    log: list[str] = []
    st = {"tick": 5000, "sent": [], "enter": None, "keys": None}

    def gettick(emu: ThumbEmu) -> None:
        emu.r[0] = st["tick"]

    def svc(emu: ThumbEmu) -> None:
        emu.r[0] = 0

    def wrapper(emu: ThumbEmu) -> None:
        a = emu.r[0]
        st["sent"].append((st["tick"], bytes([emu.rd8(a), emu.rd8(a + 1)]).hex()))
        for i in (0, 4, 5):
            emu.r[i] = 0xBAD00000 | i

    def tx_submit(emu: ThumbEmu) -> None:
        expect(emu.r[1] == 24, f"tx_submit bits {emu.r[1]}")
        a = emu.r[0]
        st["sent"].append((st["tick"], bytes(emu.rd8(a + i) for i in range(3)).hex()))
        for i in (0, 1, 2, 3):
            emu.r[i] = 0xBAD00000 | i

    def tx_wait(emu: ThumbEmu) -> None:
        for i in (0, 1, 2, 3):
            emu.r[i] = 0xBAD00000 | i

    def enter(emu: ThumbEmu) -> None:
        st["enter"] = (emu.r[0], emu.r[1] - FLASH, emu.r[2])

    def keys(emu: ThumbEmu) -> None:
        st["keys"] = (emu.r[0] - FLASH, emu.r[1])

    def prep(emu: ThumbEmu) -> None:
        expect(
            (emu.r[0], emu.r[1]) == (TEXT_STRUCT + 4, TEXT_STRUCT + 6),
            "prep args mismatch",
        )

    def itoa(emu: ThumbEmu) -> None:
        digits = str(emu.r[0] & 0xFF).encode()
        emu.wrn(emu.r[1], int.from_bytes(digits + b"\x00", "little"), len(digits) + 1)
        emu.r[0] = len(digits) + 1

    def draw(emu: ThumbEmu) -> None:
        expect(emu.r[0] == TEXT_STRUCT, "draw arg mismatch")
        out = bytearray()
        a = p.text_buf
        while emu.rd8(a):
            out.append(emu.rd8(a))
            a += 1
        st["drawn"] = out.decode()

    emu = ThumbEmu(
        image,
        {
            p.gettick: gettick,
            p.svc: svc,
            p.wrapper: wrapper,
            p.tx_submit: tx_submit,
            p.tx_wait: tx_wait,
            p.enter: enter,
            p.keys: keys,
            p.prep: prep,
            p.itoa: itoa,
            p.draw: draw,
        },
        cave_off=p.cave,
    )
    emu.r[13] = 0x20001300
    for a in range(p.ram_base, p.ram_end):
        emu.ram[a] = 0xA5

    def tick(n: int) -> None:
        for _ in range(n):
            emu.call(lab["tick"])
            st["tick"] += 1

    tick(50)
    expect(not st["sent"], f"sent without press: {st['sent']}")

    main = page_items(image, p.main_page)
    expect(len(main) == MAIN_COUNT + 1, f"main count {len(main)}")
    expect(
        image[lab["items_main"] : lab["items_main"] + MAIN_COUNT * REC]
        == stock[p.main_items : p.main_items + MAIN_COUNT * REC],
        "stock main items changed",
    )

    def open_screen(handler: int, cursor: int, count: int) -> int:
        off = (handler - APP_BASE) & ~1
        evt = 0x20000900
        emu.r[0] = evt
        emu.call(off)
        e_evt, e_page, e_cur = st["enter"]
        k_page, k_cur = st["keys"]
        expect(e_evt == evt, "event ptr not passed to menu enter")
        expect(e_page == k_page and e_cur == k_cur == cursor, "screen args mismatch")
        expect(emu.rd32(cursor) < count, "cursor not sanitized")
        return e_page

    evt = 0x20000900

    def send_via(off: int, r0: int) -> list[str]:
        st["sent"].clear()
        emu.r[0] = r0
        emu.call(off)
        tick(period * NSLOTS + 20)
        sent = list(st["sent"])
        gaps = [b[0] - a[0] for a, b in zip(sent, sent[1:])]
        if len(sent) > 1 and sent[0][1] == "bf3f" and sent[1][1].startswith("a3"):
            expect(gaps[0] == 2 * period, f"pause after identify {gaps[0]}")
            gaps = gaps[1:]
        expect(all(g == period for g in gaps), f"gaps {gaps}")
        return [h for _t, h in sent]

    def want(reg: int, val: int, dev: int = DEV_POINT) -> list[str]:
        if dev == DEV_POINT:
            return [pk.hex() for pk in word_session(reg, val)]
        if dev == DEV_FAK:
            data = [val]
            addrs = [reg]
        elif dev == DEV_FAK_WORD:
            data = [val & 0xFF, val >> 8]
            addrs = [reg, reg + 1]
        else:
            c0, c1 = val & 0xFF, val >> 8
            data = [c0, c1, c0 ^ c1 if c0 >= 0xB0 else 0xE8]
            addrs = [reg, reg + 1, reg + 2]
        writes = [bytes([0xA3, a, v]).hex() for a, v in zip(addrs, data) for _ in range(2)]
        return ["bf3f"] * FAK_WRITE_IDENTIFY + writes + ["bf65"]

    def event(off: int, code: int) -> str | None:
        st["drawn"] = None
        emu.ram[evt] = code
        emu.r[0] = evt
        emu.call(off)
        return st["drawn"]

    defaults_checked = [False]

    def test_value(key: str, off: int) -> str:
        _ru, _en, byte, step, vmax, _d, base, reg, vmin, size, radix, cap, dev = VALUES[key]
        at = p.values + byte
        shown = event(off, 2)
        if not defaults_checked[0]:
            for k, row in VALUES.items():
                expect(emu.rd8(p.values + row[2]) == row[5], f"default {k}")
            expect(emu.rd16(p.values_mark) == VALUES_MARK, "values mark not set")
            defaults_checked[0] = True
        expect(shown == f" {emu.rd8(at)}", f"{key}: drawn {shown!r}")
        start = emu.rd8(at)
        if start + step <= vmax:
            event(off, 0)
            expect(emu.rd8(at) == start + step, f"{key}: '+' failed")
        for _ in range(100):
            event(off, 0)
        expect(emu.rd8(at) == vmax, f"{key}: max {emu.rd8(at)} != {vmax}")
        expect(event(off, 2) == f" {vmax}", f"{key}: draw max")
        for _ in range(100):
            event(off, 1)
        expect(emu.rd8(at) == 0, f"{key}: min {emu.rd8(at)}")
        expect(event(off, 2) == " 0", f"{key}: draw 0")
        group = sorted((r for r in VALUES.values() if r[6] == base), key=lambda r: r[2])
        expect(len(group) == size, f"{key}: group size {len(group)} != {size}")
        maxes = [r[4] for r in group]
        cases = [
            [0] * size,
            maxes,
            [1] + [0] * (size - 1),
            [min(3, m) - min(3, m) % r[3] for m, r in zip(maxes, group)],
        ]
        if size == 1:
            cases.append([5])
        sums = []
        for digits in cases:
            total = 0
            for i, d in enumerate(digits):
                emu.ram[p.values + base + i] = d
                total = total * radix + d
            total = min(cap, max(vmin, total))
            got = send_via(off, 0)
            expect(got == want(reg, total, dev), f"{key} {digits} sent {got}")
            sums.append(total)
        return f"0..{vmax} step {step}, OK -> reg {reg}: {sums}"

    # stock text width (r0 = str, r1 = font) on the stock image mapped at APP_BASE
    stock_emu = ThumbEmu(b"\xff" * (APP_BASE - FLASH) + stock, {}, cave_off=0)
    stock_emu.r[13] = 0x20001300

    def measure(text: str) -> int:
        for k, c in enumerate(cstr(text)):
            stock_emu.ram[0x20000800 + k] = c
        stock_emu.r[0] = 0x20000800
        stock_emu.r[1] = u32(stock, p.settings_page + 12)
        stock_emu.call(APP_BASE - FLASH + p.measure, max_steps=20000)
        return stock_emu.r[0]

    expect((measure("A"), measure("AB")) == (6, 12), "stock text measure mismatch")

    def walk(i: int, handler: int, depth: int, target: int | None = None) -> None:
        pg = pages[i]
        kids = pg[4]
        cursor = p.cursors + 4 * i
        page_off = open_screen(handler, cursor, len(kids))
        expect(page_off == lab[f"page{i}"], f"screen{i} opened page {page_off:#x}")
        items = page_items(image, page_off)
        expect(len(items) == len(kids), f"page{i} count {len(items)}")
        pad = "  " * depth
        acts = 0
        cmd_logged = False
        font, pitch = u32(image, page_off + 12), u32(image, page_off + 16)
        tmpl = struct.unpack_from("<5I", stock, p.template)
        if pg[5]["small"]:
            expect(font == u32(stock, p.settings_page + 12), f"page{i}: font {font:#x}")
        else:
            expect(font == tmpl[3], f"page{i}: font {font:#x}")
        expect(pitch == (pg[5]["pitch"] or tmpl[4]), f"page{i}: pitch {pitch}")
        if kids[0][0] == "text":
            noop = lab["noop"]
            expect(struct.unpack_from("<H", image, noop)[0] == 0x4770, "noop is not bx lr")
            for k, ((ru, en, h, flag), kid) in enumerate(zip(items, kids)):
                icon = u32(image, u32(image, page_off + 4) - APP_BASE + k * REC + 8)
                expect((ru, en, flag, icon, h) == (kid[1], kid[1], 1, 0, APP_BASE + noop | 1),
                       f"text row {k}: {ru}/{en}/{flag}/{icon:#x}/{h:#x}")
            got = send_via(noop, 0)
            expect(not got, f"text row OK sent {got}")
            y0, y1 = image[page_off + 1], image[page_off + 3]
            rows = (y1 - y0 + 1 - SMALL_FONT_H) // pitch + 1
            log.append(f"{pad}{len(kids)} text rows, font {font:#x}, pitch {pitch}, {rows} visible, "
                       f"OK -> noop, no frames")
            widths = [measure(ru) for ru, *_ in items]
            log.append(f"{pad}widths px: {widths}")
            wide = [(t[1], w) for t, w in zip(kids, widths) if w > TEXT_MAX_W]
            expect(not wide, f"text rows wider than {TEXT_MAX_W} px: {wide}")
            return
        for (ru, en, h, flag), kid in zip(items, kids):
            off = (h - APP_BASE) & ~1
            if kid[0] == "page":
                expect((ru, en, flag) == (kid[1], kid[2], 0), f"page{i}: {ru}/{en}/{flag}")
                log.append(f"{pad}{ru} / {en}")
                walk(next(n for n, q in enumerate(pages) if q is kid), h, depth + 1, target)
            elif kid[0] == "link":
                expect((ru, en, flag) == (kid[1], kid[2], 0), f"link page{i}: {ru}/{en}/{flag}")
                expect(target is None, f"link {ru} inside a shared list")
                log.append(f"{pad}{ru} / {en}")
                emu.ram[p.target] = 0xA5
                walk(next(n for n, q in enumerate(pages) if q is kid[4]), h, depth + 1, kid[5])
                expect(emu.rd8(p.target) == kid[5], f"link {ru}: target {emu.rd8(p.target)}")
            elif kid[0] == "value":
                expect((ru, en, flag) == (*VALUES[kid[1]][:2], 2), f"value {kid[1]}: {ru}/{flag}")
                log.append(f"{pad}{ru} {test_value(kid[1], off)}")
            else:
                expect((ru, en, flag) == (kid[1], kid[2], 1), f"action {ru}/{flag}")
                reg = kid[3]
                if reg == REG_TARGET:
                    expect(target is not None, f"action {ru}: shared list opened without link")
                    expect(emu.rd8(p.target) == target, f"action {ru}: target {emu.rd8(p.target)}")
                    reg = target
                got = send_via(off, 0)
                expect(got == want(reg, kid[4], kid[5]), f"action {ru}: sent {got}")
                if kid[5] and not cmd_logged:
                    log.append(f"{pad}{ru}: {' '.join(got)}")
                    cmd_logged = kid[5] == DEV_FAK_CMD
                acts += 1
        if acts:
            log.append(f"{pad}{acts} actions: frames every {period} ms, packets ok")

    ru, en, handler, flag = main[-1]
    expect((ru, en, flag) == (TREE[1], TREE[2], 0), f"main[16] = {ru}/{en}/{flag}")
    log.append(f"main[16] {ru} / {en}")
    walk(0, handler, 1)

    dev_items = u32(image, lab["page0"] + 4) - APP_BASE
    info = struct.unpack_from("<5I", image, dev_items)
    expect(read_str(image, info[0]) == "INFO" and info[3] == APP_BASE + lab[f"screen{pages.index(TREE[4][0])}"] | 1,
           "INFO is not the first item of Девайсы")
    expect(info[2] == u32(stock, p.icon_info + 8), f"INFO icon {info[2]:#x}")
    log.append(f"  INFO: first in {TREE[1]}, icon {info[2]:#x} (stock '{ICON_NAMES['icon_info']}')")

    last = max(i for i, pg in enumerate(pages) if len(pg[4]) >= 2)
    cursor = p.cursors + 4 * last
    emu.wr32(cursor, 1)
    open_screen(APP_BASE + lab[f"screen{last}"], cursor, len(pages[last][4]))
    expect(emu.rd32(cursor) == 1, "valid cursor was reset")
    n_sent = len(st["sent"])
    tick(period * 3)
    expect(len(st["sent"]) == n_sent, "extra frames after session")
    acts = path_actions()
    expect(all(a[3] != REG_TARGET for a in acts), "unresolved REG_TARGET action")
    expect(sum(1 for a in acts if a[5] == DEV_POINT) == 10 + 5 * sum(len(g[2]) for g in PULSE_GROUPS),
           "point action count")
    n_cmd = sum(len(c) for _g, _e, c in FAK_HEALTH_CMDS + FAK_ENERGY_CMDS * 2 + MED_CMDS) + len(FAK_AMMO_CMDS)
    n_cp2 = sum(len(c) for _g, _e, c in CP2_CMDS * 2) + len(CP2_FAK_CMDS)
    expect(sum(1 for a in acts if a[5] == DEV_FAK_CMD) == n_cmd + n_cp2 and n_cmd == 28 + 8 + 50 * 2 + 29
           and n_cp2 == 23 * 2 + 3, "medkit command count")
    log.append(f"  actions: {len(acts)} ({n_cmd} medkit commands, {n_cp2} command post commands)")

    diff = [i for i in range(len(stock)) if image[i] != stock[i]]
    allowed = set(range(p.cave, meta["cave_end"]))
    allowed |= set(range(p.nav_limit, p.nav_limit + 2))
    allowed |= set(range(p.nav_lit, p.nav_lit + 4))
    allowed |= set(range(p.hook, p.hook + 4))
    allowed |= set(range(p.main_page + 4, p.main_page + 12))
    allowed |= set(range(STOCK_SIZE - 4, STOCK_SIZE))
    if hasattr(p, "ver_bl"):
        allowed |= set(range(p.ver_bl, p.ver_bl + 4))
        sp = emu.r[13]
        emu.wr32(sp + p.ver_text_sp, 0)
        emu.r[0] = p.ver_minor
        emu.call(lab["ver_minor"])
        ptr = emu.rd32(sp + p.ver_text_sp)
        text = read_str(image, ptr)
        expect(text == f"{p.ver_minor}-mod", f"version text {text!r}")
        log.append(f"  Информация: minor '{p.ver_minor}' -> '{text}'")
    extra = [i for i in diff if i not in allowed]
    expect(not extra, f"unexpected diffs at {[hex(i) for i in extra[:8]]}")
    log.append(f"  diff vs stock: {len(diff)} bytes, all in allowed regions")
    return log
