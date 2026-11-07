"""Optional host-side model assistance."""

from agentsync.providers.advice import (
    AdviceRequest,
    AdviceResult,
    SuggestedHandoff,
    SuggestedRole,
    SuggestedTask,
    get_advice,
    prepare_decomposition,
    prepare_handoff,
    prepare_role_suggestions,
)
from agentsync.providers.base import (
    MockProvider,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    OwnerAuthorization,
    ProviderError,
    ProviderKind,
    ProviderUsage,
)
from agentsync.providers.http import HTTPProvider, ProviderProfile

__all__ = [
    "AdviceRequest",
    "AdviceResult",
    "HTTPProvider",
    "MockProvider",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "OwnerAuthorization",
    "ProviderError",
    "ProviderKind",
    "ProviderProfile",
    "ProviderUsage",
    "SuggestedHandoff",
    "SuggestedRole",
    "SuggestedTask",
    "get_advice",
    "prepare_decomposition",
    "prepare_handoff",
    "prepare_role_suggestions",
]
