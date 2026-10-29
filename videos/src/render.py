import asyncio
import functools
import http.server
import io
import os
import shutil
import subprocess
import sys
import threading

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
FFMPEG = shutil.which("ffmpeg") or os.path.join(os.path.expanduser("~"), "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe")
PORT = 8811
FPS = 30
SHUTTER = 0.5


def serve():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(QuietHandler, directory=ROOT)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def open_page(browser, plan, fmt):
    width, height = (1080, 1920) if fmt == "v" else (1920, 1080)
    page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" and "Failed to load resource" not in message.text else None)
    page.on("response", lambda response: errors.append(f"{response.status} {response.url}") if response.status >= 400 and not response.url.endswith("favicon.ico") else None)
    await page.goto(f"http://127.0.0.1:{PORT}/{plan}.html?fmt={fmt}")
    duration = await page.evaluate("window.__ready")
    if errors:
        raise RuntimeError(f"{plan} {fmt}: {errors}")
    return page, duration


async def stills(browser, plan, fmt, times, out):
    page, _ = await open_page(browser, plan, fmt)
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)
    thumbs = []
    for time in times:
        await page.evaluate(f"window.seek({time})")
        image = Image.open(io.BytesIO(await page.screenshot(type="png"))).convert("RGB")
        image.thumbnail((640, 640) if fmt == "h" else (360, 640))
        tile = Image.new("RGB", (image.width, image.height + 30), (20, 20, 20))
        tile.paste(image, (0, 30))
        ImageDraw.Draw(tile).text((8, 2), f"{plan} {fmt} {time:.2f}s", font=font, fill=(255, 230, 120))
        thumbs.append(tile)
    columns = 3 if fmt == "h" else 5
    rows = (len(thumbs) + columns - 1) // columns
    tile_w, tile_h = thumbs[0].size
    sheet = Image.new("RGB", (columns * (tile_w + 6), rows * (tile_h + 6)), (0, 0, 0))
    for index, tile in enumerate(thumbs):
        sheet.paste(tile, ((index % columns) * (tile_w + 6), (index // columns) * (tile_h + 6)))
    sheet.save(out, quality=88)
    await page.close()


async def video_blur(browser, plan, fmt, out, samples):
    page, duration = await open_page(browser, plan, fmt)
    width, height = (1080, 1920) if fmt == "v" else (1920, 1080)
    frames = int(round(duration * FPS))
    process = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-framerate", str(FPS), "-i", "-",
                                "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
                               stdin=subprocess.PIPE)
    for index in range(frames):
        total = np.zeros((height, width, 3), np.float32)
        for sample in range(samples):
            await page.evaluate(f"window.seek({(index + sample / samples * SHUTTER) / FPS})")
            total += np.asarray(Image.open(io.BytesIO(await page.screenshot(type="jpeg", quality=95))).convert("RGB"), np.float32)
        process.stdin.write((total / samples + 0.5).astype(np.uint8).tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")
    await page.close()
    print(out, frames, "frames", samples, "samples", os.path.getsize(out) // 1024, "KB")


async def video(browser, plan, fmt, out):
    page, duration = await open_page(browser, plan, fmt)
    frames = int(round(duration * FPS))
    process = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                                "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
                               stdin=subprocess.PIPE)
    for index in range(frames):
        await page.evaluate(f"window.seek({index / FPS})")
        process.stdin.write(await page.screenshot(type="jpeg", quality=94))
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")
    await page.close()
    print(out, frames, "frames", os.path.getsize(out) // 1024, "KB")


async def main():
    mode = sys.argv[1]
    server = serve()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, channel="chrome", args=["--force-color-profile=srgb"])
        if mode == "stills":
            plan, fmt = sys.argv[2], sys.argv[3]
            times = [float(value) for value in sys.argv[4].split(",")]
            await stills(browser, plan, fmt, times, os.path.join(ROOT, "qc", f"{plan}_{fmt}.jpg"))
        elif mode == "blur":
            samples = int(sys.argv[2])
            for job in sys.argv[3:]:
                plan, fmt = job.split(":")
                await video_blur(browser, plan, fmt, os.path.join(ROOT, "out", f"{plan}_{fmt}.mp4"), samples)
        else:
            for job in sys.argv[2:]:
                plan, fmt = job.split(":")
                await video(browser, plan, fmt, os.path.join(ROOT, "out", f"{plan}_{fmt}.mp4"))
        await browser.close()
    server.shutdown()


asyncio.run(main())
