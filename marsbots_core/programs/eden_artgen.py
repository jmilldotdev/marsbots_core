import time
import uuid

import discord

from marsbots_core.resources.discord_utils import update_message


async def generation_loop(client, token, message, ctx, refresh_interval: int):
    task_id = str(uuid.uuid4())
    finished = False
    last_image = None
    while not finished:
        result = client.fetch(token=token)
        status = result["status"]["status"]
        if status == "complete":
            filepath = f"{task_id}-testimage.png"
            output_img = result["output"]["creation"]
            output_img.save(filepath)
            finished = True
            async with ctx.channel.typing():
                local_file = discord.File(filepath, filename=filepath)
                await message.reply("result", file=local_file)

        elif status == "failed":
            finished = True
            async with ctx.channel.typing():
                await message.reply("Something went wrong :(")
        else:
            progress = result["status"].get("progress")
            latest_image = result["config"]["data"].get("progress_image")

            if progress:
                update_progress(message, progress)

            if latest_image and latest_image != last_image:
                update_image(message, latest_image)
                last_image = latest_image

            time.sleep(refresh_interval)


async def update_progress(message, progress):
    message_content = f"Generation is {progress*100}% complete"
    await update_message(message, content=message_content)


async def update_image(message, image):
    await update_message(message, [image])
