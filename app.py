"""
================================================================================
EXTREMELY VERBOSE, FEATURE-PACKED IMAGE EDITOR DEMONSTRATION
WITH A SINGLE "BEND TOOL" THAT ACTS LIKE A SELECTION TOOL FOR BENDS.
--------------------------------------------------------------------------------
Retains:
  - Layers, shape data, multiple erasers, direct select, brush, shapes, etc.
  - Full undo/redo with a snapshot-based history panel
  - Large docstrings and comments
--------------------------------------------------------------------------------
BEND TOOL:
  - Click a shape => anchors appear
  - Drag anchor => move it
  - Shift+Click anchor => remove it (if line-based, if > 2 anchors remain)
  - Alt+Click on segment => insert new anchor
  - Ctrl+Click near anchors => warp them in a radius
"""

import tkinter as tk
from tkinter import ttk, filedialog, colorchooser
import copy
import math
from PIL import Image, ImageTk

# ------------------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------------------
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14

MAX_HISTORY = 30
ERASER_RADIUS = 15.0
SOFT_ERASER_FADE_STEP = 20
BEND_WARP_RADIUS = 50.0

# Key modifiers for different Bend actions:
SHIFT_MASK = 0x0001      # On some platforms, SHIFT is bit 0
ALT_MASK = 0x0008        # On many platforms, Alt is bit 3
CONTROL_MASK = 0x0004    # On many platforms, Ctrl is bit 2


# ------------------------------------------------------------------------------
# LAYER
# ------------------------------------------------------------------------------
class Layer:
    def __init__(self, name, visible=True, locked=False):
        self.name = name
        self.visible = visible
        self.locked = locked
        self.items = []

    def add_item(self, item_id, shape_type):
        self.items.append((item_id, shape_type))

    def remove_item(self, item_id):
        self.items = [(iid, st) for (iid, st) in self.items if iid != item_id]


# ------------------------------------------------------------------------------
# SHAPE DATA
# ------------------------------------------------------------------------------
class ShapeData:
    def __init__(self):
        self.shapes = {}

    def store(self, item_id, shape_type, coords, fill, outline, width):
        self.shapes[item_id] = {
            'type': shape_type,
            'coords': coords[:],
            'fill': fill,
            'outline': outline,
            'width': width
        }

    def remove(self, item_id):
        if item_id in self.shapes:
            del self.shapes[item_id]

    def get(self, item_id):
        return self.shapes.get(item_id)

    def update_coords(self, item_id, new_coords):
        if item_id in self.shapes:
            self.shapes[item_id]['coords'] = new_coords[:]


# ------------------------------------------------------------------------------
# EDITOR HISTORY
# ------------------------------------------------------------------------------
class EditorHistory:
    def __init__(self):
        self.states = []
        self.current_index = -1

    def push_state(self, shape_data, layers, description):
        if self.current_index < len(self.states) - 1:
            self.states = self.states[:self.current_index+1]
        if len(self.states) >= MAX_HISTORY:
            del self.states[0]
            self.current_index -= 1
        shape_data_copy = copy.deepcopy(shape_data.shapes)
        layers_copy = []
        for lyr in layers:
            new_lyr = Layer(lyr.name, lyr.visible, lyr.locked)
            new_lyr.items = copy.deepcopy(lyr.items)
            layers_copy.append(new_lyr)

        self.states.append((shape_data_copy, layers_copy, description))
        self.current_index = len(self.states) - 1

    def can_undo(self):
        return self.current_index > 0

    def can_redo(self):
        return self.current_index < len(self.states) - 1

    def undo(self):
        if self.can_undo():
            self.current_index -= 1
            return self.states[self.current_index]
        return None

    def redo(self):
        if self.can_redo():
            self.current_index += 1
            return self.states[self.current_index]
        return None

    def go_to(self, index):
        if 0 <= index < len(self.states):
            self.current_index = index
            return self.states[self.current_index]
        return None

    def get_current_state(self):
        if 0 <= self.current_index < len(self.states):
            return self.states[self.current_index]
        return None

    def get_all_descriptions(self):
        return [f"{i}: {desc[2]}" for i, desc in enumerate(self.states)]


# ------------------------------------------------------------------------------
# MAIN EDITOR
# ------------------------------------------------------------------------------
class SimpleImageEditor:
    def __init__(self, root):
        self.root = root
        root.title("Huge Editor with Single Bend Tool Working Like a Bending Selection")
        root.geometry("1300x800")

        self.shape_data = ShapeData()
        self.layers = []
        self.current_layer_index = None
        self.selected_item = None

        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE

        self.current_tool = None
        self.tool_buttons = {}

        # For shape creation
        self.temp_item = None
        self.start_x = None
        self.start_y = None
        self.last_x = None
        self.last_y = None

        # For "Select" move
        self.moving_shape = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # For Direct Select
        self.direct_select_anchors = []
        self.direct_select_dragging_anchor = None
        self.direct_select_drag_index = None

        # For Bend Tool
        self.bend_anchors = []
        self.bend_drag_anchor = None
        self.bend_drag_index = None

        self.eraser_radius = ERASER_RADIUS
        self.soft_eraser_fade_step = SOFT_ERASER_FADE_STEP

        self.history = EditorHistory()

        self.build_frames()
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options()
        self.setup_layers_panel()
        self.setup_history_panel()

        self.add_layer("Layer 1")
        self.push_history("Initial State")

        self.root.bind("<Control-z>", self.on_ctrl_z)
        self.root.bind("<Control-y>", self.on_ctrl_y)

    # -------------------------------------------------------------------------
    # LARGE UI BUILD
    # -------------------------------------------------------------------------
    def build_frames(self):
        self.toolbar_frame = tk.Frame(self.root, width=120, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.side_frame = tk.Frame(self.root, width=300, bg="#F0F0F0")
        self.side_frame.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_toolbar(self):
        tools = [
            ("Select", None),
            ("Direct Select", None),
            ("Bend Tool", None),     # Single unified Bend Tool
            ("Brush", None),
            ("Line", None),
            ("Rectangle", None),
            ("Ellipse", None),
            ("Text", None),
            ("Sharp Eraser", None),
            ("Round Eraser", None),
            ("Soft Eraser", None),
        ]
        for (tool_name, _) in tools:
            b = tk.Button(self.toolbar_frame, text=tool_name,
                          command=lambda t=tool_name: self.select_tool(t))
            b.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool_name] = b

        # Some extra
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)

    def select_tool(self, tool_name):
        self.current_tool = tool_name
        self.moving_shape = False
        self.direct_select_dragging_anchor = None
        self.bend_drag_anchor = None

        self.clear_direct_select_anchors()
        self.clear_bend_anchors()

        for n, btn in self.tool_buttons.items():
            if n == tool_name:
                btn.config(relief=tk.SUNKEN, bg="#a0cfe6")
            else:
                btn.config(relief=tk.RAISED, bg="SystemButtonFace")

    def setup_canvas(self):
        self.canvas = tk.Canvas(self.main_frame, bg="white", cursor="cross")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.on_left_down)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_up)

    def setup_tool_options(self):
        f = tk.Frame(self.main_frame, bg="#DDDDDD", height=50)
        f.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Label(f, text="Stroke:").pack(side=tk.LEFT, padx=5)
        self.stroke_btn = tk.Button(f, bg=self.stroke_color, width=3,
                                    command=self.pick_stroke_color)
        self.stroke_btn.pack(side=tk.LEFT, padx=5)

        tk.Label(f, text="Fill:").pack(side=tk.LEFT, padx=5)
        self.fill_btn = tk.Button(f, bg=self.fill_color, width=3,
                                  command=self.pick_fill_color)
        self.fill_btn.pack(side=tk.LEFT, padx=5)

        tk.Label(f, text="Brush Size:").pack(side=tk.LEFT, padx=5)
        self.brush_size_slider = ttk.Scale(f, from_=1, to=50, orient=tk.HORIZONTAL,
                                           command=self.on_brush_size_change)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT, padx=5)

        tk.Label(f, text="Font Size:").pack(side=tk.LEFT, padx=5)
        self.font_size_spin = ttk.Spinbox(f, from_=8, to=144, width=4,
                                          command=self.on_font_size_change)
        self.font_size_spin.set(str(self.font_size))
        self.font_size_spin.pack(side=tk.LEFT, padx=5)

    def setup_layers_panel(self):
        lbl = tk.Label(self.side_frame, text="Layers", bg="#F0F0F0",
                       font=("Arial", 12, "bold"))
        lbl.pack(pady=5)

        panel = tk.Frame(self.side_frame, bg="#F0F0F0")
        panel.pack(fill=tk.X)

        self.layer_listbox = tk.Listbox(panel)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.layer_listbox.bind("<<ListboxSelect>>", self.on_layer_select)

        sb = tk.Scrollbar(panel, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=sb.set)

        ctrl = tk.Frame(self.side_frame, bg="#F0F0F0")
        ctrl.pack(fill=tk.X)
        tk.Button(ctrl, text="Up", command=self.move_layer_up).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl, text="Down", command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl, text="Hide/Show", command=self.toggle_layer_visibility).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl, text="Delete", command=self.delete_layer).pack(side=tk.LEFT, padx=2)

    def add_layer(self, name=None):
        if name is None:
            name = f"Layer {len(self.layers)+1}"
        lyr = Layer(name)
        self.layers.insert(0, lyr)
        self.layer_listbox.insert(0, name)
        self.layer_listbox.selection_clear(0, tk.END)
        self.layer_listbox.selection_set(0)
        self.on_layer_select(None)
        self.push_history(f"Added {name}")

    def on_layer_select(self, event):
        sel = self.layer_listbox.curselection()
        if sel:
            self.current_layer_index = sel[0]

    def move_layer_up(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == 0:
            return
        self.layers[idx], self.layers[idx-1] = self.layers[idx-1], self.layers[idx]
        up_name = self.layer_listbox.get(idx-1)
        cur_name = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx-1, idx)
        self.layer_listbox.insert(idx-1, cur_name)
        self.layer_listbox.insert(idx, up_name)
        self.layer_listbox.selection_set(idx-1)
        self.current_layer_index = idx-1
        for (iid, st) in self.layers[idx-1].items:
            self.canvas.tag_raise(iid)
        self.push_history(f"Layer {cur_name} moved up")

    def move_layer_down(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers)-1:
            return
        self.layers[idx], self.layers[idx+1] = self.layers[idx+1], self.layers[idx]
        cur_name = self.layer_listbox.get(idx)
        dn_name = self.layer_listbox.get(idx+1)
        self.layer_listbox.delete(idx, idx+1)
        self.layer_listbox.insert(idx, dn_name)
        self.layer_listbox.insert(idx+1, cur_name)
        self.layer_listbox.selection_set(idx+1)
        self.current_layer_index = idx+1
        for (iid, st) in self.layers[idx+1].items:
            self.canvas.tag_lower(iid)
        self.push_history(f"Layer {cur_name} moved down")

    def toggle_layer_visibility(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lyr = self.layers[idx]
        lyr.visible = not lyr.visible
        new_state = tk.NORMAL if lyr.visible else tk.HIDDEN
        for (iid, st) in lyr.items:
            self.canvas.itemconfigure(iid, state=new_state)
        label = lyr.name
        if not lyr.visible:
            label += " (hidden)"
        self.layer_listbox.delete(idx)
        self.layer_listbox.insert(idx, label)
        self.layer_listbox.selection_set(idx)
        self.push_history(f"Toggled visibility on {lyr.name}")

    def delete_layer(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lyr = self.layers[idx]
        for (iid, st) in lyr.items:
            self.canvas.delete(iid)
            self.shape_data.remove(iid)
        nm = lyr.name
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0
        self.selected_item = None
        self.push_history(f"Deleted layer {nm}")

    def setup_history_panel(self):
        lbl = tk.Label(self.side_frame, text="History", bg="#F0F0F0", font=("Arial", 12, "bold"))
        lbl.pack(pady=5)

        self.history_listbox = tk.Listbox(self.side_frame)
        self.history_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)

        hr_frame = tk.Frame(self.side_frame, bg="#F0F0F0")
        hr_frame.pack(fill=tk.X)
        tk.Button(hr_frame, text="Undo", command=self.do_undo).pack(side=tk.LEFT, padx=2)
        tk.Button(hr_frame, text="Redo", command=self.do_redo).pack(side=tk.LEFT, padx=2)

    def push_history(self, description):
        self.history.push_state(self.shape_data, self.layers, description)
        self.refresh_history_listbox()

    def refresh_history_listbox(self):
        self.history_listbox.delete(0, tk.END)
        for desc in self.history.get_all_descriptions():
            self.history_listbox.insert(tk.END, desc)

    def on_history_select(self, event):
        idx = self.history_listbox.curselection()
        if not idx:
            return
        index = idx[0]
        st = self.history.go_to(index)
        if st:
            self.apply_history_state(st)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def do_undo(self):
        st = self.history.undo()
        if st:
            self.apply_history_state(st)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def do_redo(self):
        st = self.history.redo()
        if st:
            self.apply_history_state(st)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def on_ctrl_z(self, event=None):
        self.do_undo()

    def on_ctrl_y(self, event=None):
        self.do_redo()

    def apply_history_state(self, state):
        shape_data_copy, layers_copy, desc = state
        self.canvas.delete("all")
        self.shape_data.shapes.clear()
        self.layers.clear()
        self.layer_listbox.delete(0, tk.END)
        self.selected_item = None

        old_to_new = {}
        for old_id, sdata in shape_data_copy.items():
            stype = sdata['type']
            coords = sdata['coords']
            fill = sdata['fill']
            outline = sdata['outline']
            width = sdata['width']
            new_id = None

            if stype == "line":
                new_id = self.canvas.create_line(*coords, fill=outline, width=width)
            elif stype == "rectangle":
                new_id = self.canvas.create_rectangle(*coords, outline=outline, fill=fill, width=width)
            elif stype == "ellipse":
                new_id = self.canvas.create_oval(*coords, outline=outline, fill=fill, width=width)
            elif stype == "brush":
                new_id = self.canvas.create_line(*coords, fill=outline, width=width)
            elif stype == "text":
                new_id = self.canvas.create_text(coords[0], coords[1], text="Sample", fill=outline)
            elif stype == "image":
                new_id = self.canvas.create_text(coords[0], coords[1],
                                                 text="(Missing image data in history)",
                                                 fill="red")
            else:
                new_id = self.canvas.create_line(*coords, fill=outline, width=width)

            old_to_new[old_id] = new_id
            self.shape_data.shapes[new_id] = copy.deepcopy(sdata)

        for lcopy in layers_copy:
            new_lyr = Layer(lcopy.name, lcopy.visible, lcopy.locked)
            new_items = []
            for (iid, st) in lcopy.items:
                new_iid = old_to_new.get(iid)
                if new_iid is not None:
                    new_items.append((new_iid, st))
            new_lyr.items = new_items
            self.layers.append(new_lyr)
            label = lcopy.name
            if not lcopy.visible:
                label += " (hidden)"
            self.layer_listbox.insert(tk.END, label)

        for lyr in self.layers:
            if not lyr.visible:
                for (iid, st) in lyr.items:
                    self.canvas.itemconfigure(iid, state=tk.HIDDEN)

    # -------------------------------------------------------------------------
    # MOUSE EVENTS
    # -------------------------------------------------------------------------
    def on_left_down(self, event):
        if self.current_layer_index is None:
            if self.layers:
                self.current_layer_index = 0
            else:
                return
        layer = self.layers[self.current_layer_index]
        if layer.locked or not layer.visible:
            return

        self.start_x, self.start_y = event.x, event.y
        self.last_x, self.last_y = event.x, event.y

        if self.current_tool == "Select":
            self.handle_select_click(event.x, event.y)

        elif self.current_tool == "Direct Select":
            self.handle_direct_select_click(event.x, event.y)

        elif self.current_tool == "Bend Tool":
            self.handle_bend_tool_click(event)

        elif self.current_tool == "Brush":
            self.create_brush_segment(event.x, event.y, layer)

        elif self.current_tool in ("Line","Rectangle","Ellipse"):
            self.temp_item = None

        elif self.current_tool == "Text":
            txt = self.canvas.create_text(event.x, event.y, text="Sample",
                                          fill=self.stroke_color, font=("Arial", self.font_size))
            layer.add_item(txt, "text")
            self.shape_data.store(txt, "text", [event.x, event.y],
                                  fill=self.stroke_color, outline=self.stroke_color, width=1)
            self.select_item(txt)
            self.push_history("Created text")

        elif self.current_tool == "Sharp Eraser":
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                self.erase_item(item[0])
                self.push_history("Sharp Eraser used")

        elif self.current_tool == "Round Eraser":
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                self.round_erase_anchor_points(item[0], event.x, event.y)
                self.push_history("Round Eraser used")

        elif self.current_tool == "Soft Eraser":
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                self.soft_erase_shape(item[0])
                self.push_history("Soft Eraser used")

    def on_left_drag(self, event):
        if self.current_layer_index is None:
            return
        layer = self.layers[self.current_layer_index]
        if layer.locked or not layer.visible:
            return

        if self.current_tool == "Select" and self.moving_shape and self.selected_item:
            self.move_entire_shape(event.x, event.y)

        elif self.current_tool == "Direct Select" and self.direct_select_dragging_anchor is not None:
            self.direct_select_drag_anchor(event.x, event.y)

        elif self.current_tool == "Bend Tool" and self.bend_drag_anchor is not None:
            self.bend_tool_drag_anchor(event.x, event.y)

        elif self.current_tool == "Brush":
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            if abs(dx) > 1 or abs(dy) > 1:
                line_id = self.canvas.create_line(self.last_x, self.last_y, event.x, event.y,
                                                  fill=self.stroke_color, width=self.brush_size)
                layer.add_item(line_id, "brush")
                self.shape_data.store(line_id, "brush",
                                      [self.last_x, self.last_y, event.x, event.y],
                                      fill=None, outline=self.stroke_color, width=self.brush_size)
                self.select_item(line_id)
                self.last_x, self.last_y = event.x, event.y

        elif self.current_tool == "Line":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            self.temp_item = self.canvas.create_line(self.start_x, self.start_y,
                                                     event.x, event.y,
                                                     fill=self.stroke_color,
                                                     width=self.brush_size)

        elif self.current_tool == "Rectangle":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            x1,y1,x2,y2 = self.normalize_rect([self.start_x, self.start_y, event.x, event.y])
            self.temp_item = self.canvas.create_rectangle(x1,y1,x2,y2,
                                                          outline=self.stroke_color,
                                                          fill=self.fill_color,
                                                          width=self.brush_size)

        elif self.current_tool == "Ellipse":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            x1,y1,x2,y2 = self.normalize_rect([self.start_x, self.start_y, event.x, event.y])
            self.temp_item = self.canvas.create_oval(x1,y1,x2,y2,
                                                     outline=self.stroke_color,
                                                     fill=self.fill_color,
                                                     width=self.brush_size)

    def on_left_up(self, event):
        if self.current_tool == "Select" and self.moving_shape:
            self.moving_shape = False
            self.push_history("Moved shape")
            return

        if self.current_tool == "Direct Select" and self.direct_select_dragging_anchor is not None:
            self.direct_select_dragging_anchor = None
            self.direct_select_drag_index = None
            self.push_history("Anchor moved (Direct Select)")
            return

        if self.current_tool == "Bend Tool" and self.bend_drag_anchor is not None:
            self.bend_drag_anchor = None
            self.bend_drag_index = None
            self.push_history("Anchor moved (Bend Tool)")
            return

        if self.temp_item and self.current_tool in ("Line","Rectangle","Ellipse"):
            self.finalize_shape_creation()
            self.push_history(f"Created {self.current_tool}")


    # -------------------------------------------------------------------------
    # BEND TOOL (One Tool That Does Add/Remove/Move/Warp)
    # -------------------------------------------------------------------------
    def handle_bend_tool_click(self, event):
        """
        This single Bend Tool acts like a selection tool but for anchor bending:
          - SHIFT+Click on an anchor => remove anchor (if possible)
          - ALT+Click on a segment => add anchor
          - CTRL+Click near anchors => warp them
          - Otherwise, click an anchor => drag anchor
          - Click shape => show anchors
        """
        mods = event.state
        x, y = event.x, event.y

        # Check if SHIFT, ALT, CTRL are pressed:
        shift_pressed = (mods & SHIFT_MASK) != 0
        alt_pressed   = (mods & ALT_MASK) != 0
        ctrl_pressed  = (mods & CONTROL_MASK) != 0

        # If we have anchors visible, see if we clicked one
        handle = self.find_bend_anchor(x, y)
        if handle is not None:
            # SHIFT+Click => remove anchor (line-based, if >2 anchors)
            if shift_pressed:
                shape_id, anchor_idx = handle
                self.remove_bend_anchor(shape_id, anchor_idx)
                return
            else:
                # start dragging anchor
                self.bend_drag_anchor = handle[0]
                self.bend_drag_index = handle[1]
                return

        # else maybe we clicked the shape
        item = self.canvas.find_closest(x, y)
        if not item:
            self.select_item(None)
            self.clear_bend_anchors()
            return

        shape_id = item[0]
        shape_info = self.shape_data.get(shape_id)
        if not shape_info:
            self.select_item(None)
            self.clear_bend_anchors()
            return

        # if ALT => add anchor
        if alt_pressed:
            if shape_info['type'] in ("line","brush"):
                self.add_bend_anchor(shape_id, x, y)
                return

        # if CTRL => warp anchors in BEND_WARP_RADIUS
        if ctrl_pressed:
            self.bend_warp_anchors(shape_id, x, y)
            return

        # Otherwise => show anchors
        self.select_item(shape_id)
        self.show_bend_anchors(shape_id)


    def find_bend_anchor(self, x, y):
        """
        See if (x,y) is close to any anchor squares in bend_anchors.
        """
        radius = 6
        for (hid, sid, idx) in self.bend_anchors:
            hx1, hy1, hx2, hy2 = self.canvas.coords(hid)
            if hx1 - radius < x < hx2 + radius and hy1 - radius < y < hy2 + radius:
                return (sid, idx)
        return None

    def bend_tool_drag_anchor(self, x, y):
        if not self.bend_drag_anchor:
            return
        shape_info = self.shape_data.get(self.bend_drag_anchor)
        if not shape_info:
            return
        coords = shape_info['coords']
        idx = self.bend_drag_index
        coords[idx] = x
        coords[idx+1] = y

        stype = shape_info['type']
        if stype in ("line","brush"):
            self.canvas.coords(self.bend_drag_anchor, *coords)
        elif stype in ("rectangle","ellipse"):
            x1,y1,x2,y2 = self.normalize_rect(coords)
            self.canvas.coords(self.bend_drag_anchor, x1,y1,x2,y2)
        elif stype == "text":
            self.canvas.coords(self.bend_drag_anchor, coords[0], coords[1])

        self.shape_data.update_coords(self.bend_drag_anchor, coords)
        self.update_bend_anchors(self.bend_drag_anchor)

    def show_bend_anchors(self, item_id):
        self.clear_bend_anchors()
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        # create squares
        for i in range(0, len(coords),2):
            xx = coords[i]
            yy = coords[i+1]
            h = self.canvas.create_rectangle(xx-3, yy-3, xx+3, yy+3, fill="red", outline="red")
            self.bend_anchors.append((h, item_id, i))

    def update_bend_anchors(self, item_id):
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        for (hid, sid, idx) in self.bend_anchors:
            if sid == item_id:
                x = coords[idx]
                y = coords[idx+1]
                self.canvas.coords(hid, x-3, y-3, x+3, y+3)

    def clear_bend_anchors(self):
        for (hid, sid, idx) in self.bend_anchors:
            self.canvas.delete(hid)
        self.bend_anchors.clear()

    def add_bend_anchor(self, shape_id, x, y):
        """
        Insert a new anchor in the line's coords near x,y,
        by finding the closest segment to (x,y).
        """
        shape_info = self.shape_data.get(shape_id)
        if not shape_info or shape_info['type'] not in ("line","brush"):
            return
        coords = shape_info['coords']
        if len(coords) < 4:
            # just append or insert in the middle
            coords.insert(2, y)
            coords.insert(2, x)
            self.canvas.coords(shape_id, *coords)
            self.shape_data.update_coords(shape_id, coords)
            self.show_bend_anchors(shape_id)
            return

        # find best segment
        best_i = 0
        best_dist = float("inf")
        for i in range(0, len(coords)-2, 2):
            x1,y1 = coords[i], coords[i+1]
            x2,y2 = coords[i+2], coords[i+3]
            d = self.point_segment_dist(x,y, x1,y1, x2,y2)
            if d < best_dist:
                best_dist = d
                best_i = i
        # insert after best_i+1
        coords.insert(best_i+2, y)
        coords.insert(best_i+2, x)
        self.canvas.coords(shape_id, *coords)
        self.shape_data.update_coords(shape_id, coords)
        self.show_bend_anchors(shape_id)

    def remove_bend_anchor(self, shape_id, anchor_idx):
        """
        If shape has >2 anchors, remove anchor at anchor_idx.
        """
        shape_info = self.shape_data.get(shape_id)
        if not shape_info or shape_info['type'] not in ("line","brush"):
            return
        coords = shape_info['coords']
        if len(coords) <= 4:
            print("Cannot remove anchor. Would have too few anchors.")
            return
        del coords[anchor_idx:anchor_idx+2]
        self.canvas.coords(shape_id, *coords)
        self.shape_data.update_coords(shape_id, coords)
        self.show_bend_anchors(shape_id)

    def bend_warp_anchors(self, shape_id, x, y):
        """
        Ctrl+Click => warp anchors near (x,y) in a radius BEND_WARP_RADIUS
        """
        shape_info = self.shape_data.get(shape_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        for i in range(0, len(coords), 2):
            dx = coords[i] - x
            dy = coords[i+1] - y
            dist = math.hypot(dx, dy)
            if dist < BEND_WARP_RADIUS:
                factor = (BEND_WARP_RADIUS - dist)/BEND_WARP_RADIUS
                coords[i] += dx * 0.3 * factor
                coords[i+1] += dy * 0.3 * factor
        # update
        stype = shape_info['type']
        if stype in ("line","brush"):
            self.canvas.coords(shape_id, *coords)
        elif stype in ("rectangle","ellipse"):
            x1,y1,x2,y2 = self.normalize_rect(coords)
            self.canvas.coords(shape_id, x1,y1,x2,y2)
        self.shape_data.update_coords(shape_id, coords)
        self.show_bend_anchors(shape_id)


    def point_segment_dist(self, px, py, x1, y1, x2, y2):
        seg_len_sq = (x2 - x1)**2 + (y2 - y1)**2
        if seg_len_sq == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1)*(x2 - x1) + (py - y1)*(y2 - y1)) / seg_len_sq
        if t < 0:
            return math.hypot(px - x1, py - y1)
        if t > 1:
            return math.hypot(px - x2, py - y2)
        projx = x1 + t*(x2 - x1)
        projy = y1 + t*(y2 - y1)
        return math.hypot(px - projx, py - projy)

    # -------------------------------------------------------------------------
    # SHAPE CREATION
    # -------------------------------------------------------------------------
    def create_brush_segment(self, x, y, layer):
        line_id = self.canvas.create_line(x, y, x+1, y+1, fill=self.stroke_color,
                                          width=self.brush_size)
        layer.add_item(line_id, "brush")
        self.shape_data.store(line_id, "brush", [x,y,x+1,y+1],
                              fill=None, outline=self.stroke_color, width=self.brush_size)
        self.select_item(line_id)

    def finalize_shape_creation(self):
        layer = self.layers[self.current_layer_index]
        stype = self.current_tool.lower()
        layer.add_item(self.temp_item, stype)
        coords = self.canvas.coords(self.temp_item)
        fill_val = None if stype == "line" else self.fill_color
        self.shape_data.store(self.temp_item, stype, coords, fill_val,
                              self.stroke_color, self.brush_size)
        self.select_item(self.temp_item)
        self.temp_item = None

    # -------------------------------------------------------------------------
    # ERASER STUFF
    # -------------------------------------------------------------------------
    def erase_item(self, item_id):
        lyr = self.find_layer_of_item(item_id)
        if lyr:
            lyr.remove_item(item_id)
        self.shape_data.remove(item_id)
        self.canvas.delete(item_id)
        if self.selected_item == item_id:
            self.selected_item = None

    def round_erase_anchor_points(self, item_id, ex, ey):
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        stype = shape_info['type']
        if stype not in ("line","brush"):
            coords = shape_info['coords']
            for i in range(0,len(coords),2):
                dx = coords[i] - ex
                dy = coords[i+1] - ey
                dist = math.hypot(dx, dy)
                if dist < self.eraser_radius:
                    self.erase_item(item_id)
                    return
            return

        coords = shape_info['coords']
        new_points = []
        for i in range(0,len(coords),2):
            dx = coords[i] - ex
            dy = coords[i+1] - ey
            dist = math.hypot(dx, dy)
            if dist >= self.eraser_radius:
                new_points.append(coords[i])
                new_points.append(coords[i+1])
        if len(new_points) < 4:
            self.erase_item(item_id)
            return
        self.canvas.coords(item_id, *new_points)
        self.shape_data.update_coords(item_id, new_points)

    def soft_erase_shape(self, item_id):
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return

        def fade_color(hexcol):
            if not hexcol or len(hexcol) != 7:
                return hexcol
            r = int(hexcol[1:3], 16)
            g = int(hexcol[3:5], 16)
            b = int(hexcol[5:7], 16)
            target = 255
            def fade_channel(c):
                diff = target - c
                if abs(diff) < self.soft_eraser_fade_step:
                    return target
                if diff > 0:
                    return c + self.soft_eraser_fade_step
                return c - self.soft_eraser_fade_step
            nr = fade_channel(r)
            ng = fade_channel(g)
            nb = fade_channel(b)
            return f"#{nr:02x}{ng:02x}{nb:02x}"

        old_outline = shape_info['outline']
        old_fill = shape_info['fill']
        new_outline = fade_color(old_outline)
        new_fill = fade_color(old_fill)
        shape_info['outline'] = new_outline
        shape_info['fill'] = new_fill
        if new_outline:
            self.canvas.itemconfig(item_id, outline=new_outline)
        if new_fill:
            self.canvas.itemconfig(item_id, fill=new_fill)

    # -------------------------------------------------------------------------
    # UTILS
    # -------------------------------------------------------------------------
    def find_layer_of_item(self, item_id):
        for lyr in self.layers:
            for (iid, st) in lyr.items:
                if iid == item_id:
                    return lyr
        return None

    def select_item(self, item_id):
        if self.selected_item:
            old_info = self.shape_data.get(self.selected_item)
            if old_info:
                w = old_info['width']
                try:
                    self.canvas.itemconfig(self.selected_item, width=w)
                except:
                    pass
        self.selected_item = item_id
        if item_id:
            try:
                self.canvas.itemconfig(item_id, width=max(self.brush_size+2,3))
            except:
                pass

    @staticmethod
    def normalize_rect(c):
        x1, y1, x2, y2 = c
        return (min(x1,x2), min(y1,y2),
                max(x1,x2), max(y1,y2))

    def pick_stroke_color(self):
        c = colorchooser.askcolor(title="Choose Stroke Color", initialcolor=self.stroke_color)
        if c and c[1]:
            self.stroke_color = c[1]
            self.stroke_btn.config(bg=self.stroke_color)

    def pick_fill_color(self):
        c = colorchooser.askcolor(title="Choose Fill Color", initialcolor=self.fill_color)
        if c and c[1]:
            self.fill_color = c[1]
            self.fill_btn.config(bg=self.fill_color)

    def on_brush_size_change(self, event=None):
        val = self.brush_size_slider.get()
        self.brush_size = int(float(val))

    def on_font_size_change(self):
        try:
            v = int(self.font_size_spin.get())
            self.font_size = v
        except ValueError:
            pass

    # -------------------------------------------------------------------------
    # UNDO/REDO
    # -------------------------------------------------------------------------
    def on_ctrl_z(self, event=None):
        self.do_undo()

    def on_ctrl_y(self, event=None):
        self.do_redo()

    def do_undo(self):
        st = self.history.undo()
        if st:
            self.apply_history_state(st)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def do_redo(self):
        st = self.history.redo()
        if st:
            self.apply_history_state(st)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    # -------------------------------------------------------------------------
    # OPEN / SAVE
    # -------------------------------------------------------------------------
    def open_image_layer(self):
        fp = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Image Files","*.png;*.jpg;*.jpeg;*.gif;*.bmp"),("All Files","*.*")]
        )
        if not fp:
            return
        try:
            img = Image.open(fp)
            tk_img = ImageTk.PhotoImage(img)
        except Exception as e:
            print("Could not open image:", e)
            return
        layer_name = "ImageLayer_" + fp.split('/')[-1]
        self.add_layer(layer_name)
        iid = self.canvas.create_image(0,0,anchor=tk.NW, image=tk_img)
        # keep reference
        self.canvas.image = tk_img
        self.shape_data.store(iid, "image", [0,0], fill=None, outline=None, width=1)
        self.layers[0].add_item(iid, "image")
        self.push_history(f"Opened image {fp}")

    def save_canvas_snapshot(self):
        fp = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".png",
            filetypes=[("PNG Files","*.png"),("All Files","*.*")]
        )
        if not fp:
            return
        self.canvas.update()
        x0 = self.root.winfo_rootx() + self.canvas.winfo_x()
        y0 = self.root.winfo_rooty() + self.canvas.winfo_y()
        x1 = x0 + self.canvas.winfo_width()
        y1 = y0 + self.canvas.winfo_height()

        try:
            import pyscreenshot as ImageGrab
            snap = ImageGrab.grab(bbox=(x0,y0,x1,y1))
            snap.save(fp)
            print("Saved snapshot to", fp)
        except ImportError:
            print("pyscreenshot not installed.")
        except Exception as e:
            print("Error saving snapshot:", e)

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()

