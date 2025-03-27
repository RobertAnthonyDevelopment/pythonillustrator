import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog
import copy
import math

# Attempt Pillow import for image support
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: Pillow (PIL) not installed. Some features may fail.")

# ------------------------------------------------------------------------------
# GLOBAL CONSTANTS
# ------------------------------------------------------------------------------
DEFAULT_BRUSH_SIZE = 3
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_FILL_COLOR = "#FFFFFF"
DEFAULT_FONT_SIZE = 14

MAX_HISTORY = 30
ERASER_RADIUS = 15.0
SOFT_ERASER_FADE_STEP = 20

# Bend tool parameters (adjust as needed)
BEND_RADIUS_A = 60.0   # Tool A: push/anchor-drag bending
BEND_RADIUS_B = 50.0   # Tool B: arc-based bending

# Threshold (pixels) for auto-connecting endpoints
CONNECT_THRESHOLD = 10

# ------------------------------------------------------------------------------
# TEXT EDITOR DIALOG CLASS
# ------------------------------------------------------------------------------
class TextEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, title="Edit Text", initial_props=None):
        self.initial_props = initial_props or {
            "text": "",
            "font": "Arial",
            "font_size": DEFAULT_FONT_SIZE,
            "fill": DEFAULT_STROKE_COLOR
        }
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="Text:").grid(row=0, column=0, sticky="w")
        self.text_var = tk.StringVar(value=self.initial_props["text"])
        tk.Entry(master, textvariable=self.text_var, width=40).grid(row=0, column=1)
        
        tk.Label(master, text="Font:").grid(row=1, column=0, sticky="w")
        self.font_var = tk.StringVar(value=self.initial_props["font"])
        tk.Entry(master, textvariable=self.font_var).grid(row=1, column=1)
        
        tk.Label(master, text="Font Size:").grid(row=2, column=0, sticky="w")
        self.size_var = tk.IntVar(value=self.initial_props["font_size"])
        tk.Entry(master, textvariable=self.size_var).grid(row=2, column=1)
        
        tk.Label(master, text="Fill Color:").grid(row=3, column=0, sticky="w")
        self.fill_var = tk.StringVar(value=self.initial_props["fill"])
        tk.Entry(master, textvariable=self.fill_var).grid(row=3, column=1)
        return master

    def apply(self):
        self.result = {
            "text": self.text_var.get(),
            "font": self.font_var.get(),
            "font_size": self.size_var.get(),
            "fill": self.fill_var.get()
        }

# ------------------------------------------------------------------------------
# LAYER CLASS
# ------------------------------------------------------------------------------
class Layer:
    """
    A layer holds a name, visibility and lock status, plus a list of items.
    Each item is a tuple (canvas_item_id, shape_type).
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
# SHAPE DATA CLASS
# ------------------------------------------------------------------------------
class ShapeData:
    """
    Stores data for each drawn shape.
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
        if shape_type in ("line", "brush", "bending_line", "editable_text"):
            self.shapes[item_id]['anchors'] = []
        if shape_type == "group":
            self.shapes[item_id]['children'] = []

    def remove(self, item_id):
        if item_id in self.shapes:
            del self.shapes[item_id]

    def get(self, item_id):
        return self.shapes.get(item_id)

    def update_coords(self, item_id, new_coords):
        if item_id in self.shapes:
            self.shapes[item_id]['coords'] = new_coords[:]

# ------------------------------------------------------------------------------
# EDITOR HISTORY CLASS
# ------------------------------------------------------------------------------
class EditorHistory:
    """
    Simple linear history for undo/redo.
    """
    def __init__(self):
        self.states = []
        self.current_index = -1

    def push_state(self, shape_data, layers, description):
        if self.current_index < len(self.states) - 1:
            self.states = self.states[:self.current_index + 1]
        if len(self.states) >= MAX_HISTORY:
            del self.states[0]
            self.current_index -= 1
        shape_data_copy = copy.deepcopy(shape_data.shapes)
        layers_copy = []
        for lyr in layers:
            new_layer = Layer(lyr.name, lyr.visible, lyr.locked)
            new_layer.items = copy.deepcopy(lyr.items)
            layers_copy.append(new_layer)
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

    def get_all_descriptions(self):
        return [f"{i}: {desc[2]}" for i, desc in enumerate(self.states)]

# ------------------------------------------------------------------------------
# MAIN EDITOR CLASS
# ------------------------------------------------------------------------------
class SimpleImageEditor:
    """
    Main editor class with drawing, text editing, layering and image operations.
    """
    def __init__(self, root):
        self.root = root
        root.title("Enhanced Editor with Anchors, Bending, Editable Text & Image Editing")
        root.geometry("1400x900")

        self.shape_data = ShapeData()
        self.layers = []
        self.current_layer_index = None
        self.selected_items = set()

        self.brush_size = DEFAULT_BRUSH_SIZE
        self.stroke_color = DEFAULT_STROKE_COLOR
        self.fill_color = DEFAULT_FILL_COLOR
        self.font_size = DEFAULT_FONT_SIZE

        self.current_tool = None
        self.tool_buttons = {}

        self.temp_item = None
        self.start_x = None
        self.start_y = None
        self.last_x = None
        self.last_y = None
        self.select_rect_id = None

        self.bendA_active = False
        self.bendB_active = False
        self.bend_dragging = False
        self.bend_target = None
        self.bendA_dragging_anchor_idx = None
        self.bendA_segment_idx = None
        self.bendB_dragging_anchor_idx = None
        self.initial_angle = None

        self.direct_select_dragging_anchor = None
        self.direct_select_drag_index = None

        self.history = EditorHistory()

        # Dictionary to keep a reference to images (store tuples of (PIL_image, PhotoImage))
        self.image_refs = {}

        self.build_frames()
        self.setup_toolbar()
        self.setup_canvas()
        self.setup_tool_options()
        self.setup_layers_panel()
        self.setup_history_panel()

        self.add_layer("Layer 1")
        self.push_history("Initial Setup")

        self.root.bind("<Control-z>", self.on_ctrl_z)
        self.root.bind("<Control-y>", self.on_ctrl_y)
        self.root.bind("<Control-g>", self.group_selected_items)
        self.canvas.bind("<KeyPress-a>", self.on_key_toggle_anchor)
        self.canvas.focus_set()

    # -------------------- UI BUILD METHODS -----------------------------
    def build_frames(self):
        self.toolbar_frame = tk.Frame(self.root, width=140, bg="#E0E0E0")
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.main_frame = tk.Frame(self.root, bg="#DDDDDD")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.side_frame = tk.Frame(self.root, width=300, bg="#F0F0F0")
        self.side_frame.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_toolbar(self):
        tools = [
            "Select", "Direct Select", "Add Anchor",
            "Bend Tool A", "Bend Tool B", "Bend Tool C",
            "Brush", "Line", "Rectangle", "Ellipse",
            "Text", "Sharp Eraser", "Round Eraser", "Soft Eraser", "Group"
        ]
        for tool in tools:
            b = tk.Button(self.toolbar_frame, text=tool,
                          command=lambda t=tool: self.select_tool(t))
            b.pack(pady=5, fill=tk.X)
            self.tool_buttons[tool] = b
        # Extra buttons for image operations and layers
        ttk.Button(self.toolbar_frame, text="Add Layer", command=self.add_layer).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Open Image", command=self.open_image).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Rotate Image", command=self.rotate_image).pack(pady=5, fill=tk.X)
        ttk.Button(self.toolbar_frame, text="Save Canvas", command=self.save_canvas_snapshot).pack(pady=5, fill=tk.X)

    def select_tool(self, tool_name):
        self.current_tool = tool_name
        if tool_name not in ("Select", "Direct Select"):
            self.selected_items.clear()
        self.bendA_active = (tool_name == "Bend Tool A")
        self.bendB_active = (tool_name == "Bend Tool B")
        self.bend_dragging = False
        self.bend_target = None
        self.bendA_dragging_anchor_idx = None
        self.bendA_segment_idx = None
        self.bendB_dragging_anchor_idx = None
        self.initial_angle = None
        if self.select_rect_id:
            self.canvas.delete(self.select_rect_id)
            self.select_rect_id = None
        self.clear_direct_select_anchors()
        for n, btn in self.tool_buttons.items():
            btn.config(relief=tk.SUNKEN if n == tool_name else tk.RAISED,
                       bg=("#a0cfe6" if n == tool_name else "SystemButtonFace"))

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
        self.stroke_btn = tk.Button(f, bg=self.stroke_color, width=3, command=self.pick_stroke_color)
        self.stroke_btn.pack(side=tk.LEFT, padx=5)
        tk.Label(f, text="Fill:").pack(side=tk.LEFT, padx=5)
        self.fill_btn = tk.Button(f, bg=self.fill_color, width=3, command=self.pick_fill_color)
        self.fill_btn.pack(side=tk.LEFT, padx=5)
        tk.Label(f, text="Brush Size:").pack(side=tk.LEFT, padx=5)
        self.brush_size_slider = ttk.Scale(f, from_=1, to=50, orient=tk.HORIZONTAL, command=self.on_brush_size_change)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT, padx=5)
        tk.Label(f, text="Font Size:").pack(side=tk.LEFT, padx=5)
        self.font_size_spin = ttk.Spinbox(f, from_=8, to=144, width=4, command=self.on_font_size_change)
        self.font_size_spin.set(str(self.font_size))
        self.font_size_spin.pack(side=tk.LEFT, padx=5)

    def setup_layers_panel(self):
        lb = tk.Label(self.side_frame, text="Layers", bg="#F0F0F0", font=("Arial", 12, "bold"))
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
        lb = tk.Label(self.side_frame, text="History", bg="#F0F0F0", font=("Arial", 12, "bold"))
        lb.pack(pady=5)
        self.history_listbox = tk.Listbox(self.side_frame)
        self.history_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)
        hf = tk.Frame(self.side_frame, bg="#F0F0F0")
        hf.pack(fill=tk.X)
        tk.Button(hf, text="Undo", command=self.do_undo).pack(side=tk.LEFT, padx=2)
        tk.Button(hf, text="Redo", command=self.do_redo).pack(side=tk.LEFT, padx=2)

    # --------------------- LAYER METHODS -------------------------------
    def add_layer(self, name=None):
        if name is None:
            name = f"Layer {len(self.layers)+1}"
        new_layer = Layer(name)
        self.layers.insert(0, new_layer)
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
        self.layers[idx], self.layers[idx - 1] = self.layers[idx - 1], self.layers[idx]
        u = self.layer_listbox.get(idx - 1)
        c = self.layer_listbox.get(idx)
        self.layer_listbox.delete(idx - 1, idx)
        self.layer_listbox.insert(idx - 1, c)
        self.layer_listbox.insert(idx, u)
        self.layer_listbox.selection_set(idx - 1)
        self.current_layer_index = idx - 1
        for (iid, _) in self.layers[idx - 1].items:
            self.canvas.tag_raise(iid)
        self.push_history(f"Layer {c} moved up")

    def move_layer_down(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == len(self.layers) - 1:
            return
        self.layers[idx], self.layers[idx + 1] = self.layers[idx + 1], self.layers[idx]
        c = self.layer_listbox.get(idx)
        d = self.layer_listbox.get(idx + 1)
        self.layer_listbox.delete(idx, idx + 1)
        self.layer_listbox.insert(idx, d)
        self.layer_listbox.insert(idx + 1, c)
        self.layer_listbox.selection_set(idx + 1)
        self.current_layer_index = idx + 1
        for (iid, _) in self.layers[idx + 1].items:
            self.canvas.tag_lower(iid)
        self.push_history(f"Layer {c} moved down")

    def toggle_layer_visibility(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        layer = self.layers[idx]
        layer.visible = not layer.visible
        new_state = tk.NORMAL if layer.visible else tk.HIDDEN
        for (iid, _) in layer.items:
            self.canvas.itemconfigure(iid, state=new_state)
        nm = layer.name + ("" if layer.visible else " (hidden)")
        self.layer_listbox.delete(idx)
        self.layer_listbox.insert(idx, nm)
        self.layer_listbox.selection_set(idx)
        self.push_history(f"Toggled layer {layer.name}")

    def delete_layer(self):
        sel = self.layer_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        layer = self.layers[idx]
        for (iid, _) in layer.items:
            self.canvas.delete(iid)
            self.shape_data.remove(iid)
        nm = layer.name
        self.layers.pop(idx)
        self.layer_listbox.delete(idx)
        self.current_layer_index = None if not self.layers else 0
        self.selected_items.clear()
        self.push_history(f"Deleted layer {nm}")

    # --------------------- HISTORY METHODS -------------------------------
    def push_history(self, description):
        self.history.push_state(self.shape_data, self.layers, description)
        self.refresh_history_listbox()
        self.auto_connect_lines()

    def refresh_history_listbox(self):
        self.history_listbox.delete(0, tk.END)
        for d in self.history.get_all_descriptions():
            self.history_listbox.insert(tk.END, d)

    def on_history_select(self, event):
        sel = self.history_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        state = self.history.go_to(idx)
        if state:
            self.apply_history_state(state)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def do_undo(self):
        state = self.history.undo()
        if state:
            self.apply_history_state(state)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def do_redo(self):
        state = self.history.redo()
        if state:
            self.apply_history_state(state)
            self.refresh_history_listbox()
            self.history_listbox.selection_set(self.history.current_index)

    def on_ctrl_z(self, event):
        self.do_undo()

    def on_ctrl_y(self, event):
        self.do_redo()

    def apply_history_state(self, state):
        shape_dict, layers_c, desc = state
        self.canvas.delete("all")
        self.shape_data.shapes.clear()
        self.layers.clear()
        self.layer_listbox.delete(0, tk.END)
        self.selected_items.clear()
        for item in list(self.canvas.find_all()):
            self.canvas.delete(item)
        old_to_new = {}
        for old_id, sdata in shape_dict.items():
            stype = sdata['type']
            coords = sdata['coords']
            fill = sdata['fill']
            outl = sdata['outline']
            wd = sdata['width']
            new_id = None
            if stype == "line":
                new_id = self.canvas.create_line(*coords, fill=outl, width=wd,
                                                   smooth=True, splinesteps=36)
            elif stype == "rectangle":
                new_id = self.canvas.create_rectangle(*coords, outline=outl, fill=fill, width=wd)
            elif stype == "ellipse":
                new_id = self.canvas.create_oval(*coords, outline=outl, fill=fill, width=wd)
            elif stype == "editable_text":
                props = sdata.get("text_props", {})
                new_id = self.canvas.create_text(coords[0], coords[1],
                                                 text=props.get("text", ""),
                                                 fill=props.get("fill", self.stroke_color),
                                                 font=(props.get("font", "Arial"), props.get("font_size", DEFAULT_FONT_SIZE)))
                self.canvas.tag_bind(new_id, "<Double-Button-1>", lambda event, id=new_id: self.edit_text_item(id))
            elif stype == "text":
                new_id = self.canvas.create_text(coords[0], coords[1], text="Sample", fill=outl)
            elif stype == "image":
                new_id = self.canvas.create_text(coords[0], coords[1],
                                                 text="(Missing image in snapshot)",
                                                 fill="red")
            elif stype == "group":
                if "children" in sdata and sdata["children"]:
                    bbs = [self.canvas.bbox(child) for child in sdata["children"] if self.canvas.bbox(child)]
                    if bbs:
                        x1 = min(bb[0] for bb in bbs)
                        y1 = min(bb[1] for bb in bbs)
                        x2 = max(bb[2] for bb in bbs)
                        y2 = max(bb[3] for bb in bbs)
                        new_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline="purple", dash=(4,2))
                    else:
                        new_id = self.canvas.create_rectangle(0, 0, 0, 0)
                else:
                    new_id = self.canvas.create_rectangle(0, 0, 0, 0)
            else:
                new_id = self.canvas.create_line(*coords, fill=outl, width=wd)
            old_to_new[old_id] = new_id
            self.shape_data.shapes[new_id] = copy.deepcopy(sdata)
        for laycopy in layers_c:
            new_layer = Layer(laycopy.name, laycopy.visible, laycopy.locked)
            ni = []
            for (iid, st) in laycopy.items:
                if iid in old_to_new:
                    ni.append((old_to_new[iid], st))
            new_layer.items = ni
            self.layers.append(new_layer)
            lbname = laycopy.name + ("" if laycopy.visible else " (hidden)")
            self.layer_listbox.insert(tk.END, lbname)
        for lyr in self.layers:
            if not lyr.visible:
                for (iid, _) in lyr.items:
                    self.canvas.itemconfigure(iid, state=tk.HIDDEN)

    # --------------------- IMAGE METHODS (New) -----------------------------
    def open_image(self):
        """Opens an image file using Pillow and places it on the canvas."""
        if not PIL_AVAILABLE:
            messagebox.showerror("Error", "Pillow is not installed.")
            return
        file_path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Image Files", ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif")), ("All Files", "*.*")]
        )
        if file_path:
            try:
                pil_image = Image.open(file_path)
            except Exception as e:
                messagebox.showerror("Error", f"Unable to open image: {e}")
                return
            tk_image = ImageTk.PhotoImage(pil_image)
            # Create image item on canvas at top-left
            item = self.canvas.create_image(0, 0, anchor="nw", image=tk_image)
            # Store both the PIL image and the PhotoImage to avoid garbage collection
            self.image_refs[item] = (pil_image, tk_image)
            # Store shape data for the image
            self.shape_data.store(item, "image", [0, 0, pil_image.width, pil_image.height], None, "", 0)
            if self.current_layer_index is None:
                self.add_layer("Image Layer")
                self.current_layer_index = 0
            self.layers[self.current_layer_index].add_item(item, "image")
            self.push_history("Opened image")

    def rotate_image(self):
        """Rotates the selected image by an angle provided by the user."""
        if not self.selected_items:
            messagebox.showinfo("Info", "Please select an image first.")
            return
        item = next(iter(self.selected_items))
        shape = self.shape_data.get(item)
        if not shape or shape['type'] != "image":
            messagebox.showinfo("Info", "Selected item is not an image.")
            return
        angle = simpledialog.askfloat("Rotate Image", "Enter rotation angle (degrees):", initialvalue=90)
        if angle is None:
            return
        # Retrieve the current PIL image
        stored = self.image_refs.get(item)
        if not stored:
            messagebox.showerror("Error", "No image found.")
            return
        pil_image, _ = stored
        # Rotate the image using Pillow (expand to adjust the size)
        rotated = pil_image.rotate(angle, expand=True)
        new_tk_image = ImageTk.PhotoImage(rotated)
        self.image_refs[item] = (rotated, new_tk_image)
        self.canvas.itemconfig(item, image=new_tk_image)
        self.push_history("Rotated image")

    # --------------------- EDITABLE TEXT METHODS -----------------------------
    def create_editable_text(self, x, y):
        dialog = TextEditorDialog(self.root, title="Create Text")
        if dialog.result:
            props = dialog.result
            item = self.canvas.create_text(x, y, text=props["text"],
                                           fill=props["fill"],
                                           font=(props["font"], props["font_size"]))
            # Use a simple approximate bounding box
            self.shape_data.store(item, "editable_text", [x, y, x+100, y+30], None, props["fill"], 1)
            self.shape_data.shapes[item]["text_props"] = props
            self.canvas.tag_bind(item, "<Double-Button-1>", lambda event, id=item: self.edit_text_item(id))
            if self.current_layer_index is not None:
                self.layers[self.current_layer_index].add_item(item, "editable_text")
            self.selected_items = {item}
            self.highlight_selection()
            self.push_history("Created editable text")

    def edit_text_item(self, item):
        props = self.shape_data.get(item).get("text_props", {})
        dialog = TextEditorDialog(self.root, title="Edit Text", initial_props=props)
        if dialog.result:
            new_props = dialog.result
            self.canvas.itemconfig(item, text=new_props["text"],
                                   fill=new_props["fill"],
                                   font=(new_props["font"], new_props["font_size"]))
            self.shape_data.shapes[item]["text_props"] = new_props
            self.push_history("Edited text")

    # --------------------- MOUSE EVENT METHODS -----------------------------
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
            if event.state & 0x0001:
                self.handle_select_click(event.x, event.y, add=True)
            else:
                self.handle_select_click(event.x, event.y, add=False)
        elif self.current_tool == "Direct Select":
            self.handle_direct_select_down(event.x, event.y)
        elif self.current_tool == "Add Anchor":
            self.handle_add_anchor_click(event.x, event.y)
        elif self.current_tool in ("Bend Tool A", "Bend Tool B"):
            self.handle_bend_tool_down(event.x, event.y)
        elif self.current_tool == "Bend Tool C":
            self.handle_draw_bending_line_down(event.x, event.y)
        elif self.current_tool == "Brush":
            self.create_brush_segment(event.x, event.y, layer)
        elif self.current_tool in ("Line", "Rectangle", "Ellipse"):
            self.temp_item = None
        elif self.current_tool == "Text":
            self.create_editable_text(event.x, event.y)
        elif self.current_tool == "Sharp Eraser":
            it = self.canvas.find_closest(event.x, event.y)
            if it:
                shape = self.shape_data.get(it[0])
                if shape and shape['type'] in ("line", "brush", "bending_line"):
                    self.round_erase_anchor_points(it[0], event.x, event.y, radius=ERASER_RADIUS * 0.5)
                self.push_history("Sharp Eraser used")
        elif self.current_tool == "Round Eraser":
            it = self.canvas.find_closest(event.x, event.y)
            if it:
                shape = self.shape_data.get(it[0])
                if shape and shape['type'] in ("line", "brush", "bending_line"):
                    self.round_erase_anchor_points(it[0], event.x, event.y, radius=ERASER_RADIUS)
                self.push_history("Round Eraser used")
        elif self.current_tool == "Soft Eraser":
            it = self.canvas.find_closest(event.x, event.y)
            if it:
                shape = self.shape_data.get(it[0])
                if shape:
                    self.soft_erase_shape(it[0])
                self.push_history("Soft Eraser used")
        if self.current_tool == "Select" and not self.canvas.find_closest(event.x, event.y):
            self.select_rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                                outline="gray", dash=(2,2))

    def on_left_drag(self, event):
        if self.current_layer_index is None:
            return
        layer = self.layers[self.current_layer_index]
        if layer.locked or not layer.visible:
            return
        if self.current_tool == "Select":
            if self.select_rect_id:
                self.canvas.coords(self.select_rect_id, self.start_x, self.start_y, event.x, event.y)
            else:
                if len(self.selected_items) == 1:
                    self.move_entire_shape(event.x, event.y)
        elif self.current_tool == "Direct Select" and self.direct_select_dragging_anchor is not None:
            self.handle_direct_select_drag(event.x, event.y)
        elif self.current_tool in ("Bend Tool A", "Bend Tool B") and self.bend_dragging:
            self.handle_bend_tool_drag(event.x, event.y)
        elif self.current_tool == "Bend Tool C":
            self.handle_draw_bending_line_drag(event.x, event.y)
        elif self.current_tool == "Brush":
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            if abs(dx) > 1 or abs(dy) > 1:
                ln = self.canvas.create_line(self.last_x, self.last_y, event.x, event.y,
                                              fill=self.stroke_color, width=self.brush_size,
                                              smooth=True, splinesteps=36)
                layer.add_item(ln, "brush")
                self.shape_data.store(ln, "brush", [self.last_x, self.last_y, event.x, event.y],
                                       None, self.stroke_color, self.brush_size)
                self.selected_items = {ln}
                self.highlight_selection()
                self.last_x, self.last_y = event.x, event.y
        elif self.current_tool == "Line":
            if self.temp_item:
                self.canvas.delete(self.temp_item)
            self.temp_item = self.canvas.create_line(self.start_x, self.start_y, event.x, event.y,
                                                      fill=self.stroke_color, width=self.brush_size,
                                                      smooth=True, splinesteps=36)
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
        if self.current_tool == "Select":
            if self.select_rect_id:
                x1, y1, x2, y2 = self.canvas.coords(self.select_rect_id)
                ids = set(self.canvas.find_enclosed(x1, y1, x2, y2))
                self.selected_items |= ids
                self.canvas.delete(self.select_rect_id)
                self.select_rect_id = None
                self.highlight_selection()
                self.push_history("Multi-selected items")
                return
            if len(self.selected_items) == 1:
                self.push_history("Moved shape")
                return
        elif self.current_tool == "Direct Select" and self.direct_select_dragging_anchor is not None:
            self.direct_select_dragging_anchor = None
            self.direct_select_drag_index = None
            for sid in self.selected_items:
                shape = self.shape_data.get(sid)
                if shape and 'anchors' in shape and len(shape['anchors']) >= 2:
                    self.apply_anchor_interpolation(sid)
            self.push_history("DirectSelect anchor move")
            return
        elif self.current_tool in ("Bend Tool A", "Bend Tool B") and self.bend_dragging:
            self.bend_dragging = False
            self.bend_target = None
            self.bendA_dragging_anchor_idx = None
            self.bendB_dragging_anchor_idx = None
            self.push_history(f"Bent shape with {self.current_tool}")
            return
        elif self.current_tool == "Bend Tool C":
            self.handle_draw_bending_line_up()
            self.push_history("Created bending line")
            return
        if self.temp_item and self.current_tool in ("Line", "Rectangle", "Ellipse"):
            self.finalize_shape_creation()
            self.push_history(f"Created {self.current_tool}")

    # --------------------- DIRECT SELECT METHODS ---------------------------
    def handle_direct_select_down(self, x, y):
        found = None
        if hasattr(self, "direct_select_anchors"):
            for (hid, sid, idx) in self.direct_select_anchors:
                bbox = self.canvas.coords(hid)
                if x >= bbox[0] and x <= bbox[2] and y >= bbox[1] and y <= bbox[3]:
                    found = (sid, idx)
                    break
        if found:
            self.direct_select_dragging_anchor = found
            self.direct_select_drag_index = found[1]
        else:
            it = self.canvas.find_closest(x, y)
            if it:
                sid = it[0]
                shape = self.shape_data.get(sid)
                if shape and "anchors" in shape:
                    self.selected_items = {sid}
                    self.show_direct_select_anchors(sid)
                    self.direct_select_dragging_anchor = None
                    self.direct_select_drag_index = None

    def handle_direct_select_drag(self, x, y):
        if not self.direct_select_dragging_anchor:
            return
        sid, idx = self.direct_select_dragging_anchor
        shape = self.shape_data.get(sid)
        if not shape:
            return
        coords = shape["coords"]
        coords[idx] = x
        coords[idx + 1] = y
        self.canvas.coords(sid, *coords)
        self.shape_data.update_coords(sid, coords)
        self.update_direct_select_anchors(sid)

    # --------------------- UTILITY METHODS -------------------------------
    @staticmethod
    def normalize_rect(c):
        x1, y1, x2, y2 = c
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def pick_stroke_color(self):
        col = colorchooser.askcolor(title="Stroke Color", initialcolor=self.stroke_color)
        if col and col[1]:
            self.stroke_color = col[1]
            self.stroke_btn.config(bg=self.stroke_color)

    def pick_fill_color(self):
        col = colorchooser.askcolor(title="Fill Color", initialcolor=self.fill_color)
        if col and col[1]:
            self.fill_color = col[1]
            self.fill_btn.config(bg=self.fill_color)

    def on_brush_size_change(self, event=None):
        self.brush_size = int(float(self.brush_size_slider.get()))

    def on_font_size_change(self):
        try:
            self.font_size = int(self.font_size_spin.get())
        except Exception:
            pass

    # --------------------- OPEN / SAVE METHODS ----------------------------
    def save_canvas_snapshot(self):
        fp = filedialog.asksaveasfilename(
            title="Save",
            defaultextension=".png",
            filetypes=(("PNG Files", "*.png"), ("All Files", "*.*"))
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
            messagebox.showerror("Error", "pyscreenshot not installed. Cannot save snapshot.")
        except Exception as e:
            messagebox.showerror("Error", f"Error saving snapshot: {e}")

    # --------------------- DRAW BENDING LINE (Tool C) METHODS ----------------
    def handle_draw_bending_line_down(self, x, y):
        self.temp_item = self.canvas.create_line(x, y, x, y,
                                                  fill=self.stroke_color,
                                                  width=self.brush_size,
                                                  smooth=True, splinesteps=36)
        if self.current_layer_index is None:
            return
        self.layers[self.current_layer_index].add_item(self.temp_item, "bending_line")
        self.shape_data.store(self.temp_item, "bending_line", [x, y],
                              None, self.stroke_color, self.brush_size)
        self.shape_data.shapes[self.temp_item]['anchors'].append(0)
        self.last_x, self.last_y = x, y

    def handle_draw_bending_line_drag(self, x, y):
        if self.temp_item is None:
            return
        coords = self.canvas.coords(self.temp_item)
        coords.extend([x, y])
        self.canvas.coords(self.temp_item, *coords)
        self.shape_data.update_coords(self.temp_item, coords)
        anchor_indices = self.shape_data.shapes[self.temp_item]['anchors']
        if (len(coords) - 2) not in anchor_indices:
            anchor_indices.append(len(coords) - 2)
            anchor_indices.sort()
        self.last_x, self.last_y = x, y

    def handle_draw_bending_line_up(self):
        if self.temp_item is None:
            return
        self.push_history("Drew bending line")
        self.temp_item = None

    # --------------------- SHAPE CREATION METHODS --------------------------
    def create_brush_segment(self, x, y, layer):
        ln = self.canvas.create_line(x, y, x + 1, y + 1,
                                     fill=self.stroke_color,
                                     width=self.brush_size,
                                     smooth=True, splinesteps=36)
        layer.add_item(ln, "brush")
        self.shape_data.store(ln, "brush", [x, y, x + 1, y + 1],
                              None, self.stroke_color, self.brush_size)
        self.selected_items = {ln}
        self.highlight_selection()

    def finalize_shape_creation(self):
        layer = self.layers[self.current_layer_index]
        stype = self.current_tool.lower()
        layer.add_item(self.temp_item, stype)
        coords = self.canvas.coords(self.temp_item)
        fill_val = None if stype == "line" else self.fill_color
        self.shape_data.store(self.temp_item, stype, coords, fill_val, self.stroke_color, self.brush_size)
        self.selected_items = {self.temp_item}
        self.highlight_selection()
        self.temp_item = None

    # --------------------- ERASER METHODS ----------------------------------
    def round_erase_anchor_points(self, item_id, ex, ey, radius=ERASER_RADIUS):
        shape = self.shape_data.get(item_id)
        if not shape:
            return
        if shape['type'] not in ("line", "brush", "bending_line"):
            return
        coords = shape['coords']
        new_coords = []
        for i in range(0, len(coords), 2):
            if math.hypot(coords[i] - ex, coords[i + 1] - ey) >= radius:
                new_coords.extend([coords[i], coords[i + 1]])
        if len(new_coords) < 4:
            self.erase_item(item_id)
            return
        self.canvas.coords(item_id, *new_coords)
        self.shape_data.update_coords(item_id, new_coords)

    def soft_erase_shape(self, item_id):
        shape = self.shape_data.get(item_id)
        if not shape:
            return
        def fade_color(hc):
            if not hc or len(hc) != 7:
                return hc
            r = int(hc[1:3], 16)
            g = int(hc[3:5], 16)
            b = int(hc[5:7], 16)
            target = 255
            def fch(c):
                diff = target - c
                if abs(diff) < SOFT_ERASER_FADE_STEP:
                    return target
                return c + SOFT_ERASER_FADE_STEP if diff > 0 else c - SOFT_ERASER_FADE_STEP
            return f"#{fch(r):02x}{fch(g):02x}{fch(b):02x}"
        new_outline = fade_color(shape['outline'])
        new_fill = fade_color(shape['fill'])
        shape['outline'] = new_outline
        shape['fill'] = new_fill
        if new_outline:
            self.canvas.itemconfig(item_id, outline=new_outline)
        if new_fill:
            self.canvas.itemconfig(item_id, fill=new_fill)

    def erase_item(self, item_id):
        layer = self.find_layer_of_item(item_id)
        if layer:
            layer.remove_item(item_id)
        self.shape_data.remove(item_id)
        self.canvas.delete(item_id)
        if item_id in self.selected_items:
            self.selected_items.remove(item_id)

    # --------------------- UTILITY METHODS ---------------------------------
    def find_layer_of_item(self, item_id):
        for layer in self.layers:
            for (iid, _) in layer.items:
                if iid == item_id:
                    return layer
        return None

    def highlight_selection(self):
        for item in self.canvas.find_all():
            try:
                base_width = self.shape_data.get(item)['width']
                self.canvas.itemconfig(item, width=base_width)
            except Exception:
                pass
        for sid in self.selected_items:
            try:
                base_width = self.shape_data.get(sid)['width']
                self.canvas.itemconfig(sid, width=max(base_width + 2, 3))
            except Exception:
                pass

    def handle_select_click(self, x, y, add=False):
        it = self.canvas.find_closest(x, y)
        if it:
            iid = it[0]
            layer = self.find_layer_of_item(iid)
            if layer and not layer.locked:
                if add:
                    self.selected_items.add(iid)
                else:
                    self.selected_items = {iid}
                self.highlight_selection()
            else:
                self.selected_items.clear()
                self.highlight_selection()
        else:
            self.selected_items.clear()
            self.highlight_selection()

    def move_entire_shape(self, x, y):
        dx = x - self.last_x
        dy = y - self.last_y
        for item in self.selected_items.copy():
            try:
                self.canvas.move(item, dx, dy)
                shape = self.shape_data.get(item)
                if shape:
                    new_coords = [coord + dx if i % 2 == 0 else coord + dy for i, coord in enumerate(shape['coords'])]
                    self.canvas.coords(item, *new_coords)
                    self.shape_data.update_coords(item, new_coords)
            except Exception as e:
                print(f"Error moving item {item}: {e}")
        self.last_x, self.last_y = x, y

    # --------------------- DIRECT SELECT ANCHOR METHODS ---------------------
    def clear_direct_select_anchors(self):
        for (hid, _, _) in getattr(self, "direct_select_anchors", []):
            self.canvas.delete(hid)
        self.direct_select_anchors = []

    def show_direct_select_anchors(self, item_id):
        self.clear_direct_select_anchors()
        shape = self.shape_data.get(item_id)
        if not shape:
            return
        coords = shape['coords']
        anchors = shape.get('anchors', [])
        self.direct_select_anchors = []
        for i in range(0, len(coords), 2):
            x = coords[i]
            y = coords[i+1]
            color = "red" if i in anchors else "blue"
            hid = self.canvas.create_rectangle(x - 3, y - 3, x + 3, y + 3, fill=color, outline=color)
            self.direct_select_anchors.append((hid, item_id, i))

    def update_direct_select_anchors(self, item_id):
        shape = self.shape_data.get(item_id)
        if not shape:
            return
        coords = shape['coords']
        anchors = shape.get('anchors', [])
        for (hid, sid, idx) in self.direct_select_anchors:
            if sid == item_id:
                x = coords[idx]
                y = coords[idx + 1]
                color = "red" if idx in anchors else "blue"
                self.canvas.coords(hid, x - 3, y - 3, x + 3, y + 3)
                self.canvas.itemconfig(hid, fill=color, outline=color)

    def find_direct_anchor(self, x, y):
        rad = 5
        for (hid, sid, idx) in self.direct_select_anchors:
            hx1, hy1, hx2, hy2 = self.canvas.coords(hid)
            if (hx1 - rad < x < hx2 + rad) and (hy1 - rad < y < hy2 + rad):
                return (sid, idx)
        return None

    def on_key_toggle_anchor(self, event):
        if self.current_tool == "Direct Select" and self.selected_items:
            for sid in self.selected_items:
                shape = self.shape_data.get(sid)
                if not shape:
                    continue
                anchors = shape.get('anchors', [])
                if self.direct_select_drag_index is not None:
                    idx = self.direct_select_drag_index
                    if idx in anchors:
                        anchors.remove(idx)
                    else:
                        anchors.append(idx)
                    shape['anchors'] = sorted(anchors)
                    self.update_direct_select_anchors(sid)
            self.push_history("Toggled anchor status")

    def apply_anchor_interpolation(self, shape_id):
        shape = self.shape_data.get(shape_id)
        if not shape or 'anchors' not in shape:
            return
        anchors = sorted(shape['anchors'])
        if len(anchors) < 2:
            return
        coords = shape['coords']
        for a in range(len(anchors) - 1):
            start_idx = anchors[a]
            end_idx = anchors[a + 1]
            x1, y1 = coords[start_idx], coords[start_idx + 1]
            x2, y2 = coords[end_idx], coords[end_idx + 1]
            num_points = (end_idx - start_idx) // 2 - 1
            if num_points <= 0:
                continue
            for i in range(1, num_points + 1):
                t = i / (num_points + 1)
                xi = (1 - t) * x1 + t * x2
                yi = (1 - t) * y1 + t * y2
                idx = start_idx + 2 * i
                coords[idx] = xi
                coords[idx + 1] = yi
        self.canvas.coords(shape_id, *coords)
        self.shape_data.update_coords(shape_id, coords)
        self.update_direct_select_anchors(shape_id)

    # --------------------- ADD ANCHOR METHOD -------------------------------
    def handle_add_anchor_click(self, mx, my):
        it = self.canvas.find_closest(mx, my)
        if not it:
            return
        iid = it[0]
        shape = self.shape_data.get(iid)
        if not shape or shape['type'] not in ("line", "brush", "bending_line"):
            return
        coords = shape['coords']
        seg_i = self.find_closest_segment_index(mx, my, coords)
        if seg_i is None:
            return
        x1, y1 = coords[seg_i], coords[seg_i + 1]
        x2, y2 = coords[seg_i + 2], coords[seg_i + 3]
        seg_len_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
        if seg_len_sq < 1e-10:
            insert_x, insert_y = x1, y1
            insert_idx = seg_i + 2
        else:
            t = ((mx - x1) * (x2 - x1) + (my - y1) * (y2 - y1)) / seg_len_sq
            t = max(0.0, min(1.0, t))
            insert_x = x1 + t * (x2 - x1)
            insert_y = y1 + t * (y2 - y1)
            insert_idx = seg_i + 2
        coords.insert(insert_idx, insert_y)
        coords.insert(insert_idx, insert_x)
        shape['anchors'].append(insert_idx)
        shape['anchors'] = sorted(shape['anchors'])
        self.canvas.coords(iid, *coords)
        self.shape_data.update_coords(iid, coords)
        self.selected_items = {iid}
        self.show_direct_select_anchors(iid)
        self.push_history("Added anchor")

    # --------------------- GROUPING METHODS -------------------------------
    def group_selected_items(self, event=None):
        if len(self.selected_items) < 2:
            return
        group_id = self.canvas.create_rectangle(0, 0, 0, 0, outline="purple", dash=(4, 2))
        children = list(self.selected_items)
        boxes = []
        for cid in children:
            bb = self.canvas.bbox(cid)
            if bb:
                boxes.append(bb)
        if boxes:
            x1 = min(bb[0] for bb in boxes)
            y1 = min(bb[1] for bb in boxes)
            x2 = max(bb[2] for bb in boxes)
            y2 = max(bb[3] for bb in boxes)
            self.canvas.coords(group_id, x1, y1, x2, y2)
        else:
            self.canvas.coords(group_id, 0, 0, 0, 0)
        self.shape_data.store(group_id, "group", self.canvas.coords(group_id), None, "purple", 1)
        self.shape_data.shapes[group_id]['children'] = children
        for cid in children:
            self.canvas.itemconfigure(cid, state="hidden")
            for layer in self.layers:
                layer.items = [(iid, st) for (iid, st) in layer.items if iid != cid]
        if self.current_layer_index is not None:
            self.layers[self.current_layer_index].add_item(group_id, "group")
        self.selected_items = {group_id}
        self.highlight_selection()
        self.push_history("Grouped items")

    # --------------------- AUTO-CONNECT LINES -----------------------------
    def auto_connect_lines(self):
        ids = list(self.shape_data.shapes.keys())
        merged = False
        for i in range(len(ids)):
            id1 = ids[i]
            shape1 = self.shape_data.get(id1)
            if not shape1 or shape1['type'] not in ("line", "brush", "bending_line"):
                continue
            coords1 = shape1['coords']
            endpoints1 = [(coords1[0], coords1[1]), (coords1[-2], coords1[-1])]
            for j in range(i + 1, len(ids)):
                id2 = ids[j]
                shape2 = self.shape_data.get(id2)
                if not shape2 or shape2['type'] not in ("line", "brush", "bending_line"):
                    continue
                coords2 = shape2['coords']
                endpoints2 = [(coords2[0], coords2[1]), (coords2[-2], coords2[-1])]
                for (p1, idx1) in zip(endpoints1, (0, len(coords1)-2)):
                    for (p2, idx2) in zip(endpoints2, (0, len(coords2)-2)):
                        if math.hypot(p1[0]-p2[0], p1[1]-p2[1]) < CONNECT_THRESHOLD:
                            if idx1 == len(coords1)-2 and idx2 == 0:
                                new_coords = coords1 + coords2[2:]
                            elif idx1 == 0 and idx2 == len(coords2)-2:
                                new_coords = coords2 + coords1[2:]
                            elif idx1 == len(coords1)-2 and idx2 == len(coords2)-2:
                                new_coords = coords1 + list(reversed(coords2[:-1]))
                            elif idx1 == 0 and idx2 == 0:
                                new_coords = list(reversed(coords2)) + coords1[2:]
                            else:
                                new_coords = coords1 + coords2
                            self.canvas.coords(id1, *new_coords)
                            self.shape_data.update_coords(id1, new_coords)
                            self.erase_item(id2)
                            merged = True
                            break
                    if merged:
                        break
                if merged:
                    break
            if merged:
                break
        if merged:
            self.auto_connect_lines()

    # --------------------- BEND TOOL METHODS -----------------------------
    def handle_bend_tool_down(self, x, y):
        item = self.canvas.find_closest(x, y)
        if not item:
            self.selected_items.clear()
            return
        iid = item[0]
        shape = self.shape_data.get(iid)
        if not shape or shape['type'] not in ("line", "brush", "bending_line"):
            self.selected_items.clear()
            return
        self.selected_items = {iid}
        self.bend_dragging = True
        self.bend_target = iid
        coords = shape['coords']
        if len(coords) < 4:
            midx = (coords[0] + coords[-2]) / 2
            midy = (coords[1] + coords[-1]) / 2
            coords.insert(2, midx)
            coords.insert(3, midy)
            self.canvas.coords(iid, *coords)
            self.shape_data.update_coords(iid, coords)
        if self.bendA_active:
            aidx = self.find_nearby_anchor(iid, x, y, radius=6)
            if aidx is not None:
                self.bendA_dragging_anchor_idx = aidx
            else:
                self.bendA_segment_idx = self.find_closest_segment_index(x, y, coords)
        if self.bendB_active:
            aidx = self.find_nearby_anchor(iid, x, y, radius=6)
            if aidx is not None:
                self.bendB_dragging_anchor_idx = aidx
        self.last_x, self.last_y = x, y

    def handle_bend_tool_drag(self, x, y):
        if not self.bend_dragging or not self.bend_target:
            return
        shape = self.shape_data.get(self.bend_target)
        if not shape:
            return
        coords = shape['coords']
        if self.bendA_active:
            if self.bendA_dragging_anchor_idx is not None:
                self.bend_tool_a_anchor_drag(shape, x, y)
            else:
                self.bend_tool_a_push(coords, x, y)
        elif self.bendB_active:
            if self.bendB_dragging_anchor_idx is not None:
                self.bend_tool_b_anchor_drag(shape, x, y)
            else:
                self.bend_tool_b_push(coords, x, y)
        self.canvas.coords(self.bend_target, *coords)
        self.shape_data.update_coords(self.bend_target, coords)
        self.last_x, self.last_y = x, y

    def bend_tool_a_anchor_drag(self, shape, mx, my):
        coords = shape['coords']
        anchors = shape.get('anchors', [])
        idx = self.bendA_dragging_anchor_idx
        coords[idx] = mx
        coords[idx + 1] = my
        sorted_anchors = sorted(anchors)
        cur_pos = sorted_anchors.index(idx)
        prev_anchor = sorted_anchors[cur_pos - 1] if cur_pos > 0 else None
        next_anchor = sorted_anchors[cur_pos + 1] if cur_pos < len(sorted_anchors) - 1 else None
        if prev_anchor is not None:
            self.local_anchor_interpolation(coords, prev_anchor, idx)
        if next_anchor is not None:
            self.local_anchor_interpolation(coords, idx, next_anchor)

    def bend_tool_a_push(self, coords, mx, my):
        dx = mx - self.last_x
        dy = my - self.last_y
        radius = BEND_RADIUS_A
        for i in range(0, len(coords), 2):
            px, py = coords[i], coords[i + 1]
            dist = math.hypot(px - self.last_x, py - self.last_y)
            if dist < radius:
                f = 1.0 - (dist / radius)
                coords[i] += dx * f
                coords[i + 1] += dy * f

    def bend_tool_b_anchor_drag(self, shape, mx, my):
        coords = shape['coords']
        anchors = shape.get('anchors', [])
        idx = self.bendB_dragging_anchor_idx
        coords[idx] = mx
        coords[idx + 1] = my
        sorted_anchors = sorted(anchors)
        cur_pos = sorted_anchors.index(idx)
        prev_anchor = sorted_anchors[cur_pos - 1] if cur_pos > 0 else None
        next_anchor = sorted_anchors[cur_pos + 1] if cur_pos < len(sorted_anchors) - 1 else None
        if prev_anchor is not None:
            self.arc_anchor_interpolation(coords, prev_anchor, idx)
        if next_anchor is not None:
            self.arc_anchor_interpolation(coords, idx, next_anchor)

    def bend_tool_b_push(self, coords, mx, my):
        dx = mx - self.last_x
        dy = my - self.last_y
        radius = BEND_RADIUS_B
        for i in range(0, len(coords), 2):
            px, py = coords[i], coords[i + 1]
            dist = math.hypot(px - self.last_x, py - self.last_y)
            if dist < radius:
                f = 1.0 - (dist / radius)
                coords[i] += dx * f
                coords[i + 1] += dy * f

    def arc_anchor_interpolation(self, coords, start_idx, end_idx):
        x1, y1 = coords[start_idx], coords[start_idx + 1]
        x2, y2 = coords[end_idx], coords[end_idx + 1]
        num_points = (end_idx - start_idx) // 2 - 1
        if num_points <= 0:
            return
        for i in range(1, num_points + 1):
            t = i / (num_points + 1)
            xi = (1 - t) * x1 + t * x2
            yi = (1 - t) * y1 + t * y2
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            offset = 10 * math.sin(math.pi * t) if length != 0 else 0
            perp_dx = -dy / length if length != 0 else 0
            perp_dy = dx / length if length != 0 else 0
            new_x = xi + offset * perp_dx
            new_y = yi + offset * perp_dy
            idx = start_idx + 2 * i
            coords[idx] = new_x
            coords[idx + 1] = new_y

    def local_anchor_interpolation(self, coords, start_idx, end_idx):
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx
        x1, y1 = coords[start_idx], coords[start_idx + 1]
        x2, y2 = coords[end_idx], coords[end_idx + 1]
        num_points = (end_idx - start_idx) // 2 - 1
        if num_points <= 0:
            return
        for i in range(1, num_points + 1):
            t = i / (num_points + 1)
            xi = (1 - t) * x1 + t * x2
            yi = (1 - t) * y1 + t * y2
            idx = start_idx + 2 * i
            coords[idx] = xi
            coords[idx + 1] = yi

    def find_nearby_anchor(self, item_id, mx, my, radius=6):
        shape = self.shape_data.get(item_id)
        if not shape or 'anchors' not in shape:
            return None
        coords = shape['coords']
        for aidx in shape['anchors']:
            ax = coords[aidx]
            ay = coords[aidx + 1]
            if abs(mx - ax) < radius and abs(my - ay) < radius:
                return aidx
        return None

    def find_closest_segment_index(self, mx, my, coords):
        best_i = None
        best_dist = float("inf")
        for i in range(0, len(coords) - 2, 2):
            d = self.point_segment_dist(mx, my, coords[i], coords[i + 1],
                                        coords[i + 2], coords[i + 3])
            if d < best_dist:
                best_dist = d
                best_i = i
        return best_i

    def point_segment_dist(self, px, py, x1, y1, x2, y2):
        seg_len_sq = (x2 - x1)**2 + (y2 - y1)**2
        if seg_len_sq == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / seg_len_sq
        if t < 0:
            return math.hypot(px - x1, py - y1)
        if t > 1:
            return math.hypot(px - x2, py - y2)
        projx = x1 + t * (x2 - x1)
        projy = y1 + t * (y2 - y1)
        return math.hypot(px - projx, py - projy)

if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleImageEditor(root)
    root.mainloop()
