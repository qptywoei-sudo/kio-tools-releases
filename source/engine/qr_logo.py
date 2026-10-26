"""Local QR artwork and exact-payload scan verification. No network or files outside inputs."""
from __future__ import annotations
import base64, html, io, math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageOps


def _number(value, default, minimum, maximum):
    number = float(default if value is None else value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError('invalidRequest')
    return number


def logo_image(job):
    """Only an already authorized, browser-normalized PNG/JPEG input may be used."""
    index = job.get('logoInput')
    if index is None:
        return None
    inputs = job.get('inputs', [])
    if type(index) is not int or index < 0 or index >= len(inputs):
        raise ValueError('invalidRequest')
    path = Path(inputs[index])
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('fileTooLarge')
    with Image.open(path) as source:
        if source.format not in ('PNG', 'JPEG') or getattr(source, 'n_frames', 1) != 1:
            raise ValueError('invalidRequest')
        if source.width * source.height > 16_000_000:
            raise ValueError('fileTooLarge')
        source.load()
        return ImageOps.exif_transpose(source).convert('RGBA')



def logo_geometry(matrix_size, size, logo_percent=30):
    ratio = _number(logo_percent, 30, 10, 30) / 100
    side = max(1, round((size * (matrix_size - 8) / matrix_size) * ratio))
    outer = min(size, side + 8)
    left = (size - outer) // 2
    return {'unit': size / matrix_size, 'side': side, 'outer': outer, 'left': left}


def module_under_badge(geometry, x, y, shape):
    """Remove a touched module as one cell, never a clipped black fragment.

    Use the union of SVG ideal bounds and PNG rounded pixel bounds. A half-pixel
    guard also covers antialiasing along the white card's actual edge.
    """
    unit = geometry['unit']
    x0, y0 = min(x * unit, round(x * unit)), min(y * unit, round(y * unit))
    x1, y1 = max((x + 1) * unit, round((x + 1) * unit)), max((y + 1) * unit, round((y + 1) * unit))
    left, outer = geometry['left'], geometry['outer']
    if shape == 'circle':
        center = left + outer / 2
        nearest_x, nearest_y = max(x0, min(center, x1)), max(y0, min(center, y1))
        return (nearest_x - center) ** 2 + (nearest_y - center) ** 2 <= (outer / 2 + .5) ** 2
    return x1 >= left - .5 and x0 <= left + outer + .5 and y1 >= left - .5 and y0 <= left + outer + .5


def artwork(matrix, size, foreground, background, style, job, logo_percent=30):
    """Return a raster and a self-contained SVG made from the identical QR matrix."""
    n = len(matrix)
    unit = size / n
    from qrcode.util import pattern_position
    alignment = [position + 4 for position in pattern_position((n - 25) // 4)]
    image = Image.new('RGBA', (size, size), background)
    draw = ImageDraw.Draw(image)
    blocks = []
    fill = html.escape(foreground, quote=True)
    logo = logo_image(job)
    shape = job.get('logo_shape', 'square')
    if logo is not None and shape not in ('square', 'circle'):
        raise ValueError('invalidRequest')
    geometry = logo_geometry(n, size, logo_percent) if logo is not None else None
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if not on or (geometry is not None and module_under_badge(geometry, x, y, shape)):
                continue
            box = (round(x * unit), round(y * unit), round((x + 1) * unit) - 1, round((y + 1) * unit) - 1)
            # Keep the QR function patterns square even with decorative data modules.
            finder = (x < 13 and y < 13) or (x >= n - 13 and y < 13) or (x < 13 and y >= n - 13) or x == 10 or y == 10 or any(abs(x - center_x) <= 2 and abs(y - center_y) <= 2 for center_x in alignment for center_y in alignment)
            if style == 'circle' and not finder:
                draw.ellipse(box, fill=foreground)
                blocks.append(f'<circle cx="{x + .5}" cy="{y + .5}" r="0.5" fill="{fill}"/>')
            elif style == 'rounded' and not finder:
                draw.rounded_rectangle(box, radius=unit * .22, fill=foreground)
                blocks.append(f'<rect x="{x}" y="{y}" width="1" height="1" rx="0.22" fill="{fill}"/>')
            else:
                draw.rectangle(box, fill=foreground)
                blocks.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{fill}" shape-rendering="crispEdges"/>')
    if logo is not None:
        side = geometry['side']
        # Fixed four output pixels of white padding. Request options cannot
        # override padding or bypass the automatic scan-verified size search.
        outer = geometry['outer']
        badge = Image.new('RGBA', (outer, outer), '#ffffff')
        placed = ImageOps.contain(logo, (side, side), Image.Resampling.LANCZOS)
        inside = Image.new('RGBA', (side, side))
        inside.alpha_composite(placed, ((side - placed.width) // 2, (side - placed.height) // 2))
        if shape == 'circle':
            inner_mask = Image.new('L', inside.size)
            ImageDraw.Draw(inner_mask).ellipse((0, 0, side - 1, side - 1), fill=255)
            inside.putalpha(ImageChops.multiply(inside.getchannel('A'), inner_mask))
        badge.alpha_composite(inside, ((outer - side) // 2, (outer - side) // 2))
        if shape == 'circle':
            mask = Image.new('L', badge.size)
            ImageDraw.Draw(mask).ellipse((0, 0, outer - 1, outer - 1), fill=255)
            badge.putalpha(mask)
        left = geometry['left']
        image.alpha_composite(badge, (left, left))
        buffer = io.BytesIO()
        badge.save(buffer, 'PNG')
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        # The logo is a normalized, self-contained PNG. The exported SVG never
        # retains executable SVG markup or references the source logo file.
        blocks.append(f'<image x="{left / unit:.9g}" y="{left / unit:.9g}" width="{outer / unit:.9g}" height="{outer / unit:.9g}" href="data:image/png;base64,{encoded}"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size}" height="{size}"><rect width="{n}" height="{n}" fill="{html.escape(background, quote=True)}"/>' + ''.join(blocks) + '</svg>'
    return image, svg, logo is not None


def verify_scan(image, expected):
    import zxingcpp
    decoded = zxingcpp.read_barcodes(image.convert('RGB'))
    return any(item.format == zxingcpp.BarcodeFormat.QRCode and item.text == expected for item in decoded)


def logo_candidates(matrix_size, size):
    cell = size / matrix_size
    candidates = []
    for percent in range(30, 9, -1):
        geometry = logo_geometry(matrix_size, size, percent)
        # Keep the card and its antialiased edge within the central corridor,
        # outside finder/separator/timing regions. Central alignment patterns
        # remain part of the exact export decoder's error-correction check.
        near = max(12 * cell, round(12 * cell)) + .5
        far = min((matrix_size - 12) * cell, round((matrix_size - 12) * cell)) - .5
        if geometry['left'] > near and geometry['left'] + geometry['outer'] < far:
            candidates.append(percent)
    return candidates


def verify_export(path, expected):
    """Check the actual bytes being delivered, including SVG image embedding/JPEG encoding."""
    if Path(path).suffix.lower() == '.svg':
        import pymupdf
        with pymupdf.open(path) as document:
            page = document[0]
            scale = min(1, 2048 / max(page.rect.width, page.rect.height))
            pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = Image.frombytes('RGB', (pixels.width, pixels.height), pixels.samples)
    else:
        with Image.open(path) as source:
            source.load()
            image = source.convert('RGB')
    try:
        return verify_scan(image, expected)
    finally:
        image.close()


def verify_svg(svg, expected):
    import pymupdf
    with pymupdf.open(stream=svg.encode('utf-8'), filetype='svg') as document:
        page = document[0]
        scale = min(1, 2048 / max(page.rect.width, page.rect.height))
        pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.frombytes('RGB', (pixels.width, pixels.height), pixels.samples)
    try:
        return verify_scan(image, expected)
    finally:
        image.close()
