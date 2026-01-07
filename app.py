import os
import shutil
import cv2
import uuid
import asyncio
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, WebSocket, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

# --- Configuration ---
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("extracted_frames")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FrameExtractor")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/frames", StaticFiles(directory=OUTPUT_DIR), name="frames")
templates = Jinja2Templates(directory="templates")

# --- Utils ---
def get_blur_score(image):
    """Calculates the variance of the Laplacian. Higher = Sharper."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws/process")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        # 1. Receive Configuration
        data = await websocket.receive_json()
        video_filename = data.get("filename")
        mode = data.get("mode", "interval") # interval, count, every_n
        value = float(data.get("value", 1)) # seconds, count, or n-frames
        blur_threshold = float(data.get("blur_threshold", 0)) # 0 = off
        
        video_path = UPLOAD_DIR / video_filename
        if not video_path.exists():
            await websocket.send_json({"status": "error", "message": "Video file not found."})
            return

        # Prepare output directory
        session_id = str(uuid.uuid4())[:8]
        session_dir = OUTPUT_DIR / f"job_{session_id}"
        session_dir.mkdir(exist_ok=True)
        
        # Open Video
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            await websocket.send_json({"status": "error", "message": "Could not open video."})
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30.0 # Fallback
        
        duration = total_frames / fps
        
        await websocket.send_json({
            "status": "info", 
            "message": f"Video loaded. {total_frames} frames, {fps:.2f} FPS, {duration:.2f}s."
        })

        # Calculate frames to extract
        frames_to_process = []
        
        if mode == "interval":
            # Extract every X seconds
            step_frames = int(value * fps)
            if step_frames < 1: step_frames = 1
            frames_to_process = range(0, total_frames, step_frames)
            
        elif mode == "count":
            # Extract exactly X frames (distributed evenly)
            target_count = int(value)
            if target_count > total_frames: target_count = total_frames
            if target_count < 1: target_count = 1
            step = total_frames / target_count
            frames_to_process = [int(i * step) for i in range(target_count)]
            
        elif mode == "every_n":
            # Extract every Nth frame
            step_frames = int(value)
            if step_frames < 1: step_frames = 1
            frames_to_process = range(0, total_frames, step_frames)

        # Processing Loop
        extracted_count = 0
        processed_count = 0
        total_tasks = len(frames_to_process)
        
        # Optimization: We can't jump randomly efficiently in all codecs, 
        # but setting CAP_PROP_POS_FRAMES is better than reading all.
        
        for target_frame_idx in frames_to_process:
            # Check if client disconnected
            # (Websocket receive with timeout is tricky, assuming connection stays open)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
            ret, frame = cap.read()
            
            if not ret:
                break
                
            # Blur Detection
            is_good = True
            score = 0
            if blur_threshold > 0:
                score = get_blur_score(frame)
                if score < blur_threshold:
                    is_good = False
            
            if is_good:
                out_name = f"frame_{target_frame_idx:06d}.jpg"
                out_path = session_dir / out_name
                cv2.imwrite(str(out_path), frame)
                extracted_count += 1
                
                # Send update
                await websocket.send_json({
                    "status": "progress",
                    "progress": (processed_count + 1) / total_tasks * 100,
                    "extracted": extracted_count,
                    "latest_image": f"/frames/job_{session_id}/{out_name}",
                    "score": score
                })
            else:
                # Send skip notice (optional, maybe just update progress)
                 await websocket.send_json({
                    "status": "skipped",
                    "progress": (processed_count + 1) / total_tasks * 100,
                    "reason": f"Blurry (Score: {score:.1f})"
                })

            processed_count += 1
            # Yield control briefly to allow event loop to handle messages
            await asyncio.sleep(0.001)

        cap.release()
        
        await websocket.send_json({
            "status": "complete", 
            "message": f"Done! Extracted {extracted_count} images.",
            "directory": str(session_dir.absolute())
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await websocket.send_json({"status": "error", "message": str(e)})

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    try:
        # Clean filename
        clean_name = str(uuid.uuid4()) + "_" + file.filename
        file_path = UPLOAD_DIR / clean_name
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {"filename": clean_name, "original_name": file.filename}
    except Exception as e:
        return {"error": str(e)}

@app.get("/open-folder")
def open_folder(path: str):
    """Opens the folder in the OS file explorer."""
    try:
        if os.name == 'nt':
            os.startfile(path)
        elif os.name == 'posix':
            subprocess.call(['open', path]) # MacOS
        else:
            subprocess.call(['xdg-open', path]) # Linux
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    # Clean up old uploads on start (optional)
    uvicorn.run(app, host="127.0.0.1", port=8000)
