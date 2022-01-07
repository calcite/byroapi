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
from .template import Template, draw_on_template
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

        filled_form = self._fill_form(form_payload)
        try:
            output_file.write(filled_form.getbuffer())
        except Exception as e:
            raise e
        finally:
            filled_form.close()

    async def _process_form(self, form_payload: dict) -> Union[BinaryIO, None]:

        filled_form = self._fill_form(form_payload)

        if form_payload["result"]["email"]["to"] is not None:
            # Sending the result by mail
            async with AIOSMTP(**self._config["email"]["smtp"]) as yag:
                # Prepare the buffer
                filled_form.seek(0)

                # Attachment file name
                filled_form.name = form_payload["result"]["email"][
                    "attachments"] or f"{form_payload['template']}.pdf"
                form_payload["result"]["email"]["attachments"] = filled_form
                await yag.send(**form_payload["result"]["email"])

            logger.info("Filled form %s sent to %s.", form_payload["template"],
                        form_payload["result"]["email"]["to"])

        if form_payload["result"]["download"]:
            return filled_form
        else:
            return None

    def _update_template(self, template_payload):
        pass

    def start(self):
        # REST
        self._http_task = self._loop.create_task(self._http_handler.run(
            host=self._config['rest_api']['addr'],
            port=self._config['rest_api']['port']
        ))

    def stop(self):
        # REST
        self._http_handler.shutdown()
