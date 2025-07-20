import os
import asyncio
import shutil
import zipfile
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ContentType, ParseMode
from aiogram.types import Message, Document
from aiogram.fsm.storage.memory import MemoryStorage
from colorama import init

from telethon import functions
from telethon.errors import RPCError
from opentele.tl.telethon import TelegramClient as OpenteleClient
from opentele.api import API

# ===== INIT =====
init(autoreset=True)

# ===== CONFIG =====
API_TYPE = "TelegramDesktop"
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "306645446"))
SAVE_DIR = "uploaded_sessions"
os.makedirs(SAVE_DIR, exist_ok=True)

from aiogram.client.default import DefaultBotProperties

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ===== SESSION CHECKER =====
class SessionChecker:
    def __init__(self):
        self.banned_dir = "session-banned"
        self.frozen_dir = "session-frozen"
        self.error_dir = "session-error"
        for d in [self.banned_dir, self.frozen_dir, self.error_dir]:
            os.makedirs(d, exist_ok=True)

    async def safe_disconnect(self, client):
        if client:
            try:
                await client.disconnect()
            except:
                pass
            await asyncio.sleep(1)

    async def get_info(self, client):
        try:
            me = await client.get_me()
            auth_result = await client(functions.account.GetAuthorizationsRequest())
            current_auth = max(auth_result.authorizations, key=lambda x: x.date_created)
            now = datetime.now(current_auth.date_created.tzinfo)
            diff = now - current_auth.date_created
            days = diff.days
            return {
                'id': me.id,
                'phone': me.phone,
                'name': me.first_name or 'Tidak ada nama',
                'username': me.username or '—',
                'location': f"{current_auth.region}, {current_auth.country}",
                'age': f"{days} hari",
                'devices': len(auth_result.authorizations),
            }
        except:
            return None

    async def is_frozen(self, client):
        try:
            await client(functions.account.ResetAuthorizationRequest(hash=0))
            return False
        except RPCError as e:
            return "FROZEN_METHOD_INVALID" in str(e)

    def move(self, session, target):
        base = os.path.splitext(os.path.basename(session))[0]
        for ext in [".session", ".session-journal", ".json"]:
            f = os.path.join(SAVE_DIR, base + ext)
            if os.path.exists(f):
                shutil.move(f, os.path.join(target, os.path.basename(f)))

    async def check(self, path):
        try:
            api = API.TelegramMacOS.Generate() if API_TYPE == "TelegramMacOS" else API.TelegramDesktop.Generate()
            client = OpenteleClient(path, api=api)
            await client.connect()
            if not await client.is_user_authorized():
                await self.safe_disconnect(client)
                self.move(path, self.banned_dir)
                return "BANNED", None
            if await self.is_frozen(client):
                await self.safe_disconnect(client)
                self.move(path, self.frozen_dir)
                return "FROZEN", None
            info = await self.get_info(client)
            await self.safe_disconnect(client)
            return "ACTIVE", info
        except Exception:
            self.move(path, self.error_dir)
            return "ERROR", None

checker = SessionChecker()

# ===== HANDLER =====
@router.message(F.text == "/start")
async def start_cmd(msg: Message):
    if msg.from_user.id != OWNER_ID:
        return await msg.answer("❌ Kamu tidak punya izin untuk menggunakan bot ini.")
    await msg.answer("👋 Kirimkan file `.session` atau `.zip` berisi session untuk dicek.")

@router.message(F.content_type == ContentType.DOCUMENT)
async def handle_file(msg: Message):
    if msg.from_user.id != OWNER_ID:
        return await msg.answer("❌ Akses ditolak.")

    document: Document = msg.document
    filename = document.file_name
    file_path = os.path.join(SAVE_DIR, filename)
    await document.download(destination=file_path)

    if filename.endswith(".zip"):
        temp_extract = os.path.join(SAVE_DIR, "temp")
        os.makedirs(temp_extract, exist_ok=True)
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract)
        except:
            return await msg.answer("❌ Gagal mengekstrak ZIP.")

        reply = "📦 Hasil pengecekan:"
        found = False

        for root, _, files in os.walk(temp_extract):
            for f in files:
                if f.endswith(".session"):
                    found = True
                    session_path = os.path.join(root, f)
                    shutil.copy(session_path, os.path.join(SAVE_DIR, f))
                    status, info = await checker.check(os.path.join(SAVE_DIR, f))
                    if status == "ACTIVE":
                        reply += f"\n✅ `{info['phone']}` aktif - {info['name']}"
                    elif status == "BANNED":
                        reply += f"\n🚫 `{f}` banned"
                    elif status == "FROZEN":
                        reply += f"\n🛑 `{f}` frozen"
                    else:
                        reply += f"\n❌ `{f}` error"

        shutil.rmtree(temp_extract)
        os.remove(file_path)

        if not found:
            reply = "❌ Tidak ada file `.session` ditemukan dalam ZIP."
        return await msg.answer(reply)

    elif filename.endswith(".session"):
        status, info = await checker.check(file_path)
        if status == "ACTIVE":
            reply = (
                f"✅ **AKTIF**\n"
                f"• ID: `{info['id']}`\n"
                f"• Nomor: `{info['phone']}`\n"
                f"• Nama: {info['name']}\n"
                f"• Username: @{info['username']}\n"
                f"• Lokasi: {info['location']}\n"
                f"• Umur Akun: {info['age']}\n"
                f"• Perangkat lain: {info['devices']}"
            )
        elif status == "BANNED":
            reply = "🚫 Akun ini *BANNED*."
        elif status == "FROZEN":
            reply = "🛑 Akun ini *FROZEN*."
        else:
            reply = "❌ Gagal mengecek session. Format mungkin salah."
        return await msg.answer(reply)

    await msg.answer("❌ Format tidak dikenali. Kirim .session atau .zip.")

# ===== MAIN =====
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    async def main():
        await dp.start_polling(bot)

    asyncio.run(main())
