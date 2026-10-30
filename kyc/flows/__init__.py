"""Flow registry: every module in this package that exports FLOW is registered. Drop a file in, no wiring."""
import importlib
import pkgutil

FLOWS = {}
for _m in pkgutil.iter_modules(__path__):
    _flow = getattr(importlib.import_module(f'{__name__}.{_m.name}'), 'FLOW', None)
    if _flow:
        FLOWS[_flow.key] = _flow
