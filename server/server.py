import asyncio
import json
import logging


class GameServer(asyncio.DatagramProtocol):
    """
    Asyncio-based UDP game server
    """

    def __init__(self):
        self.transport = None
        self.clients = {}

    def connection_made(self, transport):
        self.transport = transport
        socket_name = transport.get_extra_info("sockname")
        print(f"UDP game server listening on {socket_name}")

    def datagram_received(self, data, addr):
        try:
            message = json.loads(data.decode())
        except json.JSONDecodeError:
            print(f"Invalid JSON from {addr}: {data!r}")
            return

        action = message.get("action")

        if action == "join":
            self._handle_join(message, addr)
        elif action == "move":
            self._handle_move(message, addr)
        elif action == "leave":
            self._handle_leave(addr)
        else:
            self._handle_unknown_action(action, addr)

    def _handle_join(self, message, addr):
        """Handle the 'join' action."""
        name = message.get("player_name", "Anonymous")
        self.clients[addr] = name
        print(f"Player joined: {name} at {addr}")

        join_msg = {"action": "player_joined", "player_name": name}
        self._broadcast(join_msg)

        welcome = {"action": "welcome", "message": f"Welcome, {name}!"}
        self._send(welcome, addr)

    def _handle_move(self, message, addr):
        """Handle the 'move' action."""
        name = self.clients.get(addr, "Unknown")
        position = message.get("position")
        move_msg = {
            "action": "player_move",
            "player_name": name,
            "position": position,
        }
        self._broadcast(move_msg)

    def _handle_leave(self, addr):
        """Handle the 'leave' action."""
        name = self.clients.pop(addr, None)
        print(f"Player left: {name} from {addr}")
        leave_msg = {"action": "player_left", "player_name": name}
        self._broadcast(leave_msg)

    def _handle_unknown_action(self, action, addr):
        """Handle unknown actions."""
        error = {"action": "error", "message": f"Unknown action: {action}"}
        self._send(error, addr)

    def _send(self, message: dict, addr):
        """Send a JSON message to a single client."""
        raw = json.dumps(message).encode() + b"\n"
        self.transport.sendto(raw, addr)

    def _broadcast(self, message: dict):
        """Broadcast a JSON message to all connected clients."""
        raw = json.dumps(message).encode() + b"\n"
        for client_addr in list(self.clients.keys()):
            try:
                self.transport.sendto(raw, client_addr)
            except Exception:
                logging.warning(f"Failed to send message to {client_addr}")


async def main(host: str = "0.0.0.0", port: int = 9999):
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting UDP game server...")

    loop = asyncio.get_running_loop()

    # Create the UDP endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        GameServer, local_addr=(host, port)
    )

    try:
        # Run until cancelled
        await asyncio.sleep(float("inf"))
    except KeyboardInterrupt:
        print("Shutting down server...")
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())
