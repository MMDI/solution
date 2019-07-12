#!/usr/bin/env python3

from typing import List, Optional

import sys
import logging
import asyncio
import aiohttp

MAX_RETRIES = 5

log = logging.getLogger()

def setup_logging() -> None:
    """ Setup a logger """
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

async def try_login(session: aiohttp.ClientSession) -> Optional[str]:
    """ Attempt to login and get an access token """
    creds = {
        "username": "guest",
        "password": "guest"
    }
    url = "http://localhost:5000/api/login"
    attempts = 0
    while attempts < MAX_RETRIES:
        resp = await session.post(url, json=creds)
        if resp.status == 200:
            body = await resp.json()
            return body.get('access_token')
    log.error("Too many login attempts %d/%d", attempts, MAX_RETRIES)
    return None

async def try_get(session: aiohttp.ClientSession, url: str, token: Optional[str]) -> Optional[str]:
    """ Attempt to fetch a secret """
    attempts = 0
    while attempts < MAX_RETRIES:
        resp = await session.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status == 200:
            body = await resp.json()
            return body.get('answer')
        if resp.status == 401:
            log.warning("401 Unauthorized, retrying...")
            token = await try_login(session)
            if not token:
                log.error("Error getting new access token")
                return None
    log.error("Too many login attempts %d/%d", attempts, MAX_RETRIES)
    return None

async def main() -> None:
    """ Entry point """
    answers: List[str] = []
    secret_urls = [
        "http://localhost:5000/api/secret1",
        "http://localhost:5000/api/secret2",
        "http://localhost:5000/api/secret3"
    ]
    async with aiohttp.ClientSession() as session:
        token = await try_login(session)
        for url in secret_urls:
            resp = await try_get(session, url, token)
            if not resp:
                log.error("Error getting secret at %s", url)
                continue
            answers.append(resp)
    for answer in answers:
        log.info(answer)

if __name__ == "__main__":
    setup_logging()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    # Graceful exit. Zero-sleep to allow underlying connections to close
    # (https://github.com/aio-libs/aiohttp/issues/1925)
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
