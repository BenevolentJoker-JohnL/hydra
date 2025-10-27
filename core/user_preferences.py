"""
User Preferences Manager for Hydra

Persists user settings between sessions including routing modes,
UI preferences, and other configuration options.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class RoutingPreferences:
    """Routing mode preferences"""
    mode: Optional[str] = None  # "fast", "reliable", "async", or None for auto
    priority: int = 5
    min_success_rate: float = 0.95
    prefer_cpu: bool = False


@dataclass
class UIPreferences:
    """UI display preferences"""
    use_context: bool = True
    use_tools: bool = True
    use_reasoning: bool = False
    create_artifacts: bool = True
    terminal_height: int = 400


@dataclass
class UserPreferences:
    """Complete user preferences"""
    routing: RoutingPreferences
    ui: UIPreferences
    last_updated: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()


class PreferencesManager:
    """
    Manages user preferences with automatic persistence.

    Preferences are stored in ~/.hydra/user_preferences.json
    """

    def __init__(self, preferences_dir: Optional[str] = None):
        """
        Initialize preferences manager.

        Args:
            preferences_dir: Custom preferences directory (default: ~/.hydra)
        """
        if preferences_dir:
            self.preferences_dir = Path(preferences_dir)
        else:
            self.preferences_dir = Path.home() / ".hydra"

        self.preferences_file = self.preferences_dir / "user_preferences.json"

        # Ensure directory exists
        self.preferences_dir.mkdir(parents=True, exist_ok=True)

        # Load or create default preferences
        self.preferences = self._load_preferences()

    def _load_preferences(self) -> UserPreferences:
        """Load preferences from file or create defaults"""
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r') as f:
                    data = json.load(f)

                # Convert nested dicts to dataclasses
                routing = RoutingPreferences(**data.get('routing', {}))
                ui = UIPreferences(**data.get('ui', {}))

                prefs = UserPreferences(
                    routing=routing,
                    ui=ui,
                    last_updated=data.get('last_updated', '')
                )

                logger.info(f"📂 Loaded user preferences from {self.preferences_file}")
                return prefs

            except Exception as e:
                logger.warning(f"Failed to load preferences: {e}. Using defaults.")
                return self._create_default_preferences()
        else:
            logger.info("Creating default user preferences")
            prefs = self._create_default_preferences()
            self._save_preferences(prefs)
            return prefs

    def _create_default_preferences(self) -> UserPreferences:
        """Create default preferences"""
        return UserPreferences(
            routing=RoutingPreferences(),
            ui=UIPreferences()
        )

    def _save_preferences(self, prefs: UserPreferences):
        """Save preferences to file"""
        try:
            # Update timestamp
            prefs.last_updated = datetime.now().isoformat()

            # Convert to dict
            data = {
                'routing': asdict(prefs.routing),
                'ui': asdict(prefs.ui),
                'last_updated': prefs.last_updated
            }

            # Write to file
            with open(self.preferences_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"💾 Saved preferences to {self.preferences_file}")

        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")

    def get_routing_preferences(self) -> RoutingPreferences:
        """Get routing preferences"""
        return self.preferences.routing

    def update_routing_preferences(
        self,
        mode: Optional[str] = None,
        priority: Optional[int] = None,
        min_success_rate: Optional[float] = None,
        prefer_cpu: Optional[bool] = None
    ):
        """
        Update routing preferences.

        Args:
            mode: Routing mode ("fast", "reliable", "async", or None)
            priority: Priority level 1-10
            min_success_rate: Minimum success rate 0.0-1.0
            prefer_cpu: Prefer CPU for async mode
        """
        if mode is not None:
            self.preferences.routing.mode = mode
        if priority is not None:
            self.preferences.routing.priority = priority
        if min_success_rate is not None:
            self.preferences.routing.min_success_rate = min_success_rate
        if prefer_cpu is not None:
            self.preferences.routing.prefer_cpu = prefer_cpu

        self._save_preferences(self.preferences)

    def get_ui_preferences(self) -> UIPreferences:
        """Get UI preferences"""
        return self.preferences.ui

    def update_ui_preferences(
        self,
        use_context: Optional[bool] = None,
        use_tools: Optional[bool] = None,
        use_reasoning: Optional[bool] = None,
        create_artifacts: Optional[bool] = None,
        terminal_height: Optional[int] = None
    ):
        """
        Update UI preferences.

        Args:
            use_context: Use project context
            use_tools: Enable tool usage
            use_reasoning: Use reasoning mode
            create_artifacts: Create artifacts
            terminal_height: Terminal panel height
        """
        if use_context is not None:
            self.preferences.ui.use_context = use_context
        if use_tools is not None:
            self.preferences.ui.use_tools = use_tools
        if use_reasoning is not None:
            self.preferences.ui.use_reasoning = use_reasoning
        if create_artifacts is not None:
            self.preferences.ui.create_artifacts = create_artifacts
        if terminal_height is not None:
            self.preferences.ui.terminal_height = terminal_height

        self._save_preferences(self.preferences)

    def reset_to_defaults(self):
        """Reset all preferences to defaults"""
        self.preferences = self._create_default_preferences()
        self._save_preferences(self.preferences)
        logger.info("🔄 Reset preferences to defaults")

    def get_preferences_file_path(self) -> str:
        """Get the path to the preferences file"""
        return str(self.preferences_file)

    def export_preferences(self) -> Dict[str, Any]:
        """Export preferences as dictionary"""
        return {
            'routing': asdict(self.preferences.routing),
            'ui': asdict(self.preferences.ui),
            'last_updated': self.preferences.last_updated
        }


# Global instance
_preferences_manager: Optional[PreferencesManager] = None


def get_preferences_manager() -> PreferencesManager:
    """Get or create global preferences manager"""
    global _preferences_manager
    if _preferences_manager is None:
        _preferences_manager = PreferencesManager()
    return _preferences_manager
