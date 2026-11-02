"""One square vector composition shared by preview, PNG, SVG and print exports."""
import io
import math
from functools import lru_cache
from html import escape
from pathlib import Path

import reportlab
import resvg_py
from PIL import Image, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


@lru_cache
def font_files():
    root = Path(reportlab.__file__).parent / 'fonts'
    return [str(root / name) for name in ('Vera.ttf', 'VeraBd.ttf', 'VeraIt.ttf', 'VeraBI.ttf')]


def gradient_colors(design, part):
    stops = design.get(part + '_stops')
    if stops:
        return stops
    first = design.get(part, '#163b75' if part == 'foreground' else '#ffffff')
    last = design.get(part + '_end')
    return [first, last] if last else [first]


def render(data, design, fmt='png', size=1024, print_width_cm=None, print_preset='standard'):
    from .qr import qr_matrix
    matrix = qr_matrix(data)
    n = len(matrix)
    edge = 1000
    top_text, bottom_text = design.get('top_text', ''), design.get('bottom_text', '')
    frame = design.get('frame', 'none')
    callout = frame in ('scan', 'banner')
    pad = 18 if frame == 'border' else 0
    top_band = 110 if top_text else 0
    bottom_band = 110 if bottom_text else 0
    frame_band = 60 if callout else 0
    side = edge - 2 * pad - top_band - bottom_band - frame_band
    left, top = (edge - side) / 2, pad + top_band
    cell = side / n
    fg, bg = design.get('foreground', '#163b75'), design.get('background', '#ffffff')
    definitions = []

    def fill(part):
        colors = gradient_colors(design, part)
        if len(colors) == 1:
            return colors[0]
        stops = ''.join(f'<stop offset="{i * 100 / (len(colors) - 1):g}%" stop-color="{color}"/>' for i, color in enumerate(colors))
        name = 'qr-' + part
        if design.get(part + '_gradient', 'linear') == 'radial':
            definitions.append(f'<radialGradient id="{name}" gradientUnits="userSpaceOnUse" cx="500" cy="450" r="700">{stops}</radialGradient>')
        else:
            angle = math.radians(design.get(part + '_angle', 0))
            cx, cy = math.cos(angle) * 500, math.sin(angle) * 500
            definitions.append(f'<linearGradient id="{name}" gradientUnits="userSpaceOnUse" x1="{500-cx:g}" y1="{500-cy:g}" x2="{500+cx:g}" y2="{500+cy:g}">{stops}</linearGradient>')
        return f'url(#{name})'

    fg_fill, bg_fill = fill('foreground'), fill('background')
    marker = design.get('eye_color') or fg_fill
    shapes = []
    square_commands = []

    def shape(x, y, width, style, color):
        if style == 'circle':
            return f'<circle cx="{x+width/2:g}" cy="{y+width/2:g}" r="{width/2:g}" fill="{color}"/>'
        if style == 'diamond':
            return f'<polygon points="{x+width/2:g},{y:g} {x+width:g},{y+width/2:g} {x+width/2:g},{y+width:g} {x:g},{y+width/2:g}" fill="{color}"/>'
        radius = width * .2 if style == 'rounded' else 0
        return f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{width:g}" rx="{radius:g}" fill="{color}"/>'

    def finder(x, y):
        return (4 <= x < 11 and 4 <= y < 11) or (n-11 <= x < n-4 and 4 <= y < 11) or (4 <= x < 11 and n-11 <= y < n-4)

    pattern = design.get('pattern', 'square')
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if not on or finder(x, y):
                continue
            px, py = left + x * cell, top + y * cell
            functional = x == 10 or y == 10
            if pattern == 'dots' and not functional:
                shapes.append(shape(px, py, cell, 'circle', fg_fill))
            elif pattern == 'diamond' and not functional:
                shapes.append(shape(px, py, cell, 'diamond', fg_fill))
            else:
                dx = cell * .075 if pattern == 'vertical' and not functional else 0
                dy = cell * .075 if pattern == 'horizontal' and not functional else 0
                radius = cell * (.4 if pattern == 'soft' else .22) if pattern in ('soft', 'rounded') and not functional else 0
                if not radius and not dx and not dy:
                    square_commands.append(f'M{px:g},{py:g}h{cell:g}v{cell:g}h{-cell:g}z')
                else:
                    shapes.append(f'<rect x="{px+dx:g}" y="{py+dy:g}" width="{cell-2*dx:g}" height="{cell-2*dy:g}" rx="{radius:g}" fill="{fg_fill}"/>')
    if square_commands:
        # Keep square modules crisp at the requested raster resolution.
        shapes.insert(0,f'<path d="{"".join(square_commands)}" fill="{fg_fill}" shape-rendering="crispEdges"/>')

    outer = design.get('eye_frame_style') or design.get('eye_style', 'square')
    inner = design.get('eye_ball_style') or design.get('eye_style', 'square')
    for index, (x, y) in enumerate(((4, 4), (n-11, 4), (4, n-11))):
        px, py = left+x*cell, top+y*cell
        mask = shape(px, py, 7*cell, outer, 'white') + shape(px+cell, py+cell, 5*cell, outer, 'black') + shape(px+2*cell, py+2*cell, 3*cell, inner, 'white')
        definitions.append(f'<mask id="finder-{index}" maskUnits="userSpaceOnUse" x="0" y="0" width="1000" height="1000">{mask}</mask>')
        shapes.append(f'<rect x="{px:g}" y="{py:g}" width="{7*cell:g}" height="{7*cell:g}" fill="{marker}" mask="url(#finder-{index})"/>')

    logo = design.get('logo')
    if logo:
        width = side * .14
        x, y = left+(side-width)/2, top+(side-width)/2
        inset = width*.1
        shapes.append(f'<rect x="{x-inset:g}" y="{y-inset:g}" width="{width+2*inset:g}" height="{width+2*inset:g}" rx="10" fill="white"/>')
        shapes.append(f'<image href="{escape(logo, quote=True)}" x="{x:g}" y="{y:g}" width="{width:g}" height="{width:g}" preserveAspectRatio="xMidYMid meet"/>')

    def text(label, position):
        font_size = int(design.get(position+'_text_size') or design.get('text_size', 20))
        bold = design.get(position+'_text_bold')
        italic = design.get(position+'_text_italic')
        bold = design.get('text_bold', True) if bold is None else bold
        italic = design.get('text_italic', False) if italic is None else italic
        color = design.get(position+'_text_color') or fg
        filename = font_files()[3 if bold and italic else 1 if bold else 2 if italic else 0]
        # Match vector and raster metrics, including descenders and italic bounds.
        font = ImageFont.truetype(filename, font_size)
        bbox = font.getbbox(label, anchor='ls')
        height = bbox[3]-bbox[1]
        scale = min(1.6, (edge-2*pad-24)/max(1, bbox[2]-bbox[0]))
        offset = max(0, min(100, design.get(position+'_text_offset', 0)))/100
        if position == 'top':
            gap = max(0, top-pad-height*scale) * offset
            baseline = top-gap-bbox[3]*scale
        else:
            start = top+side+frame_band
            gap = max(0, edge-pad-start-height*scale) * offset
            baseline = start+gap-bbox[1]*scale
        weight, slant = ('700' if bold else '400'), ('italic' if italic else 'normal')
        shapes.append(f'<text x="{edge/(2*scale):g}" y="{baseline/scale:g}" transform="scale({scale:g})" text-anchor="middle" font-family="Bitstream Vera Sans,Arial,sans-serif" font-size="{font_size}" font-weight="{weight}" font-style="{slant}" fill="{color}">{escape(label)}</text>')

    if top_text:
        text(top_text, 'top')
    if callout:
        label = design.get('frame_label', 'SCAN ME')
        y = top+side
        color, paper = (fg, bg) if frame == 'banner' else (bg, fg)
        shapes.append(f'<rect x="{left:g}" y="{y:g}" width="{side:g}" height="50" rx="12" fill="{paper}" stroke="{fg}" stroke-width="2"/>')
        if label:
            shapes.append(f'<text x="500" y="{y+34:g}" text-anchor="middle" font-family="Bitstream Vera Sans,Arial,sans-serif" font-size="26" font-weight="700" fill="{color}">{escape(label)}</text>')
    if bottom_text:
        text(bottom_text, 'bottom')
    if frame == 'border':
        shapes.append(f'<rect x="4" y="4" width="992" height="992" rx="30" fill="none" stroke="{fg}" stroke-width="5"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 1000 1000"><defs>{"".join(definitions)}</defs><rect width="1000" height="1000" fill="{bg_fill}"/>{"".join(shapes)}</svg>'
    if fmt == 'svg':
        return svg.encode(), 'image/svg+xml'
    png = resvg_py.svg_to_bytes(svg_string=svg, font_files=font_files(), skip_system_fonts=True)
    image = Image.open(io.BytesIO(png)).convert('RGB')
    output = io.BytesIO()
    if fmt == 'pdf':
        # All QR images are square. Only the explicit A4 paper preset adds a sheet.
        width = (print_width_cm*72/2.54) if print_width_cm else size*72/300
        page_width, page_height = (210*72/25.4, 297*72/25.4) if print_preset == 'a4' else (width, width)
        printed = min(170*72/25.4, width) if print_preset == 'a4' else width
        pdf = canvas.Canvas(output, pagesize=(page_width, page_height))
        pdf.setTitle('TuraQRcode')
        pdf.drawImage(ImageReader(image), (page_width-printed)/2, (page_height-printed)/2, width=printed, height=printed)
        pdf.showPage()
        pdf.save()
        return output.getvalue(), 'application/pdf'
    image.save(output, 'PNG', dpi=(300, 300))
    return output.getvalue(), 'image/png'
