import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from PIL import Image, ImageTk

# If you want advanced text manipulation, you might do: from PIL import ImageDraw, ImageFont
# For saving snapshots with pyscreenshot (optional):
# import pyscreenshot as ImageGrab

# Constants
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14
UNDO_STACK_LIMIT = 10

class Layer:
    """
    Represents a layer in the editor, holding canvas items and
    controlling visibility, etc.
    """
    def __init__(self, name, visible=True, locked=False):
        self.name = name
        self.visible = visible
        self.locked = locked
        # List of (canvas_item_id, shape_type)
        self.items = []
    
    def add_item(self, item_id, shape_type):
        self.items.append((item_id, shape_type))
    
    def remove_item(self, item_id):
        self.items = [(iid, t) for (iid, t) in self.items if iid != item_id]

class SimpleImageEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("SimpleImageEditor")
        self.root.geometry("1200x700")  # set a decent starting size

        # Set up main frames: left (toolbar), center (canvas & options), right (layers)
        self.toolbar_frame = tk.Frame(self.root, width=80, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.layers_frame = tk.Frame(self.root, width=200, bg="#F0F0F0")
        self.layers_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Undo stack
        self.undo_stack = []

        # Tools
        self.current_tool = None
        self.tool_buttons = {}

        # Canvas
        self.canvas = None

        # Drawing attributes
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE

        # For shape drawing (line, rectangle, ellipse)
        self.start_x = None
        self.start_y = None
        self.temp_item = None
        self.selected_item = None

        # For brush or eraser
        self.last_x = None
        self.last_y = None

        # Bend tool state
        self.bend_drafting = False
        self.bend_points = []

        # Layers
        self.layers = []
        self.current_layer_index = None

        # Build UI
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options_panel()
        self.setup_layers_panel()

        # Keyboard shortcuts
        self.root.bind("<Control-z>", self.undo)
        self.root.bind("<Control-Z>", self.undo)

        # Start with one default layer
        self.add_layer()

    # ------------------------------------------------
    # UI SETUP
    # ------------------------------------------------
    def setup_toolbar(self):
        """Create the buttons for tools on the left toolbar."""
        tools = [
            ("Select", None),
            ("Brush", None),
            ("Line", None),
            ("Rectangle", None),
            ("Ellipse", None),
            ("Text", None),
            ("Eraser", None),
            ("Bend", None),
        ]
        for (tool_name, _) in tools:
            b = tk.Button(self.toolbar_frame, text=tool_name,
                          command=lambda t=tool_name: self.select_tool(t))
            b.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool_name] = b
        
        # Additional utility buttons on the toolbar
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer)\
            .pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image_layer)\
            .pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot)\
            .pack(pady=5, fill=tk.X)

        # Default tool
        self.select_tool("Select")

    def setup_canvas(self):
        """Create the canvas in the main_frame."""
        self.canvas = tk.Canvas(self.main_frame, bg="white", cursor="cross")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Bind mouse events to the canvas for drawing
        self.canvas.bind("<Button-1>", self.on_left_button_down)
        self.canvas.bind("<B1-Motion>", self.on_left_button_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_button_up)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)  # for bend finalization

    def setup_tool_options_panel(self):
        """Place color pickers, brush size slider, font size spinbox at the bottom."""
        self.tool_options_frame = tk.Frame(self.main_frame, height=50, bg="#DDDDDD")
        self.tool_options_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Stroke color
        tk.Label(self.tool_options_frame, text="Stroke:").pack(side=tk.LEFT, padx=5)
        self.stroke_btn = tk.Button(self.tool_options_frame, bg=self.stroke_color, width=3,
                                    command=self.pick_stroke_color)
        self.stroke_btn.pack(side=tk.LEFT, padx=5)

        # Fill color
        tk.Label(self.tool_options_frame, text="Fill:").pack(side=tk.LEFT, padx=5)
        self.fill_btn = tk.Button(self.tool_options_frame, bg=self.fill_color, width=3,
                                  command=self.pick_fill_color)
        self.fill_btn.pack(side=tk.LEFT, padx=5)

        # Brush size
        tk.Label(self.tool_options_frame, text="Brush Size:").pack(side=tk.LEFT, padx=5)
        self.brush_size_slider = ttk.Scale(self.tool_options_frame, from_=1, to=20,
                                           orient=tk.HORIZONTAL, command=self.on_brush_size_change)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT, padx=5)

        # Font size
        tk.Label(self.tool_options_frame, text="Font Size:").pack(side=tk.LEFT, padx=5)
        self.font_size_spin = ttk.Spinbox(self.tool_options_frame, from_=8, to=72, width=4,
                                          command=self.on_font_size_change)
        self.font_size_spin.set(str(self.font_size))
        self.font_size_spin.pack(side=tk.LEFT, padx=5)

    def setup_layers_panel(self):
        """Right panel with a listbox for layers and control buttons."""
        tk.Label(self.layers_frame, text="Layers", bg="#F0F0F0",
                 font=("Arial", 12, "bold")).pack(pady=5)

        # Listbox + scrollbar
        list_frame = tk.Frame(self.layers_frame, bg="#F0F0F0")
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.layer_listbox = tk.Listbox(list_frame)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.layer_listbox.bind("<<ListboxSelect>>", self.on_layer_select)

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=scrollbar.set)

        # Buttons below the listbox
        ctrl_frame = tk.Frame(self.layers_frame, bg="#F0F0F0")
        ctrl_frame.pack(fill=tk.X)
        tk.Button(ctrl_frame, text="Up", command=self.move_layer_up).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Down", command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Hide/Show", command=self.toggle_layer_visibility).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Delete", command=self.delete_layer).pack(side=tk.LEFT, padx=2)

    # ------------------------------------------------
    # TOOL SELECTION
    # ------------------------------------------------
    def select_tool(self, tool_name):
        """
        Called when a toolbar button is clicked.
        If we were in the middle of bending, finalize or discard
        that bend if we switch away from 'Bend'.
        """
        if self.bend_drafting and self.current_tool == "Bend" and tool_name != "Bend":
            # Discard the partially drawn curve
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            self.bend_points.clear()
            self.bend_drafting = False
            self.temp_item = None

        self.current_tool = tool_name
        # Update button appearance
        for name, btn in self.tool_buttons.items():
            if name == tool_name:
                btn.config(relief=tk.SUNKEN, bg="#a0cfe6")
            else:
                btn.config(relief=tk.RAISED, bg="SystemButtonFace")

    # ------------------------------------------------
    # LAYERS
    # ------------------------------------------------
    def add_layer(self, layer_name=None):
        if layer_name is None:
            layer_name = f"Layer {len(self.layers) + 1}"
        new_layer = Layer(layer_name)
        # Insert at top
        self.layers.insert(0, new_layer)
        self.layer_listbox.insert(0, layer_name)
        # select
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
            return  # already top
        # Swap
        self.layers[idx], self.layers[idx-1] = self.layers[idx-1], self.layers[idx]
        above_name = self.layer_listbox.get(idx-1)
        current_name = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx-1, idx)
        self.layer_listbox.insert(idx-1, current_name)
        self.layer_listbox.insert(idx, above_name)
        self.layer_listbox.selection_set(idx-1)
        self.current_layer_index = idx-1
        # Raise items
        for (iid, shape_type) in self.layers[idx-1].items:
            self.canvas.tag_raise(iid)

    def move_layer_down(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers)-1:
            return  # bottom
        # Swap
        self.layers[idx], self.layers[idx+1] = self.layers[idx+1], self.layers[idx]
        current_name = self.layer_listbox.get(idx)
        below_name = self.layer_listbox.get(idx+1)
        self.layer_listbox.delete(idx, idx+1)
        self.layer_listbox.insert(idx, below_name)
        self.layer_listbox.insert(idx+1, current_name)
        self.layer_listbox.selection_set(idx+1)
        self.current_layer_index = idx+1
        # Lower items
        for (iid, shape_type) in self.layers[idx+1].items:
            self.canvas.tag_lower(iid)

    def toggle_layer_visibility(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        layer = self.layers[idx]
        layer.visible = not layer.visible
        new_state = tk.NORMAL if layer.visible else tk.HIDDEN
        # Update canvas items
        for (iid, shape_type) in layer.items:
            self.canvas.itemconfigure(iid, state=new_state)
        # Reflect in listbox label
        self.layer_listbox.delete(idx)
        label = layer.name
        if not layer.visible:
            label += " (hidden)"
        self.layer_listbox.insert(idx, label)
        self.layer_listbox.selection_set(idx)

    def delete_layer(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        layer_to_delete = self.layers[idx]
        for (iid, shape_type) in layer_to_delete.items:
            self.canvas.delete(iid)
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0

    # ------------------------------------------------
    # COLORS & SIZES
    # ------------------------------------------------
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
        val = self.brush_size_slider.get()
        self.brush_size = int(float(val))

    def on_font_size_change(self):
        try:
            v = int(self.font_size_spin.get())
            self.font_size = v
        except ValueError:
            pass

    # ------------------------------------------------
    # CANVAS EVENT HANDLERS
    # ------------------------------------------------
    def on_left_button_down(self, event):
        if self.current_layer_index is None:
            if self.layers:
                self.current_layer_index = 0
                self.layer_listbox.selection_set(0)
            else:
                return

        layer = self.layers[self.current_layer_index]
        if layer.locked or not layer.visible:
            return

        self.start_x, self.start_y = event.x, event.y
        self.last_x, self.last_y = event.x, event.y

        if self.current_tool == "Select":
            closest = self.canvas.find_closest(event.x, event.y)
            if closest:
                iid = closest[0]
                belongs_to = self.find_layer_of_item(iid)
                if belongs_to and not belongs_to.locked:
                    self.select_item(iid)
                else:
                    self.select_item(None)
            else:
                self.select_item(None)

        elif self.current_tool == "Brush":
            line_id = self.canvas.create_line(event.x, event.y, event.x+1, event.y+1,
                                              fill=self.stroke_color, width=self.brush_size)
            layer.add_item(line_id, "Brush")
            self.push_undo(("create", line_id))
            self.select_item(line_id)

        elif self.current_tool == "Eraser":
            closest = self.canvas.find_closest(event.x, event.y)
            if closest:
                self.erase_item(closest[0])

        elif self.current_tool == "Text":
            text_id = self.canvas.create_text(event.x, event.y, text="Sample",
                                              fill=self.stroke_color,
                                              font=("Arial", self.font_size))
            layer.add_item(text_id, "Text")
            self.push_undo(("create", text_id))
            self.select_item(text_id)

        elif self.current_tool in ("Line", "Rectangle", "Ellipse"):
            self.temp_item = None

        elif self.current_tool == "Bend":
            if not self.bend_drafting:
                self.bend_drafting = True
                self.bend_points = [(event.x, event.y)]
                self.temp_item = None
            else:
                self.bend_points.append((event.x, event.y))
            self.update_bend_curve()

    def on_left_button_drag(self, event):
        if self.current_layer_index is None:
            return
        layer = self.layers[self.current_layer_index]
        if layer.locked or not layer.visible:
            return

        if self.current_tool == "Brush":
            line_id = self.canvas.create_line(self.last_x, self.last_y, event.x, event.y,
                                              fill=self.stroke_color, width=self.brush_size)
            layer.add_item(line_id, "Brush")
            self.push_undo(("create", line_id))
            self.select_item(line_id)
            self.last_x, self.last_y = event.x, event.y

        elif self.current_tool == "Eraser":
            closest = self.canvas.find_closest(event.x, event.y)
            if closest:
                self.erase_item(closest[0])

        elif self.current_tool == "Line":
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
        # finalize line/rect/ellipse if we have a temp item
        if self.current_tool in ("Line", "Rectangle", "Ellipse") and self.temp_item:
            layer = self.layers[self.current_layer_index]
            shape_type = self.current_tool
            layer.add_item(self.temp_item, shape_type)
            self.push_undo(("create", self.temp_item))
            self.select_item(self.temp_item)
            self.temp_item = None

    def on_double_click(self, event):
        """
        Double-click finalizes the Bend tool's curve if drafting one.
        """
        if self.current_tool == "Bend" and self.bend_drafting:
            self.finalize_bend_curve()

    # ------------------------------------------------
    # BEND TOOL LOGIC
    # ------------------------------------------------
    def update_bend_curve(self):
        if len(self.bend_points) < 2:
            return
        if self.temp_item:
            self.canvas.delete(self.temp_item)

        pts = []
        for (x, y) in self.bend_points:
            pts.extend([x, y])

        self.temp_item = self.canvas.create_line(
            *pts,
            fill=self.stroke_color,
            width=self.brush_size,
            smooth=True,
            splinesteps=36
        )

    def finalize_bend_curve(self):
        if not self.temp_item:
            # no shape
            self.bend_points.clear()
            self.bend_drafting = False
            return

        layer = self.layers[self.current_layer_index]
        layer.add_item(self.temp_item, "Bend")
        self.push_undo(("create", self.temp_item))
        self.select_item(self.temp_item)

        self.bend_points.clear()
        self.temp_item = None
        self.bend_drafting = False

    # ------------------------------------------------
    # SELECTION & ERASING
    # ------------------------------------------------
    def select_item(self, item_id):
        # Remove highlight from previously selected
        if self.selected_item:
            try:
                self.canvas.itemconfig(self.selected_item, width=self.brush_size)
            except:
                pass
        self.selected_item = item_id
        if item_id:
            # highlight by thickening the outline
            try:
                self.canvas.itemconfig(item_id, width=max(self.brush_size + 2, 3))
            except:
                pass

    def erase_item(self, item_id):
        layer = self.find_layer_of_item(item_id)
        if layer and not layer.locked:
            layer.remove_item(item_id)
            self.push_undo(("delete", item_id,
                            self.canvas.type(item_id),
                            self.canvas.coords(item_id),
                            self.canvas.itemconfig(item_id)))
            self.canvas.delete(item_id)
            if self.selected_item == item_id:
                self.selected_item = None

    def find_layer_of_item(self, item_id):
        for l in self.layers:
            for (iid, t) in l.items:
                if iid == item_id:
                    return l
        return None

    # ------------------------------------------------
    # UNDO
    # ------------------------------------------------
    def push_undo(self, action):
        """
        Action is either:
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
            # Remove the created item
            item_id = action[1]
            layer = self.find_layer_of_item(item_id)
            if layer:
                layer.remove_item(item_id)
            self.canvas.delete(item_id)
            if item_id == self.selected_item:
                self.selected_item = None

        elif atype == "delete":
            # Restore item
            item_id, item_type, coords, config = action[1], action[2], action[3], action[4]
            if item_type == "line":
                restored_id = self.canvas.create_line(*coords)
            elif item_type == "rectangle":
                restored_id = self.canvas.create_rectangle(*coords)
            elif item_type == "oval":
                restored_id = self.canvas.create_oval(*coords)
            elif item_type == "text":
                text_val = config.get("text", ("", "Restored"))[-1]
                restored_id = self.canvas.create_text(coords[0], coords[1], text=text_val)
            elif item_type in ("polygon", "Bend"):
                # Bend was created with create_line(..., smooth=True)
                restored_id = self.canvas.create_line(*coords, smooth=True)
            else:
                # fallback
                restored_id = self.canvas.create_line(*coords)

            for ckey, cval in config.items():
                try:
                    self.canvas.itemconfig(restored_id, {ckey: cval[-1]})
                except:
                    pass

            # Put it back into the top layer (or create a new layer if none)
            if not self.layers:
                self.add_layer()
            self.layers[0].add_item(restored_id, item_type)

    # ------------------------------------------------
    # OPEN/SAVE
    # ------------------------------------------------
    def open_image_layer(self):
        file_path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=(("Image Files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("All Files", "*.*"))
        )
        if not file_path:
            return
        try:
            img = Image.open(file_path)
        except Exception as e:
            print("Could not open image:", e)
            return
        tk_img = ImageTk.PhotoImage(img)
        image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
        # keep a reference
        self.canvas.image = tk_img

        layer_name = f"ImageLayer_{file_path.split('/')[-1]}"
        self.add_layer(layer_name)
        self.layers[0].add_item(image_id, "Image")
        self.select_tool("Select")

    def save_canvas_snapshot(self):
        file_path = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".png",
            filetypes=[("PNG Files", "*.png"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        self.canvas.update()
        x0 = self.root.winfo_rootx() + self.canvas.winfo_x()
        y0 = self.root.winfo_rooty() + self.canvas.winfo_y()
        x1 = x0 + self.canvas.winfo_width()
        y1 = y0 + self.canvas.winfo_height()

        # If you have pyscreenshot installed, you can do:
        try:
            import pyscreenshot as ImageGrab
            im = ImageGrab.grab(bbox=(x0, y0, x1, y1))
            im.save(file_path)
        except ImportError:
            print("pyscreenshot not installed. Cannot save canvas snapshot.")
        except Exception as e:
            print("Error while saving snapshot:", e)


# --------------------------
# Run the editor
# --------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()



