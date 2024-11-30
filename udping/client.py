# -*- coding: utf-8 -*-
"""
Copyright (c) 2008-2024 synodriver <diguohuangjiajinweijun@gmail.com>
"""
import argparse
import asyncio
import time
from typing import List, Optional


class PingClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, timeout: float, loop: asyncio.AbstractEventLoop = None):
        self.transport = None
        self.drain_waiter = asyncio.Event()
        self.drain_waiter.set()
        self.lock = asyncio.Lock()
        self.timeout = timeout

        self._loop = loop or asyncio.get_running_loop()
        self._close_waiter = self._loop.create_future()
        self._resp_waiter = None

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

    async def drain(self):
        await self.drain_waiter.wait()

    async def aclose(self):
        self.transport.close()
        await self._close_waiter

    async def send(self, data):
        async with self.lock:
            self.transport.sendto(data)
            await self.drain()

    async def send_ping(self, payload: bytes) -> Optional[int]:
        assert self._resp_waiter is None
        waiter = self._loop.create_future()
        self._resp_waiter = waiter
        curtime = time.time_ns()
        await self.send(payload)
        try:
            await asyncio.wait_for(self._resp_waiter, self.timeout)
        except asyncio.TimeoutError:
            return None
        else:
            return time.time_ns() - curtime
        finally:
            self._resp_waiter = None

    def datagram_received(self, data, addr):
        if self._resp_waiter is not None:
            self._resp_waiter.set_result(data)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=str, default="8500")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("-n", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


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
    clients = {}
    for port in ports:
        _, protocol = await loop.create_datagram_endpoint(
            lambda: PingClientProtocol(args.timeout, loop),
            remote_addr=(args.host, port),
        )
        clients[port] = protocol
    print(f"ping {args.host}:{args.port} with timeout {args.timeout}")

    for i in range(args.n):
        tasks = []
        for port, client in clients.items():
            tasks.append(asyncio.create_task(client.send_ping(b"ping")))
        await asyncio.gather(*tasks)
        for port, t in zip(ports, tasks):
            latency = t.result()
            if latency is None:
                print(f"ping port {port} timeout")
            else:
                print(f"port {port} latency is {latency}ns")
        # latency = await protocol.send_ping(b"ping")
        # if latency is None:
        #     print("ping timeout")
        # else:
        #     print(f"latency is {latency}ns")


if __name__ == "__main__":
    asyncio.run(main())
