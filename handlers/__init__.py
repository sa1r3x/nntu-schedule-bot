from aiogram import Router

from . import deadlines, debug, menu, schedule, start


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(menu.router)
    root.include_router(schedule.router)
    root.include_router(deadlines.router)
    root.include_router(debug.router)
    return root
