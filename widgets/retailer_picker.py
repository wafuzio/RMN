from tkinter import ttk, BooleanVar, Frame
import tkinter as tk

RETAILERS = [
    "Amazon",
    "Walmart", 
    "Kroger",
    "Instacart",
    "Albertsons",
    "Doordash",
    "gopuff",
    "Target",
    "Hyvee",
    "Meijer",
    "Ahold",
]


class RetailerPicker(Frame):
    """
    Multi-select retailer picker. Selected are highlighted; unavailable are disabled/gray.
    
    Use:
        picker = RetailerPicker(parent, unavailable={"Ahold"})
        picker.grid(...)
        selected = picker.get_selected()
    """
    def __init__(self, master=None, unavailable=None, columns=4, **kwargs):
        super().__init__(master, **kwargs)
        self.unavailable = set(unavailable or [])
        self.columns = columns
        self.vars: dict[str, BooleanVar] = {}
        
        # macOS renders ttk colors more predictably under 'clam'
        style = ttk.Style(self)
        try:
            if style.theme_use() != "clam":
                style.theme_use("clam")
        except Exception:
            pass
        
        style.configure("Retailer.TCheckbutton", padding=(10, 6), focuscolor="")
        style.map(
            "Retailer.TCheckbutton",
            background=[("selected", "#e6f2ff"), ("!selected", "#f5f5f5"), ("disabled", "#ededed")],
            foreground=[("disabled", "#9a9a9a"), ("!disabled", "#111")],
        )
        
        for idx, name in enumerate(RETAILERS):
            var = BooleanVar(value=False)
            self.vars[name] = var
            chk = ttk.Checkbutton(
                self, text=name, variable=var,
                style="Retailer.TCheckbutton", takefocus=True,
                onvalue=True, offvalue=False,
            )
            if name in self.unavailable:
                chk.state(["disabled"])
            r, c = divmod(idx, self.columns)
            chk.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
        
        for c in range(self.columns):
            self.grid_columnconfigure(c, weight=1)
        
        controls = ttk.Frame(self)
        controls.grid(row=len(RETAILERS)//self.columns + 1, column=0,
                      columnspan=self.columns, sticky="ew", pady=(8, 0))
        ttk.Button(controls, text="Select All", command=self.select_all).pack(side="left")
        ttk.Button(controls, text="Clear All", command=self.clear_all).pack(side="left", padx=(8, 0))
    
    def get_selected(self) -> list[str]:
        return [name for name, var in self.vars.items() if var.get() and name not in self.unavailable]
    
    def select_all(self):
        for name, var in self.vars.items():
            if name not in self.unavailable:
                var.set(True)
    
    def clear_all(self):
        for var in self.vars.values():
            var.set(False)
