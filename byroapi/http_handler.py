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
        self._logger = logging.getLogger("byroapi.REST")

        self._form_request_clbk = form_request_clbk
        self._template_update_clbk = template_update_clbk

        self._form_result_config = CascaDict({
            "download": False,
            "email": {
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
            self._logger.error("Error processing form: %s", str(e))
            return web.json_response({}, status=500, reason=str(e))

        if resp:
            return web.Response(
                headers=MultiDict({
                    "Content-Disposition": "Attachment; filename=neco.pdf"
                }),
                body=resp.getvalue(), content_type="application/pdf"
            )
        else:
            return web.Response()

    def _init_router(self):
        self._app.router.add_post("/api/v1/form", self._process_form)

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

