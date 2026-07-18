"""Single source of truth for environment configuration.

All os.getenv() calls MUST live in this file only. Values are read and
validated once, fail-fast, at import time of the composition root.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    host: str
    port: int

    @staticmethod
    def from_env() -> "Config":
        return Config(
            host=os.getenv("HOST", "0.0.0.0"),  # noqa: S104
            port=int(os.getenv("PORT", "8000")),
        )
