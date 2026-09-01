import re
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
        return value

class UserCreate(Credentials):
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    role: Literal['analyst', 'viewer'] = 'analyst'

class CaseCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default='', max_length=500)

class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal['analyst', 'viewer']

class Review(BaseModel):
    status: Literal['open', 'reviewed']

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prev_txid: str = Field(pattern=r'^[0-9a-f]{64}$')
    prev_vout: int = Field(ge=0, le=4294967295, strict=True)
    sequence: int | None = Field(default=None, ge=0, le=4294967295, strict=True)

class Output(BaseModel):
    model_config = ConfigDict(extra='forbid')
    index: int = Field(ge=0, strict=True)
    value_sats: int = Field(ge=0, le=2100000000000000, strict=True)
    address: str | None = Field(default=None, max_length=200)
    script_type: str | None = Field(default=None, max_length=80)
    script_hex: str | None = Field(default=None, max_length=20000, pattern=r"^(?:[0-9a-fA-F]{2})*$")

class Transaction(BaseModel):
    model_config = ConfigDict(extra='ignore')
    txid: str = Field(pattern=r'^[0-9a-f]{64}$')
    observed_at: datetime | None = None
    block_time: datetime | None = None
    confirmed: bool | None = Field(default=None, strict=True)
    confirmations: int | None = Field(default=None, ge=0, strict=True)
    block_height: int | None = Field(default=None, ge=0, strict=True)
    block_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    size_bytes: int | None = Field(default=None, ge=1, le=4000000, strict=True)
    weight: int | None = Field(default=None, ge=1, le=4000000, strict=True)
    version: int | None = Field(default=None, strict=True)
    locktime: int | None = Field(default=None, ge=0, le=4294967295, strict=True)
    @model_validator(mode='after')
    def consistent_confirmation(self):
        if self.confirmed is False and (self.confirmations or 0)>0:
            raise ValueError('Unconfirmed transactions cannot have positive confirmations.')
        return self
    inputs: list[Input] = Field(default_factory=list, max_length=500)
    outputs: list[Output] = Field(min_length=1, max_length=500)
    fee_sats: int | None = Field(default=None, ge=0, le=2100000000000000, strict=True)
    vsize: int | None = Field(default=None, ge=1, le=4000000, strict=True)
    @field_validator('observed_at', 'block_time')
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError('Timestamps must include a timezone (for example Z).')
        return value
    @field_validator('outputs')
    @classmethod
    def unique_outputs(cls, value):
        if [o.index for o in value] != list(range(len(value))):
            raise ValueError('Output indexes must be consecutive, starting at zero.')
        if sum(o.value_sats for o in value) > 2100000000000000:
            raise ValueError('Total output value exceeds the Bitcoin supply bound.')
        return value

class Observation(BaseModel):
    txid: str = Field(pattern=r'^[0-9a-f]{64}$')
    observed_at: datetime
    peer_ip: str
    peer_port: int = Field(ge=1, le=65535)
    sensor: str = Field(min_length=1, max_length=100)
    @field_validator('peer_ip')
    @classmethod
    def ip_address(cls, value):
        import ipaddress
        return str(ipaddress.ip_address(value))
    @field_validator('observed_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Observation timestamp must include timezone.')
        return value
