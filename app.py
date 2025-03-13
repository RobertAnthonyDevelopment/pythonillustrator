import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from PIL import Image, ImageTk, ImageDraw, ImageFont  # For image-based layer or text manipulations

# Constants for default values
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14
UNDO_STACK_LIMIT = 10

class Layer:
    """
    Represents a layer in the editor.
    Each layer can have:
      - A list of shapes (canvas items or reference to data)
      - Visibility (on/off)
      - Lock state
      - Name
    """
    def __init__(self, name, visible=True, locked=False):
        self.name = name
        self.visible = visible
        self.locked = locked
        self.items = []  # list of (canvas_item_id, shape_type)
    
    def add_item(self, item_id, shape_type):
        self.items.append((item_id, shape_type))
    
    def remove_item(self, item_id):
        self.items = [(iid, t) for (iid, t) in self.items if iid != item_id]

class SimpleImageEditor:
    def __init__(self, root):
        self.root = root
        root.title("SimpleImageEditor")
        root.minsize(1000, 600)

        # Undo stack
        self.undo_stack = []

        # Top-level frames: toolbar on the left, main area in the center, layers on the right
        self.toolbar_frame = tk.Frame(root, width=60, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.main_frame = tk.Frame(root)
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.layers_frame = tk.Frame(root, width=200, bg="#F0F0F0")
        self.layers_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Toolbar
        self.current_tool = None
        self.tool_buttons = {}
        self.setup_toolbar()

        # Canvas area
        self.canvas = tk.Canvas(self.main_frame, bg="white", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Variables for shape drawing, selection, transformations
        self.start_x = None
        self.start_y = None
        self.last_x = None
        self.last_y = None
        self.temp_item = None
        self.selected_item = None
        self.selected_layer = None  # The layer the selected item belongs to

        # Drawing settings
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE

        # Layers management
        self.layers = []
        self.current_layer_index = None
        self.setup_layers_panel()

        # Tool option panel (color pickers, brush size slider, etc.)
        self.setup_tool_options_panel()

        # Canvas bindings for drawing or transformations
        self.canvas.bind("<Button-1>", self.on_left_button_down)
        self.canvas.bind("<B1-Motion>", self.on_left_button_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_button_up)

        # Keyboard shortcuts
        self.root.bind("<Control-z>", self.undo)  # Undo
        self.root.bind("<Control-Z>", self.undo)  # Shift+Ctrl+Z, same as Ctrl+z
        # Additional shortcuts can be bound for tool switching, etc.

        # Start by creating an initial layer
        self.add_layer()

    # -----------------------------
    # Toolbar and Tools
    # -----------------------------
    def setup_toolbar(self):
        """
        Create the toolbar buttons for different tools.
        In a real scenario, you might load icons for each button.
        """
        tools = [
            ("Select", None),
            ("Brush", None),
            ("Line", None),
            ("Rectangle", None),
            ("Ellipse", None),
            ("Text", None),
            ("Eraser", None),
        ]

        for (tool_name, icon_path) in tools:
            btn = tk.Button(self.toolbar_frame, text=tool_name, command=lambda t=tool_name: self.select_tool(t))
            btn.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool_name] = btn
        
        # By default, select the 'Select' tool
        self.select_tool("Select")

        # Additional toolbar features
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)

    def select_tool(self, tool_name):
        self.current_tool = tool_name
        # Update button appearance to indicate selected tool
        for tname, btn in self.tool_buttons.items():
            if tname == tool_name:
                btn.config(relief=tk.SUNKEN, bg="#a0cfe6")
            else:
                btn.config(relief=tk.RAISED, bg="SystemButtonFace")

    # -----------------------------
    # Layers Panel
    # -----------------------------
    def setup_layers_panel(self):
        tk.Label(self.layers_frame, text="Layers", bg="#F0F0F0", font=("Arial", 12, "bold")).pack(pady=5)
        
        # Frame to hold the listbox and controls
        list_frame = tk.Frame(self.layers_frame, bg="#F0F0F0")
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.layer_listbox = tk.Listbox(list_frame)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.layer_listbox.bind("<<ListboxSelect>>", self.on_layer_select)

        # Scrollbar (optional)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=scrollbar.set)

        # Layer control buttons
        ctrl_frame = tk.Frame(self.layers_frame, bg="#F0F0F0")
        ctrl_frame.pack(fill=tk.X)
        tk.Button(ctrl_frame, text="Up", command=self.move_layer_up).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Down", command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Delete", command=self.delete_layer).pack(side=tk.LEFT, padx=2)

    def add_layer(self, layer_name=None):
        """
        Add a new layer (empty by default).
        """
        if layer_name is None:
            layer_name = f"Layer {len(self.layers)+1}"
        new_layer = Layer(layer_name)
        self.layers.insert(0, new_layer)  # top of the stack
        self.layer_listbox.insert(0, layer_name)
        self.layer_listbox.selection_clear(0, tk.END)
        self.layer_listbox.selection_set(0)  # select new layer
        self.on_layer_select(None)

    def on_layer_select(self, event):
        """
        Handler for when the user selects a layer from the listbox.
        Sets the current layer to the selected one.
        """
        selection = self.layer_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.current_layer_index = index

    def move_layer_up(self):
        """
        Move the selected layer up (increase stacking).
        """
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == 0:
            return  # already top
        # Swap in list
        self.layers[idx], self.layers[idx-1] = self.layers[idx-1], self.layers[idx]
        # Update listbox
        name_above = self.layer_listbox.get(idx-1)
        name_current = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx-1, idx)
        self.layer_listbox.insert(idx-1, name_current)
        self.layer_listbox.insert(idx, name_above)
        # Reselect
        self.layer_listbox.selection_set(idx-1)
        self.current_layer_index = idx-1
        # Also update canvas stacking
        layer_moved = self.layers[idx-1]
        layer_above = self.layers[idx]
        for (iid, t) in layer_moved.items:
            # raise each item above items in layer_above
            self.canvas.tag_raise(iid)

    def move_layer_down(self):
        """
        Move the selected layer down (decrease stacking).
        """
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers)-1:
            return  # already bottom
        # Swap in list
        self.layers[idx], self.layers[idx+1] = self.layers[idx+1], self.layers[idx]
        # Update listbox
        name_current = self.layer_listbox.get(idx)
        name_below = self.layer_listbox.get(idx+1)
        self.layer_listbox.delete(idx, idx+1)
        self.layer_listbox.insert(idx, name_below)
        self.layer_listbox.insert(idx+1, name_current)
        # Reselect
        self.layer_listbox.selection_set(idx+1)
        self.current_layer_index = idx+1
        # Also update canvas stacking
        layer_moved = self.layers[idx+1]
        layer_below = self.layers[idx]
        for (iid, t) in layer_moved.items:
            # lower each item below items in layer_below
            self.canvas.tag_lower(iid)

    def delete_layer(self):
        """
        Delete the selected layer and all its items from the canvas.
        """
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        layer_to_delete = self.layers[idx]
        # Delete all items from canvas
        for (iid, shape_type) in layer_to_delete.items:
            self.canvas.delete(iid)
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0

    # -----------------------------
    # Tool Options Panel
    # -----------------------------
    def setup_tool_options_panel(self):
        # We'll place this panel at the bottom of main_frame
        self.tool_options_frame = tk.Frame(self.main_frame, bg="#DDD", height=50)
        self.tool_options_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Color pickers
        tk.Label(self.tool_options_frame, text="Stroke:").pack(side=tk.LEFT, padx=5)
        self.stroke_btn = tk.Button(self.tool_options_frame, bg=DEFAULT_STROKE_COLOR, width=3,
                                    command=self.pick_stroke_color)
        self.stroke_btn.pack(side=tk.LEFT, padx=5)
        tk.Label(self.tool_options_frame, text="Fill:").pack(side=tk.LEFT)
        self.fill_btn = tk.Button(self.tool_options_frame, bg=DEFAULT_FILL_COLOR, width=3,
                                  command=self.pick_fill_color)
        self.fill_btn.pack(side=tk.LEFT, padx=5)

        # Brush size slider
        tk.Label(self.tool_options_frame, text="Brush Size:").pack(side=tk.LEFT, padx=5)
        self.brush_size_slider = ttk.Scale(self.tool_options_frame, from_=1, to=20, orient=tk.HORIZONTAL,
                                           command=self.on_brush_size_change)
        self.brush_size_slider.set(DEFAULT_BRUSH_SIZE)
        self.brush_size_slider.pack(side=tk.LEFT, padx=5)

        # Font size
        tk.Label(self.tool_options_frame, text="Font Size:").pack(side=tk.LEFT, padx=5)
        self.font_size_spin = ttk.Spinbox(self.tool_options_frame, from_=8, to=72, width=4,
                                          command=self.on_font_size_change)
        self.font_size_spin.set(str(DEFAULT_FONT_SIZE))
        self.font_size_spin.pack(side=tk.LEFT, padx=5)

    def pick_stroke_color(self):
        color_code = colorchooser.askcolor(title="Choose Stroke Color", initialcolor=self.stroke_color)
        if color_code and color_code[1]:
            self.stroke_color = color_code[1]
            self.stroke_btn.config(bg=self.stroke_color)

    def pick_fill_color(self):
        color_code = colorchooser.askcolor(title="Choose Fill Color", initialcolor=self.fill_color)
        if color_code and color_code[1]:
            self.fill_color = color_code[1]
            self.fill_btn.config(bg=self.fill_color)

    def on_brush_size_change(self, event=None):
        self.brush_size = int(float(self.brush_size_slider.get()))

    def on_font_size_change(self):
        try:
            val = int(self.font_size_spin.get())
            self.font_size = val
        except ValueError:
            pass

    # -----------------------------
    # Canvas Mouse Event Handlers
    # -----------------------------
    def on_left_button_down(self, event):
        """
        Mouse down: either select item or start drawing shape/line/brush.
        """
        if self.current_layer_index is None:
            # If no layer selected, auto-select top layer
            if self.layers:
                self.current_layer_index = 0
                self.layer_listbox.selection_set(0)
            else:
                return  # no layers to draw on

        current_layer = self.layers[self.current_layer_index]
        # If layer is locked or not visible, do nothing
        if current_layer.locked or not current_layer.visible:
            return

        self.start_x, self.start_y = event.x, event.y
        self.last_x, self.last_y = event.x, event.y

        if self.current_tool == "Select":
            # Attempt to select top item under cursor
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                iid = item[0]
                # Check if this item is in the current layer
                belongs_to = self.find_layer_of_item(iid)
                if belongs_to is not None and not belongs_to.locked:
                    self.select_item(iid)
                else:
                    self.select_item(None)
            else:
                self.select_item(None)

        elif self.current_tool == "Brush":
            # Create a small line or dot to start
            line_id = self.canvas.create_line(event.x, event.y, event.x+1, event.y+1,
                                              fill=self.stroke_color, width=self.brush_size)
            current_layer.add_item(line_id, "Brush")
            self.push_undo(("create", line_id))
            self.select_item(line_id)

        elif self.current_tool == "Eraser":
            # Erase topmost item
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                iid = item[0]
                self.erase_item(iid)
            # For drag erasing, you might continuously erase in on_left_button_drag

        elif self.current_tool == "Text":
            text_id = self.canvas.create_text(event.x, event.y, text="Sample",
                                              fill=self.stroke_color,
                                              font=("Arial", self.font_size))
            current_layer.add_item(text_id, "Text")
            self.push_undo(("create", text_id))
            self.select_item(text_id)

        elif self.current_tool in ("Line", "Rectangle", "Ellipse"):
            self.temp_item = None  # We'll build this in the drag event

    def on_left_button_drag(self, event):
        if self.current_layer_index is None:
            return
        current_layer = self.layers[self.current_layer_index]
        if current_layer.locked or not current_layer.visible:
            return

        if self.current_tool == "Brush":
            line_id = self.canvas.create_line(self.last_x, self.last_y, event.x, event.y,
                                              fill=self.stroke_color, width=self.brush_size)
            current_layer.add_item(line_id, "Brush")
            self.push_undo(("create", line_id))
            self.select_item(line_id)
            self.last_x, self.last_y = event.x, event.y

        elif self.current_tool == "Eraser":
            # Erase items we drag over
            item = self.canvas.find_closest(event.x, event.y)
            if item:
                iid = item[0]
                self.erase_item(iid)

        elif self.current_tool == "Line":
            # Remove old preview
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            self.temp_item = self.canvas.create_line(self.start_x, self.start_y, event.x, event.y,
                                                     fill=self.stroke_color, width=self.brush_size)
        elif self.current_tool == "Rectangle":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            self.temp_item = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y,
                                                          outline=self.stroke_color,
                                                          fill=self.fill_color,
                                                          width=self.brush_size)
        elif self.current_tool == "Ellipse":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            self.temp_item = self.canvas.create_oval(self.start_x, self.start_y, event.x, event.y,
                                                     outline=self.stroke_color,
                                                     fill=self.fill_color,
                                                     width=self.brush_size)

    def on_left_button_up(self, event):
        if self.current_tool in ("Line", "Rectangle", "Ellipse") and self.temp_item:
            # finalize
            current_layer = self.layers[self.current_layer_index]
            shape_type = self.current_tool
            current_layer.add_item(self.temp_item, shape_type)
            self.push_undo(("create", self.temp_item))
            self.select_item(self.temp_item)
            self.temp_item = None

    def select_item(self, item_id):
        # Remove highlight from previously selected
        if self.selected_item:
            try:
                self.canvas.itemconfig(self.selected_item, width=self.brush_size)
            except:
                pass
        self.selected_item = item_id
        if item_id:
            try:
                # highlight new
                self.canvas.itemconfig(item_id, width=max(self.brush_size+2, 3))
            except:
                pass

    def erase_item(self, item_id):
        layer_of_item = self.find_layer_of_item(item_id)
        if layer_of_item and not layer_of_item.locked:
            layer_of_item.remove_item(item_id)
            self.push_undo(("delete", item_id, self.canvas.type(item_id),
                            self.canvas.coords(item_id), 
                            self.canvas.itemconfig(item_id)))
            self.canvas.delete(item_id)
            if self.selected_item == item_id:
                self.selected_item = None

    def find_layer_of_item(self, item_id):
        """
        Returns the layer that contains this item_id or None.
        """
        for layer in self.layers:
            for (iid, t) in layer.items:
                if iid == item_id:
                    return layer
        return None

    # -----------------------------
    # Undo Management
    # -----------------------------
    def push_undo(self, action):
        """
        Action could be: 
          ("create", item_id)
          ("delete", item_id, item_type, coords, config)
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
            # Means we created an item
            item_id = action[1]
            # Remove it from canvas and from layer
            layer = self.find_layer_of_item(item_id)
            if layer:
                layer.remove_item(item_id)
            self.canvas.delete(item_id)
            if item_id == self.selected_item:
                self.selected_item = None

        elif atype == "delete":
            # Means we deleted an item, so restore it
            item_id, item_type, coords, config = action[1], action[2], action[3], action[4]
            # Recreate
            if item_type == "line":
                restored_id = self.canvas.create_line(*coords)
            elif item_type == "rectangle":
                restored_id = self.canvas.create_rectangle(*coords)
            elif item_type == "oval":
                restored_id = self.canvas.create_oval(*coords)
            elif item_type == "text":
                # We need text specifics from config
                text_val = config["text"][-1] if "text" in config else "RestoredText"
                restored_id = self.canvas.create_text(coords[0], coords[1], text=text_val)
            elif item_type == "polygon":
                restored_id = self.canvas.create_polygon(*coords)
            else:
                # fallback
                restored_id = self.canvas.create_line(*coords)

            # Apply config
            for ckey, cval in config.items():
                # cval is a tuple like ('fill', '#xxxxxx'), so cval[-1] is the actual color
                # or it might be another structure. Let's assume last is the value
                try:
                    self.canvas.itemconfig(restored_id, {ckey: cval[-1]})
                except:
                    pass

            # Insert back into the top layer (or create a new default layer?)
            if not self.layers:
                self.add_layer()
            self.layers[0].add_item(restored_id, item_type)

    # -----------------------------
    # Layered Image: open and save
    # -----------------------------
    def open_image_layer(self):
        """Open an image file and create a new layer containing it."""
        file_path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=(("Image Files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("All Files", "*.*"))
        )
        if not file_path:
            return
        
        img = Image.open(file_path)
        # Convert to PhotoImage for canvas
        tk_img = ImageTk.PhotoImage(img)
        image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
        # We must store a reference to keep it displayed
        self.canvas.image = tk_img

        # Add to a new layer
        layer_name = f"ImageLayer_{file_path.split('/')[-1]}"
        self.add_layer(layer_name)
        self.layers[0].add_item(image_id, "Image")
        self.select_tool("Select")

    def save_canvas_snapshot(self):
        """Save the current canvas as an image (flattened)."""
        file_path = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".png",
            filetypes=[("PNG Files", "*.png"), ("All Files", "*.*")]
        )
        if not file_path:
            return
        
        # Get canvas bounding box
        self.canvas.update()
        x0 = self.root.winfo_rootx() + self.canvas.winfo_x()
        y0 = self.root.winfo_rooty() + self.canvas.winfo_y()
        x1 = x0 + self.canvas.winfo_width()
        y1 = y0 + self.canvas.winfo_height()
        
        # Use Pillow to grab the screen region of the canvas
        try:
            import pyscreenshot as ImageGrab
            img = ImageGrab.grab(bbox=(x0, y0, x1, y1))
            img.save(file_path)
        except ImportError:
            # If pyscreenshot or PIL's ImageGrab is not available on some platforms,
            # you'd have to rely on other methods
            print("pyscreenshot not installed. Cannot save canvas snapshot.")

# Example usage:
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()

