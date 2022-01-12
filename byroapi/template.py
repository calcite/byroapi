"""
.. module: byroapi.template
   :synopsis: Classes and methods for template handling.
.. moduleauthor:: "Josef Nevrly <josef.nevrly@gmail.com>"
"""
import io
import logging
from pathlib import Path
from typing import BinaryIO, Callable, Any


from PyPDF2 import PdfFileReader, PdfFileWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab.rl_config

from cascadict import CascaDict

from .base import ByroapiException


class TemplateError(ByroapiException):
    pass


# Disable warnings when importing fonts
reportlab.rl_config.warnOnMissingFontGlyphs = 0


# Logging
logger = logging.getLogger("byroapi.template")


class Template:

    def __init__(self, template_config: dict, config: CascaDict):
        self._config = config
        self._template_config = template_config

        # Initialize defaults
        if (("field_defaults" in self._template_config) and
           (self._template_config["field_defaults"] is not None)):
            self._field_defaults = self._config["field_defaults"].cascade(
                self._template_config["field_defaults"])
        else:
            self._field_defaults = self._config["field_defaults"]

        # Initialize fields
        self._fields = {}
        for field in self._template_config["fields"]:
            self._fields[field["name"]] = self._field_defaults[
                field["type"]].cascade(field)

        # Initialize template files
        self._template_source = Path(self._template_config["template"]["path"])
        if self._template_source.is_dir():
            self._template_file_pattern = \
                self._template_config["template"]["path_value_substitution"][
                    "pattern"] or "{0}.pdf"
            self._template_file_selector = \
                self._template_config["template"]["path_value_substitution"][
                    "value"]
            if self._template_file_selector is None:
                raise TemplateError("Template file selector not defined.")

    @property
    def template_id(self) -> str:
        return self._template_config["id"]

    @staticmethod
    def _draw_properties(field: dict, draw_canvas: canvas.Canvas) -> None:
        for field_property in field["custom"]:
            getattr(draw_canvas, f"set{field_property['property']}")(
                *field_property["values"])

    @staticmethod
    def _validate_coords(field: dict) -> None:
        coord_list = tuple(field["coords"].values())
        if None in coord_list:
            raise TemplateError(f"Invalid coordinates for field "
                                f"{field['name']}: {coord_list}")

    def _draw_string(self, value: Any, field: dict,
                     draw_canvas: canvas.Canvas) -> None:
        self._validate_coords(field)
        self._draw_properties(field, draw_canvas)
        draw_canvas.drawString(field["coords"]["x"] * mm,
                               field["coords"]["y"] * mm, value)

    def _draw_image(self, value: Any, field: dict,
                    draw_canvas: canvas.Canvas) -> None:
        self._validate_coords(field)
        self._draw_properties(field, draw_canvas)

        # Image size
        im = ImageReader(value)
        width, height = field["width"], field["height"]
        im_h, im_w = im.getSize()
        ar = im_h / im_w

        # Recalculate the other dimension if not specified.
        try:
            width = (field["width"] or (field["height"] / ar)) * mm
            height = (field["height"] or (field["width"] * ar)) * mm
        except TypeError:
            pass  # Both fields are None

        # Draw the image
        draw_canvas.drawImage(im, field["coords"]["x"] * mm,
                              field["coords"]["y"] * mm,
                              width=width, height=height, mask=field["mask"])

    def get_template_file_path(self, name_variable: str) -> Path:
        if self._template_source.is_dir():
            template_file = \
                self._template_source / self._template_file_pattern.format(
                    name_variable)
        else:
            template_file = self._template_source

        return template_file

    def get_template_path(self, values: dict) -> str:
        try:
            template_file = self.get_template_file_path(
                values[self._template_file_selector])
        except KeyError:
            raise TemplateError(
                f"Pattern selector ({self._template_file_selector}) "
                f"not present in the value set.")

        return template_file.as_posix()

    def get_draw_function(self,
                          values: dict) -> Callable[[canvas.Canvas], None]:

        def inner_draw_function(draw_canvas: canvas.Canvas):
            for key, field in self._fields.items():
                value = values.get(key, field["default"])
                if field['type'] == "page_break":
                    draw_canvas.showPage()
                else:
                    try:
                        getattr(self, f"_draw_{field['type']}")(value, field,
                                                                draw_canvas)
                    except AttributeError:
                        raise TemplateError(
                            f"Unknown field type: {field['type']}")

            draw_canvas.showPage()

        return inner_draw_function


def draw_on_template(template_path: str,
                     output: BinaryIO,
                     drawing_function: Callable[[canvas.Canvas], None]) -> None:
    # https://code-maven.com/add-image-to-existing-pdf-file-in-python
    draw_buffer = io.BytesIO()
    draw_canvas = canvas.Canvas(draw_buffer)
    drawing_function(draw_canvas)
    draw_canvas.save()
    draw_buffer.seek(0)

    drawing_overlay_pdf = PdfFileReader(draw_buffer)
    template_pdf = PdfFileReader(template_path)
    output_pdf = PdfFileWriter()

    if len(template_pdf.pages) != len(drawing_overlay_pdf.pages):
        raise Exception(
            f"Not all pages are filled ({len(template_pdf.pages)}/"
            f"{len(drawing_overlay_pdf.pages)})")

    for template_page, overlay_page in zip(template_pdf.pages,
                                           drawing_overlay_pdf.pages):
        template_page.mergePage(overlay_page)
        output_pdf.addPage(template_page)

    output_pdf.write(output)

    draw_buffer.close()


def register_fonts(font_config: list) -> None:
    for font in font_config:
        if font["name"] is None:
            continue
        pdfmetrics.registerFont(TTFont(font["name"], font["path"]))
        logger.info("Registered font %s (%s)", font["name"], font["path"])


