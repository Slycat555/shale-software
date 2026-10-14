#!/usr/bin/env python3
"""Writes the Software Manager's icons from the strata of the Shale logo, the same way
shale-linux's tools/make-app-icons.py makes Software Update's and Shale Snapshots'.

Usage: make-icons.py [LOGO.svg]   (default: /usr/share/pixmaps/shale-logo.svg)
  usr/share/icons/hicolor/scalable/apps/shale-software.svg
      a solid shopping bag over faint strata
  usr/share/icons/hicolor/scalable/status/shale-logo-badge-symbolic.svg
      the logo in one colour (every other stripe), for the "System package" badge
"""
import os
import re
import sys

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPolygonF, QTransform

BG = "#2b3440"
SYMBOL = "#c3cfdc"  # the logo's lightest stripe
CX = CY = 64
R = 58
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read_logo(path):
    """The logo's stripes as (fill, QPainterPath)."""
    with open(path, encoding="utf-8") as f:
        svg = f.read()
    stripes = []
    for fill, d in re.findall(r'<path fill="(#[0-9a-f]+)" d="M([^"Z]+)Z"', svg):
        pts = [QPointF(*map(float, p.split(","))) for p in d.split()]
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        stripes.append((fill, path))
    return stripes


def svg_path(path, fill, extra=""):
    parts = []
    for poly in path.toSubpathPolygons():
        pts = " ".join(f"{p.x():.2f},{p.y():.2f}" for p in poly)
        if pts:
            parts.append(f"M{pts}Z")
    return f'<path fill="{fill}"{extra} d="{"".join(parts)}"/>' if parts else ""


def circle(cx, cy, r):
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), r, r)
    return path


def bag():
    # A shopping bag: a body that widens towards the bottom, and a thin, wide handle
    # (half a ring) above it.
    body = QPainterPath()
    body.addPolygon(QPolygonF([QPointF(*p) for p in [
        (36, 50), (92, 50), (99, 102), (93, 109), (35, 109), (29, 102), (36, 50)]]))
    body.closeSubpath()
    ring = circle(64, 50, 20).subtracted(circle(64, 50, 14))
    top = QPainterPath()
    top.addRect(QRectF(30, 20, 68, 30))
    return body.united(ring.intersected(top))


def shrink(path, factor=0.66):
    """The symbol at a size that leaves room around it, centred in the disc."""
    t = QTransform()
    t.translate(CX, CY)
    t.scale(factor, factor)
    t.translate(-CX, -CY)
    return t.map(path)


def software_icon(stripes):
    shape = shrink(bag())
    out = [f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="{BG}"/>']
    # Faint strata behind a solid bag in the logo's lightest colour (like Software Update).
    out += [svg_path(p, fill, ' fill-opacity="0.22"') for fill, p in stripes]
    out.append(svg_path(shape.intersected(circle(CX, CY, R)), SYMBOL))
    return out


def badge_icon(stripes):
    # A ring with every other stripe inside it.
    inner = circle(CX, CY, R - 14)
    out = [svg_path(circle(CX, CY, R).subtracted(circle(CX, CY, R - 8)), "#2e3436", ' fill-rule="evenodd"')]
    out += [svg_path(p.intersected(inner), "#2e3436") for _, p in stripes[1::2]]
    return out


def write(rel, parts):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">\n  '
                + "\n  ".join(p for p in parts if p) + "\n</svg>\n")


stripes = read_logo(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/pixmaps/shale-logo.svg")
write("usr/share/icons/hicolor/scalable/apps/shale-software.svg", software_icon(stripes))
write("usr/share/icons/hicolor/scalable/status/shale-logo-badge-symbolic.svg", badge_icon(stripes))
