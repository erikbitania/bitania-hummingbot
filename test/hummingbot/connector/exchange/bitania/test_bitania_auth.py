import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock

from hummingbot.connector.exchange.bitania.bitania_auth import BitaniaAuth
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest


class BitaniaAuthTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api_key = "testApiKey"
        self.secret_key = "testApiSecret"
        self.auth = BitaniaAuth(api_key=self.api_key, secret_key=self.secret_key)

    def test_header_for_authentication(self):
        headers = self.auth.header_for_authentication()
        self.assertEqual(self.api_key, headers["X-API-Key"])
        self.assertEqual(self.secret_key, headers["X-API-Secret"])

    async def test_rest_authenticate_injects_headers(self):
        request = RESTRequest(
            method=RESTMethod.POST,
            url="https://api.bitania.com/v1/exchange/orders",
            data='{"pair": "BTC/USDT"}',
            is_auth_required=True,
        )
        authed = await self.auth.rest_authenticate(request)
        self.assertEqual(self.api_key, authed.headers["X-API-Key"])
        self.assertEqual(self.secret_key, authed.headers["X-API-Secret"])
        # Body must be untouched — no signature/timestamp added.
        self.assertEqual('{"pair": "BTC/USDT"}', authed.data)

    async def test_rest_authenticate_preserves_existing_headers(self):
        request = RESTRequest(
            method=RESTMethod.GET,
            url="https://api.bitania.com/v1/exchange/balances",
            headers={"Content-Type": "application/json"},
            is_auth_required=True,
        )
        authed = await self.auth.rest_authenticate(request)
        self.assertEqual("application/json", authed.headers["Content-Type"])
        self.assertEqual(self.api_key, authed.headers["X-API-Key"])

    async def test_ws_authenticate_is_passthrough(self):
        request = MagicMock()
        result = await self.auth.ws_authenticate(request)
        self.assertIs(request, result)

    def test_ws_auth_payload(self):
        payload = self.auth.ws_auth_payload()
        self.assertEqual("auth", payload["op"])
        self.assertEqual(self.api_key, payload["apiKey"])
        self.assertEqual(self.secret_key, payload["apiSecret"])


if __name__ == "__main__":
    asyncio.get_event_loop()
