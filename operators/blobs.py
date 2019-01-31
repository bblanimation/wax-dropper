'''
Created on Jan 14, 2019

@author: Patrick
'''
'''
Created on Dec 17, 2018

@author: Patrick
'''

import bpy
import bmesh

from common_utilities import bversion, get_settings
from common_drawing import outline_region
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from textbox import TextBox

def blobby_bone_draw_callback(self, context): 
    self.help_box.draw() 
    #self.crv.draw(context)
    #self.crv.draw_extra(context)
    prefs = get_settings()
    r,g,b = prefs.active_region_color
    outline_region(context.region,(r,g,b,1))  
    
    
class D3Tool_OT_wax_droplet(bpy.types.Operator):
    """Click to Add Wax Droplets"""
    bl_idname = "d3tool.add_wax_droplets_to_object"
    bl_label = "Wax Dropper"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls,context):
        if context.object == None: return False
        return True
    
    def modal_nav(self, event):
        events_nav = {'MIDDLEMOUSE', 'WHEELINMOUSE','WHEELOUTMOUSE', 'WHEELUPMOUSE','WHEELDOWNMOUSE'} #TODO, better navigation, another tutorial
        handle_nav = False
        handle_nav |= event.type in events_nav

        if handle_nav: 
            return 'nav'
        return ''
    
    def modal_main(self,context,event):
        # general navigation
        nmode = self.modal_nav(event)
        if nmode != '':
            return nmode  #stop here and tell parent modal to 'PASS_THROUGH'

        if event.type in {"NUMPAD_PLUS"}:
            self.operation = 'ADD'
            self.update_help_message()
            return 'main'
        
        if event.type in {'NUMPAD_MINUS'}:
            self.operation = 'SUBTRACT'
            self.update_help_message()
            return 'main'

        if event.type == 'UP_ARROW' and event.value == 'PRESS':
            self.blob_size += .25
            self.blob_size = min(6.0, self.blob_size)
            self.update_help_message()
            
            return 'main'
        if event.type == 'DOWN_ARROW' and event.value == 'PRESS':
            self.blob_size -= .25

            self.blob_size = max(0.5, self.blob_size)
            self.update_help_message()
            
             
        if (event.type == 'RIGHTMOUSE' and event.value == 'PRESS' and event.shift) or \
           (event.type == 'LEFTMOUSE' and event.shift and event.value == 'PRESS'):
            if 'Meta Bone' not in bpy.data.objects:
                self.make_bone_base(context)
                #return 'main'
            
            x, y = event.mouse_region_x, event.mouse_region_y
            metabase = bpy.data.objects.get('Meta Wax')
            
            if self.bone_bvh == None:  #first time clicking
                #metabase.data.resolution = 1.5
                self.update_bone_obj_bvh(context)
            
            
            region = context.region
            rv3d = context.region_data
            coord = x, y
            view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
            ray_target = ray_origin + (view_vector * 1000)
        
            #res, loc, no, ind, obj, omx = context.scene.ray_cast(ray_origin, ray_target - ray_origin)
            mx = metabase.matrix_world
            imx = mx.inverted()
            loc, no, ind, d = self.bone_bvh.ray_cast(imx * ray_origin, imx * ray_target - imx * ray_origin)
            
            if loc:  
                if event.type == 'RIGHTMOUSE':
                    to_remove = []
                    for mb in metabase.data.elements:
                        if (mb.co - loc).length < 1.5 * self.blob_size:
                            to_remove.append(mb)
                    #closest_mb = min(metabase.data.elements, key = lambda x: (x.co - loc).length)
                    #metabase.data.elements.remove(closest_mb)
                    for mb in to_remove:
                        metabase.data.elements.remove(mb)
                    
                else:
                    mb = metabase.data.elements.new(type = 'BALL')
                    mb.co = loc
                    mb.radius = self.blob_size
                self.update_bone_obj_bvh(context)
                
            else:
                res, loc, no, ind, obj, omx = context.scene.ray_cast(ray_origin, ray_target - ray_origin)    
                
                if res:
                    print('adding a new metaball')
                    mb = metabase.data.elements.new(type = 'BALL')
                    mb.co = imx * loc
                    mb.radius = self.blob_size
                    
                    if event.type == 'RIGHTMOUSE':
                        mb.radius = 2 * self.blob_seize
                        mb.use_negative = True
                        
                        
                    self.update_bone_obj_bvh(context)

        if event.type == 'RET' and event.value == 'PRESS':
            self.finish(context)
            return 'finish'
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            self.remove_meta_data()
            return 'cancel' 

        return 'main'
    
    def update_bone_obj_bvh(self,context):
        
        context.scene.update()
        temp_me = self.meta_obj.to_mesh(context.scene, apply_modifiers = True, settings = 'PREVIEW')
        temp_bme = bmesh.new()
        temp_bme.from_mesh(temp_me)
        
        temp_bme.to_mesh(self.bone_obj.data)
        self.bone_bvh = BVHTree.FromBMesh(temp_bme)
        
        self.bone_obj.data.update()
        bpy.data.meshes.remove(temp_me)
        temp_bme.free()
        
    def update_help_message(self):
        
        msg =  "SHIFT + Left Click to place wax \n SHIFT + RIGHT MOUSE to remove wax \n ENTER to finish \nESC to cancel"
        msg += "\n Up Arrow and Down arrow to change brush size"
        
        msg += "\n\nWax Drop Size: " + str(round(self.blob_size, 2))
        
        msg += "\n\nFinal Operation: " + self.operation
        
        self.help_box.raw_text = msg
        self.help_box.format_and_wrap_text()
        
        return msg
    def modal(self, context, event):
        context.area.tag_redraw()
        
        FSM = {}    
        FSM['main']    = self.modal_main
        FSM['nav']     = self.modal_nav
        
        nmode = FSM[self.mode](context, event)
        
        if nmode == 'nav': 
            return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            #context.space_data.show_manipulator = True
            
            #if nmode == 'finish':
            #   context.space_data.transform_manipulators = {'TRANSLATE', 'ROTATE'}
            #else:
            #    context.space_data.transform_manipulators = {'TRANSLATE'}
            #clean up callbacks
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}

    def invoke(self,context, event):
        
        bpy.ops.ed.undo_push()
        
        model = context.object
        
        for ob in context.scene.objects:
            if ob != context.object:
                ob.hide = True
        
        
        if len(model.modifiers):
            bme = bmesh.new()
            bme.from_object(model, context.scene, deform = True)
            model.modifiers.clear()
            bme.to_mesh(model.data)
            model.data.update()
            bme.free()
            
            
        
        self.model = model
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

    

    def finish(self, context):
        
        jmod = self.model.modifiers.new('Join Wax', type = 'BOOLEAN')
        if self.operation == 'ADD':
            jmod.operation = 'UNION'
        else:
            jmod.uperation = 'DFFERENCE'
        jmod.object = self.bone_obj
        
        bpy.context.scene.update()  
        bme = bmesh.new()
        bme.from_object(self.model, context.scene, deform = True)
        self.model.modifiers.clear()
        bme.to_mesh(self.model.data)
        self.model.data.update()
        bme.free()
        
        self.remove_meta_data()

        pass
    
    def remove_meta_data(self):
        
        if 'Meta Wax' in bpy.data.objects:
            meta_obj = bpy.data.objects.get('Meta Wax')
            md = meta_obj.data
        
            bpy.data.objects.remove(meta_obj)
            bpy.data.metaballs.remove(md)
    
        if 'Wax Blobs' in bpy.data.objects:
       
            wax_obj = bpy.data.objects.get('Wax Blobs')
            wd = wax_obj.data
            bpy.data.objects.remove(wax_obj)
            bpy.data.meshes.remove(wd)
            
        
        
    def make_bone_base(self, context):
        if 'Meta Wax' in bpy.data.objects:
            meta_obj = bpy.data.objects.get('Meta Wax')
            meta_data = meta_obj.data
        else:
            meta_data = bpy.data.metaballs.new('Meta Wax')
            meta_obj = bpy.data.objects.new('Meta Wax', meta_data)
            meta_data.resolution = .4
            meta_data.render_resolution = 1
            context.scene.objects.link(meta_obj)
        if 'Wax Blobs' not in bpy.data.objects:
            bone_me = bpy.data.meshes.new('Wax Blobs')
            bone_obj = bpy.data.objects.new('Wax Blobs', bone_me)
            context.scene.objects.link(bone_obj)
            smod = bone_obj.modifiers.new('Smooth', type = 'SMOOTH')
            smod.iterations = 10
        else:
            bone_obj = bpy.data.objects.get('Wax Blobs')
            bone_me = bone_obj.data
            
        meta_obj.hide = True    
        meta_obj.matrix_world = context.object.matrix_world
        bone_obj.matrix_world = context.object.matrix_world
        
        return bone_obj, meta_obj
def register():
    bpy.utils.register_class(D3Tool_OT_wax_droplet)
    
    
def unregister():
    bpy.utils.unregister_class(D3Tool_OT_wax_droplet)
    
    
if __name__ == "__main__":
    register()