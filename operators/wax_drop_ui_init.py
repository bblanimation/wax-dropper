'''
Created on Oct 11, 2015

@author: Patrick
'''

import time
import random

from bpy_extras import view3d_utils

from .wax_drop_datastructure import InputPoint, SplineSegment, CurveNode
from ..addon_common.cookiecutter.cookiecutter import CookieCutter
from ..addon_common.common import ui
from ..addon_common.common.blender import show_error_message
from ..addon_common.common.ui import Drawing


class WaxDrop_UI_Init():
    def ui_setup(self):
        # UI Box functionality
        def get_blobsize(): return self.wax_opts["blob_size"]
        def get_blobsize_print(): return "%0.3f" % self.wax_opts["blob_size"]
        def set_blobsize(v): self.wax_opts["blob_size"] = min(max(0.001, float(v)),8.0)

        def get_radius(): return self.wax_opts["paint_radius"]
        def get_radius_print(): return "%0.3f" % self.wax_opts["paint_radius"]
        def set_radius(v):
            self.wax_opts["paint_radius"] = max(0.1, int(v*10)/10)
            if self.brush:
                print("setting bursh radius")
                self.brush.radius = self.wax_opts["paint_radius"]
                self.brush_density()

        def get_resolution(): return self.wax_opts["resolution"]
        def get_resolution_print(): return "%0.3f" % self.wax_opts["resolution"]
        def set_resolution(v):
            self.wax_opts["resolution"] = min(max(0.05, float(v)), 2.0)
            self.meta_obj.data.resolution = self.wax_opts["resolution"]
            self.push_meta_to_wax()
        def get_action(): return self.wax_opts["action"]
        def set_action(v): self.wax_opts["action"] = v

        def get_surface_target(): return self.wax_opts["surface_target"]
        def set_surface_target(v): self.wax_opts["surface_target"] = v

        # instructions
        self.instructions = {
            "place wax": "Left-click on the mesh to add a new wax ball",
            "remove wax": "Right-click on the mesh to remove a wax ball",
            "sketch": "Hold shift + left-click and drag to sketch in a series of wax balls",
            "paint": "Left-click to paint",
        }

        def mode_getter():
            return self._state
        def mode_setter(m):
            self.fsm_change(m)
        #def mode_change():
        #    nonlocal segmentation_container, paint_radius
        #    m = self._state
        #    precut_container.visible = (m in {'spline', 'seed', 'region'})
        #    paint_radius.visible = (m in {'region'})
        #    no_options.visible = not (m in {'region'})
        #    segmentation_container.visible = (m in {'segmentation'})
        #self.fsm_change_callback(mode_change)

        def radius_getter():
            return self.brush_radius
        def radius_setter(v):
            self.brush_radius = max(0.1, int(v*10)/10)
            if self.brush:
                self.brush.radius = self.brush_radius

        # def compute_cut():
        #     # should this be a state instead?
        #     self.network_cutter.knife_geometry4()
        #     self.network_cutter.find_perimeter_edges()
        #     for patch in self.network_cutter.face_patches:
        #         patch.grow_seed(self.input_net.bme, self.network_cutter.boundary_edges)
        #         patch.color_patch()
        #     self.net_ui_context.bme.to_mesh(self.net_ui_context.ob.data)
        #     self.fsm_change('segmentation')

        win_tools = self.wm.create_window('Polytrim Tools', {'pos':7, 'movable':True, 'bgcolor':(0.50, 0.50, 0.50, 0.90)})

        precut_container = win_tools.add(ui.UI_Container()) # TODO: make this rounded

        container = precut_container.add(ui.UI_Frame('Cut Tools'))
        container.add(ui.UI_Button('Compute Cut', lambda:self.fsm_change('segmentation'), align=-1, icon=ui.UI_Image('divide32.png', width=32, height=32)))
        container.add(ui.UI_Button('Cancel', lambda:self.done(cancel=True), align=0))

        segmentation_container = win_tools.add(ui.UI_Container())
        container = segmentation_container.add(ui.UI_Frame('Wax Dropper Tools'))
        container.add(ui.UI_Button('Commit', self.done, align=0))
        container.add(ui.UI_Button('Cancel', lambda:self.done(cancel=True), align=0))

        info = self.wm.create_window('Polytrim Help', {'pos':9, 'movable':True})#, 'bgcolor':(0.30, 0.60, 0.30, 0.90)})
        #info.add(ui.UI_Label('Instructions', align=0, margin=4))
        self.inst_paragraphs = [info.add(ui.UI_Markdown('', min_size=(200,10))) for i in range(4)]
        #for i in self.inst_paragraphs: i.visible = False
        #self.ui_instructions = info.add(ui.UI_Markdown('test', min_size=(200,200)))
        opts = info.add(ui.UI_Frame('Tool Options'))
        opts.add(ui.UI_Number("Size", get_blobsize, set_blobsize, fn_get_print_value=get_blobsize_print, fn_set_print_value=set_blobsize))
        opts.add(ui.UI_Number("Paint Radius", get_radius, set_radius, fn_get_print_value=get_radius_print, fn_set_print_value=set_radius))
        opts.add(ui.UI_Number("Resolution", get_resolution, set_resolution, fn_get_print_value=get_resolution_print, fn_set_print_value=set_resolution, update_multiplier = 0.05))
        
        action = opts.add(ui.UI_Options(get_action, set_action, label="Action: ", vertical=False))
        action.add_option("add")
        action.add_option("subtract")
        action.add_option("none")

        surface = opts.add(ui.UI_Options(get_surface_target, set_surface_target, label="Surface: ", vertical=False))
        surface.add_option("object")
        surface.add_option("wax on wax")
        surface.add_option("scene")

        self.set_ui_text_no_points()


    # XXX: Fine for now, but will likely be irrelevant in future
    def ui_text_update(self):
        '''
        updates the text in the info box
        '''
        if self._state == 'spline':
            if self.input_net.is_empty:
                self.set_ui_text_no_points()
            elif self.input_net.num_points == 1:
                self.set_ui_text_1_point()
            elif self.input_net.num_points > 1:
                self.set_ui_text_multiple_points()
            elif self.grabber and self.grabber.in_use:
                self.set_ui_text_grab_mode()

        elif self._state == 'region':
            self.set_ui_text_paint()
        elif self._state == 'seed':
            self.set_ui_text_seed_mode()

        elif self._state == 'segmentation':
            self.set_ui_text_segmetation_mode()

        else:
            self.reset_ui_text()

    # XXX: Fine for now, but will likely be irrelevant in future
    def set_ui_text_no_points(self):
        ''' sets the viewports text when no points are out '''
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['place wax'])
        self.inst_paragraphs[1].set_markdown('B) ' + self.instructions['remove wax'])
        self.inst_paragraphs[2].set_markdown('C) ' + self.instructions['sketch'])
        self.inst_paragraphs[3].set_markdown('D) ' + self.instructions['paint'])

    def set_ui_text_1_point(self):
        ''' sets the viewports text when 1 point has been placed'''
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['add (extend)'])
        self.inst_paragraphs[1].set_markdown('B) ' + self.instructions['delete'])
        self.inst_paragraphs[2].set_markdown('C) ' + self.instructions['sketch extend'])
        self.inst_paragraphs[3].set_markdown('C) ' + self.instructions['select'])
        self.inst_paragraphs[4].set_markdown('D) ' + self.instructions['tweak'])
        #self.inst_paragraphs[5].set_markdown('E) ' + self.instructions['add (disconnect)'])
        self.inst_paragraphs[6].set_markdown('F) ' + self.instructions['delete (disconnect)'])

        #self.inst_paragraphs[4].set_markdown('E) ' + self.instructions['add (disconnect)'])


    def set_ui_text_multiple_points(self):
        ''' sets the viewports text when there are multiple points '''
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['add (extend)'])
        self.inst_paragraphs[1].set_markdown('B) ' + self.instructions['add (insert)'])
        self.inst_paragraphs[2].set_markdown('C) ' + self.instructions['delete'])
        self.inst_paragraphs[3].set_markdown('D) ' + self.instructions['delete (disconnect)'])
        self.inst_paragraphs[4].set_markdown('E) ' + self.instructions['sketch'])
        self.inst_paragraphs[5].set_markdown('F) ' + self.instructions['tweak'])
        self.inst_paragraphs[6].set_markdown('G) ' + self.instructions['close loop'])

    def set_ui_text_grab_mode(self):
        ''' sets the viewports text during general creation of line '''
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['tweak confirm'])

    def set_ui_text_seed_mode(self):
        ''' sets the viewport text during seed selection'''
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['seed add'])

    def set_ui_text_segmetation_mode(self):
        ''' sets the viewport text during seed selection'''
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['segmentation'])

    def set_ui_text_paint(self):
        self.reset_ui_text()
        self.inst_paragraphs[0].set_markdown('A) ' + self.instructions['paint'])
        self.inst_paragraphs[1].set_markdown('B) ' + self.instructions['paint extend'])
        self.inst_paragraphs[2].set_markdown('C) ' + self.instructions['paint remove'])
        self.inst_paragraphs[3].set_markdown('D) ' + self.instructions['paint mergey'])

    def reset_ui_text(self):
        for inst_p in self.inst_paragraphs:
            inst_p.set_markdown('')
