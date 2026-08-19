"""
Virtual 5G GSM Core Network Engine.
Provides a mock core network cell management and signal load simulation engine.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class VirtualCell:
    """
    Represents a virtual 5G base station (gNodeB / Cell) inside the Virtual Core.
    """

    def __init__(
        self,
        cell_id: Optional[str] = None,
        mcc: int = 984,
        mnc: int = 79,
        rsrp: float = -50.0,
        rtt: float = 20.0,
        users: int = 0,
    ):
        """
        Initializes a new Virtual Cell.

        Args:
            cell_id (Optional[str]): Unique cell ID. If not provided, a random UUID will be generated.
            mcc (int): Mobile Country Code (default: 984).
            mnc (int): Mobile Network Code (default: 79).
            rsrp (float): Reference Signal Received Power in dBm (default: -50.0 dBm).
            rtt (float): Round-Trip-Time latency in milliseconds (default: 20.0 ms).
            users (int): Current active connected user count (default: 0).
        """
        self.id: str = cell_id or str(uuid.uuid4())
        self.mcc: int = mcc
        self.mnc: int = mnc
        self.rsrp: float = rsrp
        self.rtt: float = rtt
        self.users: int = users
        self.last_update: float = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns a dictionary representation of the cell, including a last_update timestamp.
        """
        return {
            "id": self.id,
            "mcc": self.mcc,
            "mnc": self.mnc,
            "rsrp": self.rsrp,
            "rtt": self.rtt,
            "users": self.users,
            "last_update": self.last_update,
        }

    def update_timestamp(self) -> None:
        """Updates the last_update timestamp to the current Unix epoch."""
        self.last_update = time.time()


# Global dictionary holding active virtual cell records.
# Keys are cell IDs (str), values are VirtualCell instances.
VIRTUAL_CELLS: Dict[str, VirtualCell] = {}


def create_cell(
    mcc: int = 984,
    mnc: int = 79,
    rsrp: float = -50.0,
    rtt: float = 20.0,
    users: int = 0,
    cell_id: Optional[str] = None,
) -> VirtualCell:
    """
    Creates a new virtual 5G cell and registers it in the global registry.
    """
    cell = VirtualCell(cell_id=cell_id, mcc=mcc, mnc=mnc, rsrp=rsrp, rtt=rtt, users=users)
    VIRTUAL_CELLS[cell.id] = cell
    logger.info(f"Created virtual 5G cell: {cell.id} (MCC: {mcc}, MNC: {mnc})")
    return cell


def get_cell(cell_id: str) -> Optional[VirtualCell]:
    """
    Retrieves a registered virtual cell by its ID.
    """
    return VIRTUAL_CELLS.get(cell_id)


def update_cell(cell_id: str, **kwargs: Any) -> Optional[VirtualCell]:
    """
    Updates designated fields of an existing virtual cell.
    """
    cell = VIRTUAL_CELLS.get(cell_id)
    if not cell:
        logger.warning(f"Failed to update cell: {cell_id} not found.")
        return None

    for key, value in kwargs.items():
        if hasattr(cell, key):
            setattr(cell, key, value)
        else:
            logger.warning(f"VirtualCell has no attribute '{key}' and cannot be updated.")

    cell.update_timestamp()
    logger.debug(f"Updated virtual cell: {cell_id}")
    return cell


def delete_cell(cell_id: str) -> bool:
    """
    Removes a virtual cell from the global registry.
    """
    if cell_id in VIRTUAL_CELLS:
        del VIRTUAL_CELLS[cell_id]
        logger.info(f"Deleted virtual cell: {cell_id}")
        return True
    logger.warning(f"Failed to delete cell: {cell_id} not found.")
    return False


def list_cells() -> List[VirtualCell]:
    """
    Returns a list of all globally registered virtual cells.
    """
    return list(VIRTUAL_CELLS.values())


def simulate_load(cell_id: str, users: int) -> Optional[VirtualCell]:
    """
    Simulates high user load on a given cell by updating the user count and dynamically
    degrading signal strength (RSRP) and increasing network latency (RTT).

    Load physics:
    - Base RSRP: -50 dBm (Excellent signal). Degrades by 0.15 dBm per active user.
    - Base RTT: 20 ms (Ultra-fast). Increases by 0.5 ms per active user.
    """
    cell = VIRTUAL_CELLS.get(cell_id)
    if not cell:
        logger.warning(f"Failed to simulate load: cell {cell_id} not found.")
        return None

    # Force user counts to be non-negative
    cell.users = max(0, users)

    # Physics modeling constants
    base_rsrp = -50.0  # dBm
    base_rtt = 20.0    # ms

    # Linear degradation factors
    rtt_increment_per_user = 0.5
    rsrp_decrement_per_user = 0.15

    # Compute values and enforce physical real-world boundaries
    # RSRP usually spans from -50 dBm (perfect) down to -140 dBm (dead zone)
    cell.rsrp = max(-140.0, base_rsrp - (cell.users * rsrp_decrement_per_user))
    # Latency goes up but caps at standard timeout thresholds (e.g., 1000ms)
    cell.rtt = min(1000.0, base_rtt + (cell.users * rtt_increment_per_user))

    cell.update_timestamp()
    logger.info(
        f"Simulated load on cell {cell_id}: users={cell.users}, "
        f"RSRP={cell.rsrp:.2f}dBm, RTT={cell.rtt:.1f}ms"
    )
    return cell
