# -*- coding: utf-8 -*-
"""
.. module: byroapi.byroapi
   :synopsis: Main module
.. moduleauthor:: "Josef Nevrly <josef.nevrly@gmail.com>"
"""


import asyncio
import io
import logging
from typing import BinaryIO, Union

from aioyagmail import AIOSMTP

from .http_handler import HttpHandler
from .template import Template, draw_on_template, register_fonts
from .base import ByroapiException


logger = logging.getLogger("byroapi")


class ByroApiError(ByroapiException):
    pass


class ByroApi:

    def __init__(self, config, loop=None):
        self._config = config
        self._loop = loop or asyncio.get_event_loop()

        # REST
        self._http_handler = HttpHandler(
            self._loop,
            form_request_clbk=self._process_form,
            template_update_clbk=self._update_template
        )
        self._http_task = None

        # Templates
        register_fonts(self._config["templating"]["fonts"])

        self._templates = {}
        for template in self._config["templating"]["templates"]:
            self._templates[template["id"]] = Template(
                template, self._config["templating"]
            )

    def _fill_form(self, form_payload: dict) -> BinaryIO:
        form_output = io.BytesIO()
        try:
            template = self._templates[form_payload["template"]]
        except KeyError:
            err_msg = f"Unknown template: {form_payload['template']}"
            logger.error(err_msg)
            form_output.close()
            raise ByroApiError(err_msg)

        draw_on_template(template.get_template_path(
            form_payload["form_data"]),
            form_output,
            template.get_draw_function(form_payload["form_data"])
        )

        return form_output

    def fill_form_to_file(self, form_payload: dict,
                          output_file: BinaryIO) -> None:

        with self._fill_form(form_payload) as filled_form:
            try:
                output_file.write(filled_form.getbuffer())
            except Exception as e:
                raise e

    async def _process_form(self, form_payload: dict) -> Union[BinaryIO, None]:

        filled_form = self._fill_form(form_payload)

        appendix_msg = ""
        if form_payload["result"]["email"]["to"] is not None:

            # Configure sender (default from SMTP config, or dynamic
            # from the API request
            smtp_settings = self._config["email"]["smtp"].cascade()
            if form_payload["result"]["email"]["from"] is not None:
                if "user" in smtp_settings:
                    logger.warning("Email 'from' field defined although user "
                                   "set in SMTP configuration -> skipping.")
                else:
                    smtp_settings["user"] = form_payload["result"][
                         "email"]["from"]
            else:
                if "user" not in smtp_settings:
                    logger.warning(
                        "User not configured in SMTP setting and no "
                        "'from' field defined in the request -> Sender will "
                        "be unknown.")

            smtp_settings = dict(smtp_settings.copy_flat())
            # Sending the result by mail
            async with AIOSMTP(**smtp_settings) as yag:
                # Prepare the buffer
                filled_form.seek(0)

                # Attachment file name
                filled_form.name = form_payload["result"]["email"][
                    "attachments"] or f"{form_payload['template']}.pdf"
                form_payload["result"]["email"]["attachments"] = filled_form

                # Get rid of the from field
                send_params = dict(form_payload["result"]["email"].copy_flat())
                send_params.pop("from", None)

                await yag.send(**send_params)

            appendix_msg = \
                f'Mail sent to {form_payload["result"]["email"]["to"]}'

        logger.info("Form %s processed for data: {%s}. %s",
                    form_payload["template"],
                    "; ".join([f"{k}: {v}" for k, v in
                              form_payload["form_data"].items()]),
                    appendix_msg
                    )

        if form_payload["result"]["download"]:
            return filled_form
        else:
            return None

    def _update_template(self, template_id, template_data, var_id):
        try:
            template = self._templates[template_id]
        except KeyError:
            raise ByroApiError(f"Unknown template: {template_id}")

        # Get template path
        template_path = template.get_template_file_path(var_id)

        # Save the template
        try:
            with template_path.open("wb") as template_file:
                template_file.write(template_data)
        except Exception as e:
            raise ByroApiError(f"Could not save template to {template_path}")

        logger.info("Template %s updated for %s to file %s", template_id,
                    var_id, template_path)

    def start(self):
        # REST
        self._http_task = self._loop.create_task(self._http_handler.run(
            host=self._config['rest_api']['addr'],
            port=self._config['rest_api']['port']
        ))

    def stop(self):
        # REST
        self._http_handler.shutdown()
