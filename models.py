"""
Pydantic request / response models for the HTTP API.

Kept deliberately small: the engine and the service work with plain dicts so
they stay testable without any web framework installed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import config


class ConnectRequest(BaseModel):
    port: str = Field(..., description="COM port name, or VIRTUAL for test mode")
    baudrate: int = Field(default=config.SERIAL_BAUDRATE, ge=1200, le=2000000)
    scenario: str = Field(default="normal",
                          description="Test-mode scenario, ignored for hardware")


class ScenarioRequest(BaseModel):
    scenario: str = Field(default="normal")


class CommandRequest(BaseModel):
    sensors: Optional[List[str]] = Field(
        default=None, description="Add-on sensors to enable; defaults to all")
    enable: bool = True


class SimpleResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


class PortInfo(BaseModel):
    device: str
    description: str = ""
    hwid: str = ""
    kind: str = "hardware"


class StatusResponse(BaseModel):
    connected: bool
    mode: str
    test_mode: bool
    port: Optional[str] = None
    device_message: Optional[str] = None
    risk_level: Optional[str] = None
    emergency_mode: bool = False

    model_config = {"extra": "allow"}


class LatestResponse(BaseModel):
    available: bool
    message: Optional[str] = None
    latest: Optional[Dict[str, Any]] = None
    status: Optional[Dict[str, Any]] = None
    baseline: Optional[Dict[str, Any]] = None
    alerts: List[Dict[str, Any]] = []

    model_config = {"extra": "allow"}


class HistoryResponse(BaseModel):
    count: int
    source: str
    items: List[Dict[str, Any]] = []
