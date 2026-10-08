import os
from pathlib import Path
from typing import Optional, Dict, Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from app.config import settings

UNICODE_FONT_NAME = "UnicodeFont"
UNICODE_FONT_AVAILABLE = False


def setup_unicode_font() -> bool:
    """
    Discovers and registers a TrueType font supporting Unicode
    (including Devanagari, CJK, Arabic, etc.) with ReportLab.
    Prioritizes the bundled NotoSansDevanagari font in the repository,
    followed by system fonts.
    
    Technical Note on Complex Script Shaping:
    ReportLab renders TrueType glyphs linearly based on unicode code points
    without an integrated OpenType GSUB/GPOS shaping engine (such as HarfBuzz).
    While individual glyphs are rendered portably across platforms, complex conjunct
    ligatures (e.g. Sanskrit/Hindi conjuncts) appear as sequential glyphs.
    """
    global UNICODE_FONT_AVAILABLE
    if UNICODE_FONT_AVAILABLE:
        return True

    # 1. Bundled repo font (portable across Linux, Docker, Windows)
    bundled_font = settings.BASE_DIR / "app" / "fonts" / "NotoSansDevanagari-Regular.ttf"
    
    candidate_paths = [
        str(bundled_font),
        "C:/Windows/Fonts/ARIALUNI.ttf",  # Arial Unicode MS (Windows)
        "C:/Windows/Fonts/Nirmala.ttf",   # Nirmala UI Indic (Windows)
        "C:/Windows/Fonts/arial.ttf",     # Windows Arial
        "C:/Windows/Fonts/segoeui.ttf",   # Windows Segoe UI
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont(UNICODE_FONT_NAME, p))
                UNICODE_FONT_AVAILABLE = True
                return True
            except Exception:
                continue

    return False


setup_unicode_font()


def contains_non_ascii(text: str) -> bool:
    """Checks if text contains non-ASCII characters that require a TrueType font."""
    return any(ord(c) > 127 for c in text)


class CertificateGenerator:
    """
    Generates vector PDF certificates based on predefined templates
    (Classic and Modern) with QR code verification and full Unicode TrueType support.
    """

    def __init__(self):
        self.page_width, self.page_height = landscape(A4)

    def _draw_qr_code(self, c: canvas.Canvas, x: float, y: float, size: float, verify_url: str):
        """Draws a vector QR Code linking to verification URL on the canvas."""
        try:
            qr = QrCodeWidget(verify_url)
            bounds = qr.getBounds()
            w = bounds[2] - bounds[0]
            h = bounds[3] - bounds[1]
            if w > 0 and h > 0:
                d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
                d.add(qr)
                renderPDF.draw(d, c, x, y)
        except Exception:
            c.setStrokeColor(colors.HexColor("#94A3B8"))
            c.rect(x, y, size, size)
            c.setFont("Helvetica", 6)
            c.drawCentredString(x + size / 2, y + size / 2, "QR CODE")

    def generate(
        self,
        output_path: Path,
        recipient_name: str,
        event_name: str,
        issuer_name: str,
        issue_date: str,
        certificate_id: str,
        description: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        template_type: str = "classic",
        verify_base_url: Optional[str] = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(output_path), pagesize=landscape(A4))
        w, h = self.page_width, self.page_height

        base_url = verify_base_url or settings.APP_BASE_URL
        verify_url = f"{base_url}/api/v1/certificates/verify/{certificate_id}"

        use_unicode = (
            UNICODE_FONT_AVAILABLE and (
                contains_non_ascii(recipient_name) or
                contains_non_ascii(event_name) or
                (description and contains_non_ascii(description)) or
                contains_non_ascii(issuer_name)
            )
        )

        name_font = UNICODE_FONT_NAME if use_unicode else ("Times-BoldItalic" if template_type == "classic" else "Helvetica-Bold")
        text_font = UNICODE_FONT_NAME if use_unicode else "Helvetica"
        bold_font = UNICODE_FONT_NAME if use_unicode else "Helvetica-Bold"

        if template_type == "modern":
            self._render_modern(c, w, h, recipient_name, event_name, issuer_name, issue_date,
                                certificate_id, description, extra_data, verify_url, name_font, text_font, bold_font)
        else:
            self._render_classic(c, w, h, recipient_name, event_name, issuer_name, issue_date,
                                 certificate_id, description, extra_data, verify_url, name_font, text_font, bold_font)

        c.showPage()
        c.save()
        return output_path

    def _render_classic(self, c, w, h, recipient_name, event_name, issuer_name, issue_date,
                        certificate_id, description, extra_data, verify_url, name_font, text_font, bold_font):
        primary_color = colors.HexColor("#0F172A")    # Deep Navy
        gold_color = colors.HexColor("#D97706")       # Warm Gold
        gold_dark = colors.HexColor("#B45309")        # Dark Gold
        slate_color = colors.HexColor("#475569")      # Slate text
        light_bg = colors.HexColor("#FAFAF9")         # Soft warm background
        seal_bg = colors.HexColor("#FEF3C7")          # Soft gold badge

        # Background
        c.setFillColor(light_bg)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # Borders
        c.setStrokeColor(primary_color)
        c.setLineWidth(5)
        c.rect(20, 20, w - 40, h - 40)

        c.setStrokeColor(gold_color)
        c.setLineWidth(1.5)
        c.rect(28, 28, w - 56, h - 56)

        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.5)
        c.rect(34, 34, w - 68, h - 68)

        # Corner Accents
        c.setFillColor(gold_color)
        for cx, cy in [(38, 38), (w - 38, 38), (38, h - 38), (w - 38, h - 38)]:
            c.circle(cx, cy, 3, fill=1, stroke=0)

        # Header: Issuer
        c.setFont(bold_font, 12)
        c.setFillColor(gold_dark)
        org_title = (issuer_name or "GLOBAL CERTIFICATION AUTHORITY").upper()
        c.drawCentredString(w / 2, h - 75, org_title)

        # Title
        c.setFont(bold_font, 30)
        c.setFillColor(primary_color)
        c.drawCentredString(w / 2, h - 118, "CERTIFICATE OF ACHIEVEMENT")

        # Divider
        c.setStrokeColor(gold_color)
        c.setLineWidth(2)
        c.line(w / 2 - 130, h - 130, w / 2 + 130, h - 130)
        c.circle(w / 2, h - 130, 3.5, fill=1, stroke=0)

        # Presentation Line
        c.setFont(text_font, 11)
        c.setFillColor(slate_color)
        c.drawCentredString(w / 2, h - 165, "THIS IS PROUDLY PRESENTED TO")

        # Recipient Name with dynamic auto-scaling
        c.setFillColor(primary_color)
        name_font_size = 28
        c.setFont(name_font, name_font_size)
        text_width = c.stringWidth(recipient_name, name_font, name_font_size)
        max_name_width = w - 160

        if text_width > max_name_width:
            name_font_size = int(name_font_size * (max_name_width / text_width))
            name_font_size = max(14, name_font_size)
            c.setFont(name_font, name_font_size)

        c.drawCentredString(w / 2, h - 215, recipient_name)

        # Underline
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(1)
        name_line_width = min(max_name_width, max(260, text_width + 40))
        c.line(w / 2 - name_line_width / 2, h - 225, w / 2 + name_line_width / 2, h - 225)

        # Event Description
        c.setFont(text_font, 11)
        c.setFillColor(slate_color)
        c.drawCentredString(w / 2, h - 260, "for successfully completing and demonstrating proficiency in")

        # Event Name with auto-scaling
        c.setFont(bold_font, 18)
        c.setFillColor(primary_color)
        event_font_size = 18
        event_width = c.stringWidth(event_name, bold_font, event_font_size)
        max_event_width = w - 180
        if event_width > max_event_width:
            event_font_size = int(event_font_size * (max_event_width / event_width))
            event_font_size = max(12, event_font_size)
            c.setFont(bold_font, event_font_size)

        c.drawCentredString(w / 2, h - 295, event_name)

        # Optional remarks
        current_y = h - 322
        if description:
            c.setFont(text_font, 9.5)
            c.setFillColor(slate_color)
            desc_text = description[:140] + ("..." if len(description) > 140 else "")
            c.drawCentredString(w / 2, current_y, desc_text)
            current_y -= 16

        if extra_data:
            meta_parts = [f"{k.capitalize()}: {v}" for k, v in extra_data.items() if v and not str(k).startswith("_")]
            if meta_parts:
                meta_str = " | ".join(meta_parts[:3])
                c.setFont(bold_font, 8.5)
                c.setFillColor(gold_dark)
                c.drawCentredString(w / 2, current_y, meta_str)

        # Decorative Seal
        seal_x, seal_y = w / 2, 115
        c.setFillColor(seal_bg)
        c.setStrokeColor(gold_color)
        c.setLineWidth(2)
        c.circle(seal_x, seal_y, 32, fill=1, stroke=1)
        c.circle(seal_x, seal_y, 28, fill=0, stroke=1)

        c.setFont(bold_font, 7)
        c.setFillColor(gold_dark)
        c.drawCentredString(seal_x, seal_y + 9, "OFFICIAL")
        c.drawCentredString(seal_x, seal_y - 2, "SEAL OF")
        c.drawCentredString(seal_x, seal_y - 12, "EXCELLENCE")

        # Left Footer: QR Code & Verification Info
        qr_x, qr_y = 65, 75
        self._draw_qr_code(c, qr_x, qr_y, 55, verify_url)

        left_info_x = qr_x + 65
        c.setFont(text_font, 8.5)
        c.setFillColor(slate_color)
        c.drawString(left_info_x, 120, f"Issued Date: {issue_date}")
        c.drawString(left_info_x, 107, "Certificate ID:")
        c.setFont("Courier-Bold", 8)
        c.setFillColor(primary_color)
        c.drawString(left_info_x, 95, certificate_id)
        c.setFont(text_font, 7)
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.drawString(left_info_x, 82, "Scan QR code to verify online")

        # Right Footer: Signature Block
        right_x = w - 230
        c.setStrokeColor(colors.HexColor("#64748B"))
        c.setLineWidth(1)
        c.line(right_x, 110, right_x + 150, 110)

        c.setFont(bold_font, 11)
        c.setFillColor(primary_color)
        c.drawString(right_x + 15, 117, issuer_name or "Authorized Officer")

        c.setFont(bold_font, 8.5)
        c.setFillColor(slate_color)
        c.drawString(right_x + 20, 95, "Authorized Signatory")
        c.setFont(text_font, 7.5)
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.drawString(right_x + 25, 82, "Board of Examiners")

    def _render_modern(self, c, w, h, recipient_name, event_name, issuer_name, issue_date,
                       certificate_id, description, extra_data, verify_url, name_font, text_font, bold_font):
        indigo_dark = colors.HexColor("#1E1B4B")
        emerald_accent = colors.HexColor("#059669")
        slate_text = colors.HexColor("#334155")
        bg_color = colors.HexColor("#F8FAFC")

        # Background
        c.setFillColor(bg_color)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # Top Accent Header Bar
        c.setFillColor(indigo_dark)
        c.rect(0, h - 18, w, 18, fill=1, stroke=0)
        c.setFillColor(emerald_accent)
        c.rect(0, h - 24, w, 6, fill=1, stroke=0)

        # Outer clean border
        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(2)
        c.rect(25, 25, w - 50, h - 50)

        # Header Title
        c.setFont(bold_font, 11)
        c.setFillColor(emerald_accent)
        c.drawString(60, h - 70, (issuer_name or "ACCREDITED INSTITUTION").upper())

        c.setFont(bold_font, 26)
        c.setFillColor(indigo_dark)
        c.drawString(60, h - 105, "CERTIFICATE OF RECOGNITION")

        # Presentation Line
        c.setFont(text_font, 10.5)
        c.setFillColor(slate_text)
        c.drawString(60, h - 150, "This is proudly presented to")

        # Recipient Name with dynamic auto-scaling
        c.setFont(bold_font, 26)
        c.setFillColor(indigo_dark)
        c.drawString(60, h - 195, recipient_name)

        # Event Description
        c.setFont(text_font, 11)
        c.setFillColor(slate_text)
        c.drawString(60, h - 240, "For successfully completing and meeting all program requirements in")

        c.setFont(bold_font, 17)
        c.setFillColor(emerald_accent)
        c.drawString(60, h - 270, event_name)

        if description:
            c.setFont(text_font, 9.5)
            c.setFillColor(slate_text)
            c.drawString(60, h - 300, description[:150])

        # Bottom Left: QR Code
        qr_x, qr_y = 60, 60
        self._draw_qr_code(c, qr_x, qr_y, 60, verify_url)

        c.setFont(text_font, 8)
        c.setFillColor(slate_text)
        c.drawString(135, 105, f"Date: {issue_date}")
        c.drawString(135, 90, f"Credential ID: {certificate_id}")
        c.setFont(text_font, 7)
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.drawString(135, 75, "Verify: Scan QR code or browse /verify")

        # Bottom Right: Issuer Sign
        right_x = w - 220
        c.setStrokeColor(colors.HexColor("#94A3B8"))
        c.setLineWidth(1)
        c.line(right_x, 90, right_x + 160, 90)

        c.setFont(bold_font, 10)
        c.setFillColor(indigo_dark)
        c.drawString(right_x, 75, issuer_name or "Authorized Director")


certificate_generator = CertificateGenerator()
