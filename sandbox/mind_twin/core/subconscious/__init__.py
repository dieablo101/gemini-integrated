"""
Subconscious incubation & apophenic thought package.
Dual-process architecture: System 1 associative crunching gated by novelty detection
and verified by reality probes.
"""

from sandbox.mind_twin.core.subconscious.novelty_detector import (
    NoveltyDetector,
    NoveltyEvaluation,
)
from sandbox.mind_twin.core.subconscious.conclusive_probe import (
    ConclusiveRealityProbe,
    RealityProbeResult,
)
from sandbox.mind_twin.core.subconscious.epiphany_channel import (
    EpiphanyChannel,
    EpiphanyPacket,
)
from sandbox.mind_twin.core.subconscious.subconscious_worker import (
    SubconsciousWorker,
    IncubationCluster,
)

__all__ = [
    "NoveltyDetector",
    "NoveltyEvaluation",
    "ConclusiveRealityProbe",
    "RealityProbeResult",
    "EpiphanyChannel",
    "EpiphanyPacket",
    "SubconsciousWorker",
    "IncubationCluster",
]
