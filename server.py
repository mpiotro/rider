import asyncio
import logging
import os
import sys
import struct
import math

import arcade
import pymunk

from common.constants import SPRITE_SCALING_TILES, TRACK_FRICTION, SPRITE_SCALING_PLAYER, SCREEN_WIDTH, SCREEN_HEIGHT


# Damping - Amount of speed lost per second
DEFAULT_DAMPING = 1.0
PLAYER_DAMPING = 0.4

# Friction between objects
PLAYER_FRICTION = 1.0
WALL_FRICTION = 0.9
DYNAMIC_ITEM_FRICTION = 0.7
NO_FRICTION = 0.0

ROTATION_SPEED = 180  # degrees per second

# Mass (defaults to 1)
PLAYER_MASS = 6

# Keep player from going too fast
PLAYER_MAX_HORIZONTAL_SPEED = 2400
PLAYER_MAX_VERTICAL_SPEED = 2400

# Force applied while on the ground
THRUST_FORCE = 2800


PORT = 9999
SIM_FPS = 30
DT = 1.0 / SIM_FPS
MAX_PLAYERS = 4
PLAYER_MASS = 5

KEY_BIT_MAPPING = {
    "up": 0b001,
    "left": 0b010,
    "right": 0b100,
    # "boost": 0b1000,
}


class Player:
    def __init__(self, player_id, texture_path, pos_x=0, pos_y=0):
        self.id = player_id
        self.body = None
        self.sprite = arcade.Sprite(
            texture_path,
            SPRITE_SCALING_PLAYER,
            center_x=pos_x,
            center_y=pos_y
        )

        self.key_states = {"up": False, "left": False, "right": False, "down": False}


class RiderServerProtocol:
    def __init__(
        self,
        phys_engine: arcade.PymunkPhysicsEngine,
        client_map: dict,
    ):
        self.transport = None
        self.phys_engine = phys_engine
        self.client_map = client_map

        # Map name
        map_name = "assets/maps/rider.tmx"

        # Load in TileMap
        tile_map = arcade.load_tilemap(map_name, SPRITE_SCALING_TILES)

        # Pull the sprite layers out of the tile map
        self.background_list = tile_map.sprite_lists["ground"]
        self.track_list = tile_map.sprite_lists["track"]
        self.item_list = tile_map.sprite_lists["objects"]
        self.lines_list = tile_map.sprite_lists["lines"]

        # Create the items
        self.phys_engine.add_sprite_list(
            self.item_list,
            friction=DYNAMIC_ITEM_FRICTION,
            mass=60,
            collision_type="item",
            damping=0.4,
            elasticity=0.6,
        )

        space = self.phys_engine.space
        static_body = space.static_body

        # Grab your object‑layer polygons (already converted to Arcade TiledObject)
        for tiled_obj in tile_map.object_lists["walls"]:
            for a, b in zip(tiled_obj.shape, tiled_obj.shape[1:]):
                seg = pymunk.Segment(static_body, a, b, radius=1.0)
                seg.friction = WALL_FRICTION
                space.add(seg)



    def connection_made(self, transport):
        self.transport = transport
        sockname = transport.get_extra_info("sockname")
        print(f"Server listening on UDP {sockname}")

    def datagram_received(self, data, addr):

        if addr not in self.client_map:
            player_id = len(self.client_map)
            player = Player(
                player_id,
                "assets/rider_red.png",
                pos_x=200,
                pos_y=200,
            )
            self.client_map[addr] = player


            # Add the player.
            self.phys_engine.add_sprite(
                player.sprite,
                friction=PLAYER_FRICTION,
                mass=PLAYER_MASS,
                damping=PLAYER_DAMPING,
                moment_of_inertia=arcade.PymunkPhysicsEngine.MOMENT_INF,
                collision_type="player",
                max_horizontal_velocity=PLAYER_MAX_HORIZONTAL_SPEED,
                max_vertical_velocity=PLAYER_MAX_VERTICAL_SPEED,
            )

            player.body = self.phys_engine.get_physics_object(player.sprite).body

            # self.phys_engine.space.add(player.body, player.shape)

            self.transport.sendto(bytes([2, player_id]), addr)
            print(f"Assigned player {player_id} to {addr}")

        player = self.client_map[addr]
        if data and data[0] == 1 and len(data) >= 2:
            b = data[1]
            st = player.key_states
            st["up"] = bool(b & KEY_BIT_MAPPING["up"])
            st["left"] = bool(b & KEY_BIT_MAPPING["left"])
            st["right"] = bool(b & KEY_BIT_MAPPING["right"])

    @staticmethod
    def connection_lost(exc):
        print("Connection lost")


async def simulation_loop(phys_engine, client_map, transport):
    ANGULAR_TORQUE = math.radians(ROTATION_SPEED)
    ANGULAR_DAMPING = 1.0

    while True:
        # apply per‐player inputs
        for _, player in enumerate(client_map.values()):  # Unpack the tuple
            st = player.key_states
            body = player.body

            # Handle rotation input
            if st["left"] and not st["right"]:
                body.angular_velocity += ANGULAR_TORQUE * DT
            elif st["right"] and not st["left"]:
                body.angular_velocity -= ANGULAR_TORQUE * DT

            # Apply angular damping
            body.angular_velocity *= max(0, 1.0 - ANGULAR_DAMPING * DT)

            # Thrust
            if st["up"]:
                fx = math.cos(body.angle) * THRUST_FORCE
                fy = math.sin(body.angle) * THRUST_FORCE

                if st["left"]:
                    fx *= 0.5
                    fy *= 0.5
                elif st["right"]:
                    fx *= 0.2
                    fy *= 0.2

                player.body.apply_force_at_world_point((fx, fy), body.position)

            if st["up"] and st["down"]:
                fx = math.cos(body.angle) * THRUST_FORCE * 0.2
                fy = math.sin(body.angle) * THRUST_FORCE * 0.2
                body.apply_force_at_world_point((fx, fy), body.position)


        # advance physics
        phys_engine.step(DT)

        # build broadcast: type=3 + 4*(x,y,a)
        packed = []

        for _, player in enumerate(client_map.values()):
            if player.body:
                packed.extend([player.body.position.x, player.body.position.y, player.body.angle])
            else:
                packed.extend([0.0, 0.0, 0.0])

        while len(packed) < 3 * MAX_PLAYERS:
            packed.extend([100.0, 100.0, 0.0])

        payload = bytes([3]) + struct.pack("!" + "fff" * MAX_PLAYERS, *packed)

        # send to all known clients
        for addr in client_map:
            transport.sendto(payload, addr)

        await asyncio.sleep(DT)


async def main():
    print("Starting UDP server")

    phys_engine = arcade.PymunkPhysicsEngine(
            damping=DEFAULT_DAMPING, gravity=(0.0, 0.0)
        )

    client_map = {}

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: RiderServerProtocol(phys_engine, client_map),
        local_addr=("127.0.0.1", 9999),
    )

    asyncio.create_task(
        simulation_loop(phys_engine, client_map, transport)
    )

    try:
        await asyncio.Future()
    finally:
        transport.close()


asyncio.run(main())
