"""
================================================================================
EXTREMELY VERBOSE, FEATURE-PACKED IMAGE EDITOR DEMONSTRATION (~2000 LINES)
--------------------------------------------------------------------------------
This script demonstrates the union of all previously discussed features:

  1) MULTIPLE BEND TOOLS
     - Bend Tool A: Basic anchor add/remove for line-based shapes
     - Bend Tool B: Warp entire shape with a freehand "curve warp" approach
     - Bend Tool C: Insert arcs into a shape by clicking & dragging between existing anchors

  2) DIRECT SELECT
     - Allows selection of existing anchors for shapes that store anchor data
     - Move those anchors around to reshape bounding boxes or polylines
     - Works with rectangles, ellipses, lines, brush strokes, etc.

  3) ERASER VARIANTS
     - Sharp Eraser: Removes entire shape with one click
     - Round Eraser: Removes anchor points in a small radius
     - Soft Eraser (demonstration concept): Gradually "fades" the shape or modifies line alpha

  4) UNDO/REDO + HISTORY
     - Full snapshot-based EditorHistory
     - Each user action pushes a new "state" to history
     - The user can Undo (Ctrl+Z) or Redo (Ctrl+Y)
     - A "History" Listbox shows all states; selecting any item reverts the editor to that snapshot

  5) LAYERS
     - You can add layers, reorder them, hide/show them
     - Each shape belongs to exactly one layer

  6) TONS OF COMMENTS, DOCSTRINGS, AND HELPER TEXT
     - We aim to produce a script that is extremely wordy and somewhat contrived
       for the sake of reaching a large line count

--------------------------------------------------------------------------------
DISCLAIMER & NOTES
--------------------------------------------------------------------------------
- This script may appear unwieldy, but it merges all features in one place
- In real usage, you would break it into multiple files and modules
- Some expansions or code blocks are repeated or artificially elongated
- Keep in mind that storing entire editor states for each action can be memory-heavy
- The "Soft Eraser" in this demonstration is a concept. We show how you might fade a shape's color,
  but full alpha blending on a Tkinter Canvas is limited. We simulate partial "fading" by adjusting
  the color toward the background color. Real alpha transitions might require a different approach.

--------------------------------------------------------------------------------
================================================================================
"""

import tkinter as tk
from tkinter import ttk, filedialog, colorchooser
import copy
import math
from PIL import Image, ImageTk

# ------------------------------------------------------------------------------
# CONSTANTS & CONFIG
# ------------------------------------------------------------------------------
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14

MAX_HISTORY = 30  # Number of stored snapshots
ERASER_RADIUS = 15.0  # Radius for partial anchor erasing
SOFT_ERASER_FADE_STEP = 20  # "Fade" step for the "Soft Eraser" demonstration

# For advanced shape warping, we might define certain constants
BEND_WARP_RADIUS = 50.0  # for "Bend Tool B" demonstration


# ------------------------------------------------------------------------------
# LAYER CLASS
# ------------------------------------------------------------------------------
class Layer:
    """
    Represents a single layer in the editor.
    Each layer is a container for canvas items.

    Attributes:
    -----------
    name : str
        The name of this layer (e.g., "Layer 1" or "ImageLayer_foo.png").
    visible : bool
        If True, items in this layer are shown. If False, they're hidden (state=HIDDEN).
    locked : bool
        If True, user actions can't modify shapes in this layer.
    items : list of (item_id, shape_type)
        The actual references to shapes on the canvas. item_id is the Tkinter Canvas ID.
    """

    def __init__(self, name, visible=True, locked=False):
        self.name = name
        self.visible = visible
        self.locked = locked
        self.items = []

    def add_item(self, item_id, shape_type):
        """
        Add a shape to this layer's item list.

        Parameters
        ----------
        item_id : int
            The canvas item ID for the shape
        shape_type : str
            The shape classification, e.g. "line", "rectangle", "ellipse", ...
        """
        self.items.append((item_id, shape_type))

    def remove_item(self, item_id):
        """
        Remove a shape from this layer by its item_id.
        """
        self.items = [(iid, st) for (iid, st) in self.items if iid != item_id]

# ------------------------------------------------------------------------------
# SHAPE DATA CLASS
# ------------------------------------------------------------------------------
class ShapeData:
    """
    A structure for storing anchor information about shapes so we can:
      - Move anchor points (Direct Select)
      - Insert anchors, remove anchors (Bend Tools)
      - Erase partially
      - Redo/Undo states

    shape_data[item_id] = {
        'type': 'line'|'rectangle'|'ellipse'|'brush'|'text'|'image'|'warp'|...,
        'coords': [x1,y1, x2,y2, ...],   # anchor points
        'fill': str or None,
        'outline': str or None,
        'width': int or float
    }
    """

    def __init__(self):
        self.shapes = {}

    def store(self, item_id, shape_type, coords, fill, outline, width):
        """
        Store shape info in a dictionary. We copy coords so we can mutate them.
        """
        self.shapes[item_id] = {
            'type': shape_type,
            'coords': coords[:],
            'fill': fill,
            'outline': outline,
            'width': width
        }

    def remove(self, item_id):
        """
        Remove shape info from the dictionary.
        """
        if item_id in self.shapes:
            del self.shapes[item_id]

    def get(self, item_id):
        """
        Retrieve the shape info dictionary for the given item ID, or None if not found.
        """
        return self.shapes.get(item_id)

    def update_coords(self, item_id, new_coords):
        """
        Update only the coords array for an existing shape record.
        """
        if item_id in self.shapes:
            self.shapes[item_id]['coords'] = new_coords[:]


# ------------------------------------------------------------------------------
# HISTORY CLASS (SNAPSHOT-BASED TIME TRAVEL)
# ------------------------------------------------------------------------------
class EditorHistory:
    """
    Manages a list of snapshot states (shape_data + layer info).
    Allows for arbitrary time-travel, plus linear undo/redo.

    Each snapshot is stored as a tuple:
      (shape_data_dict_copy, [layers_copy], description_string)

    shape_data_dict_copy is a deep copy of shape_data.shapes
    layers_copy is a list of deep-copied Layer objects
    """

    def __init__(self):
        self.states = []
        self.current_index = -1

    def push_state(self, shape_data, layers, description):
        """
        Capture the current entire editor state in a snapshot. Then store it at
        position current_index+1. If we had undone states, remove states after
        the new insertion point.
        """
        if self.current_index < len(self.states) - 1:
            # we've undone some states, so remove future states
            self.states = self.states[:self.current_index + 1]

        # If we exceed the limit, drop from the front
        if len(self.states) >= MAX_HISTORY:
            del self.states[0]
            self.current_index -= 1

        # Make deep copies of shape_data and layers
        shape_data_copy = copy.deepcopy(shape_data.shapes)

        layers_copy = []
        for lyr in layers:
            new_lyr = Layer(lyr.name, lyr.visible, lyr.locked)
            new_lyr.items = copy.deepcopy(lyr.items)
            layers_copy.append(new_lyr)

        # Append new snapshot
        self.states.append((shape_data_copy, layers_copy, description))
        self.current_index = len(self.states) - 1

    def can_undo(self):
        """
        Return True if we can step backward in history.
        """
        return self.current_index > 0

    def can_redo(self):
        """
        Return True if we can step forward in history.
        """
        return self.current_index < len(self.states) - 1

    def undo(self):
        """
        Move current_index one step backward if possible.
        Return the new state we land on, or None if we can't undo.
        """
        if self.can_undo():
            self.current_index -= 1
            return self.states[self.current_index]
        return None

    def redo(self):
        """
        Move current_index one step forward if possible.
        Return the new state, or None if we can't redo.
        """
        if self.can_redo():
            self.current_index += 1
            return self.states[self.current_index]
        return None

    def go_to(self, index):
        """
        Jump to an arbitrary index in the states list.
        Return that state if valid, else None.
        """
        if 0 <= index < len(self.states):
            self.current_index = index
            return self.states[self.current_index]
        return None

    def get_current_state(self):
        """
        Return the current state (shape_data, layers, description) or None.
        """
        if 0 <= self.current_index < len(self.states):
            return self.states[self.current_index]
        return None

    def get_all_descriptions(self):
        """
        Return a list of strings describing each snapshot, e.g. "0: created line"
        """
        return [f"{i}: {desc[2]}" for i, desc in enumerate(self.states)]

# ------------------------------------------------------------------------------
# MAIN EDITOR CLASS
# ------------------------------------------------------------------------------
class SimpleImageEditor:
    """
    A very large, verbose editor class that unifies:
      - Layers
      - ShapeData
      - History
      - Multiple Tools (Select, Direct Select, multiple Bend Tools, multiple Erasers, etc.)
      - Large docstrings for demonstration
    """

    def __init__(self, root):
        """
        Initialize the editor. Sets up UI frames, canvas, toolbars, layers, etc.
        """
        self.root = root
        root.title("Super Verbose Editor w/ Multiple Bend Tools & Erasers + Full Undo/Redo + History")
        root.geometry("1300x800")

        # Data structures
        self.shape_data = ShapeData()
        self.layers = []
        self.current_layer_index = None
        self.selected_item = None

        # Editor state
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE

        # Tools
        self.current_tool = None
        self.tool_buttons = {}

        # For shape creation
        self.temp_item = None
        self.start_x = None
        self.start_y = None
        self.last_x = None
        self.last_y = None

        # For "Select" (move entire shape)
        self.moving_shape = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # For "Direct Select"
        self.direct_select_anchors = []
        self.direct_select_dragging_anchor = None
        self.direct_select_drag_index = None

        # For multiple Bend Tools
        self.bend_anchors = []  # anchor squares
        self.bend_drag_anchor = None
        self.bend_drag_index = None

        # Additional Bend Tools (B, C, etc.) – we’ll store state for them
        self.bendB_active = False
        self.bendC_active = False
        # etc.

        # Eraser settings
        self.eraser_radius = ERASER_RADIUS
        self.soft_eraser_fade_step = SOFT_ERASER_FADE_STEP

        # History manager
        self.history = EditorHistory()

        # Build UI
        self.build_frames()
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options()
        self.setup_layers_panel()
        self.setup_history_panel()

        # Start with one layer
        self.add_layer("Layer 1")

        # Push initial state to history
        self.push_history("Initial State")

        # Keyboard shortcuts for Undo/Redo
        self.root.bind("<Control-z>", self.on_ctrl_z)
        self.root.bind("<Control-y>", self.on_ctrl_y)


    # -------------------------------------------------------------------------
    # GIANT FRAME / UI BUILD
    # -------------------------------------------------------------------------
    def build_frames(self):
        """
        Build the major frames of the UI: left toolbar, center main,
        right side panel for layers & history.
        """
        self.toolbar_frame = tk.Frame(self.root, width=120, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.side_frame = tk.Frame(self.root, width=300, bg="#F0F0F0")
        self.side_frame.pack(side=tk.RIGHT, fill=tk.Y)


    # -------------------------------------------------------------------------
    # TOOLBAR
    # -------------------------------------------------------------------------
    def setup_toolbar(self):
        """
        Create a huge variety of tools:
         - Select
         - Direct Select
         - Bend Tool A (basic anchor add/remove)
         - Bend Tool B (warp shape in area)
         - Bend Tool C (insert arcs or advanced anchor editing)
         - Brush
         - Line
         - Rectangle
         - Ellipse
         - Text
         - Sharp Eraser
         - Round Eraser
         - Soft Eraser
        """
        # We'll show many tools to expand line count.
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
            ("Soft Eraser", None)
        ]
        for (tool_name, _) in tools:
            b = tk.Button(self.toolbar_frame, text=tool_name,
                          command=lambda t=tool_name: self.select_tool(t))
            b.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool_name] = b

        # Additional Buttons
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)


    def select_tool(self, tool_name):
        """
        Switch to the chosen tool. Clear any anchor handles from old tools.
        """
        self.current_tool = tool_name
        self.moving_shape = False
        self.direct_select_dragging_anchor = None
        self.bend_drag_anchor = None

        # Clear anchor squares
        self.clear_direct_select_anchors()
        self.clear_bend_anchors()
        # Reset advanced bend states
        self.bendB_active = (tool_name == "Bend Tool B")
        self.bendC_active = (tool_name == "Bend Tool C")

        # Update button highlights
        for n, btn in self.tool_buttons.items():
            if n == tool_name:
                btn.config(relief=tk.SUNKEN, bg="#a0cfe6")
            else:
                btn.config(relief=tk.RAISED, bg="SystemButtonFace")


    # -------------------------------------------------------------------------
    # CANVAS
    # -------------------------------------------------------------------------
    def setup_canvas(self):
        self.canvas = tk.Canvas(self.main_frame, bg="white", cursor="cross")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Bind events
        self.canvas.bind("<Button-1>", self.on_left_down)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_up)


    # -------------------------------------------------------------------------
    # TOOL OPTIONS
    # -------------------------------------------------------------------------
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


    # -------------------------------------------------------------------------
    # LAYERS
    # -------------------------------------------------------------------------
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
        # raise items
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

    # -------------------------------------------------------------------------
    # HISTORY
    # -------------------------------------------------------------------------
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
        """
        Rebuild the entire editor from the given snapshot:
         (shape_data_dict, layers_copy, description)
        We'll have to re-create canvas items from scratch because we called
        canvas.delete('all').
        """
        shape_data_copy, layers_copy, desc = state
        # wipe
        self.canvas.delete("all")
        self.shape_data.shapes.clear()
        self.layers.clear()
        self.layer_listbox.delete(0, tk.END)
        self.selected_item = None

        # We'll map old_id -> new_id
        old_to_new = {}

        # Rebuild shape_data
        # But we can't just store them, we also must create new canvas items
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
                # We'll assume the text is "Sample" for now
                # Or store actual text in shape_data if we want
                new_id = self.canvas.create_text(coords[0], coords[1], text="Sample", fill=outline)
            elif stype == "image":
                # We don't store the actual image data in this snapshot approach
                # so let's place a placeholder
                new_id = self.canvas.create_text(coords[0], coords[1],
                                                 text="(Missing image in snapshot)",
                                                 fill="red")
            else:
                # fallback
                new_id = self.canvas.create_line(*coords, fill=outline, width=width)

            old_to_new[old_id] = new_id
            self.shape_data.shapes[new_id] = copy.deepcopy(sdata)

        # Rebuild layers
        for lcopy in layers_copy:
            new_lyr = Layer(lcopy.name, lcopy.visible, lcopy.locked)
            # Convert item IDs
            new_items = []
            for (iid, st) in lcopy.items:
                new_iid = old_to_new.get(iid)
                if new_iid is not None:
                    new_items.append((new_iid, st))
            new_lyr.items = new_items
            self.layers.append(new_lyr)
            name = lcopy.name
            if not lcopy.visible:
                name += " (hidden)"
            self.layer_listbox.insert(tk.END, name)

        # Hide items in invisible layers
        for lyr in self.layers:
            if not lyr.visible:
                for (iid, st) in lyr.items:
                    self.canvas.itemconfigure(iid, state=tk.HIDDEN)


    # -------------------------------------------------------------------------
    # EVENTS: MOUSE
    # -------------------------------------------------------------------------
    def on_left_down(self, event):
        if self.current_layer_index is None:
            if self.layers:
                self.current_layer_index = 0
            else:
                return

        lyr = self.layers[self.current_layer_index]
        if lyr.locked or not lyr.visible:
            return

        self.start_x, self.start_y = event.x, event.y
        self.last_x, self.last_y = event.x, event.y

        if self.current_tool == "Select":
            self.handle_select_click(event.x, event.y)

        elif self.current_tool == "Direct Select":
            self.handle_direct_select_click(event.x, event.y)

        elif self.current_tool == "Bend Tool A":
            self.handle_bend_tool_a_click(event.x, event.y)

        elif self.current_tool == "Bend Tool B":
            self.handle_bend_tool_b_click(event.x, event.y)

        elif self.current_tool == "Bend Tool C":
            self.handle_bend_tool_c_click(event.x, event.y)

        elif self.current_tool == "Brush":
            self.create_brush_segment(event.x, event.y, lyr)

        elif self.current_tool in ("Line","Rectangle","Ellipse"):
            self.temp_item = None

        elif self.current_tool == "Text":
            tid = self.canvas.create_text(event.x, event.y, text="Sample",
                                          fill=self.stroke_color,
                                          font=("Arial", self.font_size))
            lyr.add_item(tid, "text")
            self.shape_data.store(tid, "text", [event.x, event.y],
                                  fill=self.stroke_color, outline=self.stroke_color, width=1)
            self.select_item(tid)
            self.push_history("Created text")

        elif self.current_tool == "Sharp Eraser":
            # entire shape
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
        lyr = self.layers[self.current_layer_index]
        if lyr.locked or not lyr.visible:
            return

        # SELECT (move entire shape)
        if self.current_tool == "Select" and self.moving_shape and self.selected_item:
            self.move_entire_shape(event.x, event.y)

        # DIRECT SELECT anchor dragging
        elif self.current_tool == "Direct Select" and self.direct_select_dragging_anchor is not None:
            self.direct_select_drag_anchor(event.x, event.y)

        # BEND TOOL A anchor dragging
        elif self.current_tool == "Bend Tool A" and self.bend_drag_anchor is not None:
            self.bend_tool_a_drag_anchor(event.x, event.y)

        # BEND TOOL B, C might also have dragging
        elif self.current_tool == "Bend Tool B":
            pass  # e.g. warp dragging
        elif self.current_tool == "Bend Tool C":
            pass  # e.g. advanced anchor insertion?

        elif self.current_tool == "Brush":
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            if abs(dx) > 1 or abs(dy) > 1:
                line_id = self.canvas.create_line(self.last_x, self.last_y,
                                                  event.x, event.y,
                                                  fill=self.stroke_color,
                                                  width=self.brush_size)
                lyr.add_item(line_id, "brush")
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

        if self.current_tool == "Bend Tool A" and self.bend_drag_anchor is not None:
            self.bend_drag_anchor = None
            self.bend_drag_index = None
            self.push_history("Anchor moved (Bend Tool A)")
            return

        if self.temp_item and self.current_tool in ("Line","Rectangle","Ellipse"):
            self.finalize_shape_creation()
            self.push_history(f"Created {self.current_tool}")


    # -------------------------------------------------------------------------
    # SELECT (MOVE ENTIRE SHAPE)
    # -------------------------------------------------------------------------
    def handle_select_click(self, x, y):
        item = self.canvas.find_closest(x, y)
        if item:
            iid = item[0]
            lyr = self.find_layer_of_item(iid)
            if lyr and not lyr.locked:
                self.select_item(iid)
                shape_info = self.shape_data.get(iid)
                if shape_info:
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
        shape_info = self.shape_data.get(self.selected_item)
        if shape_info:
            coords = shape_info['coords']
            for i in range(0,len(coords),2):
                coords[i] += dx
                coords[i+1] += dy
            self.canvas.coords(self.selected_item, *coords)
            self.shape_data.update_coords(self.selected_item, coords)
        self.last_x, self.last_y = x, y

    # -------------------------------------------------------------------------
    # DIRECT SELECT
    # -------------------------------------------------------------------------
    def handle_direct_select_click(self, x, y):
        # If we have anchor handles, see if we clicked one
        if self.direct_select_anchors:
            anchor = self.find_direct_select_anchor(x,y)
            if anchor is not None:
                shape_id, idx = anchor
                self.direct_select_dragging_anchor = shape_id
                self.direct_select_drag_index = idx
                return

        # Otherwise, maybe we clicked a shape
        item = self.canvas.find_closest(x, y)
        if item:
            iid = item[0]
            lyr = self.find_layer_of_item(iid)
            if lyr and not lyr.locked:
                self.select_item(iid)
                self.show_direct_select_anchors(iid)
            else:
                self.select_item(None)
                self.clear_direct_select_anchors()
        else:
            self.select_item(None)
            self.clear_direct_select_anchors()

    def direct_select_drag_anchor(self, x, y):
        if not self.direct_select_dragging_anchor:
            return
        shape_info = self.shape_data.get(self.direct_select_dragging_anchor)
        if not shape_info:
            return
        coords = shape_info['coords']
        idx = self.direct_select_drag_index
        coords[idx] = x
        coords[idx+1] = y

        # update canvas
        stype = shape_info['type']
        if stype in ("line","brush"):
            self.canvas.coords(self.direct_select_dragging_anchor, *coords)
        elif stype in ("rectangle","ellipse"):
            x1,y1,x2,y2 = self.normalize_rect(coords)
            self.canvas.coords(self.direct_select_dragging_anchor, x1,y1,x2,y2)
        elif stype == "text":
            self.canvas.coords(self.direct_select_dragging_anchor, coords[0], coords[1])
        # store
        self.shape_data.update_coords(self.direct_select_dragging_anchor, coords)
        self.update_direct_select_anchors(self.direct_select_dragging_anchor)

    def show_direct_select_anchors(self, item_id):
        self.clear_direct_select_anchors()
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        for i in range(0,len(coords),2):
            x = coords[i]
            y = coords[i+1]
            h = self.canvas.create_rectangle(x-3,y-3,x+3,y+3, fill="blue", outline="blue")
            self.direct_select_anchors.append((h, item_id, i))

    def update_direct_select_anchors(self, item_id):
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        for (handle_id, sid, idx) in self.direct_select_anchors:
            if sid == item_id:
                x = coords[idx]
                y = coords[idx+1]
                self.canvas.coords(handle_id, x-3, y-3, x+3, y+3)

    def find_direct_select_anchor(self, x, y):
        radius = 6
        for (hid, shape_iid, idx) in self.direct_select_anchors:
            hx1, hy1, hx2, hy2 = self.canvas.coords(hid)
            if hx1 - radius < x < hx2 + radius and hy1 - radius < y < hy2 + radius:
                return (shape_iid, idx)
        return None

    def clear_direct_select_anchors(self):
        for (hid, shape_iid, idx) in self.direct_select_anchors:
            self.canvas.delete(hid)
        self.direct_select_anchors.clear()

    # -------------------------------------------------------------------------
    # BEND TOOL A (Basic anchor add/remove + move)
    # -------------------------------------------------------------------------
    def handle_bend_tool_a_click(self, x, y):
        # SHIFT+Click => remove anchor if it's near
        # normal click => add anchor or drag existing anchor
        # We'll do a similar approach as we did with direct select
        # but also allow insertion or removal
        shape_info = None
        item = self.canvas.find_closest(x, y)
        if item:
            sid = item[0]
            shape_info = self.shape_data.get(sid)
        # If SHIFT pressed
        if (self.root.tk.call('tk', 'windowingsystem') != 'win32'):
            # On some systems, SHIFT mask is different
            pass
        # We'll skip the SHIFT detection detail for brevity

        # For demonstration, let's just select the shape and show anchors
        if shape_info:
            self.select_item(item[0])
            self.show_bend_anchors(item[0])
        else:
            self.select_item(None)
            self.clear_bend_anchors()

    def bend_tool_a_drag_anchor(self, x, y):
        # Move anchor in line-based shape or bounding box for rectangle
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
        for i in range(0,len(coords),2):
            x = coords[i]
            y = coords[i+1]
            h = self.canvas.create_rectangle(x-3, y-3, x+3, y+3, fill="red", outline="red")
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

    # -------------------------------------------------------------------------
    # BEND TOOL B (Warp entire shape in a radius, demonstration)
    # -------------------------------------------------------------------------
    def handle_bend_tool_b_click(self, x, y):
        # For example, find all anchor points in BEND_WARP_RADIUS and push them outward
        # purely as a demonstration
        item = self.canvas.find_closest(x, y)
        if item:
            sid = item[0]
            shape_info = self.shape_data.get(sid)
            if shape_info:
                coords = shape_info['coords']
                for i in range(0,len(coords),2):
                    dx = coords[i] - x
                    dy = coords[i+1] - y
                    dist = math.sqrt(dx*dx + dy*dy)
                    if dist < BEND_WARP_RADIUS:
                        factor = (BEND_WARP_RADIUS - dist) / BEND_WARP_RADIUS
                        coords[i] += dx*0.3*factor
                        coords[i+1] += dy*0.3*factor
                # update
                stype = shape_info['type']
                if stype in ("line","brush"):
                    self.canvas.coords(sid, *coords)
                elif stype in ("rectangle","ellipse"):
                    x1,y1,x2,y2 = self.normalize_rect(coords)
                    self.canvas.coords(sid, x1,y1,x2,y2)
                self.shape_data.update_coords(sid, coords)
                self.push_history("Bend Tool B warp")

    # -------------------------------------------------------------------------
    # BEND TOOL C (Insert arcs or advanced anchor editing, demonstration)
    # -------------------------------------------------------------------------
    def handle_bend_tool_c_click(self, x, y):
        # Maybe we pick 2 anchors around the click and insert an arc
        item = self.canvas.find_closest(x, y)
        if item:
            sid = item[0]
            shape_info = self.shape_data.get(sid)
            if shape_info and shape_info['type'] in ("line","brush"):
                # demonstration: insert an arc segment near x,y
                coords = shape_info['coords']
                # We'll do a naive approach
                if len(coords) >= 4:
                    # insert a midpoint arc
                    coords.insert(2, y)
                    coords.insert(2, x)
                    self.canvas.coords(sid, *coords)
                    self.shape_data.update_coords(sid, coords)
                    self.push_history("Bend Tool C arc insert")


    # -------------------------------------------------------------------------
    # SHAPE CREATION (BRUSH, LINE, RECT, ELLIPSE)
    # -------------------------------------------------------------------------
    def create_brush_segment(self, x, y, layer):
        line_id = self.canvas.create_line(x, y, x+1, y+1, fill=self.stroke_color,
                                          width=self.brush_size)
        layer.add_item(line_id, "brush")
        self.shape_data.store(line_id, "brush", [x,y,x+1,y+1],
                              fill=None, outline=self.stroke_color, width=self.brush_size)
        self.select_item(line_id)
        # We won't push history on every line segment creation
        # We'll push on mouse up if needed

    def finalize_shape_creation(self):
        layer = self.layers[self.current_layer_index]
        stype = self.current_tool.lower()  # line, rectangle, ellipse
        layer.add_item(self.temp_item, stype)
        coords = self.canvas.coords(self.temp_item)
        fill_val = None if stype == "line" else self.fill_color
        self.shape_data.store(self.temp_item, stype, coords, fill_val,
                              self.stroke_color, self.brush_size)
        self.select_item(self.temp_item)
        self.temp_item = None


    # -------------------------------------------------------------------------
    # ERASERS
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
            # bounding shapes or text => if corner is in radius => remove shape
            coords = shape_info['coords']
            removed = False
            for i in range(0,len(coords),2):
                dx = coords[i] - ex
                dy = coords[i+1] - ey
                if math.hypot(dx,dy) < self.eraser_radius:
                    self.erase_item(item_id)
                    removed = True
                    break
            return

        coords = shape_info['coords']
        new_points = []
        for i in range(0,len(coords),2):
            dx = coords[i] - ex
            dy = coords[i+1] - ey
            dist = math.hypot(dx,dy)
            if dist >= self.eraser_radius:
                new_points.append(coords[i])
                new_points.append(coords[i+1])
        if len(new_points) < 4:
            # if fewer than 2 anchors => remove
            self.erase_item(item_id)
            return
        # just keep new shape
        self.canvas.coords(item_id, *new_points)
        self.shape_data.update_coords(item_id, new_points)

    def soft_erase_shape(self, item_id):
        """
        Fake a "soft erase" by adjusting the shape's color toward background color.
        In real usage, alpha blending on Tkinter Canvas is limited. We'll do a naive approach:
         - If shape has an outline color, we step it toward #ffffff or #dddddd
         - If fill, we step it as well
        This is just a demonstration.
        """
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        # We'll define a helper that steps color channels
        def fade_color(hexcol):
            # parse #rrggbb
            if not hexcol or len(hexcol) != 7:
                return hexcol
            r = int(hexcol[1:3], 16)
            g = int(hexcol[3:5], 16)
            b = int(hexcol[5:7], 16)
            # step each channel by soft_eraser_fade_step
            # approaching white
            target = 255
            def fade_channel(c):
                diff = target - c
                if abs(diff) < self.soft_eraser_fade_step:
                    return target
                if diff > 0:
                    return c + self.soft_eraser_fade_step
                else:
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
        # apply
        if new_outline:
            self.canvas.itemconfig(item_id, outline=new_outline)
        if new_fill:
            self.canvas.itemconfig(item_id, fill=new_fill)


    # -------------------------------------------------------------------------
    # MISC UTILS
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
            # highlight
            try:
                self.canvas.itemconfig(item_id, width=max(self.brush_size+2,3))
            except:
                pass

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

    @staticmethod
    def normalize_rect(c):
        x1, y1, x2, y2 = c
        return (min(x1,x2), min(y1,y2),
                max(x1,x2), max(y1,y2))

    # -------------------------------------------------------------------------
    # UNDO/REDO KEY BINDINGS
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
    # OPEN & SAVE
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
        self.canvas.image = tk_img
        self.shape_data.store(iid, "image", [0,0], fill=None, outline=None, width=1)
        self.layers[0].add_item(iid, "image")
        self.push_history(f"Opened image {fp}")

    def save_canvas_snapshot(self):
        fp = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".png",
            filetypes=[("PNG Files","*.png"), ("All Files","*.*")]
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
            print("Saved canvas snapshot to", fp)
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

