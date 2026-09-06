"""Core components of the adaptive DP-KSA edge/cloud framework.

The package exposes the privacy mechanism, adaptive scheduler, dataset
loader, local inference engine, cloud adapter, and telemetry adapter.

External dependencies are imported by the individual adapters; importing the
package itself only defines the public version and re-exports.
"""

from .dataset import DatasetLoader, DocumentoBenchmark
from .engine import (
    LocalNeuralEngine,
    ModelDownloadError,
    OutputInferenza,
    assicura_presenza_modello,
)
from .model_config import DEFAULT_LOCAL_MODEL_CONFIG, LocalModelConfig
from .privacy import DP_KSA_Filter, DPBudgetExhaustedError, EsitoDP, probabilita_passaggio_ptr
from .scheduler import AdaptiveScheduler, DecisioneScheduler, PrivacyBudgetExhaustedError

__all__ = [
    "AdaptiveScheduler",
    "DEFAULT_LOCAL_MODEL_CONFIG",
    "DPBudgetExhaustedError",
    "DP_KSA_Filter",
    "DatasetLoader",
    "DecisioneScheduler",
    "DocumentoBenchmark",
    "EsitoDP",
    "LocalNeuralEngine",
    "LocalModelConfig",
    "ModelDownloadError",
    "OutputInferenza",
    "PrivacyBudgetExhaustedError",
    "probabilita_passaggio_ptr",
    "assicura_presenza_modello",
]

__version__ = "0.1.0"
