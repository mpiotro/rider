import asyncio
import json
import math
from collections.abc import Callable


class GameClientProtocol(asyncio.DatagramProtocol):
    """
    Asyncio-based UDP client for the game server.
    """

    def __init__(self, player_name: str):
        self.transport: asyncio.DatagramTransport = None  # type: ignore
        self.player_name = player_name
        self.server_addr: tuple[str, int] = None  # set in main
        self.handlers: list[Callable[[dict], None]] = []

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport
        print(f"UDP socket open, sending join as '{self.player_name}'")
        # Send join message
        join = {"action": "join", "player_name": self.player_name}
        self.send(join)

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        try:
            message = json.loads(data.decode())
        except json.JSONDecodeError:
            print(f"Received invalid JSON from {addr}: {data!r}")
            return

        # Dispatch to registered handlers
        for h in self.handlers:
            h(message)

    def error_received(self, exc: Exception):
        print("Error received:", exc)

    def connection_lost(self, exc: Exception):
        print("Socket closed")

    def send(self, message: dict):
        """Send a JSON message to the game server."""
        if not self.transport or not self.server_addr:
            print("Transport or server address not set")
            return
        raw = json.dumps(message).encode() + b"\n"
        self.transport.sendto(raw, self.server_addr)

    def register_handler(self, handler: Callable[[dict], None]):
        """Register a callback to handle incoming messages."""
        self.handlers.append(handler)


async def main(host: str = "127.0.0.1", port: int = 9999, player_name: str = "Rider1"):
    loop = asyncio.get_running_loop()

    # Instantiate protocol and define server address
    protocol = GameClientProtocol(player_name)
    protocol.server_addr = (host, port)

    # Create UDP endpoint; bind to any local port
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, remote_addr=(host, port)
    )

    # Example handler: print all messages
    def on_message(msg: dict):
        print("Received message:", msg)

    protocol.register_handler(on_message)

    # Example: send periodic moves
    try:
        x = 0
        while True:
            # Update position in a circle for demo purposes
            angle = x * 0.1
            pos = {"x": 5 * math.cos(angle), "y": 5 * math.sin(angle)}
            move = {"action": "move", "position": pos}
            protocol.send(move)
            x += 1
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        print("Sending leave and closing...")
        leave = {"action": "leave"}
        protocol.send(leave)
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())
