from aiogram import Router
from handlers.common import router as common_router
from . import deadlines, debug, menu, schedule, start


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(menu.router)
    root.include_router(schedule.router)
    root.include_router(deadlines.router)
    root.include_router(debug.router)
    root.include_router(common_router)
    return root
