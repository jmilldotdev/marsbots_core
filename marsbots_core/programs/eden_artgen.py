import os
import asyncio
import uuid
import requests
import json
import io
import aiohttp
from moviepy.editor import VideoFileClip
from typing import List
from dataclasses import dataclass, field
import discord
from marsbots_core.resources.discord_utils import update_message


@dataclass
class SourceSettings:
    origin: str
    author: int
    author_name: str
    guild: int
    guild_name: str
    channel: int    
    channel_name: str

@dataclass
class EdenClipXSettings:
    text_input: str
    image_url: str = ""
    step_multiplier: float = 1.0
    color_target_pixel_fraction: float = 0.75
    color_loss_f: float = 0.0
    color_rgb_target: tuple[float] = (0.0, 0.0, 0.0)
    image_weight: float = 0.35
    n_permuted_prompts_to_add: int = -1
    width: int = 0
    height: int = 0
    num_octaves: int = 3
    octave_scale: float = 2.0
    clip_model_options: List = field(default_factory=lambda: [["ViT-B/32", "ViT-B/16", "RN50"]])
    num_iterations: tuple[int] = (100, 200, 300)


@dataclass
class StableDiffusionSettings:
    width: int
    height: int
    text_input: str
    mode: str = "generate"
    seed: int = 42 
    fixed_code: bool = False
    interpolation_texts: List = field(default_factory=lambda: [])
    n_interpolate: int = 10
    ddim_steps: int = 50
    plms: bool = False
    C: int = 4
    f: int = 8    

@dataclass
class OracleSettings:
    text_input: str



async def generation_loop(
    gateway_url,
    minio_url,
    source,
    config,
    user_message,
    bot_message,
    ctx,
    refresh_interval: int,
    gif: bool = False
):

    generator_names = {
        EdenClipXSettings: 'eden-clipx',
        StableDiffusionSettings: 'stable-diffusion',
        OracleSettings: 'oracle'
    }

    generator_name = generator_names[type(config)]
    data = {'source': source.__dict__, 'generator_name': generator_name, 'config': config.__dict__}
    result = requests.post(gateway_url+'/request_creation', json=data)

    if not await check_server_result_ok(result, bot_message):
        return

    result = json.loads(result.content)
    task_id = result['task_id']
    current_sha = None

    while True:
        result = requests.post(gateway_url+'/get_creations', json={"task": task_id})

        if not await check_server_result_ok(result, bot_message):
            return

        result = json.loads(result.content)

        if not result:
            return append_message(bot_message, "_Server error: task ID not found_")

        result = result[0]
        status = result['status']
        
        # update message string
        if status == 'failed':
            await append_message(bot_message, "_Server error: Eden task failed_")
        elif status in 'pending':
            await append_message(bot_message, "_Creation is pending_")
        elif status == 'queued':
            queue_idx = result['status_code']
            await append_message(bot_message, f"_Creation is #{queue_idx} in queue_")
        elif status == 'running':
            progress = result['status_code']
            await append_message(bot_message, f"_Creation is **{progress}%** complete_")
        elif status == 'complete':
            await append_message(bot_message, "")

        # update message image
        if status == 'complete' or 'intermediate_sha' in result:
            
            video_clip = False
            if status == 'complete':
                if 'video_sha' in result:
                    last_sha = result['video_sha']
                    video_clip = True
                else:
                    last_sha = result['sha']
            else:
                last_sha = result['intermediate_sha'][-1]
            
            if last_sha != current_sha:
                current_sha = last_sha
                
                if video_clip:
                    await append_message(bot_message, "_Creation is finished. Making GIF..._")

                    sha_url = f'{minio_url}/{current_sha}.mp4'
                    sha_mp4 = sha_url.split('/')[-1]
                    
                    if gif:
                        sha_gif = sha_mp4.replace('.mp4', '.gif')
                        res = requests.get(sha_url)
                        with open(sha_mp4, "wb") as f:
                            f.write(res.content)
                        VideoFileClip(sha_mp4).write_gif(sha_gif)
                        discord_file = discord.File(sha_gif, sha_gif)                        
                        if os.path.isfile(sha_mp4):
                            os.remove(sha_mp4)
                        if os.path.isfile(sha_gif):
                            os.remove(sha_gif)
                    
                    else:
                        discord_file = await get_discord_file_from_url(sha_url, sha_mp4)
                    
                    await append_message(bot_message, "")
                    
                    try:
                        await update_image(bot_message, discord_file)
                    except:
                        await append_message(bot_message, "GIF attachment failed... :(")

                else:
                    sha_url = f'{minio_url}/{current_sha}'
                    filename = f'{current_sha}.png'
                    discord_file = await get_discord_file_from_url(sha_url, filename)
                    await update_image(bot_message, discord_file)

        if status not in ['queued', 'pending', 'running']:
            break

        await asyncio.sleep(refresh_interval)


def appender(message, suffix):
    return message.split("\n")[0] + "\n\n" + suffix


async def append_message(message, message_suffix):
    message_content = appender(message.content, message_suffix)
    await update_message(message, content=message_content)


async def update_image(message, image):
    await update_message(message, files=[image])


async def get_discord_file_from_url(url, filename):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = io.BytesIO(await resp.read())
            discord_file = discord.File(data, filename)
            return discord_file


async def check_server_result_ok(result, bot_message):
    if result.status_code != 200:
        error_message = result.content.decode("utf-8")
        await append_message(bot_message, f"_Server error: {error_message}_")
    return result.status_code == 200
