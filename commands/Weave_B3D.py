#------------------------------------------------------------------------------
#
# SCRIPT OVERVIEW (CPU Version):
#
# This Autodesk Fusion 360 add-in generates a serpentine or wavy pattern on the
# surface of a selected B-Rep body using only the CPU.
#
# How it works:
# 1.  UI Setup: A command dialog is created with various inputs for the user,
#     such as the body to process, wall thickness, wave amplitude, frequency, etc.
#
# 2.  Geometry Slicing & Data Extraction (Phase 1): The script slices the
#     selected body into horizontal layers. For each slice, it projects the
#     cross-section, orders its curves, and samples points and their normal
#     vectors. This geometric data is collected for all layers.
#
# 3.  Calculation & Model Reconstruction (Phase 2): The script iterates through
#     the collected data for each layer.
#     a. CPU Calculation: For each layer, it calculates the new wavy point
#        positions directly within this script using standard math functions.
#     b. Reconstruction: It then immediately reconstructs the model in Fusion 360,
#        layer by layer, by creating a sketch, drawing a spline from the
#        modified points, offsetting it, and extruding the profile.
#
# 4.  Error Handling & UX: A progress dialog keeps the user informed. The script
#     includes robust error handling for geometric operations.
#
#------------------------------------------------------------------------------

import adsk.core, adsk.fusion, adsk.cam
import os
import traceback
import time
import math

# Global list to keep command handlers in scope.
handlers = []

# --- Path Setup ---
# Define paths for the add-in directory.
addin_path = os.path.dirname(os.path.realpath(__file__))

# --- Input Validation Handler ---
class SerpentineCommandValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.ValidateInputsEventArgs):
        """
        Validates user inputs and provides real-time feedback.
        """
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            inputs = args.inputs
            frequency_input = inputs.itemById('wave_frequency')
            if frequency_input and frequency_input.value > 70:
                ui.statusMessage = 'Advertencia de rendimiento: Un alto número de ondas aumenta el tiempo de cálculo.'
            else:
                ui.statusMessage = ''
        except:
            if adsk.core.Application.get().userInterface:
                adsk.core.Application.get().userInterface.messageBox('Error en ValidateInputs: {}'.format(traceback.format_exc()))

# --- Command Creation Handler ---
class SerpentineCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        """
        Sets up the command dialog, including all inputs and event connections.
        """
        try:
            # Get the command object from the event arguments.
            cmd = args.command
            inputs = cmd.commandInputs
            
            # Set the help file for the command.
            cmd.helpFile = 'resources/Weave_B3D_help.html'

            # --- Connect Event Handlers ---
            # Connect the 'execute' event to our execution handler.
            on_execute = SerpentineCommandExecuteHandler()
            cmd.execute.add(on_execute)

            # Connect the 'validateInputs' event to our validation handler.
            on_validate_inputs = SerpentineCommandValidateInputsHandler()
            cmd.validateInputs.add(on_validate_inputs)
            
            # Store handlers in the global list to prevent them from being garbage collected.
            handlers.append(on_execute)
            handlers.append(on_validate_inputs)

            # --- Define Command Inputs ---
            app = adsk.core.Application.get()
            design = app.activeProduct
            unitsMgr = design.unitsManager

            # Input for selecting the target body.
            body_selection_input = inputs.addSelectionInput('body_selection', 'Seleccionar cuerpo', 'Por favor, seleccione el cuerpo a procesar.')
            body_selection_input.addSelectionFilter('Bodies')
            body_selection_input.setSelectionLimits(1, 1)

            # Value inputs for geometric parameters.
            inputs.addIntegerSpinnerCommandInput('wave_frequency', 'Ondas totales', 1, 200, 1, 40)
            inputs.addFloatSpinnerCommandInput('wall_thickness', 'Grosor de la cuerda', unitsMgr.defaultLengthUnits, 0.0, 3.2, 0.01, 0.8)
            inputs.addFloatSpinnerCommandInput('layer_height', 'Altura de la cuerda', unitsMgr.defaultLengthUnits, 0.0, 100.0, 0.01, 0.8)
            inputs.addFloatSpinnerCommandInput('wave_amplitude', 'Amplitud máxima de onda', unitsMgr.defaultLengthUnits, 0.0, 10.0, 0.01, 2.0)
            inputs.addIntegerSpinnerCommandInput('phase_shift', 'Desfase de onda entre cuerdas (0-360)', 0, 360, 1, 180)
            inputs.addFloatSpinnerCommandInput('general_offset', 'Desfase interno/externo (-2mm/+2mm)', unitsMgr.defaultLengthUnits, -2.0, 2.0, 0.01, 0.0)
            inputs.addBoolValueInput('generate_pattern_only', 'Generar solo el patrón', True, '', False)

        except:
            adsk.core.Application.get().userInterface.messageBox('Error en CommandCreated: {}'.format(traceback.format_exc()))

# --- Command Execution Handler ---
# This class is executed when the user clicks "OK" in the command dialog.
class SerpentineCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args: adsk.core.CommandEventArgs):
        """
        Main execution logic for the add-in.
        """
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)
            
            # --- Gather Input Values ---
            inputs = args.command.commandInputs
            input_values = {}
            for ipt in inputs:
                if ipt.objectType == adsk.core.SelectionCommandInput.classType():
                    selections = [ipt.selection(i).entity for i in range(ipt.selectionCount)]
                    input_values[ipt.id] = selections
                else:
                    input_values[ipt.id] = ipt.value

            selected_body = adsk.fusion.BRepBody.cast(input_values['body_selection'][0])
            wall_thickness = input_values['wall_thickness']
            layer_height = input_values['layer_height']
            wave_amplitude = input_values['wave_amplitude']
            wave_frequency = input_values['wave_frequency']
            phase_shift = input_values['phase_shift']
            generate_pattern_only = input_values['generate_pattern_only']
            general_offset_value = input_values['general_offset']
            wave_sharpness = 1

            if not selected_body: return

            # --- Setup Fusion 360 Objects ---
            root_comp = design.rootComponent
            sketches = root_comp.sketches
            construction_planes = root_comp.constructionPlanes
            extrudes = root_comp.features.extrudeFeatures

            bbox = selected_body.boundingBox
            z_min = bbox.minPoint.z
            z_max = bbox.maxPoint.z
            
            # --- Calculate Number of Slices ---
            total_slices = 0
            max_slices = math.floor((z_max - z_min) / layer_height)
            if generate_pattern_only:
                if phase_shift == 0 or phase_shift == 360:
                    total_slices = 1
                elif 0 < phase_shift < 360:
                    pattern_slices = int(360 / phase_shift)
                    total_slices = min(pattern_slices, max_slices)
            else:
                total_slices = max_slices

            # --- PHASE 1: Geometry Extraction ---
            progress_dialog = ui.createProgressDialog()
            progress_dialog.show('Procesando capas', '', 0, total_slices)

            estimated_total_time = 0
            time_per_layer = 0
            extrusion_error_count = 0
            max_offset_iterations = 100

            current_z = z_min
            slice_count = 0
            while slice_count < total_slices:
                
                if progress_dialog.wasCancelled: break

                if estimated_total_time > 0:
                    remaining_time = max(0, estimated_total_time - (time_per_layer * slice_count))
                    minutes, seconds = divmod(int(remaining_time), 60)
                    progress_dialog.message = f"Construyendo cuerda {slice_count + 1} de {total_slices}...\n(Tiempo restante: {minutes}m {seconds}s)"
                else:
                    progress_dialog.message = f"Construyendo cuerda {slice_count + 1} de {total_slices}..."

                progress_dialog.progressValue = slice_count
                adsk.doEvents()

                if slice_count == 0: layer_start_time = time.time()

                # Create a construction plane for the current slice.
                slice_plane_input = construction_planes.createInput()
                offset_value = adsk.core.ValueInput.createByReal(current_z)
                slice_plane_input.setByOffset(root_comp.xYConstructionPlane, offset_value)
                slice_plane = construction_planes.add(slice_plane_input)
                
                # Create a sketch and project the body's cut edges onto it.
                slice_sketch = sketches.add(slice_plane)
                slice_sketch.projectCutEdges(selected_body)
                
                if slice_sketch.profiles.count > 0:
                    # Find the main profile (the one with the largest area).
                    main_profile = max(slice_sketch.profiles, key=lambda p: p.areaProperties().area)
                    max_perimeter = main_profile.areaProperties().perimeter
                    
                    # Dynamically adjust amplitude to prevent self-intersections.
                    # Golden rule: amplitude + (thickness/2) <= (wavelength/2)
                    wave_length_helper = max_perimeter / wave_frequency
                    max_allowed_amplitude = ((wave_length_helper / 2) - (wall_thickness)) * 0.75 # 75% for safety margin
                    final_amplitude = min(wave_amplitude, max_allowed_amplitude)

                    # Adjust the general offset based on thickness and final amplitude.
                    general_offset = general_offset_value + 0.022 - ((wall_thickness / 2) + final_amplitude)

                    if main_profile:
                        # Apply a general offset to the entire profile.
                        curves_to_offset = adsk.core.ObjectCollection.create()
                        for curve in main_profile.profileLoops.item(0).profileCurves:
                            curves_to_offset.add(curve.sketchEntity)

                        profile_bbox = main_profile.boundingBox
                        offset_direction_point = adsk.core.Point3D.create(
                            (profile_bbox.minPoint.x + profile_bbox.maxPoint.x) / 2,
                            (profile_bbox.minPoint.y + profile_bbox.maxPoint.y) / 2,
                            (profile_bbox.minPoint.z + profile_bbox.maxPoint.z) / 2
                        )
                        offset_slice = slice_sketch.offset(curves_to_offset, offset_direction_point, -general_offset)

                        # Delete the original projected curves.
                        for curve in curves_to_offset:
                            if curve.isValid: curve.deleteMe()

                        # Re-find the main profile, which is now the offset one.
                        if slice_sketch.profiles.count > 0:
                            main_profile = max(slice_sketch.profiles, key=lambda p: p.areaProperties().area)

                            if main_profile:
                                # Order curves and extract data.
                                ordered_curves_data = self.get_ordered_curves(main_profile)
                                if ordered_curves_data:
                                    layer_data = self.extract_curve_data(ordered_curves_data, slice_sketch, current_z, wave_frequency, final_amplitude)
                                    processed_points = self.calculate_wave_points_cpu(slice_count, layer_data, wave_frequency, phase_shift, wave_sharpness)
                                    
                                    points = adsk.core.ObjectCollection.create()
                                    for p_data in processed_points:
                                        points.add(adsk.core.Point3D.create(p_data[0], p_data[1], p_data[2]))

                                    # Clean up temporary geometry.
                                    for curve in offset_slice:
                                        if curve.isValid: curve.deleteMe()

                                    if points.count > 1:
                                        center_spline = slice_sketch.sketchCurves.sketchFittedSplines.add(points)
                                        center_spline.isClosed = True
                                        
                                        if slice_sketch.profiles.count > 0:
                                            # (The robust offset and extrusion logic remains the same)
                                            wavy_profile = slice_sketch.profiles.item(0)
                                            center_curves_collection = adsk.core.ObjectCollection.create()
                                            for c in wavy_profile.profileLoops.item(0).profileCurves:
                                                center_curves_collection.add(c.sketchEntity)

                                            bbox = wavy_profile.boundingBox
                                            direction_point = adsk.core.Point3D.create(
                                                (bbox.minPoint.x + bbox.maxPoint.x) / 2,
                                                (bbox.minPoint.y + bbox.maxPoint.y) / 2,
                                                (bbox.minPoint.z + bbox.maxPoint.z) / 2
                                            )
                                            
                                            # ... [Robust offset and extrusion logic as before] ...
                                            # Internal offset
                                            dialogMessage = progress_dialog.message
                                            intern_increase = 0.0
                                            extern_increase = 0.0
                                            intern_iteration = 0
                                            extern_iteration = 0
                                            intern_curves = None
                                            extern_curves = None
                                            one_error = False

                                            while not one_error:
                                                half_wall_thickness = wall_thickness / 2
                                                while intern_iteration < max_offset_iterations:
                                                    intern_iteration += 1
                                                    intern_increase += 0.0001
                                                    try:
                                                        intern_curves = slice_sketch.offset(center_curves_collection, direction_point, half_wall_thickness)
                                                        all_profiles = [p for p in slice_sketch.profiles if p.isValid and p.areaProperties().area > 0.01]
                                                        if len(all_profiles) == 2 and all_profiles[0].areaProperties().area < all_profiles[1].areaProperties().area: break
                                                        else:
                                                            for curve in intern_curves: curve.deleteMe()
                                                            half_wall_thickness += intern_increase if intern_iteration % 2 else -intern_increase
                                                            progress_dialog.message = f"{dialogMessage}\nIntento: {intern_iteration}"
                                                    except:
                                                        try:
                                                            for curve in intern_curves: curve.deleteMe()
                                                        except: pass
                                                        half_wall_thickness += intern_increase if intern_iteration % 2 else -intern_increase
                                                        progress_dialog.message = f"{dialogMessage}\nIntento: {intern_iteration}"
                                                
                                                # External offset
                                                half_wall_thickness = wall_thickness / 2
                                                while extern_iteration < max_offset_iterations:
                                                    extern_iteration += 1
                                                    extern_increase += 0.0001
                                                    try:
                                                        extern_curves = slice_sketch.offset(center_curves_collection, direction_point, -half_wall_thickness)
                                                        all_profiles = [p for p in slice_sketch.profiles if p.isValid and p.areaProperties().area > 0.01]
                                                        if len(all_profiles) == 3 and all_profiles[0].areaProperties().area < all_profiles[2].areaProperties().area: break
                                                        else:
                                                            for curve in extern_curves: curve.deleteMe()
                                                            half_wall_thickness += extern_increase if extern_iteration % 2 else -extern_increase
                                                            progress_dialog.message = f"{dialogMessage}\nIntento: {extern_iteration}"
                                                    except:
                                                        try:
                                                            for curve in extern_curves: curve.deleteMe()
                                                        except: pass
                                                        half_wall_thickness += extern_increase if extern_iteration % 2 else -extern_increase
                                                        progress_dialog.message = f"{dialogMessage}\nIntento: {extern_iteration}"
                                                    
                                                if intern_iteration == max_offset_iterations or extern_iteration == max_offset_iterations:
                                                    one_error = True
                                                    extrusion_error_count += 1
                                                
                                                if not one_error:
                                                    # --- Extrude the Wall Profile ---
                                                    all_profiles = [p for p in slice_sketch.profiles if p.isValid and p.areaProperties().area > 0.01]
                                                    if len(all_profiles) != 3: continue
                                                    
                                                    try:
                                                        all_profiles.sort(key=lambda p: p.areaProperties().area, reverse=True)
                                                        if all_profiles:
                                                            profiles_to_extrude = adsk.core.ObjectCollection.create()
                                                            profiles_to_extrude.add(all_profiles[1])
                                                            profiles_to_extrude.add(all_profiles[2])
                                                            extrude_input = extrudes.createInput(profiles_to_extrude, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                                                            distance = adsk.core.ValueInput.createByReal(layer_height)
                                                            extrude_input.setDistanceExtent(False, distance)
                                                            extrude_retValue = extrudes.add(extrude_input)
                                                            # For micro volumes
                                                            if extrude_retValue.bodies.count > 0:
                                                                extrude_volumen = extrude_retValue.bodies.item(0).physicalProperties.volume
                                                                if extrude_volumen < 1e-3:
                                                                    # Delete extrudes and sketch
                                                                    extrude_retValue.deleteMe()
                                                                    for curve in intern_curves: curve.deleteMe()
                                                                    for curve in extern_curves: curve.deleteMe()
                                                                else:
                                                                    break # All good
                                                    except:
                                                        extrusion_error_count += 1
                                                        break
                                    if slice_count == 0:
                                        layer_end_time = time.time()
                                        time_per_layer = layer_end_time - layer_start_time
                                        estimated_total_time = time_per_layer * total_slices
                
                current_z += layer_height
                slice_count += 1
                
                #if slice_count == 17:
                if slice_count == total_slices and generate_pattern_only:
                    break
            
            # --- Finalization ---
            progress_dialog.hide()
            if extrusion_error_count == 0:
                ui.messageBox("Proceso completado exitosamente.")
            else:
                ui.messageBox(f"Advertencia: El proceso se completó, pero no se pudieron crear {extrusion_error_count} capa(s) debido a errores geométricos.")
        except:
            if adsk.core.Application.get().userInterface:
                adsk.core.Application.get().userInterface.messageBox('Error en Execute: {}'.format(traceback.format_exc()))
            if 'progress_dialog' in locals() and progress_dialog:
                progress_dialog.hide()


    def calculate_wave_points_cpu(self, slice_count, layer_data, wave_frequency, phase_shift_degrees, wave_sharpness):
        """
        Calculates the new positions for points on a layer to form a sine wave.
        This version runs entirely on the CPU using the standard 'math' module.

        Args:
            layer_data (dict): Contains all geometry data for a single layer.
            wave_frequency (float): The total number of waves around the perimeter.
            phase_shift_degrees (float): The phase shift for this layer in degrees.

        Returns:
            list[list[float]]: A list of new point coordinates [x, y, z].
        """
        processed_points = []
        phase_shift_in_radians = phase_shift_degrees * (math.pi / 180.0)
        layer_phase_offset = slice_count * phase_shift_in_radians
        total_perimeter = layer_data["total_perimeter"]
        final_amplitude = layer_data["final_amplitude"]

        for item in layer_data["geometry"]:
            perimeter_pos = item["perimeter_pos"]
            
            # Calculate the sine wave phase for the current point
            phase = (perimeter_pos / total_perimeter) * wave_frequency * 2 * math.pi + layer_phase_offset
            
            # Calculate the displacement magnitude along the normal
            displacement = final_amplitude * math.tanh(wave_sharpness * math.sin(phase))
            
            point = item["point"]
            normal = item["normal"]
            
            # Apply the displacement to the point along its normal vector
            new_point = [
                point[0] + normal[0] * displacement,
                point[1] + normal[1] * displacement,
                point[2] + normal[2] * displacement
            ]
            processed_points.append(new_point)
            
        return processed_points

    def get_ordered_curves(self, profile):
        """
        Takes a profile and returns its constituent sketch curves in a continuous,
        ordered list. It handles cases where curves need to be traversed in reverse.
        
        Args:
            profile (adsk.fusion.Profile): The profile to process.

        Returns:
            list[dict]: A list of dictionaries, where each dict contains the
                        'curve' (SketchEntity) and a boolean 'is_reversed'.
                        Returns an empty list if the profile is invalid.
        """
        app = adsk.core.Application.get()
        ui = app.userInterface

        profile_loop = profile.profileLoops.item(0)
        remaining_curves = [c.sketchEntity for c in profile_loop.profileCurves]

        if not remaining_curves:
            return []

        if len(remaining_curves) == 1:
            return [{'curve': remaining_curves[0], 'is_reversed': False}]
        
        connection_tolerance = 0.01 
        ordered_curves_data = []
        
        # --- Find a deterministic starting curve ---
        # Find the curve containing the point with the lowest Y, then lowest X value.
        start_curve = None
        min_y = float('inf')
        min_x = float('inf')

        for curve in remaining_curves:
            # Check both start and end points of the curve
            for point in [curve.startSketchPoint.geometry, curve.endSketchPoint.geometry]:
                if point.y < min_y - connection_tolerance:
                    min_y = point.y
                    min_x = point.x
                    start_curve = curve
                elif abs(point.y - min_y) < connection_tolerance and point.x < min_x:
                    min_x = point.x
                    start_curve = curve
        
        if not start_curve: # Fallback if no start curve is found
            start_curve = remaining_curves[0]

        remaining_curves.remove(start_curve)

        # Determine the starting point and direction for the chosen start_curve
        start_point_geom = start_curve.startSketchPoint.geometry
        if abs(start_point_geom.y - min_y) < connection_tolerance and abs(start_point_geom.x - min_x) < connection_tolerance:
            # The start point of the curve is the "lowest" point, so we traverse forward.
            ordered_curves_data.append({'curve': start_curve, 'is_reversed': False})
            last_end_point = start_curve.endSketchPoint
        else:
            # The end point of the curve is the "lowest" point, so we traverse "backwards".
            ordered_curves_data.append({'curve': start_curve, 'is_reversed': True})
            last_end_point = start_curve.startSketchPoint

        # --- Sequentially find the next closest curve ---
        while remaining_curves:
            min_dist = float('inf')
            best_match_index = -1
            is_reversed_for_best_match = False

            # Find the curve in the remaining pool with an endpoint closest to the last endpoint
            for i, next_curve in enumerate(remaining_curves):
                dist_to_start = next_curve.startSketchPoint.geometry.distanceTo(last_end_point.geometry)
                dist_to_end = next_curve.endSketchPoint.geometry.distanceTo(last_end_point.geometry)

                if dist_to_start < min_dist:
                    min_dist = dist_to_start
                    best_match_index = i
                    is_reversed_for_best_match = False

                if dist_to_end < min_dist:
                    min_dist = dist_to_end
                    best_match_index = i
                    is_reversed_for_best_match = True
            
            # If the closest found curve is within tolerance, consider it connected.
            if best_match_index != -1 and min_dist < connection_tolerance:
                best_match_curve = remaining_curves.pop(best_match_index)
                
                ordered_curves_data.append({'curve': best_match_curve, 'is_reversed': is_reversed_for_best_match})

                # Update the last_end_point for the next iteration
                if is_reversed_for_best_match:
                    last_end_point = best_match_curve.startSketchPoint
                else:
                    last_end_point = best_match_curve.endSketchPoint
            else:
                # If no curve is found within the tolerance, the path is broken.
                #ui.messageBox(f"Warning: Could not find a connecting curve for profile. Path may be broken. Found {len(ordered_curves_data)} of {len(profile_loop.profileCurves)} curves.")
                break # Exit the loop

        return ordered_curves_data

    def extract_curve_data(self, ordered_curves_data, sketch, z_height, wave_frequency, final_amplitude):
        """
        Samples points along the ordered path of curves and calculates their normal vectors.
        This data is packaged for the external processing script.

        Args:
            ordered_curves_data (list[dict]): The output from get_ordered_curves.
            sketch (adsk.fusion.Sketch): The sketch containing the curves.
            z_height (float): The Z-height of the current layer.
            layer_index (int): The index of the current layer.
            wave_frequency (float): The number of waves for the layer.
            final_amplitude (float): The calculated wave amplitude for the layer.

        Returns:
            dict: A dictionary containing all geometric data for the layer.
        """
        points_and_normals = []
        cumulative_length = 0.0
        total_perimeter = sum(data['curve'].length for data in ordered_curves_data)
        num_ordered_curves = len(ordered_curves_data)

        for curve_index, data in enumerate(ordered_curves_data):
            original_curve = data['curve']
            is_reversed = data['is_reversed']

            if not original_curve.isValid: continue
            evaluator = original_curve.geometry.evaluator
            (ret, start_param, end_param) = evaluator.getParameterExtents()
            curve_length = original_curve.length
            
            # Calculate how many points this curve segment gets based on its length proportion
            num_points = max(2, int((curve_length / total_perimeter) * (wave_frequency * 3)))

            # Determine the number of points to sample for this specific curve segment
            # We omit the last point of each curve segment, except for the very last one, to avoid duplicates.
            is_last_curve_in_loop = (curve_index == num_ordered_curves - 1)
            points_to_sample_on_this_curve = num_points if is_last_curve_in_loop else num_points -1
            
            # Ensure we at least sample one point if the calculation results in zero
            if points_to_sample_on_this_curve < 1:
                 points_to_sample_on_this_curve = 1


            for i in range(points_to_sample_on_this_curve):
                # Calculate fraction along the curve for this point (0.0 to 1.0)
                fraction = i / (num_points - 1) if num_points > 1 else 0.0

                # Determine the distance along the curve's natural parameterization.
                # If reversed, we sample from the end towards the start to match traversal direction.
                dist_from_start = (1.0 - fraction) * curve_length if is_reversed else fraction * curve_length
                
                # The perimeter position always increases, regardless of curve direction.
                current_perimeter_pos = cumulative_length + (fraction * curve_length)

                # Get the geometry at that distance
                (ret, param) = evaluator.getParameterAtLength(start_param, dist_from_start)
                (ret, point) = evaluator.getPointAtParameter(param)
                (ret, tangent) = evaluator.getTangent(param)
                
                # The tangent must always point in the direction of traversal.
                # We flip it if the curve's natural direction is opposite to our traversal.
                if is_reversed:
                    tangent.scaleBy(-1.0)

                sketch_plane_normal = sketch.referencePlane.geometry.normal
                normal = tangent.crossProduct(sketch_plane_normal)
                normal.normalize()

                points_and_normals.append({
                    "point": [point.x, point.y, point.z],
                    "normal": [normal.x, normal.y, normal.z],
                    "perimeter_pos": current_perimeter_pos
                })
            cumulative_length += curve_length

        return {
            "z_height": z_height,
            "total_perimeter": total_perimeter,
            "final_amplitude": final_amplitude,
            "geometry": points_and_normals
        }