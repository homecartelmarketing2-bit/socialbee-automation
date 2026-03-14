import os
import threading
import queue
import requests
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
from io import BytesIO
from tkcalendar import DateEntry
from datetime import date

from src.config import APP_SOURCES, APP_FIELD_OPTIONS, VIDEO_EXTENSIONS
from src.airtable_client import fetch_all_records_for_base
from src.caption import generate_short_caption, get_item_names, compose_caption
from src.socialbee_poster import post_to_socialbee


class ImageBrowser(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SocialBee Interactive Poster")
        self.state("zoomed")  # Maximize window to fit any screen
        self.configure(bg="#1e1e2e")
        self.images = []
        self.current_index = 0
        self.photo_cache = {}
        self.posting = False
        self.result_queue = queue.Queue()

        # Style for ttk widgets (dark theme)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
            fieldbackground="#313244",
            background="#3b3b52",
            foreground="#cdd6f4",
            selectbackground="#89b4fa",
            selectforeground="#1e1e2e",
            arrowcolor="#cdd6f4",
        )
        style.map("Dark.TCombobox",
            fieldbackground=[("readonly", "#313244")],
            foreground=[("readonly", "#cdd6f4")],
        )
        style.configure("Dark.Horizontal.TProgressbar",
            troughcolor="#313244",
            background="#89b4fa",
            thickness=6,
        )

        self._build_ui()
        self.status_label.config(text="Select a source to begin.")

    def _build_ui(self):
        # Main horizontal container
        main_frame = tk.Frame(self, bg="#1e1e2e")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ── LEFT PANEL (Image) ──
        left_frame = tk.Frame(main_frame, bg="#1e1e2e")
        left_frame.pack(side="left", fill="both", expand=True)

        # Source selector dropdown
        self.source_frame = tk.Frame(left_frame, bg="#1e1e2e")
        self.source_frame.pack(fill="x", padx=10, pady=(5, 0))

        tk.Label(
            self.source_frame, text="Source:", font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4", bg="#1e1e2e"
        ).pack(side="left")

        self.source_ids = list(APP_SOURCES.keys())
        self.source_names = list(APP_SOURCES.values())
        self.source_combo = ttk.Combobox(
            self.source_frame, values=self.source_names, state="readonly",
            font=("Segoe UI", 10), width=35, style="Dark.TCombobox"
        )
        self.source_combo.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self.source_combo.bind("<<ComboboxSelected>>", self._on_source_change)

        # Field selector dropdown (hidden by default, shown for sources with field options)
        self.field_frame = tk.Frame(left_frame, bg="#1e1e2e")
        self.field_frame.pack(fill="x", padx=10, pady=(5, 0))
        self.field_frame.pack_forget()  # hidden initially

        tk.Label(
            self.field_frame, text="Field:", font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4", bg="#1e1e2e"
        ).pack(side="left")

        self.field_combo = ttk.Combobox(
            self.field_frame, values=[], state="readonly",
            font=("Segoe UI", 10), width=35, style="Dark.TCombobox"
        )
        self.field_combo.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self.field_combo.bind("<<ComboboxSelected>>", self._on_field_change)

        # Progress bar (hidden by default)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            left_frame, variable=self.progress_var,
            maximum=100, mode="determinate",
            style="Dark.Horizontal.TProgressbar",
        )

        # Top bar
        top_frame = tk.Frame(left_frame, bg="#1e1e2e")
        top_frame.pack(fill="x", padx=10, pady=(5, 5))

        self.counter_label = tk.Label(
            top_frame, text="", font=("Segoe UI", 12),
            fg="#cdd6f4", bg="#1e1e2e"
        )
        self.counter_label.pack(side="left")

        self.filename_label = tk.Label(
            top_frame, text="", font=("Segoe UI", 10),
            fg="#a6adc8", bg="#1e1e2e"
        )
        self.filename_label.pack(side="right")

        # Image canvas
        self.canvas = tk.Canvas(left_frame, bg="#313244", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)

        # Navigation buttons
        nav_frame = tk.Frame(left_frame, bg="#1e1e2e")
        nav_frame.pack(fill="x", padx=10, pady=(5, 5))

        btn_style = {
            "font": ("Segoe UI", 11, "bold"),
            "fg": "#1e1e2e",
            "bg": "#89b4fa",
            "activebackground": "#74c7ec",
            "activeforeground": "#1e1e2e",
            "relief": "flat",
            "cursor": "hand2",
            "padx": 20,
            "pady": 8,
        }

        self.prev_btn = tk.Button(
            nav_frame, text="◀  Prev", command=self.prev_image, **btn_style
        )
        self.prev_btn.pack(side="left")

        self.status_label = tk.Label(
            nav_frame, text="Loading...", font=("Segoe UI", 10),
            fg="#a6adc8", bg="#1e1e2e"
        )
        self.status_label.pack(side="left", expand=True)

        self.next_btn = tk.Button(
            nav_frame, text="Next  ▶", command=self.next_image, **btn_style
        )
        self.next_btn.pack(side="right")

        # ── RIGHT PANEL (Caption & Posting Controls) ──
        right_frame = tk.Frame(main_frame, bg="#2a2a3e", width=380)
        right_frame.pack(side="right", fill="y", padx=(5, 0))
        right_frame.pack_propagate(False)

        pad = 10

        # --- Bottom fixed area (PACK FIRST so it claims space at bottom) ---
        bottom_fixed = tk.Frame(right_frame, bg="#2a2a3e")
        bottom_fixed.pack(fill="x", side="bottom", padx=pad, pady=(5, pad))

        self.post_btn = tk.Button(
            bottom_fixed, text="Post to SocialBee", font=("Segoe UI", 11, "bold"),
            fg="#1e1e2e", bg="#f9e2af", activebackground="#f2cdcd",
            relief="flat", cursor="hand2", padx=15, pady=8,
            command=self._on_post
        )
        self.post_btn.pack(fill="x", pady=(0, 3))

        self.post_status_var = tk.StringVar(value="")
        self.post_status_label = tk.Label(
            bottom_fixed, textvariable=self.post_status_var, font=("Segoe UI", 8),
            fg="#f38ba8", bg="#2a2a3e", wraplength=340
        )
        self.post_status_label.pack(fill="x")

        # --- Scrollable area (fills remaining space above bottom) ---
        scroll_container = tk.Frame(right_frame, bg="#2a2a3e")
        scroll_container.pack(fill="both", expand=True, side="top")

        right_canvas = tk.Canvas(scroll_container, bg="#2a2a3e", highlightthickness=0)
        right_scrollbar = tk.Scrollbar(scroll_container, orient="vertical", command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scrollbar.set)

        right_scrollbar.pack(side="right", fill="y")
        right_canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(right_canvas, bg="#2a2a3e")
        inner_window = right_canvas.create_window((0, 0), window=inner, anchor="nw")

        # Make inner frame fill canvas width & update scroll region
        def _configure_inner(event):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        inner.bind("<Configure>", _configure_inner)

        def _configure_canvas(event):
            right_canvas.itemconfig(inner_window, width=event.width)
        right_canvas.bind("<Configure>", _configure_canvas)

        # Mouse wheel — only scroll when mouse is over the right panel
        def _on_enter(event):
            right_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _on_leave(event):
            right_canvas.unbind_all("<MouseWheel>")
        def _on_mousewheel(event):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        right_canvas.bind("<Enter>", _on_enter)
        right_canvas.bind("<Leave>", _on_leave)

        # Section: Item Names
        tk.Label(
            inner, text="Item Names", font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4", bg="#2a2a3e", anchor="w"
        ).pack(fill="x", padx=pad, pady=(pad, 2))

        self.item_names_var = tk.StringVar(value="(navigate to a photo)")
        self.item_names_label = tk.Label(
            inner, textvariable=self.item_names_var, font=("Segoe UI", 9),
            fg="#a6e3a1", bg="#2a2a3e", anchor="w", justify="left", wraplength=340
        )
        self.item_names_label.pack(fill="x", padx=pad, pady=(0, 5))

        # Generate Caption button
        self.gen_caption_btn = tk.Button(
            inner, text="Generate Caption", font=("Segoe UI", 10, "bold"),
            fg="#1e1e2e", bg="#a6e3a1", activebackground="#94e2d5",
            relief="flat", cursor="hand2", padx=10, pady=5,
            command=self._on_generate_caption
        )
        self.gen_caption_btn.pack(fill="x", padx=pad, pady=(0, 5))

        # Caption text area
        tk.Label(
            inner, text="Caption Preview", font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4", bg="#2a2a3e", anchor="w"
        ).pack(fill="x", padx=pad, pady=(0, 2))

        caption_frame = tk.Frame(inner, bg="#313244")
        caption_frame.pack(fill="x", padx=pad, pady=(0, 5))

        self.caption_text = tk.Text(
            caption_frame, font=("Segoe UI", 8), fg="#cdd6f4", bg="#313244",
            insertbackground="#cdd6f4", wrap="word", relief="flat",
            padx=6, pady=6, height=12
        )
        caption_scroll = tk.Scrollbar(caption_frame, command=self.caption_text.yview)
        self.caption_text.configure(yscrollcommand=caption_scroll.set)
        caption_scroll.pack(side="right", fill="y")
        self.caption_text.pack(side="left", fill="both", expand=True)

        # Category
        cat_frame = tk.Frame(inner, bg="#2a2a3e")
        cat_frame.pack(fill="x", padx=pad, pady=(0, 5))

        tk.Label(
            cat_frame, text="Category:", font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4", bg="#2a2a3e"
        ).pack(side="left")

        self.category_var = tk.StringVar(value="Moodboard")
        self.category_entry = tk.Entry(
            cat_frame, textvariable=self.category_var, font=("Segoe UI", 9),
            fg="#cdd6f4", bg="#313244", insertbackground="#cdd6f4",
            relief="flat", width=18
        )
        self.category_entry.pack(side="left", padx=(8, 0))

        # Schedule section
        sched_frame = tk.Frame(inner, bg="#2a2a3e")
        sched_frame.pack(fill="x", padx=pad, pady=(0, 5))

        tk.Label(
            sched_frame, text="Schedule:", font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4", bg="#2a2a3e"
        ).pack(anchor="w")

        # Post now checkbox
        self.post_now_var = tk.BooleanVar(value=True)
        self.post_now_check = tk.Checkbutton(
            sched_frame, text="Post now", variable=self.post_now_var,
            font=("Segoe UI", 9), fg="#cdd6f4", bg="#2a2a3e",
            selectcolor="#313244", activebackground="#2a2a3e",
            activeforeground="#cdd6f4", command=self._toggle_schedule
        )
        self.post_now_check.pack(anchor="w", pady=(2, 5))

        # Schedule controls (hidden by default)
        self.sched_controls = tk.Frame(sched_frame, bg="#2a2a3e")

        # Date row
        date_row = tk.Frame(self.sched_controls, bg="#2a2a3e")
        date_row.pack(fill="x", pady=(0, 5))

        tk.Label(
            date_row, text="Date:", font=("Segoe UI", 8),
            fg="#a6adc8", bg="#2a2a3e"
        ).pack(side="left")

        self.date_entry = DateEntry(
            date_row, font=("Segoe UI", 9), width=12,
            background="#313244", foreground="#cdd6f4",
            headersbackground="#2a2a3e", headersforeground="#cdd6f4",
            selectbackground="#89b4fa", selectforeground="#1e1e2e",
            normalbackground="#313244", normalforeground="#cdd6f4",
            weekendbackground="#3b3b52", weekendforeground="#cdd6f4",
            othermonthforeground="#585b70", othermonthwebackground="#3b3b52",
            borderwidth=0, date_pattern="yyyy-mm-dd",
            mindate=date.today(),
        )
        self.date_entry.pack(side="left", padx=(5, 0))

        # Time row
        time_row = tk.Frame(self.sched_controls, bg="#2a2a3e")
        time_row.pack(fill="x", pady=(0, 3))

        tk.Label(
            time_row, text="Time:", font=("Segoe UI", 8),
            fg="#a6adc8", bg="#2a2a3e"
        ).pack(side="left")

        self.hour_var = tk.StringVar(value="10")
        hour_spin = tk.Spinbox(
            time_row, from_=0, to=23, width=3, wrap=True,
            textvariable=self.hour_var, font=("Segoe UI", 9),
            fg="#cdd6f4", bg="#313244", buttonbackground="#3b3b52",
            relief="flat", format="%02.0f"
        )
        hour_spin.pack(side="left", padx=(5, 0))

        tk.Label(
            time_row, text=":", font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4", bg="#2a2a3e"
        ).pack(side="left")

        self.minute_var = tk.StringVar(value="00")
        minute_spin = tk.Spinbox(
            time_row, from_=0, to=59, width=3, wrap=True,
            textvariable=self.minute_var, font=("Segoe UI", 9),
            fg="#cdd6f4", bg="#313244", buttonbackground="#3b3b52",
            relief="flat", format="%02.0f", increment=5
        )
        minute_spin.pack(side="left")

        tk.Label(
            time_row, text="(24hr)", font=("Segoe UI", 7),
            fg="#585b70", bg="#2a2a3e"
        ).pack(side="left", padx=(5, 0))

        # Keyboard bindings
        self.bind("<Left>", lambda e: self.prev_image())
        self.bind("<Right>", lambda e: self.next_image())
        self.bind("<Escape>", lambda e: self.destroy())

    def _toggle_schedule(self):
        """Show/hide schedule controls based on 'Post now' checkbox."""
        if self.post_now_var.get():
            self.sched_controls.pack_forget()
        else:
            self.sched_controls.pack(fill="x")

    # ── Source loading ──

    def _on_source_change(self, event=None):
        """Load images when user selects a source from dropdown."""
        idx = self.source_combo.current()
        if idx < 0:
            return
        base_id = self.source_ids[idx]
        source_name = self.source_names[idx]

        # Reset state
        self.images = []
        self.photo_cache = {}
        self.current_index = 0
        self.canvas.delete("all")
        self.counter_label.config(text="")
        self.filename_label.config(text="")
        self.item_names_var.set("")
        self.caption_text.delete("1.0", "end")

        # Check if this source has field options (sub-dropdown)
        if base_id in APP_FIELD_OPTIONS:
            self.field_combo.set("")
            self.field_combo.config(values=APP_FIELD_OPTIONS[base_id])
            self.field_frame.pack_forget()
            self.field_frame.pack(fill="x", padx=10, pady=(5, 0), after=self.source_frame)
            self.status_label.config(text="Select a field type to load images.")
            return
        else:
            self.field_frame.pack_forget()

        self._start_fetch(base_id, source_name)

    def _on_field_change(self, event=None):
        """Load images when user selects a field from the sub-dropdown."""
        field_name = self.field_combo.get()
        # Ignore separator items
        if not field_name or field_name.startswith("──"):
            self.field_combo.set("")
            return

        idx = self.source_combo.current()
        if idx < 0:
            return
        base_id = self.source_ids[idx]
        source_name = self.source_names[idx]

        # Reset state
        self.images = []
        self.photo_cache = {}
        self.current_index = 0
        self.canvas.delete("all")
        self.counter_label.config(text="")
        self.filename_label.config(text="")
        self.item_names_var.set("")
        self.caption_text.delete("1.0", "end")

        self._start_fetch(base_id, f"{source_name} → {field_name}", field_name=field_name)

    def _start_fetch(self, base_id, source_name, field_name=None):
        """Start fetching images from Airtable in a background thread."""
        self.status_label.config(text=f"Loading {source_name}...")
        self.source_combo.config(state="disabled")
        self.field_combo.config(state="disabled")
        self.progress_var.set(0)
        self.progress_bar.pack(fill="x", padx=10, pady=(3, 0))
        self.update_idletasks()

        def _progress(table_num, total_tables, images_so_far):
            pct = (table_num / total_tables) * 100 if total_tables else 0
            self.after(0, lambda t=table_num, tt=total_tables, img=images_so_far, p=pct:
                self._update_progress(t, tt, img, p))

        def _fetch():
            try:
                images = fetch_all_records_for_base(base_id, progress_callback=_progress, field_name=field_name)
                self.after(0, lambda: self._on_images_loaded(images))
            except Exception as e:
                self.after(0, lambda: self._on_fetch_error(str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_progress(self, table_num, total_tables, images_so_far, pct):
        """Update progress bar and status text during fetch."""
        self.progress_var.set(pct)
        self.status_label.config(
            text=f"Fetching table {table_num}/{total_tables}... {images_so_far} images found"
        )

    def _on_images_loaded(self, images):
        """Called when images are fetched from Airtable."""
        self.progress_bar.pack_forget()
        self.source_combo.config(state="readonly")
        self.field_combo.config(state="readonly")
        self.images = images
        self.photo_cache = {}
        self.current_index = 0
        if images:
            self.status_label.config(text=f"Loaded {len(images)} images")
            self.load_image(0)
        else:
            self.status_label.config(text="No images found in this source.")
            self.counter_label.config(text="0 / 0")

    def _on_fetch_error(self, error):
        """Called when fetching fails."""
        self.progress_bar.pack_forget()
        self.source_combo.config(state="readonly")
        self.field_combo.config(state="readonly")
        self.status_label.config(text=f"Error: {error}")

    # ── Image loading ──

    def load_image(self, index):
        if not self.images:
            return

        self.current_index = index
        img_data = self.images[index]
        total = len(self.images)

        self.counter_label.config(text=f"{index + 1} / {total}")
        self.filename_label.config(text=img_data["filename"])
        self.status_label.config(text="Loading image...")
        self.update_idletasks()

        # Update item names on right panel
        item_names = get_item_names(img_data.get("fields", {}))
        self.item_names_var.set(item_names if item_names else "(no item names)")

        # Clear caption area on navigation
        self.caption_text.delete("1.0", "end")

        # Check cache
        if index in self.photo_cache:
            self._display_cached(index)
            return

        # Download
        try:
            ext = os.path.splitext(img_data["filename"])[1].lower()
            is_video = ext in VIDEO_EXTENSIONS

            if is_video:
                pil_img = self._make_video_placeholder(img_data["filename"])
            else:
                resp = requests.get(img_data["url"], timeout=30)
                resp.raise_for_status()
                pil_img = Image.open(BytesIO(resp.content))

            self.update_idletasks()
            cw = self.canvas.winfo_width() or 800
            ch = self.canvas.winfo_height() or 500

            ratio = min(cw / pil_img.width, ch / pil_img.height)
            if ratio < 1:
                new_w = int(pil_img.width * ratio)
                new_h = int(pil_img.height * ratio)
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

            photo = ImageTk.PhotoImage(pil_img)
            self.photo_cache[index] = photo
            self._display_cached(index)

        except Exception as e:
            self.status_label.config(text=f"Error: {e}")

    def _make_video_placeholder(self, filename):
        """Create a placeholder image for video files."""
        w, h = 640, 480
        img = Image.new("RGB", (w, h), (40, 40, 40))
        draw = ImageDraw.Draw(img)
        # Draw play triangle
        cx, cy = w // 2, h // 2 - 20
        size = 50
        draw.polygon(
            [(cx - size, cy - size), (cx - size, cy + size), (cx + size, cy)],
            fill=(255, 255, 255),
        )
        # Draw filename text below
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        draw.text((w // 2, cy + size + 40), filename, fill=(200, 200, 200), font=font, anchor="mt")
        draw.text((w // 2, cy + size + 70), "VIDEO FILE", fill=(150, 150, 150), font=font, anchor="mt")
        return img

    def _display_cached(self, index):
        photo = self.photo_cache[index]
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self.canvas.create_image(cw // 2, ch // 2, image=photo, anchor="center")
        self.status_label.config(text="Ready")

        if index + 1 < len(self.images) and (index + 1) not in self.photo_cache:
            self.after(100, self._preload, index + 1)

    def _preload(self, index):
        if index in self.photo_cache:
            return
        try:
            img_data = self.images[index]
            ext = os.path.splitext(img_data["filename"])[1].lower()
            is_video = ext in VIDEO_EXTENSIONS

            if is_video:
                pil_img = self._make_video_placeholder(img_data["filename"])
            else:
                resp = requests.get(img_data["url"], timeout=30)
                resp.raise_for_status()
                pil_img = Image.open(BytesIO(resp.content))

            cw = self.canvas.winfo_width() or 800
            ch = self.canvas.winfo_height() or 500
            ratio = min(cw / pil_img.width, ch / pil_img.height)
            if ratio < 1:
                new_w = int(pil_img.width * ratio)
                new_h = int(pil_img.height * ratio)
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

            photo = ImageTk.PhotoImage(pil_img)
            self.photo_cache[index] = photo
        except Exception:
            pass

    def next_image(self):
        if self.current_index < len(self.images) - 1:
            self.load_image(self.current_index + 1)

    def prev_image(self):
        if self.current_index > 0:
            self.load_image(self.current_index - 1)

    # ── Caption generation ──

    def _on_generate_caption(self):
        if not self.images:
            return

        img_data = self.images[self.current_index]
        self.gen_caption_btn.config(state="disabled", text="Generating...")
        self.update_idletasks()

        def _generate():
            try:
                ai_line = generate_short_caption(img_data)
                item_names = get_item_names(img_data.get("fields", {}))
                full_caption = compose_caption(ai_line, item_names)
                self.after(0, lambda: self._set_caption(full_caption))
            except Exception as e:
                self.after(0, lambda: self._set_caption(f"Error generating caption: {e}"))
            finally:
                self.after(0, lambda: self.gen_caption_btn.config(state="normal", text="Generate Caption"))

        threading.Thread(target=_generate, daemon=True).start()

    def _set_caption(self, text):
        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", text)

    # ── Posting ──

    def _on_post(self):
        if self.posting:
            return
        if not self.images:
            messagebox.showwarning("No Image", "No image selected.")
            return

        caption = self.caption_text.get("1.0", "end").strip()
        if not caption:
            messagebox.showwarning("No Caption", "Generate or type a caption first.")
            return

        img_data = self.images[self.current_index]
        category = self.category_var.get().strip() or None
        if self.post_now_var.get():
            schedule_date = None
            schedule_time = None
        else:
            schedule_date = self.date_entry.get_date().strftime("%Y-%m-%d")
            hour = self.hour_var.get().zfill(2)
            minute = self.minute_var.get().zfill(2)
            schedule_time = f"{hour}:{minute}"

        # Check if Brave is running — it must be CLOSED for Playwright to work
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq brave.exe"],
                capture_output=True, text=True, timeout=5
            )
            if "brave.exe" in result.stdout.lower():
                messagebox.showwarning(
                    "Close Brave First",
                    "Brave browser is currently open.\n\n"
                    "Please CLOSE Brave completely before posting.\n"
                    "Playwright needs exclusive access to Brave's profile."
                )
                return
        except Exception:
            pass

        self.posting = True
        self.post_btn.config(state="disabled", text="Posting...", bg="#585b70")
        self.post_status_var.set("Downloading image & launching Brave...")

        thread = threading.Thread(
            target=post_to_socialbee,
            args=(caption, img_data["url"], img_data["filename"],
                  category, schedule_date, schedule_time, self.result_queue),
            daemon=True,
        )
        thread.start()
        self._poll_result()

    def _poll_result(self):
        try:
            status, message = self.result_queue.get_nowait()
            self.posting = False
            self.post_btn.config(state="normal", text="Post to SocialBee", bg="#f9e2af")

            if status == "success":
                self.post_status_var.set("Posted successfully!")
                messagebox.showinfo("Success", message)
            else:
                self.post_status_var.set(f"Error: {message}")
                messagebox.showerror("Error", message)
        except queue.Empty:
            self.after(500, self._poll_result)
