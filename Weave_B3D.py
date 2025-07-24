import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import os

from .commands.Weave_B3D import SerpentineCommandCreatedHandler # Importamos nuestro manejador

# Variables globales para mantener referencias a los elementos de la UI
# Esto es crucial para poder limpiar el Add-In correctamente al detenerlo.
handlers = []
cmd_defs = []
ui = None

# Ruta a las imagenes
imgs_path_relative = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources', 'imgs')

# ID único para nuestro comando y panel
PANEL_ID = 'B3D_Panel'
WORKSPACE_ID = 'FusionSolidEnvironment'

# Función que se ejecuta cuando se inicia el Add-In
def run(context):
    try:
        global ui
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Crear la definición del comando
        # Le decimos a Fusion que cuando se cree este comando, llame a nuestra clase SerpentineCommandCreatedHandler
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            'SerpentineWallSlicerCommand_ID', 
            'Crear cuerdas Serpenteantes', 
            f"""Crea multiples cuerpos nuevos en forma de cuerdas ondulados alrededor del cuerpo.\n
            <img src="{imgs_path_relative}/PhasedWavyWallSlicer.png" width="300"/>""", 
            'resources/icons/SerpentineWallSlicer'
        )
        on_command_created = SerpentineCommandCreatedHandler()
        cmd_def.commandCreated.add(on_command_created)
        
        # Guardar la definición y el manejador para poder limpiarlos después
        cmd_defs.append(cmd_def)
        handlers.append(on_command_created)

        # Añadir el botón a la barra de herramientas
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        toolbar_panel = workspace.toolbarPanels.itemById(PANEL_ID)
        if not toolbar_panel:
            toolbar_panel = workspace.toolbarPanels.add(PANEL_ID, 'Boceto 3D')
            
        button_control = toolbar_panel.controls.addCommand(cmd_def)
        button_control.isPromoted = False
        button_control.isVisible = True

    except:
        if ui:
            ui.messageBox('Error al iniciar el Add-In:\n{}'.format(traceback.format_exc()))

# Función que se ejecuta cuando se detiene el Add-In
def stop(context):
    try:
        global ui
        if ui:
            # Limpiar la UI
            workspace = ui.workspaces.itemById(WORKSPACE_ID)
            toolbar_panel = workspace.toolbarPanels.itemById(PANEL_ID)
            if toolbar_panel:
                button_control = toolbar_panel.controls.itemById('SerpentineWallSlicerCommand_ID')
                if button_control:
                    button_control.deleteMe()
                # Si el panel está vacío después de borrar el botón, lo eliminamos
                if toolbar_panel.controls.count == 0:
                    toolbar_panel.deleteMe()

            # Limpiar la definición del comando
            cmd_def = ui.commandDefinitions.itemById('SerpentineWallSlicerCommand_ID')
            if cmd_def:
                cmd_def.deleteMe()
    except:
        if ui:
            ui.messageBox('Error al detener el Add-In:\n{}'.format(traceback.format_exc()))


