import tkinter as tk
from tkinter import ttk, filedialog, colorchooser
from PIL import Image, ImageTk

DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14
UNDO_STACK_LIMIT = 10

class Layer:
    """
    A layer holds canvas items plus metadata (visibility, lock).
    items = list of (item_id, shape_type)
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

class ShapeData:
    """
    Stores coordinate info so we can 'bend' or 'move' shapes.

    We'll keep a dict mapping canvas_item_id -> {
        'type': 'line'|'rectangle'|'ellipse'|'brush'|...,
        'coords': [x1, y1, x2, y2, ...]  # anchor coords,
        'fill': color,
        'outline': color,
        'width': stroke_width,
        ...
    }

    For rectangles or ellipses, 'coords' is [x1, y1, x2, y2] for bounding box corners.
    For a line, 'coords' is [x1, y1, x2, y2].
    For a brush stroke (simple approach), [x1, y1, x2, y2].
    """
    def __init__(self):
        self.shapes = {}

    def store(self, item_id, shape_type, coords, fill, outline, width):
        # Save shape in our dictionary
        self.shapes[item_id] = {
            'type': shape_type,
            'coords': coords[:],  # copy
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
        self.root.title("Simple Image Editor (Two Selection Tools + Bending)")
        self.root.geometry("1200x700")

        # State & Data
        self.undo_stack = []
        self.layers = []
        self.current_layer_index = None

        # Tools
        self.current_tool = None
        self.tool_buttons = {}
        # We'll have two selection tools:
        #  1) "Select (Move)" for bounding box movement
        #  2) "Direct Select (Bend)" for anchor-level editing
        self.moving_shape = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # Drawing
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE

        # Temp variables for shape creation
        self.start_x = None
        self.start_y = None
        self.temp_item = None
        self.selected_item = None

        # For brush or eraser
        self.last_x = None
        self.last_y = None

        # For direct select
        self.anchor_handles = []  # list of small squares
        self.dragging_anchor = None
        self.dragging_anchor_index = None

        # We'll store shape geometry in a separate data structure
        self.shape_data = ShapeData()

        # Build UI
        self.build_frames()
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options()
        self.setup_layers_panel()

        # Start with one layer
        self.add_layer()

        # Binds
        self.root.bind("<Control-z>", self.undo)
        self.root.bind("<Control-Z>", self.undo)

    # --------------------------------------------------------
    # FRAMES
    # --------------------------------------------------------
    def build_frames(self):
        # Left: toolbar
        self.toolbar_frame = tk.Frame(self.root, width=80, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        # Center: main area (canvas + bottom tool options)
        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Right: layers
        self.layers_frame = tk.Frame(self.root, width=200, bg="#F0F0F0")
        self.layers_frame.pack(side=tk.RIGHT, fill=tk.Y)

    # --------------------------------------------------------
    # TOOLBAR
    # --------------------------------------------------------
    def setup_toolbar(self):
        tools = [
            ("Select (Move)", None),
            ("Direct Select (Bend)", None),  # second type of selection
            ("Brush", None),
            ("Line", None),
            ("Rectangle", None),
            ("Ellipse", None),
            ("Text", None),
            ("Eraser", None)
        ]
        for (tool_name, _) in tools:
            btn = tk.Button(self.toolbar_frame, text=tool_name,
                            command=lambda t=tool_name: self.select_tool(t))
            btn.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool_name] = btn

        # Extra toolbar actions
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)

        self.select_tool("Select (Move)")

    def select_tool(self, tool_name):
        self.current_tool = tool_name
        # Clear any direct select anchors if switching away
        if tool_name != "Direct Select (Bend)":
            self.clear_anchors()

        # Reset item move states
        self.moving_shape = False
        self.dragging_anchor = None

        # Update button appearance
        for name, btn in self.tool_buttons.items():
            if name == tool_name:
                btn.config(relief=tk.SUNKEN, bg="#a0cfe6")
            else:
                btn.config(relief=tk.RAISED, bg="SystemButtonFace")

    # --------------------------------------------------------
    # CANVAS
    # --------------------------------------------------------
    def setup_canvas(self):
        self.canvas = tk.Canvas(self.main_frame, bg="white", cursor="cross")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Bind events
        self.canvas.bind("<Button-1>", self.on_left_down)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_up)

    def on_left_down(self, event):
        if self.current_layer_index is None:
            if self.layers:
                self.current_layer_index = 0
            else:
                return

        current_layer = self.layers[self.current_layer_index]
        if current_layer.locked or not current_layer.visible:
            return

        self.start_x, self.start_y = event.x, event.y
        self.last_x, self.last_y = event.x, event.y

        if self.current_tool == "Select (Move)":
            # See if we clicked on an existing item
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                iid = item[0]
                belongs_to = self.find_layer_of_item(iid)
                if belongs_to and not belongs_to.locked:
                    self.select_item(iid)
                    # Start moving shape
                    shape_info = self.shape_data.get(iid)
                    if shape_info:
                        # track offset
                        coords = self.canvas.coords(iid)
                        self.drag_offset_x = event.x - coords[0]
                        self.drag_offset_y = event.y - coords[1]
                        self.moving_shape = True
                else:
                    # clicked empty
                    self.select_item(None)
            else:
                self.select_item(None)

        elif self.current_tool == "Direct Select (Bend)":
            # If we already have an item selected with anchor handles
            # check if we clicked on an anchor
            if self.anchor_handles:
                handle = self.find_clicked_handle(event.x, event.y)
                if handle is not None:
                    # Start dragging a specific anchor
                    self.dragging_anchor = handle[0]  # item_id
                    self.dragging_anchor_index = handle[1]  # index in coords
                    return

            # Otherwise, maybe we clicked a new item
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                iid = item[0]
                belongs_to = self.find_layer_of_item(iid)
                if belongs_to and not belongs_to.locked:
                    self.select_item(iid)
                    # Show anchors for this shape
                    self.show_anchors(iid)
                else:
                    self.select_item(None)
                    self.clear_anchors()
            else:
                self.select_item(None)
                self.clear_anchors()

        elif self.current_tool == "Brush":
            # create a tiny line segment
            line_id = self.canvas.create_line(event.x, event.y, event.x+1, event.y+1,
                                              fill=self.stroke_color,
                                              width=self.brush_size)
            current_layer.add_item(line_id, "brush")
            self.push_undo(("create", line_id))
            self.shape_data.store(line_id, "brush",
                                  [event.x, event.y, event.x+1, event.y+1],
                                  fill=None, outline=self.stroke_color, width=self.brush_size)
            self.select_item(line_id)

        elif self.current_tool == "Eraser":
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                self.erase_item(item[0])

        elif self.current_tool == "Line":
            self.temp_item = None

        elif self.current_tool == "Rectangle":
            self.temp_item = None

        elif self.current_tool == "Ellipse":
            self.temp_item = None

        elif self.current_tool == "Text":
            text_id = self.canvas.create_text(event.x, event.y,
                                              text="Sample",
                                              fill=self.stroke_color,
                                              font=("Arial", self.font_size))
            current_layer.add_item(text_id, "text")
            self.push_undo(("create", text_id))
            # Store shape info (just x,y for text)
            self.shape_data.store(text_id, "text",
                                  [event.x, event.y],
                                  fill=self.stroke_color, outline=self.stroke_color, width=1)
            self.select_item(text_id)

    def on_left_drag(self, event):
        if self.current_tool == "Select (Move)" and self.moving_shape and self.selected_item:
            # Move entire shape
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            self.canvas.move(self.selected_item, dx, dy)
            # update shape_data coords
            shape_info = self.shape_data.get(self.selected_item)
            if shape_info:
                coords = shape_info['coords']
                # shift all coords
                for i in range(0, len(coords), 2):
                    coords[i] += dx
                    coords[i+1] += dy
                # update on canvas
                self.canvas.coords(self.selected_item, *coords)
                self.shape_data.update_coords(self.selected_item, coords)
            self.last_x, self.last_y = event.x, event.y

        elif self.current_tool == "Direct Select (Bend)" and self.dragging_anchor is not None:
            # Drag just one anchor point
            shape_info = self.shape_data.get(self.selected_item)
            if not shape_info:
                return
            coords = shape_info['coords']
            idx = self.dragging_anchor_index
            coords[idx] = event.x
            coords[idx+1] = event.y

            # update the shape in the canvas
            if shape_info['type'] in ("line", "brush"):
                # line or brush -> coords are x1,y1,x2,y2
                self.canvas.coords(self.selected_item, *coords)
            elif shape_info['type'] == "rectangle":
                # coords = [x1, y1, x2, y2]
                # interpret them as bounding corners
                x1, y1, x2, y2 = self.normalize_rect_coords(coords)
                self.canvas.coords(self.selected_item, x1, y1, x2, y2)
            elif shape_info['type'] == "ellipse":
                # same bounding box logic
                x1, y1, x2, y2 = self.normalize_rect_coords(coords)
                self.canvas.coords(self.selected_item, x1, y1, x2, y2)
            elif shape_info['type'] == "text":
                # single anchor for text
                self.canvas.coords(self.selected_item, coords[0], coords[1])
            # store updated coords
            self.shape_data.update_coords(self.selected_item, coords)
            self.update_anchors(self.selected_item)

        else:
            # Possibly drawing a new shape
            layer = None
            if self.current_layer_index is not None and self.current_layer_index < len(self.layers):
                layer = self.layers[self.current_layer_index]

            if self.current_tool == "Line":
                # draw a preview line
                if self.temp_item:
                    self.canvas.delete(self.temp_item)
                self.temp_item = self.canvas.create_line(self.start_x, self.start_y,
                                                         event.x, event.y,
                                                         fill=self.stroke_color,
                                                         width=self.brush_size)

            elif self.current_tool == "Rectangle":
                if self.temp_item:
                    self.canvas.delete(self.temp_item)
                x1, y1, x2, y2 = self.normalize_rect_coords([self.start_x, self.start_y, event.x, event.y])
                self.temp_item = self.canvas.create_rectangle(x1, y1, x2, y2,
                                                              outline=self.stroke_color,
                                                              fill=self.fill_color,
                                                              width=self.brush_size)

            elif self.current_tool == "Ellipse":
                if self.temp_item:
                    self.canvas.delete(self.temp_item)
                x1, y1, x2, y2 = self.normalize_rect_coords([self.start_x, self.start_y, event.x, event.y])
                self.temp_item = self.canvas.create_oval(x1, y1, x2, y2,
                                                         outline=self.stroke_color,
                                                         fill=self.fill_color,
                                                         width=self.brush_size)

    def on_left_up(self, event):
        if self.current_tool == "Select (Move)" and self.moving_shape:
            self.moving_shape = False
            return

        if self.current_tool == "Direct Select (Bend)" and self.dragging_anchor is not None:
            self.dragging_anchor = None
            self.dragging_anchor_index = None
            return

        # Possibly finalize shape creation
        if self.current_tool in ("Line", "Rectangle", "Ellipse") and self.temp_item:
            layer = self.layers[self.current_layer_index]
            shape_type = self.current_tool.lower()  # 'line','rectangle','ellipse'
            layer.add_item(self.temp_item, shape_type)
            self.push_undo(("create", self.temp_item))
            # store shape info
            coords = self.canvas.coords(self.temp_item)
            # line => [x1,y1,x2,y2]
            # rect/ellipse => [x1,y1,x2,y2]
            fill_val = None if shape_type == "line" else self.fill_color
            self.shape_data.store(self.temp_item, shape_type, coords,
                                  fill=fill_val,
                                  outline=self.stroke_color,
                                  width=self.brush_size)
            self.select_item(self.temp_item)
            self.temp_item = None

    # --------------------------------------------------------
    # ANCHOR POINTS FOR DIRECT SELECT
    # --------------------------------------------------------
    def show_anchors(self, item_id):
        """Display small squares at each anchor in shape_data."""
        self.clear_anchors()

        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']
        # We’ll show a small square around each anchor
        # For e.g. line => 2 anchors, rect => 2 corners in coords
        # or text => 1 anchor, ellipse => 2 corners
        step = 2
        for i in range(0, len(coords), step):
            x = coords[i]
            y = coords[i+1]
            handle_id = self.canvas.create_rectangle(x-3, y-3, x+3, y+3,
                                                     fill="blue", outline="blue")
            self.anchor_handles.append((handle_id, item_id, i))  
            # (handle's canvas id, shape's item_id, index in coords)

    def update_anchors(self, item_id):
        """
        After shape coords are updated, reposition anchor squares.
        """
        shape_info = self.shape_data.get(item_id)
        if not shape_info:
            return
        coords = shape_info['coords']

        # Loop through anchor_handles that belong to this item
        for (handle_id, shape_id, idx) in self.anchor_handles:
            if shape_id == item_id:
                x = coords[idx]
                y = coords[idx+1]
                self.canvas.coords(handle_id, x-3, y-3, x+3, y+3)

    def clear_anchors(self):
        """Remove all anchor squares from the canvas and list."""
        for (handle_id, shape_id, idx) in self.anchor_handles:
            self.canvas.delete(handle_id)
        self.anchor_handles.clear()

    def find_clicked_handle(self, x, y):
        """Check if we clicked any anchor handle."""
        # We'll do a simple bounding search
        radius = 5
        for (handle_id, shape_id, idx) in self.anchor_handles:
            hx1, hy1, hx2, hy2 = self.canvas.coords(handle_id)
            if hx1 - radius < x < hx2 + radius and hy1 - radius < y < hy2 + radius:
                return (shape_id, idx)
        return None

    # --------------------------------------------------------
    # SELECTION & ERASING
    # --------------------------------------------------------
    def select_item(self, item_id):
        """Highlight newly selected item, unhighlight old."""
        # Unhighlight old
        if self.selected_item:
            # revert stroke width
            shape_info = self.shape_data.get(self.selected_item)
            if shape_info:
                try:
                    self.canvas.itemconfig(self.selected_item, width=shape_info['width'])
                except:
                    pass

        self.selected_item = item_id
        if item_id:
            # highlight
            try:
                self.canvas.itemconfig(item_id, width=max(self.brush_size + 2, 3))
            except:
                pass

    def erase_item(self, item_id):
        layer = self.find_layer_of_item(item_id)
        if layer:
            layer.remove_item(item_id)
            shape = self.shape_data.get(item_id)
            if shape:
                coords_backup = self.canvas.coords(item_id)
                config_backup = self.canvas.itemconfig(item_id)
                self.push_undo(("delete", item_id,
                                shape['type'],
                                coords_backup,
                                config_backup))
            self.shape_data.remove(item_id)
            self.canvas.delete(item_id)
            if self.selected_item == item_id:
                self.selected_item = None
            self.clear_anchors()

    def find_layer_of_item(self, item_id):
        """Find which layer (if any) has this item."""
        for lyr in self.layers:
            for (iid, stype) in lyr.items:
                if iid == item_id:
                    return lyr
        return None

    # --------------------------------------------------------
    # UTILS
    # --------------------------------------------------------
    def normalize_rect_coords(self, c):
        """Make sure x1< x2, y1< y2 for bounding box shapes."""
        x1, y1, x2, y2 = c
        return (min(x1, x2), min(y1, y2),
                max(x1, x2), max(y1, y2))

    # --------------------------------------------------------
    # LAYERS
    # --------------------------------------------------------
    def setup_layers_panel(self):
        tk.Label(self.layers_frame, text="Layers", bg="#F0F0F0",
                 font=("Arial", 12, "bold")).pack(pady=5)

        panel = tk.Frame(self.layers_frame, bg="#F0F0F0")
        panel.pack(fill=tk.BOTH, expand=True)

        self.layer_listbox = tk.Listbox(panel)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.layer_listbox.bind("<<ListboxSelect>>", self.on_layer_select)

        sb = tk.Scrollbar(panel, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=sb.set)

        # layer controls
        btn_frame = tk.Frame(self.layers_frame, bg="#F0F0F0")
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="Up", command=self.move_layer_up).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Down", command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Hide/Show", command=self.toggle_layer_visibility).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Delete", command=self.delete_layer).pack(side=tk.LEFT, padx=2)

    def add_layer(self, name=None):
        if name is None:
            name = f"Layer {len(self.layers) + 1}"
        lyr = Layer(name)
        self.layers.insert(0, lyr)
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
        above_name = self.layer_listbox.get(idx-1)
        curr_name = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx-1, idx)
        self.layer_listbox.insert(idx-1, curr_name)
        self.layer_listbox.insert(idx, above_name)
        self.layer_listbox.selection_set(idx-1)
        self.current_layer_index = idx-1
        # Raise items in that layer
        for (iid, st) in self.layers[idx-1].items:
            self.canvas.tag_raise(iid)

    def move_layer_down(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers)-1:
            return
        self.layers[idx], self.layers[idx+1] = self.layers[idx+1], self.layers[idx]
        curr_name = self.layer_listbox.get(idx)
        below_name = self.layer_listbox.get(idx+1)
        self.layer_listbox.delete(idx, idx+1)
        self.layer_listbox.insert(idx, below_name)
        self.layer_listbox.insert(idx+1, curr_name)
        self.layer_listbox.selection_set(idx+1)
        self.current_layer_index = idx+1
        # Lower items
        for (iid, st) in self.layers[idx+1].items:
            self.canvas.tag_lower(iid)

    def toggle_layer_visibility(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lyr = self.layers[idx]
        lyr.visible = not lyr.visible
        state_val = tk.NORMAL if lyr.visible else tk.HIDDEN
        for (iid, st) in lyr.items:
            self.canvas.itemconfigure(iid, state=state_val)

        # rename in list
        txt = lyr.name
        if not lyr.visible:
            txt += " (hidden)"
        self.layer_listbox.delete(idx)
        self.layer_listbox.insert(idx, txt)
        self.layer_listbox.selection_set(idx)

    def delete_layer(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lyr = self.layers[idx]
        for (iid, st) in lyr.items:
            self.canvas.delete(iid)
            self.shape_data.remove(iid)
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0
        self.select_item(None)
        self.clear_anchors()

    # --------------------------------------------------------
    # TOOL OPTIONS (Bottom)
    # --------------------------------------------------------
    def setup_tool_options(self):
        self.tool_options_frame = tk.Frame(self.main_frame, bg="#DDDDDD", height=50)
        self.tool_options_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Stroke
        tk.Label(self.tool_options_frame, text="Stroke:").pack(side=tk.LEFT, padx=5)
        self.stroke_btn = tk.Button(self.tool_options_frame, bg=self.stroke_color, width=3,
                                    command=self.pick_stroke_color)
        self.stroke_btn.pack(side=tk.LEFT, padx=5)

        # Fill
        tk.Label(self.tool_options_frame, text="Fill:").pack(side=tk.LEFT, padx=5)
        self.fill_btn = tk.Button(self.tool_options_frame, bg=self.fill_color, width=3,
                                  command=self.pick_fill_color)
        self.fill_btn.pack(side=tk.LEFT, padx=5)

        # Brush size
        tk.Label(self.tool_options_frame, text="Brush Size:").pack(side=tk.LEFT, padx=5)
        self.brush_size_slider = ttk.Scale(self.tool_options_frame, from_=1, to=20,
                                           orient=tk.HORIZONTAL,
                                           command=self.on_brush_size_change)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT, padx=5)

        # Font size
        tk.Label(self.tool_options_frame, text="Font Size:").pack(side=tk.LEFT, padx=5)
        self.font_size_spin = ttk.Spinbox(self.tool_options_frame, from_=8, to=72, width=4,
                                          command=self.on_font_size_change)
        self.font_size_spin.set(str(self.font_size))
        self.font_size_spin.pack(side=tk.LEFT, padx=5)

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
            val = int(self.font_size_spin.get())
            self.font_size = val
        except ValueError:
            pass

    # --------------------------------------------------------
    # UNDO
    # --------------------------------------------------------
    def push_undo(self, action):
        """
        action = 
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
        atype = action[0]

        if atype == "create":
            # remove the item
            item_id = action[1]
            self.erase_item(item_id)

        elif atype == "delete":
            # restore the item
            item_id, shape_type, coords, config = action[1], action[2], action[3], action[4]
            if shape_type == "line":
                restored = self.canvas.create_line(*coords)
            elif shape_type == "rectangle":
                restored = self.canvas.create_rectangle(*coords)
            elif shape_type == "ellipse":
                restored = self.canvas.create_oval(*coords)
            elif shape_type == "text":
                # text: get text property
                text_val = config.get("text", ("", "Restored"))[-1]
                restored = self.canvas.create_text(coords[0], coords[1], text=text_val)
            elif shape_type == "brush":
                restored = self.canvas.create_line(*coords)
            else:
                # fallback
                restored = self.canvas.create_line(*coords)

            # apply config
            for k, v in config.items():
                try:
                    self.canvas.itemconfig(restored, {k: v[-1]})
                except:
                    pass

            # re-insert shape data
            stroke = config.get("outline", [None, self.stroke_color])[-1]
            fill_c = config.get("fill", [None, None])[-1]
            width_v = config.get("width", [None, self.brush_size])[-1]
            self.shape_data.store(restored, shape_type, coords,
                                  fill=fill_c, outline=stroke, width=width_v)

            # Insert back to top layer or create new
            if not self.layers:
                self.add_layer()
            self.layers[0].add_item(restored, shape_type)

# -------------------------------
# OPEN/SAVE
# -------------------------------
    def open_image_layer(self):
        fp = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("All Files", "*.*")]
        )
        if not fp:
            return
        try:
            img = Image.open(fp)
            tk_img = ImageTk.PhotoImage(img)
        except Exception as e:
            print("Error loading image:", e)
            return

        iid = self.canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
        # keep reference
        self.canvas.image = tk_img

        lyr_name = "ImageLayer_" + fp.split('/')[-1]
        self.add_layer(lyr_name)
        self.layers[0].add_item(iid, "image")

        # store shape data as minimal
        self.shape_data.store(iid, "image", [0,0], fill=None, outline=None, width=1)

    def save_canvas_snapshot(self):
        fp = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".png",
            filetypes=[("PNG Files", "*.png"), ("All Files", "*.*")]
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
            snap = ImageGrab.grab(bbox=(x0, y0, x1, y1))
            snap.save(fp)
        except ImportError:
            print("pyscreenshot not installed.")
        except Exception as e:
            print("Error saving snapshot:", e)


# -------------------------------------
# RUN
# -------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()

