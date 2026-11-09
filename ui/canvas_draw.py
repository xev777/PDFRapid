# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Dibujo de cada tipo de objeto y vista previa mientras se dibuja. Parte de PageCanvas (ui/canvas.py)."""
import math
import base64
from PyQt6.QtCore import (Qt, QPointF, QRectF, QRect)
from PyQt6.QtGui import (QPixmap, QPainter, QPen, QBrush, QColor, QFont,
                         QFontMetrics, QPolygonF, QPainterPath)
from models.annotation import Ann, REVIEW_STATES
from core.i18n import T
from core.constants import (HS, T_ARROW, T_ARROW_SHAPE, T_CIRCLE, T_DARROW, T_HL, T_LINE, T_RECT, T_RRECT, T_TEXTBOX, T_TRI)
from core.logger import log
from ui.styles import C


class DrawMixin:
    def _pen(self, ann, op):
        c = QColor(ann.stroke)
        c.setAlpha(int(255 * op))
        styles = {"solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine, "dotted": Qt.PenStyle.DotLine}
        pen = QPen(c, ann.stroke_width, styles.get(ann.stroke_style, Qt.PenStyle.SolidLine))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _arrow_head(self, p, x1, y1, x2, y2, size, color, op):
        angle = math.atan2(y2-y1, x2-x1)
        a1 = angle + math.pi * 5/6
        a2 = angle - math.pi * 5/6
        pts = QPolygonF([QPointF(x2,y2), QPointF(x2+size*math.cos(a1), y2+size*math.sin(a1)),
                         QPointF(x2+size*math.cos(a2), y2+size*math.sin(a2))])
        c = QColor(color)
        c.setAlpha(int(255 * op))
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(pts)

    def _draw(self, p, a):
        try:
            op = max(0.05, min(1.0, a.opacity))
            def qc(hx, alpha=255):
                if not hx: return None
                c = QColor(hx)
                c.setAlpha(int(alpha * op))
                return c
            p.setPen(self._pen(a, op))
            fc = qc(a.fill)
            tc = qc(a.text_color)
            p.setBrush(QBrush(fc) if fc else Qt.BrushStyle.NoBrush)
            if a.rotation != 0:
                r = a.brect()
                cx, cy = r.center().x(), r.center().y()
                p.save()
                p.translate(cx, cy)
                p.rotate(a.rotation)
                p.translate(-cx, -cy)
            x1, y1, x2, y2 = a.x1, a.y1, a.x2, a.y2
            if a.kind == "image":
                if a.image_data:
                    try:
                        img_bytes = base64.b64decode(a.image_data)
                        pixmap = QPixmap()
                        pixmap.loadFromData(img_bytes)
                        p.drawPixmap(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)).toRect(), pixmap)
                    except Exception:
                        p.fillRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)), QColor(200,200,200))
            elif a.kind == "ink" and len(a.points) > 1:
                path = QPainterPath(QPointF(*a.points[0]))
                for x, y in a.points[1:]: path.lineTo(x, y)
                p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
            elif a.kind in ("underline", "strikeout"):
                xa, xb, ya, yb = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
                y = yb - 1 if a.kind == "underline" else (ya + yb) / 2
                p.setPen(QPen(qc(a.stroke), max(1.2, (yb - ya) * 0.08))); p.drawLine(QPointF(xa, y), QPointF(xb, y))
            elif a.kind == "redact":                      # zona marcada para tachado definitivo
                rr = QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                p.fillRect(rr, QBrush(QColor(198, 40, 40, 70), Qt.BrushStyle.BDiagPattern))
                p.fillRect(rr, QColor(198, 40, 40, 40))
                p.setPen(QPen(QColor("#c62828"), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(rr)
            elif a.kind == "highlight":
                # como un marcador: multiplicar deja el texto negro y nítido (igual que Acrobat)
                c2 = QColor(a.stroke)
                c2.setAlpha(min(255, int(255 * op) + 60))
                mode = p.compositionMode()
                if not self.night: p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                p.fillRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)), c2)
                p.setCompositionMode(mode)
            elif a.kind == "text":
                p.setFont(a.qfont())
                p.setPen(QPen(tc or QColor(0,0,0)))
                fm = QFontMetrics(a.qfont())
                for i, ln in enumerate(a.text.split('\n')):
                    p.drawText(QPointF(x1, y1+i*fm.height()), ln)
            elif a.kind == "textbox":
                br = QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1))
                if a.box_bg:
                    bg = QColor(a.box_bg)
                    bg.setAlpha(int(bg.alpha() * op))
                    p.fillRect(br, bg)
                if a.box_bw > 0:
                    bc = QColor(a.box_border)
                    bc.setAlpha(int(255 * op))
                    p.setPen(QPen(bc, a.box_bw))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(br)
                if a.text:
                    p.setFont(a.qfont())
                    tcc = QColor(a.text_color)
                    tcc.setAlpha(int(255 * op))
                    p.setPen(QPen(tcc))
                    af = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
                          "right": Qt.AlignmentFlag.AlignRight}.get(a.text_align, Qt.AlignmentFlag.AlignLeft)
                    p.drawText(br.adjusted(5,5,-5,-5), af | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, a.text)
            elif a.kind == "line":
                p.drawLine(QPointF(x1,y1), QPointF(x2,y2))
            elif a.kind in ("arrow", "darrow"):
                p.drawLine(QPointF(x1,y1), QPointF(x2,y2))
                if a.arrow_end: self._arrow_head(p, x1, y1, x2, y2, a.arrow_size, a.stroke, op)
                if a.arrow_start or a.kind == "darrow":
                    self._arrow_head(p, x2, y2, x1, y1, a.arrow_size, a.stroke, op)
                p.setPen(self._pen(a, op))
                p.setBrush(QBrush(fc) if fc else Qt.BrushStyle.NoBrush)
            elif a.kind == "rect":
                p.drawRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)))
            elif a.kind == "rrect":
                r2 = a.corner_r or 10
                p.drawRoundedRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)), r2, r2)
            elif a.kind == "circle":
                p.drawEllipse(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)))
            elif a.kind == "triangle":
                cx2 = (x1+x2)/2
                p.drawPolygon(QPolygonF([QPointF(cx2,y1), QPointF(x2,y2), QPointF(x1,y2)]))
            elif a.kind == "arrow_shape":
                dx, dy = x2-x1, y2-y1
                length = max(math.hypot(dx,dy), 1)
                angle = math.atan2(dy, dx)
                shaft_w = max(abs(y2-y1)*0.3, 6)
                head_w = shaft_w * 2.5
                head_len = min(length*0.35, shaft_w*3)
                pts = [QPointF(0,-shaft_w/2), QPointF(length-head_len,-shaft_w/2),
                       QPointF(length-head_len,-head_w/2), QPointF(length,0),
                       QPointF(length-head_len,head_w/2), QPointF(length-head_len,shaft_w/2),
                       QPointF(0,shaft_w/2)]
                p.save()
                p.translate(x1, y1)
                p.rotate(math.degrees(angle))
                fcc = QColor(a.fill or a.stroke)
                fcc.setAlpha(int(fcc.alpha() * op))
                scc = QColor(a.stroke)
                scc.setAlpha(int(255 * op))
                p.setBrush(QBrush(fcc))
                p.setPen(QPen(scc, a.stroke_width))
                p.drawPolygon(QPolygonF(pts))
                p.restore()
            elif a.kind == "comment":
                r2 = QRectF(min(x1,x2), min(y1,y2), 28, 28)
                p.setBrush(QBrush(QColor("#FFE066")))
                p.setPen(QPen(QColor("#C8A000"), 1.5))
                p.drawEllipse(r2)
                p.setFont(QFont("Segoe UI Emoji", 12))
                p.setPen(QPen(QColor("#333")))
                p.drawText(r2, Qt.AlignmentFlag.AlignCenter, "💬")
                if a.comment_visible or a.selected:
                    body = a.thread_text()
                    bw, bx, by = 220, r2.right()+8, r2.top()
                    bh = 34 + QFontMetrics(QFont("Segoe UI", 9)).boundingRect(
                        QRect(0, 0, bw - 12, 2000), Qt.TextFlag.TextWordWrap, body).height()
                    br = QRectF(bx, by, bw, bh)
                    p.fillRect(br.adjusted(3,3,3,3), QColor(0,0,0,60))
                    p.fillRect(br, QColor("#FFFCE8"))
                    p.setPen(QPen(QColor("#C8A000"), 1))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(br)
                    tri = QPolygonF([QPointF(bx,by+10), QPointF(r2.right(), r2.center().y()), QPointF(bx,by+20)])
                    p.setBrush(QBrush(QColor("#FFFCE8")))
                    p.setPen(QPen(QColor("#C8A000"), 1))
                    p.drawPolygon(tri)
                    p.setPen(QPen(QColor("#333333")))
                    p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    author_line = f"{a.author}  {a.date}" if a.author else a.date
                    if a.status: author_line += f"  · {T(REVIEW_STATES[a.status][0])}"
                    p.drawText(QRectF(bx+6, by+4, bw-12, 16), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine, author_line)
                    p.setFont(QFont("Segoe UI", 9))
                    p.drawText(QRectF(bx+6, by+22, bw-12, bh-28), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, body)
            if a.rotation != 0:
                p.restore()
            if a.selected:
                sc = QColor(0, 120, 212)
                p.setPen(QPen(sc, 1.5, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                br2 = a.brect().adjusted(-2,-2,2,2)
                p.save()                                  # el marco gira con el objeto
                if a.rotation:
                    c = br2.center(); p.translate(c); p.rotate(a.rotation); p.translate(-c)
                p.drawRect(br2)
                p.setPen(QPen(QColor(0, 120, 212, 150), 1.2))       # pista de giro: arcos fuera de las esquinas
                for k, c in enumerate((br2.topLeft(), br2.topRight(), br2.bottomRight(), br2.bottomLeft())):
                    p.drawArc(QRectF(c.x() - 11, c.y() - 11, 22, 22), ((90, 0, 270, 180)[k] + 15) * 16, 16 * 60)
                p.restore()
                for i, h in enumerate(a.handles()):
                    if i == 8:
                        p.setBrush(QBrush(QColor(0,200,80)))
                        p.setPen(QPen(sc, 1))
                        p.drawEllipse(QRectF(h.x()-HS/2, h.y()-HS/2, HS, HS))
                    else:
                        p.setBrush(QBrush(QColor(C['white'])))
                        p.setPen(QPen(sc, 1))
                        p.drawRect(QRectF(h.x()-HS/2, h.y()-HS/2, HS, HS))
        except Exception:
            log.exception(f"draw kind={a.kind}")

    def _prev_draw(self, pt):
        pm = QPixmap(self._base)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for a in self.anns: self._draw(p, a)
        styles = {"solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine, "dotted": Qt.PenStyle.DotLine}
        pen = QPen(self.p_stroke, self.p_width, styles.get(self.p_style, Qt.PenStyle.DashLine))
        p.setPen(pen)
        p.setBrush(QBrush(self.p_fill) if self.p_fill else Qt.BrushStyle.NoBrush)
        x1, y1, x2, y2 = self._drag0.x(), self._drag0.y(), pt.x(), pt.y()
        if self.tool == T_HL:
            c = QColor(self.p_stroke)
            c.setAlpha(80)
            p.fillRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)), c)
        elif self.tool in (T_TEXTBOX, T_RECT):
            p.drawRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)))
        elif self.tool == T_RRECT:
            p.drawRoundedRect(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)), 10, 10)
        elif self.tool == T_LINE:
            p.drawLine(QPointF(x1,y1), QPointF(x2,y2))
        elif self.tool in (T_ARROW, T_DARROW):
            p.drawLine(QPointF(x1,y1), QPointF(x2,y2))
        elif self.tool == T_CIRCLE:
            p.drawEllipse(QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)))
        elif self.tool == T_TRI:
            cx2 = (x1+x2)/2
            p.drawPolygon(QPolygonF([QPointF(cx2,y1), QPointF(x2,y2), QPointF(x1,y2)]))
        elif self.tool == T_ARROW_SHAPE:
            tmp = Ann(T_ARROW_SHAPE, x1=x1, y1=y1, x2=x2, y2=y2,
                      stroke=self.p_stroke.name(), stroke_width=self.p_width,
                      fill=self.p_fill.name() if self.p_fill else self.p_stroke.name())
            dx, dy = x2-x1, y2-y1
            length = max(math.hypot(dx,dy), 1)
            angle = math.atan2(dy, dx)
            shaft_w = max(abs(y2-y1)*0.3, 6)
            head_w = shaft_w * 2.5
            head_len = min(length*0.35, shaft_w*3)
            pts = [QPointF(0,-shaft_w/2), QPointF(length-head_len,-shaft_w/2),
                   QPointF(length-head_len,-head_w/2), QPointF(length,0),
                   QPointF(length-head_len,head_w/2), QPointF(length-head_len,shaft_w/2),
                   QPointF(0,shaft_w/2)]
            p.save()
            p.translate(x1, y1)
            p.rotate(math.degrees(angle))
            fcc = QColor(tmp.fill or tmp.stroke)
            fcc.setAlpha(int(fcc.alpha()*0.7))
            scc = QColor(tmp.stroke)
            scc.setAlpha(int(255*0.7))
            p.setBrush(QBrush(fcc))
            p.setPen(QPen(scc, tmp.stroke_width))
            p.drawPolygon(QPolygonF(pts))
            p.restore()
        p.end()
        self.setPixmap(pm)

    def _make_ann(self, p1, p2):
        return Ann(self.tool, x1=p1.x(), y1=p1.y(), x2=p2.x(), y2=p2.y(),
                   stroke=self.p_stroke.name(), fill=self.p_fill.name() if self.p_fill else None,
                   stroke_width=self.p_width, stroke_style=self.p_style, opacity=self.p_opacity,
                   font_name=self.p_fname, font_size=self.p_fsize, text_color=self.p_fcolor.name(),
                   arrow_end=True, arrow_size=12)
