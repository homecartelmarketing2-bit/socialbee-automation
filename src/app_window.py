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

from src.config import APP_SOURCES, APP_FIELD_OPTIONS, PAIRED_FIELD_OPTIONS, VIDEO_EXTENSIONS
from src.airtable_client import fetch_all_records_for_base, fetch_paired_records_for_base, clear_cache, mark_record_posted, mark_record_disregarded, update_cache
from src.caption import generate_short_caption, get_item_names, compose_caption
from src.socialbee_poster import post_to_socialbee, post_to_socialbee_multiple, post_to_socialbee_story, setup_automation_profile, setup_chrome_story_profile, setup_chrome_post_profile


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
        self.paired_mode = False
        self.paired_field_name = None  # tracks which paired option is active
        self._current_source = None
        self._current_field = None
        self.result_queue = queue.Queue()

        # Grid view state
        self.view_mode = "single"       # "single" or "grid"
        self.grid_thumbs = {}           # index -> PhotoImage thumbnail
        self.grid_labels = {}           # index -> Label widget
        self._grid_load_cancel = False  # flag to cancel background loading
        self.grid_selected = set()      # multi-select: set of selected indices

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
        self.left_frame = tk.Frame(main_frame, bg="#1e1e2e")
        self.left_frame.pack(side="left", fill="both", expand=True)
        left_frame = self.left_frame

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

        self.refresh_btn = tk.Button(
            self.source_frame, text="Refresh", font=("Segoe UI", 8, "bold"),
            fg="#1e1e2e", bg="#f38ba8", activebackground="#eba0ac",
            relief="flat", cursor="hand2", padx=8, pady=2,
            command=self._on_refresh
        )
        self.refresh_btn.pack(side="left", padx=(6, 0))

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

        self.grid_toggle_btn = tk.Button(
            top_frame, text="Grid View", font=("Segoe UI", 9, "bold"),
            fg="#1e1e2e", bg="#74c7ec", activebackground="#89dceb",
            relief="flat", cursor="hand2", padx=10, pady=2,
            command=self._toggle_view_mode
        )
        self.grid_toggle_btn.pack(side="left", padx=(12, 0))

        self.filename_label = tk.Label(
            top_frame, text="", font=("Segoe UI", 10),
            fg="#a6adc8", bg="#1e1e2e"
        )
        self.filename_label.pack(side="right")

        # Image canvas
        self.canvas = tk.Canvas(left_frame, bg="#313244", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)

        # Grid view container (hidden by default, swaps with canvas)
        self.grid_container = tk.Frame(left_frame, bg="#313244")

        self.grid_canvas = tk.Canvas(self.grid_container, bg="#313244", highlightthickness=0)
        self.grid_scrollbar = tk.Scrollbar(
            self.grid_container, orient="vertical", command=self.grid_canvas.yview
        )
        self.grid_canvas.configure(yscrollcommand=self.grid_scrollbar.set)
        self.grid_scrollbar.pack(side="right", fill="y")
        self.grid_canvas.pack(side="left", fill="both", expand=True)

        self.grid_inner = tk.Frame(self.grid_canvas, bg="#313244")
        self.grid_inner_window = self.grid_canvas.create_window(
            (0, 0), window=self.grid_inner, anchor="nw"
        )

        def _configure_grid_inner(event):
            self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        self.grid_inner.bind("<Configure>", _configure_grid_inner)

        def _configure_grid_canvas(event):
            self.grid_canvas.itemconfig(self.grid_inner_window, width=event.width)
        self.grid_canvas.bind("<Configure>", _configure_grid_canvas)

        # Right-click context menu for grid thumbnails
        self.grid_menu = tk.Menu(self, tearoff=0)
        self._grid_menu_index = None

        # Navigation buttons
        self.nav_frame = tk.Frame(left_frame, bg="#1e1e2e")
        self.nav_frame.pack(fill="x", padx=10, pady=(5, 5))
        nav_frame = self.nav_frame

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

        self.play_btn = tk.Button(
            nav_frame, text="▶  Play Video", font=("Segoe UI", 11, "bold"),
            fg="#1e1e2e", bg="#a6e3a1", activebackground="#94e2d5",
            activeforeground="#1e1e2e", relief="flat", cursor="hand2",
            padx=14, pady=8, command=self._play_video
        )
        # Hidden by default — shown only for video files

        self.play_left_btn = tk.Button(
            nav_frame, text="▶  Before Reels", font=("Segoe UI", 11, "bold"),
            fg="#1e1e2e", bg="#a6e3a1", activebackground="#94e2d5",
            activeforeground="#1e1e2e", relief="flat", cursor="hand2",
            padx=14, pady=8, command=lambda: self._play_paired_video("left")
        )
        self.play_right_btn = tk.Button(
            nav_frame, text="▶  After Reels", font=("Segoe UI", 11, "bold"),
            fg="#1e1e2e", bg="#f9e2af", activebackground="#f5c2e7",
            activeforeground="#1e1e2e", relief="flat", cursor="hand2",
            padx=14, pady=8, command=lambda: self._play_paired_video("right")
        )
        # Hidden by default — shown only for paired video files

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

        self.post_story_btn = tk.Button(
            bottom_fixed, text="Post to SocialBee Story", font=("Segoe UI", 11, "bold"),
            fg="#1e1e2e", bg="#a6e3a1", activebackground="#94e2d5",
            relief="flat", cursor="hand2", padx=15, pady=8,
            command=self._on_post_story
        )
        self.post_story_btn.pack(fill="x", pady=(0, 3))

        self.setup_chrome_post_btn = tk.Button(
            bottom_fixed, text="Setup Login (Chrome - Post)", font=("Segoe UI", 9),
            fg="#cdd6f4", bg="#45475a", activebackground="#585b70",
            relief="flat", cursor="hand2", padx=10, pady=4,
            command=self._on_setup_chrome_post_login
        )
        self.setup_chrome_post_btn.pack(fill="x", pady=(0, 3))

        self.setup_chrome_btn = tk.Button(
            bottom_fixed, text="Setup Login (Chrome - Story)", font=("Segoe UI", 9),
            fg="#cdd6f4", bg="#45475a", activebackground="#585b70",
            relief="flat", cursor="hand2", padx=10, pady=4,
            command=self._on_setup_chrome_login
        )
        self.setup_chrome_btn.pack(fill="x", pady=(0, 3))

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

        if source_name == self._current_source:
            return
        self._current_source = source_name
        self._current_field = None

        # Reset state
        self.images = []
        self.photo_cache = {}
        self.current_index = 0
        self.canvas.delete("all")
        self.counter_label.config(text="")
        self.filename_label.config(text="")
        self.item_names_var.set("")
        self.caption_text.delete("1.0", "end")

        # Reset paired mode and grid when switching sources
        self.paired_mode = False
        self.paired_field_name = None
        self._update_post_button()
        self._grid_load_cancel = True
        if self.view_mode == "grid":
            self._show_single_view()

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

    def _on_refresh(self):
        """Clear cache and reload current source/field."""
        clear_cache()
        self._current_field = None
        self._current_source = None
        # Re-trigger the current selection
        idx = self.source_combo.current()
        if idx < 0:
            self.status_label.config(text="Cache cleared. Select a source.")
            return
        field_name = self.field_combo.get() if self.field_combo.get() else None
        if field_name and not field_name.startswith("──"):
            self._on_field_change()
        else:
            self._on_source_change()

    def _on_field_change(self, event=None):
        """Load images when user selects a field from the sub-dropdown."""
        field_name = self.field_combo.get()
        # Ignore separator items
        if not field_name or field_name.startswith("──"):
            self.field_combo.set("")
            return

        if field_name == self._current_field:
            return
        self._current_field = field_name

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
        self._grid_load_cancel = True
        if self.view_mode == "grid":
            self._show_single_view()

        # Check if this is a paired field option
        if field_name in PAIRED_FIELD_OPTIONS:
            self.paired_mode = True
            self.paired_field_name = field_name
            field1, field2 = PAIRED_FIELD_OPTIONS[field_name]
            self._update_post_button()
            self._start_fetch(base_id, f"{source_name} → {field_name}", paired_fields=(field1, field2))
        else:
            self.paired_mode = False
            self.paired_field_name = None
            self._update_post_button()
            self._start_fetch(base_id, f"{source_name} → {field_name}", field_name=field_name)

    def _start_fetch(self, base_id, source_name, field_name=None, paired_fields=None):
        """Start fetching images from Airtable in a background thread."""
        # Track for cache updates after marking as posted
        self._fetch_base_id = base_id
        if paired_fields:
            self._fetch_cache_key = f"{paired_fields[0]}+{paired_fields[1]}"
        else:
            self._fetch_cache_key = field_name or "Blended Image"
        self.status_label.config(text=f"Loading {source_name}...")
        self.source_combo.config(state="disabled")
        self.field_combo.config(state="disabled")
        self.progress_var.set(0)
        self.progress_bar.pack(fill="x", padx=10, pady=(3, 0))
        self.update_idletasks()

        def _progress(table_num, total_tables, images_so_far):
            pct = (table_num / total_tables) * 100 if total_tables else 0
            label = "pairs" if paired_fields else "images"
            self.after(0, lambda t=table_num, tt=total_tables, img=images_so_far, p=pct, lb=label:
                self._update_progress(t, tt, img, p, lb))

        def _fetch():
            try:
                if paired_fields:
                    field1, field2 = paired_fields
                    images = fetch_paired_records_for_base(base_id, field1, field2, progress_callback=_progress)
                else:
                    images = fetch_all_records_for_base(base_id, progress_callback=_progress, field_name=field_name)
                self.after(0, lambda: self._on_images_loaded(images))
            except Exception as e:
                self.after(0, lambda: self._on_fetch_error(str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_progress(self, table_num, total_tables, images_so_far, pct, label="images"):
        """Update progress bar and status text during fetch."""
        self.progress_var.set(pct)
        self.status_label.config(
            text=f"Fetching table {table_num}/{total_tables}... {images_so_far} {label} found"
        )

    def _on_images_loaded(self, images):
        """Called when images are fetched from Airtable."""
        self.progress_bar.pack_forget()
        self.source_combo.config(state="readonly")
        self.field_combo.config(state="readonly")
        self.images = images
        self.photo_cache = {}
        self.current_index = 0

        # Reset grid state
        self._grid_load_cancel = True
        self.grid_thumbs = {}
        self.grid_labels = {}
        if self.view_mode == "grid":
            self._show_single_view()

        if images:
            label = "pairs" if self.paired_mode else "images"
            self.status_label.config(text=f"Loaded {len(images)} {label}")
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

        # Capture canvas size BEFORE any label changes to prevent layout shift
        self.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 800
        canvas_h = self.canvas.winfo_height() or 500

        self.current_index = index
        img_data = self.images[index]
        total = len(self.images)
        is_pair = img_data.get("type") == "pair"

        posted_mark = " [POSTED]" if img_data.get("fields", {}).get("SB Posted") else ""
        disregard_mark = " [DISREGARD]" if img_data.get("fields", {}).get("Disregard") else ""
        self.counter_label.config(text=f"{index + 1} / {total}{posted_mark}{disregard_mark}")
        if is_pair:
            self.filename_label.config(
                text=f"{img_data['left']['filename']}  |  {img_data['right']['filename']}"
            )
        else:
            self.filename_label.config(text=img_data["filename"])
        self.status_label.config(text="Loading image..." if not is_pair else "Loading paired images...")

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
            if is_pair:
                photo = self._load_paired_image(img_data, canvas_w, canvas_h)
            else:
                photo = self._load_single_image(img_data, canvas_w, canvas_h)

            self.photo_cache[index] = photo
            self._display_cached(index)

        except Exception as e:
            self.status_label.config(text=f"Error: {e}")

    def _load_single_image(self, img_data, cw=None, ch=None):
        """Download and resize a single image, return PhotoImage."""
        ext = os.path.splitext(img_data["filename"])[1].lower()
        is_video = ext in VIDEO_EXTENSIONS

        if is_video:
            pil_img = self._load_video_thumbnail(img_data)
        else:
            resp = requests.get(img_data["url"], timeout=30)
            resp.raise_for_status()
            pil_img = Image.open(BytesIO(resp.content))

        if cw is None or ch is None:
            self.update_idletasks()
            cw = self.canvas.winfo_width() or 800
            ch = self.canvas.winfo_height() or 500

        ratio = min(cw / pil_img.width, ch / pil_img.height)
        if ratio < 1:
            new_w = int(pil_img.width * ratio)
            new_h = int(pil_img.height * ratio)
            pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

        return ImageTk.PhotoImage(pil_img)

    def _load_paired_image(self, img_data, cw=None, ch=None):
        """Download both images and create a side-by-side combined PhotoImage."""
        left_ext = os.path.splitext(img_data["left"].get("filename", ""))[1].lower()
        right_ext = os.path.splitext(img_data["right"].get("filename", ""))[1].lower()
        left_is_video = left_ext in VIDEO_EXTENSIONS
        right_is_video = right_ext in VIDEO_EXTENSIONS

        if left_is_video:
            left_pil = self._load_video_thumbnail(img_data["left"])
        else:
            left_resp = requests.get(img_data["left"]["url"], timeout=30)
            left_resp.raise_for_status()
            left_pil = Image.open(BytesIO(left_resp.content))

        if right_is_video:
            right_pil = self._load_video_thumbnail(img_data["right"])
        else:
            right_resp = requests.get(img_data["right"]["url"], timeout=30)
            right_resp.raise_for_status()
            right_pil = Image.open(BytesIO(right_resp.content))

        if cw is None or ch is None:
            self.update_idletasks()
            cw = self.canvas.winfo_width() or 800
            ch = self.canvas.winfo_height() or 500

        combined = self._create_paired_image(left_pil, right_pil, cw, ch,
                                              img_data["left"].get("label", "Left"),
                                              img_data["right"].get("label", "Right"))
        return ImageTk.PhotoImage(combined)

    def _create_paired_image(self, left_pil, right_pil, canvas_w, canvas_h, left_label, right_label):
        """Create a side-by-side image with labels."""
        gap = 24
        label_height = 28
        available_h = canvas_h - label_height
        half_w = (canvas_w - gap) // 2

        # Resize left
        ratio_l = min(half_w / left_pil.width, available_h / left_pil.height)
        if ratio_l < 1:
            left_pil = left_pil.resize(
                (int(left_pil.width * ratio_l), int(left_pil.height * ratio_l)), Image.LANCZOS
            )

        # Resize right
        ratio_r = min(half_w / right_pil.width, available_h / right_pil.height)
        if ratio_r < 1:
            right_pil = right_pil.resize(
                (int(right_pil.width * ratio_r), int(right_pil.height * ratio_r)), Image.LANCZOS
            )

        # Create combined canvas
        total_w = left_pil.width + gap + right_pil.width
        max_h = max(left_pil.height, right_pil.height) + label_height
        combined = Image.new("RGB", (total_w, max_h), (49, 50, 68))  # #313244

        # Paste images (vertically centered below labels)
        left_y = label_height + (max_h - label_height - left_pil.height) // 2
        right_y = label_height + (max_h - label_height - right_pil.height) // 2
        combined.paste(left_pil, (0, left_y))
        combined.paste(right_pil, (left_pil.width + gap, right_y))

        # Draw labels
        draw = ImageDraw.Draw(combined)
        try:
            font = ImageFont.truetype("segoeui.ttf", 14)
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = ImageFont.load_default()

        # Left label - centered above left image
        left_center_x = left_pil.width // 2
        draw.text((left_center_x, 6), left_label, fill=(137, 180, 250), font=font, anchor="mt")

        # Right label - centered above right image
        right_center_x = left_pil.width + gap + right_pil.width // 2
        draw.text((right_center_x, 6), right_label, fill=(137, 180, 250), font=font, anchor="mt")

        # Draw divider line in gap
        divider_x = left_pil.width + gap // 2
        draw.line([(divider_x, label_height), (divider_x, max_h)], fill=(88, 91, 112), width=2)

        return combined

    def _load_video_thumbnail(self, img_data):
        """Download video thumbnail from Airtable and overlay a play icon."""
        thumb_url = img_data.get("thumb_url") or img_data.get("url", "")
        filename = img_data.get("filename", "video.mp4")
        try:
            resp = requests.get(thumb_url, timeout=30)
            resp.raise_for_status()
            pil_img = Image.open(BytesIO(resp.content)).convert("RGBA")

            # Semi-transparent dark overlay
            overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 80))
            pil_img = Image.alpha_composite(pil_img, overlay)

            # Draw play triangle
            draw = ImageDraw.Draw(pil_img)
            cx, cy = pil_img.width // 2, pil_img.height // 2
            size = min(pil_img.width, pil_img.height) // 8
            draw.polygon(
                [(cx - size, cy - size), (cx - size, cy + size), (cx + size, cy)],
                fill=(255, 255, 255, 220),
            )

            return pil_img.convert("RGB")
        except Exception:
            return self._make_video_placeholder(filename)

    def _make_video_placeholder(self, filename):
        """Fallback placeholder when video thumbnail is unavailable."""
        w, h = 640, 480
        img = Image.new("RGB", (w, h), (40, 40, 40))
        draw = ImageDraw.Draw(img)
        cx, cy = w // 2, h // 2 - 20
        size = 50
        draw.polygon(
            [(cx - size, cy - size), (cx - size, cy + size), (cx + size, cy)],
            fill=(255, 255, 255),
        )
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

        # Show POSTED badge if record is marked
        img_data = self.images[index]
        if img_data.get("fields", {}).get("SB Posted"):
            self.canvas.create_rectangle(cw - 130, 10, cw - 10, 42, fill="#a6e3a1", outline="")
            self.canvas.create_text(cw - 70, 26, text="POSTED", font=("Segoe UI", 12, "bold"), fill="#1e1e2e")

        # Show DISREGARD badge
        if img_data.get("fields", {}).get("Disregard"):
            self.canvas.create_rectangle(10, 10, 150, 42, fill="#f38ba8", outline="")
            self.canvas.create_text(80, 26, text="DISREGARD", font=("Segoe UI", 12, "bold"), fill="#1e1e2e")

        self.status_label.config(text="Ready")

        # Show/hide Play Video button(s)
        img_data = self.images[index]
        is_pair = img_data.get("type") == "pair"

        if is_pair:
            self.play_btn.pack_forget()
            left_ext = os.path.splitext(img_data["left"].get("filename", ""))[1].lower()
            right_ext = os.path.splitext(img_data["right"].get("filename", ""))[1].lower()
            left_is_video = left_ext in VIDEO_EXTENSIONS
            right_is_video = right_ext in VIDEO_EXTENSIONS
            if left_is_video:
                self.play_left_btn.pack(side="left", padx=(10, 0))
            else:
                self.play_left_btn.pack_forget()
            if right_is_video:
                self.play_right_btn.pack(side="left", padx=(10, 0))
            else:
                self.play_right_btn.pack_forget()
        else:
            self.play_left_btn.pack_forget()
            self.play_right_btn.pack_forget()
            ext = os.path.splitext(img_data.get("filename", ""))[1].lower()
            if ext in VIDEO_EXTENSIONS:
                self.play_btn.pack(side="left", padx=(10, 0))
            else:
                self.play_btn.pack_forget()

        if index + 1 < len(self.images) and (index + 1) not in self.photo_cache:
            # Pass current canvas size to preload so it uses consistent dimensions
            self.after(100, self._preload, index + 1, cw, ch)

    def _play_video(self):
        """Download the current video to a temp file and open with default player."""
        if not self.images:
            return
        img_data = self.images[self.current_index]
        url = img_data.get("url", "")
        filename = img_data.get("filename", "video.mp4")
        if not url:
            return

        self.status_label.config(text="Downloading video...")
        self.update_idletasks()

        def _download_and_play():
            try:
                import tempfile
                resp = requests.get(url, timeout=120, stream=True)
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                ext = os.path.splitext(filename)[1] or ".mp4"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="sb_vid_")
                downloaded = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    tmp.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        self.after(0, lambda p=pct, m=mb, t=total_mb: self.status_label.config(
                            text=f"Downloading video... {p}% ({m:.1f}/{t:.1f} MB)"))
                tmp.close()
                os.startfile(tmp.name)
                self.after(0, lambda: self.status_label.config(text="Video opened in player"))
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Video error: {e}"))

        threading.Thread(target=_download_and_play, daemon=True).start()

    def _play_paired_video(self, side):
        """Download and play a video from a paired record (left or right side)."""
        if not self.images:
            return
        img_data = self.images[self.current_index]
        if img_data.get("type") != "pair":
            return
        side_data = img_data.get(side, {})
        url = side_data.get("url", "")
        filename = side_data.get("filename", "video.mp4")
        if not url:
            return

        label = side_data.get("label", side)
        self.status_label.config(text=f"Downloading {label}...")
        self.update_idletasks()

        def _download_and_play():
            try:
                import tempfile
                resp = requests.get(url, timeout=120, stream=True)
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                ext = os.path.splitext(filename)[1] or ".mp4"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="sb_vid_")
                downloaded = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    tmp.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        self.after(0, lambda p=pct, m=mb, t=total_mb, lb=label: self.status_label.config(
                            text=f"Downloading {lb}... {p}% ({m:.1f}/{t:.1f} MB)"))
                tmp.close()
                os.startfile(tmp.name)
                self.after(0, lambda: self.status_label.config(text=f"{label} opened in player"))
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Video error: {e}"))

        threading.Thread(target=_download_and_play, daemon=True).start()

    def _preload(self, index, cw=None, ch=None):
        if index in self.photo_cache:
            return
        try:
            img_data = self.images[index]
            is_pair = img_data.get("type") == "pair"

            if is_pair:
                photo = self._load_paired_image(img_data, cw, ch)
            else:
                photo = self._load_single_image(img_data, cw, ch)

            self.photo_cache[index] = photo
        except Exception:
            pass

    def next_image(self):
        if self.current_index < len(self.images) - 1:
            self.load_image(self.current_index + 1)

    def prev_image(self):
        if self.current_index > 0:
            self.load_image(self.current_index - 1)

    # ── Grid view ──

    def _toggle_view_mode(self):
        if not self.images:
            return
        if self.view_mode == "single":
            self._show_grid_view()
        else:
            self._show_single_view()

    def _show_grid_view(self):
        self.view_mode = "grid"
        self.grid_toggle_btn.config(text="Single View", bg="#f9e2af")

        # Hide single view, show grid
        self.canvas.pack_forget()
        self.grid_container.pack(
            fill="both", expand=True, padx=10, pady=5, before=self.nav_frame
        )

        # Disable prev/next (grid scrolls instead)
        self.prev_btn.config(state="disabled")
        self.next_btn.config(state="disabled")

        # Update header
        label = "pairs" if self.paired_mode else "images"
        self.counter_label.config(text=f"{len(self.images)} {label}")
        self.filename_label.config(text="Click a thumbnail to select")

        # Bind mousewheel for grid scrolling
        self.grid_canvas.bind(
            "<Enter>",
            lambda e: self.grid_canvas.bind_all("<MouseWheel>", self._grid_mousewheel),
        )
        self.grid_canvas.bind(
            "<Leave>", lambda e: self.grid_canvas.unbind_all("<MouseWheel>")
        )

        self._build_grid()

    def _show_single_view(self, index=None):
        self.view_mode = "single"
        self._grid_load_cancel = True
        self.grid_toggle_btn.config(text="Grid View", bg="#74c7ec")

        # Unbind grid mousewheel
        self.grid_canvas.unbind("<Enter>")
        self.grid_canvas.unbind("<Leave>")
        try:
            self.grid_canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

        # Hide grid, show single view
        self.grid_container.pack_forget()
        self.canvas.pack(
            fill="both", expand=True, padx=10, pady=5, before=self.nav_frame
        )

        # Re-enable prev/next
        self.prev_btn.config(state="normal")
        self.next_btn.config(state="normal")

        if index is not None:
            self.load_image(index)
        elif self.images:
            self.load_image(self.current_index)

    def _grid_mousewheel(self, event):
        self.grid_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_grid(self):
        # Clear existing grid content
        for widget in self.grid_inner.winfo_children():
            widget.destroy()
        self.grid_thumbs = {}
        self.grid_labels = {}
        self._grid_load_cancel = False
        self.grid_selected.clear()

        # Calculate columns based on available width
        self.update_idletasks()
        available_w = self.grid_canvas.winfo_width() or 800
        thumb_size = 150
        gap = 8
        cols = max(1, (available_w + gap) // (thumb_size + gap))
        self._grid_thumb_size = thumb_size
        self._grid_cols = cols

        # Create placeholder cells
        try:
            placeholder_font = ImageFont.truetype("segoeui.ttf", 16)
        except Exception:
            try:
                placeholder_font = ImageFont.truetype("arial.ttf", 16)
            except Exception:
                placeholder_font = ImageFont.load_default()

        for i, img_data in enumerate(self.images):
            row = i // cols
            col = i % cols

            cell = tk.Frame(self.grid_inner, bg="#3b3b52", padx=3, pady=3)
            cell.grid(row=row, column=col, padx=gap // 2, pady=gap // 2, sticky="n")

            # Placeholder thumbnail (dark square with number)
            placeholder = Image.new("RGB", (thumb_size, thumb_size), (59, 59, 82))
            draw = ImageDraw.Draw(placeholder)
            draw.text(
                (thumb_size // 2, thumb_size // 2), str(i + 1),
                fill=(100, 100, 130), font=placeholder_font, anchor="mm",
            )
            # Show POSTED badge on placeholder immediately
            if img_data.get("fields", {}).get("SB Posted"):
                draw.rectangle([4, 4, 62, 22], fill=(166, 227, 161))
                draw.text((33, 13), "POSTED", fill=(30, 30, 46), font=placeholder_font, anchor="mm")
            # Show DISREGARD badge on placeholder
            if img_data.get("fields", {}).get("Disregard"):
                draw.rectangle([4, thumb_size - 22, 80, thumb_size - 4], fill=(243, 139, 168))
                draw.text((42, thumb_size - 13), "DISREGARD", fill=(30, 30, 46), font=placeholder_font, anchor="mm")
            photo = ImageTk.PhotoImage(placeholder)

            img_label = tk.Label(cell, image=photo, bg="#3b3b52", cursor="hand2")
            img_label.image = photo
            img_label.pack()
            img_label.bind("<Button-1>", lambda e, idx=i: self._on_grid_click(idx, e))
            img_label.bind("<Button-3>", lambda e, idx=i: self._on_grid_right_click(e, idx))

            # Filename label (truncated)
            is_pair = img_data.get("type") == "pair"
            if is_pair:
                fname = img_data["left"]["filename"]
                display = f"[2x] {fname[:18]}" if len(fname) > 18 else f"[2x] {fname}"
            else:
                fname = img_data["filename"]
                display = fname[:22] if len(fname) > 22 else fname

            name_label = tk.Label(
                cell, text=display, font=("Segoe UI", 7),
                fg="#a6adc8", bg="#3b3b52", wraplength=thumb_size,
            )
            name_label.pack()
            name_label.bind("<Button-1>", lambda e, idx=i: self._on_grid_click(idx, e))
            name_label.bind("<Button-3>", lambda e, idx=i: self._on_grid_right_click(e, idx))

            self.grid_labels[i] = img_label

        # Highlight currently selected
        self._grid_highlight(self.current_index)

        # Scroll to show current image
        self.update_idletasks()
        self._grid_scroll_to(self.current_index)

        # Load actual thumbnails in background
        self.status_label.config(text="Loading thumbnails...")
        threading.Thread(target=self._load_grid_thumbnails, daemon=True).start()

    def _grid_highlight(self, index):
        for i, label in self.grid_labels.items():
            parent = label.master
            if i == index:
                parent.config(bg="#89b4fa")
                label.config(bg="#89b4fa")
            else:
                parent.config(bg="#3b3b52")
                label.config(bg="#3b3b52")

    def _grid_scroll_to(self, index):
        """Scroll the grid to make the given index visible."""
        if not self.grid_labels or index not in self.grid_labels:
            return
        self.grid_canvas.update_idletasks()
        label = self.grid_labels[index]
        cell = label.master
        # Get position relative to grid_inner
        y = cell.winfo_y()
        total_h = self.grid_inner.winfo_reqheight()
        canvas_h = self.grid_canvas.winfo_height()
        if total_h > canvas_h and total_h > 0:
            fraction = max(0, (y - canvas_h // 3)) / total_h
            self.grid_canvas.yview_moveto(fraction)

    def _on_grid_click(self, index, event=None):
        # Ctrl+Click toggles multi-select; plain click opens single view
        if event and (event.state & 0x4):  # Ctrl held
            if index in self.grid_selected:
                self.grid_selected.discard(index)
            else:
                self.grid_selected.add(index)
            self._grid_highlight_multi()
            count = len(self.grid_selected)
            if count:
                self.counter_label.config(text=f"{count} selected")
            else:
                self.counter_label.config(text=f"{len(self.images)} items")
            return
        # Plain click — clear multi-select and open single view
        self.grid_selected.clear()
        self.current_index = index
        self._show_single_view(index)

    def _grid_highlight_multi(self):
        """Highlight all multi-selected cells with a distinct color."""
        for i, label in self.grid_labels.items():
            parent = label.master
            if i in self.grid_selected:
                parent.config(bg="#f38ba8")
                label.config(bg="#f38ba8")
            elif i == self.current_index:
                parent.config(bg="#89b4fa")
                label.config(bg="#89b4fa")
            else:
                parent.config(bg="#3b3b52")
                label.config(bg="#3b3b52")

    def _on_canvas_right_click(self, event):
        """Show context menu on right-click in single view."""
        if not self.images:
            return
        index = self.current_index
        img_data = self.images[index]
        is_disregarded = img_data.get("fields", {}).get("Disregard")

        self.grid_menu.delete(0, "end")
        if not is_disregarded:
            self.grid_menu.add_command(
                label="Disregard",
                command=lambda: self._disregard_records([index], True),
            )
        else:
            self.grid_menu.add_command(
                label="Undo Disregard",
                command=lambda: self._disregard_records([index], False),
            )
        self.grid_menu.post(event.x_root, event.y_root)

    def _on_grid_right_click(self, event, index):
        """Show context menu on right-click in grid view."""
        # If right-clicking on an item not in selection, select only that item
        if self.grid_selected and index not in self.grid_selected:
            self.grid_selected.clear()
            self._grid_highlight_multi()
        if not self.grid_selected:
            self.grid_selected.add(index)
            self._grid_highlight_multi()
            self.counter_label.config(text="1 selected")

        self.grid_menu.delete(0, "end")

        selected_indices = list(self.grid_selected)
        any_disregarded = any(
            self.images[i].get("fields", {}).get("Disregard")
            for i in selected_indices
        )
        any_not_disregarded = any(
            not self.images[i].get("fields", {}).get("Disregard")
            for i in selected_indices
        )

        count = len(selected_indices)
        label_suffix = f" ({count})" if count > 1 else ""

        if any_not_disregarded:
            self.grid_menu.add_command(
                label=f"Disregard{label_suffix}",
                command=lambda: self._disregard_records(selected_indices, True),
            )
        if any_disregarded:
            self.grid_menu.add_command(
                label=f"Undo Disregard{label_suffix}",
                command=lambda: self._disregard_records(selected_indices, False),
            )

        self.grid_menu.post(event.x_root, event.y_root)

    def _disregard_records(self, indices, disregard):
        """Mark/unmark multiple records as Disregard in Airtable (background)."""
        action = "Disregarding" if disregard else "Un-disregarding"
        self.status_label.config(text=f"{action} {len(indices)} record(s)...")

        def _do():
            for idx in indices:
                img_data = self.images[idx]
                base_id = img_data.get("base_id")
                table_id = img_data.get("table_id")
                record_id = img_data.get("record_id")
                if not all([base_id, table_id, record_id]):
                    continue
                success = mark_record_disregarded(base_id, table_id, record_id, disregard)
                if success:
                    img_data.setdefault("fields", {})["Disregard"] = disregard
            # Update disk cache
            try:
                update_cache(self._fetch_base_id, self._fetch_cache_key, self.images)
            except Exception as e:
                print(f"  Cache update warning: {e}")
            # Refresh UI on main thread
            self.after(0, self._after_disregard, indices)

        threading.Thread(target=_do, daemon=True).start()

    def _after_disregard(self, indices):
        """Refresh grid thumbnails and clear selection after disregard update."""
        self.grid_selected.clear()
        self.status_label.config(text="Done!")
        # Clear single-view cache for affected indices
        for idx in indices:
            self.photo_cache.pop(idx, None)
        # Rebuild grid to refresh badges, or reload single view
        if self.view_mode == "grid":
            self._build_grid()
        else:
            self.load_image(self.current_index)

    def _load_grid_thumbnails(self):
        """Load thumbnails in background using Airtable thumbnail URLs."""
        thumb_size = self._grid_thumb_size
        total = len(self.images)

        try:
            badge_font = ImageFont.truetype("segoeui.ttf", 10)
        except Exception:
            try:
                badge_font = ImageFont.truetype("arial.ttf", 10)
            except Exception:
                badge_font = ImageFont.load_default()

        for i, img_data in enumerate(self.images):
            if self._grid_load_cancel:
                return
            try:
                is_pair = img_data.get("type") == "pair"
                if is_pair:
                    url = img_data["left"].get("thumb_url", img_data["left"]["url"])
                else:
                    url = img_data.get("thumb_url", img_data["url"])

                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                pil_img = Image.open(BytesIO(resp.content))

                # Fit into square thumbnail
                pil_img.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
                square = Image.new("RGB", (thumb_size, thumb_size), (49, 50, 68))
                x_off = (thumb_size - pil_img.width) // 2
                y_off = (thumb_size - pil_img.height) // 2
                square.paste(pil_img, (x_off, y_off))

                draw = ImageDraw.Draw(square)

                # Draw "2x" badge for paired images
                if is_pair:
                    draw.rectangle(
                        [thumb_size - 30, 4, thumb_size - 4, 22], fill=(137, 180, 250)
                    )
                    draw.text(
                        (thumb_size - 17, 13), "2x",
                        fill=(30, 30, 46), font=badge_font, anchor="mm",
                    )

                # Draw "POSTED" badge if record is marked
                if img_data.get("fields", {}).get("SB Posted"):
                    draw.rectangle(
                        [4, 4, 62, 22], fill=(166, 227, 161)
                    )
                    draw.text(
                        (33, 13), "POSTED",
                        fill=(30, 30, 46), font=badge_font, anchor="mm",
                    )

                # Draw "DISREGARD" badge
                if img_data.get("fields", {}).get("Disregard"):
                    draw.rectangle(
                        [4, thumb_size - 22, 80, thumb_size - 4], fill=(243, 139, 168)
                    )
                    draw.text(
                        (42, thumb_size - 13), "DISREGARD",
                        fill=(30, 30, 46), font=badge_font, anchor="mm",
                    )

                photo = ImageTk.PhotoImage(square)
                self.grid_thumbs[i] = photo

                if not self._grid_load_cancel:
                    self.after(0, self._update_grid_thumb, i, photo)

                # Update progress periodically
                if (i + 1) % 10 == 0 or i + 1 == total:
                    if not self._grid_load_cancel:
                        count = i + 1
                        self.after(
                            0,
                            lambda c=count, t=total: self.status_label.config(
                                text=f"Thumbnails: {c}/{t}"
                            ),
                        )
            except Exception:
                continue

        if not self._grid_load_cancel:
            self.after(
                0,
                lambda: self.status_label.config(
                    text=f"Grid loaded — {len(self.grid_thumbs)}/{total} thumbnails"
                ),
            )

    def _update_grid_thumb(self, index, photo):
        if index in self.grid_labels and self.view_mode == "grid":
            label = self.grid_labels[index]
            label.config(image=photo)
            label.image = photo

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

    def _update_post_button(self):
        """Update the post button text based on current mode."""
        if self.paired_mode and self.paired_field_name == "Before Reels + After Reels":
            self.post_btn.config(text="Ready to Post Before and After Reels", bg="#cba6f7")
        elif self.paired_mode:
            self.post_btn.config(text="Ready to Post Before and After", bg="#cba6f7")
        else:
            self.post_btn.config(text="Post to SocialBee", bg="#f9e2af")

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

        self.posting = True
        self.post_btn.config(state="disabled", text="Posting...", bg="#585b70")

        is_pair = img_data.get("type") == "pair"

        if is_pair:
            is_reels = self.paired_field_name == "Before Reels + After Reels"
            dl_label = "2 reels" if is_reels else "2 images"
            self.post_status_var.set(f"Downloading {dl_label} & posting (headless)...")
            image_urls = [img_data["left"]["url"], img_data["right"]["url"]]
            filenames = [img_data["left"]["filename"], img_data["right"]["filename"]]
            thread = threading.Thread(
                target=post_to_socialbee_multiple,
                args=(caption, image_urls, filenames,
                      category, schedule_date, schedule_time, self.result_queue),
                daemon=True,
            )
        else:
            self.post_status_var.set("Downloading image & posting (headless)...")
            thread = threading.Thread(
                target=post_to_socialbee,
                args=(caption, img_data["url"], img_data["filename"],
                      category, schedule_date, schedule_time, self.result_queue),
                daemon=True,
            )

        thread.start()
        self._poll_result()

    def _on_post_story(self):
        if self.posting:
            return
        if not self.images:
            messagebox.showwarning("No Image", "No image selected.")
            return

        caption = self.caption_text.get("1.0", "end").strip()
        # Story posts don't require a caption — allow empty

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

        self.posting = True
        self.post_btn.config(state="disabled")
        self.post_story_btn.config(state="disabled", text="Posting Story...", bg="#585b70")
        self.post_status_var.set("Downloading image & posting Story...")

        thread = threading.Thread(
            target=post_to_socialbee_story,
            args=(caption, img_data["url"], img_data["filename"],
                  category, schedule_date, schedule_time, self.result_queue),
            daemon=True,
        )
        thread.start()
        self._poll_result_story()

    def _poll_result_story(self):
        try:
            status, message = self.result_queue.get_nowait()
            self.posting = False
            self.post_btn.config(state="normal")
            self.post_story_btn.config(state="normal", text="Post to SocialBee Story", bg="#a6e3a1")
            self._update_post_button()

            if status == "success":
                self.post_status_var.set("Story posted successfully! Marking in Airtable...")
                messagebox.showinfo("Success", message)
                img_data = self.images[self.current_index]
                self._mark_as_posted(img_data)
            else:
                self.post_status_var.set(f"Error: {message}")
                messagebox.showerror("Error", message)
        except queue.Empty:
            self.after(500, self._poll_result_story)

    def _poll_result(self):
        try:
            status, message = self.result_queue.get_nowait()
            self.posting = False
            self.post_btn.config(state="normal")
            self.post_story_btn.config(state="normal")
            self._update_post_button()

            if status == "success":
                self.post_status_var.set("Posted successfully! Marking in Airtable...")
                messagebox.showinfo("Success", message)
                # Mark as posted in Airtable (background, non-blocking)
                img_data = self.images[self.current_index]
                self._mark_as_posted(img_data)
            else:
                self.post_status_var.set(f"Error: {message}")
                messagebox.showerror("Error", message)
        except queue.Empty:
            self.after(500, self._poll_result)

    def _mark_as_posted(self, img_data):
        """Mark the current record as posted in Airtable (background thread)."""
        base_id = img_data.get("base_id")
        table_id = img_data.get("table_id")
        record_id = img_data.get("record_id")

        if not all([base_id, table_id, record_id]):
            print("  Cannot mark as posted: missing base_id/table_id/record_id")
            return

        def _do_mark():
            success = mark_record_posted(base_id, table_id, record_id)
            if success:
                img_data.setdefault("fields", {})["SB Posted"] = True
                # Update disk cache so badge persists after app restart
                try:
                    update_cache(self._fetch_base_id, self._fetch_cache_key, self.images)
                except Exception as e:
                    print(f"  Cache update warning: {e}")
                self.after(0, lambda: self.post_status_var.set("Posted & marked in Airtable!"))
                self.after(0, lambda: self._refresh_posted_badge())
            else:
                self.after(0, lambda: self.post_status_var.set("Posted but could not mark in Airtable"))

        threading.Thread(target=_do_mark, daemon=True).start()

    def _refresh_posted_badge(self):
        """Refresh the current display to show/hide POSTED badge."""
        if self.images and self.current_index in self.photo_cache:
            self._display_cached(self.current_index)

    def _on_setup_login(self):
        """Open Brave with automation profile for one-time SocialBee login."""
        self.setup_login_btn.config(state="disabled", text="Browser open — log in to SocialBee...")
        self.post_status_var.set("Log in to SocialBee in the browser, then close it.")
        self.update_idletasks()

        def _run():
            try:
                setup_automation_profile()
                self.after(0, lambda: self.post_status_var.set("Login saved! Headless posting ready."))
            except Exception as e:
                self.after(0, lambda: self.post_status_var.set(f"Setup error: {e}"))
            finally:
                self.after(0, lambda: self.setup_login_btn.config(state="normal", text="Setup Login"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_setup_chrome_post_login(self):
        """Open Chrome with post profile for one-time SocialBee login."""
        self.setup_chrome_post_btn.config(state="disabled", text="Chrome open — log in to SocialBee...")
        self.post_status_var.set("Log in to SocialBee in Chrome, then close it.")
        self.update_idletasks()

        def _run():
            try:
                setup_chrome_post_profile()
                self.after(0, lambda: self.post_status_var.set("Chrome login saved! Post ready."))
            except Exception as e:
                self.after(0, lambda: self.post_status_var.set(f"Chrome setup error: {e}"))
            finally:
                self.after(0, lambda: self.setup_chrome_post_btn.config(
                    state="normal", text="Setup Login (Chrome - Post)"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_setup_chrome_login(self):
        """Open Chrome with story profile for one-time SocialBee login."""
        self.setup_chrome_btn.config(state="disabled", text="Chrome open — log in to SocialBee...")
        self.post_status_var.set("Log in to SocialBee in Chrome, then close it.")
        self.update_idletasks()

        def _run():
            try:
                setup_chrome_story_profile()
                self.after(0, lambda: self.post_status_var.set("Chrome login saved! Story posting ready."))
            except Exception as e:
                self.after(0, lambda: self.post_status_var.set(f"Chrome setup error: {e}"))
            finally:
                self.after(0, lambda: self.setup_chrome_btn.config(
                    state="normal", text="Setup Login (Chrome - Story)"))

        threading.Thread(target=_run, daemon=True).start()
