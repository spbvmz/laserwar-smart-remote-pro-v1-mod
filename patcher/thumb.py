"""Image signature, Thumb encoders and a small Thumb-1 interpreter for checking the added code."""
from __future__ import annotations

import struct

FLASH = 0x08000000
STOCK_SIZE = 0x16800
TRAILER_LEN = 8  # version u32 + CRC u32
MAGIC = 0xC0DE5EED  # session state is armed
FRAME_MS = 50  # airtime of one 24-bit Miles frame (upper bound)


def stm32_crc_le(data: bytes, init: int = 0xFFFFFFFF) -> int:
    """STM32 CRC unit: poly 0x04C11DB7, init 0xFFFFFFFF, little-endian 32-bit words, no final xor."""
    crc = init
    if len(data) % 4:
        data = data + b"\x00" * (4 - len(data) % 4)
    for i in range(0, len(data), 4):
        crc ^= struct.unpack_from("<I", data, i)[0]
        for _ in range(32):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def sign_image(image: bytearray) -> bytes:
    """Rewrite the last 4 bytes with the CRC of everything before them."""
    if len(image) != STOCK_SIZE:
        raise ValueError("bad size")
    sig = stm32_crc_le(bytes(image[:-4]))
    image[-4:] = struct.pack("<I", sig)
    return struct.pack("<I", sig)


def encode_bl(from_off: int, to_off: int) -> bytes:
    """Thumb BL from_off -> to_off (file offsets)."""
    pc = FLASH + from_off + 4
    target = FLASH + (to_off & ~1)
    delta = target - pc
    if delta < -(1 << 24) or delta >= (1 << 24):
        raise ValueError(f"BL out of range: {from_off:#x} -> {to_off:#x} delta={delta}")
    if delta < 0:
        imm = delta & ((1 << 25) - 1)
        s = 1
    else:
        imm = delta
        s = 0
    imm10 = (imm >> 12) & 0x3FF
    imm11 = (imm >> 1) & 0x7FF
    i1 = (imm >> 23) & 1
    i2 = (imm >> 22) & 1
    j1 = 0 if (i1 ^ s) else 1
    j2 = 0 if (i2 ^ s) else 1
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0xD000 | (j1 << 13) | (0x1000) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def decode_bl(data: bytes, from_off: int) -> int:
    hw1, hw2 = struct.unpack_from("<HH", data, from_off)
    if (hw1 & 0xF800) != 0xF000 or (hw2 & 0xE000) != 0xE000 or (hw2 & 0x1000) == 0:
        raise ValueError("not a BL")
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1 = 1 - (j1 ^ s)
    i2 = 1 - (j2 ^ s)
    imm32 = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        imm32 |= ~((1 << 25) - 1)
        imm32 &= 0xFFFFFFFF
        if imm32 & 0x80000000:
            imm32 -= 0x100000000
    return (FLASH + from_off + 4 + imm32) - FLASH


def encode_bcond(from_off: int, to_off: int, cond: int) -> bytes:
    """Thumb B<cond> T1: cond in 0..13 (EQ=0, NE=1)."""
    delta = to_off - (from_off + 4)
    if delta % 2:
        raise ValueError("Bcond misaligned")
    imm8 = delta // 2
    if not (-128 <= imm8 <= 127):
        raise ValueError(f"Bcond out of range: {imm8}")
    return struct.pack("<H", 0xD000 | ((cond & 0xF) << 8) | (imm8 & 0xFF))


def encode_b(from_off: int, to_off: int) -> bytes:
    """Thumb B T2 unconditional: imm11 halfwords from PC+4."""
    delta = to_off - (from_off + 4)
    if delta % 2:
        raise ValueError("B misaligned")
    imm11 = delta // 2
    if not (-1024 <= imm11 <= 1023):
        raise ValueError(f"B out of range: {imm11}")
    return struct.pack("<H", 0xE000 | (imm11 & 0x7FF))


def encode_ldr_lit(rt: int, from_off: int, lit_off: int) -> bytes:
    """LDR Rt, [PC, #imm] T1; lit_off must be 4-aligned."""
    base = (FLASH + from_off + 4) & ~3
    tgt = FLASH + lit_off
    if tgt < base or (tgt - base) % 4:
        raise ValueError(f"LDR lit bad {from_off:#x}->{lit_off:#x}")
    imm8 = (tgt - base) // 4
    if imm8 > 0xFF:
        raise ValueError(f"LDR lit imm too large: {imm8}")
    return struct.pack("<H", 0x4800 | ((rt & 7) << 8) | imm8)


class ThumbEmu:
    """Minimal Thumb-1 interpreter for the added code; firmware calls are replaced by stubs."""

    def __init__(self, image: bytes, stubs: dict[int, object], cave_off: int):
        self.img = image
        self.stubs = stubs
        self.cave_off = cave_off
        self.r = [0] * 16
        self.ram: dict[int, int] = {}
        self.n = self.z = self.c = self.v = False
        self.trace: list[str] = []

    def rd32(self, a: int) -> int:
        if FLASH <= a < FLASH + len(self.img):
            return struct.unpack_from("<I", self.img, a - FLASH)[0]
        return sum(self.ram.get(a + i, 0) << (8 * i) for i in range(4))

    def rd8(self, a: int) -> int:
        if FLASH <= a < FLASH + len(self.img):
            return self.img[a - FLASH]
        return self.ram.get(a, 0)

    def wr32(self, a: int, v: int) -> None:
        self.wrn(a, v, 4)

    def wrn(self, a: int, v: int, n: int) -> None:
        if FLASH <= a < FLASH + len(self.img):
            raise RuntimeError(f"write to flash {a:#x}")
        for i in range(n):
            self.ram[a + i] = (v >> (8 * i)) & 0xFF

    def rd16(self, a: int) -> int:
        return self.rd8(a) | (self.rd8(a + 1) << 8)

    def flags_sub(self, a: int, b: int) -> int:
        res = (a - b) & 0xFFFFFFFF
        self.n = bool(res >> 31)
        self.z = res == 0
        self.c = a >= b
        self.v = bool(((a ^ b) & (a ^ res)) >> 31)
        return res

    def flags_add(self, a: int, b: int) -> int:
        full = a + b
        res = full & 0xFFFFFFFF
        self.n = bool(res >> 31)
        self.z = res == 0
        self.c = full > 0xFFFFFFFF
        self.v = bool((~(a ^ b) & (a ^ res)) >> 31)
        return res

    def cond(self, c: int) -> bool:
        return [
            self.z, not self.z, self.c, not self.c, self.n, not self.n,
            self.v, not self.v, self.c and not self.z, (not self.c) or self.z,
            self.n == self.v, self.n != self.v,
            (not self.z) and self.n == self.v, self.z or self.n != self.v,
        ][c]

    def call(self, entry_off: int, max_steps: int = 500) -> None:
        RET = 0xFFFFFFF0
        r = self.r
        r[14] = RET | 1
        pc = FLASH + entry_off
        sp0 = r[13]
        for _ in range(max_steps):
            if pc == RET:
                if r[13] != sp0:
                    raise RuntimeError(f"stack unbalanced {r[13]:#x} != {sp0:#x}")
                return
            h = struct.unpack_from("<H", self.img, pc - FLASH)[0]
            nxt = pc + 2
            if (h & 0xF800) == 0xF000:
                tgt = FLASH + decode_bl(self.img, pc - FLASH)
                self.trace.append(f"{pc:#x}: bl {tgt:#x}")
                stub = self.stubs.get(tgt - FLASH)
                if stub is None and tgt - FLASH >= self.cave_off:
                    r[14] = (pc + 4) | 1
                    pc = tgt
                    continue
                if stub is None:
                    raise RuntimeError(f"BL to unstubbed {tgt:#x}")
                stub(self)
                for i in (1, 2, 3, 12):
                    r[i] = 0xDEAD0000 | i
                pc += 4
                continue
            if (h & 0xFE00) == 0xB400:  # push
                regs = [i for i in range(8) if h & (1 << i)] + ([14] if h & 0x100 else [])
                r[13] -= 4 * len(regs)
                for k, i in enumerate(regs):
                    self.wr32(r[13] + 4 * k, r[i])
            elif (h & 0xFE00) == 0xBC00:  # pop
                regs = [i for i in range(8) if h & (1 << i)]
                for k, i in enumerate(regs):
                    r[i] = self.rd32(r[13] + 4 * k)
                r[13] += 4 * len(regs)
                if h & 0x100:
                    nxt = self.rd32(r[13]) & ~1
                    r[13] += 4
            elif (h & 0xFF80) == 0xB000:
                r[13] += (h & 0x7F) * 4
            elif (h & 0xFF80) == 0xB080:
                r[13] -= (h & 0x7F) * 4
            elif (h & 0xF800) == 0x4800:
                r[(h >> 8) & 7] = self.rd32(((pc + 4) & ~3) + (h & 0xFF) * 4)
            elif (h & 0xF800) == 0xA000:
                r[(h >> 8) & 7] = ((pc + 4) & ~3) + (h & 0xFF) * 4
            elif (h & 0xF800) == 0x9000:
                self.wr32(r[13] + (h & 0xFF) * 4, r[(h >> 8) & 7])
            elif (h & 0xF800) == 0x9800:
                r[(h >> 8) & 7] = self.rd32(r[13] + (h & 0xFF) * 4)
            elif (h & 0xF000) == 0x5000:  # ldr/str [rn, rm]
                op, a, d = (h >> 9) & 7, r[(h >> 3) & 7] + r[(h >> 6) & 7], h & 7
                if op < 3:
                    self.wrn(a, r[d], (4, 2, 1)[op])
                elif op == 4:
                    r[d] = self.rd32(a)
                elif op == 5:
                    r[d] = self.rd16(a)
                elif op == 6:
                    r[d] = self.rd8(a)
                else:
                    v = self.rd8(a) if op == 3 else self.rd16(a)
                    bits = 8 if op == 3 else 16
                    r[d] = (v - (1 << bits) if v >> (bits - 1) else v) & 0xFFFFFFFF
            elif (h & 0xF800) == 0x6000:
                self.wr32(r[(h >> 3) & 7] + ((h >> 6) & 31) * 4, r[h & 7])
            elif (h & 0xF800) == 0x6800:
                r[h & 7] = self.rd32(r[(h >> 3) & 7] + ((h >> 6) & 31) * 4)
            elif (h & 0xF800) == 0x0800:
                sh = (h >> 6) & 31 or 32
                res = r[(h >> 3) & 7] >> sh
                r[h & 7] = res
                self.n, self.z = False, res == 0
            elif (h & 0xF800) == 0x7000:
                self.wrn(r[(h >> 3) & 7] + ((h >> 6) & 31), r[h & 7], 1)
            elif (h & 0xF800) == 0x7800:
                r[h & 7] = self.rd8(r[(h >> 3) & 7] + ((h >> 6) & 31))
            elif (h & 0xF800) == 0x8000:
                self.wrn(r[(h >> 3) & 7] + ((h >> 6) & 31) * 2, r[h & 7], 2)
            elif (h & 0xF800) == 0x8800:
                r[h & 7] = self.rd16(r[(h >> 3) & 7] + ((h >> 6) & 31) * 2)
            elif (h & 0xFFC0) == 0x4300:
                d = h & 7
                r[d] |= r[(h >> 3) & 7]
                self.n, self.z = bool(r[d] >> 31), r[d] == 0
            elif (h & 0xFFC0) == 0x4040:
                d = h & 7
                r[d] ^= r[(h >> 3) & 7]
                self.n, self.z = bool(r[d] >> 31), r[d] == 0
            elif (h & 0xFF87) == 0x4700:
                nxt = r[(h >> 3) & 15] & ~1
            elif (h & 0xFFC0) == 0x4340:
                d = h & 7
                r[d] = (r[d] * r[(h >> 3) & 7]) & 0xFFFFFFFF
                self.n, self.z = bool(r[d] >> 31), r[d] == 0
            elif (h & 0xF800) == 0x3800:
                d = (h >> 8) & 7
                r[d] = self.flags_sub(r[d], h & 0xFF)
            elif (h & 0xF800) == 0x2000:
                d = (h >> 8) & 7
                r[d] = h & 0xFF
                self.n, self.z = False, r[d] == 0
            elif (h & 0xF800) == 0x2800:
                self.flags_sub(r[(h >> 8) & 7], h & 0xFF)
            elif (h & 0xF800) == 0x3000:
                d = (h >> 8) & 7
                r[d] = self.flags_add(r[d], h & 0xFF)
            elif (h & 0xFFC0) == 0x4280:
                self.flags_sub(r[h & 7], r[(h >> 3) & 7])
            elif (h & 0xFE00) == 0x1A00:
                r[h & 7] = self.flags_sub(r[(h >> 3) & 7], r[(h >> 6) & 7])
            elif (h & 0xFE00) == 0x1800:
                r[h & 7] = self.flags_add(r[(h >> 3) & 7], r[(h >> 6) & 7])
            elif (h & 0xFE00) == 0x1C00:
                r[h & 7] = self.flags_add(r[(h >> 3) & 7], (h >> 6) & 7)
            elif (h & 0xF800) == 0x0000 and h != 0:
                sh = (h >> 6) & 31
                res = (r[(h >> 3) & 7] << sh) & 0xFFFFFFFF
                r[h & 7] = res
                self.n, self.z = bool(res >> 31), res == 0
            elif (h & 0xF000) == 0xD000 and (h & 0x0F00) < 0x0E00:
                if self.cond((h >> 8) & 0xF):
                    off = h & 0xFF
                    if off & 0x80:
                        off -= 0x100
                    nxt = pc + 4 + off * 2
            elif (h & 0xF800) == 0xE000:
                off = h & 0x7FF
                if off & 0x400:
                    off -= 0x800
                nxt = pc + 4 + off * 2
            elif h == 0xBF00:
                pass
            else:
                raise RuntimeError(f"unsupported insn {h:04x} @ {pc:#x}")
            pc = nxt
        raise RuntimeError("emulator step limit")
