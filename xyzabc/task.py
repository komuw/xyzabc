import os
import uuid
import json
import asyncio
import datetime

from . import broker


class Task:
    """
    call it as:
        Task()(33,"hello", name="komu")

    usage:
        broker = xyzabc.broker.SimpleBroker()
        task = Task(
                broker=broker,
                queue_name="PrintQueue",
                eta=60,
                retries=3,
                log_id="myLogID",
                hook_metadata='{"email": "example@example.com"}',
            )
        task.delay(33, "hello", name="komu")
    
    You can also chain things as:
        task1 = xyzabc.task.Task()
        task2 = xyzabc.task.Task(chain=task1)
        task3 = xyzabc.task.Task(chain=task2)
    """

    def __init__(
        self, broker: broker.BaseBroker, queue_name, eta, retries, log_id, hook_metadata, chain=None
    ) -> None:
        self.broker = broker
        self.queue_name = queue_name
        self.eta = eta
        self.retries = retries
        self.log_id = log_id
        self.hook_metadata = hook_metadata
        if not isinstance(chain, (type(None), Task)):
            raise ValueError(
                """chain should be of type:: None or xyzabc.task.Task You entered {0}""".format(
                    type(chain)
                )
            )
        self.chain = chain

    def __or__(self, other):
        """
        Operator Overloading is bad.
        It should die a swift death.

        This allows someone to do:
            task1 = xyzabc.task.Task()
            task2 = xyzabc.task.Task()
            task3 = xyzabc.task.Task()

            task1 | task2 | task3
        """
        self.chain = other
        return other

    async def __call__(self, *args, **kwargs):
        await self.async_run(*args, **kwargs)

    async def async_run(self, *args, **kwargs):
        raise NotImplementedError("run method must be implemented.")

    def blocking_run(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.async_run(*args, **kwargs))

    async def async_delay(self, *args, **kwargs):
        """
        Parameters:
            args: The positional arguments to pass on to the task.
            kwargs: The keyword arguments to pass on to the task.
        """
        # Queue this to queue
        class_name: str = self.__class__.__name__

        eta = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.eta)
        protocol = {
            "version": 1,
            "task_id": str(uuid.uuid4()),
            "eta": eta.isoformat(),
            "retries": self.retries,
            "queue_name": self.queue_name,
            "log_id": self.log_id,
            "hook_metadata": self.hook_metadata,
            "timelimit": 1800,
            "args": args,
            "kwargs": kwargs,
        }

        protocol_json = json.dumps(protocol)
        await self.broker.enqueue(item=protocol_json, queue_name=self.queue_name)

    def blocking_delay(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.async_delay(*args, **kwargs))
