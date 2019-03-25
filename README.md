# 'Wax Dropper':

...

# Instructions for Use:

* ...

# Instructions for Use as Submodule:

* The following functions can be rewritten in a subclass:

    * `self.can_start(context)`
        * returns `True` if Wax Dropper ui and data structures can be initialized, else `False`
        * by default, this function checks the following, where `ob` is `bpy.context.active_object`: `return ob is not None and ob.type == "MESH"`
        * must be rewritten with the `@classmethod` decorator
    * `self.ui_setup_post()`
        * called after ui elements have been declared
        * create your own ui panels and elements
        * add/edit buttons, frames, properties, etc. in the existing structure:
        ```
            self.info_panel
                self.inst_paragraphs
                self.options_frame
                    self.wax_actions_options
                    self.wax_surface_options
            self.tools_panel
                self.mode_frame
                    self.mode_options
                self.finish_frame
                    self.fuse_and_continue_button
                    self.commit_button
                    self.cancel_button
        ```
        * hide existing ui elements with the following code (replace `self.info_panel` with any ui element above): `self.info_panel.visible = False`
    * `self.start_post()`
        * called after ui and data structures have been initialized
    * `self.end_commit_post()`
        * called after Wax Dropper is committed
