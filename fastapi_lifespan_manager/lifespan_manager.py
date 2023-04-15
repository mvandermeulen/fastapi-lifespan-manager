from __future__ import annotations

import inspect
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    AsyncIterator,
    ContextManager,
    Dict,
    Generic,
    Iterator,
    List,
    Literal,
    Optional,
    Union,
    cast,
    overload,
)

from fastapi import FastAPI
from fastapi.concurrency import contextmanager_in_threadpool

from .types import AnyState, RawLifespan, State, TApp


def _convert_raw_lifespan_to_ctx(
    app: TApp,
    raw_lifespan: RawLifespan[TApp],
) -> Union[ContextManager[AnyState], AsyncContextManager[AnyState]]:
    if inspect.isasyncgenfunction(raw_lifespan):
        return asynccontextmanager(raw_lifespan)(app)
    if inspect.isgeneratorfunction(raw_lifespan):
        return contextmanager(raw_lifespan)(app)

    return cast(Union[ContextManager[AnyState], AsyncContextManager[AnyState]], raw_lifespan(app))


@asynccontextmanager
async def _run_raw_lifespan(raw_lifespan: RawLifespan[TApp], app: TApp) -> AsyncIterator[AnyState]:
    ctx = _convert_raw_lifespan_to_ctx(app, raw_lifespan)

    actx: AsyncContextManager[AnyState]
    actx = contextmanager_in_threadpool(ctx) if isinstance(ctx, ContextManager) else ctx

    async with actx as state:
        yield state


class LifespanManager(Generic[TApp]):
    lifespans: List[RawLifespan[TApp]]

    if TYPE_CHECKING:

        @overload
        def __new__(cls, __lifespans: Iterator[RawLifespan[TApp]], /) -> LifespanManager[TApp]:
            pass

        @overload
        def __new__(cls, __lifespans: Literal[None] = None, /) -> LifespanManager[FastAPI]:
            pass

        def __new__(cls, __lifespans: Optional[Iterator[RawLifespan[TApp]]] = ..., /) -> LifespanManager[Any]:
            pass

    else:

        def __init__(self, lifespans: Optional[Iterator[RawLifespan[TApp]]] = None, /) -> None:
            self.lifespans = [*(lifespans or [])]

    def add(self, lifespan: RawLifespan[TApp]) -> RawLifespan[TApp]:
        self.lifespans.append(lifespan)
        return lifespan

    def remove(self, lifespan: RawLifespan[TApp]) -> None:
        self.lifespans.remove(lifespan)

    @asynccontextmanager
    async def __call__(self, app: TApp) -> AsyncIterator[State]:
        async with AsyncExitStack() as astack:
            state: Dict[str, Any] = {}

            for raw_lifespan in self.lifespans:
                sub_state = await astack.enter_async_context(_run_raw_lifespan(raw_lifespan, app))

                if sub_state:
                    state.update(sub_state)

            print(state)
            yield state


if not TYPE_CHECKING:
    # mypy complains about using a dataclass directly with LifeSpanManager
    LifeSpanManager = dataclass(init=False)(LifespanManager)

__all__ = [
    "LifespanManager",
]
