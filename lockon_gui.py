import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

try:
    import cv2
except ImportError:  # pragma: no cover - handled in the GUI
    cv2 = None

try:
    import mediapipe as mp
except ImportError:  # pragma: no cover - handled in the GUI
    mp = None

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - handled in the GUI
    serial = None
    list_ports = None


BAUDRATE = 115200
POSITION_MIN = -700
POSITION_MAX = 700
TICK_MS = 120
SPEED_MIN = 1
SPEED_MAX = 500
DEFAULT_SPEED = 50
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360
VIDEO_REFRESH_MS = 33
DEFAULT_CAMERA_INDEX = 0
DEFAULT_CAMERA_FPS = 30
HAND_MODEL_PATH = Path("hand_landmarker.task")
DETECT_EVERY_FRAMES = 2
TRACKING_DEADZONE_PX = 35
TRACKING_GAIN = 0.25
TRACKING_TARGETS = ("Rien", "Main", "Tete")
TRACKING_SPEED_MODES = ("Normal", "Fast")
TRACKING_SPEED_MULTIPLIERS = {
    "Normal": 1.0,
    "Fast": 2.4,
}
DEFAULT_PREDICTION_MS = 160
MAX_PREDICTION_MS = 500


class LockonGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LOCKON v0.2")
        self.root.resizable(False, False)

        self.serial_link = None
        self.camera = None
        self.camera_after_id = None
        self.landmarker = None
        self.face_cascade = None
        self.video_photo = None
        self.active_directions: set[str] = set()
        self.frame_index = 0
        self.hand_draw_data = []
        self.face_draw_data = []
        self.observed_target_center = None
        self.target_center = None
        self.target_label = ""
        self.previous_observed_target_center = None
        self.previous_target_time = None
        self.target_velocity = (0.0, 0.0)

        self.pos_x = tk.IntVar(value=0)
        self.pos_y = tk.IntVar(value=0)
        self.speed_input = tk.IntVar(value=DEFAULT_SPEED)
        self.applied_speed = tk.IntVar(value=DEFAULT_SPEED)
        self.camera_index = tk.IntVar(value=DEFAULT_CAMERA_INDEX)
        self.tracking_target = tk.StringVar(value="Main")
        self.tracking_speed_mode = tk.StringVar(value="Normal")
        self.tracking_deadzone = tk.IntVar(value=TRACKING_DEADZONE_PX)
        self.tracking_gain_percent = tk.IntVar(value=int(TRACKING_GAIN * 100))
        self.prediction_enabled = tk.BooleanVar(value=False)
        self.prediction_ms = tk.IntVar(value=DEFAULT_PREDICTION_MS)
        self.target_count = tk.IntVar(value=0)
        self.port = tk.StringVar()
        self.status = tk.StringVar(value="Deconnecte")
        self.camera_status = tk.StringVar(value="Camera arretee")
        self.detection_status = tk.StringVar(value="Detection inactive")
        self.tracking_status = tk.StringVar(value="Suivi inactif")

        self.style = ttk.Style()
        self.style.configure("Connected.TButton", foreground="green")
        self.style.configure("Disconnect.TButton", foreground="red")
        self.style.configure("Neutral.TButton")

        self._build_ui()
        self.refresh_ports()
        self._bind_keys()
        self._update_connection_buttons()
        self._update_camera_buttons()
        self._tick()
        self.root.after(300, self.start_camera)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0)

        video = ttk.LabelFrame(frame, text="Video", padding=10)
        video.grid(row=0, column=0, sticky="n", padx=(0, 14))

        self.video_canvas = tk.Canvas(
            video,
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            background="#111111",
            highlightthickness=0,
        )
        self.video_canvas.grid(row=0, column=0, columnspan=4)
        self.video_image = self.video_canvas.create_image(0, 0, anchor="nw")
        self.video_message = self.video_canvas.create_text(
            VIDEO_WIDTH // 2,
            VIDEO_HEIGHT // 2,
            fill="#f0f0f0",
            text="Camera arretee",
        )

        ttk.Label(video, text="Index").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Spinbox(
            video,
            from_=0,
            to=9,
            textvariable=self.camera_index,
            width=4,
        ).grid(row=1, column=1, sticky="w", padx=(6, 10), pady=(10, 0))
        self.start_camera_button = ttk.Button(
            video,
            text="Demarrer",
            command=self.start_camera,
        )
        self.start_camera_button.grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(10, 0))
        self.stop_camera_button = ttk.Button(
            video,
            text="Arreter",
            command=self.stop_camera,
        )
        self.stop_camera_button.grid(row=1, column=3, sticky="ew", pady=(10, 0))

        side = ttk.Frame(frame)
        side.grid(row=0, column=1, sticky="n")

        connection = ttk.LabelFrame(side, text="Connexion", padding=10)
        connection.grid(row=0, column=0, sticky="ew")

        self.port_combo = ttk.Combobox(
            connection,
            textvariable=self.port,
            width=18,
            state="readonly",
        )
        self.port_combo.grid(row=0, column=0, padx=(0, 8))

        ttk.Button(connection, text="Rafraichir", command=self.refresh_ports).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        self.connect_button = ttk.Button(connection, text="Connecter", command=self.connect)
        self.connect_button.grid(row=0, column=2, padx=(0, 8))
        self.disconnect_button = ttk.Button(
            connection,
            text="Deconnecter",
            command=self.disconnect,
        )
        self.disconnect_button.grid(row=0, column=3)

        controls = ttk.LabelFrame(side, text="Controles", padding=10)
        controls.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        self._arrow_button(controls, "Haut", "UP").grid(row=0, column=1, padx=6, pady=6)
        self._arrow_button(controls, "Gauche", "LEFT").grid(row=1, column=0, padx=6, pady=6)
        ttk.Button(controls, text="CENTRE", command=self.center).grid(
            row=1,
            column=1,
            padx=6,
            pady=6,
        )
        self._arrow_button(controls, "Droite", "RIGHT").grid(row=1, column=2, padx=6, pady=6)
        self._arrow_button(controls, "Bas", "DOWN").grid(row=2, column=1, padx=6, pady=6)

        settings = ttk.LabelFrame(side, text="Parametres", padding=10)
        settings.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        ttk.Label(settings, text="Vitesse").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Spinbox(
            settings,
            from_=SPEED_MIN,
            to=SPEED_MAX,
            textvariable=self.speed_input,
            width=5,
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(settings, text="Envoyer", command=self.apply_speed).grid(row=0, column=2)

        tracking = ttk.LabelFrame(side, text="Tracking", padding=10)
        tracking.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        ttk.Label(tracking, text="Cible").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(
            tracking,
            textvariable=self.tracking_target,
            values=TRACKING_TARGETS,
            width=9,
            state="readonly",
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(tracking, text="Mode").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Combobox(
            tracking,
            textvariable=self.tracking_speed_mode,
            values=TRACKING_SPEED_MODES,
            width=8,
            state="readonly",
        ).grid(row=0, column=3, sticky="w")

        ttk.Label(tracking, text="Zone morte").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(
            tracking,
            from_=5,
            to=120,
            textvariable=self.tracking_deadzone,
            width=5,
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(tracking, text="Gain").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(
            tracking,
            from_=5,
            to=100,
            textvariable=self.tracking_gain_percent,
            width=5,
        ).grid(row=1, column=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            tracking,
            text="Prediction",
            variable=self.prediction_enabled,
            command=self._on_prediction_changed,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(tracking, text="Avance ms").grid(
            row=2,
            column=2,
            sticky="w",
            padx=(0, 8),
            pady=(8, 0),
        )
        ttk.Spinbox(
            tracking,
            from_=0,
            to=MAX_PREDICTION_MS,
            textvariable=self.prediction_ms,
            width=5,
        ).grid(row=2, column=3, sticky="w", pady=(8, 0))

        self.tracking_target.trace_add("write", lambda *_args: self._on_tracking_target_changed())
        self.tracking_speed_mode.trace_add("write", lambda *_args: self._update_tracking_status())

        state = ttk.LabelFrame(side, text="Etat", padding=10)
        state.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        state.columnconfigure(1, weight=1)

        ttk.Label(state, text="Pos X").grid(row=0, column=0, sticky="w")
        ttk.Label(state, textvariable=self.pos_x, width=24).grid(row=0, column=1, sticky="e")
        ttk.Label(state, text="Pos Y").grid(row=1, column=0, sticky="w")
        ttk.Label(state, textvariable=self.pos_y, width=24).grid(row=1, column=1, sticky="e")
        ttk.Label(state, text="Vitesse").grid(row=2, column=0, sticky="w")
        ttk.Label(state, textvariable=self.applied_speed, width=24).grid(row=2, column=1, sticky="e")
        ttk.Label(state, text="Camera").grid(row=3, column=0, sticky="w")
        ttk.Label(state, textvariable=self.camera_status, width=24).grid(row=3, column=1, sticky="e")
        ttk.Label(state, text="Detection").grid(row=4, column=0, sticky="w")
        ttk.Label(state, textvariable=self.detection_status, width=24).grid(row=4, column=1, sticky="e")
        ttk.Label(state, text="Suivi").grid(row=5, column=0, sticky="w")
        ttk.Label(state, textvariable=self.tracking_status, width=24).grid(row=5, column=1, sticky="e")
        ttk.Label(state, text="Cibles").grid(row=6, column=0, sticky="w")
        ttk.Label(state, textvariable=self.target_count, width=24).grid(row=6, column=1, sticky="e")
        ttk.Label(state, text="Serie").grid(row=7, column=0, sticky="w")
        ttk.Label(state, textvariable=self.status, width=24).grid(row=7, column=1, sticky="e")

    def _arrow_button(self, parent: ttk.Frame, label: str, direction: str) -> ttk.Button:
        button = ttk.Button(parent, text=label, width=8)
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
        self._update_connection_buttons()
        self.root.after(2000, self.center)

    def disconnect(self) -> None:
        if self.serial_link is not None:
            self.serial_link.close()
            self.serial_link = None
        self.status.set("Deconnecte")
        self._update_connection_buttons()

    def _update_connection_buttons(self) -> None:
        is_connected = self.serial_link is not None and self.serial_link.is_open
        if is_connected:
            self.connect_button.configure(style="Connected.TButton")
            self.disconnect_button.configure(style="Disconnect.TButton")
        else:
            self.connect_button.configure(style="Neutral.TButton")
            self.disconnect_button.configure(style="Neutral.TButton")

    def _update_camera_buttons(self) -> None:
        is_running = self.camera is not None and self.camera.isOpened()
        if cv2 is None:
            self.start_camera_button.configure(state="disabled")
            self.stop_camera_button.configure(state="disabled")
        elif is_running:
            self.start_camera_button.configure(state="disabled")
            self.stop_camera_button.configure(state="normal")
        else:
            self.start_camera_button.configure(state="normal")
            self.stop_camera_button.configure(state="disabled")

    def start_camera(self) -> None:
        if cv2 is None:
            self.camera_status.set("OpenCV manquant")
            self._set_video_message("Installe opencv-python")
            return

        try:
            index = int(self.camera_index.get())
        except tk.TclError:
            index = DEFAULT_CAMERA_INDEX
            self.camera_index.set(index)

        self.stop_camera()

        camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not camera.isOpened():
            camera.release()
            camera = cv2.VideoCapture(index)

        if not camera.isOpened():
            self.camera = None
            self.camera_status.set(f"Camera {index} indisponible")
            self._set_video_message("Camera indisponible")
            self._update_camera_buttons()
            return

        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
        camera.set(cv2.CAP_PROP_FPS, DEFAULT_CAMERA_FPS)
        self.camera = camera
        self.camera_status.set(f"Camera {index} active")
        self._update_camera_buttons()
        self._update_detection_status()
        self._update_video_frame()

    def stop_camera(self) -> None:
        if self.camera_after_id is not None:
            self.root.after_cancel(self.camera_after_id)
            self.camera_after_id = None
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.video_photo = None
        self.hand_draw_data = []
        self.face_draw_data = []
        self.observed_target_center = None
        self.target_center = None
        self.target_label = ""
        self.previous_observed_target_center = None
        self.previous_target_time = None
        self.target_velocity = (0.0, 0.0)
        self.target_count.set(0)
        self.camera_status.set("Camera arretee")
        self._set_video_message("Camera arretee")
        self._update_camera_buttons()
        self._update_detection_status()

    def _set_video_message(self, message: str) -> None:
        self.video_canvas.itemconfigure(self.video_image, image="")
        self.video_canvas.itemconfigure(self.video_message, text=message, state="normal")

    def _update_video_frame(self) -> None:
        if self.camera is None or not self.camera.isOpened():
            self.camera_after_id = None
            self._update_camera_buttons()
            return

        ok, frame = self.camera.read()
        if ok:
            frame = cv2.flip(frame, 0)
            frame = cv2.resize(frame, (VIDEO_WIDTH, VIDEO_HEIGHT), interpolation=cv2.INTER_AREA)
            self._process_detection(frame)
            self._draw_lockon_overlay(frame)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ppm_header = f"P6 {VIDEO_WIDTH} {VIDEO_HEIGHT} 255\n".encode("ascii")
            self.video_photo = tk.PhotoImage(
                data=ppm_header + rgb_frame.tobytes(),
                format="PPM",
            )
            self.video_canvas.itemconfigure(self.video_image, image=self.video_photo)
            self.video_canvas.itemconfigure(self.video_message, state="hidden")
        else:
            self.camera_status.set("Lecture impossible")
            self._set_video_message("Flux indisponible")

        self.camera_after_id = self.root.after(VIDEO_REFRESH_MS, self._update_video_frame)

    def _update_detection_status(self) -> None:
        target = self.tracking_target.get()
        if target == "Rien":
            self.detection_status.set("Detection inactive")
            self._clear_targets()
            self._update_tracking_status()
            return
        if target == "Main" and mp is None:
            self.detection_status.set("MediaPipe manquant")
            return
        if target == "Main" and not HAND_MODEL_PATH.exists():
            self.detection_status.set("Modele absent")
            return
        if target == "Tete" and not self._ensure_face_cascade():
            self.detection_status.set("Cascade tete absente")
            return
        if self.camera is None or not self.camera.isOpened():
            self.detection_status.set("En attente camera")
            return
        self.detection_status.set(f"Detection {target.lower()}")
        self._update_tracking_status()

    def _update_tracking_status(self) -> None:
        target = self.tracking_target.get()
        if target == "Rien":
            self.tracking_status.set("Suivi inactif")
            return
        if self.camera is None or not self.camera.isOpened():
            self.tracking_status.set("En attente camera")
            return
        if self.target_center is None:
            self.tracking_status.set("Recherche cible")
            return
        mode = self.tracking_speed_mode.get().lower()
        suffix = " pred" if self.prediction_enabled.get() else ""
        self.tracking_status.set(f"{target} {mode}{suffix}")

    def _on_tracking_target_changed(self) -> None:
        self._clear_targets()
        self._update_detection_status()

    def _on_prediction_changed(self) -> None:
        self._reset_prediction()
        if self.observed_target_center is not None:
            self.target_center = self._predict_target_center(self.observed_target_center)
        self._update_tracking_status()

    def _clear_targets(self) -> None:
        self.hand_draw_data = []
        self.face_draw_data = []
        self.observed_target_center = None
        self.target_center = None
        self.target_label = ""
        self._reset_prediction()
        self.target_count.set(0)

    def _reset_prediction(self) -> None:
        self.previous_observed_target_center = None
        self.previous_target_time = None
        self.target_velocity = (0.0, 0.0)

    def _ensure_face_cascade(self) -> bool:
        if cv2 is None:
            return False
        if self.face_cascade is not None and not self.face_cascade.empty():
            return True

        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(str(cascade_path))
        return not self.face_cascade.empty()

    def _ensure_landmarker(self) -> bool:
        if mp is None:
            self._update_detection_status()
            return False
        if self.landmarker is not None:
            return True
        if mp is None or not HAND_MODEL_PATH.exists():
            self._update_detection_status()
            return False

        base_options = mp.tasks.BaseOptions(model_asset_path=str(HAND_MODEL_PATH))
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        return True

    def _process_detection(self, frame) -> None:
        target = self.tracking_target.get()
        if target == "Rien":
            self._clear_targets()
            return

        self.frame_index += 1
        if self.frame_index % DETECT_EVERY_FRAMES != 0:
            self._draw_current_target(frame)
            return

        if target == "Main":
            self._process_hand_detection(frame)
        elif target == "Tete":
            self._process_head_detection(frame)

        self._update_tracking_status()
        self._draw_current_target(frame)

    def _process_hand_detection(self, frame) -> None:
        if not self._ensure_landmarker():
            return

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp_ms = int(time.perf_counter() * 1000)
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        self.hand_draw_data = []
        self.face_draw_data = []
        for index, hand_landmarks in enumerate(result.hand_landmarks):
            label = "Main"
            if index < len(result.handedness) and result.handedness[index]:
                label = result.handedness[index][0].category_name
            self.hand_draw_data.append((hand_landmarks, label))

        self._set_observed_target(self._select_hand_target(), "Main")
        self.target_count.set(len(self.hand_draw_data))
        self.detection_status.set("Verrouillage" if self.hand_draw_data else "Recherche")

    def _process_head_detection(self, frame) -> None:
        if not self._ensure_face_cascade():
            self._update_detection_status()
            return

        self.hand_draw_data = []
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray_frame,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
        )
        self.face_draw_data = [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
        self._set_observed_target(self._select_head_target(), "Tete")
        self.target_count.set(len(self.face_draw_data))
        self.detection_status.set("Verrouillage" if self.face_draw_data else "Recherche")

    def _set_observed_target(self, observed_center, label: str) -> None:
        self.observed_target_center = observed_center
        if observed_center is None:
            self.target_center = None
            self.target_label = ""
            self._reset_prediction()
            return

        now = time.perf_counter()
        if self.previous_observed_target_center is not None and self.previous_target_time is not None:
            elapsed = now - self.previous_target_time
            if 0.0 < elapsed < 1.0:
                previous_x, previous_y = self.previous_observed_target_center
                self.target_velocity = (
                    (observed_center[0] - previous_x) / elapsed,
                    (observed_center[1] - previous_y) / elapsed,
                )

        self.previous_observed_target_center = observed_center
        self.previous_target_time = now
        self.target_center = self._predict_target_center(observed_center)
        self.target_label = label

    def _predict_target_center(self, observed_center):
        if not self.prediction_enabled.get():
            return observed_center

        try:
            prediction_ms = int(self.prediction_ms.get())
        except tk.TclError:
            prediction_ms = DEFAULT_PREDICTION_MS
            self.prediction_ms.set(prediction_ms)

        prediction_ms = max(0, min(prediction_ms, MAX_PREDICTION_MS))
        self.prediction_ms.set(prediction_ms)
        horizon_seconds = prediction_ms / 1000.0
        velocity_x, velocity_y = self.target_velocity
        predicted_x = observed_center[0] + int(velocity_x * horizon_seconds)
        predicted_y = observed_center[1] + int(velocity_y * horizon_seconds)
        return (
            max(0, min(VIDEO_WIDTH - 1, predicted_x)),
            max(0, min(VIDEO_HEIGHT - 1, predicted_y)),
        )

    def _select_hand_target(self):
        best_center = None
        best_area = 0
        for hand_landmarks, _label in self.hand_draw_data:
            points = [
                self._landmark_to_pixel(landmark, VIDEO_WIDTH, VIDEO_HEIGHT)
                for landmark in hand_landmarks
            ]
            x_values = [point[0] for point in points]
            y_values = [point[1] for point in points]
            area = (max(x_values) - min(x_values)) * (max(y_values) - min(y_values))
            if area > best_area:
                best_area = area
                best_center = (
                    (min(x_values) + max(x_values)) // 2,
                    (min(y_values) + max(y_values)) // 2,
                )
        return best_center

    def _select_head_target(self):
        if not self.face_draw_data:
            return None
        x, y, width, height = max(
            self.face_draw_data,
            key=lambda face: face[2] * face[3],
        )
        return (x + (width // 2), y + (height // 2))

    def _draw_current_target(self, frame) -> None:
        if self.tracking_target.get() == "Main":
            self._draw_hands(frame)
        elif self.tracking_target.get() == "Tete":
            self._draw_heads(frame)

    def _draw_hands(self, frame) -> None:
        for hand_landmarks, label in self.hand_draw_data:
            self._draw_hand_overlay(frame, hand_landmarks, label)

    def _draw_heads(self, frame) -> None:
        for x, y, width, height in self.face_draw_data:
            cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 220, 0), 2)
            cv2.rectangle(frame, (x, max(0, y - 28)), (x + 95, y), (0, 220, 0), -1)
            cv2.putText(
                frame,
                "Tete",
                (x + 6, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )

    def _draw_hand_overlay(self, frame, hand_landmarks, label: str) -> None:
        height, width = frame.shape[:2]
        points = [self._landmark_to_pixel(landmark, width, height) for landmark in hand_landmarks]

        for connection in mp.tasks.vision.HandLandmarksConnections.HAND_CONNECTIONS:
            start = points[connection.start]
            end = points[connection.end]
            cv2.line(frame, start, end, (255, 180, 0), 2, cv2.LINE_AA)

        for point in points:
            cv2.circle(frame, point, 4, (0, 220, 0), -1)

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        x1 = max(min(x_values) - 20, 0)
        y1 = max(min(y_values) - 20, 0)
        x2 = min(max(x_values) + 20, width - 1)
        y2 = min(max(y_values) + 20, height - 1)

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.rectangle(frame, (x1, max(0, y1 - 28)), (x1 + 120, y1), (0, 220, 0), -1)
        cv2.putText(
            frame,
            label,
            (x1 + 6, y1 - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        cv2.circle(frame, (center_x, center_y), 5, (0, 220, 0), -1)

    def _draw_lockon_overlay(self, frame) -> None:
        center_x = VIDEO_WIDTH // 2
        center_y = VIDEO_HEIGHT // 2
        color = (0, 220, 0) if self.target_center is not None else (0, 180, 255)

        cv2.line(frame, (center_x - 24, center_y), (center_x + 24, center_y), color, 1)
        cv2.line(frame, (center_x, center_y - 24), (center_x, center_y + 24), color, 1)
        cv2.putText(
            frame,
            f"Cibles: {self.target_count.get()}",
            (18, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        if (
            self.prediction_enabled.get()
            and self.observed_target_center is not None
            and self.target_center is not None
            and self.observed_target_center != self.target_center
        ):
            cv2.circle(frame, self.observed_target_center, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.line(frame, self.observed_target_center, self.target_center, color, 1, cv2.LINE_AA)
        if self.target_center is not None:
            cv2.circle(frame, self.target_center, 8, color, 2, cv2.LINE_AA)
            if self.target_label:
                cv2.putText(
                    frame,
                    self.target_label,
                    (self.target_center[0] + 12, self.target_center[1] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                    cv2.LINE_AA,
                )

    @staticmethod
    def _landmark_to_pixel(landmark, width: int, height: int) -> tuple[int, int]:
        x = min(max(int(landmark.x * width), 0), width - 1)
        y = min(max(int(landmark.y * height), 0), height - 1)
        return x, y

    def center(self) -> None:
        self.pos_x.set(0)
        self.pos_y.set(0)
        self._send_position()

    def apply_speed(self) -> None:
        speed = max(SPEED_MIN, min(int(self.speed_input.get()), SPEED_MAX))
        self.speed_input.set(speed)
        self.applied_speed.set(speed)
        self.status.set(f"Vitesse appliquee: {speed}")

    def _press(self, direction: str) -> None:
        self.active_directions.add(direction)

    def _release(self, direction: str) -> None:
        self.active_directions.discard(direction)

    def _tick(self) -> None:
        if self.active_directions:
            if self.tracking_target.get() != "Rien":
                self.tracking_status.set("Pause manuel")
            step = max(SPEED_MIN, min(int(self.applied_speed.get()), SPEED_MAX))
            x = self.pos_x.get()
            y = self.pos_y.get()

            if "UP" in self.active_directions:
                x += step
            if "DOWN" in self.active_directions:
                x -= step
            if "LEFT" in self.active_directions:
                y -= step
            if "RIGHT" in self.active_directions:
                y += step

            self.pos_x.set(max(POSITION_MIN, min(POSITION_MAX, x)))
            self.pos_y.set(max(POSITION_MIN, min(POSITION_MAX, y)))
            self._send_position()
        elif self.tracking_target.get() != "Rien":
            self._apply_tracking()

        self.root.after(TICK_MS, self._tick)

    def _apply_tracking(self) -> None:
        if self.tracking_target.get() == "Rien" or self.target_center is None:
            self._update_tracking_status()
            return

        target_x, target_y = self.target_center
        offset_x = target_x - (VIDEO_WIDTH // 2)
        offset_y = target_y - (VIDEO_HEIGHT // 2)

        correction_y = self._tracking_correction(offset_x)
        correction_x = self._tracking_correction(-offset_y)

        if correction_x == 0 and correction_y == 0:
            self.tracking_status.set("Cible centree")
            return

        next_x = self._clamp_position(self.pos_x.get() + correction_x)
        next_y = self._clamp_position(self.pos_y.get() + correction_y)

        if next_x == self.pos_x.get() and next_y == self.pos_y.get():
            self.tracking_status.set("Limite servo")
            return

        self.pos_x.set(next_x)
        self.pos_y.set(next_y)
        self.tracking_status.set("Suivi pred" if self.prediction_enabled.get() else "Suivi actif")
        self._send_position()

    def _tracking_correction(self, offset: int) -> int:
        deadzone = max(0, int(self.tracking_deadzone.get()))
        if abs(offset) <= deadzone:
            return 0

        speed_multiplier = TRACKING_SPEED_MULTIPLIERS.get(self.tracking_speed_mode.get(), 1.0)
        max_step = max(SPEED_MIN, min(int(self.applied_speed.get() * speed_multiplier), SPEED_MAX))
        gain = max(1, int(self.tracking_gain_percent.get())) / 100.0
        correction = int(offset * gain * speed_multiplier)
        if correction == 0:
            correction = 1 if offset > 0 else -1
        return max(-max_step, min(max_step, correction))

    @staticmethod
    def _clamp_position(position: int) -> int:
        return max(POSITION_MIN, min(POSITION_MAX, position))

    def _send_position(self) -> None:
        command = f"POS {self.pos_x.get()} {self.pos_y.get()}\n"
        if self.serial_link is None or not self.serial_link.is_open:
            self.status.set(f"Simulation: {command.strip()}")
            return

        try:
            self.serial_link.write(command.encode("ascii"))
            serial_reply = self._read_serial_reply()
            if serial_reply:
                self.status.set(serial_reply)
            else:
                self.status.set(f"Envoye: {command.strip()}")
        except serial.SerialException as exc:
            self.status.set(f"Erreur serie: {exc}")
            self.disconnect()

    def _read_serial_reply(self) -> str:
        if self.serial_link is None or not self.serial_link.is_open:
            return ""

        replies = []
        first_line = self.serial_link.readline().decode("ascii", errors="replace").strip()
        if first_line:
            replies.append(first_line)

        while self.serial_link.in_waiting:
            line = self.serial_link.readline().decode("ascii", errors="replace").strip()
            if line:
                replies.append(line)
        return replies[-1] if replies else ""

    def close(self) -> None:
        self.disconnect()
        self.stop_camera()
        if self.landmarker is not None:
            self.landmarker.close()
            self.landmarker = None
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = LockonGui(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
