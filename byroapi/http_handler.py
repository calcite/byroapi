"""
.. module: byroapi.http_handler
   :synopsis: Handles the HTTP and Websocket connection to the UI.
.. moduleauthor:: "Josef Nevrly <josef.nevrly@gmail.com>"
"""

import logging

from aiohttp import web
from multidict import MultiDict
from cascadict import CascaDict

from .base import ByroapiException


class RestApiError(ByroapiException):
    pass


class HttpHandler:

    def __init__(self, loop, form_request_clbk=None, template_update_clbk=None):

        self._loop = loop
        self._sockjs_manager = None
        self._app = web.Application()
        self._runner = None
        self._init_router()
        self._host_addr = None
        self._host_port = None
        self._logger = logging.getLogger("byroapi")

        self._form_request_clbk = form_request_clbk
        self._template_update_clbk = template_update_clbk

        self._form_result_config = CascaDict({
            "download": False,
            "download_name": None,
            "email": {
                "from": None,
                "to": None,
                "subject": None,
                "contents": None,
                "attachments": None
            }
        })

    async def _process_form(self, request):
        form_payload = await request.json()

        # Inject result manipulation defaults
        form_payload["result"] = self._form_result_config.cascade(
            form_payload.get("result", {}))

        try:
            if self._form_request_clbk is not None:
                resp = await self._form_request_clbk(form_payload)
            else:
                raise RestApiError("Form request processing not defined.")
        except Exception as e:
            template = form_payload.get("template", "Unknown")
            msg = f"Error processing form {template}: {str(e)}"
            self._logger.error(msg)
            return web.json_response({}, status=500, reason=msg)

        if resp:
            download_name = form_payload["result"]["download_name"]

            # https://stackoverflow.com/a/35469345
            return web.Response(
                headers=MultiDict({
                    "Content-Disposition":
                        f"Attachment;filename={download_name}"
                        if download_name else "Attachment"
                }),
                body=resp.getvalue(), content_type="application/pdf"
            )
        else:
            return web.Response()

    async def _process_template(self, request):
        try:
            if self._template_update_clbk is not None:
                self._template_update_clbk(
                    request.match_info["template"],
                    await request.read(),
                    request.match_info["var_id"]
                )
                return web.Response(text="Template succesfully updated.\n")
            else:
                raise RestApiError("Template update process not defined.")
        except Exception as e:
            msg = f"Error updating template: {str(e)}"
            self._logger.error(msg)
            return web.json_response({}, status=500, reason=msg)

    def _init_router(self):
        self._app.router.add_post("/api/v1/form", self._process_form)
        self._app.router.add_put(r"/api/v1/template/{template}/{var_id}", self._process_template)

    async def run(self, host='0.0.0.0', port='8080'):
        # http://aiohttp.readthedocs.io/en/stable/_modules/aiohttp/web.html?highlight=run_app

        self._app.on_shutdown.append(self._on_shutdown)
        self._logger.info("Starting HTTP server")
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Now run it all
        self._host_addr = host
        self._host_port = port

        site = web.TCPSite(self._runner, self._host_addr, self._host_port)
        await site.start()
        self._logger.info(
            f"HTTP server running at {self._host_addr}:{self._host_port}")

    async def _on_shutdown(self, app):
        self._logger.debug("Backend server shut down...")

    def shutdown(self):
        self._logger.debug("Shutting down the HttpHandler...")
        self._loop.create_task(self._app.shutdown())

