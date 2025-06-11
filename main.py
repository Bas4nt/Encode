import os
import subprocess
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, FileTooLarge
import time
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize Pyrogram client
app = Client(
    "VideoEncoderBot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("TELEGRAM_TOKEN")
)

# Directory for temporary files
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# FFmpeg command for HEVC encoding
FFMPEG_CMD = (
    "ffmpeg -i {input} -c:v libx265 -crf 23 -preset medium -c:a copy {output}"
)

# Maximum file size (2GB for Telegram)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes

async def check_video_info(file_path):
    """Check video duration and codec using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration,codec_name",
            "-of", "json", file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        info = eval(result.stdout.replace("true", "True").replace("false", "False"))
        duration = float(info.get("format", {}).get("duration", 0))
        codec = info.get("streams", [{}])[0].get("codec_name", "")
        return duration, codec
    except Exception as e:
        logger.error(f"Error checking video info: {e}")
        return 0, None

async def get_encoding_progress(file_path, total_duration, message):
    """Provide encoding progress updates."""
    output_file = file_path.replace(".mp4", "_encoded.mp4")
    while os.path.exists(file_path):
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", output_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            info = eval(result.stdout.replace("true", "True").replace("false", "False"))
            current_duration = float(info.get("format", {}).get("duration", 0))
            progress = min(int((current_duration / total_duration) * 100), 100)
            await message.edit_text(f"Encoding: {progress}% complete")
            await asyncio.sleep(5)
        except Exception:
            await asyncio.sleep(5)

async def encode_video(input_path, output_path, message):
    """Encode video to HEVC using FFmpeg."""
    cmd = FFMPEG_CMD.format(input=input_path, output=output_path)
    try:
        duration, codec = await check_video_info(input_path)
        if not duration:
            await message.edit_text("Error: Invalid video file.")
            return False
        if codec == "hevc":
            await message.edit_text("Video is already in HEVC format. No encoding needed.")
            return False

        # Start progress tracking
        progress_task = asyncio.create_task(get_encoding_progress(input_path, duration, message))

        # Run FFmpeg
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        progress_task.cancel()

        if process.returncode != 0:
            await message.edit_text("Error during encoding. Please try again.")
            logger.error(f"FFmpeg error: {process.stderr}")
            return False
        return True
    except Exception as e:
        await message.edit_text("Error during encoding. Please try again.")
        logger.error(f"Encoding error: {e}")
        return False

async def cleanup_files(*files):
    """Delete temporary files."""
    for file in files:
        if os.path.exists(file):
            os.remove(file)
            logger.info(f"Deleted temporary file: {file}")

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Handle /start command."""
    await message.reply_text(
        "Welcome to the Video Encoder Bot! 🎥\n"
        "Send a video file (up to 2GB) or a video URL to compress it to HEVC (H.265).\n"
        "Use /encode to start encoding manually."
    )

@app.on_message(filters.video | filters.command("encode"))
async def handle_video(client, message):
    """Handle video files or /encode command."""
    try:
        # Check if it's a video file
        if message.video:
            file_size = message.video.file_size
            if file_size > MAX_FILE_SIZE:
                await message.reply_text("Error: Video exceeds 2GB limit.")
                return

            # Download video
            status = await message.reply_text("Downloading video...")
            file_path = os.path.join(TEMP_DIR, f"{message.video.file_id}.mp4")
            await message.download(file_path)
            await status.edit_text("Download complete. Checking video...")

            # Check file size after download
            if os.path.getsize(file_path) > MAX_FILE_SIZE:
                await status.edit_text("Error: Downloaded video exceeds 2GB limit.")
                await cleanup_files(file_path)
                return

            # Encode video
            output_path = file_path.replace(".mp4", "_encoded.mp4")
            await status.edit_text("Encoding started...")
            success = await encode_video(file_path, output_path, status)

            if not success:
                await cleanup_files(file_path, output_path)
                return

            # Upload encoded video
            await status.edit_text("Encoding complete. Uploading...")
            try:
                await client.send_video(
                    chat_id=message.chat.id,
                    video=output_path,
                    caption="Encoded video (HEVC)",
                    reply_to_message_id=message.id
                )
                await status.edit_text("Upload complete!")
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await client.send_video(
                    chat_id=message.chat.id,
                    video=output_path,
                    caption="Encoded video (HEVC)",
                    reply_to_message_id=message.id
                )
                await status.edit_text("Upload complete!")
            except FileTooLarge:
                await status.edit_text("Error: Encoded video exceeds 2GB limit.")
            finally:
                await cleanup_files(file_path, output_path)

        elif message.text and message.text.startswith("/encode"):
            await message.reply_text("Please send a video file to encode.")
        else:
            await message.reply_text("Please send a video file or use /encode with a video.")

    except Exception as e:
        await message.reply_text("An error occurred. Please try again.")
        logger.error(f"Error handling video: {e}")

# Run the bot
if __name__ == "__main__":
    logger.info("Starting Video Encoder Bot...")
    app.run()
