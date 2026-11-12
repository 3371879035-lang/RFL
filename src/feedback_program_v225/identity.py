"""Filter semantics are part of identity even when all parameter shapes are reused."""
import hashlib
from feedback_program_v223.runtime import model_identity as base_model_identity
from feedback_program_v224.runtime import world_identity as base_world_identity

SEMANTICS = 'V225_NONINTERLEAVED_EPISODE_OBSERVED_FILTER'

def model_identity(model):
    return hashlib.sha256((SEMANTICS+'|'+base_model_identity(model)).encode()).hexdigest()

def world_identity(model):
    return hashlib.sha256((SEMANTICS+'|'+base_world_identity(model)).encode()).hexdigest()
