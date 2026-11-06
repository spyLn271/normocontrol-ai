"""Состояние приложения, создаваемое в lifespan."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from normocontrol.api.jobs import JobQueue
from normocontrol.api.repository import CheckRepository
from normocontrol.config.settings import Settings
from normocontrol.pipeline import Services


@dataclass(slots=True)
class AppState:
    settings: Settings
    services: Services
    repository: CheckRepository
    queue: JobQueue


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.normocontrol
    return state
