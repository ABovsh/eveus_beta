"""Helper functions for Eveus integration."""
from datetime import datetime
from typing import Optional

def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable string."""
    try:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}m")
            
        return " ".join(parts)
    except (TypeError, ValueError):
        return "0m"

def format_system_time(timestamp: int) -> str:
    """Format system timestamp to time string."""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%H:%M")
    except (TypeError, ValueError):
        return "unknown"

def calculate_soc_kwh(
    initial_soc: float,
    max_capacity: float,
    energy_charged: float,
    correction: float
) -> Optional[float]:
    """Calculate state of charge in kWh."""
    try:
        if initial_soc < 0 or initial_soc > 100 or max_capacity <= 0:
            return None
            
        initial_kwh = (initial_soc / 100) * max_capacity
        efficiency = (1 - correction / 100)
        charged_kwh = energy_charged * efficiency
        total_kwh = initial_kwh + charged_kwh
        
        return round(max(0, min(total_kwh, max_capacity)), 2)
    except (TypeError, ValueError):
        return None
