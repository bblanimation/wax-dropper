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
# NONE!

# Blender imports
import bpy
from bpy.types import Panel

# Module imports
from ..functions.common import *


class VIEW3D_PT_tools_wax_dropper(Panel):
    bl_space_type  = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_label       = "Wax Dropper Interface"
    bl_idname      = "VIEW3D_PT_tools_wax_dropper"
    bl_context     = "objectmode"
    bl_category    = "Wax Dropper"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        if bpy.data.texts.find('Addon Skeleton log') >= 0:
            split = layout_split(layout, align=True, factor=0.9)
            split.operator("scene.report_error", text="Report Error", icon="URL").addon_name = "Wax Dropper"
            split.operator("scene.close_report_error", text="", icon="PANEL_CLOSE").addon_name = "Wax Dropper"

        layout.operator("object.wax_dropper")
