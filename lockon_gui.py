import tkinter as tk
from tkinter import ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - handled in the GUI
    serial = None
    list_ports = None


BAUDRATE = 115200
POSITION_MIN = -100
POSITION_MAX = 100
TICK_MS = 80


class LockonGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LOCKON v0.1")
        self.root.resizable(False, False)

        self.serial_link = None
        self.active_directions: set[str] = set()

        self.pos_x = tk.IntVar(value=0)
        self.pos_y = tk.IntVar(value=0)
        self.speed = tk.IntVar(value=5)
        self.port = tk.StringVar()
        self.status = tk.StringVar(value="Deconnecte")

        self._build_ui()
        self.refresh_ports()
        self._bind_keys()
        self._tick()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0)

        connection = ttk.LabelFrame(frame, text="Connexion", padding=10)
        connection.grid(row=0, column=0, columnspan=3, sticky="ew")

        self.port_combo = ttk.Combobox(
            connection,
            textvariable=self.port,
            width=18,
            state="readonly",
        )
        self.port_combo.grid(row=0, column=0, padx=(0, 8))

        ttk.Button(connection, text="Rafraichir", command=self.refresh_ports).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(connection, text="Connecter", command=self.connect).grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(connection, text="Deconnecter", command=self.disconnect).grid(
            row=0, column=3
        )

        controls = ttk.LabelFrame(frame, text="Controle manuel", padding=10)
        controls.grid(row=1, column=0, columnspan=3, pady=12)

        self._arrow_button(controls, "↑", "UP").grid(row=0, column=1, padx=6, pady=6)
        self._arrow_button(controls, "←", "LEFT").grid(row=1, column=0, padx=6, pady=6)
        ttk.Button(controls, text="CENTRE", command=self.center).grid(
            row=1, column=1, padx=6, pady=6
        )
        self._arrow_button(controls, "→", "RIGHT").grid(row=1, column=2, padx=6, pady=6)
        self._arrow_button(controls, "↓", "DOWN").grid(row=2, column=1, padx=6, pady=6)

        telemetry = ttk.LabelFrame(frame, text="Etat", padding=10)
        telemetry.grid(row=2, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(telemetry, text="Pos X").grid(row=0, column=0, sticky="w")
        ttk.Label(telemetry, textvariable=self.pos_x, width=6).grid(row=0, column=1)
        ttk.Label(telemetry, text="Pos Y").grid(row=1, column=0, sticky="w")
        ttk.Label(telemetry, textvariable=self.pos_y, width=6).grid(row=1, column=1)

        speed_frame = ttk.LabelFrame(frame, text="Vitesse", padding=10)
        speed_frame.grid(row=2, column=1, columnspan=2, sticky="ew")

        ttk.Scale(
            speed_frame,
            from_=1,
            to=20,
            orient="horizontal",
            variable=self.speed,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Spinbox(
            speed_frame,
            from_=1,
            to=20,
            textvariable=self.speed,
            width=5,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(frame, textvariable=self.status).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(12, 0),
        )

    def _arrow_button(self, parent: ttk.Frame, label: str, direction: str) -> ttk.Button:
        button = ttk.Button(parent, text=label, width=6)
        button.bind("<ButtonPress-1>", lambda _event: self._press(direction))
        button.bind("<ButtonRelease-1>", lambda _event: self._release(direction))
        button.bind("<Leave>", lambda _event: self._release(direction))
        return button

    def _bind_keys(self) -> None:
        key_map = {
            "<Up>": "UP",
            "<Down>": "DOWN",
            "<Left>": "LEFT",
            "<Right>": "RIGHT",
        }
        for key, direction in key_map.items():
            self.root.bind(key, lambda _event, item=direction: self._press(item))
            self.root.bind(
                f"<KeyRelease-{key[1:-1]}>",
                lambda _event, item=direction: self._release(item),
            )

    def refresh_ports(self) -> None:
        if list_ports is None:
            self.port_combo["values"] = []
            self.status.set("Module pyserial manquant: python -m pip install -r requirements.txt")
            return

        ports = [port.device for port in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and self.port.get() not in ports:
            preferred_ports = [port for port in ports if port.upper() != "COM1"]
            self.port.set(preferred_ports[0] if preferred_ports else ports[0])

    def connect(self) -> None:
        if serial is None:
            self.status.set("Impossible de connecter: pyserial n'est pas installe")
            return

        selected_port = self.port.get().strip()
        if not selected_port:
            self.status.set("Aucun port serie selectionne")
            return

        self.disconnect()
        try:
            self.serial_link = serial.Serial(
                selected_port,
                BAUDRATE,
                timeout=0.05,
                write_timeout=0.2,
            )
        except serial.SerialException as exc:
            self.serial_link = None
            self.status.set(f"Connexion impossible sur {selected_port}: {exc}")
            return

        self.status.set(f"Connecte sur {selected_port}")
        self.root.after(2000, self.center)

    def disconnect(self) -> None:
        if self.serial_link is not None:
            self.serial_link.close()
            self.serial_link = None
        self.status.set("Deconnecte")

    def center(self) -> None:
        self.pos_x.set(0)
        self.pos_y.set(0)
        self._send_position()

    def _press(self, direction: str) -> None:
        self.active_directions.add(direction)

    def _release(self, direction: str) -> None:
        self.active_directions.discard(direction)

    def _tick(self) -> None:
        if self.active_directions:
            step = max(1, min(int(self.speed.get()), 20))
            x = self.pos_x.get()
            y = self.pos_y.get()

            if "LEFT" in self.active_directions:
                x -= step
            if "RIGHT" in self.active_directions:
                x += step
            if "UP" in self.active_directions:
                y += step
            if "DOWN" in self.active_directions:
                y -= step

            self.pos_x.set(max(POSITION_MIN, min(POSITION_MAX, x)))
            self.pos_y.set(max(POSITION_MIN, min(POSITION_MAX, y)))
            self._send_position()

        self.root.after(TICK_MS, self._tick)

    def _send_position(self) -> None:
        command = f"POS {self.pos_x.get()} {self.pos_y.get()}\n"
        if self.serial_link is None or not self.serial_link.is_open:
            self.status.set(f"Simulation: {command.strip()}")
            return

        try:
            self.serial_link.write(command.encode("ascii"))
            self.status.set(f"Envoye: {command.strip()}")
        except serial.SerialException as exc:
            self.status.set(f"Erreur serie: {exc}")
            self.disconnect()


def main() -> None:
    root = tk.Tk()
    app = LockonGui(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.disconnect(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
