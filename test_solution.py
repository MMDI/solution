#!/usr/bin/env python3

import asyncio
import collections
import socket
import aiohttp
import aiohttp.test_utils
import aiohttp.web
import pytest
import solution

_RedirectContext = collections.namedtuple('RedirectContext', 'add_server session')

@pytest.fixture
async def aiohttp_redirector() -> None:
    """ Redirect requests to local test server """
    resolver = FakeResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        yield _RedirectContext(add_server=resolver.add, session=session)

class CaseControlledTestServer(aiohttp.test_utils.RawTestServer):
    """ Test server that relies on test case """
    def __init__(self, **kwargs):
        super().__init__(self._handle_request, **kwargs)
        self._requests = asyncio.Queue()
        self._responses = {}                # {id(request): Future}

    async def close(self) -> None:
        """ Cancel all pending requests before closing """
        for future in self._responses.values():
            future.cancel()
        await super().close()

    async def _handle_request(self, request):
        """ Push request to test case and wait until it provides a response """
        self._responses[id(request)] = response = asyncio.Future()
        self._requests.put_nowait(request)
        try:
            # wait until test case provides a response
            return await response
        finally:
            del self._responses[id(request)]

    async def receive_request(self):
        """ Wait until test server receives a request """
        return await self._requests.get()

    def send_response(self, request, *args, **kwargs):
        """ Send web response from test case to client code """
        response = aiohttp.web.Response(*args, **kwargs)
        self._responses[id(request)].set_result(response)

class FakeResolver:
    """ Resolves tested addresses to local test servers """
    def __init__(self) -> None:
        self._servers = {}

    def add(self, host, port, target_port):
        """ Add a tested address """
        self._servers[host, port] = target_port

    async def resolve(self, host, port=0):
        """ Resolve a host:port into a connectable address """
        try:
            fake_port = self._servers[host, port]
        except KeyError:
            raise OSError('No test server known for %s' % host)
        return [{
            'hostname': host,
            'host': '127.0.0.1',
            'port': fake_port,
            'proto': 0,
            'flags': socket.AI_NUMERICHOST,
        }]

@pytest.mark.asyncio
async def test_try_login(aiohttp_redirector):
    async with CaseControlledTestServer() as server:
        aiohttp_redirector.add_server('localhost', 5000, server.port)
        session = aiohttp_redirector.session

        task = asyncio.create_task(solution.try_login(session))
        request = await server.receive_request()
        assert request.path_qs == '/api/login'

        server.send_response(request,
                             text='{"access_token": "3da2cb47-489c-48f7-957e-6fbf5a75fc47"}',
                             content_type='application/json')
        token = await task
        assert token == '3da2cb47-489c-48f7-957e-6fbf5a75fc47'

@pytest.mark.asyncio
async def test_try_get(aiohttp_redirector):
    async with CaseControlledTestServer() as server:
        aiohttp_redirector.add_server('localhost', 5000, server.port)
        session = aiohttp_redirector.session

        url = "http://localhost:5000/api/secret1"
        token = '3da2cb47-489c-48f7-957e-6fbf5a75fc47'
        task = asyncio.create_task(solution.try_get(session, url, token))
        request = await server.receive_request()
        assert request.path_qs == '/api/secret1'

        server.send_response(request,
                             text='{"answer": "The first door, unlocked."}',
                             content_type='application/json')
        answer = await task
        assert answer == 'The first door, unlocked.'
