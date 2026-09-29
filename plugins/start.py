from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import settings_db
from helper.buttons import send_photo_styled


START_TEXT = (
    "<b>ᴀᴅᴠᴀɴᴄᴇ ʀᴇɴᴀᴍᴇ ʙᴏᴛ</b>\n\n"
    "<blockquote>ʀᴇɴᴀᴍᴇ ʏᴏᴜʀ ғɪʟᴇs ᴡɪᴛʜ ʏᴏᴜʀ sᴀᴠᴇᴅ sᴇᴛᴛɪɴɢs.</blockquote>\n\n"
    "<b>ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ᴛᴏ ᴄᴏɴғɪɢᴜʀᴇ ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ, ᴄᴀᴘᴛɪᴏɴ, "
    "ᴛʜᴜᴍʙɴᴀɪʟ, ᴍᴇᴅɪᴀ ᴛʏᴘᴇ ᴀɴᴅ ᴍᴇᴛᴀᴅᴀᴛᴀ.</b>\n\n"
    "<blockquote>ғɪʟᴇs sᴇɴᴅ ᴋʀᴏ → ǫᴜᴇᴜᴇ ʙᴀɴᴇɢɪ → /done sᴇ ᴘʀᴏᴄᴇssɪɴɢ sᴛᴀʀᴛ.</blockquote>"
)


def start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("sᴇᴛᴛɪɴɢs", callback_data="settings:home")]
    ])


@Client.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user = await settings_db.get_user(message.from_user.id)
    markup = start_keyboard()
    photo = user.get("ui_start_pic") or Config.SETTINGS_PIC
    try:
        await send_photo_styled(client, message, photo, START_TEXT, markup)
    except Exception:
        # Decorative UI must never make /start unusable.
        await message.reply_photo(photo=photo, caption=START_TEXT, reply_markup=markup)
