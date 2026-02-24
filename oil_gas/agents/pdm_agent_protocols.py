"""Compatibility wrapper for shared PdM agent protocols.

Source of truth lives in ``predictive_maintenance.agents.protocols``.
This module remains for oil_gas backward compatibility.
"""

from predictive_maintenance.agents import protocols as _protocols

__all__ = [name for name in dir(_protocols) if not name.startswith("_")]

for _name in __all__:
    globals()[_name] = getattr(_protocols, _name)
