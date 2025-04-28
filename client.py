import asyncio
import struct
import threading
import arcade
import math
import sys
import os

import threading

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)

# — CONFIG —
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9999
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
MAX_PLAYERS = 4
SPRITE_IMAGES = [
    "assets/rider_red.png",
    "assets/rider_red.png",
    "assets/rider_red.png",
    "assets/rider_red.png",
]

SCREEN_TITLE = "Rider"

# How big are our image tiles?
SPRITE_IMAGE_SIZE = 32

# Scale sprites up or down
SPRITE_SCALING_PLAYER = 1
SPRITE_SCALING_TILES = 1

# Scaled sprite size for tiles
SPRITE_SIZE = int(SPRITE_IMAGE_SIZE * SPRITE_SCALING_PLAYER)

# Size of grid to show on screen, in number of tiles
SCREEN_GRID_WIDTH = 25
SCREEN_GRID_HEIGHT = 15

# Size of screen to show, in pixels
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1024

# --- Physics forces. Higher number, faster accelerating.

# Gravity
GRAVITY = 0.0

# Damping - Amount of speed lost per second
DEFAULT_DAMPING = 1.0
PLAYER_DAMPING = 0.4

# Friction between objects
PLAYER_FRICTION = 1.0
WALL_FRICTION = 0.9
DYNAMIC_ITEM_FRICTION = 0.7
TRACK_FRICTION = 0.5
NO_FRICTION = 0.0

ROTATION_SPEED = 180  # degrees per second

# Mass (defaults to 1)
PLAYER_MASS = 6

# Keep player from going too fast
PLAYER_MAX_HORIZONTAL_SPEED = 2400
PLAYER_MAX_VERTICAL_SPEED = 2400

# Force applied while on the ground
THRUST_FORCE = 2800

# Networking
SEND_INTERVAL = 1.0 / 30.0  # Send inputs at 30Hz

recv_lock = threading.Lock()

class NetworkClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, recv_states, info):
        self.recv_states = recv_states  # list of dicts
        self.info = info  # {'id': None}


    def connection_made(self, transport):
        self.transport = transport
        print(f"Connected to server {SERVER_HOST}:{SERVER_PORT}")

    def datagram_received(self, data, addr):
        if not data:
            return
        t = data[0]
        if t == 2 and len(data) >= 2:
            self.info["id"] = data[1]
        elif t == 3 and len(data) == 1 + 12 * MAX_PLAYERS:
            floats = struct.unpack("!" + "fff" * MAX_PLAYERS, data[1:])
            for i in range(MAX_PLAYERS):
                x, y, a = floats[i * 3: (i + 1) * 3]
                self.recv_states[i]["target_x"] = x
                self.recv_states[i]["target_y"] = y
                self.recv_states[i]["target_angle"] = a


    def error_received(self, exc):
        print("Network error:", exc)


class ClientWindow(arcade.Window):
    # def __init__(self):
    #     super().__init__(WINDOW_WIDTH, WINDOW_HEIGHT, "Speedway (4-Player)")
    #     # key flags (this player only)
    #     self.keys = {"up": False, "left": False, "right": False}
    #     # incoming positions for all players
    #     self.recv_states = [
    #         {"x": WINDOW_WIDTH / 2, "y": WINDOW_HEIGHT / 2, "angle": 0.0}
    #         for _ in range(MAX_PLAYERS)
    #     ]
    #     self.info = {"id": None}
    #
    #     # create a sprite for each slot
    #     self.sprites = arcade.SpriteList()
    #     for img in SPRITE_IMAGES:
    #         s = arcade.Sprite(img, scale=0.5)
    #         self.sprites.append(s)
    #
    #     # start network thread
    #     self.transport = None
    #     threading.Thread(target=self._start_network, daemon=True).start()

    """Main Window"""

    def __init__(self, width, height, title):
        """Create the variables"""

        # Init the parent class
        super().__init__(width, height, title)

        # Player sprite
        self.player_sprite: arcade.Sprite | None = None

        # Sprite lists we need
        self.player_list: arcade.SpriteList | None = None
        self.background_list: arcade.SpriteList | None = None
        self.track_list: arcade.SpriteList | None = None
        self.lines_list: arcade.SpriteList | None = None
        self.wall_list: arcade.SpriteList | None = None
        self.item_list: arcade.SpriteList | None = None
        self.trace_list: arcade.SpriteList | None = None
        self.inner_list: arcade.SpriteList | None = None

        # Player textures for different angular velocities
        self.player_textures: list[arcade.Texture] = []

        # Track the current state of what key is pressed
        self.left_pressed: bool = False
        self.right_pressed: bool = False
        self.up_pressed: bool = False
        self.down_pressed: bool = False

        self.keys = {"up": False, "left": False, "right": False}

        # Set background color
        self.background_color = arcade.color.AMAZON

        self.left_timer = 0.0

        # incoming positions for all players
        self.recv_states = [
            {
                "x": WINDOW_WIDTH / 2,
                "y": WINDOW_HEIGHT / 2,
                "angle": 0.0,
                "target_x": WINDOW_WIDTH / 2,
                "target_y": WINDOW_HEIGHT / 2,
                "target_angle": 0.0,
            }
            for _ in range(MAX_PLAYERS)
        ]
        self.recv_lock = threading.Lock()
        self.info = {"id": None}

        # Networking
        self.transport = None
        threading.Thread(target=self._start_network, daemon=True).start()

        # Time tracking for network send
        self.send_timer = 0.0



    def setup(self):
        """Set up everything with the game"""

        # Create the sprite lists
        self.player_list = arcade.SpriteList()
        # Map name
        map_name = "assets/maps/rider.tmx"

        # Load in TileMap
        tile_map = arcade.load_tilemap(map_name, SPRITE_SCALING_TILES)

        self.trace_list = arcade.SpriteList()  # Initialize the trace list

        # Pull the sprite layers out of the tile map
        self.background_list = tile_map.sprite_lists["ground"]
        self.track_list = tile_map.sprite_lists["track"]
        self.item_list = tile_map.sprite_lists["objects"]
        self.lines_list = tile_map.sprite_lists["lines"]
        self.inner_list = tile_map.sprite_lists["Inner"]

        # Create player sprite with default texture
        self.player_sprite = arcade.Sprite(
            "assets/rider_red.png",
            SPRITE_SCALING_PLAYER,
        )

        # Load alternative textures
        # self.player_textures = [
        #     arcade.load_texture("assets/rider_red_right_1.png"),
        #     arcade.load_texture("assets/rider_red.png"),
        #     arcade.load_texture("assets/rider_red_left_1.png"),
        #     arcade.load_texture("assets/rider_red_left_2.png"),
        #     arcade.load_texture("assets/rider_red_left_3.png"),
        #     arcade.load_texture("assets/rider_red_left_4.png"),
        #     arcade.load_texture("assets/rider_red_left_5.png"),
        # ]

        self.player_list.append(self.player_sprite)

        self.player_list.append(arcade.Sprite(
            "assets/rider_red.png",
            SPRITE_SCALING_PLAYER
        ))

        self.player_list.append(arcade.Sprite(
            "assets/rider_red.png",
            SPRITE_SCALING_PLAYER
        ))

        self.player_list.append(arcade.Sprite(
            "assets/rider_red.png",
            SPRITE_SCALING_PLAYER
        ))


    def _start_network(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        conn = loop.create_datagram_endpoint(
            lambda: NetworkClientProtocol(self.recv_states, self.info),
            remote_addr=(SERVER_HOST, SERVER_PORT),
        )
        self.transport, _ = loop.run_until_complete(conn)
        loop.run_forever()

    def on_key_press(self, key, mods):
        if key == arcade.key.UP:
            self.keys["up"] = True
        if key == arcade.key.LEFT:
            self.keys["left"] = True
        if key == arcade.key.RIGHT:
            self.keys["right"] = True

    def on_key_release(self, key, mods):
        if key == arcade.key.UP:
            self.keys["up"] = False
        if key == arcade.key.LEFT:
            self.keys["left"] = False
        if key == arcade.key.RIGHT:
            self.keys["right"] = False

    def on_update(self, dt):
        # Smooth interpolation factor
        interpolation_factor = 0.2  # tune this if needed

        with self.recv_lock:
            for i, sprite in enumerate(self.player_list):
                st = self.recv_states[i]
                # Interpolate position
                st["x"] += (st["target_x"] - st["x"]) * interpolation_factor
                st["y"] += (st["target_y"] - st["y"]) * interpolation_factor
                st["angle"] += (st["target_angle"] - st["angle"]) * interpolation_factor

                # Apply to sprite
                sprite.center_x = st["x"]
                sprite.center_y = st["y"]
                sprite.angle = -math.degrees(st["angle"])

        # Network input send throttling
        self.send_timer += dt
        if self.send_timer >= SEND_INTERVAL:
            self.send_timer = 0.0
            if self.transport:
                b = (
                        (1 if self.keys["up"] else 0) << 0
                        | (1 if self.keys["left"] else 0) << 1
                        | (1 if self.keys["right"] else 0) << 2
                )
                self.transport.sendto(bytes([1, b]))

    def on_draw(self):
        """Draw everything"""
        self.clear()

        self.background_list.draw()
        self.track_list.draw()
        self.item_list.draw()
        self.inner_list.draw()
        self.lines_list.draw()
        self.trace_list.draw()
        self.player_list.draw()


def main():
    window = ClientWindow(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    window.setup()
    arcade.run()


if __name__ == "__main__":
    main()
