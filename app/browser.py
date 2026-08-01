import asyncio

# Chromium is memory-heavy; Railway should collect stores one at a time.
browser_semaphore = asyncio.Semaphore(1)
