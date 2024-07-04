import suno
import requests
import random
import time
from typing import Optional

class CustomSunoClient(suno.Client):
    def __init__(self, cookie: str, impersonate: str = "chrome") -> None:
        super().__init__(cookie)
        self.impersonate = impersonate

    def request(self, *args, **kwargs) -> requests.Response:
        kwargs["impersonate"] = kwargs.get("impersonate", self.impersonate)
        return self._session.request(*args, **kwargs)

# Define the rest of your necessary imports and logic here...
import os
import streamlit as st
from mutagen.mp3 import MP3
from moviepy.editor import ImageClip
import openai
import anthropic
import requests

# Access environment variables
suno_cookie = os.getenv('SUNO_COOKIE')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
openai_api_key = os.getenv('OPENAI_API_KEY')

# Initialize clients with environment variables
client = CustomSunoClient(cookie=suno_cookie, impersonate="firefox")  # Example with "firefox"
client2 = anthropic.Anthropic(api_key=anthropic_api_key)
client_open = openai.OpenAI(api_key=openai_api_key)

# The rest of your Streamlit app code remains the same...

# Convert transcription data to SRT format
def convert_to_srt(transcription_data):
    srt_content = ""
    words_group = []  # To store groups of words
    for i, item in enumerate(transcription_data):
        words_group.append(item)
        if len(words_group) == 4 or i == len(transcription_data) - 1:  # Group words by 4 or the last group
            start_time = words_group[0]['start']
            end_time = words_group[-1]['end']
            words_text = ' '.join([word['word'] for word in words_group])
            srt_index = len(srt_content.split('\n\n')) + 1

            # Format the times for SRT
            start_srt = f"{int(start_time // 3600):02}:{int(start_time % 3600 // 60):02}:{int(start_time % 60):02},{int(start_time % 1 * 1000):03}"
            end_srt = f"{int(end_time // 3600):02}:{int(end_time % 3600 // 60):02}:{int(end_time % 60):02},{int(end_time % 1 * 1000):03}"

            srt_content += f"{srt_index}\n{start_srt} --> {end_srt}\n{words_text}\n\n"
            words_group = []  # Reset for the next group

    return srt_content

# Generate lyric song video
def generate_lyric_video(song_prompt, style_prompt):
    try:
        # Generate lyrics
        message = client2.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=2132,
            temperature=0.5,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Generate lyrics for this song: " + song_prompt + ". Only give me the lyrics, nothing else. Start with Lyrics:"
                        }
                    ]
                }
            ]
        )
        lyrics = message.content[0].text
        lyrics = lyrics.split("Lyrics:", 1)[-1].strip()

        clips = client.songs.generate(
            lyrics,
            custom=True,
            tags=style_prompt,
            instrumental=False,
        )
        time.sleep(100)
        clip_id = clips[1]['id']
        clip = client.songs.get(clip_id)
        song_url = clip['audio_url']
        print(song_url)

        r = requests.get(song_url)
        with open("downloaded_speech.mp3", "wb") as audio_file:
            audio_file.write(r.content)

        # Now, open the downloaded file for transcription
        audio_file = open("downloaded_speech.mp3", "rb")
        transcript = client_open.audio.transcriptions.create(
            file=audio_file,
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )

        # Print the words from the transcript
        print(transcript.words)

        audio_file.close()

        # Load the MP3 file
        audio = MP3("downloaded_speech.mp3")

        # Get the duration of the MP3 file in seconds
        duration_seconds = audio.info.length

        # Round the duration to the nearest second
        rounded_duration = round(duration_seconds)

        audio_duration = rounded_duration

        # Get image generation prompt and image
        response = client_open.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": f"Give me a short album cover description of the song: {song_prompt} no words in the album cover"},
            ]
        )
        print(response.choices[0].message.content)
        image_design = response.choices[0].message.content

        # Using DALL-E 3 API to generate image
        response = client_open.images.generate(
            model="dall-e-3",
            prompt=image_design,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        response = requests.get(image_url)
        with open("background.jpg", "wb") as img_file:
            img_file.write(response.content)

        # Generate SRT content
        transcription_data = transcript.words
        srt_content = convert_to_srt(transcription_data)

        # Save the SRT content to a file
        with open("subtitles.srt", "w") as srt_file:
            srt_file.write(srt_content)

        scale_cmd = [
            "ffmpeg", "-i", "background.jpg", "-vf",   # Ensure ffmpeg is added to your system path
            "scale='if(gt(a,16/9),1080,-2)':'if(gt(a,16/9),-2,1034)'", "-y",
            "background_even.jpg"
        ]
        subprocess.run(scale_cmd, check=True)

        # Create a video from the background image
        create_video_cmd = [
            "ffmpeg", "-loop", "1", "-i", "background_even.jpg",
            "-i", "downloaded_speech.mp3", "-c:v", "libx264", "-tune",
            "stillimage", "-c:a", "aac", "-b:a", "192k", "-pix_fmt",
            "yuv420p", "-t", str(audio_duration), "-shortest", "temp_video.mp4"
        ]
        subprocess.run(create_video_cmd, check=True)

        # Add subtitles to the video
        add_subtitles_cmd = [
            "ffmpeg", "-i", "temp_video.mp4", "-vf",
            "subtitles=subtitles.srt:force_style='Alignment=10,MarginL=0,MarginR=0,MarginV=20'",
            "-c:a", "copy", "final_video_with_subtitles.mp4"
        ]
        subprocess.run(add_subtitles_cmd, check=True)

        return "final_video_with_subtitles.mp4"
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None

# Streamlit UI
st.title('Lyric Video Generator')

song_prompt = st.text_input("Song Prompt", "Generate whatever song you want")
style_prompt = st.text_input("Style Prompt", "Any style you want")

if st.button('Generate Lyric Video'):
    with st.spinner('Generating Video...'):
        video_path = generate_lyric_video(song_prompt, style_prompt)
        if video_path:
            st.video(video_path)