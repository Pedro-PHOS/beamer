"""Render native Design colour controls and every preview without showing a window.

Render the shared Windows/Linux Qt interface.
"""

import argparse
import json
import logging
import math
import os
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NEW_COLOURS = {"aurora", "opal", "sea_glass", "arc", "magnesium", "ruby", "cobalt",
               "moss", "plum", "woad", "saffron", "citron", "laser", "electric", "fuchsia", "ultraviolet"}


def sample(renderer, style, colour):
    from core import effects
    image = renderer.preview(style, colour)
    scene_name = 'preview_switch_scene' if style.startswith('switch:') else 'preview_scene'
    original = getattr(effects, scene_name)

    def without_effect(*args, **kwargs):
        return dict(original(*args, **kwargs), pens=[])

    with mock.patch.object(effects, scene_name, without_effect):
        baseline = renderer.preview(style, colour)
    return image, renderer.changed_pixels(image, baseline)


def colour_rows(platform):
    sys.path.insert(0, str(ROOT / "win_app"))
    import pages_win
    return [(name, list(values)) for name, values in pages_win.colour_groups()]




class QtRenderer:
    def __init__(self, scale=1):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        sys.path.insert(0, str(ROOT / "win_app"))
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QImage, QPainter, QColor
        from PySide6.QtCore import Qt
        import effect_previews
        import app_config
        import theme
        from core import effects
        self.app = QApplication.instance() or QApplication([])
        if self.app.platformName() != "offscreen":
            raise RuntimeError("Qt previews require the offscreen platform")
        theme.init_fonts()
        self.scale = scale
        self.QImage, self.QPainter, self.QColor, self.Qt = QImage, QPainter, QColor, Qt
        self.previews, self.config, self.theme = effect_previews, app_config, theme
        self.styles = ("glow", "beam") + effects.EFFECT_IDS + tuple('switch:' + value for value in effects.SWITCH_STYLES)

    def set_dark(self, dark):
        self.theme.set_dark(dark)

    def image(self, width, height):
        image = self.QImage(math.ceil(width * self.scale), math.ceil(height * self.scale), self.QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(self.scale)
        image.fill(self.Qt.GlobalColor.transparent)
        return image

    def capture(self, widget):
        from PySide6.QtCore import QPoint
        image = self.QImage(math.ceil(widget.width() * self.scale), math.ceil(widget.height() * self.scale),
                            self.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(self.Qt.GlobalColor.transparent)
        painter = self.QPainter(image)
        painter.scale(self.scale, self.scale)
        widget.render(painter, QPoint(0, 0))
        painter.end()
        return image

    def preview(self, style, colour):
        if style.startswith('switch:'):
            widget = self.previews.SwitchStill(style.split(':')[1], 'beam', self.config.palette_colours(colour))
        else:
            widget = self.previews.EffectStill(style, self.config.palette_colours(colour))
        widget.setFixedHeight(84)
        widget.resize(180, 84)
        image = self.image(180, 84)
        painter = self.QPainter(image)
        widget._paint_still(painter, widget._still_time(), still=True)
        painter.end()
        widget.deleteLater()
        return image

    def changed_pixels(self, image, baseline):
        converted = image.convertToFormat(self.QImage.Format.Format_RGBA8888)
        data = bytes(converted.constBits())
        before = bytes(baseline.convertToFormat(self.QImage.Format.Format_RGBA8888).constBits())
        return sum(max(abs(data[index + c] - before[index + c]) for c in range(3)) > 3
                   for index in range(0, len(data) - 3, 4))

    def save(self, image, path):
        if not image.save(str(path)):
            raise RuntimeError(f"Could not save {path}")

    def design_tile(self, family, style, selected=False, hide_pointer=False):
        from PySide6.QtCore import QCoreApplication, QEvent
        from win_app.tests.test_settings_layout_acceptance import SyntheticWindow, responder_harness, write_synthetic_settings
        import tempfile
        if not hasattr(self, "design"):
            self._settings = tempfile.TemporaryDirectory()
            with mock.patch.object(responder_harness, "free_port", return_value=24821):
                self.design = SyntheticWindow(write_synthetic_settings(Path(self._settings.name)))
            self.design.full_screen_timer.stop()
            self.design.refresh_timer.stop()
            self.design._select_page("design")
            self.design.resize(1400, 1100)
            self.design.show()
        choice = self.design.glow_style_choice if family == "crossing" else self.design.switch_style_choice
        self.theme.apply_stylesheet(self.app)
        choice.set_value(style if selected else None)
        preview = choice.tile(style).layout().itemAt(0).widget()
        preview._image = None
        preview.update()
        for _ in range(2):
            QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            self.app.processEvents()
        tile = choice.tile(style)
        if hide_pointer:
            from core import effects
            names = ("preview_scene", "preview_switch_scene")
            with mock.patch.multiple(effects, **{
                    name: (lambda original: lambda *args, **kwargs: dict(original(*args, **kwargs), pointer=None))(
                        getattr(effects, name)) for name in names}):
                preview._image = None
                self.app.processEvents()
                return tile, self.capture(tile)
        return tile, self.capture(tile)


    def colour_page(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        import widgets
        host = QWidget()
        host.setStyleSheet(self.theme.stylesheet())
        layout = QVBoxLayout(host)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(widgets.label("Design / Colour", "heading"))
        choices = widgets.SwatchGroups([(group, [(value, title, self.config.palette_colours(value)) for value, title in values])
                                        for group, values in colour_rows("qt")], "colourful")
        layout.addWidget(choices.view)
        host.resize(1200, layout.sizeHint().height())
        layout.activate()
        return self.capture(host)

    def contact_sheet(self, rows, compact=False):
        cell_w, cell_h, columns = 196, 108, 6
        styles = ("aperture",) if compact else self.styles
        per_colour = 28 + math.ceil(len(styles) / columns) * cell_h
        count = len(rows) if compact else sum(len(values) for _group, values in rows)
        image = self.image(columns * cell_w, count * per_colour)
        image.fill(self.QColor(self.theme.colour("ground")))
        painter = self.QPainter(image)
        painter.setPen(self.QColor(self.theme.colour("ink")))
        samples, top = [], 0
        for group_index, (group, values) in enumerate(rows):
            for colour_index, (colour, title) in enumerate(values):
                x_offset = colour_index * cell_w if compact else 0
                if compact:
                    top = group_index * per_colour
                painter.setFont(self.theme.font(13))
                painter.setFont(self.theme.font(11 if compact else 13))
                painter.drawText(x_offset + 6, top + 20, f"{group} / {title}" if compact else f"{group} / {title} ({colour})")
                top += 28
                for index, style in enumerate(styles):
                    column, row = index % columns, index // columns
                    preview, pixels = sample(self, style, colour)
                    samples.append(dict(group=group, colour=colour, style=style, visible_pixels=pixels))
                    painter.drawImage(x_offset + column * cell_w + 8, top + row * cell_h, preview)
                    painter.setFont(self.theme.font(10))
                    painter.drawText(x_offset + column * cell_w + 8, top + row * cell_h + 100, style)
                top += math.ceil(len(styles) / columns) * cell_h
        painter.end()
        return image, samples

    def style_contact_sheet(self, rows, path):
        from PySide6.QtCore import QRect
        cell_w, cell_h = 300, 280
        image = self.image(cell_w * 2, cell_h * len(rows))
        image.fill(self.QColor(self.theme.colour("ground")))
        painter = self.QPainter(image)
        painter.setPen(self.QColor(self.theme.colour("ink")))
        for index, (family, style, light, dark) in enumerate(rows):
            y = index * cell_h
            painter.drawText(8, y + 18, f"{family}: {style}")
            painter.drawText(8, y + 38, "Light")
            painter.drawText(cell_w + 8, y + 38, "Dark")
            target = QRect(8, y + 48, 275, 210)
            painter.drawImage(target, light)
            painter.drawImage(target.translated(cell_w, 0), dark)
        painter.end()
        self.save(image, path)


def style_cases():
    from core import effects
    for style in ("glow", "beam", *effects.EFFECT_IDS):
        yield "crossing", style
    for style in effects.SWITCH_STYLES:
        yield "switch", style


def relative_luminance(rgb):
    channels = [value / 255 for value in rgb]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))


def style_metrics(renderer, family, style):
    tile, image = renderer.design_tile(family, style, False, hide_pointer=True)
    if renderer.__class__.__name__ == "QtRenderer":
        from PySide6.QtCore import QPoint
        preview = tile.layout().itemAt(0).widget()
        origin = preview.mapTo(tile, QPoint())
        rect = (origin.x(), origin.y(), preview.width(), preview.height())
        converted = image.convertToFormat(renderer.QImage.Format.Format_RGBA8888)
        get_pixel = lambda x, y: converted.pixelColor(x, y).getRgb()[:3]
        image_width, image_height = image.width(), image.height()
    else:
        preview = tile.tile_content.preview
        bounds = preview.frame()
        rect = (round(bounds.origin.x), round(bounds.origin.y), round(bounds.size.width), round(bounds.size.height))
        channels, data = image.samplesPerPixel(), bytes(image.bitmapData())
        image_width, image_height = image.pixelsWide(), image.pixelsHigh()
        def get_pixel(x, y):
            offset = y * image.bytesPerRow() + x * channels
            return tuple(data[offset:offset + 3])
    ground = (14, 15, 13)
    ground_lum = relative_luminance(ground)
    x0, y0, width, height = rect
    left, top = max(0, round(x0 * renderer.scale)), max(0, round(y0 * renderer.scale))
    right = min(image_width, round((x0 + width) * renderer.scale))
    bottom = min(image_height, round((y0 + height) * renderer.scale))
    distances, marked = [], 0
    for y in range(top, bottom):
        for x in range(left, right):
            rgb = get_pixel(x, y)
            if max(abs(rgb[index] - ground[index]) for index in range(3)) > 3:
                marked += 1
                lum = relative_luminance(rgb)
                distances.append((max(lum, ground_lum) + .05) / (min(lum, ground_lum) + .05))
    distances.sort()
    index = min(len(distances) - 1, math.ceil(.9 * len(distances)) - 1) if distances else 0
    return (distances[index] if distances else 1.0), marked / max(1, (right - left) * (bottom - top))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("qt",), required=True)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contact-sheet", action="store_true")
    parser.add_argument("--style-tiles", action="store_true", help="Render the native Design tile widgets")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renderer = QtRenderer(args.scale)
    if args.style_tiles:
        report = []
        tile_images = {}
        for dark in (False, True):
            mode = "dark" if dark else "light"
            renderer.set_dark(dark)
            for family, style in style_cases():
                contrast, coverage = style_metrics(renderer, family, style)
                folder = args.output / family / mode / f"{args.scale}x"
                folder.mkdir(parents=True, exist_ok=True)
                for selected in (False, True):
                    _tile, image = renderer.design_tile(family, style, selected)
                    suffix = "selected" if selected else "unselected"
                    renderer.save(image, folder / f"{style}-{suffix}.png")
                    if not selected:
                        tile_images.setdefault((family, style), {})[mode] = image
                report.append((family, style, mode, args.scale, contrast, coverage))
        sheet_rows = [(family, style, images["light"], images["dark"])
                      for (family, style), images in tile_images.items()]
        renderer.style_contact_sheet(sheet_rows, args.output / f"{args.platform}-{args.scale}x-style-contact.png")
        print("| Style | Appearance | Scale | Contrast | Coverage |")
        print("|---|---|---:|---:|---:|")
        for family, style, mode, scale, contrast, coverage in report:
            print(f"| {family}/{style} | {mode} | {scale}x | {contrast:.2f}:1 | {coverage:.2%} |")
        return
    rows, records = colour_rows(args.platform), []
    for dark in (False, True):
        mode = "dark" if dark else "light"
        renderer.set_dark(dark)
        path = args.output / f"{args.platform}-colours-1200pt-{args.scale}x-{mode}.png"
        renderer.save(renderer.colour_page(), path)
        print(path, flush=True)
        if args.contact_sheet:
            image, samples = renderer.contact_sheet(rows)
            path = args.output / f"{args.platform}-contact-{args.scale}x-{mode}.png"
            renderer.save(image, path)
            records.extend(dict(sample, mode=mode) for sample in samples)
            print(path, "samples", len(samples), "minimum visible pixels", min(s["visible_pixels"] for s in samples), flush=True)
            compact, _samples = renderer.contact_sheet(rows, compact=True)
            path = args.output / f"{args.platform}-palettes-{args.scale}x-{mode}.png"
            renderer.save(compact, path)
            print(path, flush=True)
    if records:
        path = args.output / f"{args.platform}-pixels-{args.scale}x.json"
        path.write_text(json.dumps(records, indent=2) + "\n")
        missing = [sample for sample in records if sample["visible_pixels"] == 0]
        if missing:
            raise RuntimeError(f"Native previews without visible coloured pixels: {missing}")


if __name__ == "__main__":
    main()
