"""Canonical wire-before-seal boundary, independent of RFL/native execution."""
from dataclasses import fields, is_dataclass
from fractions import Fraction
from hashlib import sha256
import json


def encode(value):
    if isinstance(value, Fraction):
        return {'rational': [value.numerator, value.denominator]}
    if is_dataclass(value):
        return {f.name: encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, float):
        return {'binary64_hex': value.hex()}
    if isinstance(value, (tuple, list)):
        return [encode(x) for x in value]
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    return value


def seal(value):
    return sha256(json.dumps(encode(value), sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True).encode('ascii')).hexdigest()
