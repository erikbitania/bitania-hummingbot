from typing import Dict

from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class BitaniaAuth(AuthBase):
    """
    Bitania authentication.

    Unlike Binance, Bitania does NOT use HMAC request signing, timestamps, or a
    listen key. Private REST requests are authenticated purely by two plaintext
    headers sent over TLS:

        X-API-Key:    <api key>
        X-API-Secret: <api secret>

    WebSocket auth is handled separately by the user-stream data source via an
    ``{"op": "auth", ...}`` JSON frame (see bitania_api_user_stream_data_source),
    so ``ws_authenticate`` here is a pass-through.
    """

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Injects the API key/secret headers into the request. There is no
        signature and no timestamp to add, so the body/params are untouched.
        """
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self.header_for_authentication())
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        Bitania authenticates the websocket with an explicit auth frame sent by
        the user-stream data source, not via the request signer. Pass-through.
        """
        return request

    def header_for_authentication(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "X-API-Secret": self.secret_key,
        }

    def ws_auth_payload(self) -> Dict[str, str]:
        """
        The JSON frame used to authenticate the websocket connection:
            {"op": "auth", "apiKey": "...", "apiSecret": "..."}
        """
        return {
            "op": "auth",
            "apiKey": self.api_key,
            "apiSecret": self.secret_key,
        }
