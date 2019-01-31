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
import os
import math
import time

# Blender imports
import bgl
import bpy
import bmesh
from bmesh.types import BMVert, BMEdge, BMFace
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_line
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from bpy_extras import view3d_utils

# Addon imports
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


class WAX_OT_operator_skeleton(CookieCutter):
    """ Operator skeleton """
    bl_idname      = "wax.operator_skeleton"
    bl_label       = "Operator Skeleton"
    bl_description = ""
    bl_space_type  = "VIEW_3D"
    bl_region_type = "TOOLS"

    default_keymap = {
        "draw_bone":{"RIGHTMOUSE", "LEFTMOUSE"},
        "commit":   {"RET",},
        "cancel":   {"RIGHTMOUSE", "ESC"},
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

        self.header_text_set("Wax Dropper")
        self.cursor_modal_set("CROSSHAIR")
        self.manipulator_hide()

        scn = bpy.context.scene

        # get target object and apply modifiers
        self.obj = bpy.context.object
        if len(self.obj.modifiers) > 0: apply_modifiers(self.obj)

        # hide other objects
        hide([obj for obj in scn.objects if obj != self.obj])

        # self.is_dirty = False

        self.bone_obj, self.meta_obj = self.make_bone_base()
        self.bone_bvh = None

        self.wax_opts = WaxDropperOptions()

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
        help.add(ui.UI_WrappedLabel("ENTER to finish"))
        help.add(ui.UI_WrappedLabel("ESC to cancel"))
        opts = win.add(ui.UI_Frame("Options"))
        opts.add(ui.UI_Number("Size", get_blobsize, set_blobsize, fn_get_print_value=get_blobsize_print, fn_set_print_value=set_blobsize))
        action = opts.add(ui.UI_Options(get_action, set_action, label="Action: ", vertical=False))
        action.add_option("add")
        action.add_option("subtract")

    def end_commit(self):
        """ Commit changes to mesh! """
        scn = bpy.context.scene
        jmod = self.obj.modifiers.new('Join Wax', type='BOOLEAN')
        print(self.wax_opts["action"])
        if self.wax_opts["action"] == 'add':
            jmod.operation = 'UNION'
        else:
            jmod.operation = 'DIFFERENCE'
        jmod.object = self.bone_obj

        apply_modifiers(self.obj)

        self.remove_meta_data()

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

        if self.actions.pressed("draw_bone"):
            if 'Meta Bone' not in bpy.data.objects:
                self.make_bone_base()
            self.draw_bone()
            return

        if self.actions.pressed("commit"):
            self.done();
            return

        if self.actions.pressed("cancel"):
            self.done(cancel=True)
            return

    ###################################################
    # draw functions

    @CookieCutter.Draw("post2d")
    def draw_postpixel(self):
        pass

    ###################################################
    # class variables

    # NONE!

    #############################################
    # class methods

    def make_bone_base(self):
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
            bone_me = bpy.data.meshes.new('Wax Blobs')
            bone_obj = bpy.data.objects.new('Wax Blobs', bone_me)
            scn.objects.link(bone_obj)
            smod = bone_obj.modifiers.new('Smooth', type = 'SMOOTH')
            smod.iterations = 10
        else:
            bone_obj = bpy.data.objects.get('Wax Blobs')
            bone_me = bone_obj.data

        meta_obj.hide = True
        meta_obj.matrix_world = self.obj.matrix_world
        bone_obj.matrix_world = self.obj.matrix_world

        return bone_obj, meta_obj

    def draw_bone(self):
        scn = bpy.context.scene
        coord = self.event.mouse_region_x, self.event.mouse_region_y
        metabase = bpy.data.objects.get('Meta Wax')

        region = bpy.context.region
        rv3d = bpy.context.region_data
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray_target = ray_origin + (view_vector * 1000)

        imx = metabase.matrix_world.inverted()
        d, loc = self.bone_obj.ray_cast(imx * ray_origin, imx * ray_target - imx * ray_origin)[:2]

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
                self.push_meta_to_bone()
        else:
            res, loc = scn.ray_cast(ray_origin, ray_target - ray_origin)[:2]
            if not res:
                return

            print('adding a new metaball')
            mb = metabase.data.elements.new(type='BALL')
            mb.co = imx * loc
            mb.radius = self.wax_opts["blob_size"] * (2 if self.event.type == "RIGHTMOUSE" else 1)
            mb.use_negative = self.event.type == "RIGHTMOUSE"
            self.push_meta_to_bone()

    def remove_meta_data(self):
        # remove meta data
        meta_obj = bpy.data.objects.get('Meta Wax')
        if meta_obj is not None:
            md = meta_obj.data
            bpy.data.objects.remove(meta_obj)
            bpy.data.metaballs.remove(md)
        wax_obj = bpy.data.objects.get('Wax Blobs')
        if wax_obj is not None:
            wd = wax_obj.data
            bpy.data.objects.remove(wax_obj)
            bpy.data.meshes.remove(wd)

    def push_meta_to_bone(self):
        ct = time.time()
        scn = bpy.context.scene
        scn.update()
        self.bone_obj.data = self.meta_obj.to_mesh(scn, apply_modifiers=True, settings='PREVIEW')

    #############################################
