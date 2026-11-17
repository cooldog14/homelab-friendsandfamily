#!/usr/bin/env python3
"""High-level homelab architecture diagram.

This public diagram intentionally contains no addresses, ports, hostnames,
domains, VM IDs, hardware models, service inventories or known gaps.

Style adapted from Goblinmine/homelab-diagram (MIT, see LICENSE).
Output: out/homelab.svg + out/homelab.png.
"""
import html
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "out"

W, H = 2000, 1140

BG = "#0b0f15"
GRID = "#151c26"
PANEL = "#111821"
CHIP = "#19222e"
BORDER = "#253042"
TEXT = "#e6edf3"
MUTED = "#8d9aab"
FAINT = "#5d6a7c"
SANS = "Fira Sans"
MONO = "Fira Code"

PUB = "#f85149"
WG = "#39c5cf"
TAIL = "#bc8cff"
LAN = "#58a6ff"

class SVG:
    def __init__(self):
        self.p = []

    def rect(self, x, y, w, h, rx=12, fill=PANEL, stroke=BORDER, sw=1.2):
        self.p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                      f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=14, fill=TEXT, weight=400, anchor="start", mono=False, ls=0):
        fam = MONO if mono else SANS
        lsa = f' letter-spacing="{ls}"' if ls else ""
        self.p.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-size="{size}" fill="{fill}" '
                      f'font-weight="{weight}" text-anchor="{anchor}"{lsa}>{html.escape(s)}</text>')

    def line(self, pts, color, sw=3, dash=None, r=12):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.p.append(f'<path d="{rounded(pts, r)}" fill="none" stroke="{color}" stroke-width="{sw}" '
                      f'stroke-linecap="round" stroke-linejoin="round"{d}/>')

    def arrow(self, pts, color, sw=2.6, dash=None, r=12):
        self.line(pts, color, sw, dash, r)
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        ln = max(abs(dx), abs(dy)) or 1
        ux, uy = dx / ln, dy / ln
        a, b = 9, 5
        p1 = (x1 - ux * a - uy * b, y1 - uy * a + ux * b)
        p2 = (x1 - ux * a + uy * b, y1 - uy * a - ux * b)
        self.p.append(f'<path d="M{x1},{y1} L{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f} Z" fill="{color}"/>')

    def label(self, x, y, s, color=MUTED, size=11, anchor="middle"):
        w = len(s) * size * 0.6 + 12
        bx = x - w / 2 if anchor == "middle" else (x if anchor == "start" else x - w)
        self.rect(bx, y - size - 3, w, size + 10, rx=5, fill=BG, stroke=BG, sw=0)
        self.text(bx + w / 2, y, s, size, color, 500, "middle", mono=True)


S = SVG()


def add(s):
    S.p.append(s)


def rounded(pts, r=12):
    if len(pts) == 2:
        return f"M{pts[0][0]},{pts[0][1]} L{pts[1][0]},{pts[1][1]}"
    d = f"M{pts[0][0]},{pts[0][1]}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1 = max(abs(x1 - x0), abs(y1 - y0))
        l2 = max(abs(x2 - x1), abs(y2 - y1))
        rr = min(r, l1 / 2, l2 / 2)
        ax = x1 - (x1 - x0) / l1 * rr if l1 else x1
        ay = y1 - (y1 - y0) / l1 * rr if l1 else y1
        bx = x1 + (x2 - x1) / l2 * rr if l2 else x1
        by = y1 + (y2 - y1) / l2 * rr if l2 else y1
        d += f" L{ax:.1f},{ay:.1f} Q{x1},{y1} {bx:.1f},{by:.1f}"
    d += f" L{pts[-1][0]},{pts[-1][1]}"
    return d


def folder(x, y, w, h, tab_w, color):
    """Card with a folder tab. The tab text is drawn separately."""
    t = y - 34
    r, rt, sl = 14, 9, 16
    d = (f"M{x},{y+h-r} L{x},{t+rt} Q{x},{t} {x+rt},{t} L{x+tab_w-sl:.1f},{t} "
         f"C{x+tab_w-sl/3:.1f},{t} {x+tab_w-sl/3:.1f},{y} {x+tab_w+sl/2:.1f},{y} "
         f"L{x+w-r},{y} Q{x+w},{y} {x+w},{y+r} L{x+w},{y+h-r} Q{x+w},{y+h} {x+w-r},{y+h} "
         f"L{x+r},{y+h} Q{x},{y+h} {x},{y+h-r} Z")
    add(f'<path d="{d}" fill="#0f151e" stroke="{color}aa" stroke-width="1.8"/>')
    add(f'<rect x="{x+1}" y="{y+16}" width="4" height="{h-32}" rx="2" fill="{color}"/>')


def tab(x, y, name, kind, color=TEXT):
    add(f'<text x="{x+16}" y="{y-10}" font-family="{SANS}" fill="{TEXT}">'
        f'<tspan font-size="20" font-weight="700" fill="{color}">{html.escape(name)}</tspan>'
        f'<tspan dx="7" font-size="20" font-weight="700" fill-opacity="0.6">·</tspan>'
        f'<tspan dx="7" font-size="14" font-weight="600">{html.escape(kind)}</tspan></text>')


def dot(x, y, color):
    add(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')


def cloud(cx, cy):
    blobs = [(-80, 14, 32), (-38, -6, 43), (20, -14, 47), (70, 4, 36), (100, 20, 23), (-100, 24, 21)]
    for dx, dy, r in blobs:
        add(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="{r+2}" fill="#3a4a60"/>')
    add(f'<rect x="{cx-112}" y="{cy+8}" width="224" height="36" rx="18" fill="#3a4a60"/>')
    for dx, dy, r in blobs:
        add(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="{r}" fill="#1a2433"/>')
    add(f'<rect x="{cx-110}" y="{cy+10}" width="220" height="32" rx="16" fill="#1a2433"/>')
    S.text(cx, cy + 2, "Internet", 24, TEXT, 600, "middle")
    S.text(cx, cy + 25, "public traffic enters through the edge", 12, MUTED, 400, "middle")


# ---------------------------------------------------------------- background + header
add(f'<defs><pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
    f'<circle cx="1.5" cy="1.5" r="1.3" fill="{GRID}"/></pattern></defs>')
BG_IDX = len(S.p)
add("")
add("")

S.text(40, 86, "Friends & Family Homelab", 40, TEXT, 700, ls=-0.5)
S.text(40, 112, "high-level architecture", 14, MUTED, 400)
S.text(W - 40, 86, "2026", 16, MUTED, 400, "end")

# connections first; cards cover the ends
S.arrow([(1000, 210), (1000, 248), (500, 248), (500, 300)], PUB, 3)
S.label(750, 242, "HTTPS", PUB, 11)
S.label(960, 442, "WireGuard", WG, 11)
S.arrow([(840, 780), (1080, 780)], TAIL, 2.4, dash="2 5")
S.label(960, 772, "Tailscale admin", TAIL, 11)

cloud(1000, 150)

# ---------------------------------------------------------------- public edge
fx, fy, fw, fh = 160, 300, 680, 300
folder(fx, fy, fw, fh, 250, PUB)
tab(fx, fy, "Public edge", "VPS")
S.text(fx + 24, fy + 42, "Only public ingress", 20, TEXT, 600)
S.text(fx + 24, fy + 64, "TLS terminates here; application backends stay private", 12, MUTED, 400)
for i, (label, color) in enumerate([("Caddy TLS termination", PUB), ("nftables + CrowdSec", PUB),
                                    ("WireGuard endpoint", WG)]):
    y = fy + 104 + i * 46
    dot(fx + 30, y - 4, color)
    S.text(fx + 48, y, label, 14.5, TEXT, 500)
S.text(fx + 24, fy + fh - 20, "public names and explicit forwards only", 11, FAINT, 400)

# ---------------------------------------------------------------- home
hx, hy, hw, hh = 1080, 280, 840, 650
folder(hx, hy, hw, hh, 300, LAN)
tab(hx, hy, "Home", "Proxmox host")
S.text(hx + 24, hy + 40, "Private network", 20, TEXT, 600)
S.text(hx + 24, hy + 62, "VMs, service stacks, shared storage and backups", 12, MUTED, 400)

# application VM
ax, ay, aw, ah = hx + 30, hy + 80, hw - 60, 220
S.rect(ax, ay, aw, ah, rx=12, fill=PANEL, stroke=BORDER, sw=1.3)
add(f'<rect x="{ax+1}" y="{ay+12}" width="4" height="{ah-24}" rx="2" fill="{LAN}"/>')
S.text(ax + 20, ay + 30, "Application VM", 16, TEXT, 600)
S.text(ax + 20, ay + 49, "Docker Compose · 8 stacks", 11.5, MUTED, 400)

chips = ["Photos", "Documents", "Media", "Comms", "Games", "Monitoring"]
cw, ch, gap = 240, 52, 12
for i, name in enumerate(chips):
    col, row = i % 3, i // 3
    x = ax + 16 + col * (cw + gap)
    y = ay + 70 + row * (ch + 10)
    S.rect(x, y, cw, ch, rx=9, fill=CHIP, stroke=BORDER, sw=1)
    dot(x + 16, y + ch / 2, LAN)
    S.text(x + 30, y + ch / 2 + 5, name, 14, TEXT, 500)

S.text(ax + aw - 16, ay + ah - 12, "iGPU passthrough for media", 11, MUTED, 500, "end", mono=True)

# the backend tunnel terminates at the application VM, not at the hypervisor
S.arrow([(840, 450), (1108, 450)], WG, 2.6, dash="6 5")

# other VMs
oy = ay + ah + 20
S.rect(ax, oy, aw, 88, rx=12, fill=PANEL, stroke=BORDER, sw=1.3)
add(f'<rect x="{ax+1}" y="{oy+12}" width="4" height="{64}" rx="2" fill="{FAINT}"/>')
S.text(ax + 20, oy + 28, "Other VMs", 15, TEXT, 600)
S.text(ax + 20, oy + 50, "additional internal workloads", 12.5, MUTED, 400)

# storage + backups
sy = oy + 108
sw = (aw - 20) / 2
for i, (title, lines, accent) in enumerate([
    ("Shared storage", ["media · documents", "mounted by VMs"], LAN),
    ("Backups", ["encrypted local repository", "offsite copy"], WG),
]):
    x = ax + i * (sw + 20)
    S.rect(x, sy, sw, 120, rx=12, fill=PANEL, stroke=BORDER, sw=1.3)
    add(f'<rect x="{x+1}" y="{sy+12}" width="4" height="96" rx="2" fill="{accent}"/>')
    S.text(x + 18, sy + 28, title, 15, TEXT, 600)
    for j, line in enumerate(lines):
        S.text(x + 18, sy + 52 + j * 20, line, 11.5, MUTED, 400)

S.text(hx + 24, hy + hh - 14, "addresses, ports and inventories omitted", 10.5, FAINT, 400, mono=True)

# ---------------------------------------------------------------- admin + legend
ax2, ay2, aw2, ah2 = 160, 680, 680, 200
S.rect(ax2, ay2, aw2, ah2, rx=12, fill=PANEL, stroke=TAIL + "aa", sw=1.6)
add(f'<rect x="{ax2+1}" y="{ay2+14}" width="4" height="{ah2-28}" rx="2" fill="{TAIL}"/>')
S.text(ax2 + 20, ay2 + 34, "Admin overlay", 19, TEXT, 600)
S.text(ax2 + 20, ay2 + 56, "separate from public ingress", 12, MUTED, 400)
for i, label in enumerate(["Tailscale tailnet", "private HTTPS names", "admin devices"]):
    y = ay2 + 92 + i * 30
    dot(ax2 + 28, y - 4, TAIL)
    S.text(ax2 + 44, y, label, 13.5, TEXT, 500)

lx, ly, lw, lh = 160, 950, 1760, 100
S.rect(lx, ly, lw, lh, rx=12, fill=PANEL, stroke=BORDER, sw=1.3)
S.text(lx + 20, ly + 30, "Legend", 16, TEXT, 600)
items = [
    ("line", PUB, 3, None, "public HTTPS"),
    ("line", WG, 2.6, "6 5", "WireGuard to the application VM"),
    ("line", TAIL, 2.4, "2 5", "Tailscale admin"),
    ("chip", LAN, 0, None, "service category"),
]
for i, (kind, color, sw, dash, text) in enumerate(items):
    x = lx + 24 + i * 420
    if kind == "line":
        S.line([(x, ly + 64), (x + 58, ly + 64)], color, sw, dash)
        S.text(x + 74, ly + 68, text, 12.5, MUTED, 400)
    else:
        S.rect(x, ly + 54, 34, 18, rx=5, fill=CHIP, stroke=BORDER, sw=1)
        dot(x + 11, ly + 63, color)
        S.text(x + 50, ly + 68, text, 12.5, MUTED, 400)

S.text(160, 1100, "High-level architecture only — addresses, ports, hostnames, service inventories and known gaps are intentionally omitted.",
       11, FAINT, 400)

# ---------------------------------------------------------------- finish
H = 1140
S.rect(0, 0, W, H, rx=0, fill=BG, stroke=BG, sw=0)
S.rect(0, 0, W, H, rx=0, fill="url(#dots)", stroke="none", sw=0)
dots = S.p.pop()
S.p[BG_IDX], S.p[BG_IDX + 1] = S.p.pop(), dots

OUT.mkdir(exist_ok=True)
svg_path = OUT / "homelab.svg"
svg_path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                    + "".join(S.p) + "</svg>")
png_path = OUT / "homelab.png"
if shutil.which("rsvg-convert"):
    subprocess.run(["rsvg-convert", "-z", "1.6", "-o", str(png_path), str(svg_path)], check=True)
else:
    subprocess.run(["magick", str(svg_path), "-resize", "160%", str(png_path)], check=True)
if "--optimize" in sys.argv and shutil.which("magick"):
    tmp = png_path.with_suffix(".opt.png")
    subprocess.run(["magick", str(png_path), "-strip", "-depth", "8", "-colors", "256", str(tmp)], check=True)
    tmp.replace(png_path)
print(svg_path, png_path)
