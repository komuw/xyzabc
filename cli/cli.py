import os
import sys
import json
import random
import string
import asyncio
import typing
import logging
import inspect
import argparse


import xyzabc

os.environ["PYTHONASYNCIODEBUG"] = "1"


def load_class(dotted_path):
    """
    taken from: https://github.com/coleifer/huey/blob/4138d454cc6fd4d252c9350dbd88d74dd3c67dcb/huey/utils.py#L44
    huey is released under MIT license a copy of which can be found at: https://github.com/coleifer/huey/blob/master/LICENSE

    The license is also included below:

    Copyright (c) 2017 Charles Leifer

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.
    """
    try:
        path, klass = dotted_path.rsplit(".", 1)
        __import__(path)
        mod = sys.modules[path]
        attttr = getattr(mod, klass)
        return attttr
    except Exception:
        cur_dir = os.getcwd()
        if cur_dir not in sys.path:
            sys.path.insert(0, cur_dir)
            return load_class(dotted_path)
        err_mesage = "Error importing {0}".format(dotted_path)
        sys.stderr.write("\033[91m{0}\033[0m\n".format(err_mesage))
        raise


def main():
    """
    """
    pass


async def produce_tasks_continously(task, *args, **kwargs):
    while True:
        await task.async_delay(*args, **kwargs)


def http_task(broker) -> xyzabc.task.Task:
    class MyTask(xyzabc.task.Task):
        async def async_run(self, *args, **kwargs):
            import aiohttp

            url = kwargs["url"]
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    print("resp statsus: ", resp.status)
                    res_text = await resp.text()
                    print(res_text[:50])

    task = MyTask(
        broker=broker,
        queue_name="HttpQueue",
        eta=60,
        retries=3,
        log_id="myLogID",
        hook_metadata='{"email": "example@example.com"}',
    )
    return task


def print_task(broker) -> xyzabc.task.Task:
    class MyTask(xyzabc.task.Task):
        async def async_run(self, *args, **kwargs):
            import hashlib

            print()
            print("args:", args)
            print("kwargs:", kwargs)
            print()
            h = hashlib.blake2b()
            h.update(b"Hello world")
            h.hexdigest()
            await asyncio.sleep(2)

    task = MyTask(
        broker=broker,
        queue_name="PrintQueue",
        eta=60,
        retries=3,
        log_id="myLogID",
        hook_metadata='{"email": "example@example.com"}',
    )
    return task


################## CHAIN ##################
def adder_task(broker, chain=None) -> xyzabc.task.Task:
    class AdderTask(xyzabc.task.Task):
        async def async_run(self, a, b):
            res = a + b
            print()
            print("adder: ", res)
            print()
            return res

    task = AdderTask(
        broker=broker,
        queue_name="AdderTaskQueue",
        eta=60,
        retries=3,
        log_id="adder_task_myLogID",
        hook_metadata='{"email": "adder_task"}',
        chain=chain,
    )
    return task


def divider_task(broker, chain=None) -> xyzabc.task.Task:
    class DividerTask(xyzabc.task.Task):
        async def async_run(self, a):
            res = a / 3
            print()
            print("divider: ", res)
            print()
            return res

    task = DividerTask(
        broker=broker,
        queue_name="DividerTaskQueue",
        eta=60,
        retries=3,
        log_id="divider_task_myLogID",
        hook_metadata='{"email": "divider_task"}',
        chain=chain,
    )
    return task


def multiplier_task(broker, chain=None) -> xyzabc.task.Task:
    class MultiplierTask(xyzabc.task.Task):
        async def async_run(self, bbb, a=5.5):
            res = bbb * a
            print()
            print("multiplier: ", res)
            print()
            return res

    task = MultiplierTask(
        broker=broker,
        queue_name="MultiplierTaskQueue",
        eta=60,
        retries=3,
        log_id="multiplier_task_myLogID",
        hook_metadata='{"email": "multiplier_task"}',
        chain=chain,
    )
    return task


################## CHAIN ##################

if __name__ == "__main__":
    main()
    """
    run as:
        python cli/cli.py
    """

    MY_BROKER = xyzabc.broker.SimpleBroker()

    # 1. publish task

    ##### publish 1 ###############
    multiplier = multiplier_task(broker=MY_BROKER)
    divider = divider_task(broker=MY_BROKER, chain=multiplier)

    adder = adder_task(broker=MY_BROKER, chain=divider)
    adder.blocking_delay(3, 7)
    #############################################

    # ALTERNATIVE way of chaining
    adder = adder_task(broker=MY_BROKER)
    adder.blocking_delay(8, 15)
    adder | divider_task(broker=MY_BROKER) | multiplier_task(broker=MY_BROKER)

    #####################################
    http_task1 = http_task(broker=MY_BROKER)
    http_task1.blocking_delay(url="http://httpbin.org/get")

    print_task2 = print_task(broker=MY_BROKER)
    print_task2.blocking_delay("myarg", my_kwarg="my_kwarg")
    #####################################

    # 2.consume task
    async def async_main():
        adder_worker = xyzabc.Worker(task=adder)
        divider_worker = xyzabc.Worker(task=divider)
        multiplier_worker = xyzabc.Worker(task=multiplier)
        http_task_worker = xyzabc.Worker(task=http_task1)
        print_task_worker = xyzabc.Worker(task=print_task2)

        gather_tasks = asyncio.gather(
            adder_worker.consume_forever(),
            divider_worker.consume_forever(),
            multiplier_worker.consume_forever(),
            http_task_worker.consume_forever(),
            print_task_worker.consume_forever(),
            produce_tasks_continously(task=http_task1, url="https://httpbin.org/delay/45"),
        )
        await gather_tasks

    asyncio.run(async_main(), debug=True)
