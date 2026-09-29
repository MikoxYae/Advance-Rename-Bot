from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, BotCommand

from config import Config
from helper.database import settings_db


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
    await settings_db.ensure_user(message.from_user.id)
    await message.reply_photo(
        photo=Config.SETTINGS_PIC,
        caption=START_TEXT,
        reply_markup=start_keyboard(),
    )
