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
from mathutils import Vector
from mathutils.geometry import intersect_line_line
from bmesh.types import BMVert, BMEdge, BMFace

# Addon imports
from ..addon_common.cookiecutter.cookiecutter import CookieCutter
from ..addon_common.common import ui
from ..addon_common.common.bmesh_utils import BMeshSelectState, BMeshHideState
from ..addon_common.common.maths import Point, Point2D, XForm
from ..addon_common.common.decorators import PersistentOptions
from ..functions import *


@PersistentOptions()
class ExtruCutOptions:
    defaults = {
        "by": "count",
        "count": 5,
        "length": 0.5,
        "position": 9,
    }


class SKELETON_OT_operator_skeleton(CookieCutter):
    """ Operator skeleton """
    bl_idname      = "skeleton.operator_skeleton"
    bl_label       = "Operator Skeleton"
    bl_description = ""
    bl_space_type  = "VIEW_3D"
    bl_region_type = "TOOLS"

    default_keymap = {
        "displace": {"LEFTMOUSE","CTRL+LEFTMOUSE"},
        "commit": {"RET",},
        "cancel": {"RIGHTMOUSE", "ESC"},
    }

    ################################################
    # CookieCutter Operator methods

    @classmethod
    def can_start(cls, context):
        """ Start only if editing a mesh """
        return context.object != None

    def start(self):
        """ initialization function """
        scn = bpy.context.scene
        bpy.ops.ed.undo_push()  # push current state to undo

        self.header_text_set("ExtruCut")
        self.cursor_modal_set("CROSSHAIR")
        self.manipulator_hide()

        obj = bpy.context.object

        hide([o for o in scn.objects if o != obj])

        # if len(obj.modifiers) > 0:
        ct = time.time()
        if True:
            bme = bmesh.new()
            bme.from_object(obj, scn, deform=True)
            obj.modifiers.clear()
            bme.to_mesh(obj.data)
            obj.data.update()
            bme.free()
        else:
            mesh = obj.to_mesh(scn, True, "PREVIEW")
        stopWatch(1, ct)

        self.obj = obj
        self.blob_size = 2.0

        self.operation = 'ADD' #or subtract

        #TODO, tweak the modifier as needed
        help_txt = "SHIFT + Left Click to place wax \n SHIFT + RIGHT MOUSE to remove wax \n ENTER to finish \nESC to cancel"

        self.help_box = TextBox(context,500,500,300,200,10,20,help_txt)
        self.help_box.snap_to_corner(context, corner = [1,1])
        self.update_help_message()

        self.bone_obj, self.meta_obj = self.make_bone_base(context)
        self.bone_bvh = None

        self.mode = 'main'
        self._handle = bpy.types.SpaceView3D.draw_handler_add(blobby_bone_draw_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def end_commit(self):
        """ Commit changes to mesh! """

        # delete previously selected geometry
        for bmf in self.all_faces:   self.bmesh.faces.remove(bmf)
        for bme in self.inner_edges: self.bmesh.edges.remove(bme)
        for bmv in self.inner_verts: self.bmesh.verts.remove(bmv)

        # create new geometry
        def get_bmv(i, v):
            return self.join_verts[i] if i in self.join_verts else self.bmesh.verts.new(v)
        lbmv = [ get_bmv(i, v) for (i, v) in enumerate(self.extrude_verts) ]
        lbmf = [ self.bmesh.faces.new([lbmv[i_v] for i_v in liv]) for liv in self.extrude_sides ]
        lbmf += [ self.bmesh.faces.new([lbmv[i_v] for i_v in liv]) for liv in self.extrude_faces ]
        for bmf in lbmf:
            bmf.normal_update()
            bmf.select = True
        bmesh.update_edit_mesh(self.emesh)
        bpy.ops.mesh.normals_make_consistent()
        n_sides = len(self.extrude_sides)
        for bme in self.outer_edges: bme.select = False
        for bmv in self.outer_verts: bmv.select = False
        for i,bmf in enumerate(lbmf): bmf.select = (i >= n_sides)

        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="EDIT")

    def end_cancel(self):
        """ Cancel changes """
        bpy.ops.ed.undo()   # undo geometry hide

    def end(self):
        """ Restore everything, because we're done """
        self.manipulator_restore()
        self.header_text_restore()
        self.cursor_modal_restore()

    def update(self):
        """ Check if we need to update any internal data structures """
        self.segment_opts.clean()
        if not self.is_dirty: return

        # recompute
        self.is_dirty = False
        n = self.segment_opts["count"] if self.segment_opts["by"] == "count" else math.floor(self.extrude_dist / self.segment_opts["length"])
        n = max(1, min(n, 100))
        v = self.extrude_dir * self.extrude_dist
        l = len(self.outer_verts) * (n + 1)
        self.segments = n
        extrude_map = {}
        extrude_map.update({ bmv:(i * (n + 1)) for (i, bmv) in enumerate(self.outer_verts) })
        extrude_map.update({ bmv:(l + i) for (i, bmv) in enumerate(self.inner_verts) })
        def m(v): return extrude_map[v]
        self.extrude_verts = [
            bmv.co + v * r / n
            for bmv in self.outer_verts
            for r in range(0, n+1)
        ] + [
            bmv.co + v
            for bmv in self.inner_verts
        ]
        self.join_verts = {
            (i * (n + 1)):bmv for i,bmv in enumerate(self.outer_verts)
        }
        self.extrude_edges = [
            tuple(m(bmv) + r for bmv in bme.verts)
            for bme in self.outer_edges
            for r in range(0, n+1)
        ] + [
            (m(bmv) + r + 0, m(bmv) + r + 1)
            for bmv in self.outer_verts
            for r in range(0, n)
        ] + [
            tuple(m(bmv) + (0 if bmv in self.inner_verts else n) for bmv in bme.verts)
            for bme in self.all_edges
        ]
        self.extrude_sides = [
            (m(bme.verts[0]) + r, m(bme.verts[0]) + r + 1, m(bme.verts[1]) + r + 1, m(bme.verts[1]) + r)
            for bme in self.outer_edges
            for r in range(0, n)
        ]
        self.extrude_faces = [
            tuple(m(bmv) + (0 if bmv in self.inner_verts else n) for bmv in bmf.verts)
            for bmf in self.all_faces
        ]

    #############################################
    # State functions

    @CookieCutter.FSM_State("main")
    def modal_main(self):
        self.cursor_modal_set("CROSSHAIR")

        if self.actions.pressed("commit"):
            self.done();
            return
        if self.actions.pressed("cancel"):
            self.done(cancel=True)
            return

        if self.actions.pressed("displace"):
            return "displace"

    @CookieCutter.FSM_State("displace", "enter")
    def modal_enter_displace(self):
        self.mousedown_p = self.closest_extrude_Point(self.actions.mouse)
        self.mousedown_dist = self.extrude_dist

    @CookieCutter.FSM_State("displace")
    def modal_displace(self):
        self.cursor_modal_set("HAND")

        if self.actions.released("displace"):
            return "main"
        if self.actions.pressed("cancel"):
            self.extrude_dist = self.mousedown_dist
            self.is_dirty = True
            return "main"

        if self.actions.mousemove:
            p = self.closest_extrude_Point(self.actions.mouse)
            off = self.extrude_dir.dot(p - self.mousedown_p)
            self.extrude_dist = self.mousedown_dist + off
            if self.actions.ctrl:
                self.extrude_dist = math.ceil(self.extrude_dist / self.segment_opts["length"]) * self.segment_opts["length"]
            self.is_dirty = True

    ###################################################
    # draw functions

    @CookieCutter.Draw("post3d")
    def draw_postview(self):
        if self.extrude_dist is None: return

        glv = self.glVertex
        bgl.glEnable(bgl.GL_BLEND)

        # draw extrusion line
        self.drawing.line_width(1.0)
        bgl.glBegin(bgl.GL_LINES)
        bgl.glColor4f(1.0, 0.0, 1.0, 0.25)
        glv(self.extrude_pt0 - self.extrude_dir*1000)
        glv(self.extrude_pt0)
        bgl.glColor4f(0.0, 1.0, 1.0, 0.25)
        glv(self.extrude_pt0)
        glv(self.extrude_pt0 + self.extrude_dir*1000)
        bgl.glEnd()

        # draw new geometry: points
        bgl.glDepthRange(0, 0.9999)
        self.drawing.point_size(3.0)
        bgl.glBegin(bgl.GL_POINTS)
        bgl.glColor4f(0.0, 0.2, 0.1, 1.0)
        for v in self.extrude_verts:
            glv(v)
        bgl.glEnd()
        bgl.glDepthRange(0, 1)

        # draw new geometry: edges
        bgl.glDepthRange(0, 0.9999)
        self.drawing.line_width(1.0)
        bgl.glBegin(bgl.GL_LINES)
        bgl.glColor4f(0.0, 0.2, 0.1, 1.0)
        for (iv0,iv1) in self.extrude_edges:
            glv(self.extrude_verts[iv0])
            glv(self.extrude_verts[iv1])
        bgl.glEnd()
        bgl.glDepthRange(0, 1)

        # draw new geometry: faces
        n_orig = len(self.outer_edges) * self.segments
        bgl.glBegin(bgl.GL_TRIANGLES)
        bgl.glColor4f(0.7, 0.7, 0.5, 0.8)
        for liv in self.extrude_faces:
            iv0 = liv[0]
            for iv1,iv2 in zip(liv[1:-1], liv[2:]):
                glv(self.extrude_verts[iv0])
                glv(self.extrude_verts[iv1])
                glv(self.extrude_verts[iv2])
        bgl.glColor4f(0.5, 0.6, 0.5, 0.8)
        for liv in self.extrude_sides:
            iv0 = liv[0]
            for iv1,iv2 in zip(liv[1:-1], liv[2:]):
                glv(self.extrude_verts[iv0])
                glv(self.extrude_verts[iv1])
                glv(self.extrude_verts[iv2])
        bgl.glEnd()

        bgl.glDisable(bgl.GL_BLEND)

    ###################################################
    # class variables

    # NONE!

    #############################################
    # class methods

    def glVertex(self, p : Point):
        bgl.glVertex3f(*self.xform.l2w_point(p))

    def closest_extrude_Point(self, p2D : Point2D) -> Point:
        r = self.drawing.Point2D_to_Ray(p2D)
        p,_ = intersect_line_line(
            self.extrude_pt0, self.extrude_pt1,
            r.o, r.o + r.d,
            )
        return Point(p)

    #############################################
