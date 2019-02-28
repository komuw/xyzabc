import os
import abc
import uuid
import json
import asyncio
import inspect
import datetime
import random
import string
import logging

from . import broker
from . import ratelimiter
from . import hook
from . import logger
from . import protocol


class TaskOptions:
    def __init__(
        self,
        eta: float = 0.00,
        max_retries: int = 0,
        log_id: str = "",
        hook_metadata=None,
        task_id=None,
    ):
        self._validate_task_options_args(
            eta=eta,
            max_retries=max_retries,
            log_id=log_id,
            hook_metadata=hook_metadata,
            task_id=task_id,
        )
        self.eta = eta
        if self.eta < 0.00:
            self.eta = 0.00
        self.eta = protocol.Protocol._eta_to_isoformat(eta=self.eta)

        self.current_retries = 0
        self.max_retries = max_retries
        if self.max_retries < 0:
            self.max_retries = 0

        self.log_id = log_id
        if not self.log_id:
            self.log_id = ""

        self.hook_metadata = hook_metadata
        if not self.hook_metadata:
            self.hook_metadata = ""

        self.task_id = task_id
        if not self.task_id:
            self.task_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=13))

    def __str__(self):
        return str(self.__dict__)

    def _validate_task_options_args(self, eta, max_retries, log_id, hook_metadata, task_id):
        if not isinstance(eta, float):
            raise ValueError(
                """`eta` should be of type:: `float` You entered: {0}""".format(type(eta))
            )
        if not isinstance(max_retries, int):
            raise ValueError(
                """`max_retries` should be of type:: `int` You entered: {0}""".format(
                    type(max_retries)
                )
            )
        if not isinstance(log_id, str):
            raise ValueError(
                """`log_id` should be of type:: `str` You entered: {0}""".format(type(log_id))
            )
        if not isinstance(hook_metadata, (type(None), str)):
            raise ValueError(
                """`hook_metadata` should be of type:: `None` or `str` You entered: {0}""".format(
                    type(hook_metadata)
                )
            )
        if not isinstance(task_id, (type(None), str)):
            raise ValueError(
                """`task_id` should be of type:: `None` or `str` You entered: {0}""".format(
                    type(task_id)
                )
            )


class Task(abc.ABC):
    """
    call it as:
        Task()(33,"hello", name="komu")

    usage:
        broker = wiji.broker.SimpleBroker()
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
        task1 = wiji.task.Task()
        task2 = wiji.task.Task(chain=task1)
        task3 = wiji.task.Task(chain=task2)
    """

    def __init__(
        self,
        the_broker: broker.BaseBroker,
        queue_name,
        task_name=None,
        chain=None,
        the_hook=None,
        rateLimiter=None,
        loglevel: str = "DEBUG",
        log_metadata=None,
        log_handler=None,
    ) -> None:
        self._validate_task_args(
            the_broker=the_broker,
            queue_name=queue_name,
            task_name=task_name,
            chain=chain,
            the_hook=the_hook,
            rateLimiter=rateLimiter,
            loglevel=loglevel,
            log_metadata=log_metadata,
            log_handler=log_handler,
        )

        self.the_broker = the_broker
        self.queue_name = queue_name
        self.task_name = task_name
        self.chain = chain
        self.loglevel = loglevel.upper()

        self.task_name = task_name
        if not self.task_name:
            self.task_name = self.__class__.__name__

        self.log_metadata = log_metadata
        if not self.log_metadata:
            self.log_metadata = {}
        self.log_metadata.update({"task_name": self.task_name, "queue_name": self.queue_name})

        self.logger = log_handler
        if not self.logger:
            self.logger = logger.SimpleBaseLogger("wiji.Task")
        self.logger.bind(loglevel=self.loglevel, log_metadata=self.log_metadata)
        self._sanity_check_logger(event="task_sanity_check_logger")

        self.the_hook = the_hook
        if not self.the_hook:
            self.the_hook = hook.SimpleHook(logger=self.logger)

        self.rateLimiter = rateLimiter
        if not self.rateLimiter:
            self.rateLimiter = ratelimiter.SimpleRateLimiter(logger=self.logger)

        self.task_options = TaskOptions()

    def __or__(self, other):
        """
        Operator Overloading is bad.
        It should die a swift death.

        This allows someone to do:
            task1 = wiji.task.Task()
            task2 = wiji.task.Task()
            task3 = wiji.task.Task()

            task1 | task2 | task3
        """
        self.chain = other
        return other

    async def __call__(self, *args, **kwargs):
        await self.run(*args, **kwargs)

    def __str__(self):
        return str(
            {
                "task_name": self.task_name,
                "the_broker": self.the_broker,
                "queue_name": self.queue_name,
                "chain": self.chain,
                "task_options": self.task_options.__dict__,
            }
        )

    def _validate_task_args(
        self,
        the_broker,
        queue_name,
        task_name,
        chain,
        the_hook,
        rateLimiter,
        loglevel,
        log_metadata,
        log_handler,
    ):
        if not isinstance(the_broker, (type(None), broker.BaseBroker)):
            raise ValueError(
                """the_broker should be of type:: None or wiji.broker.BaseBroker You entered: {0}""".format(
                    type(the_broker)
                )
            )
        if not isinstance(queue_name, str):
            raise ValueError(
                """`queue_name` should be of type:: `str` You entered: {0}""".format(
                    type(queue_name)
                )
            )

        if not isinstance(task_name, (type(None), str)):
            raise ValueError(
                """`task_name` should be of type:: `None` or `str` You entered: {0}""".format(
                    type(task_name)
                )
            )
        if not isinstance(chain, (type(None), Task)):
            raise ValueError(
                """`chain` should be of type:: `None` or `wiji.task.Task` You entered: {0}""".format(
                    type(chain)
                )
            )
        if not isinstance(the_hook, (type(None), hook.BaseHook)):
            raise ValueError(
                """`the_hook` should be of type:: `None` or `wiji.hook.BaseHook` You entered: {0}""".format(
                    type(the_hook)
                )
            )
        if not isinstance(rateLimiter, (type(None), ratelimiter.BaseRateLimiter)):
            raise ValueError(
                """`rateLimiter` should be of type:: `None` or `wiji.ratelimiter.BaseRateLimiter` You entered: {0}""".format(
                    type(rateLimiter)
                )
            )
        if not isinstance(log_handler, (type(None), logger.BaseLogger)):
            raise ValueError(
                """`log_handler` should be of type:: `None` or `wiji.logger.BaseLogger` You entered: {0}""".format(
                    type(log_handler)
                )
            )
        if loglevel.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(
                """`loglevel` should be one of; 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'. You entered: {0}""".format(
                    loglevel
                )
            )
        if not isinstance(log_metadata, (type(None), dict)):
            raise ValueError(
                """`log_metadata` should be of type:: `None` or `dict` You entered: {0}""".format(
                    type(log_metadata)
                )
            )

        if not asyncio.iscoroutinefunction(self.run):
            raise ValueError(
                "The method: `run` of a class derived from: `wiji.task.Task` should be a python coroutine."
                "\nHint: did you forget to define the method using `async def` syntax?"
            )
        if not inspect.iscoroutinefunction(self.run):
            raise ValueError(
                "The method: `run` of a class derived from: `wiji.task.Task` should be a python coroutine."
                "\nHint: did you forget to define the method using `async def` syntax?"
            )

    def _sanity_check_logger(self, event):
        """
        Called when we want to make sure the supplied logger can log.
        This usually happens when we are instantiating a wiji.Task or a wiji.Worker
        """
        try:
            self.logger.log(logging.DEBUG, {"event": event})
        except Exception as e:
            raise e

    def _log(self, level, log_data):
        # if the supplied logger is unable to log; we move on
        try:
            self.logger.log(level, log_data)
        except Exception:
            pass

    @abc.abstractmethod
    async def run(self, *args, **kwargs):
        raise NotImplementedError("`run` method must be implemented.")

    async def delay(self, *args, **kwargs):
        """
        Parameters:
            args: The positional arguments to pass on to the task.
            kwargs: The keyword arguments to pass on to the task.
        """
        for a in args:
            if isinstance(a, TaskOptions):
                raise ValueError(
                    "You cannot use a value of type `wiji.task.TaskOptions` as a normal argument. Hint: instead, pass it in as a kwarg(named argument)"
                )
        for k, v in list(kwargs.items()):
            if isinstance(v, TaskOptions):
                self.task_options = v
                kwargs.pop(k)

        proto = protocol.Protocol(
            version=1,
            task_id=self.task_options.task_id,
            eta=self.task_options.eta,
            current_retries=self.task_options.current_retries,
            max_retries=self.task_options.max_retries,
            log_id=self.task_options.log_id,
            hook_metadata=self.task_options.hook_metadata,
            argsy=args,
            kwargsy=kwargs,
        )
        await self.the_broker.enqueue(
            item=proto.json(), queue_name=self.queue_name, task_options=self.task_options
        )

    def synchronous_delay(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.delay(*args, **kwargs))


class _watchdogTask(Task):
    """
    This is a task that runs in the MainThread(as every other task).
    Its job is to start a new thread(Thread-<wiji_watchdog>) and communicate with it.
    That new thread will log a stack-trace if it detects any blocking calls(IO-bound, CPU-bound or otherwise) running on the MainThread.
    That trace is meant to help users of `wiji` be able to fix their applications.

    This task is always scheduled in the in-memory broker(`wiji.broker.SimpleBroker`).
    """

    async def run(self):
        self._log(
            logging.DEBUG,
            {
                "event": "wiji.WatchDogTask.run",
                "state": "watchdog_run",
                "task_name": self.task_name,
                "task_id": self.task_options.task_id,
            },
        )
        await asyncio.sleep(0.1 / 1.5)


WatchDogTask = _watchdogTask(the_broker=broker.SimpleBroker(), queue_name="WatchDogTask_Queue")