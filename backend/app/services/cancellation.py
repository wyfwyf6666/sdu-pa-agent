import asyncio
from typing import Any, Awaitable, Dict, Iterable, Optional


class OperationCancelledError(Exception):
    """Raised when a running operation has been cancelled by the user."""

    def __init__(self, identifier: Optional[str] = None) -> None:
        message = "Operation cancelled by user."
        if identifier:
            message = f"{message} token={identifier}"
        super().__init__(message)
        self.identifier = identifier


class CancellationService:
    """
    Manage cancellation tokens mapped to asyncio.Event instances.
    When a token is cancelled, the associated event is set so that cooperating
    coroutines can detect the cancellation and abort promptly.
    """

    def __init__(self) -> None:
        self._events: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def _ensure_event(self, identifier: str) -> asyncio.Event:
        async with self._lock:
            event = self._events.get(identifier)
            if event is None:
                event = asyncio.Event()
                self._events[identifier] = event
            else:
                event.clear()
        return event

    async def register(self, identifier: Optional[str]) -> Optional[asyncio.Event]:
        """
        Ensure an event exists for the identifier and return it. When identifier
        is None, returns None so callers can skip cancellation checks.
        """
        if not identifier:
            return None
        return await self._ensure_event(identifier)

    async def cancel(self, identifier: Optional[str]) -> bool:
        """
        Mark the identifier as cancelled. Returns True when a running operation
        was notified, False otherwise.
        """
        if not identifier:
            return False
        async with self._lock:
            event = self._events.get(identifier)
        if event is None:
            return False
        event.set()
        return True

    async def clear(self, identifier: Optional[str]) -> None:
        """Remove the event for the identifier once the operation finishes."""
        if not identifier:
            return
        async with self._lock:
            self._events.pop(identifier, None)

    async def is_cancelled(self, identifier: Optional[str]) -> bool:
        if not identifier:
            return False
        async with self._lock:
            event = self._events.get(identifier)
        if event is None:
            return False
        return event.is_set()

    async def raise_if_cancelled(self, *identifiers: Optional[str]) -> None:
        for identifier in identifiers:
            if identifier and await self.is_cancelled(identifier):
                raise OperationCancelledError(identifier)

    async def wait_or_cancel(
        self, coro: Awaitable[Any], identifiers: Iterable[Optional[str]]
    ):
        """
        Wait for either the coroutine to finish or a cancellation signal. If
        cancellation happens first, raise OperationCancelledError.
        """
        id_list = list(identifiers)
        cancel_events = []
        valid_ids = []
        for identifier in id_list:
            if not identifier:
                continue
            async with self._lock:
                event = self._events.get(identifier)
            if event is None:
                event = await self._ensure_event(identifier)
            cancel_events.append(event)
            valid_ids.append(identifier)

        if not cancel_events:
            return await coro

        main_task = asyncio.ensure_future(coro)
        wait_set = {main_task}
        wait_set.update(asyncio.create_task(event.wait()) for event in cancel_events)

        done, pending = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

        if main_task in done:
            return main_task.result()

        # cancellation triggered
        for identifier, event in zip(valid_ids, cancel_events):
            if event.is_set():
                raise OperationCancelledError(identifier)
        raise OperationCancelledError()


cancellation_service = CancellationService()
