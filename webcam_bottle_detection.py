import argparse
import sys
import time

import cv2

try:
    import mediapipe as mp
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "Le package 'mediapipe' est manquant. Installe les dependances avec :\n"
        "python -m pip install -r requirements.txt"
    ) from exc


WINDOW_NAME = "LOCKON - Webcam Hand Detection"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Affiche le flux webcam et les boites de detection des mains."
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Index de la webcam a utiliser (defaut: 0).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Largeur demandee a la webcam (defaut: 1280).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        help="Hauteur demandee a la webcam (defaut: 720).",
    )
    parser.add_argument(
        "--camera-fps",
        type=int,
        default=30,
        help="FPS demandes a la webcam (defaut: 30).",
    )
    parser.add_argument(
        "--process-width",
        type=int,
        default=640,
        help="Largeur utilisee pour la detection (defaut: 640).",
    )
    parser.add_argument(
        "--process-height",
        type=int,
        default=360,
        help="Hauteur utilisee pour la detection (defaut: 360).",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=1600,
        help="Largeur initiale de la fenetre OpenCV (defaut: 1600).",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=900,
        help="Hauteur initiale de la fenetre OpenCV (defaut: 900).",
    )
    parser.add_argument(
        "--max-hands",
        type=int,
        default=2,
        help="Nombre maximum de mains a detecter (defaut: 2).",
    )
    parser.add_argument(
        "--min-detection-confidence",
        type=float,
        default=0.5,
        help="Seuil minimal pour detecter une main (defaut: 0.5).",
    )
    parser.add_argument(
        "--min-tracking-confidence",
        type=float,
        default=0.5,
        help="Seuil minimal pour suivre une main (defaut: 0.5).",
    )
    parser.add_argument(
        "--model-path",
        default="hand_landmarker.task",
        help="Chemin local du modele MediaPipe (defaut: hand_landmarker.task).",
    )
    parser.add_argument(
        "--detect-every",
        type=int,
        default=1,
        help="Effectue la detection une frame sur N et reutilise le dernier resultat (defaut: 1).",
    )
    parser.add_argument(
        "--no-detect",
        action="store_true",
        help="Affiche uniquement le flux webcam pour mesurer le FPS sans detection.",
    )
    return parser.parse_args()


def ensure_model(model_path: str) -> str:
    import urllib.request
    from pathlib import Path

    path = Path(model_path)
    if path.exists():
        return str(path)

    print(f"Telechargement du modele de main vers '{path}'...")
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(MODEL_URL, path)
    return str(path)


def open_camera(index: int, width: int, height: int, fps: int) -> cv2.VideoCapture:
    camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not camera.isOpened():
        camera = cv2.VideoCapture(index)

    if not camera.isOpened():
        raise RuntimeError(
            f"Impossible d'ouvrir la webcam a l'index {index}. "
            "Verifie l'index ou qu'aucune autre application ne l'utilise."
        )

    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    camera.set(cv2.CAP_PROP_FPS, fps)
    return camera


def landmark_to_pixel(landmark, width: int, height: int) -> tuple[int, int]:
    x = min(max(int(landmark.x * width), 0), width - 1)
    y = min(max(int(landmark.y * height), 0), height - 1)
    return x, y


def draw_hand_overlay(frame, hand_landmarks, handedness_label: str) -> None:
    height, width = frame.shape[:2]
    points = [landmark_to_pixel(landmark, width, height) for landmark in hand_landmarks]

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
    cv2.rectangle(frame, (x1, max(0, y1 - 28)), (x1 + 110, y1), (0, 220, 0), -1)
    cv2.putText(
        frame,
        handedness_label,
        (x1 + 6, y1 - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )

    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    cv2.circle(frame, (center_x, center_y), 4, (0, 220, 0), -1)


def draw_hud(frame, hand_count: int, fps: float, camera_fps: float) -> None:
    height, width = frame.shape[:2]
    center_x = width // 2
    center_y = height // 2

    cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y), (0, 180, 255), 1)
    cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20), (0, 180, 255), 1)

    status = f"Mains detectees: {hand_count}"
    cv2.putText(
        frame,
        status,
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "CPU",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"FPS: {fps:.1f}",
        (20, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"Cam FPS: {camera_fps:.1f}",
        (20, 140),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "Q pour quitter",
        (20, height - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def extract_hand_draw_data(result) -> list[tuple[list, str]]:
    hands = []
    for index, hand_landmarks in enumerate(result.hand_landmarks):
        handedness_label = "Main"
        if index < len(result.handedness) and result.handedness[index]:
            handedness_label = result.handedness[index][0].category_name
        hands.append((hand_landmarks, handedness_label))
    return hands


def main() -> int:
    args = parse_args()
    model_path = ensure_model(args.model_path)

    camera = open_camera(args.camera_index, args.width, args.height, args.camera_fps)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, args.window_width, args.window_height)
    reported_camera_fps = camera.get(cv2.CAP_PROP_FPS)
    print(f"FPS webcam demandes: {args.camera_fps}")
    print(f"FPS webcam annonces: {reported_camera_fps:.1f}")

    base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=args.max_hands,
        min_hand_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
    )

    detect_every = max(args.detect_every, 1)
    hand_draw_data = []

    with mp.tasks.vision.HandLandmarker.create_from_options(options) as landmarker:
        frame_index = 0
        previous_time = time.perf_counter()
        smoothed_fps = 0.0
        try:
            while True:
                ok, frame = camera.read()
                if not ok:
                    print("Lecture webcam impossible, arret du programme.", file=sys.stderr)
                    return 1

                frame = cv2.flip(frame, 1)
                current_time = time.perf_counter()
                if not args.no_detect and frame_index % detect_every == 0:
                    processing_frame = cv2.resize(
                        frame,
                        (args.process_width, args.process_height),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    rgb_frame = cv2.cvtColor(processing_frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    timestamp_ms = int(current_time * 1000)
                    result = landmarker.detect_for_video(mp_image, timestamp_ms)
                    hand_draw_data = extract_hand_draw_data(result)
                frame_index += 1

                instant_fps = 1.0 / max(current_time - previous_time, 1e-6)
                previous_time = current_time
                if smoothed_fps == 0.0:
                    smoothed_fps = instant_fps
                else:
                    smoothed_fps = (0.9 * smoothed_fps) + (0.1 * instant_fps)

                hand_count = 0
                for hand_landmarks, handedness_label in hand_draw_data:
                    draw_hand_overlay(frame, hand_landmarks, handedness_label)
                    hand_count += 1

                draw_hud(frame, hand_count, smoothed_fps, reported_camera_fps)
                cv2.imshow(WINDOW_NAME, frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
        finally:
            camera.release()
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
