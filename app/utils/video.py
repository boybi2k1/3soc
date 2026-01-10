import cv2
from typing import Iterator, Tuple


def extract_frames(video_path: str, sample_rate: int = 1) -> Iterator[Tuple[int, any]]:
    """
    Extract frames from video file. sample_rate=1 yields every frame,
    sample_rate=5 yields every 5th frame, etc.
    Yields tuples (frame_index, frame_bgr_numpy).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video file: {video_path}")
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % sample_rate == 0:
            yield idx, frame
        idx += 1
    cap.release()

