import tkinter as tk
from tkinter import ttk, filedialog, colorchooser
import copy
import math
from PIL import Image, ImageTk

# ------------------------------------------------------------------------------
# GLOBAL/CONSTANTS
# ------------------------------------------------------------------------------
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14

MAX_HISTORY = 30
ERASER_RADIUS = 15.0
SOFT_ERASER_FADE_STEP = 20

BEND_RADIUS_A = 60.0   # Bend Tool A radius
BEND_RADIUS_B = 50.0   # Bend Tool B radius
BEND_RADIUS_C = 70.0   # Bend Tool C radius

# ------------------------------------------------------------------------------
# LAYER
# ------------------------------------------------------------------------------
class Layer:
    """
    Each layer has:
      - name
      - visibility
      - locked
      - items: list of (canvas_item_id, shape_type)
    """
    def __init__(self, name, visible=True, locked=False):
        self.name = name
        self.visible = visible
        self.locked = locked
        self.items = []

    def add_item(self, item_id, shape_type):
        self.items.append((item_id, shape_type))

    def remove_item(self, item_id):
        self.items = [(iid, s) for (iid, s) in self.items if iid != item_id]

# ------------------------------------------------------------------------------
# SHAPE DATA
# ------------------------------------------------------------------------------
class ShapeData:
    """
    For storing anchor points for each shape so we can bend or direct-select them.
    shape_data[item_id] = {
       'type': 'line'|'rectangle'|'ellipse'|'brush'|'text'|'image'|...,
       'coords': [x1,y1,x2,y2, ...],
       'fill': str or None,
       'outline': str or None,
       'width': float or int
    }
    """
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
    """
    We store up to MAX_HISTORY snapshots. Each is (shape_data_copy, layers_copy, description).
    This allows linear undo/redo plus direct jumps if we want.
    """
    def __init__(self):
        self.states = []
        self.current_index = -1

    def push_state(self, shape_data, layers, description):
        # If we had undone states, chop off anything after current
        if self.current_index < len(self.states) - 1:
            self.states = self.states[:self.current_index+1]
        # If we exceed max, drop the oldest
        if len(self.states) >= MAX_HISTORY:
            del self.states[0]
            self.current_index -= 1

        # Deep-copy shape data
        shape_data_copy = copy.deepcopy(shape_data.shapes)

        # Deep-copy layers
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

    def go_to(self, idx):
        if 0 <= idx < len(self.states):
            self.current_index = idx
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
        root.title("Large Editor with 3 Bend Tools, Full Code, 'Open Image' Fix")
        root.geometry("1400x900")

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

        # For shape creation (line, rect, ellipse)
        self.temp_item = None
        self.start_x = None
        self.start_y = None
        self.last_x = None
        self.last_y = None

        # For "Select" entire shape
        self.moving_shape = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # Direct Select anchors
        self.direct_select_anchors = []
        self.direct_select_dragging_anchor = None
        self.direct_select_drag_index = None

        # Bend Tools
        self.bendA_active = False
        self.bendB_active = False
        self.bendC_active = False
        self.bend_dragging = False
        self.bend_target = None

        # Holds references to loaded images so Python won't garbage-collect them
        self.loaded_images = {}

        self.history = EditorHistory()

        self.build_frames()
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options()
        self.setup_layers_panel()
        self.setup_history_panel()

        # Start with one layer
        self.add_layer("Layer 1")
        self.push_history("Initial Setup")

        # Bind Undo/Redo
        self.root.bind("<Control-z>", self.on_ctrl_z)
        self.root.bind("<Control-y>", self.on_ctrl_y)

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------
    def build_frames(self):
        self.toolbar_frame = tk.Frame(self.root, width=140, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.side_frame = tk.Frame(self.root, width=300, bg="#F0F0F0")
        self.side_frame.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_toolbar(self):
        """
        Tools:
         - Select (entire shape)
         - Direct Select (anchors visible)
         - Bend Tool A
         - Bend Tool B
         - Bend Tool C
         - Brush
         - Line, Rect, Ellipse, Text
         - Sharp, Round, Soft Erasers
        """
        tools = [
            ("Select", None),
            ("Direct Select", None),
            ("Bend Tool A", None),
            ("Bend Tool B", None),
            ("Bend Tool C", None),
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

        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)

    def select_tool(self, tool_name):
        self.current_tool = tool_name

        # reset states
        self.moving_shape = False
        self.direct_select_dragging_anchor = None

        # For bend tools, track which is active
        self.bendA_active = (tool_name == "Bend Tool A")
        self.bendB_active = (tool_name == "Bend Tool B")
        self.bendC_active = (tool_name == "Bend Tool C")
        self.bend_dragging = False
        self.bend_target = None

        self.clear_direct_select_anchors()

        # update button highlights
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
        lb = tk.Label(self.side_frame, text="Layers", bg="#F0F0F0", font=("Arial",12,"bold"))
        lb.pack(pady=5)

        panel = tk.Frame(self.side_frame, bg="#F0F0F0")
        panel.pack(fill=tk.X)

        self.layer_listbox = tk.Listbox(panel)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.layer_listbox.bind("<<ListboxSelect>>", self.on_layer_select)

        sc = tk.Scrollbar(panel, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=sc.set)

        c = tk.Frame(self.side_frame, bg="#F0F0F0")
        c.pack(fill=tk.X)
        tk.Button(c, text="Up", command=self.move_layer_up).pack(side=tk.LEFT, padx=2)
        tk.Button(c, text="Down", command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        tk.Button(c, text="Hide/Show", command=self.toggle_layer_visibility).pack(side=tk.LEFT, padx=2)
        tk.Button(c, text="Delete", command=self.delete_layer).pack(side=tk.LEFT, padx=2)

    def setup_history_panel(self):
        la = tk.Label(self.side_frame, text="History", bg="#F0F0F0", font=("Arial",12,"bold"))
        la.pack(pady=5)
        self.history_listbox = tk.Listbox(self.side_frame)
        self.history_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)

        hf = tk.Frame(self.side_frame, bg="#F0F0F0")
        hf.pack(fill=tk.X)
        tk.Button(hf, text="Undo", command=self.do_undo).pack(side=tk.LEFT, padx=2)
        tk.Button(hf, text="Redo", command=self.do_redo).pack(side=tk.LEFT, padx=2)

    # -------------------------------------------------------------------------
    # LAYER METHODS
    # -------------------------------------------------------------------------
    def add_layer(self, name=None):
        if name is None:
            name = f"Layer {len(self.layers)+1}"
        new_lyr = Layer(name)
        # Insert at the top
        self.layers.insert(0, new_lyr)
        self.layer_listbox.insert(0, name)
        self.layer_listbox.selection_clear(0, tk.END)
        self.layer_listbox.selection_set(0)
        self.on_layer_select(None)
        self.push_history(f"Added layer {name}")

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
        u = self.layer_listbox.get(idx-1)
        c = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx-1, idx)
        self.layer_listbox.insert(idx-1, c)
        self.layer_listbox.insert(idx, u)
        self.layer_listbox.selection_set(idx-1)
        self.current_layer_index = idx-1
        for (iid, st) in self.layers[idx-1].items:
            self.canvas.tag_raise(iid)
        self.push_history(f"Layer {c} moved up")

    def move_layer_down(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers)-1:
            return
        self.layers[idx], self.layers[idx+1] = self.layers[idx+1], self.layers[idx]
        c = self.layer_listbox.get(idx)
        d = self.layer_listbox.get(idx+1)
        self.layer_listbox.delete(idx, idx+1)
        self.layer_listbox.insert(idx, d)
        self.layer_listbox.insert(idx+1, c)
        self.layer_listbox.selection_set(idx+1)
        self.current_layer_index = idx+1
        for (iid, st) in self.layers[idx+1].items:
            self.canvas.tag_lower(iid)
        self.push_history(f"Layer {c} moved down")

    def toggle_layer_visibility(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        l = self.layers[idx]
        l.visible = not l.visible
        new_state = tk.NORMAL if l.visible else tk.HIDDEN
        for (iid, st) in l.items:
            self.canvas.itemconfigure(iid, state=new_state)
        nm = l.name
        if not l.visible:
            nm += " (hidden)"
        self.layer_listbox.delete(idx)
        self.layer_listbox.insert(idx, nm)
        self.layer_listbox.selection_set(idx)
        self.push_history(f"Toggled layer {l.name}")

    def delete_layer(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lay = self.layers[idx]
        for (iid, st) in lay.items:
            self.canvas.delete(iid)
            self.shape_data.remove(iid)
        nm = lay.name
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0
        self.selected_item = None
        self.push_history(f"Deleted layer {nm}")

    # -------------------------------------------------------------------------
    # HISTORY
    # -------------------------------------------------------------------------
    def push_history(self, description):
        self.history.push_state(self.shape_data, self.layers, description)
        self.refresh_history_listbox()

    def refresh_history_listbox(self):
        self.history_listbox.delete(0, tk.END)
        for d in self.history.get_all_descriptions():
            self.history_listbox.insert(tk.END, d)

    def on_history_select(self, event):
        s = self.history_listbox.curselection()
        if not s:
            return
        idx = s[0]
        st = self.history.go_to(idx)
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
        shape_dict, layers_c, desc = state
        self.canvas.delete("all")
        self.shape_data.shapes.clear()
        self.layers.clear()
        self.layer_listbox.delete(0, tk.END)
        self.selected_item = None

        old_to_new = {}
        for old_id, sdata in shape_dict.items():
            stype = sdata['type']
            coords = sdata['coords']
            fill  = sdata['fill']
            outl  = sdata['outline']
            wd    = sdata['width']
            new_id = None
            if stype == "line":
                new_id = self.canvas.create_line(*coords, fill=outl, width=wd)
            elif stype == "rectangle":
                new_id = self.canvas.create_rectangle(*coords, outline=outl, fill=fill, width=wd)
            elif stype == "ellipse":
                new_id = self.canvas.create_oval(*coords, outline=outl, fill=fill, width=wd)
            elif stype == "brush":
                new_id = self.canvas.create_line(*coords, fill=outl, width=wd)
            elif stype == "text":
                # We didn't store the actual text, so place "Sample"
                new_id = self.canvas.create_text(coords[0], coords[1], text="Sample", fill=outl)
            elif stype=="image":
                # We didn't store actual image data => placeholder
                new_id = self.canvas.create_text(coords[0], coords[1],
                                                 text="(Missing image in snapshot)",
                                                 fill="red")
            else:
                new_id = self.canvas.create_line(*coords, fill=outl, width=wd)

            old_to_new[old_id] = new_id
            self.shape_data.shapes[new_id] = copy.deepcopy(sdata)

        for laycopy in layers_c:
            newl = Layer(laycopy.name, laycopy.visible, laycopy.locked)
            ni = []
            for (iid, st) in laycopy.items:
                if iid in old_to_new:
                    ni.append((old_to_new[iid], st))
            newl.items = ni
            self.layers.append(newl)
            lbname = laycopy.name
            if not laycopy.visible:
                lbname += " (hidden)"
            self.layer_listbox.insert(tk.END, lbname)

        # hide items for invisible layers
        for l in self.layers:
            if not l.visible:
                for (iid, st) in l.items:
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
        lay = self.layers[self.current_layer_index]
        if lay.locked or not lay.visible:
            return

        self.start_x, self.start_y = event.x, event.y
        self.last_x, self.last_y   = event.x, event.y

        # Tools
        if self.current_tool == "Select":
            self.handle_select_click(event.x, event.y)
        elif self.current_tool == "Direct Select":
            self.handle_direct_select_down(event.x, event.y)
        elif self.current_tool in ("Bend Tool A","Bend Tool B","Bend Tool C"):
            self.handle_bend_tool_down(event.x, event.y)
        elif self.current_tool == "Brush":
            self.create_brush_segment(event.x, event.y, lay)
        elif self.current_tool in ("Line","Rectangle","Ellipse"):
            self.temp_item = None
        elif self.current_tool == "Text":
            txt = self.canvas.create_text(event.x, event.y, text="Sample",
                                          fill=self.stroke_color, font=("Arial", self.font_size))
            lay.add_item(txt,"text")
            self.shape_data.store(txt, "text", [event.x, event.y],
                                  self.stroke_color, self.stroke_color, 1)
            self.select_item(txt)
            self.push_history("Created text")
        elif self.current_tool == "Sharp Eraser":
            it = self.canvas.find_closest(event.x, event.y)
            if it:
                self.erase_item(it[0])
                self.push_history("Sharp Eraser used")
        elif self.current_tool == "Round Eraser":
            it = self.canvas.find_closest(event.x, event.y)
            if it:
                self.round_erase_anchor_points(it[0], event.x, event.y)
                self.push_history("Round Eraser used")
        elif self.current_tool == "Soft Eraser":
            it = self.canvas.find_closest(event.x, event.y)
            if it:
                self.soft_erase_shape(it[0])
                self.push_history("Soft Eraser used")

    def on_left_drag(self, event):
        if self.current_layer_index is None:
            return
        lay = self.layers[self.current_layer_index]
        if lay.locked or not lay.visible:
            return

        if self.current_tool == "Select" and self.moving_shape and self.selected_item:
            self.move_entire_shape(event.x, event.y)
        elif self.current_tool == "Direct Select" and self.direct_select_dragging_anchor is not None:
            self.handle_direct_select_drag(event.x, event.y)
        elif self.current_tool in ("Bend Tool A","Bend Tool B","Bend Tool C") and self.bend_dragging:
            self.handle_bend_tool_drag(event.x, event.y)
        elif self.current_tool == "Brush":
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            if abs(dx) > 1 or abs(dy) > 1:
                ln_id = self.canvas.create_line(self.last_x, self.last_y, event.x, event.y,
                                                fill=self.stroke_color, width=self.brush_size)
                lay.add_item(ln_id,"brush")
                self.shape_data.store(ln_id, "brush",
                                      [self.last_x, self.last_y, event.x, event.y],
                                      None, self.stroke_color, self.brush_size)
                self.select_item(ln_id)
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
            x1, y1, x2, y2 = self.normalize_rect([self.start_x, self.start_y, event.x, event.y])
            self.temp_item = self.canvas.create_rectangle(x1, y1, x2, y2,
                                                          outline=self.stroke_color,
                                                          fill=self.fill_color,
                                                          width=self.brush_size)
        elif self.current_tool == "Ellipse":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            x1, y1, x2, y2 = self.normalize_rect([self.start_x, self.start_y, event.x, event.y])
            self.temp_item = self.canvas.create_oval(x1, y1, x2, y2,
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
            self.push_history("DirectSelect anchor move")
            return

        if self.current_tool in ("Bend Tool A","Bend Tool B","Bend Tool C") and self.bend_dragging:
            self.bend_dragging = False
            self.bend_target = None
            self.push_history(f"Bent shape with {self.current_tool}")
            return

        if self.temp_item and self.current_tool in ("Line","Rectangle","Ellipse"):
            self.finalize_shape_creation()
            self.push_history(f"Created {self.current_tool}")

    # -------------------------------------------------------------------------
    # SELECT (MOVE ENTIRE SHAPE)
    # -------------------------------------------------------------------------
    def handle_select_click(self, x, y):
        it = self.canvas.find_closest(x, y)
        if it:
            iid = it[0]
            l = self.find_layer_of_item(iid)
            if l and not l.locked:
                self.select_item(iid)
                shapeinf = self.shape_data.get(iid)
                if shapeinf:
                    coords = self.canvas.coords(iid)
                    self.drag_offset_x = x - coords[0]
                    self.drag_offset_y = y - coords[1]
                    self.moving_shape = True
                else:
                    self.moving_shape = False
            else:
                self.select_item(None)
        else:
            self.select_item(None)

    def move_entire_shape(self, x, y):
        dx = x - self.last_x
        dy = y - self.last_y
        self.canvas.move(self.selected_item, dx, dy)
        shapeinf = self.shape_data.get(self.selected_item)
        if shapeinf:
            coords = shapeinf['coords']
            for i in range(0, len(coords), 2):
                coords[i]   += dx
                coords[i+1] += dy
            self.canvas.coords(self.selected_item, *coords)
            self.shape_data.update_coords(self.selected_item, coords)
        self.last_x, self.last_y = x, y

    # -------------------------------------------------------------------------
    # DIRECT SELECT (ANCHORS)
    # -------------------------------------------------------------------------
    def handle_direct_select_down(self, x, y):
        # If we have anchors, check if we clicked one
        if self.direct_select_anchors:
            h = self.find_direct_anchor(x, y)
            if h is not None:
                shape_id, idx = h
                self.direct_select_dragging_anchor = shape_id
                self.direct_select_drag_index = idx
                return
        # else maybe new shape selection
        it = self.canvas.find_closest(x, y)
        if it:
            iid = it[0]
            l = self.find_layer_of_item(iid)
            if l and not l.locked:
                self.select_item(iid)
                self.show_direct_select_anchors(iid)
            else:
                self.select_item(None)
                self.clear_direct_select_anchors()
        else:
            self.select_item(None)
            self.clear_direct_select_anchors()

    def handle_direct_select_drag(self, x, y):
        if not self.direct_select_dragging_anchor:
            return
        shapeinf = self.shape_data.get(self.direct_select_dragging_anchor)
        if not shapeinf:
            return
        coords = shapeinf['coords']
        idx = self.direct_select_drag_index
        coords[idx]   = x
        coords[idx+1] = y
        stype = shapeinf['type']
        if stype in ("line", "brush"):
            self.canvas.coords(self.direct_select_dragging_anchor, *coords)
        elif stype in ("rectangle", "ellipse"):
            x1, y1, x2, y2 = self.normalize_rect(coords)
            self.canvas.coords(self.direct_select_dragging_anchor, x1, y1, x2, y2)
        elif stype == "text":
            self.canvas.coords(self.direct_select_dragging_anchor, coords[0], coords[1])
        self.shape_data.update_coords(self.direct_select_dragging_anchor, coords)
        self.update_direct_select_anchors(self.direct_select_dragging_anchor)

    def clear_direct_select_anchors(self):
        for (hid, sid, idx) in self.direct_select_anchors:
            self.canvas.delete(hid)
        self.direct_select_anchors.clear()

    def show_direct_select_anchors(self, item_id):
        self.clear_direct_select_anchors()
        shapeinf = self.shape_data.get(item_id)
        if not shapeinf:
            return
        coords = shapeinf['coords']
        for i in range(0, len(coords), 2):
            x = coords[i]
            y = coords[i+1]
            h = self.canvas.create_rectangle(x-3, y-3, x+3, y+3, fill="blue", outline="blue")
            self.direct_select_anchors.append((h, item_id, i))

    def update_direct_select_anchors(self, item_id):
        shapeinf = self.shape_data.get(item_id)
        if not shapeinf:
            return
        coords = shapeinf['coords']
        for (hid, sid, idx) in self.direct_select_anchors:
            if sid == item_id:
                x = coords[idx]
                y = coords[idx+1]
                self.canvas.coords(hid, x-3, y-3, x+3, y+3)

    def find_direct_anchor(self, x, y):
        rad = 5
        for (hid, sid, idx) in self.direct_select_anchors:
            hx1, hy1, hx2, hy2 = self.canvas.coords(hid)
            if (hx1-rad < x < hx2+rad) and (hy1-rad < y < hy2+rad):
                return (sid, idx)
        return None

    # -------------------------------------------------------------------------
    # BEND TOOLS
    # -------------------------------------------------------------------------
    def handle_bend_tool_down(self, x, y):
        """
        For each Bend Tool (A,B,C), we do line-based manipulations.
        1) find line or brush shape near the mouse
        2) store last_x,y so we get a real dx,dy in the drag
        3) subdivide if needed
        4) set bend_dragging so we can keep warping as we move
        """
        item = self.canvas.find_closest(x, y)
        if not item:
            self.select_item(None)
            return
        iid = item[0]
        shape = self.shape_data.get(iid)
        if not shape:
            self.select_item(None)
            return
        stype = shape['type']
        if stype not in ("line","brush"):
            # skip rectangles/ellipses/text etc
            self.select_item(None)
            return
        self.select_item(iid)
        self.bend_dragging = True
        self.bend_target = iid

        # Make sure we can get a visible warp: store the "last" for dx/dy
        self.last_x = x
        self.last_y = y

        # If line is only two endpoints, subdivide once
        coords = shape['coords']
        if len(coords) < 4:
            # Insert midpoint so there's something to bend
            midx = (coords[0] + coords[2]) / 2
            midy = (coords[1] + coords[3]) / 2
            coords.insert(2, midy)
            coords.insert(2, midx)
            self.canvas.coords(iid, *coords)
            self.shape_data.update_coords(iid, coords)

    def handle_bend_tool_drag(self, x, y):
        """
        We do separate logic for A,B,C. All line-based manip.
        Then we update the canvas coords and shape_data accordingly.
        """
        if not self.bend_dragging or not self.bend_target:
            return
        shapeinf = self.shape_data.get(self.bend_target)
        if not shapeinf:
            return
        stype = shapeinf['type']
        if stype not in ("line","brush"):
            return

        coords = shapeinf['coords']

        if self.current_tool == "Bend Tool A":
            self.bend_tool_a(coords, x, y)
        elif self.current_tool == "Bend Tool B":
            self.bend_tool_b(coords, x, y)
        elif self.current_tool == "Bend Tool C":
            self.bend_tool_c(coords, x, y)

        # Update line with new coords
        self.canvas.coords(self.bend_target, *coords)
        self.shape_data.update_coords(self.bend_target, coords)

        # Update last_x,y so the warp accumulates
        self.last_x, self.last_y = x, y

    def bend_tool_a(self, coords, mx, my):
        """
        'Bend Tool A': find the segment nearest mouse, nudge it.
         - We'll move the midpoint and partially move endpoints.
        """
        # We want the local mouse movement:
        dx = mx - self.last_x
        dy = my - self.last_y
        if abs(dx) < 0.0001 and abs(dy) < 0.0001:
            return

        # Find closest segment
        best_i = None
        best_dist = float("inf")
        for i in range(0, len(coords)-2, 2):
            x1, y1 = coords[i], coords[i+1]
            x2, y2 = coords[i+2], coords[i+3]
            d = self.point_segment_dist(mx, my, x1, y1, x2, y2)
            if d < best_dist:
                best_dist = d
                best_i = i
        if best_i is None:
            return

        # shift the endpoints of that segment slightly
        coords[best_i]     += dx * 0.4
        coords[best_i + 1] += dy * 0.4
        coords[best_i + 2] += dx * 0.4
        coords[best_i + 3] += dy * 0.4

    def bend_tool_b(self, coords, mx, my):
        """
        'Bend Tool B': arc bend. Find points near the mouse, turn them into an arc
        from the earliest to the latest of those near points, giving a bulge.
        """
        near_ix = []
        for i in range(0, len(coords), 2):
            px, py = coords[i], coords[i+1]
            d = math.hypot(px - mx, py - my)
            if d < BEND_RADIUS_B:
                near_ix.append(i)
        if len(near_ix) < 2:
            return
        start_i = min(near_ix)
        end_i   = max(near_ix)
        sx, sy = coords[start_i], coords[start_i+1]
        ex, ey = coords[end_i], coords[end_i+1]
        steps = (end_i - start_i)//2 + 1

        # We'll bulge in the direction of mouse offset from the midpoint
        midx = (sx + ex)/2
        midy = (sy + ey)/2
        dx   = mx - midx
        dy   = my - midy

        for step in range(steps):
            t = step / max(1, steps-1)
            # basic linear interpolation
            xx = sx + t*(ex - sx)
            yy = sy + t*(ey - sy)
            # sine bulge factor
            bulge = math.sin(t*math.pi)*0.4
            x2 = xx + dx*bulge
            y2 = yy + dy*bulge
            real_i = start_i + step*2
            if real_i+1 < len(coords):
                coords[real_i]   = x2
                coords[real_i+1] = y2

    def bend_tool_c(self, coords, mx, my):
        """
        'Bend Tool C': radial warp. We push/pull all points near the mouse by a fraction.
        """
        dx = mx - self.last_x
        dy = my - self.last_y
        if abs(dx) < 0.0001 and abs(dy) < 0.0001:
            return

        for i in range(0, len(coords), 2):
            px, py = coords[i], coords[i+1]
            dist = math.hypot(px - mx, py - my)
            if dist < BEND_RADIUS_C:
                factor = (BEND_RADIUS_C - dist)/BEND_RADIUS_C
                coords[i]   += dx * factor
                coords[i+1] += dy * factor

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
        ln = self.canvas.create_line(x, y, x+1, y+1,
                                     fill=self.stroke_color,
                                     width=self.brush_size)
        layer.add_item(ln,"brush")
        self.shape_data.store(ln, "brush", [x, y, x+1, y+1],
                              None, self.stroke_color, self.brush_size)
        self.select_item(ln)

    def finalize_shape_creation(self):
        layer = self.layers[self.current_layer_index]
        stype = self.current_tool.lower()
        layer.add_item(self.temp_item, stype)
        coords = self.canvas.coords(self.temp_item)
        fill_val = None if stype=="line" else self.fill_color
        self.shape_data.store(self.temp_item, stype, coords,
                              fill_val, self.stroke_color, self.brush_size)
        self.select_item(self.temp_item)
        self.temp_item = None

    # -------------------------------------------------------------------------
    # ERASERS
    # -------------------------------------------------------------------------
    def erase_item(self, item_id):
        l = self.find_layer_of_item(item_id)
        if l:
            l.remove_item(item_id)
        self.shape_data.remove(item_id)
        self.canvas.delete(item_id)
        if self.selected_item == item_id:
            self.selected_item = None

    def round_erase_anchor_points(self, item_id, ex, ey):
        shape = self.shape_data.get(item_id)
        if not shape:
            return
        stype = shape['type']
        if stype not in ("line","brush"):
            # For rectangles or other shapes, simply check if center is near
            c = shape['coords']
            for i in range(0, len(c), 2):
                dx = c[i] - ex
                dy = c[i+1] - ey
                d  = math.hypot(dx, dy)
                if d < ERASER_RADIUS:
                    self.erase_item(item_id)
                    return
            return
        # For line/brush, remove anchor points that are too close
        coords = shape['coords']
        newp = []
        for i in range(0, len(coords), 2):
            dx = coords[i]   - ex
            dy = coords[i+1] - ey
            d  = math.hypot(dx, dy)
            if d >= ERASER_RADIUS:
                newp.append(coords[i])
                newp.append(coords[i+1])
        if len(newp) < 4:
            self.erase_item(item_id)
            return
        self.canvas.coords(item_id, *newp)
        self.shape_data.update_coords(item_id, newp)

    def soft_erase_shape(self, item_id):
        shape = self.shape_data.get(item_id)
        if not shape:
            return
        def fade_color(hc):
            if not hc or len(hc)!=7:
                return hc
            r = int(hc[1:3],16)
            g = int(hc[3:5],16)
            b = int(hc[5:7],16)
            target=255
            def fch(c):
                diff = target - c
                if abs(diff) < SOFT_ERASER_FADE_STEP:
                    return target
                if diff > 0:
                    return c + SOFT_ERASER_FADE_STEP
                return c - SOFT_ERASER_FADE_STEP
            rr = fch(r)
            gg = fch(g)
            bb = fch(b)
            return f"#{rr:02x}{gg:02x}{bb:02x}"

        outline = shape['outline']
        fill    = shape['fill']
        no = fade_color(outline)
        nf = fade_color(fill)
        shape['outline'] = no
        shape['fill']    = nf
        if no:
            self.canvas.itemconfig(item_id, outline=no)
        if nf:
            self.canvas.itemconfig(item_id, fill=nf)

    # -------------------------------------------------------------------------
    # UTILS
    # -------------------------------------------------------------------------
    def find_layer_of_item(self, item_id):
        for ly in self.layers:
            for (iid, st) in ly.items:
                if iid == item_id:
                    return ly
        return None

    def select_item(self, item_id):
        # Clear highlight on old selection
        if self.selected_item:
            old = self.shape_data.get(self.selected_item)
            if old:
                w = old['width']
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
        x1,y1,x2,y2 = c
        return (min(x1,x2), min(y1,y2),
                max(x1,x2), max(y1,y2))

    def pick_stroke_color(self):
        col = colorchooser.askcolor(title="Stroke Color", initialcolor=self.stroke_color)
        if col and col[1]:
            self.stroke_color = col[1]
            self.stroke_btn.config(bg=self.stroke_color)

    def pick_fill_color(self):
        col = colorchooser.askcolor(title="Fill Color", initialcolor=self.fill_color)
        if col and col[1]:
            self.fill_color = col[1]
            self.fill_btn.config(bg=col[1])

    def on_brush_size_change(self, event=None):
        v = self.brush_size_slider.get()
        self.brush_size = int(float(v))

    def on_font_size_change(self):
        try:
            vv = int(self.font_size_spin.get())
            self.font_size = vv
        except:
            pass

    # -------------------------------------------------------------------------
    # OPEN / SAVE
    # -------------------------------------------------------------------------
    def open_image_layer(self):
        fp = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Image Files","*.png;*.jpg;*.jpeg;*.gif;*.bmp"),
                       ("All Files","*.*")]
        )
        if not fp:
            return
        try:
            img = Image.open(fp)
            tkimg = ImageTk.PhotoImage(img)
        except Exception as e:
            print("Error opening image:", e)
            return

        # If no layer selected, create one
        if self.current_layer_index is None:
            if not self.layers:
                self.add_layer("Layer 1")
            else:
                self.current_layer_index = 0

        # Place image in current layer
        lay = self.layers[self.current_layer_index]
        iid = self.canvas.create_image(0, 0, anchor=tk.NW, image=tkimg)
        self.loaded_images[iid] = tkimg  # keep a reference

        # Store shape data
        self.shape_data.store(iid, "image", [0,0], None, None, 1)
        lay.add_item(iid, "image")

        self.push_history(f"Opened image {fp}")

    def save_canvas_snapshot(self):
        fp = filedialog.asksaveasfilename(
            title="Save",
            defaultextension=".png",
            filetypes=[("PNG Files","*.png"), ("All","*.*")]
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
            shot = ImageGrab.grab(bbox=(x0, y0, x1, y1))
            shot.save(fp)
            print("Saved snapshot to", fp)
        except ImportError:
            print("pyscreenshot not installed. Can't save snapshot.")
        except Exception as e:
            print("Error saving snapshot:", e)


# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
if __name__=="__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()

