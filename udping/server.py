# -*- coding: utf-8 -*-
"""
Copyright (c) 2008-2024 synodriver <diguohuangjiajinweijun@gmail.com>
"""
import argparse
import asyncio
from typing import Dict, List, Tuple


class PingServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        self.transport = None
        self.drain_waiter = asyncio.Event()
        self.drain_waiter.set()
        self.lock = asyncio.Lock()
        self._pending_tasks = set()
        self._loop = loop or asyncio.get_running_loop()
        self._close_waiter = self._loop.create_future()

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

    def connection_lost(self, exc):
        self.transport = None
        if exc:
            self._close_waiter.set_exception(exc)
        else:
            self._close_waiter.set_result(None)

    def pause_writing(self):
        self.drain_waiter.clear()

    def resume_writing(self):
        self.drain_waiter.set()

    async def send(self, data, addr):
        async with self.lock:
            self.transport.sendto(data, addr)
            await self.drain()

    async def drain(self):
        await self.drain_waiter.wait()

    def datagram_received(self, data, addr):
        print(f"receive ping from {addr}:{data}")
        task = asyncio.create_task(self.send(data, addr))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def aclose(self):
        self.transport.close()
        await self._close_waiter


async def main():
    parser = get_parser()
    args = parser.parse_args()
    port: str = args.port
    if "-" in port:
        temp = port.split("-")
        ports: List[int] = [i for i in range(int(temp[0]), int(temp[1]))]
    else:
        ports: List[int] = [int(port)]

    loop = asyncio.get_running_loop()
    servers: Dict[int, Tuple[PingServerProtocol, PingServerProtocol]] = {}
    for port in ports:
        _, protocol_v4 = await loop.create_datagram_endpoint(
            PingServerProtocol, local_addr=("0.0.0.0", port)
        )
        _, protocol_v6 = await loop.create_datagram_endpoint(
            PingServerProtocol, local_addr=("::", port)
        )
        servers[port] = (protocol_v4, protocol_v6)
    print(f"listen on port 0.0.0.0:{args.port}; [::]:{args.port}")
    try:
        await loop.create_future()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("exiting")
    finally:
        for port, server in servers.items():
            try:
                await server[0].aclose()
            except Exception as e:
                print(e)
            try:
                await server[1].aclose()
            except Exception as e:
                print(e)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=str, default="8500")
    return parser


if __name__ == "__main__":
    asyncio.run(main())
