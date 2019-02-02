# Copyright (C) 2018 Christopher Gearhart
# chris@bblanimation.com
# http://bblanimation.com/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# System imports
import time

# Blender imports
import bgl
import bpy
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_line
from bpy_extras import view3d_utils

# Addon imports
from .wax_drop_datastructure import *
from .wax_drop_ui_init import *
from .wax_drop_ui_tools import *
from .wax_drop_ui_draw import *
from ..addon_common.cookiecutter.cookiecutter import CookieCutter
from ..addon_common.common import ui
from ..addon_common.common.bmesh_utils import BMeshSelectState, BMeshHideState
from ..addon_common.common.maths import Point, Point2D, XForm
from ..addon_common.common.decorators import PersistentOptions
from ..functions import *

@PersistentOptions()
class WaxDropperOptions:
    defaults = {
        "action": "add",
        "blob_size": 1.0,
        "position": 9,
    }


class WAX_OT_wax_drop(WaxDrop_UI_Init, WaxDrop_UI_Draw, WaxDrop_UI_Tools, CookieCutter):
    """ Enter wax drop mode """
    operator_id    = "wax.wax_drop"

    bl_idname      = "wax.wax_drop"
    bl_label       = "Wax Drop Mode"
    bl_description = "Enter wax drop mode"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "TOOLS"

    default_keymap = {
        "draw_wax": {"RIGHTMOUSE", "LEFTMOUSE"},
        "sketch":   {"SHIFT+LEFTMOUSE"},
        "paint":    {"ALT+LEFTMOUSE"},
        "commit":   {"RET"},
        "cancel":   {"ESC"},
    }

    ################################################
    # CookieCutter Operator methods

    @classmethod
    def can_start(cls, context):
        """ Start only if editing a mesh """
        return context.object != None

    def start(self):
        """ initialization function """
        bpy.ops.ed.undo_push()  # push current state to undo

        # initialize vars
        scn = bpy.context.scene

        self.header_text_set("Wax Dropper")
        self.cursor_modal_set("CROSSHAIR")
        self.manipulator_hide()

        # get target object and apply modifiers
        self.source = bpy.context.object
        if len(self.source.modifiers) > 0: apply_modifiers(self.source)
        # hide other objects
        hide([obj for obj in scn.objects if obj != self.source])

        # make wax and meta objects
        self.wax_obj, self.meta_obj = self.make_wax_base()
        # get options for UI box
        self.wax_opts = WaxDropperOptions()

        destructive = "DESTRUCTIVE" # or "NON-DESTRUCTIVE"
        self.net_ui_context = self.NetworkUIContext(self.context, geometry_mode=destructive)
        self.hint_bad = False   # draw obnoxious things over the bad segments
        self.input_net = InputNetwork(self.net_ui_context)
        self.spline_net = SplineNetwork(self.net_ui_context)
        self.network_cutter = NetworkCutter(self.input_net, self.net_ui_context)
        self.sketcher = self.SketchManager(self.input_net, self.spline_net, self.net_ui_context, self.network_cutter)

        self.brush = None
        self.brush_radius = 1.5

        # UI Box functionality
        def get_blobsize(): return self.wax_opts["blob_size"]
        def get_blobsize_print(): return "%0.3f" % self.wax_opts["blob_size"]
        def set_blobsize(v): self.wax_opts["blob_size"] = max(0.001, float(v))
        def get_action(): return self.wax_opts["action"]
        def set_action(v): self.wax_opts["action"] = v
        def fn_get_pos_wrap(v):
            if type(v) is int: return v
            return Point2D(v)
        def fn_set_pos_wrap(v):
            if type(v) is int: return v
            return tuple(v)
        fn_pos = self.wax_opts.gettersetter("position", fn_get_wrap=fn_get_pos_wrap, fn_set_wrap=fn_set_pos_wrap)
        # UI Box elements
        win = self.wm.create_window("Wax Dropper", {"fn_pos":fn_pos, "movable":True})
        help = win.add(ui.UI_Frame("Help"))
        help.add(ui.UI_WrappedLabel("LEFT MOUSE to place wax"))
        help.add(ui.UI_WrappedLabel("RIGHT MOUSE to remove wax"))
        help.add(ui.UI_WrappedLabel("SHIFT+LEFT MOUSE to sketch"))
        help.add(ui.UI_WrappedLabel("ALT+LEFT MOUSE to paint"))
        help.add(ui.UI_WrappedLabel("ENTER to finish"))
        help.add(ui.UI_WrappedLabel("ESC to cancel"))
        opts = win.add(ui.UI_Frame("Options"))
        opts.add(ui.UI_Number("Size", get_blobsize, set_blobsize, fn_get_print_value=get_blobsize_print, fn_set_print_value=set_blobsize))
        action = opts.add(ui.UI_Options(get_action, set_action, label="Action: ", vertical=False))
        action.add_option("add")
        action.add_option("subtract")
        action.add_option("none")

    def end_commit(self):
        """ Commit changes to mesh! """
        scn = bpy.context.scene

        self.remove_meta_wax()

        if self.wax_opts["action"] != "none":
            # add/subtract wax object to/from source
            jmod = self.source.modifiers.new('Join Wax', type='BOOLEAN')
            jmod.operation = 'UNION' if self.wax_opts["action"] == 'add' else 'DIFFERENCE'
            jmod.object = self.wax_obj
            apply_modifiers(self.source)
            self.remove_wax_blobs()

    def end_cancel(self):
        """ Cancel changes """
        bpy.ops.ed.undo()

    def end(self):
        """ Restore everything, because we're done """
        self.manipulator_restore()
        self.header_text_restore()
        self.cursor_modal_restore()

    # def update(self):
    #     """ Check if we need to update any internal data structures """
    #     if not self.is_dirty: return

    #############################################
    # State functions

    @CookieCutter.FSM_State("main")
    def modal_main(self):
        self.cursor_modal_set("CROSSHAIR")

        if self.actions.pressed("draw_wax"):
            if 'Meta Wax' not in bpy.data.objects:
                self.make_wax_base()
            self.draw_wax()
            return

        if self.actions.pressed("sketch"):
            return "sketch"

        if self.actions.pressed("paint"):
            return "paint"

        if self.actions.pressed("commit"):
            self.done();
            return

        if self.actions.pressed("cancel"):
            self.done(cancel=True)
            return

    #--------------------------------------
    # sketch

    @CookieCutter.FSM_State("sketch", "can enter")
    def can_enter_sketch(self):
        return self.ray_cast_source_hit(self.actions.mouse)

    @CookieCutter.FSM_State("sketch", "enter")
    def enter_sketch(self):
        self.sketcher.reset()

        s = self.net_ui_context.selected
        n = self.net_ui_context.hovered_near[1] if self.net_ui_context.hovered_near[0] in {'POINT', 'POINT CONNECT'} else None
        if s and s.is_endpoint and n == s:
            # case 1: mouse is near selected endpoint
            self.sketching_start = s
        else:
            # case 2: start with new disconnected point
            self.sketching_start = self.add_point(self.actions.mouse)
            self.net_ui_context.selected = self.sketching_start
        self.sketcher.add_loc(*self.actions.mouse)

    @CookieCutter.FSM_State("sketch")
    def modal_sketch(self):
        if self.actions.mousemove:
            self.sketcher.smart_add_loc(*self.actions.mouse)
        if self.actions.released('sketch'):
            return 'main'

    @CookieCutter.FSM_State("sketch", "exit")
    def end_sketch(self):
        is_sketch = self.sketcher.is_good()
        if is_sketch:
            self.sketching_end = self.net_ui_context.hovered_near[1] if self.net_ui_context.hovered_near[0] in {'POINT', 'POINT CONNECT'} else None
            self.sketcher.finalize(self.context, self.sketching_start, self.sketching_end)
        self.sketcher.reset()

    #--------------------------------------
    # paint

    @CookieCutter.FSM_State('paint', 'can enter')
    def region_paint_can_enter(self):
        #any time really, may require a BVH update if
        #network cutter has been executed
        return True

    @CookieCutter.FSM_State('paint', 'enter')
    def region_paint_enter(self):
        self.brush = self.PaintBrush(self.net_ui_context, radius=self.brush_radius)
        #set the cursor to to something
        # self.network_cutter.find_boundary_faces_cycles()
        self.click_enter_paint()
        self.last_loc = None
        self.last_update = 0
        self.paint_dirty = False

    @CookieCutter.FSM_State('paint')
    def region_paint(self):
        self.cursor_modal_set('PAINT_BRUSH')

        if self.actions.released('paint'):
            return 'main'

        loc,_,_ = self.brush.ray_hit(self.actions.mouse, self.context)
        if loc and (not self.last_loc or (self.last_loc - loc).length > self.brush.radius*(0.25)):
            self.last_loc = loc
            #self.brush.absorb_geom(self.context, self.actions.mouse)
            self.paint_dirty = True
            # TODO: actually paint the particles

        if self.paint_dirty and (time.time() - self.last_update) > 0.2:
            self.paint_dirty = False
            self.last_update = time.time()

    @CookieCutter.FSM_State('paint', 'exit')
    def region_paint_exit(self):
        # TODO: finish the particle painting
        pass

    #--------------------------------------
    # paint delete

    @CookieCutter.FSM_State('paint delete', 'enter')
    def region_unpaint_enter(self):
        #set the cursor to to something
        # self.network_cutter.find_boundary_faces_cycles()
        self.click_enter_paint(delete = True)
        self.last_loc = None
        self.last_update = 0
        self.paint_dirty = False

    @CookieCutter.FSM_State('paint delete')
    def region_unpaint(self):
        self.cursor_modal_set('PAINT_BRUSH')

        if self.actions.released('RIGHTMOUSE'):
            return 'main'

        loc,_,_ = self.brush.ray_hit(self.actions.mouse, self.context)
        if loc and (not self.last_loc or (self.last_loc - loc).length > self.brush.radius*(0.25)):
            self.last_loc = loc
            #self.brush.absorb_geom(self.context, self.actions.mouse)
            self.paint_dirty = True
            # TODO: actually remove the particles

        if self.paint_dirty and (time.time() - self.last_update) > 0.2:
            self.paint_dirty = False
            self.last_update = time.time()

    @CookieCutter.FSM_State('paint delete', 'exit')
    def region_unpaint_exit(self):
        # TODO: finish removing the particles
        pass


    ###################################################
    # draw functions

    # @CookieCutter.Draw("post2d")
    # def draw_postpixel(self):
    #     pass

    ###################################################
    # class variables

    # NONE!

    #############################################
    # class methods

    def make_wax_base(self):
        scn = bpy.context.scene
        if 'Meta Wax' in bpy.data.objects:
            meta_obj = bpy.data.objects.get('Meta Wax')
            meta_data = meta_obj.data
        else:
            meta_data = bpy.data.metaballs.new('Meta Wax')
            meta_obj = bpy.data.objects.new('Meta Wax', meta_data)
            meta_data.resolution = 0.4
            meta_data.render_resolution = 1
            scn.objects.link(meta_obj)
        if 'Wax Blobs' not in bpy.data.objects:
            wax_me = bpy.data.meshes.new('Wax Blobs')
            wax_obj = bpy.data.objects.new('Wax Blobs', wax_me)
            scn.objects.link(wax_obj)
            smod = wax_obj.modifiers.new('Smooth', type = 'SMOOTH')
            smod.iterations = 10
        else:
            wax_obj = bpy.data.objects.get('Wax Blobs')
            wax_me = wax_obj.data

        meta_obj.hide = True
        meta_obj.matrix_world = self.source.matrix_world
        wax_obj.matrix_world = self.source.matrix_world

        return wax_obj, meta_obj

    def draw_wax(self):
        scn = bpy.context.scene
        coord = self.event.mouse_region_x, self.event.mouse_region_y
        metabase = bpy.data.objects.get('Meta Wax')

        region = bpy.context.region
        rv3d = bpy.context.region_data
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray_target = ray_origin + (view_vector * 1000)

        imx = metabase.matrix_world.inverted()
        d, loc = self.wax_obj.ray_cast(imx * ray_origin, imx * ray_target - imx * ray_origin)[:2]

        if d:
            if self.event.type == 'RIGHTMOUSE':
                to_remove = []
                for mb in metabase.data.elements:
                    if (mb.co - loc).length < 1.5 * self.wax_opts["blob_size"]:
                        to_remove.append(mb)
                # closest_mb = min(metabase.data.elements, key = lambda x: (x.co - loc).length)
                # metabase.data.elements.remove(closest_mb)
                for mb in to_remove:
                    metabase.data.elements.remove(mb)
            else:
                mb = metabase.data.elements.new(type='BALL')
                mb.co = loc
                mb.radius = self.wax_opts["blob_size"]
        else:
            res, loc = scn.ray_cast(ray_origin, ray_target - ray_origin)[:2]
            if not res:
                return

            print('adding a new metaball')
            mb = metabase.data.elements.new(type='BALL')
            mb.co = imx * loc
            mb.radius = self.wax_opts["blob_size"] * (2 if self.event.type == "RIGHTMOUSE" else 1)
            mb.use_negative = self.event.type == "RIGHTMOUSE"
        self.push_meta_to_wax()

    def remove_meta_wax(self):
        # remove meta wax object
        meta_obj = bpy.data.objects.get('Meta Wax')
        if meta_obj is not None:
            md = meta_obj.data
            bpy.data.objects.remove(meta_obj)
            bpy.data.metaballs.remove(md)

    def remove_wax_blobs(self):
        # remove wax blobs object
        wax_obj = bpy.data.objects.get('Wax Blobs')
        if wax_obj is not None:
            wd = wax_obj.data
            bpy.data.objects.remove(wax_obj)
            bpy.data.meshes.remove(wd)

    def push_meta_to_wax(self):
        scn = bpy.context.scene
        scn.update()
        self.wax_obj.data = self.meta_obj.to_mesh(scn, apply_modifiers=True, settings='PREVIEW')

    def ray_cast_source(self, p2d, in_world=True):
        context = self.context
        view_vector, ray_origin, ray_target = get_view_ray_data(context, p2d)
        mx,imx = self.net_ui_context.mx,self.net_ui_context.imx
        itmx = imx.transposed()
        loc, no, face_ind = ray_cast_bvh(self.net_ui_context.bvh, imx, ray_origin, ray_target)
        return (mx * loc if loc and in_world else loc, itmx * no if no and in_world else no, face_ind)

    def ray_cast_source_hit(self, p2d):
        return self.ray_cast_source(p2d, in_world=False)[0] != None

    #############################################
