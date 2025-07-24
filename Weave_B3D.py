# Copyright (C) 2025, Boceto3D
# All rights reserved.
#
# This software is provided "as is" without warranty of any kind, either expressed or
# implied, including but not limited to the implied warranties of merchantability and

"""
This is the main entry point for the "Weave B3D" Add-In for Autodesk Fusion 360.

This script initializes the Add-In, creates a new command button in the UI,
and handles the cleanup process when the Add-In is stopped.
"""

import adsk.core
import adsk.fusion
import traceback
import os

# Import the handler for the command creation event.
from .commands.Weave_B3D import SerpentineCommandCreatedHandler

# --- Global Variables ---
# It's crucial to maintain references to UI elements and handlers to properly
# clean up the Add-In when it's stopped.
_handlers = []
_cmd_defs = []
_ui = None

# --- Constants ---
# Define constants for IDs and paths to avoid magic strings.

# Get the absolute path to the 'resources' directory.
# This makes the Add-In portable and independent of the installation location.
RESOURCES_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')

# Unique ID for the custom panel where the button will be added.
PANEL_ID = 'B3D_Panel'
# ID of the workspace where the panel will be created.
WORKSPACE_ID = 'FusionSolidEnvironment'
# Unique ID for the command itself.
COMMAND_ID = 'SerpentineWeaveB3DCommand'


def run(context: dict) -> None:
    """
    Executes when the Add-In is started.

    This function sets up the user interface by creating a command definition
    and adding a button to the SOLID workspace toolbar.

    Args:
        context: A dictionary provided by Fusion 360 that contains information
                 about the Add-In's execution context.
    """
    global _ui
    try:
        app = adsk.core.Application.get()
        _ui = app.userInterface

        # --- Command Definition ---
        # Create the command definition, which is the blueprint for the command.
        # When this command is created, Fusion will call our SerpentineCommandCreatedHandler class.
        tooltip_image = os.path.join(RESOURCES_PATH, 'imgs', 'PhasedWavyWallSlicer.png')
        command_tooltip = f"""Crea multiples cuerpos nuevos en forma de cuerdas ondulados alrededor del cuerpo.\n
                            <br><img src="{tooltip_image}" width="300"/>"""

        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID,
            'Crear Cuerdas Serpenteantes',
            command_tooltip,
            os.path.join(RESOURCES_PATH, 'icons', 'SerpentineWallSlicer')
        )

        # --- Command Created Event Handler ---
        # Connect the handler to the command's 'commandCreated' event.
        on_command_created = SerpentineCommandCreatedHandler()
        cmd_def.commandCreated.add(on_command_created)

        # Store the definition and handler in global lists for cleanup during stop.
        _cmd_defs.append(cmd_def)
        _handlers.append(on_command_created)

        # --- UI Panel and Button ---
        # Add the command button to the specified toolbar panel.
        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        toolbar_panel = workspace.toolbarPanels.itemById(PANEL_ID)
        if not toolbar_panel:
            # If the panel doesn't exist, create it.
            toolbar_panel = workspace.toolbarPanels.add(PANEL_ID, 'Boceto 3D')

        button_control = toolbar_panel.controls.addCommand(cmd_def)
        # Ensure the button is visible and not promoted by default.
        button_control.isPromoted = False
        button_control.isVisible = True

    except Exception:
        if _ui:
            _ui.messageBox('Error al iniciar el Add-In:\n{}'.format(traceback.format_exc()))


def stop(context: dict) -> None:
    """
    Executes when the Add-In is stopped.

    This function cleans up all UI elements (button, panel) and command
    definitions created by the Add-In to ensure a clean exit.

    Args:
        context: A dictionary provided by Fusion 360 that contains information
                 about the Add-In's execution context.
    """
    global _ui
    try:
        if _ui:
            # --- Clean up UI Elements ---
            workspace = _ui.workspaces.itemById(WORKSPACE_ID)
            toolbar_panel = workspace.toolbarPanels.itemById(PANEL_ID)
            if toolbar_panel:
                button_control = toolbar_panel.controls.itemById(COMMAND_ID)
                if button_control:
                    button_control.deleteMe()

                # If the panel is empty after deleting the button, remove the panel itself.
                if toolbar_panel.controls.count == 0:
                    toolbar_panel.deleteMe()

            # --- Clean up Command Definition ---
            cmd_def = _ui.commandDefinitions.itemById(COMMAND_ID)
            if cmd_def:
                cmd_def.deleteMe()

    except Exception:
        if _ui:
            _ui.messageBox('Error al detener el Add-In:\n{}'.format(traceback.format_exc()))
