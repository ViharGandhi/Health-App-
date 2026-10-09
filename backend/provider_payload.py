"""Translate malformed provider data into an explicit, privacy-safe API failure."""
from functools import wraps
from inspect import iscoroutinefunction


class InvalidProviderPayload(ValueError):
    pass


def payload_boundary(function):
    """Keep pure input-validation errors distinct from network/provider failures."""
    errors = (KeyError, TypeError, ValueError, AttributeError, OverflowError)
    if iscoroutinefunction(function):
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            try:
                return await function(*args, **kwargs)
            except errors:
                raise InvalidProviderPayload('Invalid provider payload') from None
        return asynchronous
    @wraps(function)
    def synchronous(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except errors:
            raise InvalidProviderPayload('Invalid provider payload') from None
    return synchronous
