import tkinter as tk
from tkinter import ttk, filedialog, colorchooser
from PIL import Image, ImageTk

# -------------------------------------------------------------------------
# CONFIG / CONSTANTS
# -------------------------------------------------------------------------
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14
UNDO_STACK_LIMIT = 10

class Layer:
    """Represents a layer storing references to canvas items."""
    def __init__(self, name, visible=True, locked=False):
        self.name = name
        self.visible = visible
        self.locked = locked
        # List of (canvas_item_id, shape_type)
        self.items = []

    def add_item(self, item_id, shape_type):
        self.items.append((item_id, shape_type))
    
    def remove_item(self, item_id):
        self.items = [(iid, stype) for (iid, stype) in self.items if iid != item_id]

class ShapeData:
    """
    A dictionary storing shape geometry so we can display/edit anchor points:
      shape_data[item_id] = {
        'type': 'line'|'rectangle'|'ellipse'|'brush'|'text'|'image'...,
        'coords': [... anchor points ...],
        'fill': color or None,
        'outline': color or None,
        'width': stroke width or 1
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
        return self.shapes.get(item_id, None)

    def update_coords(self, item_id, new_coords):
        if item_id in self.shapes:
            self.shapes[item_id]['coords'] = new_coords[:]


class SimpleImageEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Image Editor - Two Select Tools & Bend Tool")
        self.root.geometry("1200x700")

        # Editor State
        self.undo_stack = []
        self.layers = []
        self.current_layer_index = None

        # Tools
        self.current_tool = None
        self.tool_buttons = {}
        self.selected_item = None

        # For shape creation
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE
        self.temp_item = None
        self.start_x = None
        self.start_y = None
        self.last_x = None
        self.last_y = None

        # For "Select" (move entire shape)
        self.moving_shape = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # For "Direct Select" (editing existing anchors)
        self.anchor_handles = []
        self.dragging_anchor = None
        self.dragging_anchor_index = None

        # For "Bend Tool" (add/remove anchors on line-based shapes)
        self.bend_anchors = []       # anchor squares for line shapes
        self.bend_drag_anchor = None # which anchor is being dragged
        self.bend_drag_index = None

        # Data structure for storing geometry
        self.shape_data = ShapeData()

        # Build UI
        self.build_frames()
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options()
        self.setup_layers_panel()

        # Start with 1 layer
        self.add_layer()

        # Keyboard shortcuts
        self.root.bind("<Control-z>", self.undo)
        self.root.bind("<Control-Z>", self.undo)

    # -------------------------------------------------
    # UI FRAME SETUP
    # -------------------------------------------------
    def build_frames(self):
        self.toolbar_frame = tk.Frame(self.root, width=80, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.layers_frame = tk.Frame(self.root, width=200, bg="#F0F0F0")
        self.layers_frame.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_toolbar(self):
        """
        Tools:
          - Select (move entire object)
          - Direct Select (anchor-level editing for existing shapes, no add/remove)
          - Bend Tool (line-based anchor add/remove + move)
          - Brush, Line, Rectangle, Ellipse, Text, Eraser
        """
        tools = [
            ("Select", None),                # bounding box move
            ("Direct Select", None),         # anchor editing (existing anchors)
            ("Bend Tool", None),             # add/remove anchors on lines
            ("Brush", None),
            ("Line", None),
            ("Rectangle", None),
            ("Ellipse", None),
            ("Text", None),
            ("Eraser", None)
        ]
        for (tool_name, _) in tools:
            b = tk.Button(self.toolbar_frame, text=tool_name,
                          command=lambda t=tool_name: self.select_tool(t))
            b.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool_name] = b

        # Additional actions
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)

        # Default tool
        self.select_tool("Select")

    def select_tool(self, tool_name):
        self.current_tool = tool_name

        # Cancel any shape move or anchor drag
        self.moving_shape = False
        self.dragging_anchor = None
        self.bend_drag_anchor = None

        # Clear old anchor handles if we switch tools
        self.clear_direct_select_anchors()
        self.clear_bend_anchors()

        # Update toolbar button visuals
        for name, btn in self.tool_buttons.items():
            if name == tool_name:
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
        tool_opts = tk.Frame(self.main_frame, bg="#DDDDDD", height=50)
        tool_opts.pack(side=tk.BOTTOM, fill=tk.X)

        # Stroke color
        tk.Label(tool_opts, text="Stroke:").pack(side=tk.LEFT, padx=5)
        self.stroke_btn = tk.Button(tool_opts, bg=self.stroke_color, width=3,
                                    command=self.pick_stroke_color)
        self.stroke_btn.pack(side=tk.LEFT, padx=5)

        # Fill color
        tk.Label(tool_opts, text="Fill:").pack(side=tk.LEFT)
        self.fill_btn = tk.Button(tool_opts, bg=self.fill_color, width=3,
                                  command=self.pick_fill_color)
        self.fill_btn.pack(side=tk.LEFT, padx=5)

        # Brush size
        tk.Label(tool_opts, text="Brush Size:").pack(side=tk.LEFT, padx=5)
        self.brush_size_slider = ttk.Scale(tool_opts, from_=1, to=20,
                                           orient=tk.HORIZONTAL,
                                           command=self.on_brush_size_change)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT, padx=5)

        # Font size
        tk.Label(tool_opts, text="Font Size:").pack(side=tk.LEFT, padx=5)
        self.font_size_spin = ttk.Spinbox(tool_opts, from_=8, to=72, width=4,
                                          command=self.on_font_size_change)
        self.font_size_spin.set(str(self.font_size))
        self.font_size_spin.pack(side=tk.LEFT, padx=5)

    def setup_layers_panel(self):
        tk.Label(self.layers_frame, text="Layers", bg="#F0F0F0",
                 font=("Arial", 12, "bold")).pack(pady=5)

        mid = tk.Frame(self.layers_frame, bg="#F0F0F0")
        mid.pack(fill=tk.BOTH, expand=True)

        self.layer_listbox = tk.Listbox(mid)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.layer_listbox.bind("<<ListboxSelect>>", self.on_layer_select)

        sb = tk.Scrollbar(mid, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=sb.set)

        bottom = tk.Frame(self.layers_frame, bg="#F0F0F0")
        bottom.pack(fill=tk.X)
        tk.Button(bottom, text="Up", command=self.move_layer_up).pack(side=tk.LEFT, padx=2)
        tk.Button(bottom, text="Down", command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        tk.Button(bottom, text="Hide/Show", command=self.toggle_layer_visibility).pack(side=tk.LEFT, padx=2)
        tk.Button(bottom, text="Delete", command=self.delete_layer).pack(side=tk.LEFT, padx=2)

    # -------------------------------------------------
    # LAYER MANAGEMENT
    # -------------------------------------------------
    def add_layer(self, name=None):
        if name is None:
            name = f"Layer {len(self.layers)+1}"
        new_layer = Layer(name)
        self.layers.insert(0, new_layer)
        self.layer_listbox.insert(0, name)
        self.layer_listbox.selection_clear(0, tk.END)
        self.layer_listbox.selection_set(0)
        self.on_layer_select(None)

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
        above = self.layer_listbox.get(idx-1)
        curr = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx-1, idx)
        self.layer_listbox.insert(idx-1, curr)
        self.layer_listbox.insert(idx, above)
        self.layer_listbox.selection_set(idx-1)
        self.current_layer_index = idx-1
        # raise items
        for (iid, t) in self.layers[idx-1].items:
            self.canvas.tag_raise(iid)

    def move_layer_down(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers)-1:
            return
        self.layers[idx], self.layers[idx+1] = self.layers[idx+1], self.layers[idx]
        curr = self.layer_listbox.get(idx)
        below = self.layer_listbox.get(idx+1)
        self.layer_listbox.delete(idx, idx+1)
        self.layer_listbox.insert(idx, below)
        self.layer_listbox.insert(idx+1, curr)
        self.layer_listbox.selection_set(idx+1)
        self.current_layer_index = idx+1
        # lower
        for (iid, t) in self.layers[idx+1].items:
            self.canvas.tag_lower(iid)

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

    def delete_layer(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lyr = self.layers[idx]
        for (iid, t) in lyr.items:
            self.canvas.delete(iid)
            self.shape_data.remove(iid)
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0
        self.select_item(None)
        self.clear_direct_select_anchors()
        self.clear_bend_anchors()

    # -------------------------------------------------
    # MOUSE EVENTS
    # -------------------------------------------------
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

        elif self.current_tool == "Eraser":
            closest = self.canvas.find_closest(event.x, event.y)
            if closest:
                self.erase_item(closest[0])

        elif self.current_tool in ("Line", "Rectangle", "Ellipse"):
            self.temp_item = None

        elif self.current_tool == "Text":
            text_id = self.canvas.create_text(event.x, event.y,
                                              text="Sample",
                                              fill=self.stroke_color,
                                              font=("Arial", self.font_size))
            layer.add_item(text_id, "text")
            self.push_undo(("create", text_id))
            self.shape_data.store(text_id, "text",
                                  [event.x, event.y],
                                  fill=self.stroke_color, outline=self.stroke_color, width=1)
            self.select_item(text_id)

    def on_left_drag(self, event):
        if self.current_tool == "Select" and self.moving_shape and self.selected_item:
            self.move_entire_shape(event.x, event.y)
        elif self.current_tool == "Direct Select" and self.dragging_anchor is not None:
            self.direct_select_drag_anchor(event.x, event.y)
        elif self.current_tool == "Bend Tool" and self.bend_drag_anchor is not None:
            self.bend_tool_drag_anchor(event.x, event.y)
        else:
            # Possibly drawing new shape
            self.handle_shape_drawing_drag(event)

    def on_left_up(self, event):
        if self.current_tool == "Select" and self.moving_shape:
            self.moving_shape = False
            return

        if self.current_tool == "Direct Select" and self.dragging_anchor is not None:
            self.dragging_anchor = None
            self.dragging_anchor_index = None
            return

        if self.current_tool == "Bend Tool" and self.bend_drag_anchor is not None:
            self.bend_drag_anchor = None
            self.bend_drag_index = None
            return

        # Finalize line/rect/ellipse creation
        if self.current_tool in ("Line", "Rectangle", "Ellipse") and self.temp_item:
            self.finalize_shape_creation()

    # -------------------------------------------------
    # SELECT TOOL (Move entire shape)
    # -------------------------------------------------
    def handle_select_click(self, x, y):
        item = self.canvas.find_closest(x, y)
        if item:
            iid = item[0]
            lyr = self.find_layer_of_item(iid)
            if lyr and not lyr.locked:
                self.select_item(iid)
                # Start moving shape
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
            for i in range(0, len(coords), 2):
                coords[i] += dx
                coords[i+1] += dy
            self.canvas.coords(self.selected_item, *coords)
            self.shape_data.update_coords(self.selected_item, coords)
        self.last_x, self.last_y = x, y

    # -------------------------------------------------
    # DIRECT SELECT TOOL (Edit existing anchors, no add/remove)
    # -------------------------------------------------
    def handle_direct_select_click(self, x, y):
        # If we have anchors shown, see if we clicked one
        if self.anchor_handles:
            # see if user clicked an anchor
            handle = self.find_direct_select_anchor(x, y)
            if handle is not None:
                # start dragging that anchor
                self.dragging_anchor = handle[0]  # shape item
                self.dragging_anchor_index = handle[1]
                return

        # Otherwise, maybe clicked a new shape
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
        # Move one anchor in shape_data
        shape_info = self.shape_data.get(self.selected_item)
        if not shape_info:
            return
        coords = shape_info['coords']
        idx = self.dragging_anchor_index
        coords[idx] = x
        coords[idx+1] = y

        # update canvas
        if shape_info['type'] in ("line", "brush"):
            self.canvas.coords(self.selected_item, *coords)
        elif shape_info['type'] == "rectangle":
            x1, y1, x2, y2 = self.normalize_rect(coords)
            self.canvas.coords(self.selected_item, x1, y1, x2, y2)
        elif shape_info['type'] == "ellipse":
            x1, y1, x2, y2 = self.normalize_rect(coords)
            self.canvas.coords(self.selected_item, x1, y1, x2, y2)
        elif shape_info['type'] == "text":
            self.canvas.coords(self.selected_item, coords[0], coords[1])

        self.shape_data.update_coords(self.selected_item, coords)
        # reposition anchor squares
        self.update_direct_select_anchors(self.selected_item)

    def show_direct_select_anchors(self, item_id):
        self.clear_direct_select_anchors()
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        for i in range(0, len(coords), 2):
            x = coords[i]
            y = coords[i+1]
            r = self.canvas.create_rectangle(x-3, y-3, x+3, y+3, fill="blue", outline="blue")
            self.anchor_handles.append((r, item_id, i))  # (handle_id, shape_item, index_in_coords)

    def update_direct_select_anchors(self, item_id):
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        for (handle_id, shape_iid, idx) in self.anchor_handles:
            if shape_iid == item_id:
                x = coords[idx]
                y = coords[idx+1]
                self.canvas.coords(handle_id, x-3, y-3, x+3, y+3)

    def find_direct_select_anchor(self, x, y):
        """Check if we clicked a direct-select anchor handle."""
        radius = 5
        for (handle_id, shape_iid, idx) in self.anchor_handles:
            hx1, hy1, hx2, hy2 = self.canvas.coords(handle_id)
            if hx1 - radius < x < hx2 + radius and hy1 - radius < y < hy2 + radius:
                return (shape_iid, idx)
        return None

    def clear_direct_select_anchors(self):
        for (hid, shapeid, idx) in self.anchor_handles:
            self.canvas.delete(hid)
        self.anchor_handles.clear()

    # -------------------------------------------------
    # NEW: BEND TOOL (Add/Remove anchors on line shapes)
    # -------------------------------------------------
    def handle_bend_tool_click(self, event):
        """
        If you SHIFT+click an existing anchor, remove it (unless shape would break).
        If you click on a line, add a new anchor at that approximate location.
        If you click an existing anchor (no shift), start dragging it.
        """
        # 1. Check if we SHIFT+clicked an existing anchor => remove anchor
        if event.state & 0x0001:  # SHIFT pressed on many OS. 
            # see if anchor is clicked
            handle = self.find_bend_anchor(event.x, event.y)
            if handle is not None:
                shape_id, anchor_idx = handle
                self.remove_bend_anchor(shape_id, anchor_idx)
            return

        # 2. If we have anchors for a shape, see if we clicked one
        if self.bend_anchors:
            handle = self.find_bend_anchor(event.x, event.y)
            if handle is not None:
                # start dragging that anchor
                self.bend_drag_anchor = handle[0]
                self.bend_drag_index = handle[1]
                return

        # 3. Otherwise, maybe we clicked a new line shape
        item = self.canvas.find_closest(event.x, event.y)
        if not item:
            self.select_item(None)
            self.clear_bend_anchors()
            return
        iid = item[0]
        lyr = self.find_layer_of_item(iid)
        if not lyr or lyr.locked:
            self.select_item(None)
            self.clear_bend_anchors()
            return

        shape_info = self.shape_data.get(iid)
        if not shape_info:
            self.select_item(None)
            self.clear_bend_anchors()
            return

        # If shape is line or brush => we can insert a new anchor
        if shape_info['type'] in ("line","brush"):
            self.select_item(iid)
            self.show_bend_anchors(iid)
            self.add_bend_anchor(iid, event.x, event.y)
        else:
            # For rectangle/ellipse/text, ignoring bend anchor additions
            self.select_item(iid)
            self.clear_bend_anchors()

    def show_bend_anchors(self, item_id):
        """Draw anchor squares for all points in a line-like shape."""
        self.clear_bend_anchors()
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        # each pair is an anchor
        for i in range(0, len(coords), 2):
            x, y = coords[i], coords[i+1]
            h = self.canvas.create_rectangle(x-3, y-3, x+3, y+3, fill="red", outline="red")
            self.bend_anchors.append((h, item_id, i))

    def clear_bend_anchors(self):
        for (hid, shapeid, idx) in self.bend_anchors:
            self.canvas.delete(hid)
        self.bend_anchors.clear()

    def find_bend_anchor(self, x, y):
        """Check if we clicked a bend anchor handle."""
        radius = 5
        for (hid, shape_iid, idx) in self.bend_anchors:
            hx1, hy1, hx2, hy2 = self.canvas.coords(hid)
            if hx1 - radius < x < hx2 + radius and hy1 - radius < y < hy2 + radius:
                return (shape_iid, idx)
        return None

    def bend_tool_drag_anchor(self, x, y):
        # Move a single anchor in a multi-point line
        shape_info = self.shape_data.get(self.bend_drag_anchor)
        if not shape_info:
            return
        coords = shape_info['coords']
        coords[self.bend_drag_index] = x
        coords[self.bend_drag_index+1] = y
        # update canvas
        self.canvas.coords(self.bend_drag_anchor, *coords)
        self.shape_data.update_coords(self.bend_drag_anchor, coords)
        self.update_bend_anchors(self.bend_drag_anchor)

    def update_bend_anchors(self, item_id):
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        # reposition anchor squares
        for (hid, sid, idx) in self.bend_anchors:
            if sid == item_id:
                x = coords[idx]
                y = coords[idx+1]
                self.canvas.coords(hid, x-3, y-3, x+3, y+3)

    def add_bend_anchor(self, item_id, x, y):
        """
        Insert a new anchor in the line's coords at position close to (x,y).
        We find the segment that is closest to (x,y) and split it.
        """
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        if len(coords) < 4:
            # a line with 2 anchors has coords [x1,y1,x2,y2]
            # We'll just insert it in the middle for now
            self.insert_anchor_between(coords, 0, 1, x, y)
        else:
            # find closest segment
            best_dist = float("inf")
            best_index = 0  # segment start
            for i in range(0, len(coords)-2, 2):
                segx1 = coords[i]
                segy1 = coords[i+1]
                segx2 = coords[i+2]
                segy2 = coords[i+3]
                d = self.dist_point_to_segment(x,y, segx1,segy1, segx2,segy2)
                if d < best_dist:
                    best_dist = d
                    best_index = i
            # now we insert an anchor after best_index
            self.insert_anchor_between(coords, best_index, best_index+2, x, y)

        # update the canvas and shape data
        self.canvas.coords(item_id, *coords)
        self.shape_data.update_coords(item_id, coords)
        self.show_bend_anchors(item_id)

    def remove_bend_anchor(self, shape_id, anchor_idx):
        """
        Remove one anchor if shape has more than 2 anchors left.
        anchor_idx is the index in coords array.
        """
        shape_info = self.shape_data.get(shape_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        if len(coords) <= 4:
            # We won't remove if that would make <2 anchors
            print("Cannot remove anchor: shape would have fewer than 2 anchors.")
            return
        # remove the x,y at anchor_idx, anchor_idx+1
        del coords[anchor_idx:anchor_idx+2]
        self.canvas.coords(shape_id, *coords)
        self.shape_data.update_coords(shape_id, coords)
        self.show_bend_anchors(shape_id)

    def insert_anchor_between(self, coords, idxA, idxB, x, y):
        """
        Insert (x,y) after coords[idxA:idxA+2] in the array,
        so that it appears between segment (idxA) and (idxB).
        """
        # For example, if coords = [x1,y1, x2,y2, x3,y3],
        # and idxA=2, idxB=4 => we insert after coords[2], coords[3].
        coords.insert(idxB, y)
        coords.insert(idxB, x)

    @staticmethod
    def dist_point_to_segment(px, py, x1, y1, x2, y2):
        """Return distance from (px,py) to line segment (x1,y1)-(x2,y2)."""
        # Algorithm from: https://stackoverflow.com/questions/849211/shortest-distance-between-a-point-and-a-line-segment
        seg_len_sq = (x2 - x1)**2 + (y2 - y1)**2
        if seg_len_sq == 0:
            # degenerate
            return ((px - x1)**2 + (py - y1)**2)**0.5
        t = ((px - x1)*(x2 - x1) + (py - y1)*(y2 - y1)) / seg_len_sq
        if t < 0:
            return ((px - x1)**2 + (py - y1)**2)**0.5
        elif t > 1:
            return ((px - x2)**2 + (py - y2)**2)**0.5
        projx = x1 + t*(x2 - x1)
        projy = y1 + t*(y2 - y1)
        return ((px - projx)**2 + (py - projy)**2)**0.5

    # -------------------------------------------------
    # SHAPE DRAWING: LINE / RECT / ELLIPSE
    # -------------------------------------------------
    def handle_shape_drawing_drag(self, event):
        if self.current_layer_index is None:
            return
        layer = self.layers[self.current_layer_index]
        if layer.locked or not layer.visible:
            return

        if self.current_tool == "Brush":
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            if abs(dx) < 1 and abs(dy) < 1:
                return  # skip tiny movement
            line_id = self.canvas.create_line(self.last_x, self.last_y, event.x, event.y,
                                              fill=self.stroke_color, width=self.brush_size)
            layer.add_item(line_id, "brush")
            self.push_undo(("create", line_id))
            # store shape data with 2 anchor points
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

    def finalize_shape_creation(self):
        layer = self.layers[self.current_layer_index]
        shape_type = self.current_tool.lower()  # 'line' / 'rectangle' / 'ellipse'
        layer.add_item(self.temp_item, shape_type)
        self.push_undo(("create", self.temp_item))
        coords = self.canvas.coords(self.temp_item)
        fill_val = (None if shape_type == 'line' else self.fill_color)
        self.shape_data.store(self.temp_item, shape_type, coords,
                              fill=fill_val,
                              outline=self.stroke_color,
                              width=self.brush_size)
        self.select_item(self.temp_item)
        self.temp_item = None

    def create_brush_segment(self, x, y, layer):
        line_id = self.canvas.create_line(x, y, x+1, y+1,
                                          fill=self.stroke_color,
                                          width=self.brush_size)
        layer.add_item(line_id, "brush")
        self.push_undo(("create", line_id))
        self.shape_data.store(line_id, "brush",
                              [x, y, x+1, y+1],
                              fill=None, outline=self.stroke_color, width=self.brush_size)
        self.select_item(line_id)

    # -------------------------------------------------
    # SELECTION & HELPER
    # -------------------------------------------------
    def select_item(self, item_id):
        if self.selected_item:
            # revert stroke width
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
                self.canvas.itemconfig(item_id, width=max(self.brush_size+2, 3))
            except:
                pass

    def erase_item(self, item_id):
        lyr = self.find_layer_of_item(item_id)
        if lyr:
            lyr.remove_item(item_id)
            shape_info = self.shape_data.get(item_id)
            if shape_info:
                coords_backup = self.canvas.coords(item_id)
                config_backup = self.canvas.itemconfig(item_id)
                self.push_undo(("delete", item_id,
                                shape_info['type'],
                                coords_backup,
                                config_backup))
            self.shape_data.remove(item_id)
            self.canvas.delete(item_id)
            if self.selected_item == item_id:
                self.selected_item = None
            self.clear_direct_select_anchors()
            self.clear_bend_anchors()

    def find_layer_of_item(self, item_id):
        for l in self.layers:
            for (iid, st) in l.items:
                if iid == item_id:
                    return l
        return None

    @staticmethod
    def normalize_rect(c):
        """Rect coords are (x1,y1,x2,y2); ensure x1<x2, y1<y2."""
        x1, y1, x2, y2 = c
        return (min(x1,x2), min(y1,y2), max(x1,x2), max(y1,y2))

    # -------------------------------------------------
    # COLORS / SIZE
    # -------------------------------------------------
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

    # -------------------------------------------------
    # UNDO
    # -------------------------------------------------
    def push_undo(self, action):
        """
        action is either:
         ("create", item_id)
         ("delete", item_id, shape_type, coords, config)
        """
        self.undo_stack.append(action)
        if len(self.undo_stack) > UNDO_STACK_LIMIT:
            self.undo_stack.pop(0)

    def undo(self, event=None):
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        t = action[0]

        if t == "create":
            # remove item
            item_id = action[1]
            self.erase_item(item_id)

        elif t == "delete":
            # restore item
            (item_id, shape_type, coords, config) = action[1], action[2], action[3], action[4]
            if shape_type == "line":
                restored = self.canvas.create_line(*coords)
            elif shape_type == "rectangle":
                restored = self.canvas.create_rectangle(*coords)
            elif shape_type == "ellipse":
                restored = self.canvas.create_oval(*coords)
            elif shape_type == "text":
                txt_val = config.get("text", ("", "Restored"))[-1]
                restored = self.canvas.create_text(coords[0], coords[1], text=txt_val)
            elif shape_type == "brush":
                restored = self.canvas.create_line(*coords)
            else:
                restored = self.canvas.create_line(*coords)

            # reapply config
            for k,v in config.items():
                try:
                    self.canvas.itemconfig(restored, {k: v[-1]})
                except:
                    pass

            # store shape data
            stroke_col = config.get("outline", [None, self.stroke_color])[-1]
            fill_col = config.get("fill", [None, None])[-1]
            w = config.get("width", [None, self.brush_size])[-1]
            self.shape_data.store(restored, shape_type, coords,
                                  fill=fill_col,
                                  outline=stroke_col,
                                  width=w)

            if not self.layers:
                self.add_layer()
            self.layers[0].add_item(restored, shape_type)

    # -------------------------------------------------
    # OPEN / SAVE
    # -------------------------------------------------
    def open_image_layer(self):
        fp = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Image Files","*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("All Files","*.*")]
        )
        if not fp:
            return
        try:
            im = Image.open(fp)
            tkimg = ImageTk.PhotoImage(im)
        except Exception as e:
            print("Could not open image:", e)
            return
        iid = self.canvas.create_image(0,0,anchor=tk.NW, image=tkimg)
        self.canvas.image = tkimg  # keep ref
        lyr_name = "ImageLayer_"+fp.split('/')[-1]
        self.add_layer(lyr_name)
        self.layers[0].add_item(iid, "image")
        self.shape_data.store(iid, "image",[0,0], fill=None, outline=None, width=1)

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
        except ImportError:
            print("pyscreenshot not installed. Cannot save snapshot.")
        except Exception as e:
            print("Error saving snapshot:", e)


# -------------------------------------------------
# RUN
# -------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()
