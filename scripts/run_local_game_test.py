"""Run the private game flows with the dedicated local test bot."""

import asyncio

from scripts.run_local_car_test import main

if __name__ == "__main__":
    asyncio.run(main())
